from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Header

from app.services.users import hash_demo_user
from app.sessions import SESSION_COOKIE_NAME, public_user_hash


def current_user_hash(
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    x_demo_user_id: Annotated[str | None, Header()] = None,
) -> str:
    if user_hash := public_user_hash(session_token):
        return user_hash
    return hash_demo_user(x_demo_user_id)
