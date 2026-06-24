from __future__ import annotations

import base64
import hmac
from hashlib import sha256
from uuid import uuid4

from app.config import get_settings

SESSION_COOKIE_NAME = "mca_session"


def new_session_token() -> str:
    session_id = str(uuid4())
    signature = _sign(session_id)
    return f"{session_id}.{signature}"


def session_id_from_token(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    session_id, signature = token.rsplit(".", 1)
    if not session_id or not signature:
        return None
    expected = _sign(session_id)
    if not hmac.compare_digest(signature, expected):
        return None
    return session_id


def public_user_hash(session_token: str | None) -> str | None:
    session_id = session_id_from_token(session_token)
    if session_id is None:
        return None
    salt = get_settings().user_hash_salt
    return sha256(f"{salt}:public-session:{session_id}".encode()).hexdigest()


def _sign(session_id: str) -> str:
    secret = get_settings().session_secret.encode()
    digest = hmac.new(secret, session_id.encode(), sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")
