from database import get_db

NEWS_EDITOR_ROLES = {"bar_manager", "senior_bartender"}


def can_edit_news(role: str) -> bool:
    return role in NEWS_EDITOR_ROLES


def get_events() -> list:
    conn = get_db()
    rows = conn.execute("SELECT * FROM events ORDER BY event_date, event_time").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_event(event_date: str, event_time: str, title: str, description: str = "", genre: str = "", entry_fee: str = "") -> dict:
    if not event_date or not title.strip():
        return {"error": "Дата и название обязательны"}
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO events (event_date, event_time, title, description, genre, entry_fee) VALUES (?, ?, ?, ?, ?, ?)",
        (event_date, event_time or "20:00", title.strip(), description.strip(), genre.strip(), entry_fee.strip()),
    )
    conn.commit()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (cursor.lastrowid,)).fetchone()
    conn.close()
    return dict(event)


def delete_event(event_id: int) -> dict:
    conn = get_db()
    if not conn.execute("SELECT id FROM events WHERE id = ?", (event_id,)).fetchone():
        conn.close()
        return {"error": "Событие не найдено"}
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    return {"deleted": True}
