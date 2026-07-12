from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import required_public_user_hash
from app.assistant.agent import _UNREACHABLE_MESSAGE, run_assistant_turn
from app.assistant.llm_client import (
    AssistantLlmClient,
    FailoverLlmClient,
    OpenAiLlmClient,
)
from app.assistant.schemas import AssistantChatRequest, AssistantStreamEvent
from app.config import Settings, get_settings
from app.db import get_session
from app.ratelimit import get_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter()


def _no_think_body(disable_thinking: bool) -> dict[str, object] | None:
    """For llama.cpp/llama-swap thinking models (e.g. Qwen), turn off the
    chain-of-thought so the answer lands in ``content`` instead of consuming the
    token budget on ``reasoning_content``."""
    if disable_thinking:
        return {"chat_template_kwargs": {"enable_thinking": False}}
    return None


def build_assistant_llm_client(settings: Settings) -> AssistantLlmClient:
    """Build the assistant LLM client: the primary endpoint, wrapped in
    automatic failover to a second node when both fallback values are set."""
    primary = OpenAiLlmClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        extra_body=_no_think_body(settings.llm_disable_thinking),
        api_key=settings.llm_api_key,
    )
    fallback_base_url = settings.llm_fallback_base_url.strip()
    fallback_model = settings.llm_fallback_model.strip()
    if fallback_base_url and fallback_model:
        fallback = OpenAiLlmClient(
            base_url=fallback_base_url,
            model=fallback_model,
            extra_body=_no_think_body(settings.llm_fallback_disable_thinking),
            api_key=settings.effective_llm_fallback_api_key,
        )
        return FailoverLlmClient([primary, fallback])
    return primary


@router.post("/assistant/chat")
async def assistant_chat(
    request: AssistantChatRequest,
    user_id_hash: Annotated[str, Depends(required_public_user_hash)],
    session: Annotated[Session, Depends(get_session)],
) -> StreamingResponse:
    settings = get_settings()
    if settings.rate_limit_enabled:
        limiter = get_rate_limiter()
        # Per-session bucket first: try_count_global increments on every allowed call,
        # so checking it first would let one over-cap session burn the shared daily
        # budget with 429'd attempts.
        wait = limiter.try_take(
            "assistant",
            user_id_hash,
            capacity=settings.rate_limit_assistant_per_hour,
            per_seconds=3600.0,
        )
        if wait > 0:
            raise HTTPException(
                status_code=429,
                detail="Analyst request limit reached for this session — please retry later.",
                headers={"Retry-After": str(max(1, int(wait)))},
            )
        if not limiter.try_count_global(limit=settings.rate_limit_assistant_global_per_day):
            raise HTTPException(
                status_code=429,
                detail="The demo Analyst has reached its daily capacity — try again tomorrow.",
                headers={"Retry-After": "3600"},
            )
    llm_client = build_assistant_llm_client(settings)

    async def event_stream() -> AsyncIterator[str]:
        try:
            async with contextlib.aclosing(
                run_assistant_turn(
                    session,
                    user_id_hash,
                    request.messages,
                    request.dashboard_state,
                    llm_client,
                )
            ) as stream:
                async for event in stream:
                    yield _sse_event(event)
        except Exception:
            logger.exception("assistant turn failed mid-stream")
            yield _sse_event(
                AssistantStreamEvent(event="error", data={"message": _UNREACHABLE_MESSAGE})
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse_event(event: AssistantStreamEvent) -> str:
    return f"event: {event.event}\ndata: {json.dumps(event.data, default=str)}\n\n"
