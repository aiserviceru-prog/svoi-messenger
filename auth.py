import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from database import get_db

SECRET_KEY = "svoi-messenger-secret-key-change-me-later"
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {"user_id": user_id, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user(token: str) -> dict | None:
    payload = verify_token(token)
    if not payload:
        return None

    conn = get_db()
    user = conn.execute(
        "SELECT id, username, display_name, role, venue_id, is_active FROM users WHERE id = ?",
        (payload["user_id"],),
    ).fetchone()
    conn.close()

    if user and user["is_active"]:
        return dict(user)
    return None


def register_user(
    username: str,
    display_name: str,
    password: str,
    role: str = "waiter",
    venue_id: int = None,
) -> dict:
    conn = get_db()

    existing = conn.execute(
        "SELECT id FROM users WHERE username = ?", (username,)
    ).fetchone()
    if existing:
        conn.close()
        return {"error": "Пользователь с таким логином уже существует"}

    password_hash = hash_password(password)
    cursor = conn.execute(
        "INSERT INTO users (username, display_name, password_hash, role, venue_id) VALUES (?, ?, ?, ?, ?)",
        (username, display_name, password_hash, role, venue_id),
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()

    token = create_token(user_id)
    return {
        "user_id": user_id,
        "token": token,
        "display_name": display_name,
        "role": role,
    }


def login_user(username: str, password: str) -> dict:
    conn = get_db()
    user = conn.execute(
        "SELECT id, username, display_name, password_hash, role, venue_id, is_active FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()

    if not user:
        return {"error": "Неверный логин или пароль"}

    if not user["is_active"]:
        return {"error": "Аккаунт деактивирован"}

    if not verify_password(password, user["password_hash"]):
        return {"error": "Неверный логин или пароль"}

    token = create_token(user["id"])
    return {
        "user_id": user["id"],
        "token": token,
        "display_name": user["display_name"],
        "role": user["role"],
    }
