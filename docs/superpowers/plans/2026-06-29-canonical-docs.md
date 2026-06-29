# Canonical Documentation Set — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Author a 5-document canonical, current-state reference set (4 architecture docs + a refreshed roadmap) verified against `main` @ `d30235b`, for the maintainer and AI agents.

**Architecture:** Four new docs under `docs/architecture/` plus a rescued/refreshed `docs/ROADMAP.md`, tied together by a `docs/README.md` index and linked from `README.md` + `CLAUDE.md`. The `docs/superpowers/` archive is left as history.

**Tech Stack:** Markdown + Mermaid (GitHub-rendered). No code changes; verification is path/symbol existence + Mermaid validity, not unit tests.

---

## Note on adaptation (docs plan, not a code/TDD plan)

This builds documentation, so the usual "write failing test → implement → pass" loop doesn't
apply. Each doc task is: **audit** the named source files → **write** the doc against the given
outline (real paths/symbols only) → **verify** (re-read against sources; Mermaid fences
well-formed) → **commit**. A single comprehensive path-existence sweep runs at the end (Task 7).

**Shared conventions for every doc written below:**
- First lines: a one-sentence scope note, then `> Verified against \`d30235b\` (2026-06-29).`
- Text-first; a Mermaid block only where noted in the outline.
- Inline invariant callouts use the literal marker **⚠ Invariant:**.
- All file references are clickable repo-relative paths in backticks (e.g. `` `app/models.py` ``).
- Do not state anything aspirational — if a feature is built-but-off or half-baked, say so.

---

## Task 1: System Architecture Overview (keystone)

**Files:**
- Create: `docs/architecture/overview.md`
- Audit (read before writing): `app/main.py` (app assembly + router registration), `app/config.py`
  (Settings), `app/db.py`, and the directory layout of `app/` (`api/`, `services/`, `assistant/`,
  `analysis/`, `routing/`, `crime/`, `parsers/`, `normalization/`, `exports/`, `geocoding/`,
  `places/`) and `frontend/src/` (`api/client.ts`, `components/`, `lib/`).

- [ ] **Step 1: Audit app assembly.** Read `app/main.py` and list every router it registers and
  the order. Read `app/config.py` for the `MCA_`-prefixed settings groups. Read `app/db.py` for the
  engine/session setup and the `init_db` `create_all` vs Alembic path.

- [ ] **Step 2: Write `docs/architecture/overview.md`** with these sections:
  - **Purpose & product invariant** — one paragraph; ⚠ Invariant: reports *reported incident
    context*, never scores/ranks safety (enforced in copy + `app/assistant/agent.py`).
  - **Layered model** — `app/api/` (HTTP) → `app/services/` (business logic) → `app/models.py` +
    `app/db.py` (persistence); supporting `app/schemas.py`, `app/sessions.py`, `app/config.py`,
    `app/input_modes.py`.
  - **API tiers** — public / internal (`include_in_schema=False`) / admin; ⚠ Invariant: internal
    routers must not be re-exposed on bare public paths (`tests/test_internal_surface.py`). Link to
    `api.md` for detail.
  - **Subsystem map** — one line + entry-point file for each: `assistant` (`app/assistant/agent.py`),
    `analysis` (`app/analysis/comparison.py`), `routing` (`app/routing/providers.py`), `crime`
    (`app/crime/`), `parsers`+`normalization` (upload pipeline), `exports` (`app/exports/`),
    `geocoding` (`app/geocoding/`), `places`, `services`.
  - **Request walkthrough** — trace `POST /dashboard/analyze` from public router → service →
    models → response, naming each module touched.
  - **Backend ↔ frontend** — `frontend/src/api/client.ts` calls only the public tier; build mode
    (served from `app/static/dashboard`) vs Vite dev mode.
  - **Invariants index** — bulleted list linking to where each is documented/enforced.
  - **Mermaid:** a layer + subsystem map (`flowchart`).

- [ ] **Step 3: Verify.** Re-read the doc beside `app/main.py`; confirm every named router/module
  path exists. Run:
  `ls app/main.py app/config.py app/db.py app/models.py app/schemas.py frontend/src/api/client.ts`
  Expected: all listed, no "No such file".

- [ ] **Step 4: Commit.**
```bash
git add docs/architecture/overview.md
git commit -m "docs(architecture): add system overview" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Data Model

**Files:**
- Create: `docs/architecture/data-model.md`
- Audit: `app/models.py` (all 15 entity classes), `alembic/versions/*.py` (7 migrations),
  `app/db.py`, `app/normalization/` (clustering pipeline), `app/config.py` (normalization +
  retention settings).

- [ ] **Step 1: Audit entities.** Read `app/models.py` and capture, per class, the table name, key
  columns, and relationships. The 15 entities, grouped:
  - **Upload→cluster pipeline:** `ImportBatch` → `StagingLocationObservation` → `StopVisit` →
    `PlaceCluster`.
  - **Crime:** `CrimeIncident`, `PlaceCrimeSummary`.
  - **Analysis:** `AnalysisRun`.
  - **Routing:** `RouteRequest` → `RouteAlternative` → `RouteSegment`, `RouteContextSummary`.
  - **Statistics:** `StatisticalComparison` → `StatisticalComparisonOption`,
    `StatisticalPairwiseResult`.
  - **Infra:** `GeocodeCache`.
  Note explicitly: **user identity is not a table** — it is a hashed `X-Demo-User-Id`
  (`MCA_USER_HASH_SALT`); sessions are cookie-based.

- [ ] **Step 2: Write `docs/architecture/data-model.md`** with:
  - **Entity catalog** — a table per group above (entity · table · purpose · key columns).
  - **Lifecycle** — upload → staging observations → stop visits → place clusters; ⚠ Invariant:
    raw points + stops discarded after clustering unless `MCA_RAW_UPLOAD_RETENTION=true`.
  - **Generalized vs exact coordinates** — `display_latitude/longitude` and the exporter's coarse
    rounding fallback.
  - **Migrations** — Alembic (7 versions), SQLite-dev / Postgres-prod, how to add one; note the
    `init_db` `create_all` vs `alembic upgrade head` dual path.
  - **Mermaid:** an `erDiagram` of the core entities + relationships.

- [ ] **Step 3: Verify.** Run:
  `grep -c "__tablename__" app/models.py` (expect `15`) and confirm every table name in the doc
  appears in `app/models.py`:
  `grep -oE '\`[a-z_]+\`' docs/architecture/data-model.md | tr -d '\`' | sort -u | while read t; do grep -q "\"$t\"" app/models.py && echo "ok $t" || true; done`

- [ ] **Step 4: Commit.**
```bash
git add docs/architecture/data-model.md
git commit -m "docs(architecture): add data model reference" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: API Contract

**Files:**
- Create: `docs/architecture/api.md`
- Audit: every `app/api/routes_*.py`, `app/sessions.py` (session + `required_public_user_hash` /
  `current_user_hash`), `app/schemas.py`, `tests/test_internal_surface.py`.

- [ ] **Step 1: Audit the surface.** For each `app/api/routes_*.py`, record its prefix, whether it
  sets `include_in_schema=False` (internal) and its auth dependency. Confirm the public/internal
  pairing pattern (`routes_dashboard.py` internal vs `routes_public_dashboard.py` public; same for
  `places`, `routes`). **Reconcile the exports split** — determine which export endpoints are public
  (`/exports/tableau/*`) vs internal (`/internal/exports/*`) by reading `routes_exports.py` and
  `app/main.py`.

- [ ] **Step 2: Write `docs/architecture/api.md`** with:
  - **Auth model** — session cookie, `X-Demo-User-Id` (hashed) demo identity, `X-Admin-Token`;
    `required_public_user_hash` (public, real session) vs `current_user_hash` (internal fallback).
  - **Tier reference** — three subsections (Public / Internal / Admin), each a table of
    endpoints → router file → request/response schema in `app/schemas.py`.
  - ⚠ Invariant: internal endpoints stay off bare public paths; enforced by
    `tests/test_internal_surface.py`.
  - **Gating & transport notes** — personal-uploads 404 until `MCA_PUBLIC_ENABLE_PERSONAL_UPLOADS`;
    `/assistant/chat` is Server-Sent Events.
  - **Source of truth** — `/docs` (Swagger) + `/openapi.json` for exact field-level shapes.

- [ ] **Step 3: Verify.** Run:
  `ls app/api/routes_*.py` and confirm every router named in the doc exists; confirm the internal
  set matches `grep -rl "include_in_schema=False" app/api/`.

- [ ] **Step 4: Commit.**
```bash
git add docs/architecture/api.md
git commit -m "docs(architecture): add API contract reference" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Assistant / Agent Design

**Files:**
- Create: `docs/architecture/assistant.md`
- Audit: `app/assistant/agent.py` (decision tree + refusal guard), `app/assistant/tools.py`,
  `app/assistant/summaries.py`, `app/assistant/semantic_layer.py`, `app/assistant/llm_client.py`,
  `app/assistant/place_resolution.py`, `app/assistant/prompts.py`, `app/assistant/schemas.py`,
  `app/api/routes_assistant.py`, and the frontend bridge (locate with
  `grep -rl "assistant\|analyst" frontend/src/lib frontend/src/components`).

- [ ] **Step 1: Audit the agent.** Read `app/assistant/agent.py` and capture: the decision-tree
  nodes, the single classify-only LLM call, the deterministic per-node summary path (no post-tool
  narration call), the clarification branch, and the **safety-refusal guard** (note its current
  keyword-match form). Read `tools.py` for the toolbox and `routes_assistant.py` for the SSE flow.

- [ ] **Step 2: Write `docs/architecture/assistant.md`** with:
  - **Decision-tree architecture** — one classify LLM call → deterministic per-node summary;
    clarification flow; why (robustness, no false-offline, bounded latency).
  - **Toolbox** — `get_dashboard_summary`, `run_place_analysis`, `compare_places`,
    `get_incident_details`, `suggest_followups`; `MCA_ASSISTANT_MAX_TOOL_CALLS` cap.
  - **Agent-driven pane analysis** — per-tab toolbox + the frontend bridge (name the file found).
  - **Semantic layer + deterministic summaries** — `semantic_layer.py`, `summaries.py`,
    `place_resolution.py` (names resolved internally).
  - **LLM client** — `llm_client.py`, OpenAI-compatible, `MCA_LLM_BASE_URL` / `MCA_LLM_MODEL`;
    ⚠ Invariant: endpoint offline degrades only the chat panel.
  - ⚠ Invariant: refusal/policy guard — refuses safety-score requests; enforced in
    `app/assistant/agent.py`. Note the known limitation (keyword-match breadth) and link to the
    ROADMAP item that hardens it.
  - **Mermaid:** the per-turn decision-tree flow.

- [ ] **Step 3: Verify.** Run:
  `ls app/assistant/agent.py app/assistant/tools.py app/assistant/llm_client.py app/api/routes_assistant.py`
  and confirm the five tool names in the doc each appear in `app/assistant/tools.py`
  (`grep -oE "get_dashboard_summary|run_place_analysis|compare_places|get_incident_details|suggest_followups" app/assistant/tools.py | sort -u`).

- [ ] **Step 4: Commit.**
```bash
git add docs/architecture/assistant.md
git commit -m "docs(architecture): add assistant/agent design" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Roadmap (rescue + refresh)

**Files:**
- Create: `docs/ROADMAP.md` (ported from branch, then refreshed)
- Audit: current `main` state to re-check each checkbox.

- [ ] **Step 1: Port the stranded roadmap.** Run:
```bash
git show jcscocca/claude/repo-roadmap:docs/ROADMAP.md > docs/ROADMAP.md
```

- [ ] **Step 2: Re-verify each checkbox against current code.** For each, run the check and update
  the box (check off / strike / remove with a one-line "shipped in <PR>" note as appropriate):
  - LocalAgent retired? `grep -rn "MCA_LOCALAGENT_BASE_URL\|LocalAgentClient" app/ README.md` (expect
    none) and `ls app/assistant/llm_client.py` (expect present) → Phase 0 item **shipped**.
  - Analyst docs fixed? `grep -n "MCA_LLM_BASE_URL" README.md` (expect present) → **shipped**.
  - Assistant token streaming + offline state? `grep -in "stream\|offline" README.md` and read
    `app/api/routes_assistant.py` → mark Phase 3 sub-items per findings.
  - Routes/OTP merged? `git log --oneline main | grep -i "route"` and check `MCA_ROUTING_PROVIDER`
    in README → update Phase 0 "Merge Routes" + maturity snapshot.
  - Safety-refusal guard hardened? Read the guard in `app/assistant/agent.py`; if still
    keyword-match, **leave Phase 1 item open** and align wording with `assistant.md`.
  - Half-exposed stats export? Read `routes_exports.py` for a public writer of
    `statistical-comparisons.csv`; update Phase 0 item per finding.
  - `PlaceForm.test.tsx` jsdom pragma? `grep -n "vitest-environment" frontend/src/components/*.test.tsx`
    → update Phase 0 item.
  - Admin-token boot validator? `grep -n "ADMIN_INGEST_TOKEN" app/config.py` → update Phase 0 item.

- [ ] **Step 3: Update framing.** Refresh the "Maturity snapshot" table and the "If you pick five
  things first" list to reflect what is now done. Update the `Last updated:` line to `2026-06-29`
  and the base-commit note to `d30235b`. Keep the "supersedes the dated drafts" note and the
  relative links into `docs/superpowers/`.

- [ ] **Step 4: Commit.**
```bash
git add docs/ROADMAP.md
git commit -m "docs: rescue and refresh canonical ROADMAP against current main" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Index + inbound links

**Files:**
- Create: `docs/README.md`
- Modify: `README.md` (the "Developer reference" section), `CLAUDE.md` (add a one-line pointer)

- [ ] **Step 1: Write `docs/README.md`** — a short index: one line per canonical doc (the 4
  architecture docs + ROADMAP) with its purpose and a link, then a pointer to `docs/superpowers/`
  as historical specs/plans and `docs/reference/` as background.

- [ ] **Step 2: Link from `README.md`.** In the "Developer reference" section, add a sentence:
  "For internal architecture, see [docs/README.md](docs/README.md)." (Verify the exact section
  heading first with `grep -n "Developer reference" README.md`.)

- [ ] **Step 3: Link from `CLAUDE.md`.** Add one line near the top: a pointer to
  `docs/README.md` as the deep reference index. Keep CLAUDE.md terse.

- [ ] **Step 4: Commit.**
```bash
git add docs/README.md README.md CLAUDE.md
git commit -m "docs: add canonical docs index and link from README + CLAUDE" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Final verification + PR

- [ ] **Step 1: Referenced-path sweep.** Confirm every repo path referenced across the new docs
  exists. Run:
```bash
grep -rhoE '`(app|frontend|tests|alembic|docs)/[A-Za-z0-9_./*-]+`' docs/architecture docs/README.md docs/ROADMAP.md \
  | tr -d '`' | sort -u \
  | while read p; do case "$p" in *"*"*) continue;; esac; test -e "$p" || echo "MISSING: $p"; done
```
  Expected: no `MISSING:` lines. Fix any that print.

- [ ] **Step 2: Mermaid sanity.** Confirm each ```` ```mermaid ```` fence is closed and the diagram
  type is valid (`flowchart`, `erDiagram`). Run:
  `grep -c '```mermaid' docs/architecture/*.md` and eyeball each block.

- [ ] **Step 3: Stamp check.** Confirm every new doc has the `Verified against \`d30235b\``
  line: `grep -L "Verified against" docs/architecture/*.md` (expect empty output).

- [ ] **Step 4: Open the PR.**
```bash
git push -u origin jcscocca/claude/canonical-docs
gh pr create --title "docs: canonical architecture docs + refreshed roadmap" \
  --body "Adds a 5-doc canonical reference set (overview, data-model, api, assistant + refreshed ROADMAP) verified against main. Rescues the stranded docs/ROADMAP.md. Design: docs/superpowers/specs/2026-06-29-canonical-docs-design.md.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 5: Flag cleanup.** Note in the PR description (or to the maintainer) that the stale
  `jcscocca/claude/repo-roadmap` branch can be deleted once this merges.

---

## Self-review (filled during planning)

- **Spec coverage:** all 5 docs (Tasks 1–5), index + inbound links (Task 6), conventions
  (shared block), Mermaid (per-doc steps), verification (Task 7), out-of-scope respected (no
  privacy/stats/routing/frontend/config deep-dives), ROADMAP placement at `docs/ROADMAP.md`
  (Task 5), stale-branch flag (Task 7 step 5). ✓
- **Placeholders:** none — every task names exact files, real entity/router/tool names, and exact
  verify/commit commands.
- **Consistency:** entity names match `app/models.py` (15 `__tablename__`); tool names match the
  set documented in `assistant.md`; tier terms (`required_public_user_hash` / `current_user_hash`)
  used identically in `api.md`, `overview.md`, and the audit steps.
