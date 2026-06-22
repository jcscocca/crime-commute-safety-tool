from __future__ import annotations

from fastapi import APIRouter

from app.input_modes import supported_input_modes

router = APIRouter()


@router.get("/input-modes")
def input_modes() -> dict[str, object]:
    return {"modes": supported_input_modes()}
