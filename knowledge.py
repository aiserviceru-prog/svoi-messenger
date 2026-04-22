import json
from database import get_db

EDITOR_ROLES = {"bar_manager", "senior_bartender"}

CATEGORIES = ["Классика из меню", "IBA", "Чай и кофе", "Согревающие", "Полуфабрикаты", "Авторские", "Безалкогольные"]


def can_edit_knowledge(role: str) -> bool:
    return role in EDITOR_ROLES


def _parse_cocktail(r, favorites: set = None) -> dict:
    d = dict(r)
    try:
        d["ingredients"] = json.loads(d["ingredients"]) if d["ingredients"] else []
    except Exception:
        d["ingredients"] = []
    if favorites is not None:
        d["is_favorite"] = d["id"] in favorites
    return d


def _get_user_favorites(conn, user_id: int) -> set:
    rows = conn.execute(
        "SELECT cocktail_id FROM cocktail_favorites WHERE user_id = ?", (user_id,)
    ).fetchall()
    return {r[0] for r in rows}


def get_cocktails(user_id: int = None) -> list:
    conn = get_db()
    rows = conn.execute("""
        SELECT c.*, u.display_name as author_name
        FROM cocktails c LEFT JOIN users u ON u.id = c.created_by
        ORDER BY c.name
    """).fetchall()
    favorites = _get_user_favorites(conn, user_id) if user_id else set()
    conn.close()
    return [_parse_cocktail(r, favorites) for r in rows]


def get_cocktail(cocktail_id: int, user_id: int = None) -> dict | None:
    conn = get_db()
    r = conn.execute("""
        SELECT c.*, u.display_name as author_name
        FROM cocktails c LEFT JOIN users u ON u.id = c.created_by WHERE c.id = ?
    """, (cocktail_id,)).fetchone()
    if not r:
        conn.close()
        return None
    favorites = _get_user_favorites(conn, user_id) if user_id else set()
    conn.close()
    return _parse_cocktail(r, favorites)


def add_cocktail(name: str, glass: str, garnish: str, method: str,
                 ingredients: list, instructions: str, created_by: int,
                 photo_path: str = "", category: str = "Классика") -> dict:
    if not name.strip():
        return {"error": "Название обязательно"}
    if category not in CATEGORIES:
        category = "Классика"
    conn = get_db()
    ing_json = json.dumps(ingredients, ensure_ascii=False)
    cursor = conn.execute(
        "INSERT INTO cocktails (name, photo_path, glass, garnish, method, ingredients, instructions, category, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name.strip(), photo_path, glass.strip(), garnish.strip(), method.strip(), ing_json, instructions.strip(), category, created_by),
    )
    conn.commit()
    cid = cursor.lastrowid
    conn.close()
    return get_cocktail(cid, created_by)


def update_cocktail(cocktail_id: int, **fields) -> dict:
    conn = get_db()
    if not conn.execute("SELECT id FROM cocktails WHERE id = ?", (cocktail_id,)).fetchone():
        conn.close()
        return {"error": "Коктейль не найден"}

    allowed = {"name", "photo_path", "glass", "garnish", "method", "ingredients", "instructions", "category"}
    updates = []
    values = []
    for k, v in fields.items():
        if k in allowed and v is not None:
            if k == "ingredients":
                v = json.dumps(v, ensure_ascii=False)
            if k == "category" and v not in CATEGORIES:
                continue
            updates.append(f"{k} = ?")
            values.append(v)

    if updates:
        values.append(cocktail_id)
        conn.execute(f"UPDATE cocktails SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
    conn.close()
    return get_cocktail(cocktail_id)


def delete_cocktail(cocktail_id: int) -> dict:
    conn = get_db()
    if not conn.execute("SELECT id FROM cocktails WHERE id = ?", (cocktail_id,)).fetchone():
        conn.close()
        return {"error": "Коктейль не найден"}
    conn.execute("DELETE FROM cocktails WHERE id = ?", (cocktail_id,))
    conn.commit()
    conn.close()
    return {"deleted": True}


# ── Избранное ──────────────────────────────────────────────────────────────────

def toggle_favorite(user_id: int, cocktail_id: int) -> dict:
    conn = get_db()
    existing = conn.execute(
        "SELECT 1 FROM cocktail_favorites WHERE user_id = ? AND cocktail_id = ?",
        (user_id, cocktail_id)
    ).fetchone()
    if existing:
        conn.execute(
            "DELETE FROM cocktail_favorites WHERE user_id = ? AND cocktail_id = ?",
            (user_id, cocktail_id)
        )
        is_fav = False
    else:
        conn.execute(
            "INSERT OR IGNORE INTO cocktail_favorites (user_id, cocktail_id) VALUES (?, ?)",
            (user_id, cocktail_id)
        )
        is_fav = True
    conn.commit()
    conn.close()
    return {"is_favorite": is_fav, "cocktail_id": cocktail_id}
