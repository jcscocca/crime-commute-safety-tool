# Agent Chat as a Decision Tree — Robustness Design (Phase 1)

> Status: design approved via brainstorming 2026-06-28. Phase 1 of "expand the chat UI"
> (robustness first, richer tab rendering second). Builds on the merged agent-driven pane
> analysis feature (#54) and the Seattle geocoder fix (#55). Phase 2 (richer/redesigned tabs)
> is explicitly deferred and is decoupled from this work.

## Objective

Make the assistant chat **robust and honest** by treating it as what it actually is: a
**decision tree** in which the LLM does exactly one job — **classify the user's message into one
node** (a workflow + its parameters) — and everything downstream is deterministic. The chat must
never make the user wait on a redundant LLM call, never show a false "offline" while a result is
already on screen, and degrade gracefully when a request is underspecified.

## Current Context (what shipped in #54, and what hurts)

The assistant (`app/assistant/`, `POST /assistant/chat`) runs a bounded loop:

1. **Planning** LLM call → JSON `{"type":"tool_call",…}` or `{"type":"final","message":…}`.
2. **Tool loop**: execute the tool (emit a `tool` SSE event that drives the right pane), then a
   **follow-up** LLM call (JSON) decides "another tool or final."
3. The final JSON's `message` is emitted as one `token` event; then `done`. Errors emit `error`.

The workflow tools (`add_place`, `select_places`, `analyze_places`, `compare_places`) resolve
place names internally and drive the Places / Analyze / Compare tabs through the frontend bridge
(`applyAssistantToolResult`).

Two problems surfaced in live use on the ThinkPad (gemma-26b):

- **A redundant, fragile narration step.** After the tool runs, the follow-up LLM call shoves the
  entire tool-result JSON at the 26B model and waits for a strict-JSON answer. This took ~60 s and
  came back empty/unusable — yet the answer it was asked to write **already exists** in the tool
  result (`comparison.overview.summary_text`, the neighborhood `decision` verdict). The LLM was
  re-saying computed facts.
- **A dishonest failure.** When that call failed, the agent emitted `error`, and the frontend
  replaced the real message with a blanket **"The analyst is offline"** — even though the analyst
  answered the planning call fine and **the result was already rendered in the pane**.

## Mental Model (the agreed architecture)

The chat is a **decision tree with a fixed, finite set of nodes**. The LLM is a **switchboard
operator at the door**: it maps fuzzy input → exactly one node, with parameters. It *classifies*;
it does not *generate* (except at one leaf — open questions). Everything after the match —
running the workflow, filling the pane, writing the answer — is deterministic.

This is robust *because the tree is known*: the model never invents structure, only picks from a
fixed set, so its pick is verifiable and the worst case degrades to "ask," not "do the wrong
thing." It also keeps the LLM minimal — one bounded, classify-only call per turn.

**Decoupling principle (do not break):** the agent operates on the **data layer** — it produces
the structured result and the bridge routes it into pane state; the tabs *render* that state. So
redesigning how a tab *looks* (Phase 2) requires no agent or backend change, as long as the tab is
driven by structured data the node already produces. The deterministic summary likewise reads the
computed fields, not the rendered UI.

## Approved Decisions

| Decision | Choice |
|---|---|
| The answer for a workflow turn | **Deterministic summary** built in Python from the tool result — shown immediately |
| Post-tool narration LLM call | **Removed** (redundant: it re-says computed fields) |
| Streaming | **Not built** (the instant deterministic summary already removes the wait; YAGNI) |
| LLM role | **One classification call** per turn: input → node + params, or a free-form prose answer |
| Underspecified requests | **Deterministic clarify** ("name two places to compare"), never a guess, never a scary error |
| Failure honesty | `error` only for a true failure (classifier unreachable, tool error); the frontend shows the **real** message, not a blanket "offline" |
| Multi-tool chaining in one turn | **Dropped** for Phase 1 (the workflows are single-tool; `compare_places` resolves/creates internally) |
| Tab visuals | **Out of scope** (Phase 2); this work is decoupled from them |

## The Node Set (the decision tree)

| Node | Trigger (example) | Required params | Drives | Deterministic answer reads |
|---|---|---|---|---|
| `add_place` | "save my home at 1234 Pine" | `query` | Places tab | `place.display_label`, `address`, `created` |
| `select_places` | "select home and office" | `queries[]` (+ `mode`) | selection | resolved labels, `mode` |
| `analyze_places` | "is my block unusual?" | `queries[]`/selection, dates, radius | Analyze tab | neighborhood `decision`, `rate_ratio`, CI, `adjusted_p_value`, `incident_count` |
| `compare_places` | "compare A and B" | `queries[]`/selection (≥2), dates, radius | Compare tab | per-place counts, `nearest_incident_m`, top type, `overview.summary_text` |
| **open question** (leaf) | "why is it higher?" | — | (chat only) | the LLM's own prose answer |
| **clarify / redirect** (branch) | underspecified, or safety-score | — | (chat only) | a fixed clarifying prompt / the existing invariant redirect |

Dates/radius continue to come from `dashboard_state` (the UI's current chips), overridable inline.

## Components

### 1. Deterministic summary builder (new)

`build_tool_summary(tool_result) -> str` — a new, isolated, unit-tested function in the assistant
package. One neutral, invariant-safe sentence per node, assembled from fields the result already
carries (never a safety score / ranking). It also surfaces resolution provenance from the result:
"Saved Capitol Hill at &lt;address&gt;." / "Couldn't find &lt;query&gt;." Examples:

- `compare_places` → "Pike Place: 299 vs Capitol Hill: 20 reported incidents within 250 m (last 12
  months); nearest 26 m; most common type Larceny-Theft."
- `analyze_places` → "Capitol Hill runs 1.4× its beat baseline — statistically clear (95% CI
  1.1–1.8); 84 reported incidents within 250 m."
- `add_place` → "Saved Capitol Hill at 10th & Pine, Seattle."

### 2. Agent loop (simplified)

`run_assistant_turn` collapses to a single classify-then-act flow:

1. emit `meta`; run the existing safety-score guard (unchanged → redirect + `done`).
2. **Planning call** (the one LLM call) → JSON: a `tool_call` *or* a free-form `final` answer.
3. **If `tool_call`:** resolve params; if a required param can't be satisfied (e.g. `compare`
   with fewer than two resolvable places, or empty `queries` and nothing selected) → emit the
   **clarify** prompt as the answer (`token`) and `done` — *not* an error. Otherwise execute the
   tool (emit `tool`), then emit `build_tool_summary(result)` as the `token` answer and `done`.
   **No follow-up or narration LLM call.**
4. **If free-form `final`:** emit the model's prose `message` as the `token` answer and `done`.
   (This is the only path where the LLM generates.)
5. **Errors:** the planning call failing (`LlmUnavailable`) or a tool error (`AssistantToolError`)
   emits `error` with a **specific, user-safe message**. Because there is no post-tool LLM call, a
   turn can no longer fail *after* the pane has a result.

The follow-up loop, `assistant_max_tool_calls`, and the `final.message` contract for tool turns are
removed.

**Clarify vs. error — the distinguishing mechanism.** Underspecified/ambiguous cases raise a new,
dedicated `AssistantClarification(message)` exception (instead of the generic `AssistantToolError`)
— e.g. the resolver finding fewer than two resolvable places for `compare_places`, or empty
`queries` with nothing selected. The agent renders `AssistantClarification` as a **clarify `token`
+ `done`** (a question back to the user). Every other `AssistantToolError` / `ValueError`
(service failure, genuinely bad input) stays an `error`. So "you need to tell me more" and
"something broke" are different code paths, not the same string.

### 3. Prompts

The planning prompt keeps the JSON tool-or-final contract and name extraction, but drops the
"narrate the tool results" follow-up prompt entirely. The free-form `final` answer is plain prose.

### 4. Frontend

`AssistantPanel` stops overriding the backend error with the hardcoded "The analyst is offline."
It renders the **`error` event's actual `message`**. The blanket-offline copy is reserved for a
genuine transport failure (the `fetch`/stream `catch`, i.e. the request never completed). The
deterministic summary and clarify text arrive as ordinary `token` events and need no new handling.
No protocol/event-type changes.

## Error Handling & Edge Cases

- **Classifier unreachable** (`LlmUnavailable` on the planning call): honest error — "Couldn't
  reach the analyst to interpret your request." The structured UI still works.
- **Tool error** (geocoder down, no resolvable places, service error): the tool's specific message
  is shown — as a **clarify** when it's a missing-param case, as an `error` otherwise.
- **Underspecified request**: clarify prompt, never a guess.
- **Result already on screen**: impossible to then show a false "offline" — the summary is built
  in Python after the tool, with no further failure point.
- **Invariant**: the safety-score guard is unchanged; `build_tool_summary` only restates pane data
  (counts, rate-ratio verdicts) — no scoring/ranking, no claim of presence.

## Testing

Backend:
- `build_tool_summary`: a clear, invariant-safe sentence per node; includes created/unresolved
  provenance; no safety-scoring language.
- Agent loop: a `compare_places` turn emits `tool` then a deterministic `token` then `done`, with
  **no second LLM call** (assert the fake client's `complete` is called once).
- Underspecified `compare` (one place) → a clarify `token` + `done`, **not** `error`.
- Classifier-unreachable → `error` with a specific message (not the blanket offline string).
- Free-form question → the model's prose answer is emitted.
- Safety-score request → still redirected.

Frontend:
- An `error` event renders its real `message`; the blanket-offline copy only appears on a transport
  failure (rejected `fetch`).
- A deterministic `token` renders as the answer; the pane still updates from the `tool` event.

Gate: `make test-all` (pytest + ruff + frontend `npm test` + `npm run build`).

## Delivery Slices

1. `build_tool_summary` + tests.
2. Agent loop simplification (remove follow-up/narration; add clarify routing; honest errors) +
   prompt cleanup + tests.
3. Frontend: show the real error message; reserve the offline copy for transport failure + tests.
4. `make test-all`, then a live ThinkPad smoke (no 60 s wait, no false offline, instant summary).

## Acceptance Criteria

- A workflow turn ("compare A and B") returns an **instant deterministic answer** in chat and
  drives the pane, with **one** LLM call and no post-tool wait.
- A failed/slow model never produces a false "offline" while a result is on screen; real errors
  show their actual message.
- An underspecified request yields a clarifying question, not a guess or a scary error.
- The invariant holds; `make test-all` passes.

## Non-Goals (this phase)

- Streaming, and any second/narration LLM call.
- Multi-tool chaining within a single turn.
- Routes / Export nodes (no agent tool yet).
- **Tab redesign / richer rendering** — that is Phase 2, and is decoupled from this work.
- New statistics or services (this phase only restates existing computed fields).
