from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

AUTH_ROOT = Path("data/auth")
USERS_PATH = AUTH_ROOT / "users.json"
SESSIONS_PATH = AUTH_ROOT / "sessions.json"
SESSION_COOKIE = "minutes_session"
SESSION_DAYS = 30
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(ValueError):
    pass


def register_user(email: str, password: str) -> dict[str, Any]:
    normalized_email = _normalize_email(email)
    _validate_password(password)
    users = _load_users()
    if any(str(user.get("email") or "") == normalized_email for user in users):
        raise AuthError("该邮箱已注册，请直接登录。")
    now = _now_iso()
    user = {
        "id": uuid4().hex,
        "email": normalized_email,
        "password_hash": _hash_password(password),
        "created_at": now,
        "updated_at": now,
    }
    users.append(user)
    _save_users(users)
    return _public_user(user)


def authenticate_user(email: str, password: str) -> dict[str, Any]:
    normalized_email = _normalize_email(email)
    users = _load_users()
    user = next((item for item in users if str(item.get("email") or "") == normalized_email), None)
    if not user or not _verify_password(password, str(user.get("password_hash") or "")):
        raise AuthError("邮箱或密码错误。")
    return _public_user(user)


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    users = _load_users()
    user = next((item for item in users if str(item.get("id") or "") == user_id), None)
    return _public_user(user) if user else None


def create_session(user_id: str) -> str:
    sessions = _load_sessions()
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
    sessions[token] = {
        "user_id": user_id,
        "expires_at": expires_at,
    }
    _save_sessions(sessions)
    return token


def get_user_for_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    sessions = _load_sessions()
    session = sessions.get(token)
    if not isinstance(session, dict):
        return None
    expires_at = str(session.get("expires_at") or "")
    if expires_at:
        try:
            is_expired = datetime.fromisoformat(expires_at) <= datetime.now()
        except ValueError:
            is_expired = True
        if is_expired:
            sessions.pop(token, None)
            _save_sessions(sessions)
            return None
    user_id = str(session.get("user_id") or "")
    return get_user_by_id(user_id)


def delete_session(token: str | None) -> None:
    if not token:
        return
    sessions = _load_sessions()
    if token in sessions:
        sessions.pop(token, None)
        _save_sessions(sessions)


def session_cookie_value(token: str) -> str:
    max_age = SESSION_DAYS * 24 * 60 * 60
    return f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"


def clear_session_cookie_value() -> str:
    return f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"


def parse_session_token(cookie_header: str | None) -> str | None:
    if not cookie_header:
        return None
    for chunk in cookie_header.split(";"):
        name, _, value = chunk.strip().partition("=")
        if name == SESSION_COOKIE and value:
            return value
    return None


def _normalize_email(email: str) -> str:
    normalized = str(email or "").strip().lower()
    if not normalized or not EMAIL_RE.match(normalized):
        raise AuthError("请输入有效的邮箱地址。")
    return normalized


def _validate_password(password: str) -> None:
    if len(password or "") < 6:
        raise AuthError("密码至少需要 6 位。")


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(user.get("id") or ""),
        "email": str(user.get("email") or ""),
        "created_at": str(user.get("created_at") or ""),
    }


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return f"{salt.hex()}:{digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    salt_hex, _, digest_hex = stored.partition(":")
    if not salt_hex or not digest_hex:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return hmac.compare_digest(candidate, expected)


def _load_users() -> list[dict[str, Any]]:
    if not USERS_PATH.exists():
        return []
    data = json.loads(USERS_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _save_users(users: list[dict[str, Any]]) -> None:
    _ensure_auth_root()
    USERS_PATH.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_sessions() -> dict[str, dict[str, Any]]:
    if not SESSIONS_PATH.exists():
        return {}
    data = json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _save_sessions(sessions: dict[str, dict[str, Any]]) -> None:
    _ensure_auth_root()
    SESSIONS_PATH.write_text(json.dumps(sessions, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_auth_root() -> None:
    AUTH_ROOT.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
