# Tabby-Central Slice 2: Commands + Degraded Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A no-LLM `POST /assistant/commands` endpoint executing a fixed command enum over the existing tool layer, machine-readable error codes distinguishing LLM outage from tool failure, a new `update_filters` tool, and a frontend `useAssistantTurn` hook so chips run as structured commands and only free-text input degrades when the LLM is down.

**Architecture:** The command route reuses the chat route's SSE vocabulary (`meta/tool/token/done/error` via `_sse_event`) and the existing `execute_tool` + `build_tool_summary` deterministic path — no LLM client is ever constructed. Pydantic's `Literal` command enum is the security boundary keeping the three unadvertised tool handlers unreachable. On the frontend, the turn machinery (busy/draft/status/tool-activity/offline) hoists out of `AssistantPanel` into a `useAssistantTurn` hook owned by `MapWorkspace` — fixing draft loss across rail remounts and giving chat and commands one shared event reducer. `AssistantPanel` becomes presentational.

**Tech Stack:** FastAPI + pydantic + in-process token-bucket rate limiter (`app/ratelimit.py`), SSE over StreamingResponse; React 18 + TS, Vitest.

**Spec:** `docs/superpowers/specs/2026-07-19-tabby-central-redesign-design.md` (Slice 2). Slice-2 scope notes: commands carry explicit `arguments` (no `dashboard_state` — the LLM isn't there to fill args from context, so the client passes e.g. `place_ids` itself). Post-analysis follow-up chips and proactive moments stay in Slices 3/5; this slice only converts the existing empty-state chips.

**Worktree:** dedicated worktree cut from `main`. Backend: `make install` once, then `.venv/bin/python -m pytest tests -q`. Frontend from `frontend/`: `npm test -- <file>`, `npx tsc --noEmit`. Full gate `make test-all`.

---

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `app/assistant/agent.py` | modify | `code` field on error events |
| `app/api/routes_assistant.py` | modify | `code` on catch-all error frame; new `/assistant/commands` route |
| `app/assistant/tools.py` | modify | `UpdateFiltersArgs` + `_update_filters` handler + dispatch |
| `app/assistant/semantic_layer.py` | modify | `update_filters` entry in `AVAILABLE_TOOLS` |
| `app/assistant/schemas.py` | modify | `AssistantCommandRequest` |
| module defining `build_tool_summary` (imported by `agent.py`) | modify | summary case for `update_filters` |
| `app/config.py` | modify | `rate_limit_assistant_commands_per_hour` setting |
| `tests/test_assistant_agent.py`, `tests/test_assistant_api.py`, `tests/test_assistant_tools.py` | modify | code assertions, tool tests |
| `tests/test_assistant_commands_api.py` | create | command-route tests |
| `tests/test_internal_surface.py` | modify | add `/assistant/commands` to `PUBLIC_PATHS` |
| `frontend/src/api/client.ts` | modify | shared SSE helper + `streamAssistantCommand` |
| `frontend/src/types.ts` | modify | `code` on the error event data |
| `frontend/src/lib/useAssistantTurn.ts` (+`.test.ts`) | create | the shared turn reducer/hook |
| `frontend/src/lib/assistantBridge.ts` (+ its test) | modify | `update_filters` → settings effect |
| `frontend/src/components/AssistantPanel.tsx` (+`.test.tsx`) | modify | presentational rewrite; mixed prompt/command chips; offline gating |
| `frontend/src/components/MapWorkspace.tsx` (+`.test.tsx`) | modify | own `useAssistantTurn`; enrich command args; wire props |

---

### Task 1: Machine-readable error codes on the chat path

**Files:** Modify `app/assistant/agent.py`, `app/api/routes_assistant.py`; tests in `tests/test_assistant_agent.py`, `tests/test_assistant_api.py`.

- [ ] **Step 1: Write/extend the failing tests**

In `tests/test_assistant_agent.py`, find the existing planning-failure test (grep `_UNREACHABLE` or `LlmUnavailable`). Extend its error-event assertion to also require `event.data["code"] == "llm_unreachable"`. Likewise find the tool-error test (a `FakeClient` returning a `tool_call` plan for a tool that raises `AssistantToolError`) and assert `event.data["code"] == "tool_error"`. If either test doesn't exist, add it following the file's `FakeClient` idiom (an object with `async def complete(self, messages, *, role, temperature=None, max_tokens=None)` that raises `LlmUnavailable` / returns a canned `tool_call` JSON for a failing tool).

In `tests/test_assistant_api.py`, extend `test_assistant_chat_emits_terminal_error_frame_when_turn_raises` to assert the terminal error frame's data includes `"code": "internal"`.

- [ ] **Step 2: Run to verify the new assertions fail**

Run: `.venv/bin/python -m pytest tests/test_assistant_agent.py tests/test_assistant_api.py -q`
Expected: FAIL on the `code` assertions (KeyError/mismatch).

- [ ] **Step 3: Implement**

In `app/assistant/agent.py` (three touch points, all additive to existing `data` dicts):
- The planning-failure branch (`except LlmUnavailable`, ~L203-205): `data={"message": _UNREACHABLE_MESSAGE, "code": "llm_unreachable"}`.
- The tool-error branch (`except (AssistantToolError, ValueError)` in the tool path): add `"code": "tool_error"` to the existing error data.
- If any other `event="error"` yield exists in this file, give it `"code": "internal"`.

In `app/api/routes_assistant.py`, the mid-stream catch-all (~L108): `data={"message": _UNREACHABLE_MESSAGE, "code": "internal"}` (message unchanged; the code distinguishes "unexpected exception" from a diagnosed LLM outage).

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_assistant_agent.py tests/test_assistant_api.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add app/assistant/agent.py app/api/routes_assistant.py tests/test_assistant_agent.py tests/test_assistant_api.py
git commit -m "feat(assistant): machine-readable codes on stream error events"
```

---

### Task 2: `update_filters` tool

**Files:** Modify `app/assistant/tools.py`, `app/assistant/semantic_layer.py`, the `build_tool_summary` module; test `tests/test_assistant_tools.py`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_assistant_tools.py` (match its existing fixture style for `session`/`user_id_hash` — update_filters touches no DB, so plain calls work):

```python
def test_update_filters_echoes_validated_patch(session):
    result = execute_tool(
        session, "user-hash", "update_filters",
        {"radius_m": 500, "analysis_start_date": "2026-01-01", "layer": "arrests"},
    )
    assert result["tool_name"] == "update_filters"
    assert result["result"]["patch"] == {
        "radius_m": 500,
        "analysis_start_date": "2026-01-01",
        "layer": "arrests",
    }


def test_update_filters_empty_category_clears_to_all(session):
    result = execute_tool(session, "user-hash", "update_filters", {"offense_category": ""})
    assert result["result"]["patch"] == {"offense_category": None}


def test_update_filters_requires_at_least_one_field(session):
    with pytest.raises(AssistantClarification):
        execute_tool(session, "user-hash", "update_filters", {})


def test_update_filters_rejects_bad_values(session):
    with pytest.raises(AssistantToolError):
        execute_tool(session, "user-hash", "update_filters", {"radius_m": 5})
    with pytest.raises(AssistantToolError):
        execute_tool(session, "user-hash", "update_filters", {"layer": "sonar"})
    with pytest.raises(AssistantToolError):
        execute_tool(
            session, "user-hash", "update_filters",
            {"analysis_start_date": "2026-07-01", "analysis_end_date": "2026-01-01"},
        )
```

(Import `AssistantClarification`, `AssistantToolError`, `execute_tool` the way the file already does.)

- [ ] **Step 2: Run to verify fail** — `.venv/bin/python -m pytest tests/test_assistant_tools.py -q` → FAIL (`Unknown assistant tool: update_filters`).

- [ ] **Step 3: Implement**

In `app/assistant/tools.py`, near the other args models:

```python
class UpdateFiltersArgs(BaseModel):
    radius_m: int | None = Field(default=None, ge=50, le=5000)
    analysis_start_date: date | None = None
    analysis_end_date: date | None = None
    # "" clears to all-reported (echoed as None, matching _settings_used).
    offense_category: Literal["", "PROPERTY", "PERSON", "SOCIETY"] | None = None
    layer: Literal["reported", "arrests", "calls"] | None = None

    @model_validator(mode="after")
    def _dates_ordered(self) -> "UpdateFiltersArgs":
        if (
            self.analysis_start_date is not None
            and self.analysis_end_date is not None
            and self.analysis_start_date > self.analysis_end_date
        ):
            raise ValueError("start date must be on or before end date")
        return self
```

Handler (patch keys deliberately identical to `_settings_used` so the frontend bridge's `settingsFrom` applies it unchanged):

```python
def _update_filters(args: UpdateFiltersArgs) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if args.radius_m is not None:
        patch["radius_m"] = args.radius_m
    if args.analysis_start_date is not None:
        patch["analysis_start_date"] = args.analysis_start_date.isoformat()
    if args.analysis_end_date is not None:
        patch["analysis_end_date"] = args.analysis_end_date.isoformat()
    if args.offense_category is not None:
        patch["offense_category"] = args.offense_category or None
    if args.layer is not None:
        patch["layer"] = args.layer
    if not patch:
        raise AssistantClarification(
            "Tell me which filter to change — radius, dates, categories, or layer."
        )
    return {"patch": patch}
```

Dispatch: add to `execute_tool`'s tool-name dispatch (alongside the others, validated through `UpdateFiltersArgs(**arguments)` inside the same try that wraps `ValidationError` into `AssistantToolError`):

```python
if tool_name == "update_filters":
    result = _update_filters(UpdateFiltersArgs(**arguments))
```

In `app/assistant/semantic_layer.py`, append to `AVAILABLE_TOOLS`:

```python
{
    "name": "update_filters",
    "description": (
        "Change the dashboard's analysis filters WITHOUT running an analysis. "
        "Pass any of: radius_m, analysis_start_date, analysis_end_date, "
        "offense_category (one of PROPERTY/PERSON/SOCIETY, or '' for all "
        "reported), layer (reported/arrests/calls)."
    ),
},
```

In the module defining `build_tool_summary` (imported by `agent.py` — locate it, likely `app/assistant/summaries.py` or within `agent.py`), add an `update_filters` case producing a deterministic sentence, matching the module's style. Content:

```python
if tool_name == "update_filters":
    patch = result.get("patch", {})
    parts = []
    if "radius_m" in patch:
        parts.append(f"radius {patch['radius_m']} m")
    if "analysis_start_date" in patch or "analysis_end_date" in patch:
        parts.append(
            f"dates {patch.get('analysis_start_date', '…')} – {patch.get('analysis_end_date', '…')}"
        )
    if "offense_category" in patch:
        parts.append(f"categories {patch['offense_category'] or 'all reported'}")
    if "layer" in patch:
        parts.append(f"layer {patch['layer']}")
    return "Updated the filters: " + " · ".join(parts) + "."
```

- [ ] **Step 4: Run to verify pass** — `.venv/bin/python -m pytest tests/test_assistant_tools.py tests/test_assistant_agent.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add app/assistant/tools.py app/assistant/semantic_layer.py tests/test_assistant_tools.py
git add -u  # picks up the build_tool_summary module wherever it lives
git commit -m "feat(assistant): update_filters tool returning a validated settings patch"
```

---

### Task 3: `POST /assistant/commands`

**Files:** Modify `app/assistant/schemas.py`, `app/api/routes_assistant.py`, `app/config.py`, `tests/test_internal_surface.py`; create `tests/test_assistant_commands_api.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_assistant_commands_api.py`, following `tests/test_assistant_api.py`'s client/session fixtures and SSE-parsing helpers (reuse its event-parsing helper if it has one; otherwise split the response text on `\n\n` and parse `event:`/`data:` lines the same way that file does):

```python
def test_commands_requires_public_session(client):
    response = client.post("/assistant/commands", json={"command": "suggest_followups"})
    assert response.status_code == 401


def test_commands_rejects_unknown_and_unadvertised_commands(session_client):
    # Unknown entirely.
    response = session_client.post("/assistant/commands", json={"command": "drop_tables"})
    assert response.status_code == 422
    # Real tool handlers that are NOT in the command enum must be unreachable.
    for forbidden in ("run_place_analysis", "get_neighborhood_analysis", "get_incident_details", "get_dashboard_summary"):
        response = session_client.post("/assistant/commands", json={"command": forbidden})
        assert response.status_code == 422, forbidden


def test_commands_streams_tool_summary_done_without_llm(session_client, monkeypatch):
    # Constructing an LLM client on this path is a bug — make it explode if tried.
    from app.api import routes_assistant

    def _boom(*args, **kwargs):
        raise AssertionError("commands must never build an LLM client")

    monkeypatch.setattr(routes_assistant, "build_assistant_llm_client", _boom)
    response = session_client.post("/assistant/commands", json={"command": "suggest_followups"})
    assert response.status_code == 200
    events = parse_sse(response.text)  # same helper style as test_assistant_api
    names = [e["event"] for e in events]
    assert names[0] == "meta" and events[0]["data"]["mode"] == "command"
    assert "tool" in names and names[-1] == "done"
    tool = next(e for e in events if e["event"] == "tool")
    assert tool["data"]["tool_name"] == "suggest_followups"
    assert isinstance(tool["data"]["result"]["suggestions"], list)


def test_commands_update_filters_roundtrip(session_client):
    response = session_client.post(
        "/assistant/commands",
        json={"command": "update_filters", "arguments": {"radius_m": 500}},
    )
    events = parse_sse(response.text)
    tool = next(e for e in events if e["event"] == "tool")
    assert tool["data"]["result"]["patch"] == {"radius_m": 500}


def test_commands_tool_error_carries_code(session_client):
    response = session_client.post(
        "/assistant/commands",
        json={"command": "update_filters", "arguments": {"radius_m": 5}},
    )
    events = parse_sse(response.text)
    error = next(e for e in events if e["event"] == "error")
    assert error["data"]["code"] == "tool_error"
    assert error["data"]["message"]


def test_commands_clarification_streams_as_token(session_client):
    response = session_client.post("/assistant/commands", json={"command": "update_filters"})
    events = parse_sse(response.text)
    assert any(e["event"] == "token" and "which filter" in e["data"]["delta"] for e in events)
    assert events[-1]["event"] == "done"


def test_commands_rate_limited_per_session(session_client, monkeypatch):
    # Follow test_assistant_api's rate-limit test pattern: enable limiting with a
    # tiny capacity via settings monkeypatch + reset_rate_limiter(), then exhaust it.
    ...
```

For the rate-limit test, mirror the existing chat rate-limit test in `tests/test_assistant_api.py` exactly (settings override mechanism + `reset_rate_limiter()`), swapping the path and the capacity setting name (`rate_limit_assistant_commands_per_hour = 1`) and asserting the second request returns 429 with a `Retry-After` header. If no chat rate-limit test exists to copy, write it with `monkeypatch.setattr` on `routes_assistant.get_settings`-returned object per that file's settings idiom.

Also in `tests/test_internal_surface.py`: add `"/assistant/commands"` to `PUBLIC_PATHS`.

- [ ] **Step 2: Run to verify fail** — `.venv/bin/python -m pytest tests/test_assistant_commands_api.py tests/test_internal_surface.py -q` → FAIL (404s / missing path).

- [ ] **Step 3: Implement**

`app/assistant/schemas.py`:

```python
class AssistantCommandRequest(BaseModel):
    # The fixed command enum IS the security boundary: pydantic 422s anything else,
    # so unadvertised tool handlers stay unreachable from the client.
    command: Literal[
        "analyze_places",
        "compare_places",
        "add_place",
        "select_places",
        "update_filters",
        "suggest_followups",
    ]
    arguments: dict[str, Any] = Field(default_factory=dict)
```

`app/config.py`, next to the other `rate_limit_*` fields:

```python
rate_limit_assistant_commands_per_hour: int = 120
```

`app/api/routes_assistant.py` — new route below `assistant_chat`, reusing its imports (`execute_tool`, `AssistantClarification`, `AssistantToolError` may need importing from `app.assistant.tools`; `build_tool_summary` from wherever `agent.py` gets it):

```python
_COMMAND_FAILED_MESSAGE = "That didn't go through. Try again in a moment."


@router.post("/assistant/commands")
async def assistant_command(
    request: AssistantCommandRequest,
    user_id_hash: Annotated[str, Depends(required_public_user_hash)],
    session: Annotated[Session, Depends(get_session)],
) -> StreamingResponse:
    settings = get_settings()
    if settings.rate_limit_enabled:
        limiter = get_rate_limiter()
        wait = limiter.try_take(
            "assistant_commands",
            user_id_hash,
            capacity=settings.rate_limit_assistant_commands_per_hour,
            per_seconds=3600.0,
        )
        if wait > 0:
            raise HTTPException(
                status_code=429,
                detail="Command rate limit reached. Try again shortly.",
                headers={"Retry-After": str(int(wait) + 1)},
            )
    # No global daily counter here: commands never touch the LLM, and the burst
    # middleware already caps per-IP volume.

    async def event_stream() -> AsyncIterator[str]:
        yield _sse_event(
            AssistantStreamEvent(event="meta", data={"mode": "command", "command": request.command})
        )
        try:
            tool_result = execute_tool(session, user_id_hash, request.command, dict(request.arguments))
        except AssistantClarification as exc:
            yield _sse_event(AssistantStreamEvent(event="token", data={"delta": str(exc)}))
            yield _sse_event(AssistantStreamEvent(event="done", data={}))
            return
        except (AssistantToolError, ValueError) as exc:
            yield _sse_event(
                AssistantStreamEvent(event="error", data={"message": str(exc), "code": "tool_error"})
            )
            return
        except Exception:
            logger.exception("assistant command failed")
            yield _sse_event(
                AssistantStreamEvent(
                    event="error", data={"message": _COMMAND_FAILED_MESSAGE, "code": "internal"}
                )
            )
            return
        yield _sse_event(AssistantStreamEvent(event="tool", data=tool_result))
        yield _sse_event(
            AssistantStreamEvent(event="token", data={"delta": build_tool_summary(tool_result)})
        )
        yield _sse_event(AssistantStreamEvent(event="done", data={}))

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

Match the chat route's exact 429 detail/header style if it differs from the above — mirror, don't invent. Keep HTTP detail strings free of safety language (invariant).

- [ ] **Step 4: Run to verify pass** — `.venv/bin/python -m pytest tests/test_assistant_commands_api.py tests/test_internal_surface.py tests/test_assistant_api.py -q` → PASS. Also `.venv/bin/python -m ruff check .` → clean.

- [ ] **Step 5: Commit**

```bash
git add app/assistant/schemas.py app/api/routes_assistant.py app/config.py tests/test_assistant_commands_api.py tests/test_internal_surface.py
git commit -m "feat(assistant): no-LLM /assistant/commands endpoint with fixed command enum"
```

---

### Task 4: Frontend client — `streamAssistantCommand` + error codes

**Files:** Modify `frontend/src/api/client.ts`, `frontend/src/types.ts`; test wherever the SSE parsing tests live (`frontend/src/api/client.test.ts`).

- [ ] **Step 1: Write the failing test**

In `client.test.ts`, following its existing fetch-mocking idiom for `streamAssistantChat` (find the test that feeds a fake `ReadableStream` body):

```ts
it("streams command events from /assistant/commands", async () => {
  const body = sseBody([
    'event: meta\ndata: {"mode":"command","command":"suggest_followups"}',
    'event: tool\ndata: {"tool_name":"suggest_followups","arguments":{},"result":{"suggestions":["a"]}}',
    'event: token\ndata: {"delta":"Here are follow-ups."}',
    "event: done\ndata: {}",
  ]); // reuse/extract the same fake-stream helper the chat tests use
  const fetchMock = vi.fn().mockResolvedValue(okStreamResponse(body));
  vi.stubGlobal("fetch", fetchMock);
  const events: string[] = [];
  await streamAssistantCommand(
    { command: "suggest_followups", arguments: {} },
    { onEvent: (e) => events.push(e.event) },
  );
  expect(fetchMock.mock.calls[0][0]).toContain("/assistant/commands");
  expect(events).toEqual(["meta", "tool", "token", "done"]);
});
```

Adapt helper names (`sseBody`/`okStreamResponse`) to whatever the file actually uses — if it has no such helpers, lift the body-construction inline pattern from the existing chat streaming test.

- [ ] **Step 2: Run to verify fail** — `cd frontend && npm test -- src/api/client.test.ts` → FAIL (no export).

- [ ] **Step 3: Implement**

In `frontend/src/api/client.ts`: extract the body of `streamAssistantChat` into a private helper parameterized by path and payload, and re-express both functions through it:

```ts
async function streamAssistantSse(
  path: string,
  payload: unknown,
  handlers: { onEvent: (event: AssistantStreamEvent) => void },
): Promise<void> {
  // ...the existing streamAssistantChat body verbatim, with the fetch URL/path and
  // JSON body swapped for the parameters; flushAssistantEvents loop unchanged...
}

export function streamAssistantChat(
  payload: { messages: AssistantMessage[]; dashboard_state: AssistantDashboardState },
  handlers: { onEvent: (event: AssistantStreamEvent) => void },
): Promise<void> {
  return streamAssistantSse("/assistant/chat", payload, handlers);
}

export type AssistantCommandName =
  | "analyze_places"
  | "compare_places"
  | "add_place"
  | "select_places"
  | "update_filters"
  | "suggest_followups";

export function streamAssistantCommand(
  payload: { command: AssistantCommandName; arguments?: Record<string, unknown> },
  handlers: { onEvent: (event: AssistantStreamEvent) => void },
): Promise<void> {
  return streamAssistantSse("/assistant/commands", payload, handlers);
}
```

In `frontend/src/types.ts`, the `AssistantStreamEvent` union's error member gains `code`: change its data shape to `{ message?: string; code?: string }` (match the existing member's exact formatting).

- [ ] **Step 4: Run to verify pass** — `npm test -- src/api/client.test.ts` and `npx tsc --noEmit` → PASS/clean (the chat streaming tests must pass unchanged — the refactor is behavior-preserving).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/types.ts frontend/src/api/client.test.ts
git commit -m "feat(assistant-client): streamAssistantCommand + error codes"
```

---

### Task 5: `useAssistantTurn` hook

**Files:** Create `frontend/src/lib/useAssistantTurn.ts`, `frontend/src/lib/useAssistantTurn.test.ts`.

- [ ] **Step 1: Write the failing tests**

```ts
// frontend/src/lib/useAssistantTurn.test.ts
// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({
  streamAssistantChat: vi.fn(),
  streamAssistantCommand: vi.fn(),
}));

import { streamAssistantChat, streamAssistantCommand } from "../api/client";
import { useAssistantTurn, OFFLINE_MESSAGE } from "./useAssistantTurn";
import type { ThreadItem } from "./threadItems";
import type { AssistantDashboardState } from "../types";

const dashboardState: AssistantDashboardState = {
  selected_place_ids: [], analysis_start_date: null, analysis_end_date: null,
  radii_m: [250], offense_category: null, offense_subcategory: null,
  nibrs_group: null, layer: "reported",
};

function setup(items: ThreadItem[] = []) {
  const append = vi.fn();
  const onToolResult = vi.fn();
  const hook = renderHook(() =>
    useAssistantTurn({ dashboardState, items, append, onToolResult }),
  );
  return { hook, append, onToolResult };
}

beforeEach(() => {
  vi.mocked(streamAssistantChat).mockReset();
  vi.mocked(streamAssistantCommand).mockReset();
});

describe("useAssistantTurn", () => {
  it("sendChat appends user turn, streams, commits the reply", async () => {
    vi.mocked(streamAssistantChat).mockImplementation(async (_p, { onEvent }) => {
      onEvent({ event: "token", data: { delta: "On it." } });
      onEvent({ event: "done", data: {} });
    });
    const { hook, append } = setup();
    await act(() => hook.result.current.sendChat("analyze Home"));
    expect(append).toHaveBeenCalledWith({ kind: "user_text", text: "analyze Home" });
    expect(append).toHaveBeenCalledWith({ kind: "tabby_text", text: "On it." });
    expect(hook.result.current.offline).toBe(false);
  });

  it("llm_unreachable error on chat sets offline and appends the notice", async () => {
    vi.mocked(streamAssistantChat).mockImplementation(async (_p, { onEvent }) => {
      onEvent({ event: "error", data: { message: "Couldn't reach the analyst.", code: "llm_unreachable" } });
    });
    const { hook, append } = setup();
    await act(() => hook.result.current.sendChat("hi"));
    expect(append).toHaveBeenCalledWith({ kind: "notice", text: "Couldn't reach the analyst." });
    expect(hook.result.current.offline).toBe(true);
  });

  it("a successful chat clears offline", async () => {
    vi.mocked(streamAssistantChat)
      .mockImplementationOnce(async (_p, { onEvent }) => {
        onEvent({ event: "error", data: { code: "llm_unreachable", message: "down" } });
      })
      .mockImplementationOnce(async (_p, { onEvent }) => {
        onEvent({ event: "token", data: { delta: "Back." } });
      });
    const { hook } = setup();
    await act(() => hook.result.current.sendChat("hi"));
    expect(hook.result.current.offline).toBe(true);
    await act(() => hook.result.current.sendChat(null));
    expect(hook.result.current.offline).toBe(false);
  });

  it("runCommand streams the command, forwards tool events, never flips offline", async () => {
    vi.mocked(streamAssistantCommand).mockImplementation(async (_p, { onEvent }) => {
      onEvent({ event: "tool", data: { tool_name: "update_filters", arguments: {}, result: { patch: { radius_m: 500 } } } });
      onEvent({ event: "error", data: { message: "boom", code: "tool_error" } });
    });
    const { hook, append, onToolResult } = setup();
    await act(() => hook.result.current.runCommand("Widen radius", "update_filters", { radius_m: 500 }));
    expect(append).toHaveBeenCalledWith({ kind: "user_text", text: "Widen radius" });
    expect(onToolResult).toHaveBeenCalledWith(expect.objectContaining({ tool_name: "update_filters" }));
    expect(append).toHaveBeenCalledWith({ kind: "notice", text: "boom" });
    expect(hook.result.current.offline).toBe(false);
    expect(vi.mocked(streamAssistantCommand).mock.calls[0][0]).toEqual({
      command: "update_filters",
      arguments: { radius_m: 500 },
    });
  });

  it("a thrown fetch on chat appends OFFLINE_MESSAGE and sets offline", async () => {
    vi.mocked(streamAssistantChat).mockRejectedValue(new Error("network"));
    const { hook, append } = setup();
    await act(() => hook.result.current.sendChat("hi"));
    expect(append).toHaveBeenCalledWith({ kind: "notice", text: OFFLINE_MESSAGE });
    expect(hook.result.current.offline).toBe(true);
  });

  it("ignores a second call while a turn is in flight", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    vi.mocked(streamAssistantChat).mockImplementation(async (_p, { onEvent }) => {
      onEvent({ event: "token", data: { delta: "…" } });
      await gate;
    });
    const { hook } = setup();
    let first!: Promise<void>;
    act(() => { first = hook.result.current.sendChat("one"); });
    await waitFor(() => expect(hook.result.current.busy).toBe(true));
    await act(() => hook.result.current.sendChat("two"));
    expect(vi.mocked(streamAssistantChat)).toHaveBeenCalledTimes(1);
    release();
    await act(() => first);
    expect(hook.result.current.busy).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify fail** — `npm test -- src/lib/useAssistantTurn.test.ts` → FAIL (module missing).

- [ ] **Step 3: Implement**

```ts
// frontend/src/lib/useAssistantTurn.ts
import { useCallback, useRef, useState } from "react";

import {
  streamAssistantChat,
  streamAssistantCommand,
  type AssistantCommandName,
} from "../api/client";
import { toApiMessages, type ThreadItem } from "./threadItems";
import type { AssistantDashboardState, AssistantStreamEvent } from "../types";

export const OFFLINE_MESSAGE =
  "Tabby can't reach the case files right now. Your data is unaffected — the rest of CompCat works.";

type Deps = {
  dashboardState: AssistantDashboardState;
  items: ThreadItem[];
  append: (item: ThreadItem) => void;
  onToolResult?: (data: { tool_name?: string; result?: unknown }) => void;
};

/** One reducer for both assistant streams (free-text chat and structured commands).
 * Lives in MapWorkspace so busy/draft/offline survive the panel unmounting when
 * railView flips mid-turn. Only chat outcomes drive `offline` — commands are the
 * degraded-mode path and must keep working while the LLM is down. */
export function useAssistantTurn({ dashboardState, items, append, onToolResult }: Deps) {
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [statusLine, setStatusLine] = useState("");
  const [toolActivity, setToolActivity] = useState<{ label: string }[]>([]);
  const [offline, setOffline] = useState(false);
  // Synchronous re-entrancy gate: state updates lag within a tick.
  const inFlight = useRef(false);

  const runTurn = useCallback(
    async (kind: "chat" | "command", start: (onEvent: (event: AssistantStreamEvent) => void) => Promise<void>) => {
      if (inFlight.current) return;
      inFlight.current = true;
      let text = "";
      let errored = false;
      let errMessage = "";
      let errCode = "";
      setDraft("");
      setStatusLine("");
      setToolActivity([]);
      setBusy(true);
      try {
        await start((event) => {
          if (event.event === "tool") {
            const toolName = String(event.data.tool_name ?? "tool");
            setToolActivity((current) => [{ label: toolName }, ...current].slice(0, 4));
            onToolResult?.(event.data);
          }
          if (event.event === "status") {
            setStatusLine(String(event.data.label ?? ""));
          }
          if (event.event === "token") {
            text += event.data.delta ?? "";
            setStatusLine("");
            setDraft(text);
          }
          if (event.event === "replace") {
            text = String(event.data.text ?? "");
            setStatusLine("");
            setDraft(text);
          }
          if (event.event === "error") {
            if (!errored) {
              errMessage = String(event.data.message ?? "").trim();
              errCode = String(event.data.code ?? "");
            }
            errored = true;
          }
        });
        if (!errored && text.trim()) {
          append({ kind: "tabby_text", text: text.trim() });
        }
        if (errored) {
          append({ kind: "notice", text: errMessage || OFFLINE_MESSAGE });
          if (kind === "chat" && errCode === "llm_unreachable") setOffline(true);
        } else if (kind === "chat") {
          setOffline(false);
        }
      } catch {
        append({ kind: "notice", text: OFFLINE_MESSAGE });
        if (kind === "chat") setOffline(true);
      } finally {
        setDraft("");
        setStatusLine("");
        setBusy(false);
        inFlight.current = false;
      }
    },
    [append, onToolResult],
  );

  // text === null re-sends the thread as-is (Retry after an error notice).
  const sendChat = useCallback(
    (text: string | null) => {
      const apiMessages = toApiMessages(items);
      if (text !== null) {
        apiMessages.push({ role: "user", content: text });
        append({ kind: "user_text", text });
      }
      return runTurn("chat", (onEvent) =>
        streamAssistantChat({ messages: apiMessages, dashboard_state: dashboardState }, { onEvent }),
      );
    },
    [items, append, dashboardState, runTurn],
  );

  const runCommand = useCallback(
    (label: string, command: AssistantCommandName, args: Record<string, unknown> = {}) => {
      append({ kind: "user_text", text: label });
      return runTurn("command", (onEvent) =>
        streamAssistantCommand({ command, arguments: args }, { onEvent }),
      );
    },
    [append, runTurn],
  );

  return { busy, draft, statusLine, toolActivity, offline, sendChat, runCommand };
}
```

- [ ] **Step 4: Run to verify pass** — `npm test -- src/lib/useAssistantTurn.test.ts` → PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/useAssistantTurn.ts frontend/src/lib/useAssistantTurn.test.ts
git commit -m "feat(rail): useAssistantTurn hook — shared chat/command reducer with offline tracking"
```

---

### Task 6: Presentational `AssistantPanel` + `MapWorkspace` wiring + bridge case

**Files:** Modify `frontend/src/components/AssistantPanel.tsx`, `frontend/src/components/AssistantPanel.test.tsx`, `frontend/src/components/MapWorkspace.tsx`, `frontend/src/components/MapWorkspace.test.tsx`, `frontend/src/lib/assistantBridge.ts`, `frontend/src/lib/assistantBridge.test.ts`.

This is the atomic integration step. Sub-steps:

- [ ] **Step 1: Bridge case (TDD)** — in `assistantBridge.test.ts` add:

```ts
it("maps update_filters patches to a settings effect with no view switch", () => {
  const effect = interpretToolResult({
    tool_name: "update_filters",
    result: { patch: { radius_m: 500, offense_category: null, layer: "arrests" } },
  });
  expect(effect).toEqual({ settings: { radiusM: 500, offenseCategory: "", layer: "arrests" } });
});
```

Run (FAIL), then in `assistantBridge.ts` add before `default`:

```ts
case "update_filters":
  return { settings: settingsFrom(result.patch as SettingsUsed) };
```

Run (PASS). Note: the patch's `analysis_start_date`/`analysis_end_date` keys already match `SettingsUsed` — nothing else needed.

- [ ] **Step 2: Rewrite `AssistantPanel` as presentational**

New Props (replaces `dashboardState`/`onAppend`/`onToolResult`/`busy`/`onBusyChange`):

```ts
import type { AssistantCommandName } from "../api/client";

type SuggestedAction = { label: string; command?: AssistantCommandName };

type Props = {
  items: ThreadItem[];
  busy: boolean;
  draft: string;
  statusLine: string;
  toolActivity: { label: string }[];
  offline: boolean;
  onSend: (text: string) => void;
  onRetry: () => void;
  onRunCommand: (label: string, command: AssistantCommandName) => void;
  contextStrip?: ReactNode;
};

const SUGGESTED_ACTIONS: SuggestedAction[] = [
  { label: "What's near this pin?", command: "analyze_places" },
  { label: "Compare my places", command: "compare_places" },
  { label: "What's on file around here?" }, // free-text — needs the LLM
];

const OFFLINE_COMPOSER_HINT = "Tabby can't reach the case files — chips and filters still work.";
```

Changes from the current file:
- Delete `sendTurn`, the `streamAssistantChat` import, `toApiMessages` import, all stream-event handling, and the local `draft`/`statusLine`/`toolActivity` state — they now arrive as props. Keep `greeted` localStorage logic, but set it inside the submit/chip handlers (any first interaction).
- `handleSubmit` becomes: trim, guard `!content || busy || offline`, `setInput("")`, `onSend(content)`.
- Empty-state chips render from `SUGGESTED_ACTIONS`: command chips call `onRunCommand(action.label, action.command)` and are `disabled={busy}`; the prompt chip calls `onSend(action.label)` and is `disabled={busy || offline}`.
- Notice items' Retry button calls `onRetry` (same trailing-receipts visibility rule, unchanged).
- The composer: `<textarea disabled={offline}>`; when `offline`, render `<p className="mc-rail-offline">{OFFLINE_COMPOSER_HINT}</p>` directly above the form and disable the Send button regardless of input.
- `displayItems` draft-fold stays, driven by the `draft` prop.

Rewrite `AssistantPanel.test.tsx` as a props-driven suite (no client mock, no Harness state machine — callbacks are `vi.fn()`):

```ts
const baseProps = {
  items: [] as ThreadItem[], busy: false, draft: "", statusLine: "",
  toolActivity: [], offline: false,
  onSend: vi.fn(), onRetry: vi.fn(), onRunCommand: vi.fn(),
};
```

Tests (rendered with `<AssistantPanel {...baseProps} {...overrides} />`):
1. renders items by kind incl. receipt/notice classes and the contextStrip slot (port from the current suite);
2. submit calls `onSend` with trimmed text and clears the input;
3. command chip calls `onRunCommand("Compare my places", "compare_places")`; prompt chip calls `onSend`;
4. `offline` disables the textarea, Send, and the prompt chip, shows the hint text, but leaves command chips enabled;
5. `draft` prop renders as the in-flight bubble alongside items (one node);
6. Retry appears on a notice followed only by receipts and calls `onRetry`.

- [ ] **Step 3: Wire `MapWorkspace`**

- Remove `const [assistantBusy, setAssistantBusy] = useState(false)`.
- Instantiate the hook after `assistantState` is defined:

```ts
const turn = useAssistantTurn({
  dashboardState: assistantState,
  items: thread.items,
  append: thread.append,
  onToolResult: applyAssistantToolResult,
});
```

(If `applyAssistantToolResult` is declared after `assistantState`, order them so this compiles; wrap `applyAssistantToolResult` in `useCallback` only if the hook's deps demand referential stability — they don't; plain function is fine.)
- Command-arg enrichment + panel props:

```ts
function runPanelCommand(label: string, command: AssistantCommandName) {
  const args: Record<string, unknown> =
    command === "analyze_places" || command === "compare_places"
      ? { place_ids: Array.from(savedIdSet) }
      : {};
  void turn.runCommand(label, command, args);
}
```

```tsx
<AssistantPanel
  items={thread.items}
  busy={turn.busy}
  draft={turn.draft}
  statusLine={turn.statusLine}
  toolActivity={turn.toolActivity}
  offline={turn.offline}
  onSend={(text) => void turn.sendChat(text)}
  onRetry={() => void turn.sendChat(null)}
  onRunCommand={runPanelCommand}
  contextStrip={
    <ContextStrip analysis={analysis} availableRadii={data.availableRadii} onChange={handleAnalysisChange} />
  }
/>
```

- [ ] **Step 4: Migrate `MapWorkspace.test.tsx`**

- Add `streamAssistantCommand: vi.fn()` to the `vi.mock("../api/client", ...)` factory.
- Existing chat-flow tests should pass unchanged (same streamAssistantChat contract). Fix any that break for prop-shape reasons only — do not weaken analysis/bridge/share-link/landing/pin-draft assertions.
- New test — chip runs a command and the bridge applies it without leaving the rail:

```ts
it("runs the compare chip as a structured command", async () => {
  vi.mocked(streamAssistantCommand).mockImplementation(async (_p, { onEvent }) => {
    onEvent({ event: "tool", data: { tool_name: "update_filters", arguments: {}, result: { patch: { radius_m: 500 } } } });
    onEvent({ event: "token", data: { delta: "Updated the filters: radius 500 m." } });
    onEvent({ event: "done", data: {} });
  });
  // render, reach the Tabby rail (backToTabby helper), click "Compare my places"
  // assert: streamAssistantCommand called with command "compare_places" and
  // arguments.place_ids an array; the receipt "Search radius → 500 m" appears;
  // the rail is still showing (composer present — update_filters has no tab effect).
});
```

(The mocked stream deliberately returns an `update_filters` tool event regardless of the sent command — the test pins both the outgoing command payload and the effect→receipt round-trip in one pass.)
- New test — degraded gating end to end: mock `streamAssistantChat` to emit `error` with `code: "llm_unreachable"`; send a message from the rail; assert the composer becomes disabled with the hint text visible, and the command chips are still enabled.

- [ ] **Step 5: Verify**

`cd frontend && npm test` (all green) and `npx tsc --noEmit` (clean).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/AssistantPanel.tsx frontend/src/components/AssistantPanel.test.tsx frontend/src/components/MapWorkspace.tsx frontend/src/components/MapWorkspace.test.tsx frontend/src/lib/assistantBridge.ts frontend/src/lib/assistantBridge.test.ts
git commit -m "feat(rail): chips as commands, presentational panel, degraded-mode gating"
```

---

### Task 7: CSS touch-up + full gate + E2E

- [ ] **Step 1: Offline hint style** — append to the rail block in `frontend/src/styles/mapWorkspace.css`:

```css
.mc-rail-offline{margin:0;padding:5px 9px;border:1px dashed var(--danger);border-radius:9px;color:var(--danger);font-size:11.5px;}
.mc-dock-form textarea:disabled{opacity:.55;cursor:not-allowed;}
```

Commit: `git add frontend/src/styles/mapWorkspace.css && git commit -m "style(rail): offline composer hint"`.

- [ ] **Step 2: Full gate** — repo root `make test-all` equivalent in the worktree: `.venv/bin/python -m pytest tests -q` + `.venv/bin/python -m ruff check .` + `cd frontend && npm test && npm run build`. All green.

- [ ] **Step 3: E2E via the `/verify` skill recipe** — build UI, `make seed-crime`, uvicorn on a fresh port via a uniquely-named launch config. Drive: (a) share-link seed → Back to Tabby → click "Compare my places" → assert a command turn renders (user bubble with the chip label, tool activity, deterministic summary bubble; network tab shows `/assistant/commands`, NOT `/assistant/chat`); (b) send free text with no LLM configured → notice arrives; if its code is `llm_unreachable` the composer disables with the hint while chips stay active — then click a command chip and confirm it still works; (c) invariant sweep of visible text (only "risk" hit is the fixed caveat).

---

## Out of scope (later slices)

- Inline analysis cards, run-scoped export, post-analysis follow-up chips (Slice 3)
- Presence badges + descriptors (Slice 4); proactivity (Slice 5); sheet mechanics (Slice 6); tab deletion + parity checklist (Slice 7)
- `turn_id`/abort serialization from the spec's architecture section — deferred to Slice 3 alongside cards (where stale-turn effects first become user-visible); the hook's `inFlight` gate covers slice-2's single-turn model.
