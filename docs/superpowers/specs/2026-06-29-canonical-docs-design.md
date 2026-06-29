# Canonical documentation set — design

**Date:** 2026-06-29 · **Status:** approved (design), pending spec review
**Base commit:** `d30235b` (main)
**Worktree / branch:** `.worktrees/canonical-docs` / `jcscocca/claude/canonical-docs`

## Problem

Waypoint's documentation has drifted relative to a fast-moving codebase. The *living* docs
(`README.md`, `CLAUDE.md`, `docs/DEPLOY.md`) are recent and broadly accurate, but there is **no
standalone, current-state technical reference** for the system: the only deep material is a
sprawl of ~17 dated spec/plan pairs under `docs/superpowers/`, which are point-in-time by design
and were never meant to describe the system as it is *now*. Separately, a genuinely useful
`docs/ROADMAP.md` exists but is **stranded** on the unmerged branch `jcscocca/claude/repo-roadmap`
(68 commits behind `main`) and is itself partly stale.

The result: a maintainer or an AI agent returning to the repo has to reconstruct architecture,
data model, API contract, and assistant internals from code every time, and the forward-looking
roadmap is invisible from `main`.

## Goal

Produce a small, **canonical, current-state documentation set** for the primary audience of
**the maintainer and the AI coding agents that work this repo**. It becomes the *deep reference
layer* that the terse `CLAUDE.md` and the front-door `README.md` point into. Every claim is
verified against the code at the base commit.

## Non-goals

- Not rewriting `README.md` (front door) or `CLAUDE.md` (terse agent guide) — only adding a few
  links from them into the new set.
- Not touching the `docs/superpowers/specs|plans` archive — it stays as history.
- Not an end-user/product guide (that audience was explicitly de-scoped).
- Not the "comprehensive" set: privacy/security deep-dive, statistical methodology, routing
  internals, frontend internals, and a full config reference stay in `README.md` for now and may
  graduate to their own docs later.

## Audience & tone

Maintainer + AI agents. Technical depth, real file paths (clickable), real symbol names, real
env vars. Lead with the "why," call out invariants and gotchas explicitly. Concise over
exhaustive — the live `/openapi.json` and the code remain the ultimate source of truth; these
docs orient and explain.

## The set (5 documents)

All four architecture docs live under `docs/architecture/`. The roadmap keeps its established
canonical path `docs/ROADMAP.md`. A new `docs/README.md` index ties all five together and is the
single entry point linked from `README.md` and `CLAUDE.md`.

### 1. `docs/architecture/overview.md` — System Architecture Overview (keystone)
- What/why + the product invariant (no safety scoring) up top.
- Layered model: `api → services → models/db`; where `schemas`, `sessions`, `config`,
  `input_modes` sit.
- The three API tiers (public / internal / admin) and the internal-surface invariant.
- Subsystem map (one-liner + entry-point file each): `assistant`, `analysis`, `routing`,
  `crime`, `parsers` + `normalization`, `exports`, `geocoding`, `places`, `services`.
- One end-to-end request walkthrough (`POST /dashboard/analyze`), naming the modules it touches.
- Backend ↔ frontend boundary: the `frontend/src/api/client.ts` contract, build-vs-dev serve
  modes.
- Cross-cutting invariants index, linking into the other four docs.
- **Mermaid:** a subsystem/layer map.

### 2. `docs/architecture/data-model.md` — Data Model
- Entity catalog from `app/models.py`: session/user-hash, place clusters (display coords),
  stop visits, staging observations, crime incidents, analysis runs (+ provenance), beat
  baselines, beat polygons, route requests/results, statistical comparisons.
- Relationships + the upload → stop-visit → cluster lifecycle, and what is retained vs discarded
  (privacy: raw points dropped unless `MCA_RAW_UPLOAD_RETENTION`).
- Generalized vs exact coordinates (`display_latitude/longitude`).
- Migrations: Alembic, 7 versions, SQLite-dev / Postgres-prod, how to add one; note the
  `init_db` `create_all` vs `alembic upgrade head` dual path.
- **Mermaid:** an ER diagram of the core entities.

### 3. `docs/architecture/api.md` — API Contract
- Auth model: session cookie, `X-Demo-User-Id` demo identity, `X-Admin-Token`;
  `required_public_user_hash` (public) vs `current_user_hash` (internal fallback).
- Endpoint reference grouped by router (`app/api/routes_*.py`), each pointing at its
  `app/schemas.py` request/response types — contracts and rules, not every field.
- The internal-surface invariant and how `tests/test_internal_surface.py` enforces it.
- Personal-uploads 404 gating (`MCA_PUBLIC_ENABLE_PERSONAL_UPLOADS`); SSE for `/assistant/chat`.
- Points to `/docs` (Swagger) and `/openapi.json` as the live source of truth.

### 4. `docs/architecture/assistant.md` — Assistant / Agent Design
- Decision-tree architecture: one classify-only LLM call → deterministic per-node summary
  (no post-tool narration call); the clarification flow.
- Tool toolbox (`get_dashboard_summary`, `run_place_analysis`, `compare_places`,
  `get_incident_details`, `suggest_followups`) + `MCA_ASSISTANT_MAX_TOOL_CALLS` cap.
- Agent-driven pane analysis: the per-tab toolbox + the frontend bridge.
- Semantic layer + deterministic summaries.
- `llm_client` (OpenAI-compatible, `MCA_LLM_BASE_URL` / `MCA_LLM_MODEL`), graceful degradation
  when the endpoint is offline (only the chat panel is affected).
- ⚠ The refusal/policy invariant and where it is enforced (`app/assistant/agent.py`).
- **Mermaid:** the per-turn decision-tree / request flow.

### 5. `docs/ROADMAP.md` — Roadmap (rescued + refreshed)
- Port the content from `jcscocca/claude/repo-roadmap` onto this branch.
- **Refresh every checkbox against current `main`**: mark/remove shipped items (LocalAgent
  retirement + Analyst doc fix; assistant token streaming + "analyst offline" degraded state;
  verify Routes/OTP merge status; chat-robustness items), and update the maturity snapshot and
  the "if you pick five things" list accordingly.
- Keep its "supersedes the dated drafts" note and the relative links into `docs/superpowers/`.

## Conventions (every doc)

- Opens with a one-line scope note + a `Verified against <commit-sha> (YYYY-MM-DD)` stamp so
  future staleness is visible at a glance.
- Text-first; a **Mermaid** diagram only where it earns its place (system map, ER, request
  flow) — renders on GitHub, stays diff-able.
- Invariants flagged inline with a consistent **⚠ Invariant** marker.
- Cross-link siblings; link to real files as clickable repo-relative paths.

## Cross-linking & index

- New `docs/README.md`: short index of the canonical set (the 5 docs) with a one-line purpose
  each, plus a pointer to the `docs/superpowers/` archive as history.
- `README.md`: add a link from the "Developer reference" section into `docs/architecture/` /
  `docs/README.md`.
- `CLAUDE.md`: add a one-line pointer to the canonical docs index.

## Verification

This is a docs-only change; the `make test-all` gate concerns code. Verification here means:
- Every referenced file path, symbol, endpoint, and env var exists in the code at base commit
  (audit while writing; a final grep-sweep of referenced paths).
- Mermaid blocks are syntactically valid.
- No claim is aspirational — if something is built-but-off or half-baked, say so (the roadmap's
  maturity framing).

## Risks / open items

- **Roadmap accuracy:** the refresh requires per-item verification against `main`; the riskiest
  part is silently leaving a shipped item unchecked or vice-versa. Mitigation: verify each box
  against code/PRs while refreshing.
- **Placement of ROADMAP.md:** kept at `docs/ROADMAP.md` (its canonical path) rather than inside
  `docs/architecture/`, grouped via the index. Reversible if the maintainer prefers otherwise.
- **Stale branch cleanup:** `jcscocca/claude/repo-roadmap` becomes deletable once this lands —
  flagged, not deleted as part of this work.

## Implementation outline (detailed plan via writing-plans)

1. Audit + write `overview.md` (anchors the others).
2. Audit + write `data-model.md`, `api.md`, `assistant.md` (parallelizable).
3. Rescue + refresh `ROADMAP.md`.
4. Add `docs/README.md` index; add links from `README.md` and `CLAUDE.md`.
5. Final cross-link + referenced-path grep-sweep; commit; open PR.
