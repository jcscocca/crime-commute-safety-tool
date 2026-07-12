from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.assistant.stream_guard import (
    HOLDBACK_WORDS,
    StreamGuardTripped,
    guarded_stream,
)


async def _deltas(parts: list[str]) -> AsyncIterator[str]:
    for part in parts:
        yield part


def _no_trip(text: str) -> str | None:
    return None


def _collect(parts: list[str], check) -> list[str]:
    async def run() -> list[str]:
        return [chunk async for chunk in guarded_stream(_deltas(parts), check)]

    return asyncio.run(run())


def test_short_clean_stream_is_flushed_at_end() -> None:
    parts = ["Two reported ", "incidents nearby."]
    released = _collect(parts, _no_trip)
    assert "".join(released) == "Two reported incidents nearby."
    # Under HOLDBACK_WORDS words total: nothing may release before the final flush.
    assert released == ["Two reported incidents nearby."]


def test_long_clean_stream_releases_incrementally_and_completely() -> None:
    words = [f"word{i} " for i in range(HOLDBACK_WORDS * 3)]
    released = _collect(words, _no_trip)
    assert "".join(released) == "".join(words)
    assert len(released) > 1  # streamed, not one lump


def test_release_lags_by_holdback_words() -> None:
    words = [f"w{i} " for i in range(HOLDBACK_WORDS + 3)]

    async def run() -> list[tuple[int, str]]:
        seen: list[tuple[int, str]] = []
        count = 0

        async def gen() -> AsyncIterator[str]:
            nonlocal count
            for word in words:
                count += 1
                yield word

        async for chunk in guarded_stream(gen(), _no_trip):
            seen.append((count, chunk))
        return seen

    seen = asyncio.run(run())
    # Every incremental release happened while at least HOLDBACK_WORDS words
    # remained unreleased (the final flush is exempt).
    consumed_words = 0
    for fed, chunk in seen[:-1]:
        consumed_words += len(chunk.split())
        assert fed - consumed_words >= HOLDBACK_WORDS


def test_trip_raises_and_never_releases_violating_suffix() -> None:
    # 20 innocuous words, then the violation appears and completes.
    safe = [f"w{i} " for i in range(20)]
    parts = safe + ["this is a dangerous", " area to be"]

    def check(text: str) -> str | None:
        return "REDIRECT" if "dangerous" in text else None

    async def run() -> list[str]:
        released: list[str] = []
        with pytest.raises(StreamGuardTripped) as excinfo:
            async for chunk in guarded_stream(_deltas(parts), check):
                released.append(chunk)
        assert excinfo.value.redirect == "REDIRECT"
        return released

    released = asyncio.run(run())
    assert "dangerous" not in "".join(released)


def test_trip_on_final_scan_before_tail_flush() -> None:
    # The violation completes in the last delta, inside the held tail.
    parts = ["all quiet ", "then dangerous"]

    def check(text: str) -> str | None:
        return "REDIRECT" if "dangerous" in text else None

    async def run() -> None:
        with pytest.raises(StreamGuardTripped):
            async for _chunk in guarded_stream(_deltas(parts), check):
                pass

    asyncio.run(run())


def test_trip_closes_upstream_iterator_deterministically() -> None:
    # On a guard trip the upstream generator (ultimately an httpx stream) must be
    # closed synchronously, not left for GC. Assert INSIDE the coroutine, before
    # loop teardown would close it anyway.
    closed = False

    async def gen() -> AsyncIterator[str]:
        nonlocal closed
        try:
            yield "this trips "
            yield "never reached"
        finally:
            closed = True

    def check(text: str) -> str | None:
        return "R" if "trips" in text else None

    async def run() -> None:
        with pytest.raises(StreamGuardTripped):
            async for _chunk in guarded_stream(gen(), check):
                pass
        assert closed is True

    asyncio.run(run())
