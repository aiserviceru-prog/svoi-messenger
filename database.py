import sqlite3

DB_PATH = "messenger.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'bartender',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            chat_type TEXT NOT NULL DEFAULT 'group',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chat_members (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (chat_id, user_id),
            FOREIGN KEY (chat_id) REFERENCES chats(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            message_type TEXT DEFAULT 'text',
            file_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS checklist_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section TEXT NOT NULL DEFAULT 'opening',
            title TEXT NOT NULL,
            detail TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS checklist_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL,
            completed_date TEXT NOT NULL,
            completed_by INTEGER NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (template_id) REFERENCES checklist_templates(id),
            FOREIGN KEY (completed_by) REFERENCES users(id),
            UNIQUE(template_id, completed_date)
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT NOT NULL,
            event_time TEXT DEFAULT '20:00',
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            genre TEXT DEFAULT '',
            entry_fee TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            detail TEXT DEFAULT '',
            assigned_to INTEGER,
            created_by INTEGER NOT NULL,
            status TEXT DEFAULT 'open',
            priority TEXT DEFAULT 'normal',
            deadline TEXT DEFAULT '',
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assigned_to) REFERENCES users(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS pinned_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            pinned_by INTEGER NOT NULL,
            pinned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats(id),
            FOREIGN KEY (message_id) REFERENCES messages(id),
            FOREIGN KEY (pinned_by) REFERENCES users(id),
            UNIQUE(chat_id, message_id)
        );

        -- Технологические карты коктейлей
        CREATE TABLE IF NOT EXISTS cocktails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            photo_path TEXT DEFAULT '',
            glass TEXT DEFAULT '',
            garnish TEXT DEFAULT '',
            method TEXT DEFAULT '',
            ingredients TEXT DEFAULT '[]',
            instructions TEXT DEFAULT '',
            category TEXT DEFAULT 'Классика',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        );

        -- Избранные коктейли (техкарты)
        CREATE TABLE IF NOT EXISTS cocktail_favorites (
            user_id INTEGER NOT NULL,
            cocktail_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, cocktail_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (cocktail_id) REFERENCES cocktails(id) ON DELETE CASCADE
        );

        -- Коктейльное меню
        CREATE TABLE IF NOT EXISTS menu_cocktails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            photo_path TEXT DEFAULT '',
            glass TEXT DEFAULT '',
            garnish TEXT DEFAULT '',
            method TEXT DEFAULT '',
            ingredients TEXT DEFAULT '[]',
            instructions TEXT DEFAULT '',
            category TEXT DEFAULT 'Классика из меню',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        );

        -- Избранные коктейли меню
        CREATE TABLE IF NOT EXISTS menu_cocktail_favorites (
            user_id INTEGER NOT NULL,
            cocktail_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, cocktail_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (cocktail_id) REFERENCES menu_cocktails(id) ON DELETE CASCADE
        );
    """
    )

    # Создаём основной чат
    existing = conn.execute(
        "SELECT COUNT(*) FROM chats WHERE chat_type='group'"
    ).fetchone()[0]
    if existing == 0:
        conn.execute(
            "INSERT INTO chats (name, chat_type) VALUES ('Бар Свои Чатик', 'group')"
        )
        conn.commit()
        print("✅ Чат «Бар Свои Чатик» создан")

    # Миграция: добавить колонку category если её нет
    cols = [row[1] for row in conn.execute("PRAGMA table_info(cocktails)").fetchall()]
    if "category" not in cols:
        conn.execute(
            "ALTER TABLE cocktails ADD COLUMN category TEXT DEFAULT 'Классика'"
        )
        conn.commit()
        print("✅ Миграция: добавлена колонка category")

    # Миграция: таблица избранного
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cocktail_favorites (
            user_id INTEGER NOT NULL,
            cocktail_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, cocktail_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (cocktail_id) REFERENCES cocktails(id) ON DELETE CASCADE
        )
    """
    )
    conn.commit()

    # Миграция: таблицы меню коктейлей
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS menu_cocktails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            photo_path TEXT DEFAULT '',
            glass TEXT DEFAULT '',
            garnish TEXT DEFAULT '',
            method TEXT DEFAULT '',
            ingredients TEXT DEFAULT '[]',
            instructions TEXT DEFAULT '',
            category TEXT DEFAULT 'Классика из меню',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS menu_cocktail_favorites (
            user_id INTEGER NOT NULL,
            cocktail_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, cocktail_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (cocktail_id) REFERENCES menu_cocktails(id) ON DELETE CASCADE
        )
    """
    )
    conn.commit()

    conn.close()
    print("✅ База данных готова")
