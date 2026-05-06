from database import get_db


def get_all_users(exclude_id: int = None) -> list:
    conn = get_db()
    if exclude_id:
        rows = conn.execute(
            "SELECT id, display_name, role FROM users WHERE is_active = 1 AND id != ? ORDER BY display_name",
            (exclude_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, display_name, role FROM users WHERE is_active = 1 ORDER BY display_name"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_or_get_dm(user1_id: int, user2_id: int) -> dict:
    conn = get_db()
    existing = conn.execute(
        """
        SELECT c.id, c.name FROM chats c
        WHERE c.chat_type = 'dm' AND c.id IN (
            SELECT cm1.chat_id FROM chat_members cm1
            JOIN chat_members cm2 ON cm1.chat_id = cm2.chat_id
            WHERE cm1.user_id = ? AND cm2.user_id = ?
        ) LIMIT 1
    """,
        (user1_id, user2_id),
    ).fetchone()

    if existing:
        conn.close()
        return {"chat_id": existing["id"], "name": existing["name"], "created": False}

    u1 = conn.execute(
        "SELECT display_name FROM users WHERE id = ?", (user1_id,)
    ).fetchone()
    u2 = conn.execute(
        "SELECT display_name FROM users WHERE id = ?", (user2_id,)
    ).fetchone()
    if not u1 or not u2:
        conn.close()
        return {"error": "Пользователь не найден"}

    name = f"{u1['display_name']} ↔ {u2['display_name']}"
    cursor = conn.execute(
        "INSERT INTO chats (name, chat_type) VALUES (?, 'dm')", (name,)
    )
    chat_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO chat_members (chat_id, user_id) VALUES (?, ?)", (chat_id, user1_id)
    )
    conn.execute(
        "INSERT INTO chat_members (chat_id, user_id) VALUES (?, ?)", (chat_id, user2_id)
    )
    conn.commit()
    conn.close()
    return {"chat_id": chat_id, "name": name, "created": True}


def get_user_chats(user_id: int) -> list:
    conn = get_db()

    # Групповые чаты — все видят всё (один чат)
    groups = conn.execute(
        """
        SELECT c.id, c.name, c.chat_type FROM chats c
        WHERE c.chat_type = 'group' ORDER BY c.id
    """
    ).fetchall()

    # Личные чаты пользователя
    dms = conn.execute(
        """
        SELECT c.id, c.name, c.chat_type FROM chats c
        JOIN chat_members cm ON cm.chat_id = c.id
        WHERE c.chat_type = 'dm' AND cm.user_id = ?
        ORDER BY c.id DESC
    """,
        (user_id,),
    ).fetchall()

    result = [dict(c) for c in groups] + [dict(c) for c in dms]

    # Добавляем последнее сообщение
    for chat in result:
        last = conn.execute(
            """
            SELECT m.content, m.message_type, m.created_at, u.display_name
            FROM messages m JOIN users u ON u.id = m.user_id
            WHERE m.chat_id = ? ORDER BY m.created_at DESC LIMIT 1
        """,
            (chat["id"],),
        ).fetchone()
        if last:
            preview = last["content"]
            if last["message_type"] == "image":
                preview = "📷 Фото"
            elif last["message_type"] == "video":
                preview = "🎬 Видео"
            elif last["message_type"] == "file":
                preview = "📎 " + last["content"]
            chat["last_message"] = last["display_name"] + ": " + preview
            chat["last_time"] = last["created_at"]
        else:
            chat["last_message"] = ""
            chat["last_time"] = ""

    conn.close()
    return result


def get_chat_messages(chat_id: int, limit: int = 50) -> list:
    conn = get_db()
    messages = conn.execute(
        """
        SELECT m.id, m.content, m.message_type, m.file_path, m.created_at,
               u.id as user_id, u.display_name, u.role
        FROM messages m JOIN users u ON m.user_id = u.id
        WHERE m.chat_id = ? ORDER BY m.created_at DESC LIMIT ?
    """,
        (chat_id, limit),
    ).fetchall()
    conn.close()
    return [dict(m) for m in reversed(messages)]


def save_message(
    chat_id: int,
    user_id: int,
    content: str,
    message_type: str = "text",
    file_path: str = None,
) -> dict:
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO messages (chat_id, user_id, content, message_type, file_path) VALUES (?, ?, ?, ?, ?)",
        (chat_id, user_id, content, message_type, file_path),
    )
    conn.commit()
    msg = conn.execute(
        """
        SELECT m.id, m.content, m.message_type, m.file_path, m.created_at,
               u.id as user_id, u.display_name, u.role
        FROM messages m JOIN users u ON m.user_id = u.id WHERE m.id = ?
    """,
        (cursor.lastrowid,),
    ).fetchone()
    conn.close()
    return dict(msg)
