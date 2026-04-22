import json, os, uuid
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, UploadFile, File, Header
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from database import init_db, get_db
from auth import register_user, login_user, get_current_user
from chats import get_user_chats, get_chat_messages, save_message, get_all_users, create_or_get_dm
from checklist import get_checklist, toggle_task, add_template_item, delete_template_item, reset_daily_completions, can_edit_checklist
from news import get_events, add_event, delete_event, can_edit_news
from tasks import can_create_tasks, get_assignable_users, create_task, get_tasks, complete_task, delete_task
from knowledge import (can_edit_knowledge, get_cocktails, get_cocktail,
                       add_cocktail, update_cocktail, delete_cocktail,
                       toggle_favorite, CATEGORIES)
from menu import (can_edit as can_edit_menu, get_menu_cocktails, get_menu_cocktail,
                  add_menu_cocktail, update_menu_cocktail, delete_menu_cocktail,
                  toggle_menu_favorite, MENU_CATEGORIES)

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.add_job(reset_daily_completions, "cron", hour=3, minute=0)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title="Svoi Bar", lifespan=lifespan)
os.makedirs("uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

MAX_FILE_SIZE = 25 * 1024 * 1024
IMAGE_EXTENSIONS = {'.jpg','.jpeg','.png','.gif','.webp','.heic','.heif','.bmp','.svg'}
VIDEO_EXTENSIONS = {'.mp4','.mov','.avi','.webm','.mkv'}


class ConnectionManager:
    def __init__(self):
        self.active: dict[int, list] = {}
        self.online_users: set[int] = set()

    async def connect(self, ws: WebSocket, chat_id: int, user: dict):
        await ws.accept()
        if chat_id not in self.active: self.active[chat_id] = []
        self.active[chat_id].append((ws, user))
        self.online_users.add(user["id"])

    def disconnect(self, ws: WebSocket, chat_id: int):
        if chat_id in self.active:
            self.active[chat_id] = [(w, u) for w, u in self.active[chat_id] if w != ws]
        ids = set()
        for conns in self.active.values():
            for _, u in conns: ids.add(u["id"])
        self.online_users = ids

    async def broadcast(self, chat_id: int, message: dict):
        if chat_id not in self.active: return
        for ws, _ in self.active[chat_id]:
            try: await ws.send_json(message)
            except: pass

    def get_online_names(self, chat_id: int) -> list:
        if chat_id not in self.active: return []
        return [u["display_name"] for _, u in self.active[chat_id]]

    def get_online_ids(self) -> set:
        return self.online_users


manager = ConnectionManager()


def _auth(request: Request) -> dict | None:
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "): return None
    return get_current_user(h.split(" ")[1])


# === WebSocket ===
@app.websocket("/ws/{chat_id}")
async def ws_endpoint(websocket: WebSocket, chat_id: int):
    token = websocket.query_params.get("token", "")
    user = get_current_user(token)
    if not user:
        await websocket.accept(); await websocket.close(code=4001); return

    await manager.connect(websocket, chat_id, user)
    await manager.broadcast(chat_id, {"type": "user_joined", "user": user["display_name"], "online": manager.get_online_names(chat_id)})

    try:
        while True:
            data = json.loads(await websocket.receive_text())
            if data.get("type") == "typing":
                await manager.broadcast(chat_id, {"type": "typing", "user": user["display_name"], "user_id": user["id"]})
                continue
            content = data.get("content", "").strip()
            if not content: continue
            saved = save_message(chat_id, user["id"], content)
            await manager.broadcast(chat_id, {
                "type": "message", "id": saved["id"], "content": saved["content"],
                "message_type": saved["message_type"], "file_path": saved["file_path"],
                "user_id": saved["user_id"], "display_name": saved["display_name"],
                "role": saved["role"], "created_at": saved["created_at"],
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket, chat_id)
        await manager.broadcast(chat_id, {"type": "user_left", "user": user["display_name"], "online": manager.get_online_names(chat_id)})


# === Auth ===
@app.post("/api/register")
async def api_register(request: Request):
    data = await request.json()
    u, d, p = data.get("username","").strip(), data.get("display_name","").strip(), data.get("password","")
    if not u or not d or not p: return JSONResponse({"error": "Заполни все поля"}, status_code=400)
    if len(p) < 4: return JSONResponse({"error": "Пароль минимум 4 символа"}, status_code=400)
    result = register_user(u, d, p, data.get("role", "bartender"))
    if "error" in result: return JSONResponse(result, status_code=400)
    return result

@app.post("/api/login")
async def api_login(request: Request):
    data = await request.json()
    u, p = data.get("username","").strip(), data.get("password","")
    if not u or not p: return JSONResponse({"error": "Заполни все поля"}, status_code=400)
    result = login_user(u, p)
    if "error" in result: return JSONResponse(result, status_code=401)
    return result

@app.get("/api/me")
async def api_me(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    return user

@app.get("/api/online")
async def api_online():
    return {"online_ids": list(manager.get_online_ids())}


# === Chats ===
@app.get("/api/chats")
async def api_chats(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    return get_user_chats(user["id"])

@app.get("/api/chats/{chat_id}/messages")
async def api_messages(chat_id: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    return get_chat_messages(chat_id)

@app.post("/api/chats/{chat_id}/upload")
async def api_upload(chat_id: int, file: UploadFile = File(...), authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    user = get_current_user(authorization.split(" ")[1])
    if not user: return JSONResponse({"error": "Токен недействителен"}, status_code=401)

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        return JSONResponse({"error": "Файл слишком большой (макс. 25 МБ)"}, status_code=400)

    ext = os.path.splitext(file.filename or "file")[1].lower()
    unique = f"uploads/{uuid.uuid4().hex[:12]}{ext}"
    with open(unique, "wb") as f: f.write(contents)

    msg_type = "image" if ext in IMAGE_EXTENSIONS else "video" if ext in VIDEO_EXTENSIONS else "file"
    saved = save_message(chat_id, user["id"], file.filename or "file", msg_type, f"/{unique}")
    await manager.broadcast(chat_id, {
        "type": "message", "id": saved["id"], "content": saved["content"],
        "message_type": saved["message_type"], "file_path": saved["file_path"],
        "user_id": saved["user_id"], "display_name": saved["display_name"],
        "role": saved["role"], "created_at": saved["created_at"],
    })
    return {"id": saved["id"], "file_path": saved["file_path"], "message_type": msg_type}


# === Search ===
@app.get("/api/search")
async def api_search(request: Request, q: str = ""):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if len(q) < 2: return {"results": []}
    conn = get_db()
    rows = conn.execute("""
        SELECT m.id, m.content, m.chat_id, m.created_at, u.display_name, c.name as chat_name
        FROM messages m JOIN users u ON u.id = m.user_id JOIN chats c ON c.id = m.chat_id
        WHERE m.content LIKE ? AND m.message_type = 'text' ORDER BY m.created_at DESC LIMIT 30
    """, (f"%{q}%",)).fetchall()
    conn.close()
    return {"results": [dict(r) for r in rows]}


# === Pins ===
@app.get("/api/chats/{chat_id}/pins")
async def api_pins(chat_id: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    conn = get_db()
    rows = conn.execute("""
        SELECT m.id, m.content, m.message_type, m.created_at, u.display_name
        FROM pinned_messages p JOIN messages m ON m.id = p.message_id JOIN users u ON u.id = m.user_id
        WHERE p.chat_id = ? ORDER BY p.pinned_at DESC
    """, (chat_id,)).fetchall()
    conn.close()
    return {"pins": [dict(r) for r in rows]}

@app.post("/api/chats/{chat_id}/pin/{message_id}")
async def api_pin(chat_id: int, message_id: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO pinned_messages (chat_id, message_id, pinned_by) VALUES (?, ?, ?)", (chat_id, message_id, user["id"]))
    conn.commit(); conn.close()
    return {"pinned": True}

@app.delete("/api/chats/{chat_id}/pin/{message_id}")
async def api_unpin(chat_id: int, message_id: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    conn = get_db()
    conn.execute("DELETE FROM pinned_messages WHERE chat_id = ? AND message_id = ?", (chat_id, message_id))
    conn.commit(); conn.close()
    return {"unpinned": True}


# === DM ===
@app.get("/api/users")
async def api_users(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    return get_all_users(exclude_id=user["id"])

@app.post("/api/dm")
async def api_dm(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    uid = data.get("user_id")
    if not uid: return JSONResponse({"error": "user_id обязателен"}, status_code=400)
    result = create_or_get_dm(user["id"], uid)
    if "error" in result: return JSONResponse(result, status_code=400)
    return result


# === Checklist ===
@app.get("/api/checklist")
async def api_checklist(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = get_checklist()
    data["can_edit"] = can_edit_checklist(user["role"])
    return data

@app.post("/api/checklist/toggle")
async def api_cl_toggle(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    result = toggle_task(data.get("template_id"), user["id"])
    if "error" in result: return JSONResponse(result, status_code=400)
    return result

@app.post("/api/checklist/template")
async def api_cl_add(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if not can_edit_checklist(user["role"]): return JSONResponse({"error": "Нет прав"}, status_code=403)
    data = await request.json()
    result = add_template_item(data.get("section","opening"), data.get("title",""), data.get("detail",""))
    if "error" in result: return JSONResponse(result, status_code=400)
    return result

@app.delete("/api/checklist/template/{tid}")
async def api_cl_del(tid: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if not can_edit_checklist(user["role"]): return JSONResponse({"error": "Нет прав"}, status_code=403)
    result = delete_template_item(tid)
    if "error" in result: return JSONResponse(result, status_code=400)
    return result


# === News ===
@app.get("/api/events")
async def api_events(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    return {"events": get_events(), "can_edit": can_edit_news(user["role"])}

@app.post("/api/events")
async def api_add_event(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if not can_edit_news(user["role"]): return JSONResponse({"error": "Нет прав"}, status_code=403)
    d = await request.json()
    result = add_event(d.get("event_date",""), d.get("event_time","20:00"), d.get("title",""), d.get("description",""), d.get("genre",""), d.get("entry_fee",""))
    if "error" in result: return JSONResponse(result, status_code=400)
    return result

@app.delete("/api/events/{eid}")
async def api_del_event(eid: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if not can_edit_news(user["role"]): return JSONResponse({"error": "Нет прав"}, status_code=403)
    result = delete_event(eid)
    if "error" in result: return JSONResponse(result, status_code=400)
    return result


# === Tasks ===
@app.get("/api/tasks")
async def api_tasks(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    return {"tasks": get_tasks(user), "can_create": can_create_tasks(user["role"])}

@app.get("/api/tasks/users")
async def api_task_users(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if not can_create_tasks(user["role"]): return JSONResponse({"error": "Нет прав"}, status_code=403)
    return get_assignable_users(user)

@app.post("/api/tasks")
async def api_create_task(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if not can_create_tasks(user["role"]): return JSONResponse({"error": "Нет прав"}, status_code=403)
    d = await request.json()
    result = create_task(d.get("title",""), user["id"], d.get("assigned_to"), d.get("detail",""), d.get("priority","normal"), d.get("deadline",""))
    if "error" in result: return JSONResponse(result, status_code=400)
    return result

@app.post("/api/tasks/{tid}/toggle")
async def api_task_toggle(tid: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    result = complete_task(tid, user["id"])
    if "error" in result: return JSONResponse(result, status_code=400)
    return result

@app.delete("/api/tasks/{tid}")
async def api_task_del(tid: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    result = delete_task(tid, user["id"])
    if "error" in result: return JSONResponse(result, status_code=400)
    return result


# === Knowledge (Cocktail Tech Cards) ===
@app.get("/api/cocktails")
async def api_cocktails(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    return {
        "cocktails": get_cocktails(user["id"]),
        "can_edit": can_edit_knowledge(user["role"]),
        "categories": CATEGORIES,
    }

@app.get("/api/cocktails/{cid}")
async def api_cocktail(cid: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    c = get_cocktail(cid, user["id"])
    if not c: return JSONResponse({"error": "Не найден"}, status_code=404)
    return c

@app.post("/api/cocktails")
async def api_add_cocktail(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if not can_edit_knowledge(user["role"]): return JSONResponse({"error": "Нет прав"}, status_code=403)
    d = await request.json()
    result = add_cocktail(
        name=d.get("name",""), glass=d.get("glass",""), garnish=d.get("garnish",""),
        method=d.get("method",""), ingredients=d.get("ingredients",[]),
        instructions=d.get("instructions",""), created_by=user["id"],
        photo_path=d.get("photo_path",""), category=d.get("category","Классика"),
    )
    if "error" in result: return JSONResponse(result, status_code=400)
    return result

@app.put("/api/cocktails/{cid}")
async def api_update_cocktail(cid: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if not can_edit_knowledge(user["role"]): return JSONResponse({"error": "Нет прав"}, status_code=403)
    d = await request.json()
    result = update_cocktail(
        cid,
        name=d.get("name"), glass=d.get("glass"), garnish=d.get("garnish"),
        method=d.get("method"), ingredients=d.get("ingredients"),
        instructions=d.get("instructions"), category=d.get("category"),
    )
    if "error" in result: return JSONResponse(result, status_code=400)
    return result

@app.post("/api/cocktails/{cid}/favorite")
async def api_toggle_favorite(cid: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    return toggle_favorite(user["id"], cid)

@app.post("/api/cocktails/{cid}/photo")
async def api_cocktail_photo(cid: int, file: UploadFile = File(...), authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    user = get_current_user(authorization.split(" ")[1])
    if not user: return JSONResponse({"error": "Токен недействителен"}, status_code=401)
    if not can_edit_knowledge(user["role"]): return JSONResponse({"error": "Нет прав"}, status_code=403)

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        return JSONResponse({"error": "Файл слишком большой"}, status_code=400)
    ext = os.path.splitext(file.filename or "photo.jpg")[1].lower()
    unique = f"uploads/cocktail_{cid}_{uuid.uuid4().hex[:8]}{ext}"
    with open(unique, "wb") as f: f.write(contents)
    update_cocktail(cid, photo_path=f"/{unique}")
    return {"photo_path": f"/{unique}"}

@app.delete("/api/cocktails/{cid}")
async def api_del_cocktail(cid: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if not can_edit_knowledge(user["role"]): return JSONResponse({"error": "Нет прав"}, status_code=403)
    result = delete_cocktail(cid)
    if "error" in result: return JSONResponse(result, status_code=400)
    return result




# === Menu Cocktails ===
@app.get("/api/menu")
async def api_menu(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    return {"cocktails": get_menu_cocktails(user["id"]), "can_edit": can_edit_menu(user["role"]), "categories": MENU_CATEGORIES}

@app.post("/api/menu")
async def api_add_menu(request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if not can_edit_menu(user["role"]): return JSONResponse({"error": "Нет прав"}, status_code=403)
    d = await request.json()
    result = add_menu_cocktail(
        name=d.get("name",""), glass=d.get("glass",""), garnish=d.get("garnish",""),
        method=d.get("method",""), ingredients=d.get("ingredients",[]),
        instructions=d.get("instructions",""), created_by=user["id"],
        photo_path=d.get("photo_path",""), category=d.get("category","Классика из меню"),
    )
    if "error" in result: return JSONResponse(result, status_code=400)
    return result

@app.put("/api/menu/{cid}")
async def api_update_menu(cid: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if not can_edit_menu(user["role"]): return JSONResponse({"error": "Нет прав"}, status_code=403)
    d = await request.json()
    result = update_menu_cocktail(cid, name=d.get("name"), glass=d.get("glass"), garnish=d.get("garnish"),
        method=d.get("method"), ingredients=d.get("ingredients"), instructions=d.get("instructions"), category=d.get("category"))
    if "error" in result: return JSONResponse(result, status_code=400)
    return result

@app.post("/api/menu/{cid}/favorite")
async def api_menu_favorite(cid: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    return toggle_menu_favorite(user["id"], cid)

@app.post("/api/menu/{cid}/photo")
async def api_menu_photo(cid: int, file: UploadFile = File(...), authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    user = get_current_user(authorization.split(" ")[1])
    if not user: return JSONResponse({"error": "Токен недействителен"}, status_code=401)
    if not can_edit_menu(user["role"]): return JSONResponse({"error": "Нет прав"}, status_code=403)
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE: return JSONResponse({"error": "Файл слишком большой"}, status_code=400)
    ext = os.path.splitext(file.filename or "photo.jpg")[1].lower()
    unique = f"uploads/menu_{cid}_{uuid.uuid4().hex[:8]}{ext}"
    with open(unique, "wb") as f: f.write(contents)
    update_menu_cocktail(cid, photo_path=f"/{unique}")
    return {"photo_path": f"/{unique}"}

@app.delete("/api/menu/{cid}")
async def api_del_menu(cid: int, request: Request):
    user = _auth(request)
    if not user: return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if not can_edit_menu(user["role"]): return JSONResponse({"error": "Нет прав"}, status_code=403)
    result = delete_menu_cocktail(cid)
    if "error" in result: return JSONResponse(result, status_code=400)
    return result

# === Home ===
@app.get("/", response_class=HTMLResponse)
async def home():
    return FileResponse("static/index.html")
