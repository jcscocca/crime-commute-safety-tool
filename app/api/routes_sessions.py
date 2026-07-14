from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response

from app.config import get_settings
from app.ratelimit import client_ip_from, get_rate_limiter
from app.sessions import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    new_session_token,
    session_id_from_token,
)

router = APIRouter()


@router.post("/sessions")
def create_public_session(
    request: Request,
    response: Response,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> dict[str, str]:
    if session_id_from_token(session_token) is not None:
        return {"session_state": "resumed"}

    settings = get_settings()
    if settings.rate_limit_enabled:
        ip = client_ip_from(request, trust_proxy_headers=settings.trust_proxy_headers)
        wait = get_rate_limiter().try_take(
            "sessions",
            ip,
            capacity=settings.rate_limit_sessions_per_hour,
            per_seconds=3600.0,
        )
        if wait > 0:
            raise HTTPException(
                status_code=429,
                detail="Session request limit reached — please retry later.",
                headers={"Retry-After": str(max(1, int(wait)))},
            )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=new_session_token(),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.effective_session_cookie_secure,
        samesite="lax",
    )
    return {"session_state": "created"}
