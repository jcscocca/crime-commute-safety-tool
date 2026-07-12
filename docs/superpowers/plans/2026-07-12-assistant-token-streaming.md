# Copper Streamed Finals + Turn Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Copper's chat replies become model-authored prose in Copper's voice, streamed token-by-token over the existing SSE channel, with honest progress events during the planning wait — while the product invariant (no safety scoring / presence claims) stays absolute via a holdback stream guard, and every failure mode degrades to today's deterministic-template behavior.

**Architecture:** Additive second streamed LLM call. The classify-only planning call is untouched. After a tool runs (or a `final` plan parses), a new streamed narration call gets the tool result + today's template summary as grounding and Copper's persona as system prompt; its deltas pass through a holdback guard (release N words behind the write head, full-text regex scan every delta) and out as many small `token` SSE events. Two new SSE event types: `status` (phase labels) and `replace` (guard-trip / fallback text swaps). One settings kill switch (`MCA_ASSISTANT_NARRATION_ENABLED=false`) restores today's exact behavior.

**Tech Stack:** FastAPI + httpx (async SSE client streaming), Pydantic settings, React + TypeScript + vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-07-12-assistant-token-streaming-design.md`

**Worktree:** `/Users/jscocca/Repos/waypoint-assistant-streaming` (branch `assistant-streaming`). All commands below run from this worktree root unless stated otherwise.

---

## File structure

| File | Role |
|---|---|
| `app/config.py` (modify) | `assistant_narration_enabled: bool = True` settings field |
| `app/assistant/schemas.py` (modify) | extend `AssistantStreamEvent.event` Literal with `"status"`, `"replace"` |
| `app/assistant/llm_client.py` (modify) | `stream()` on the protocol + both clients; `LlmStreamInterrupted` |
| `app/assistant/stream_guard.py` (create) | holdback guard: generic async wrapper, no assistant imports |
| `app/assistant/prompts.py` (modify) | `NARRATION_SYSTEM_PROMPT`, `build_narration_messages`, `build_tool_grounding` |
| `app/assistant/agent.py` (modify) | status events, `_output_guard_redirect` refactor, `_stream_final`, fallback ladder |
| `docker-compose.yml` (modify) | pass `MCA_ASSISTANT_NARRATION_ENABLED` through the env allowlist |
| `frontend/src/types.ts` (modify) | extend the `AssistantStreamEvent` union |
| `frontend/src/components/AssistantPanel.tsx` (modify) | status line render, `replace` handling, markdown draft |
| `frontend/src/styles/mapWorkspace.css` (modify) | `.mc-dock-statusline` style |
| `tests/test_openai_llm_client.py` (modify) | stream parsing tests |
| `tests/test_failover_llm_client.py` (modify) | stream failover tests |
| `tests/test_stream_guard.py` (create) | holdback guard unit tests |
| `tests/test_assistant_agent.py` (modify) | autouse kill-switch fixture + narration-mode turn tests |
| `tests/test_assistant_api.py` (modify) | autouse kill-switch fixture + one SSE serialization test |
| `frontend/src/components/AssistantPanel.test.tsx` (modify) | status/replace UI tests |
| `docs/architecture/assistant.md`, `docs/ROADMAP.md` (modify) | docs + roadmap tick |

Key existing facts an implementer must know:

- `get_settings()` (`app/config.py:122`) returns a **fresh `Settings()` on every call** — no cache. Tests override any setting with `monkeypatch.setenv("MCA_...", ...)`. Env prefix is `MCA_`, so the field `assistant_narration_enabled` reads `MCA_ASSISTANT_NARRATION_ENABLED`.
- The SSE wire format is produced by `_sse_event` in `app/api/routes_assistant.py:102` — generic over `event.event`, no change needed there.
- The frontend SSE parser (`frontend/src/api/client.ts:217-255`) is generic over event names — no change needed there either; only the TS union type and the panel handler change.
- Existing agent tests (`tests/test_assistant_agent.py`) assert exact event sequences like `["meta", "token", "done"]`. The kill switch gates **both** narration and status events, so an autouse fixture setting `MCA_ASSISTANT_NARRATION_ENABLED=false` keeps every existing test valid as the kill-switch contract. Narration-mode tests opt back in per-test with `monkeypatch.setenv(..., "true")`.
- The guard regexes and redirect strings already exist in `app/assistant/agent.py:36-138` (`_UNAMBIGUOUS_SAFETY_PATTERN` etc., `_SAFETY_REDIRECT`, `_PRESENCE_REDIRECT`). Do not modify the patterns.

---

### Task 0: Worktree environment setup

The worktree lacks `.venv` and `frontend/node_modules` (memory: `waypoint-worktree-setup`). Symlink them from the main checkout; symlinks dodge the dir-form `.gitignore`, so also add them to the shared `info/exclude`.

- [x] **Step 0.1: Create symlinks and excludes** *(done during plan setup — verify only)*

```bash
cd /Users/jscocca/Repos/waypoint-assistant-streaming
[ -e .venv ] || ln -s /Users/jscocca/Repos/waypoint/.venv .venv
[ -e frontend/node_modules ] || ln -s /Users/jscocca/Repos/waypoint/frontend/node_modules frontend/node_modules
grep -q "^.venv$" /Users/jscocca/Repos/waypoint/.git/info/exclude || printf ".venv\nfrontend/node_modules\n" >> /Users/jscocca/Repos/waypoint/.git/info/exclude
```

- [x] **Step 0.2: Verify the test suite runs from the worktree**

Run: `.venv/bin/python -m pytest tests/test_assistant_agent.py -q`
Expected: all pass (baseline green before any change).

---

### Task 1: Settings flag + SSE event schema

**Files:**
- Modify: `app/config.py` (after line 37, `assistant_role`)
- Modify: `app/assistant/schemas.py:52-54`
- Modify: `docker-compose.yml` (env block, after `MCA_LLM_FALLBACK_API_KEY` at line 50)
- Test: `tests/test_assistant_agent.py` (schema assertion added in Task 6; this task only needs the compile-level change verified by the suite)

- [x] **Step 1.1: Add the settings field**

In `app/config.py`, directly under `assistant_role: str = "waypoint_analyst"` (line 37):

```python
    # Streamed Copper narration finals + turn status events. Off = the pre-streaming
    # behavior (deterministic template finals, no status events) — a deploy-side kill
    # switch if local-model narration misbehaves.
    assistant_narration_enabled: bool = True
```

- [x] **Step 1.2: Extend the event Literal**

In `app/assistant/schemas.py`, change:

```python
class AssistantStreamEvent(BaseModel):
    event: Literal["meta", "tool", "token", "done", "error"]
    data: dict[str, Any]
```

to:

```python
class AssistantStreamEvent(BaseModel):
    event: Literal["meta", "tool", "token", "status", "replace", "done", "error"]
    data: dict[str, Any]
```

- [x] **Step 1.3: Pass the env var through the compose allowlist**

In `docker-compose.yml`, after the `MCA_LLM_FALLBACK_API_KEY` line (line 50), add:

```yaml
      MCA_ASSISTANT_NARRATION_ENABLED: "${MCA_ASSISTANT_NARRATION_ENABLED:-true}"
```

(The deploy env-allowlist gotcha: compose passes only listed vars — a missing entry means the ThinkPad deploy silently ignores `.env.deploy`.)

- [x] **Step 1.4: Run the backend suite to confirm nothing broke**

Run: `.venv/bin/python -m pytest tests/test_assistant_agent.py tests/test_assistant_api.py -q`
Expected: PASS (additive changes only).

- [x] **Step 1.5: Commit**

```bash
git add app/config.py app/assistant/schemas.py docker-compose.yml
git commit -m "feat(assistant): narration kill-switch setting + status/replace SSE event types"
```

---

### Task 2: `OpenAiLlmClient.stream` + `LlmStreamInterrupted`

**Files:**
- Modify: `app/assistant/llm_client.py`
- Test: `tests/test_openai_llm_client.py`

Contract (load-bearing for Task 3): `stream()` raises `LlmUnavailable` **only before the first delta** (connect error, HTTP error, empty stream). Any failure after the first delta raises `LlmStreamInterrupted` — the failover client must never switch endpoints mid-stream (tokens can't be unsaid).

- [x] **Step 2.1: Write the failing tests**

Append to `tests/test_openai_llm_client.py` (reuses `_DUMMY_REQUEST`, `_make_client` from the top of the file):

```python
# ---------- stream() ----------

class _FakeStreamResponse:
    """Stands in for the async-context response of httpx.AsyncClient.stream()."""

    def __init__(
        self,
        lines: list[str],
        status_code: int = 200,
        error_after: int | None = None,
    ) -> None:
        self._lines = lines
        self.status_code = status_code
        self._error_after = error_after
        self.request = _DUMMY_REQUEST

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=_DUMMY_REQUEST,
                response=httpx.Response(self.status_code, request=_DUMMY_REQUEST),
            )

    async def aiter_lines(self):
        for index, line in enumerate(self._lines):
            if self._error_after is not None and index == self._error_after:
                raise httpx.ReadError("connection dropped")
            yield line


def _patch_stream(monkeypatch: pytest.MonkeyPatch, response: _FakeStreamResponse) -> None:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_stream(self_client, method, url, **kwargs):  # noqa: ANN001
        yield response

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)


def _sse_line(content: str) -> str:
    return "data: " + json.dumps({"choices": [{"delta": {"content": content}}]})


async def _collect_stream(client: OpenAiLlmClient) -> list[str]:
    return [d async for d in client.stream([{"role": "user", "content": "hi"}], role=None)]


def test_stream_yields_deltas_and_stops_on_done(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stream(
        monkeypatch,
        _FakeStreamResponse(
            [
                _sse_line("Hel"),
                "",
                _sse_line("lo"),
                "data: [DONE]",
                _sse_line("NEVER"),
            ]
        ),
    )
    assert asyncio.run(_collect_stream(_make_client())) == ["Hel", "lo"]


def test_stream_skips_malformed_and_empty_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stream(
        monkeypatch,
        _FakeStreamResponse(
            [
                "data: {not json",
                'data: {"choices":[]}',
                'data: {"choices":[{"delta":{}}]}',
                _sse_line("ok"),
                "data: [DONE]",
            ]
        ),
    )
    assert asyncio.run(_collect_stream(_make_client())) == ["ok"]


def test_stream_empty_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stream(monkeypatch, _FakeStreamResponse(["data: [DONE]"]))
    with pytest.raises(LlmUnavailable, match="empty stream"):
        asyncio.run(_collect_stream(_make_client()))


def test_stream_pre_delta_http_error_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stream(monkeypatch, _FakeStreamResponse([], status_code=503))
    with pytest.raises(LlmUnavailable, match="unavailable"):
        asyncio.run(_collect_stream(_make_client()))


def test_stream_mid_stream_death_raises_interrupted(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.assistant.llm_client import LlmStreamInterrupted

    _patch_stream(
        monkeypatch,
        _FakeStreamResponse([_sse_line("partial"), _sse_line("x")], error_after=1),
    )

    async def run() -> list[str]:
        got: list[str] = []
        async for delta in _make_client().stream([{"role": "user", "content": "hi"}], role=None):
            got.append(delta)
        return got

    with pytest.raises(LlmStreamInterrupted):
        asyncio.run(run())


def test_stream_sets_stream_true_and_merges_extra_body(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    response = _FakeStreamResponse([_sse_line("hi"), "data: [DONE]"])
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_stream(self_client, method, url, **kwargs):  # noqa: ANN001
        captured.update(kwargs.get("json") or {})
        yield response

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    client = OpenAiLlmClient(
        base_url="http://localhost:8080/v1",
        model="test-model",
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    asyncio.run(
        _collect_stream(client)
    )
    assert captured["stream"] is True
    assert captured["chat_template_kwargs"] == {"enable_thinking": False}
```

- [x] **Step 2.2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_openai_llm_client.py -q`
Expected: new tests FAIL with `AttributeError: ... no attribute 'stream'` / ImportError for `LlmStreamInterrupted`; old tests pass.

- [x] **Step 2.3: Implement**

In `app/assistant/llm_client.py`: add imports `import json` and `from collections.abc import AsyncIterator` at the top. After `class LlmUnavailable(RuntimeError)`, add:

```python
class LlmStreamInterrupted(RuntimeError):
    """A streaming completion died after emitting at least one delta. Not safe to
    fail over (the consumer already saw text); callers replace the partial answer."""
```

Extend the protocol:

```python
class AssistantLlmClient(Protocol):
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        role: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        ...

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        role: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        ...
```

(Note: `def`, not `async def`, on the protocol — an async generator function is a sync callable returning an `AsyncIterator`. The implementations below are `async def` generator functions, which satisfy this structurally.)

Add to `OpenAiLlmClient` (below `complete`):

```python
    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        role: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        payload: dict[str, object] = {
            **self.extra_body,
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        timeout = httpx.Timeout(self.timeout_s, connect=self.connect_timeout_s)
        yielded = False
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self.request_headers(),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:") :].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except ValueError:
                            continue
                        try:
                            delta = chunk["choices"][0].get("delta") or {}
                        except (KeyError, IndexError, TypeError):
                            continue
                        content = delta.get("content")
                        if content:
                            yielded = True
                            yield content
        except httpx.HTTPError as exc:
            if yielded:
                raise LlmStreamInterrupted(
                    f"LLM stream died mid-generation: {exc}"
                ) from exc
            raise LlmUnavailable(f"LLM endpoint unavailable: {exc}") from exc
        if not yielded:
            raise LlmUnavailable(
                "LLM returned an empty stream (a reasoning model may have spent the "
                "token budget on reasoning_content — disable thinking or use an "
                "instruct model)."
            )
```

- [x] **Step 2.4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_openai_llm_client.py -q`
Expected: PASS.

- [x] **Step 2.5: Commit**

```bash
git add app/assistant/llm_client.py tests/test_openai_llm_client.py
git commit -m "feat(assistant): streaming completions on OpenAiLlmClient with mid-stream error contract"
```

---

### Task 3: `FailoverLlmClient.stream`

**Files:**
- Modify: `app/assistant/llm_client.py` (FailoverLlmClient)
- Test: `tests/test_failover_llm_client.py`

- [x] **Step 3.1: Write the failing tests**

Append to `tests/test_failover_llm_client.py`. Check the file's existing imports first — it already imports `FailoverLlmClient` and `LlmUnavailable`; add `LlmStreamInterrupted` to that import. Use these fakes (self-contained, do not depend on other fixtures in the file):

```python
class _StreamOk:
    def __init__(self, deltas: list[str]) -> None:
        self.deltas = deltas
        self.stream_called = 0

    async def stream(self, messages, *, role, temperature=None, max_tokens=None):
        self.stream_called += 1
        for delta in self.deltas:
            yield delta


class _StreamUnavailable:
    def __init__(self) -> None:
        self.stream_called = 0

    async def stream(self, messages, *, role, temperature=None, max_tokens=None):
        self.stream_called += 1
        raise LlmUnavailable("offline")
        yield  # pragma: no cover - makes this an async generator

    def __getattr__(self, name):  # base_url label used in failover logging
        if name == "base_url":
            return "http://primary"
        raise AttributeError(name)


class _StreamInterrupted:
    async def stream(self, messages, *, role, temperature=None, max_tokens=None):
        yield "partial "
        raise LlmStreamInterrupted("died mid-stream")


async def _drain(client) -> list[str]:
    return [d async for d in client.stream([{"role": "user", "content": "hi"}], role=None)]


def test_stream_uses_primary_when_healthy() -> None:
    primary = _StreamOk(["a", "b"])
    fallback = _StreamOk(["never"])
    assert asyncio.run(_drain(FailoverLlmClient([primary, fallback]))) == ["a", "b"]
    assert fallback.stream_called == 0


def test_stream_fails_over_before_first_delta() -> None:
    primary = _StreamUnavailable()
    fallback = _StreamOk(["from-fallback"])
    assert asyncio.run(_drain(FailoverLlmClient([primary, fallback]))) == ["from-fallback"]
    assert primary.stream_called == 1


def test_stream_raises_when_all_fail() -> None:
    with pytest.raises(LlmUnavailable, match="All LLM endpoints failed"):
        asyncio.run(_drain(FailoverLlmClient([_StreamUnavailable(), _StreamUnavailable()])))


def test_stream_mid_stream_interrupt_propagates_without_failover() -> None:
    fallback = _StreamOk(["never"])

    async def run() -> list[str]:
        got = []
        async for d in FailoverLlmClient([_StreamInterrupted(), fallback]).stream(
            [{"role": "user", "content": "hi"}], role=None
        ):
            got.append(d)
        return got

    with pytest.raises(LlmStreamInterrupted):
        asyncio.run(run())
    assert fallback.stream_called == 0
```

- [x] **Step 3.2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_failover_llm_client.py -q`
Expected: new tests FAIL (`FailoverLlmClient` has no `stream`); existing tests pass.

- [x] **Step 3.3: Implement**

Add to `FailoverLlmClient` (below `complete`); mirrors `complete`'s failure bookkeeping:

```python
    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        role: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        # LlmUnavailable is only raised by a client before its first delta (mid-stream
        # failures are LlmStreamInterrupted), so failing over here never repeats text.
        failures: list[str] = []
        last_exc: LlmUnavailable | None = None
        for index, client in enumerate(self.clients):
            try:
                async for delta in client.stream(
                    messages,
                    role=role,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    yield delta
                return
            except LlmUnavailable as exc:
                label = getattr(client, "base_url", f"client[{index}]")
                failures.append(f"{label}: {exc}")
                last_exc = exc
                if index + 1 < len(self.clients):
                    next_label = getattr(
                        self.clients[index + 1], "base_url", f"client[{index + 1}]"
                    )
                    logger.warning(
                        "LLM endpoint %s unavailable (%s); failing over to %s",
                        label,
                        exc,
                        next_label,
                    )
        raise LlmUnavailable(
            "All LLM endpoints failed: " + "; ".join(failures)
        ) from last_exc
```

- [x] **Step 3.4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_failover_llm_client.py -q`
Expected: PASS.

- [x] **Step 3.5: Commit**

```bash
git add app/assistant/llm_client.py tests/test_failover_llm_client.py
git commit -m "feat(assistant): streaming failover — switch endpoints only before the first delta"
```

---

### Task 4: Holdback stream guard

**Files:**
- Create: `app/assistant/stream_guard.py`
- Create: `tests/test_stream_guard.py`

The module is generic: it takes the delta iterator and a `check` callable (full accumulated text → redirect string or `None`). No imports from `agent.py` (agent imports guard, never the reverse).

- [x] **Step 4.1: Write the failing tests**

Create `tests/test_stream_guard.py`:

```python
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
```

- [x] **Step 4.2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_stream_guard.py -q`
Expected: FAIL with `ModuleNotFoundError: app.assistant.stream_guard`.

- [x] **Step 4.3: Implement**

Create `app/assistant/stream_guard.py`:

```python
from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable

# Words withheld behind the write head. Sized above the longest output-guard phrase
# (~10 words for the presence-claim spans) so a completing match always overlaps the
# unreleased tail — at worst an innocuous prefix of a violation has rendered.
HOLDBACK_WORDS = 12

_WORD = re.compile(r"\S+")


class StreamGuardTripped(Exception):
    """The accumulated narration matched an output-guard pattern."""

    def __init__(self, redirect: str) -> None:
        self.redirect = redirect
        super().__init__(redirect)


async def guarded_stream(
    deltas: AsyncIterator[str],
    check: Callable[[str], str | None],
) -> AsyncIterator[str]:
    """Re-run ``check`` over the full accumulated text on every delta, releasing
    text ``HOLDBACK_WORDS`` whole words behind the write head. ``check`` returns
    the redirect to raise with, or ``None`` when the text is clean."""
    accumulated = ""
    released = 0
    async for delta in deltas:
        accumulated += delta
        redirect = check(accumulated)
        if redirect is not None:
            raise StreamGuardTripped(redirect)
        boundary = _release_boundary(accumulated)
        if boundary > released:
            yield accumulated[released:boundary]
            released = boundary
    redirect = check(accumulated)
    if redirect is not None:
        raise StreamGuardTripped(redirect)
    if len(accumulated) > released:
        yield accumulated[released:]


def _release_boundary(text: str) -> int:
    """Character index releasable now: everything before the word that starts the
    final ``HOLDBACK_WORDS``-word tail."""
    starts = [match.start() for match in _WORD.finditer(text)]
    if len(starts) <= HOLDBACK_WORDS:
        return 0
    return starts[len(starts) - HOLDBACK_WORDS]
```

- [x] **Step 4.4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_stream_guard.py -q`
Expected: PASS.

- [x] **Step 4.5: Commit**

```bash
git add app/assistant/stream_guard.py tests/test_stream_guard.py
git commit -m "feat(assistant): holdback stream guard — full-text scan per delta, N-word release lag"
```

---

### Task 5: Narration prompt + grounding builders

**Files:**
- Modify: `app/assistant/prompts.py`
- Test: `tests/test_assistant_agent.py` (new section at the end; these are pure-function tests, no DB needed)

The narration prompt deliberately repeats the invariant rules rather than sharing a constant with `PLANNING_SYSTEM_PROMPT` — the planning literal stays byte-identical so planning reliability on gemma is untouched (spec: "deliberately deferred").

- [x] **Step 5.1: Write the failing tests**

Append to `tests/test_assistant_agent.py`:

```python
# ---------- narration prompt builders (pure functions) ----------


def test_build_tool_grounding_contains_tool_template_and_result():
    from app.assistant.prompts import build_tool_grounding

    grounding = build_tool_grounding(
        "compare_places",
        "Compared 2 places.",
        {"tool_name": "compare_places", "result": {"verdict": "not_clear"}},
    )
    assert "compare_places" in grounding
    assert "Compared 2 places." in grounding
    assert "not_clear" in grounding


def test_build_tool_grounding_trims_oversized_results():
    from app.assistant.prompts import MAX_GROUNDING_RESULT_CHARS, build_tool_grounding

    grounding = build_tool_grounding(
        "analyze_places",
        "Analyzed.",
        {"blob": "x" * (MAX_GROUNDING_RESULT_CHARS * 2)},
    )
    assert len(grounding) < MAX_GROUNDING_RESULT_CHARS + 500
    assert "trimmed" in grounding


def test_build_narration_messages_shape():
    from app.assistant.prompts import NARRATION_SYSTEM_PROMPT, build_narration_messages

    history = [
        AssistantChatMessage(role="user", content="compare my places"),
        AssistantChatMessage(role="assistant", content="on it"),
        AssistantChatMessage(role="user", content="and the verdict?"),
    ]
    built = build_narration_messages(history, "GROUNDING-BLOCK")
    assert built[0] == {"role": "system", "content": NARRATION_SYSTEM_PROMPT}
    assert [m["role"] for m in built[1:-1]] == ["user", "assistant", "user"]
    assert built[-1]["role"] == "user"
    assert "GROUNDING-BLOCK" in built[-1]["content"]
    assert "ONLY" in built[-1]["content"]
```

- [x] **Step 5.2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_assistant_agent.py -q -k "grounding or narration_messages"`
Expected: FAIL with ImportError.

- [x] **Step 5.3: Implement**

Append to `app/assistant/prompts.py`:

```python
NARRATION_SYSTEM_PROMPT = """You are Copper, Waypoint's case-desk analyst — a dry,
methodical records hound. Write the final chat reply to the user's last message.
Non-negotiable rules:
- Use ONLY the facts in the grounding block. Never invent, estimate, or extrapolate
  numbers, dates, addresses, place names, or findings that are not in it.
- Do not label places safe, unsafe, dangerous, or risky. Do not rank, score, or rate
  places or areas by safety, danger, or risk. No personal safety or risk scores.
  Never recommend where to live, move, stay, or avoid.
- Never claim the user was present at, witnessed, or was affected by any incident.
- Describe results in the active data layer's terms: reported incidents are reports,
  arrests are enforcement activity (not confirmed offenses at that spot), 911 calls
  are requests for service (not confirmed incidents).
- If the grounding says data is missing, insufficient, or not statistically clear,
  say so plainly — do not soften or upgrade the verdict.
- 2–4 sentences of plain prose. No headings, no bullet lists, no exclamation marks.
Voice: terse, direct, a detective reading from the file."""

# Ceiling on the tool-result JSON embedded in the narration grounding — keeps a big
# compare/analyze payload from blowing up the narrator's prompt.
MAX_GROUNDING_RESULT_CHARS = 4000


def build_tool_grounding(
    tool_name: str,
    template_summary: str,
    tool_result: dict[str, object],
) -> str:
    result_json = json.dumps(tool_result, default=str)
    if len(result_json) > MAX_GROUNDING_RESULT_CHARS:
        result_json = result_json[:MAX_GROUNDING_RESULT_CHARS] + "…(trimmed)"
    return (
        f"Tool run: {tool_name}\n"
        f"Verified one-line summary (authoritative): {template_summary}\n"
        f"Tool result JSON:\n{result_json}"
    )


def build_narration_messages(
    messages: list[AssistantChatMessage],
    grounding: str,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": NARRATION_SYSTEM_PROMPT},
        *[message.model_dump() for message in messages[-4:]],
        {
            "role": "user",
            "content": (
                "Grounding block — the verified facts for your reply. Answer my "
                "last message using ONLY these facts:\n" + grounding
            ),
        },
    ]
```

- [x] **Step 5.4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_assistant_agent.py -q -k "grounding or narration_messages"`
Expected: PASS.

- [x] **Step 5.5: Commit**

```bash
git add app/assistant/prompts.py tests/test_assistant_agent.py
git commit -m "feat(assistant): Copper narration prompt + grounding builders"
```

---

### Task 6: Agent integration — status events, streamed finals, fallback ladder

**Files:**
- Modify: `app/assistant/agent.py`
- Test: `tests/test_assistant_agent.py`, `tests/test_assistant_api.py`

This is the core task. The kill switch gates **all** new behavior (status events AND narration): off = byte-for-byte today's event sequences.

- [x] **Step 6.1: Add the autouse kill-switch fixture**

Only `tests/test_assistant_agent.py` needs it — `tests/test_assistant_api.py` stubs `run_assistant_turn` itself and never executes agent code. At the top of `tests/test_assistant_agent.py` (after imports; also add `import pytest` if absent):

```python
@pytest.fixture(autouse=True)
def _narration_off(monkeypatch: pytest.MonkeyPatch):
    # Existing turn tests pin the pre-streaming contract, which is exactly the
    # kill-switch mode. Streaming-mode tests opt back in per-test with
    # monkeypatch.setenv("MCA_ASSISTANT_NARRATION_ENABLED", "true").
    monkeypatch.setenv("MCA_ASSISTANT_NARRATION_ENABLED", "false")
```

Run: `.venv/bin/python -m pytest tests/test_assistant_agent.py -q`
Expected: PASS (flag doesn't exist in agent code yet, fixture is inert — this pins the baseline).

- [x] **Step 6.2: Write the failing narration-mode tests**

Append to `tests/test_assistant_agent.py`:

```python
# ---------- streamed narration mode (MCA_ASSISTANT_NARRATION_ENABLED=true) ----------

from app.assistant.llm_client import LlmStreamInterrupted, LlmUnavailable  # noqa: E402


class FakeStreamClient(FakeClient):
    """FakeClient plus a scripted stream() for the narration call."""

    def __init__(
        self,
        responses: list[str],
        deltas: list[str],
        fail_after: int | None = None,
        fail_before_start: bool = False,
    ) -> None:
        super().__init__(responses)
        self.deltas = deltas
        self.fail_after = fail_after
        self.fail_before_start = fail_before_start
        self.stream_calls: list[list[dict[str, str]]] = []

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        role: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        self.stream_calls.append(messages)
        if self.fail_before_start:
            raise LlmUnavailable("narrator offline")
        for index, delta in enumerate(self.deltas):
            if self.fail_after is not None and index == self.fail_after:
                raise LlmStreamInterrupted("died mid-stream")
            yield delta


def _narration_on(monkeypatch):
    monkeypatch.setenv("MCA_ASSISTANT_NARRATION_ENABLED", "true")


def test_tool_turn_streams_narration_with_status_events(tmp_path, monkeypatch):
    _narration_on(monkeypatch)
    session, user_hash = _session_with_place_and_crime(tmp_path)
    deltas = ["Two places ", "on file. ", "Counts are ", "close; nothing ", "statistically clear."]
    client = FakeStreamClient(
        ['{"type":"tool_call","tool_name":"compare_places","arguments":{}}'],
        deltas,
    )
    try:
        events = asyncio.run(
            _collect(
                session,
                user_hash,
                [AssistantChatMessage(role="user", content="Compare my places")],
                AssistantDashboardState(selected_place_ids=["place-1", "place-2"]),
                client,
            )
        )
    finally:
        session.close()

    names = [event.event for event in events]
    assert names[0] == "meta"
    assert names[-1] == "done"
    assert "tool" in names
    # Status markers present and ordered: interpreting -> running tool -> writing up.
    status_labels = [e.data["label"] for e in events if e.event == "status"]
    assert status_labels[0].startswith("interpreting")
    assert any(label.startswith("running compare_places") for label in status_labels)
    assert status_labels[-1].startswith("writing up")
    # The narration IS the answer, streamed in multiple deltas.
    tokens = [e.data["delta"] for e in events if e.event == "token"]
    assert len(tokens) > 1
    assert "".join(tokens) == "".join(deltas)
    # Grounding carried the template summary to the narrator.
    narration_prompt = json.dumps(client.stream_calls[0])
    assert "Compared" in narration_prompt or "compare_places" in narration_prompt


def test_narration_guard_trip_replaces_with_redirect(tmp_path, monkeypatch):
    _narration_on(monkeypatch)
    from app.assistant.agent import _SAFETY_REDIRECT

    session, user_hash = _session_with_place_and_crime(tmp_path)
    # 20 innocuous words, then a safety-ranking phrase completes.
    safe_words = [f"note{i} " for i in range(20)]
    client = FakeStreamClient(
        ['{"type":"tool_call","tool_name":"compare_places","arguments":{}}'],
        safe_words + ["this looks like a dangerous", " area overall."],
    )
    try:
        events = asyncio.run(
            _collect(
                session,
                user_hash,
                [AssistantChatMessage(role="user", content="Compare my places")],
                AssistantDashboardState(selected_place_ids=["place-1", "place-2"]),
                client,
            )
        )
    finally:
        session.close()

    replaces = [e for e in events if e.event == "replace"]
    assert len(replaces) == 1
    assert replaces[0].data["text"] == _SAFETY_REDIRECT
    released = "".join(e.data["delta"] for e in events if e.event == "token")
    assert "dangerous" not in released
    assert events[-1].event == "done"


def test_narration_mid_stream_death_replaces_with_template(tmp_path, monkeypatch):
    _narration_on(monkeypatch)
    session, user_hash = _session_with_place_and_crime(tmp_path)
    client = FakeStreamClient(
        ['{"type":"tool_call","tool_name":"compare_places","arguments":{}}'],
        [f"w{i} " for i in range(30)],
        fail_after=20,
    )
    try:
        events = asyncio.run(
            _collect(
                session,
                user_hash,
                [AssistantChatMessage(role="user", content="Compare my places")],
                AssistantDashboardState(selected_place_ids=["place-1", "place-2"]),
                client,
            )
        )
    finally:
        session.close()

    replaces = [e for e in events if e.event == "replace"]
    assert len(replaces) == 1
    # The replacement is the deterministic template (starts like today's summary).
    assert replaces[0].data["text"]
    assert events[-1].event == "done"


def test_narration_unreachable_falls_back_to_template(tmp_path, monkeypatch):
    _narration_on(monkeypatch)
    session, user_hash = _session_with_place_and_crime(tmp_path)
    client = FakeStreamClient(
        ['{"type":"tool_call","tool_name":"compare_places","arguments":{}}'],
        [],
        fail_before_start=True,
    )
    try:
        events = asyncio.run(
            _collect(
                session,
                user_hash,
                [AssistantChatMessage(role="user", content="Compare my places")],
                AssistantDashboardState(selected_place_ids=["place-1", "place-2"]),
                client,
            )
        )
    finally:
        session.close()

    names = [event.event for event in events]
    assert "replace" in names
    assert names[-1] == "done"
    assert not any(e.event == "error" for e in events)  # seamless fallback, not an error


def test_narration_clean_but_empty_stream_falls_back_to_template(tmp_path, monkeypatch):
    _narration_on(monkeypatch)
    session, user_hash = _session_with_place_and_crime(tmp_path)
    client = FakeStreamClient(
        ['{"type":"tool_call","tool_name":"compare_places","arguments":{}}'],
        [],
    )
    try:
        events = asyncio.run(
            _collect(
                session,
                user_hash,
                [AssistantChatMessage(role="user", content="Compare my places")],
                AssistantDashboardState(selected_place_ids=["place-1", "place-2"]),
                client,
            )
        )
    finally:
        session.close()

    replaces = [e for e in events if e.event == "replace"]
    assert len(replaces) == 1
    assert replaces[0].data["text"]
    assert events[-1].event == "done"


def test_answer_turn_streams_with_plan_message_as_grounding(tmp_path, monkeypatch):
    _narration_on(monkeypatch)
    session, user_hash = _session_with_place_and_crime(tmp_path)
    client = FakeStreamClient(
        ['{"type":"final","message":"One saved place is on file."}'],
        ["One place ", "on file."],
    )
    try:
        events = asyncio.run(
            _collect(
                session,
                user_hash,
                [AssistantChatMessage(role="user", content="What do you see?")],
                AssistantDashboardState(selected_place_ids=["place-1"]),
                client,
            )
        )
    finally:
        session.close()

    tokens = [e.data["delta"] for e in events if e.event == "token"]
    assert "".join(tokens) == "One place on file."
    assert "One saved place is on file." in json.dumps(client.stream_calls[0])


def test_answer_turn_guardtripping_draft_skips_narration(tmp_path, monkeypatch):
    _narration_on(monkeypatch)
    from app.assistant.agent import _SAFETY_REDIRECT

    session, user_hash = _session_with_place_and_crime(tmp_path)
    client = FakeStreamClient(
        ['{"type":"final","message":"This is a dangerous area."}'],
        ["should never stream"],
    )
    try:
        events = asyncio.run(
            _collect(
                session,
                user_hash,
                [AssistantChatMessage(role="user", content="What do you see?")],
                AssistantDashboardState(selected_place_ids=["place-1"]),
                client,
            )
        )
    finally:
        session.close()

    tokens = [e.data["delta"] for e in events if e.event == "token"]
    assert tokens == [_SAFETY_REDIRECT]
    assert client.stream_calls == []  # never narrate a violating draft


def test_kill_switch_preserves_todays_exact_sequence(tmp_path):
    # No _narration_on: the autouse fixture holds the switch off.
    session, user_hash = _session_with_place_and_crime(tmp_path)
    client = FakeStreamClient(
        ['{"type":"tool_call","tool_name":"compare_places","arguments":{}}'],
        ["never streamed"],
    )
    try:
        events = asyncio.run(
            _collect(
                session,
                user_hash,
                [AssistantChatMessage(role="user", content="Compare my places")],
                AssistantDashboardState(selected_place_ids=["place-1", "place-2"]),
                client,
            )
        )
    finally:
        session.close()

    assert [event.event for event in events] == ["meta", "tool", "token", "done"]
    assert client.stream_calls == []
```

- [x] **Step 6.3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_assistant_agent.py -q -k "narration or kill_switch or status_events"`
Expected: new tests FAIL (no status events, single token, no replace); baseline tests still pass.

- [x] **Step 6.4: Implement in `app/assistant/agent.py`**

Add imports (top of file):

```python
from app.assistant.llm_client import (
    AssistantLlmClient,
    LlmStreamInterrupted,
    LlmUnavailable,
)
from app.assistant.prompts import (
    build_narration_messages,
    build_planning_messages,
    build_tool_grounding,
)
from app.assistant.stream_guard import StreamGuardTripped, guarded_stream
```

Add module constants (near `_UNREACHABLE_MESSAGE`):

```python
_NARRATION_TEMPERATURE = 0.4
_NARRATION_MAX_TOKENS = 256
_STATUS_INTERPRETING = "interpreting your request…"
_STATUS_WRITING = "writing up…"
```

Add two helpers (below `_output_ranks_places`):

```python
def _output_guard_redirect(text: str) -> str | None:
    """The output-side invariant guard as a single predicate: the matching redirect
    when the text violates it, else None. Used on full finals and, via the stream
    guard, on accumulated narration text every delta."""
    if _contains_safety_ranking(text) or _output_ranks_places(text):
        return _SAFETY_REDIRECT
    if _claims_user_presence(text):
        return _PRESENCE_REDIRECT
    return None


async def _stream_final(
    llm_client: AssistantLlmClient,
    narration_messages: list[dict[str, str]],
    fallback_text: str,
    role: str,
) -> AsyncIterator[AssistantStreamEvent]:
    """Stream the narrated final through the holdback guard. On a guard trip,
    replace with the redirect; on any narration failure (unreachable, empty,
    mid-stream death), replace with fallback_text. Always ends with done."""
    yielded_any = False
    try:
        async for chunk in guarded_stream(
            llm_client.stream(
                narration_messages,
                role=role,
                temperature=_NARRATION_TEMPERATURE,
                max_tokens=_NARRATION_MAX_TOKENS,
            ),
            _output_guard_redirect,
        ):
            yielded_any = True
            yield AssistantStreamEvent(event="token", data={"delta": chunk})
    except StreamGuardTripped as trip:
        yield AssistantStreamEvent(event="replace", data={"text": trip.redirect})
        yield AssistantStreamEvent(event="done", data={})
        return
    except (LlmUnavailable, LlmStreamInterrupted):
        yield AssistantStreamEvent(event="replace", data={"text": fallback_text})
        yield AssistantStreamEvent(event="done", data={})
        return
    if not yielded_any:
        # A protocol-abiding client that ends cleanly with zero deltas (the real
        # client raises LlmUnavailable instead) must still produce an answer.
        yield AssistantStreamEvent(event="replace", data={"text": fallback_text})
    yield AssistantStreamEvent(event="done", data={})
```

Rework `run_assistant_turn`. The guard-redirect early returns (lines 167-174) and the planning call (176-189) are unchanged, except: insert after the two input-guard blocks, just before the `try` around the planning call:

```python
    narrate = settings.assistant_narration_enabled
    if narrate:
        yield AssistantStreamEvent(event="status", data={"label": _STATUS_INTERPRETING})
```

Replace the tool-plan block's final three yields (currently lines 207-209: `tool`, `token` summary, `done`) — and add the pre-execution status. The full tool branch becomes:

```python
    if plan.get("type") == "tool_call":
        tool_name = str(plan.get("tool_name"))
        if narrate:
            yield AssistantStreamEvent(
                event="status", data={"label": f"running {tool_name}…"}
            )
        try:
            tool_result = execute_tool(
                session,
                user_id_hash,
                tool_name,
                _tool_arguments(tool_name, dashboard_state, plan.get("arguments")),
            )
        except AssistantClarification as exc:
            yield AssistantStreamEvent(event="token", data={"delta": str(exc)})
            yield AssistantStreamEvent(event="done", data={})
            return
        except (AssistantToolError, ValueError) as exc:
            yield AssistantStreamEvent(event="error", data={"message": str(exc)})
            return
        yield AssistantStreamEvent(event="tool", data=tool_result)
        summary = build_tool_summary(tool_result)
        if not narrate:
            yield AssistantStreamEvent(event="token", data={"delta": summary})
            yield AssistantStreamEvent(event="done", data={})
            return
        yield AssistantStreamEvent(event="status", data={"label": _STATUS_WRITING})
        grounding = build_tool_grounding(tool_name, summary, tool_result)
        async for event in _stream_final(
            llm_client,
            build_narration_messages(messages, grounding),
            summary,
            settings.assistant_role,
        ):
            yield event
        return
```

Replace the final-message block (currently lines 212-225) with:

```python
    try:
        message = _final_message(plan)
    except ValueError as exc:
        yield AssistantStreamEvent(event="error", data={"message": str(exc)})
        return
    # Output-side invariant guard: a model answer that slipped past the input guard must not
    # stream safety-ranking language, place-ranking/livability prose, or a claim that the user
    # was present at an incident; replace it with the matching redirect.
    redirect = _output_guard_redirect(message)
    if not narrate or redirect is not None:
        # Kill switch, or the draft itself violates: emit the (guarded) text at once —
        # never hand a violating draft to the narrator.
        yield AssistantStreamEvent(event="token", data={"delta": redirect or message})
        yield AssistantStreamEvent(event="done", data={})
        return
    yield AssistantStreamEvent(event="status", data={"label": _STATUS_WRITING})
    async for event in _stream_final(
        llm_client,
        build_narration_messages(messages, "Draft answer (verified): " + message),
        message,
        settings.assistant_role,
    ):
        yield event
```

- [x] **Step 6.5: Run the agent suites**

Run: `.venv/bin/python -m pytest tests/test_assistant_agent.py tests/test_assistant_api.py -q`
Expected: PASS (both kill-switch baseline and narration-mode tests).

- [x] **Step 6.6: Add one API-level SSE serialization test**

Append to `tests/test_assistant_api.py`, following the file's existing `test_assistant_chat_streams_agent_events` pattern (stub `run_assistant_turn` on the routes module — the point is that the route and `_sse_event` pass the new event names through unmodified):

```python
def test_assistant_chat_serializes_status_and_replace_events(monkeypatch, tmp_path):
    from app.api import routes_assistant

    async def fake_run_assistant_turn(*args, **kwargs):
        yield AssistantStreamEvent(event="status", data={"label": "writing up…"})
        yield AssistantStreamEvent(event="token", data={"delta": "partial "})
        yield AssistantStreamEvent(event="replace", data={"text": "Full answer."})
        yield AssistantStreamEvent(event="done", data={})

    monkeypatch.setattr(routes_assistant, "run_assistant_turn", fake_run_assistant_turn)
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    client = TestClient(app)
    client.post("/sessions")

    response = client.post(
        "/assistant/chat",
        json={
            "messages": [{"role": "user", "content": "Compare my places"}],
            "dashboard_state": {"selected_place_ids": []},
        },
    )

    assert response.status_code == 200
    assert "event: status" in response.text
    assert '"label": "writing up' in response.text
    assert "event: replace" in response.text
    assert '"text": "Full answer."' in response.text
    assert "event: done" in response.text
```

- [x] **Step 6.7: Run to verify pass, then the full backend gate**

Run: `.venv/bin/python -m pytest tests/test_assistant_api.py -q` then `.venv/bin/python -m pytest -q` and `.venv/bin/ruff check .`
Expected: all PASS. If unrelated agent tests fail on the new `status` events, they are missing the autouse fixture — fix by confirming Step 6.1 landed in that file, not by editing assertions.

- [x] **Step 6.8: Commit**

```bash
git add app/assistant/agent.py tests/test_assistant_agent.py tests/test_assistant_api.py
git commit -m "feat(assistant): streamed Copper finals with holdback guard, status events, template fallback ladder"
```

---

### Task 7: Frontend — event types, status line, replace handling

**Files:**
- Modify: `frontend/src/types.ts:195-200`
- Modify: `frontend/src/components/AssistantPanel.tsx`
- Modify: `frontend/src/styles/mapWorkspace.css` (near `.mc-dock-log`, line ~107)
- Test: `frontend/src/components/AssistantPanel.test.tsx`

- [x] **Step 7.1: Write the failing tests**

Append inside the `describe("AssistantPanel", ...)` block of `AssistantPanel.test.tsx` (the `sseResponse` helper and `dashboardState` fixture already exist at the top of the file):

```tsx
  it("shows status labels transiently and clears them on the first token", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse(
        'event: status\ndata: {"label":"interpreting your request…"}\n\n' +
          'event: status\ndata: {"label":"writing up…"}\n\n' +
          'event: token\ndata: {"delta":"Two places on file."}\n\n' +
          "event: done\ndata: {}\n\n",
      ),
    );

    render(<AssistantPanel dashboardState={dashboardState} />);
    fireEvent.change(screen.getByLabelText("Analyst message"), { target: { value: "compare" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Two places on file.")).toBeInTheDocument();
    expect(screen.queryByText("interpreting your request…")).not.toBeInTheDocument();
    expect(screen.queryByText("writing up…")).not.toBeInTheDocument();
  });

  it("replace resets the draft and commits the replacement text", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse(
        'event: token\ndata: {"delta":"partial answer that gets "}\n\n' +
          'event: replace\ndata: {"text":"Final replacement answer."}\n\n' +
          "event: done\ndata: {}\n\n",
      ),
    );

    render(<AssistantPanel dashboardState={dashboardState} />);
    fireEvent.change(screen.getByLabelText("Analyst message"), { target: { value: "hi" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Final replacement answer.")).toBeInTheDocument();
    expect(screen.queryByText(/partial answer that gets/)).not.toBeInTheDocument();
  });
```

- [x] **Step 7.2: Run to verify failure**

Run: `cd frontend && npx vitest run src/components/AssistantPanel.test.tsx`
Expected: the two new tests FAIL (status text handled as unknown event / replace ignored so partial text persists).

- [x] **Step 7.3: Implement**

`frontend/src/types.ts` — extend the union:

```ts
export type AssistantStreamEvent =
  | { event: "meta"; data: Record<string, unknown> }
  | { event: "tool"; data: { tool_name?: string; result?: unknown; [key: string]: unknown } }
  | { event: "token"; data: { delta?: string } }
  | { event: "status"; data: { label?: string } }
  | { event: "replace"; data: { text?: string } }
  | { event: "done"; data: Record<string, unknown> }
  | { event: "error"; data: { message?: string } };
```

`AssistantPanel.tsx` — add state next to `draft` (line ~30): `const [statusLine, setStatusLine] = useState("");`

In `sendTurn`'s `onEvent` handler (lines 56-70), extend:

```ts
            if (event.event === "status") {
              setStatusLine(String(event.data.label ?? ""));
            }
            if (event.event === "token") {
              assistantText += event.data.delta ?? "";
              setStatusLine("");
              setDraft(assistantText);
            }
            if (event.event === "replace") {
              assistantText = String(event.data.text ?? "");
              setStatusLine("");
              setDraft(assistantText);
            }
```

In the `finally` block (line ~83), add `setStatusLine("");` beside `setSending(false);`.

In the render, the draft/status block (line ~134) becomes (draft switches to markdown so streaming text renders formatting as it grows):

```tsx
            {draft ? (
              <div className="mc-dock-msg is-assistant">
                <ReactMarkdown>{draft}</ReactMarkdown>
              </div>
            ) : null}
            {!draft && statusLine ? (
              <div className="mc-dock-msg is-assistant mc-dock-statusline">{statusLine}</div>
            ) : null}
```

`frontend/src/styles/mapWorkspace.css` — after the `.mc-dock-log` rule (line ~107):

```css
.mc-dock-statusline{font-style:italic;color:var(--text-dim);}
```

- [x] **Step 7.4: Run to verify pass**

Run: `cd frontend && npx vitest run src/components/AssistantPanel.test.tsx`
Expected: PASS, including the pre-existing panel tests (markdown draft must not break them).

- [x] **Step 7.5: Frontend full gate**

Run: `cd frontend && npm test && npm run build`
Expected: PASS (build catches the TS union changes everywhere, e.g. MapWorkspace handlers).

- [x] **Step 7.6: Commit**

```bash
git add frontend/src/types.ts frontend/src/components/AssistantPanel.tsx frontend/src/styles/mapWorkspace.css frontend/src/components/AssistantPanel.test.tsx
git commit -m "feat(frontend): render status lines and replace events in the Copper dock; markdown draft"
```

---

### Task 8: Docs + roadmap

**Files:**
- Modify: `docs/architecture/assistant.md`
- Modify: `docs/ROADMAP.md` (Phase 7 section, before `## Waypoint on iOS` at line ~245)

- [x] **Step 8.1: Update the assistant architecture doc**

Read `docs/architecture/assistant.md` first; update the turn-flow / SSE-events description to match reality: the seven event types (`meta`, `status`, `tool`, `token`, `replace`, `done`, `error`), the narration call (grounded on the tool result + template, Copper persona, `stream: true`), the holdback stream guard (full-text scan per delta, 12-word release lag, complete violating phrase can never render), the fallback ladder (guard trip → redirect; narration unreachable/empty/mid-stream death → deterministic template), and the `MCA_ASSISTANT_NARRATION_ENABLED` kill switch. Keep the doc's existing voice and structure — amend sections, don't rewrite the file.

- [x] **Step 8.2: Add the roadmap item**

In `docs/ROADMAP.md`, at the end of the Phase 7 item list (before `## Waypoint on iOS (2026-07-10)`):

```markdown
- [x] **Copper streamed finals + turn progress:** model-authored replies in Copper's
  voice streamed token-by-token (second, streamed narration call grounded on the tool
  result + deterministic template), honest `status` phase events during the planning
  wait, and a holdback stream guard that keeps the no-safety-scoring invariant absolute
  mid-stream. Kill switch `MCA_ASSISTANT_NARRATION_ENABLED`. Spec:
  `docs/superpowers/specs/2026-07-12-assistant-token-streaming-design.md`.
```

- [x] **Step 8.3: Commit**

```bash
git add docs/architecture/assistant.md docs/ROADMAP.md
git commit -m "docs: assistant streaming architecture + roadmap tick"
```

---

### Task 9: Full verification gate

- [x] **Step 9.1: Run the complete gate from the worktree root**

Run: `make test-all`
Expected: pytest + ruff + frontend `npm test` + `npm run build` all green. Fix anything that fails before proceeding (the fix belongs to whichever task introduced it).

- [x] **Step 9.2: Check off all boxes in this plan and re-read the spec**

Confirm each spec section (§1–§9) maps to landed code. Spec §8's test list must each have a passing test.

- [x] **Step 9.3: Final commit if anything moved, then hand off**

The branch is ready for PR per the roadmap cadence (user squash-merges). PR body should note: behavior with the kill switch off is byte-identical to main; item 4 of `docs/IOS.md` becomes literally true on the next on-device run.
