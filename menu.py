import json
from database import get_db

EDITOR_ROLES = {"bar_manager", "senior_bartender"}

MENU_CATEGORIES = ["Классика из меню", "Чай и кофе", "Согревающие", "Полуфабрикаты", "Страны", "Безалкогольные"]


def can_edit(role: str) -> bool:
    return role in EDITOR_ROLES


def _parse(r, favorites: set = None) -> dict:
    d = dict(r)
    try:
        d["ingredients"] = json.loads(d["ingredients"]) if d["ingredients"] else []
    except Exception:
        d["ingredients"] = []
    if favorites is not None:
        d["is_favorite"] = d["id"] in favorites
    return d


def _get_favorites(conn, user_id: int) -> set:
    rows = conn.execute(
        "SELECT cocktail_id FROM menu_cocktail_favorites WHERE user_id = ?", (user_id,)
    ).fetchall()
    return {r[0] for r in rows}


def get_menu_cocktails(user_id: int = None) -> list:
    conn = get_db()
    rows = conn.execute("""
        SELECT c.*, u.display_name as author_name
        FROM menu_cocktails c LEFT JOIN users u ON u.id = c.created_by
        ORDER BY c.name
    """).fetchall()
    favorites = _get_favorites(conn, user_id) if user_id else set()
    conn.close()
    return [_parse(r, favorites) for r in rows]


def get_menu_cocktail(cid: int, user_id: int = None) -> dict | None:
    conn = get_db()
    r = conn.execute("""
        SELECT c.*, u.display_name as author_name
        FROM menu_cocktails c LEFT JOIN users u ON u.id = c.created_by WHERE c.id = ?
    """, (cid,)).fetchone()
    if not r:
        conn.close()
        return None
    favorites = _get_favorites(conn, user_id) if user_id else set()
    conn.close()
    return _parse(r, favorites)


def add_menu_cocktail(name, glass, garnish, method, ingredients, instructions,
                      created_by, photo_path="", category="Классика из меню") -> dict:
    if not name.strip():
        return {"error": "Название обязательно"}
    if category not in MENU_CATEGORIES:
        category = "Классика из меню"
    conn = get_db()
    ing_json = json.dumps(ingredients, ensure_ascii=False)
    cursor = conn.execute(
        "INSERT INTO menu_cocktails (name, photo_path, glass, garnish, method, ingredients, instructions, category, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name.strip(), photo_path, glass.strip(), garnish.strip(), method.strip(), ing_json, instructions.strip(), category, created_by),
    )
    conn.commit()
    cid = cursor.lastrowid
    conn.close()
    return get_menu_cocktail(cid, created_by)


def update_menu_cocktail(cid: int, **fields) -> dict:
    conn = get_db()
    if not conn.execute("SELECT id FROM menu_cocktails WHERE id = ?", (cid,)).fetchone():
        conn.close()
        return {"error": "Не найден"}
    allowed = {"name", "photo_path", "glass", "garnish", "method", "ingredients", "instructions", "category"}
    updates, values = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            if k == "ingredients":
                v = json.dumps(v, ensure_ascii=False)
            if k == "category" and v not in MENU_CATEGORIES:
                continue
            updates.append(f"{k} = ?")
            values.append(v)
    if updates:
        values.append(cid)
        conn.execute(f"UPDATE menu_cocktails SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
    conn.close()
    return get_menu_cocktail(cid)


def delete_menu_cocktail(cid: int) -> dict:
    conn = get_db()
    if not conn.execute("SELECT id FROM menu_cocktails WHERE id = ?", (cid,)).fetchone():
        conn.close()
        return {"error": "Не найден"}
    conn.execute("DELETE FROM menu_cocktails WHERE id = ?", (cid,))
    conn.commit()
    conn.close()
    return {"deleted": True}


def toggle_menu_favorite(user_id: int, cid: int) -> dict:
    conn = get_db()
    existing = conn.execute(
        "SELECT 1 FROM menu_cocktail_favorites WHERE user_id = ? AND cocktail_id = ?",
        (user_id, cid)
    ).fetchone()
    if existing:
        conn.execute("DELETE FROM menu_cocktail_favorites WHERE user_id = ? AND cocktail_id = ?", (user_id, cid))
        is_fav = False
    else:
        conn.execute("INSERT OR IGNORE INTO menu_cocktail_favorites (user_id, cocktail_id) VALUES (?, ?)", (user_id, cid))
        is_fav = True
    conn.commit()
    conn.close()
    return {"is_favorite": is_fav, "cocktail_id": cid}
