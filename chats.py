from database import get_db


def init_chats():
    """Создаём стандартные чаты при первом запуске"""
    conn = get_db()

    existing = conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
    if existing > 0:
        conn.close()
        return

    svoi = conn.execute("SELECT id FROM venues WHERE name = 'Свои'").fetchone()
    nat = conn.execute("SELECT id FROM venues WHERE name = 'Натуралист'").fetchone()

    if not svoi or not nat:
        conn.close()
        return

    svoi_id = svoi["id"]
    nat_id = nat["id"]

    chats = [
        ("Svoi Unity", "group", None, 0, "general"),
        ("Общая Свои", "group", svoi_id, 0, "venue_general"),
        ("Общая Натуралист", "group", nat_id, 0, "venue_general"),
        ("Руководство", "group", None, 0, "management"),
        ("Бармены Свои", "group", svoi_id, 0, "bar"),
        ("Кухня Свои", "group", svoi_id, 0, "kitchen"),
        ("Зал Свои", "group", svoi_id, 0, "hall"),
        ("Бармены Натуралист", "group", nat_id, 0, "bar"),
        ("Кухня Натуралист", "group", nat_id, 0, "kitchen"),
        ("Зал Натуралист", "group", nat_id, 0, "hall"),
        ("Объявления", "announcement", None, 1, "announcement"),
    ]

    for name, chat_type, venue_id, is_announcement, category in chats:
        conn.execute(
            "INSERT INTO chats (name, chat_type, venue_id, is_announcement, category) VALUES (?, ?, ?, ?, ?)",
            (name, chat_type, venue_id, is_announcement, category),
        )

    conn.commit()
    conn.close()
    print("✅ Чаты созданы")


def get_user_chats(user_id: int) -> list:
    """Получаем список чатов, доступных пользователю"""
    conn = get_db()

    user = conn.execute(
        "SELECT role, venue_id FROM users WHERE id = ?", (user_id,)
    ).fetchone()

    if not user:
        conn.close()
        return []

    role = user["role"]
    venue_id = user["venue_id"]

    # Получаем все чаты
    all_chats = conn.execute(
        """
        SELECT c.id, c.name, c.chat_type, c.venue_id, c.is_announcement, c.category,
               v.emoji as venue_emoji
        FROM chats c
        LEFT JOIN venues v ON c.venue_id = v.id
        ORDER BY c.id
    """
    ).fetchall()

    conn.close()

    # Руководство видит все чаты
    if role == "owner":
        return [dict(c) for c in all_chats]

    # Бар-менеджер: общие + своё заведение + руководство
    if role == "bar_manager":
        result = []
        for c in all_chats:
            if c["venue_id"] is None:
                result.append(c)
            elif c["venue_id"] == venue_id:
                result.append(c)
        return [dict(c) for c in result]

    # Определяем какие категории подразделений доступны роли
    role_categories = {
        "head_chef": ["kitchen"],
        "senior_bartender": ["bar"],
        "cook": ["kitchen"],
        "bartender": ["bar"],
        "waiter": ["hall"],
    }

    allowed = role_categories.get(role, [])

    result = []
    for c in all_chats:
        cat = c["category"]
        cv = c["venue_id"]

        # Общие чаты — видят все
        if cat == "general":
            result.append(c)
        # Объявления — видят все
        elif cat == "announcement":
            result.append(c)
        # Общая своего заведения
        elif cat == "venue_general" and (cv == venue_id or venue_id is None):
            result.append(c)
        # Подразделение своего заведения
        elif cat in allowed and (cv == venue_id or venue_id is None):
            result.append(c)

    return [dict(c) for c in result]


def get_chat_messages(chat_id: int, limit: int = 50) -> list:
    """Получаем последние сообщения из чата"""
    conn = get_db()
    messages = conn.execute(
        """
        SELECT m.id, m.content, m.message_type, m.file_path, m.created_at,
               u.id as user_id, u.display_name, u.role
        FROM messages m
        JOIN users u ON m.user_id = u.id
        WHERE m.chat_id = ?
        ORDER BY m.created_at DESC
        LIMIT ?
    """,
        (chat_id, limit),
    ).fetchall()
    conn.close()

    return [dict(m) for m in reversed(messages)]


def save_message(
    chat_id: int, user_id: int, content: str, message_type: str = "text"
) -> dict:
    """Сохраняем сообщение в базу"""
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO messages (chat_id, user_id, content, message_type) VALUES (?, ?, ?, ?)",
        (chat_id, user_id, content, message_type),
    )
    conn.commit()

    msg = conn.execute(
        """
        SELECT m.id, m.content, m.message_type, m.created_at,
               u.id as user_id, u.display_name, u.role
        FROM messages m
        JOIN users u ON m.user_id = u.id
        WHERE m.id = ?
    """,
        (cursor.lastrowid,),
    ).fetchone()
    conn.close()

    return dict(msg)
