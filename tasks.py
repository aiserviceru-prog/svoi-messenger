from datetime import datetime
from database import get_db

# bar_manager и senior_bartender могут создавать задачи для bartender
TASK_CREATORS = {"bar_manager": None, "senior_bartender": ["bartender"]}


def can_create_tasks(role: str) -> bool:
    return role in TASK_CREATORS


def get_assignable_users(creator: dict) -> list:
    conn = get_db()
    allowed = TASK_CREATORS.get(creator["role"])
    if allowed is None:
        rows = conn.execute(
            "SELECT id, display_name, role FROM users WHERE is_active = 1 AND id != ? ORDER BY display_name",
            (creator["id"],),
        ).fetchall()
    else:
        placeholders = ",".join("?" * len(allowed))
        rows = conn.execute(
            f"SELECT id, display_name, role FROM users WHERE is_active = 1 AND role IN ({placeholders})",
            allowed,
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_task(title: str, created_by: int, assigned_to: int = None, detail: str = "",
                priority: str = "normal", deadline: str = "") -> dict:
    if not title.strip():
        return {"error": "Название обязательно"}
    if priority not in ("low", "normal", "high", "urgent"):
        priority = "normal"
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO tasks (title, detail, assigned_to, created_by, priority, deadline) VALUES (?, ?, ?, ?, ?, ?)",
        (title.strip(), detail.strip(), assigned_to, created_by, priority, deadline),
    )
    conn.commit()
    task = conn.execute("""
        SELECT t.*, creator.display_name as creator_name, assignee.display_name as assignee_name
        FROM tasks t JOIN users creator ON creator.id = t.created_by
        LEFT JOIN users assignee ON assignee.id = t.assigned_to WHERE t.id = ?
    """, (cursor.lastrowid,)).fetchone()
    conn.close()
    return dict(task)


def get_tasks(user: dict) -> list:
    conn = get_db()
    uid = user["id"]
    if can_create_tasks(user["role"]):
        rows = conn.execute("""
            SELECT t.*, creator.display_name as creator_name, assignee.display_name as assignee_name
            FROM tasks t JOIN users creator ON creator.id = t.created_by
            LEFT JOIN users assignee ON assignee.id = t.assigned_to
            WHERE t.created_by = ? OR t.assigned_to = ?
            ORDER BY CASE t.status WHEN 'open' THEN 0 ELSE 1 END,
                     CASE t.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
                     t.created_at DESC
        """, (uid, uid)).fetchall()
    else:
        rows = conn.execute("""
            SELECT t.*, creator.display_name as creator_name, assignee.display_name as assignee_name
            FROM tasks t JOIN users creator ON creator.id = t.created_by
            LEFT JOIN users assignee ON assignee.id = t.assigned_to
            WHERE t.assigned_to = ?
            ORDER BY CASE t.status WHEN 'open' THEN 0 ELSE 1 END,
                     CASE t.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
                     t.created_at DESC
        """, (uid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def complete_task(task_id: int, user_id: int) -> dict:
    conn = get_db()
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return {"error": "Задача не найдена"}
    if task["assigned_to"] != user_id and task["created_by"] != user_id:
        conn.close()
        return {"error": "Нет прав"}
    new_status = "open" if task["status"] == "done" else "done"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if new_status == "done" else None
    conn.execute("UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?", (new_status, now, task_id))
    conn.commit()
    conn.close()
    return {"task_id": task_id, "status": new_status, "completed_at": now}


def delete_task(task_id: int, user_id: int) -> dict:
    conn = get_db()
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return {"error": "Задача не найдена"}
    if task["created_by"] != user_id:
        conn.close()
        return {"error": "Удалить может только автор"}
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return {"deleted": True}
