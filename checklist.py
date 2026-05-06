from datetime import date, datetime
from database import get_db

EDITOR_ROLES = {"bar_manager", "senior_bartender"}


def can_edit_checklist(role: str) -> bool:
    return role in EDITOR_ROLES


def get_checklist(for_date: str = None) -> dict:
    if not for_date:
        for_date = date.today().isoformat()

    conn = get_db()
    rows = conn.execute(
        """
        SELECT t.id, t.section, t.title, t.detail, t.sort_order,
               c.completed_by, c.completed_at, u.display_name as completed_by_name
        FROM checklist_templates t
        LEFT JOIN checklist_completions c ON c.template_id = t.id AND c.completed_date = ?
        LEFT JOIN users u ON u.id = c.completed_by
        WHERE t.is_active = 1 ORDER BY t.section, t.sort_order
    """,
        (for_date,),
    ).fetchall()
    conn.close()

    sections = {"opening": [], "during": [], "closing": []}
    for r in rows:
        item = {
            "id": r["id"],
            "title": r["title"],
            "detail": r["detail"] or "",
            "done": r["completed_by"] is not None,
            "completed_by_name": r["completed_by_name"] or "",
            "completed_at": r["completed_at"] or "",
        }
        if r["section"] in sections:
            sections[r["section"]].append(item)

    total = sum(len(v) for v in sections.values())
    done = sum(1 for s in sections.values() for i in s if i["done"])
    return {"date": for_date, "sections": sections, "total": total, "done": done}


def toggle_task(template_id: int, user_id: int, for_date: str = None) -> dict:
    if not for_date:
        for_date = date.today().isoformat()

    conn = get_db()
    if not conn.execute(
        "SELECT id FROM checklist_templates WHERE id = ? AND is_active = 1",
        (template_id,),
    ).fetchone():
        conn.close()
        return {"error": "Пункт не найден"}

    existing = conn.execute(
        "SELECT id FROM checklist_completions WHERE template_id = ? AND completed_date = ?",
        (template_id, for_date),
    ).fetchone()

    if existing:
        conn.execute(
            "DELETE FROM checklist_completions WHERE id = ?", (existing["id"],)
        )
        conn.commit()
        conn.close()
        return {"done": False, "template_id": template_id}
    else:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO checklist_completions (template_id, completed_date, completed_by, completed_at) VALUES (?, ?, ?, ?)",
            (template_id, for_date, user_id, now),
        )
        conn.commit()
        user = conn.execute(
            "SELECT display_name FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        conn.close()
        return {
            "done": True,
            "template_id": template_id,
            "completed_by_name": user["display_name"] if user else "",
            "completed_at": now,
        }


def add_template_item(section: str, title: str, detail: str = "") -> dict:
    if section not in ("opening", "during", "closing"):
        return {"error": "Неверная секция"}
    if not title.strip():
        return {"error": "Название обязательно"}

    conn = get_db()
    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) as mx FROM checklist_templates WHERE section = ? AND is_active = 1",
        (section,),
    ).fetchone()["mx"]
    cursor = conn.execute(
        "INSERT INTO checklist_templates (section, title, detail, sort_order) VALUES (?, ?, ?, ?)",
        (section, title.strip(), detail.strip(), max_order + 1),
    )
    conn.commit()
    conn.close()
    return {
        "id": cursor.lastrowid,
        "section": section,
        "title": title.strip(),
        "detail": detail.strip(),
        "sort_order": max_order + 1,
    }


def delete_template_item(template_id: int) -> dict:
    conn = get_db()
    if not conn.execute(
        "SELECT id FROM checklist_templates WHERE id = ? AND is_active = 1",
        (template_id,),
    ).fetchone():
        conn.close()
        return {"error": "Пункт не найден"}
    conn.execute(
        "UPDATE checklist_templates SET is_active = 0 WHERE id = ?", (template_id,)
    )
    conn.commit()
    conn.close()
    return {"deleted": True, "template_id": template_id}


def reset_daily_completions():
    print(f"✅ Чек-листы сброшены на {date.today().isoformat()}")
