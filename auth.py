import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from database import get_db

SECRET_KEY = "svoi-bar-secret-key-change-me-later"
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30

VALID_ROLES = {"bartender", "senior_bartender", "bar_manager"}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"user_id": user_id, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM
    )


def verify_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def get_current_user(token: str) -> dict | None:
    payload = verify_token(token)
    if not payload:
        return None
    conn = get_db()
    user = conn.execute(
        "SELECT id, username, display_name, role, is_active FROM users WHERE id = ?",
        (payload["user_id"],),
    ).fetchone()
    conn.close()
    if user and user["is_active"]:
        return dict(user)
    return None


def register_user(
    username: str, display_name: str, password: str, role: str = "bartender"
) -> dict:
    if role not in VALID_ROLES:
        role = "bartender"

    conn = get_db()
    if conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
        conn.close()
        return {"error": "Пользователь с таким логином уже существует"}

    password_hash = hash_password(password)
    cursor = conn.execute(
        "INSERT INTO users (username, display_name, password_hash, role) VALUES (?, ?, ?, ?)",
        (username, display_name, password_hash, role),
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()

    return {
        "user_id": user_id,
        "token": create_token(user_id),
        "display_name": display_name,
        "role": role,
    }


def login_user(username: str, password: str) -> dict:
    conn = get_db()
    user = conn.execute(
        "SELECT id, display_name, password_hash, role, is_active FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()

    if not user:
        return {"error": "Неверный логин или пароль"}
    if not user["is_active"]:
        return {"error": "Аккаунт деактивирован"}
    if not verify_password(password, user["password_hash"]):
        return {"error": "Неверный логин или пароль"}

    return {
        "user_id": user["id"],
        "token": create_token(user["id"]),
        "display_name": user["display_name"],
        "role": user["role"],
    }
