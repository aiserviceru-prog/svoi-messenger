import json
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from database import init_db, get_db
from auth import register_user, login_user, get_current_user
from chats import init_chats, get_user_chats, get_chat_messages, save_message

app = FastAPI(title="Svoi Messenger")

# Создаём таблицы и чаты при запуске
init_db()
init_chats()


# === WebSocket: хранилище активных подключений ===
class ConnectionManager:
    def __init__(self):
        self.active: dict[int, list] = {}

    async def connect(self, websocket: WebSocket, chat_id: int, user: dict):
        await websocket.accept()
        if chat_id not in self.active:
            self.active[chat_id] = []
        self.active[chat_id].append((websocket, user))

    def disconnect(self, websocket: WebSocket, chat_id: int):
        if chat_id in self.active:
            self.active[chat_id] = [
                (ws, u) for ws, u in self.active[chat_id] if ws != websocket
            ]

    async def broadcast(self, chat_id: int, message: dict):
        if chat_id not in self.active:
            return
        for ws, user in self.active[chat_id]:
            try:
                await ws.send_json(message)
            except:
                pass

    def get_online_users(self, chat_id: int) -> list:
        if chat_id not in self.active:
            return []
        return [u["display_name"] for _, u in self.active[chat_id]]


manager = ConnectionManager()


# === WebSocket endpoint ===
@app.websocket("/ws/{chat_id}")
async def websocket_endpoint(websocket: WebSocket, chat_id: int):
    token = websocket.query_params.get("token", "")

    user = get_current_user(token)
    if not user:
        await websocket.accept()
        await websocket.close(code=4001)
        return

    await manager.connect(websocket, chat_id, user)

    await manager.broadcast(
        chat_id,
        {
            "type": "user_joined",
            "user": user["display_name"],
            "online": manager.get_online_users(chat_id),
        },
    )

    try:
        while True:
            data = await websocket.receive_text()
            msg_data = json.loads(data)
            content = msg_data.get("content", "").strip()

            if not content:
                continue

            saved = save_message(chat_id, user["id"], content)

            await manager.broadcast(
                chat_id,
                {
                    "type": "message",
                    "id": saved["id"],
                    "content": saved["content"],
                    "user_id": saved["user_id"],
                    "display_name": saved["display_name"],
                    "role": saved["role"],
                    "created_at": saved["created_at"],
                },
            )

    except WebSocketDisconnect:
        manager.disconnect(websocket, chat_id)
        await manager.broadcast(
            chat_id,
            {
                "type": "user_left",
                "user": user["display_name"],
                "online": manager.get_online_users(chat_id),
            },
        )


# === API: Регистрация ===
@app.post("/api/register")
async def api_register(request: Request):
    data = await request.json()
    username = data.get("username", "").strip()
    display_name = data.get("display_name", "").strip()
    password = data.get("password", "")
    role = data.get("role", "waiter")
    venue_id = data.get("venue_id")

    if not username or not display_name or not password:
        return JSONResponse({"error": "Заполни все поля"}, status_code=400)

    if len(password) < 4:
        return JSONResponse({"error": "Пароль минимум 4 символа"}, status_code=400)

    result = register_user(username, display_name, password, role, venue_id)
    if "error" in result:
        return JSONResponse(result, status_code=400)

    return result


# === API: Вход ===
@app.post("/api/login")
async def api_login(request: Request):
    data = await request.json()
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return JSONResponse({"error": "Заполни все поля"}, status_code=400)

    result = login_user(username, password)
    if "error" in result:
        return JSONResponse(result, status_code=401)

    return result


# === API: Текущий пользователь ===
@app.get("/api/me")
async def api_me(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"error": "Не авторизован"}, status_code=401)

    token = auth_header.split(" ")[1]
    user = get_current_user(token)
    if not user:
        return JSONResponse({"error": "Токен недействителен"}, status_code=401)

    return user


# === API: Список заведений ===
@app.get("/api/venues")
async def api_venues():
    conn = get_db()
    venues = conn.execute("SELECT id, name, emoji FROM venues").fetchall()
    conn.close()
    return [dict(v) for v in venues]


# === API: Мои чаты ===
@app.get("/api/chats")
async def api_chats(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"error": "Не авторизован"}, status_code=401)

    token = auth_header.split(" ")[1]
    user = get_current_user(token)
    if not user:
        return JSONResponse({"error": "Токен недействителен"}, status_code=401)

    chats = get_user_chats(user["id"])
    return chats


# === API: Сообщения чата ===
@app.get("/api/chats/{chat_id}/messages")
async def api_chat_messages(chat_id: int, request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"error": "Не авторизован"}, status_code=401)

    token = auth_header.split(" ")[1]
    user = get_current_user(token)
    if not user:
        return JSONResponse({"error": "Токен недействителен"}, status_code=401)

    messages = get_chat_messages(chat_id)
    return messages


# === Главная страница — мессенджер ===
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Svoi Messenger</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0c0a15; color: #e2e8f0; height: 100vh; overflow: hidden; }

            #authScreen { display: flex; align-items: center; justify-content: center; height: 100vh; }
            .auth-container { width: 100%; max-width: 380px; padding: 24px; }
            .logo { text-align: center; margin-bottom: 32px; }
            .logo .icon { font-size: 48px; }
            .logo h1 { font-size: 24px; margin-top: 8px; }
            .logo h1 span { color: #f59e0b; }
            .logo p { color: #7c7a9a; font-size: 13px; margin-top: 4px; }

            .tabs { display: flex; gap: 4px; margin-bottom: 24px; background: #1e1838; border-radius: 10px; padding: 4px; }
            .tab { flex: 1; padding: 10px; text-align: center; border: none; background: transparent; color: #7c7a9a; font-size: 14px; font-weight: 700; border-radius: 8px; cursor: pointer; font-family: inherit; }
            .tab.active { background: #2a2248; color: #f59e0b; }

            .form { display: flex; flex-direction: column; gap: 12px; }
            .form.hidden { display: none; }
            .input { padding: 12px 16px; background: #16122a; border: 1.5px solid #2a2248; border-radius: 10px; color: #e2e8f0; font-size: 14px; outline: none; font-family: inherit; }
            .input:focus { border-color: #f59e0b; }
            .input::placeholder { color: #4a4568; }
            select.input { cursor: pointer; }
            select.input option { background: #16122a; color: #e2e8f0; }

            .btn { padding: 12px; background: #f59e0b; color: #0c0a15; border: none; border-radius: 10px; font-size: 15px; font-weight: 700; cursor: pointer; font-family: inherit; }
            .btn:hover { opacity: 0.9; }
            .error-msg { background: rgba(248,113,113,0.1); color: #f87171; padding: 10px 14px; border-radius: 8px; font-size: 13px; display: none; }

            #messengerScreen { display: none; height: 100vh; }
            .msg-layout { display: flex; height: 100vh; }

            .sidebar { width: 280px; background: #16122a; border-right: 1px solid #2a2248; display: flex; flex-direction: column; flex-shrink: 0; }
            .sidebar-header { padding: 16px; border-bottom: 1px solid #2a2248; display: flex; align-items: center; justify-content: space-between; }
            .sidebar-title { font-weight: 800; font-size: 16px; }
            .sidebar-user { font-size: 11px; color: #f59e0b; }
            .logout-btn-small { background: none; border: 1px solid #2a2248; color: #7c7a9a; padding: 4px 10px; border-radius: 6px; font-size: 11px; cursor: pointer; font-family: inherit; }
            .logout-btn-small:hover { border-color: #f87171; color: #f87171; }

            .chat-list { flex: 1; overflow-y: auto; padding: 8px; }
            .chat-list-section { font-size: 10px; color: #7c7a9a; text-transform: uppercase; letter-spacing: 1.5px; padding: 12px 8px 4px; font-weight: 700; }

            .chat-item { padding: 10px 12px; border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 10px; transition: background 0.15s; margin-bottom: 2px; }
            .chat-item:hover { background: #1e1838; }
            .chat-item.active { background: #2a2248; }
            .chat-emoji { font-size: 18px; width: 32px; height: 32px; background: #1e1838; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
            .chat-item.active .chat-emoji { background: #362e5c; }
            .chat-name { font-size: 13px; font-weight: 600; }

            .chat-area { flex: 1; display: flex; flex-direction: column; }
            .chat-header { padding: 14px 20px; border-bottom: 1px solid #2a2248; background: #16122a; display: flex; align-items: center; justify-content: space-between; }
            .chat-header-title { font-weight: 800; font-size: 16px; }
            .chat-header-online { font-size: 12px; color: #34d399; }

            .chat-no-select { flex: 1; display: flex; align-items: center; justify-content: center; color: #4a4568; font-size: 15px; }

            .messages-area { flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 8px; }

            .msg-bubble { max-width: 75%; padding: 10px 14px; border-radius: 14px; font-size: 14px; line-height: 1.4; animation: fadeIn 0.2s ease; }
            .msg-bubble.other { background: #1e1838; align-self: flex-start; border-bottom-left-radius: 4px; }
            .msg-bubble.mine { background: #3b2f63; align-self: flex-end; border-bottom-right-radius: 4px; }
            .msg-author { font-size: 11px; font-weight: 700; color: #f59e0b; margin-bottom: 2px; }
            .msg-time { font-size: 10px; color: #7c7a9a; margin-top: 4px; text-align: right; }

            @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

            .input-area { padding: 12px 16px; border-top: 1px solid #2a2248; background: #16122a; display: flex; gap: 10px; }
            .msg-input { flex: 1; padding: 10px 16px; background: #0c0a15; border: 1.5px solid #2a2248; border-radius: 10px; color: #e2e8f0; font-size: 14px; outline: none; font-family: inherit; }
            .msg-input:focus { border-color: #f59e0b; }
            .send-btn { padding: 10px 18px; background: #f59e0b; color: #0c0a15; border: none; border-radius: 10px; font-weight: 700; cursor: pointer; font-family: inherit; font-size: 14px; }
            .send-btn:hover { opacity: 0.9; }

            @media (max-width: 600px) {
                .sidebar { position: absolute; z-index: 10; width: 100%; transform: translateX(0); transition: transform 0.3s; }
                .sidebar.hidden { transform: translateX(-100%); }
                .chat-area { width: 100%; }
                .mobile-back { display: inline-block; cursor: pointer; margin-right: 8px; font-size: 18px; }
            }
            @media (min-width: 601px) {
                .mobile-back { display: none; }
            }
        </style>
    </head>
    <body>

    <div id="authScreen">
        <div class="auth-container">
            <div class="logo">
                <div class="icon">🍸</div>
                <h1>Svoi <span>Messenger</span></h1>
                <p>Свои · Натуралист</p>
            </div>
            <div class="tabs">
                <button class="tab active" onclick="switchTab('login')">Вход</button>
                <button class="tab" onclick="switchTab('register')">Регистрация</button>
            </div>
            <div id="error" class="error-msg"></div>
            <div id="loginForm" class="form">
                <input class="input" id="loginUsername" placeholder="Логин">
                <input class="input" id="loginPassword" type="password" placeholder="Пароль">
                <button class="btn" onclick="doLogin()">Войти</button>
            </div>
            <div id="registerForm" class="form hidden">
                <input class="input" id="regUsername" placeholder="Логин (латиница)">
                <input class="input" id="regDisplayName" placeholder="Имя (как видят другие)">
                <input class="input" id="regPassword" type="password" placeholder="Пароль (мин. 4 символа)">
                <select class="input" id="regVenue"><option value="">Загрузка...</option></select>
                <select class="input" id="regRole">
                    <option value="owner">Руководство</option>
                    <option value="bar_manager">Бар-менеджер</option>
                    <option value="head_chef">Шеф-повар</option>
                    <option value="senior_bartender">Старший бармен</option>
                    <option value="cook">Повар</option>
                    <option value="bartender">Бармен</option>
                    <option value="waiter">Официант</option>
                </select>
                <button class="btn" onclick="doRegister()">Зарегистрироваться</button>
            </div>
        </div>
    </div>

    <div id="messengerScreen">
        <div class="msg-layout">
            <div class="sidebar" id="sidebar">
                <div class="sidebar-header">
                    <div>
                        <div class="sidebar-title">🍸 Svoi</div>
                        <div class="sidebar-user" id="sidebarUser"></div>
                    </div>
                    <button class="logout-btn-small" onclick="doLogout()">Выйти</button>
                </div>
                <div class="chat-list" id="chatList"></div>
            </div>
            <div class="chat-area" id="chatArea">
                <div class="chat-no-select" id="noChat">← Выбери чат</div>
                <div id="activeChatView" style="display:none; flex-direction:column; height:100%;">
                    <div class="chat-header">
                        <div>
                            <span class="mobile-back" onclick="showSidebar()">←</span>
                            <span class="chat-header-title" id="chatHeaderTitle"></span>
                        </div>
                        <div class="chat-header-online" id="chatOnline"></div>
                    </div>
                    <div class="messages-area" id="messagesArea"></div>
                    <div class="input-area">
                        <input class="msg-input" id="msgInput" placeholder="Сообщение..." onkeydown="if(event.key==='Enter')sendMessage()">
                        <button class="send-btn" onclick="sendMessage()">→</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
    let currentToken = localStorage.getItem('token');
    let currentUser = null;
    let currentChatId = null;
    let ws = null;

    const roleNames = {owner:'Руководство', bar_manager:'Бар-менеджер', head_chef:'Шеф-повар', senior_bartender:'Старший бармен', cook:'Повар', bartender:'Бармен', waiter:'Официант'};

    async function loadVenues() {
        const res = await fetch('/api/venues');
        const venues = await res.json();
        const select = document.getElementById('regVenue');
        select.innerHTML = '<option value="">Оба заведения</option>';
        venues.forEach(v => { select.innerHTML += `<option value="${v.id}">${v.emoji} ${v.name}</option>`; });
    }

    function switchTab(tab) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        event.target.classList.add('active');
        document.getElementById('loginForm').classList.toggle('hidden', tab !== 'login');
        document.getElementById('registerForm').classList.toggle('hidden', tab !== 'register');
        document.getElementById('error').style.display = 'none';
    }

    function showError(msg) {
        const el = document.getElementById('error');
        el.textContent = msg;
        el.style.display = 'block';
    }

    async function doLogin() {
        const username = document.getElementById('loginUsername').value;
        const password = document.getElementById('loginPassword').value;
        const res = await fetch('/api/login', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username, password}) });
        const data = await res.json();
        if (data.error) { showError(data.error); return; }
        localStorage.setItem('token', data.token);
        currentToken = data.token;
        currentUser = data;
        enterMessenger();
    }

    async function doRegister() {
        const username = document.getElementById('regUsername').value;
        const display_name = document.getElementById('regDisplayName').value;
        const password = document.getElementById('regPassword').value;
        const venue_id = document.getElementById('regVenue').value || null;
        const role = document.getElementById('regRole').value;
        const res = await fetch('/api/register', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username, display_name, password, venue_id, role}) });
        const data = await res.json();
        if (data.error) { showError(data.error); return; }
        localStorage.setItem('token', data.token);
        currentToken = data.token;
        currentUser = data;
        enterMessenger();
    }

    function doLogout() {
        localStorage.removeItem('token');
        currentToken = null;
        currentUser = null;
        if (ws) ws.close();
        document.getElementById('authScreen').style.display = 'flex';
        document.getElementById('messengerScreen').style.display = 'none';
    }

    async function enterMessenger() {
        if (!currentUser || !currentUser.display_name) {
            const res = await fetch('/api/me', { headers: {'Authorization': 'Bearer ' + currentToken} });
            if (!res.ok) { doLogout(); return; }
            currentUser = await res.json();
        }
        document.getElementById('authScreen').style.display = 'none';
        document.getElementById('messengerScreen').style.display = 'block';
        document.getElementById('sidebarUser').textContent = currentUser.display_name + ' · ' + (roleNames[currentUser.role] || currentUser.role);
        await loadChats();
    }

    async function loadChats() {
        const res = await fetch('/api/chats', { headers: {'Authorization': 'Bearer ' + currentToken} });
        const chats = await res.json();
        const list = document.getElementById('chatList');
        list.innerHTML = '';

        const groups = { general: [], svoi: [], nat: [], service: [] };
        chats.forEach(c => {
            if (c.category === 'announcement') groups.service.push(c);
            else if (c.category === 'general' || c.category === 'management') groups.general.push(c);
            else if (c.category === 'venue_general' && c.venue_id) {
                if (c.venue_emoji === '🌿') groups.nat.push(c);
                else groups.svoi.push(c);
            }
            else if (c.venue_emoji === '🌿') groups.nat.push(c);
            else if (c.venue_emoji === '🍸') groups.svoi.push(c);
            else groups.general.push(c);
        });

        function addSection(title, items) {
            if (items.length === 0) return;
            list.innerHTML += `<div class="chat-list-section">${title}</div>`;
            items.forEach(c => {
                const emoji = c.is_announcement ? '📢' : (c.venue_emoji || '💬');
                list.innerHTML += `<div class="chat-item" data-id="${c.id}" onclick="openChat(${c.id}, '${c.name.replace(/'/g, "\\'")}')"><div class="chat-emoji">${emoji}</div><div class="chat-name">${c.name}</div></div>`;
            });
        }

        addSection('Общие', groups.general);
        addSection('🍸 Свои', groups.svoi);
        addSection('🌿 Натуралист', groups.nat);
        addSection('Сервисные', groups.service);
    }

    async function openChat(chatId, chatName) {
        currentChatId = chatId;
        document.querySelectorAll('.chat-item').forEach(el => el.classList.remove('active'));
        document.querySelector(`.chat-item[data-id="${chatId}"]`)?.classList.add('active');
        document.getElementById('noChat').style.display = 'none';
        document.getElementById('activeChatView').style.display = 'flex';
        document.getElementById('chatHeaderTitle').textContent = chatName;
        document.getElementById('sidebar').classList.add('hidden');

        const res = await fetch(`/api/chats/${chatId}/messages`, { headers: {'Authorization': 'Bearer ' + currentToken} });
        const messages = await res.json();
        const area = document.getElementById('messagesArea');
        area.innerHTML = '';
        messages.forEach(m => appendMessage(m));
        area.scrollTop = area.scrollHeight;
        connectWS(chatId);
    }

    function connectWS(chatId) {
        if (ws) ws.close();
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${location.host}/ws/${chatId}?token=${currentToken}`);

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'message') {
                appendMessage(data);
                document.getElementById('messagesArea').scrollTop = document.getElementById('messagesArea').scrollHeight;
            }
            else if (data.type === 'user_joined' || data.type === 'user_left') {
                document.getElementById('chatOnline').textContent = data.online.length + ' онлайн';
            }
        };
        ws.onclose = () => {};
    }

    function appendMessage(msg) {
        const area = document.getElementById('messagesArea');
        const isMine = msg.user_id === currentUser.user_id || msg.user_id === currentUser.id;
        const time = msg.created_at ? msg.created_at.split(' ')[1]?.substring(0,5) || '' : '';
        const div = document.createElement('div');
        div.className = `msg-bubble ${isMine ? 'mine' : 'other'}`;
        div.innerHTML = `${!isMine ? `<div class="msg-author">${msg.display_name}</div>` : ''}<div>${msg.content}</div><div class="msg-time">${time}</div>`;
        area.appendChild(div);
    }

    function sendMessage() {
        const input = document.getElementById('msgInput');
        const text = input.value.trim();
        if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
        ws.send(JSON.stringify({ content: text }));
        input.value = '';
        input.focus();
    }

    function showSidebar() {
        document.getElementById('sidebar').classList.remove('hidden');
    }

    loadVenues();
    if (currentToken) { enterMessenger(); }
    </script>
    </body>
    </html>
    """
