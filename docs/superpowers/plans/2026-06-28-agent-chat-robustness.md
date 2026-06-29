# Agent Chat Robustness (Decision Tree) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the redundant, fragile post-tool narration LLM call with a deterministic per-node summary, so a workflow turn makes **one** LLM call, answers instantly, never shows a false "offline," and clarifies (rather than guesses) when underspecified.

**Architecture:** The chat is a decision tree. One planning LLM call classifies the message into a node (workflow tool) or a free-form answer. For a workflow node, the tool runs and a Python-built summary of its result is the chat answer — no second LLM call. Underspecified requests raise `AssistantClarification` (rendered as a question), distinct from real errors. The frontend shows the real error message and reserves the blanket "offline" copy for a true transport failure.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy (backend), React + TypeScript + Vitest (frontend). Tests: `pytest`, `vitest`.

All paths are relative to the worktree root: `/Users/jscocca/Repos/Crime Commute Safety Tool/.worktrees/agent-chat-robustness`. Run backend tests with `PYTHONPATH=. .venv/bin/pytest …`; frontend tests from `frontend/` with `npm test …`.

---

## File Structure

- `app/assistant/tools.py` — add `AssistantClarification`; reroute the three underspecified guards to it. (modify)
- `app/assistant/summaries.py` — **new**: `build_tool_summary(tool_result) -> str`, one neutral sentence per node from existing result fields.
- `app/assistant/agent.py` — rewrite `run_assistant_turn` to the single classify-then-act flow. (modify)
- `app/assistant/prompts.py` — delete the now-unused `build_followup_messages`. (modify)
- `app/components/AssistantPanel.tsx` (frontend) — render the real error message; offline copy only on transport failure. (modify)
- Tests: `tests/test_assistant_tools.py`, `tests/test_assistant_summaries.py` (new), `tests/test_assistant_agent.py`, `frontend/src/components/AssistantPanel.test.tsx`.

---

## Task 1: `AssistantClarification` + reroute underspecified guards

**Files:**
- Modify: `app/assistant/tools.py` (add exception near `AssistantToolError` at line 45; reroute guards at lines 105, 152, 208-209)
- Test: `tests/test_assistant_tools.py`

- [ ] **Step 1: Update the existing compare-guard test to expect the new exception**

In `tests/test_assistant_tools.py`, find `test_compare_places_requires_two_places`. Change its import/assertion from `AssistantToolError` to `AssistantClarification`:

```python
def test_compare_places_requires_two_places(tmp_path, monkeypatch):
    from app.assistant.tools import AssistantClarification

    session, user_hash = _session_with_place_and_crime(tmp_path)
    monkeypatch.setattr("app.assistant.tools.build_provider", lambda settings: _FakeProvider([]))
    try:
        with pytest.raises(AssistantClarification):
            execute_tool(
                session,
                user_hash,
                "compare_places",
                {
                    "queries": ["Library stop"],
                    "analysis_start_date": "2024-01-01",
                    "analysis_end_date": "2024-01-31",
                    "radius_m": 250,
                },
            )
    finally:
        session.close()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_assistant_tools.py::test_compare_places_requires_two_places -v`
Expected: FAIL — `AssistantClarification` does not exist / the guard still raises `AssistantToolError`.

- [ ] **Step 3: Add the exception and reroute the guards**

In `app/assistant/tools.py`, add the class right after `class AssistantToolError(ValueError):` (line 45):

```python
class AssistantClarification(Exception):
    """The request is underspecified/ambiguous — ask the user, do not error.

    Deliberately NOT a ValueError, so execute_tool's `except ValueError`
    re-wrap does not swallow it; the agent renders it as a clarifying question.
    """
```

Change the three underspecified guards from `AssistantToolError` to `AssistantClarification`:
- Line ~105 (`_add_place`): `raise AssistantClarification(f"Could not find a place for '{query}'.")`
- Line ~152 (`_analyze_places`): `raise AssistantClarification("Name a place to analyze, or select one on the dashboard.")`
- Lines ~208-209 (`_compare_places`): `raise AssistantClarification(\n            "Name at least two places to compare, or select them on the dashboard."\n        )`

Leave the internal guard `raise AssistantToolError(f"Place '{place_id}' was not found after resolution.")` (line ~109) and `Unknown assistant tool` (line ~329) as `AssistantToolError`. Do **not** add `AssistantClarification` to either `except` clause in `execute_tool` — it must propagate.

- [ ] **Step 4: Run the test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_assistant_tools.py -v`
Expected: PASS (all of `test_assistant_tools.py`).

- [ ] **Step 5: Commit**

```bash
git add app/assistant/tools.py tests/test_assistant_tools.py
git commit -m "feat(assistant): AssistantClarification for underspecified workflow requests"
```

---

## Task 2: `build_tool_summary` deterministic summaries

**Files:**
- Create: `app/assistant/summaries.py`
- Test: `tests/test_assistant_summaries.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_assistant_summaries.py`:

```python
from __future__ import annotations

from app.assistant.summaries import build_tool_summary


def _envelope(tool_name, result):
    return {"tool_name": tool_name, "arguments": {}, "result": result}


def test_compare_summary_uses_counts_and_overview():
    result = {
        "settings_used": {"radius_m": 250},
        "comparison": {
            "overview": {
                "summary_text": "Pike Place had more reported incidents than Capitol Hill.",
                "options": [
                    {"label": "Pike Place", "incident_count": 299},
                    {"label": "Capitol Hill", "incident_count": 20},
                ],
            }
        },
        "created": [],
        "unresolved": [],
    }
    text = build_tool_summary(_envelope("compare_places", result))
    assert "Pike Place: 299" in text
    assert "Capitol Hill: 20" in text
    assert "250 m" in text
    assert "more reported incidents" in text


def test_analyze_summary_reads_beat_verdict():
    result = {
        "settings_used": {"radius_m": 250},
        "neighborhood": {
            "places": [
                {
                    "place_label": "Capitol Hill",
                    "baseline_available": True,
                    "rate_ratio": 1.4,
                    "ci_lower": 1.1,
                    "ci_upper": 1.8,
                    "decision": "above_clear",
                    "place_incident_count": 84,
                }
            ]
        },
        "created": [],
        "unresolved": [],
    }
    text = build_tool_summary(_envelope("analyze_places", result))
    assert "Capitol Hill" in text
    assert "1.4×" in text
    assert "above its beat baseline, statistically clear" in text
    assert "95% CI 1.1–1.8" in text
    assert "84 reported incidents within 250 m" in text


def test_add_place_summary_reports_created_with_address():
    result = {
        "place": {"display_label": "Capitol Hill"},
        "place_id": "p1",
        "created": True,
        "address": "Capitol Hill, Seattle",
    }
    assert build_tool_summary(_envelope("add_place", result)) == "Saved Capitol Hill at Capitol Hill, Seattle."


def test_add_place_summary_reports_existing_match():
    result = {"place": {"display_label": "Home"}, "place_id": "p1", "created": False, "address": None}
    assert build_tool_summary(_envelope("add_place", result)) == "Found Home in your saved places."


def test_summary_appends_provenance_for_created_and_unresolved():
    result = {
        "settings_used": {"radius_m": 250},
        "comparison": {"overview": {"summary_text": "", "options": []}},
        "created": [{"query": "Capitol Hill", "label": "Capitol Hill", "address": "10th & Pine, Seattle"}],
        "unresolved": ["Florble Cafe"],
    }
    text = build_tool_summary(_envelope("compare_places", result))
    assert "Saved Capitol Hill at 10th & Pine, Seattle." in text
    assert "Couldn’t find “Florble Cafe”." in text


def test_unknown_tool_returns_nonempty():
    assert build_tool_summary(_envelope("run_place_analysis", {"summary_count": 1})) == "Done."
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_assistant_summaries.py -v`
Expected: FAIL — `app.assistant.summaries` does not exist.

- [ ] **Step 3: Create the implementation**

Create `app/assistant/summaries.py`:

```python
from __future__ import annotations

from typing import Any

_DECISION_PHRASES = {
    "above_clear": "above its beat baseline, statistically clear",
    "below_clear": "below its beat baseline, statistically clear",
    "not_clear": "not statistically clear vs its beat",
    "insufficient_data": "insufficient data for a beat comparison",
    "model_warning": "too few months to model reliably",
    "baseline_unavailable": "no beat baseline available",
}


def build_tool_summary(tool_result: dict[str, Any]) -> str:
    """A neutral, invariant-safe one-liner for a tool result, built from fields
    the result already carries (no safety scoring/ranking, no LLM)."""
    result = tool_result.get("result") or {}
    handler = {
        "add_place": _add_place_summary,
        "select_places": _select_places_summary,
        "analyze_places": _analyze_places_summary,
        "compare_places": _compare_places_summary,
        "get_dashboard_summary": _dashboard_summary,
        "suggest_followups": _suggest_followups_summary,
    }.get(tool_result.get("tool_name"))
    if handler is None:
        return "Done."
    return handler(result) or "Done."


def _add_place_summary(result: dict[str, Any]) -> str:
    label = (result.get("place") or {}).get("display_label") or "the place"
    if result.get("created"):
        address = result.get("address")
        return f"Saved {label} at {address}." if address else f"Saved {label}."
    return f"Found {label} in your saved places."


def _select_places_summary(result: dict[str, Any]) -> str:
    if result.get("mode") == "clear":
        return "Cleared the selection."
    labels = _resolved_labels(result)
    parts: list[str] = []
    if labels:
        verb = "Added" if result.get("mode") == "add" else "Selected"
        parts.append(f"{verb} {_join(labels)}.")
    elif not result.get("unresolved"):
        parts.append("No matching places.")
    parts.extend(_unresolved_sentences(result))
    return " ".join(parts)


def _analyze_places_summary(result: dict[str, Any]) -> str:
    radius = (result.get("settings_used") or {}).get("radius_m")
    places = (result.get("neighborhood") or {}).get("places") or []
    sentences: list[str] = []
    for place in places:
        label = place.get("place_label") or "The place"
        count = place.get("place_incident_count")
        if place.get("baseline_available") and place.get("rate_ratio") is not None:
            phrase = _DECISION_PHRASES.get(place.get("decision"), "compared to its beat")
            ci = ""
            lower, upper = place.get("ci_lower"), place.get("ci_upper")
            if lower is not None and upper is not None:
                ci = f" (95% CI {lower:.1f}–{upper:.1f})"
            sentences.append(
                f"{label}: {place['rate_ratio']:.1f}× its beat — {phrase}{ci}; "
                f"{count} reported incidents within {radius} m."
            )
        else:
            phrase = _DECISION_PHRASES.get(place.get("decision"), "no beat comparison")
            sentences.append(f"{label}: {count} reported incidents within {radius} m ({phrase}).")
    summary = " ".join(sentences) if sentences else "No places to analyze."
    return _with_provenance(summary, result)


def _compare_places_summary(result: dict[str, Any]) -> str:
    radius = (result.get("settings_used") or {}).get("radius_m")
    overview = (result.get("comparison") or {}).get("overview") or {}
    options = overview.get("options") or []
    parts: list[str] = []
    counts = "; ".join(
        f"{o.get('label')}: {o.get('incident_count')}" for o in options if o.get("label")
    )
    if counts:
        parts.append(f"Reported incidents within {radius} m — {counts}.")
    if overview.get("summary_text"):
        parts.append(overview["summary_text"])
    summary = " ".join(parts) if parts else "Compared the selected places."
    return _with_provenance(summary, result)


def _dashboard_summary(result: dict[str, Any]) -> str:
    count = (result.get("totals") or {}).get("place_count")
    return f"You have {count} saved place{'' if count == 1 else 's'}."


def _suggest_followups_summary(result: dict[str, Any]) -> str:
    suggestions = result.get("suggestions") or []
    if not suggestions:
        return "Here are some things you can try next."
    return "You could: " + " ".join(f"• {item}" for item in suggestions)


def _resolved_labels(result: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for entry in (result.get("matched") or []) + (result.get("created") or []):
        if entry.get("label"):
            labels.append(entry["label"])
    return labels


def _created_sentences(result: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for entry in result.get("created") or []:
        label = entry.get("label") or entry.get("query") or "a place"
        address = entry.get("address")
        out.append(f"Saved {label} at {address}." if address else f"Saved {label}.")
    return out


def _unresolved_sentences(result: dict[str, Any]) -> list[str]:
    return [f"Couldn’t find “{query}”." for query in (result.get("unresolved") or [])]


def _with_provenance(summary: str, result: dict[str, Any]) -> str:
    return " ".join([summary, *_created_sentences(result), *_unresolved_sentences(result)]).strip()


def _join(items: list[str]) -> str:
    items = [item for item in items if item]
    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_assistant_summaries.py -v`
Expected: PASS (6 tests). Then `PYTHONPATH=. .venv/bin/ruff check app/assistant/summaries.py tests/test_assistant_summaries.py` — clean.

- [ ] **Step 5: Commit**

```bash
git add app/assistant/summaries.py tests/test_assistant_summaries.py
git commit -m "feat(assistant): deterministic per-node tool summaries"
```

---

## Task 3: Rewrite the agent loop + drop the follow-up prompt

**Files:**
- Modify: `app/assistant/agent.py` (rewrite `run_assistant_turn`, lines ~69-107; update imports)
- Modify: `app/assistant/prompts.py` (delete `build_followup_messages`, lines ~53-86)
- Test: `tests/test_assistant_agent.py`

- [ ] **Step 1: Update the agent tests for the new behavior**

In `tests/test_assistant_agent.py`:

(a) **Delete** `test_agent_chains_two_tool_calls_then_narrates` and `test_agent_stops_executing_tools_at_the_configured_budget` (multi-tool chaining and the tool-call budget are removed).

(b) **Replace** `test_agent_executes_run_place_analysis_tool_call` with this (one LLM call; the answer is the deterministic summary):

```python
def test_agent_runs_workflow_tool_with_deterministic_summary(tmp_path):
    session, user_hash = _session_with_place_and_crime(tmp_path)
    # Planning returns a compare_places tool_call; there is NO second model call.
    client = FakeClient(
        [
            '{"type":"tool_call","tool_name":"compare_places","arguments":{}}',
        ]
    )
    try:
        events = asyncio.run(
            _collect(
                session,
                user_hash,
                [AssistantChatMessage(role="user", content="Compare my selected places.")],
                AssistantDashboardState(
                    selected_place_ids=["place-1", "place-2"],
                    analysis_start_date=date(2024, 1, 1),
                    analysis_end_date=date(2024, 1, 31),
                    radii_m=[250],
                ),
                client,
            )
        )
    finally:
        session.close()

    assert [event.event for event in events] == ["meta", "tool", "token", "done"]
    assert events[1].data["tool_name"] == "compare_places"
    assert events[2].data["delta"]  # a non-empty deterministic summary
    assert len(client.calls) == 1  # planning only — no narration call
```

This needs a second place. Add it to `_session_with_place_and_crime` (after the first `session.add(PlaceCluster(... id="place-1" ...))`, before `session.commit()`):

```python
    session.add(
        PlaceCluster(
            id="place-2",
            user_id_hash=user_hash,
            cluster_version="manual-v1",
            cluster_method="manual",
            centroid_latitude=47.62,
            centroid_longitude=-122.34,
            display_latitude=47.62,
            display_longitude=-122.34,
            visit_count=1,
            sensitivity_class="normal",
            display_label="Second stop",
            inferred_place_type="manual_place",
            label_source="test",
        )
    )
```

(c) **Add** a clarify test and an unreachable-classifier test at the end of the file:

```python
def test_agent_clarifies_underspecified_request(tmp_path):
    session, user_hash = _session_with_place_and_crime(tmp_path)
    # compare with only one resolvable place -> AssistantClarification -> clarify token, NOT error.
    client = FakeClient(
        [
            '{"type":"tool_call","tool_name":"compare_places","arguments":{"queries":["Library stop"]}}',
        ]
    )
    try:
        events = asyncio.run(
            _collect(
                session,
                user_hash,
                [AssistantChatMessage(role="user", content="Compare it.")],
                AssistantDashboardState(
                    analysis_start_date=date(2024, 1, 1),
                    analysis_end_date=date(2024, 1, 31),
                    radii_m=[250],
                ),
                client,
            )
        )
    finally:
        session.close()

    assert [event.event for event in events] == ["meta", "token", "done"]
    assert "at least two places" in events[1].data["delta"]


def test_agent_reports_unreachable_classifier(tmp_path):
    from app.assistant.llm_client import LlmUnavailable

    class RaisingClient:
        calls: list = []

        async def complete(self, messages, *, role, temperature=None, max_tokens=None):
            raise LlmUnavailable("endpoint down")

    session, user_hash = _session_with_place_and_crime(tmp_path)
    try:
        events = asyncio.run(
            _collect(
                session,
                user_hash,
                [AssistantChatMessage(role="user", content="Compare A and B.")],
                AssistantDashboardState(selected_place_ids=["place-1"]),
                RaisingClient(),
            )
        )
    finally:
        session.close()

    assert events[-1].event == "error"
    assert "Couldn't reach the analyst" in events[-1].data["message"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_assistant_agent.py -v`
Expected: FAIL — the new tests fail against the old loop (the compare test still makes 2 calls / clarify still errors / unreachable shows the raw message).

- [ ] **Step 3: Rewrite the agent loop**

In `app/assistant/agent.py`, update the imports:
- Change `from app.assistant.tools import AssistantToolError, execute_tool` to `from app.assistant.tools import AssistantClarification, AssistantToolError, execute_tool`.
- Add `from app.assistant.summaries import build_tool_summary`.
- Change `from app.assistant.prompts import build_followup_messages, build_planning_messages` to `from app.assistant.prompts import build_planning_messages`.

Add the module constant near the top (after the imports):

```python
_UNREACHABLE_MESSAGE = (
    "Couldn't reach the analyst to interpret your request. The rest of Waypoint still works."
)
```

Replace the `try:` block (lines ~69-107, from `raw_plan = await llm_client.complete(` through the `except (...)` clause) with:

```python
    try:
        raw_plan = await llm_client.complete(
            build_planning_messages(messages, context),
            role=settings.assistant_role,
            temperature=0.2,
            max_tokens=1024,
        )
        plan = _parse_model_json(raw_plan)
    except LlmUnavailable:
        yield AssistantStreamEvent(event="error", data={"message": _UNREACHABLE_MESSAGE})
        return
    except ValueError as exc:
        yield AssistantStreamEvent(event="error", data={"message": str(exc)})
        return

    if plan.get("type") == "tool_call":
        tool_name = str(plan.get("tool_name"))
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
        yield AssistantStreamEvent(event="token", data={"delta": build_tool_summary(tool_result)})
        yield AssistantStreamEvent(event="done", data={})
        return

    try:
        message = _final_message(plan)
    except ValueError as exc:
        yield AssistantStreamEvent(event="error", data={"message": str(exc)})
        return
    yield AssistantStreamEvent(event="token", data={"delta": message})
    yield AssistantStreamEvent(event="done", data={})
```

This removes the `while` loop, the `max_tool_calls` / `tool_results` / `tool_calls` locals, and the `build_followup_messages` call. `_parse_model_json`, `_final_message`, `_tool_arguments`, and `SELECTION_TOOLS` stay.

- [ ] **Step 4: Delete the now-unused follow-up prompt**

In `app/assistant/prompts.py`, delete the entire `build_followup_messages` function (lines ~53-86). Then confirm nothing else references it:

Run: `grep -rn "build_followup_messages" app/ tests/`
Expected: no matches. (If a test references it, delete that test — it covered removed behavior.)

- [ ] **Step 5: Run the assistant suites to verify they pass**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_assistant_agent.py tests/test_assistant_api.py tests/test_assistant_tools.py tests/test_assistant_summaries.py -v`
Expected: PASS. Then `PYTHONPATH=. .venv/bin/ruff check app/assistant tests` — clean (fix any unused-import warnings the rewrite leaves behind, e.g. a now-unused `Any`/loop import).

- [ ] **Step 6: Commit**

```bash
git add app/assistant/agent.py app/assistant/prompts.py tests/test_assistant_agent.py
git commit -m "feat(assistant): classify-then-act loop with deterministic summaries + clarify"
```

---

## Task 4: Frontend — show the real error message

**Files:**
- Modify: `frontend/src/components/AssistantPanel.tsx`
- Test: `frontend/src/components/AssistantPanel.test.tsx`

Run frontend commands from `frontend/`.

- [ ] **Step 1: Write the failing tests**

Add to the existing `describe("AssistantPanel", …)` block in `frontend/src/components/AssistantPanel.test.tsx`:

```ts
it("renders the backend error message instead of a blanket offline", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    sseResponse(
      'event: error\ndata: {"message":"Name at least two places to compare."}\n\n',
    ),
  );
  render(<AssistantPanel dashboardState={dashboardState} />);
  fireEvent.change(screen.getByLabelText("Analyst message"), { target: { value: "compare" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByText("Name at least two places to compare.")).toBeInTheDocument();
});

it("falls back to the offline copy on a transport failure", async () => {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network"));
  render(<AssistantPanel dashboardState={dashboardState} />);
  fireEvent.change(screen.getByLabelText("Analyst message"), { target: { value: "hi" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByText(/analyst is offline/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm test -- AssistantPanel`
Expected: FAIL — the panel currently shows the hardcoded offline copy for the `error` event, not the backend message.

- [ ] **Step 3: Implement — replace the `offline` boolean with an `errorMessage` string**

In `frontend/src/components/AssistantPanel.tsx`:

Replace the state declaration:
```tsx
  const [offline, setOffline] = useState(false);
```
with:
```tsx
  const [errorMessage, setErrorMessage] = useState("");
```

In `sendTurn`, replace `setOffline(false);` with `setErrorMessage("");`, and add a turn-local error string. The relevant block becomes:

```tsx
  async function sendTurn(turnMessages: AssistantMessage[]) {
    let assistantText = "";
    let errored = false;
    let turnError = "";
    setMessages(turnMessages);
    setDraft("");
    setErrorMessage("");
    setToolActivity([]);
    setSending(true);

    try {
      await streamAssistantChat(
        { messages: turnMessages, dashboard_state: dashboardState },
        {
          onEvent: (event) => {
            if (event.event === "tool") {
              const toolName = String(event.data.tool_name ?? "tool");
              setToolActivity((current) => [{ label: toolName }, ...current].slice(0, 4));
              onToolResult?.(event.data);
            }
            if (event.event === "token") {
              assistantText += event.data.delta ?? "";
              setDraft(assistantText);
            }
            if (event.event === "error") {
              errored = true;
              turnError = String(event.data.message ?? "").trim();
            }
          },
        },
      );
      if (!errored && assistantText.trim()) {
        setMessages([...turnMessages, { role: "assistant", content: assistantText.trim() }]);
      }
      setDraft("");
      if (errored) setErrorMessage(turnError || OFFLINE_MESSAGE);
    } catch {
      setDraft("");
      setErrorMessage(OFFLINE_MESSAGE);
    } finally {
      setSending(false);
    }
  }
```

Replace the render block (lines ~114-121) that reads `{offline ? (` with:

```tsx
      {errorMessage ? (
        <div className="mc-assistant-error" role="status">
          <p>{errorMessage}</p>
          <button type="button" className="mc-chip" onClick={handleRetry} disabled={sending}>
            Retry
          </button>
        </div>
      ) : null}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm test -- AssistantPanel`
Expected: PASS. Then the full frontend suite + lint:
Run: `npm test` then `npm run lint`
Expected: all pass, lint clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AssistantPanel.tsx frontend/src/components/AssistantPanel.test.tsx
git commit -m "feat(frontend): show real assistant error; offline copy only on transport failure"
```

---

## Task 5: Full verification gate

- [ ] **Step 1: Backend gate**

Run (from worktree root):
```bash
PYTHONPATH=. .venv/bin/pytest -q
PYTHONPATH=. .venv/bin/ruff check .
```
Expected: all pass, ruff clean.

- [ ] **Step 2: Frontend gate**

Run (from `frontend/`):
```bash
npm test
npm run build
```
Expected: all tests pass, build succeeds.

- [ ] **Step 3: Live ThinkPad smoke (manual, after merge/deploy)**

"compare Pike Place Market and Capitol Hill" → an **instant** deterministic answer in chat, the Compare tab fills, **no ~60 s wait, no "offline"**. "compare" with one place → a clarifying question, not an error.

---

## Self-Review (completed by plan author)

- **Spec coverage:** deterministic summary (Task 2), one-LLM-call loop + clarify + honest errors (Task 3), `AssistantClarification` (Task 1), frontend real-error (Task 4), gate + smoke (Task 5). All spec sections map to a task.
- **Type/name consistency:** `AssistantClarification` (Task 1) is imported/caught in Task 3; `build_tool_summary(tool_result)` (Task 2) is called in Task 3; result field names (`comparison.overview.{summary_text,options[].label,incident_count}`, neighborhood `places[].{place_label,decision,rate_ratio,ci_lower,ci_upper,place_incident_count,baseline_available}`, resolver `created[].{label,address}`, `unresolved[]` strings) verified against the live services.
- **Placeholders:** none — every step shows the actual code/command.
