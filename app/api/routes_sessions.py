from __future__ import annotations

from fastapi import APIRouter, Response

from app.sessions import SESSION_COOKIE_NAME, new_session_token

router = APIRouter()


@router.post("/sessions")
def create_public_session(response: Response) -> dict[str, str]:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=new_session_token(),
        max_age=60 * 60 * 24,
        httponly=True,
        secure=False,
        samesite="lax",
    )
    return {"session_state": "created"}
