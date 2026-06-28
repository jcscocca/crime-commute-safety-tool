# Waypoint Next Steps Roadmap

> **Status — reconciled to `main` 2026-06-28: the full v2 program (epics A–E) is shipped.**
> This refreshes the earlier post-#18 reconciliation (PR #19), which predated the epic A/B/C
> merges (PRs #20–#22, #26). The verbose per-task checklists for the *shipped* workstreams
> have been dropped — the code and the linked PRs are the source of truth. No build work
> remains; the only open items are operational: the product/privacy decision to enable
> personal uploads (epic A's flag) and standing up a live OpenTripPlanner instance (epic B).

**Goal:** Take Waypoint from a strong local/demo dashboard to a trustworthy analyst product:
robust assistant, durable analysis provenance, neighborhood-relative statistics, scalable
real-data analysis, clear public-beta boundaries, and live routing.

**Tech stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, SQLite/Postgres+PostGIS, React,
TypeScript, Vite, Vitest, pytest, ruff, and a direct OpenAI-compatible LLM endpoint with
multi-node failover (the LocalAgent SSE gateway is retired).

---

## Progress snapshot

| # | Workstream | Status | Evidence on `main` |
|---|------------|--------|--------------------|
| 1 | Assistant reliability | ✅ Shipped | JSON tolerance in `app/assistant/agent.py`; multi-node failover + thinking control ([PR #12](https://github.com/jcscocca/crime-commute-safety-tool/pull/12)); "interpret, don't restate" ([PR #14](https://github.com/jcscocca/crime-commute-safety-tool/pull/14)). Live smoke is covered by `scripts/live_smoke.py` (Step 9 hits `/assistant/chat`); the separate `live_test_assistant.sh` was never needed. |
| 2 | Analysis run provenance | ✅ Shipped | `AnalysisRun` + migration `0006_analysis_runs.py` |
| 3 | Neighborhood-relative Analyze | ✅ Shipped | `app/analysis/beat_baselines.py`, beats CSV, `MethodsAppendix.tsx`, `POST /dashboard/neighborhood`, `get_neighborhood_analysis` tool ([PR #14](https://github.com/jcscocca/crime-commute-safety-tool/pull/14)). Verdict-methodology QA all fixed: #1/#5 ([PR #17](https://github.com/jcscocca/crime-commute-safety-tool/pull/17)), #2/#3 ([PR #18](https://github.com/jcscocca/crime-commute-safety-tool/pull/18)). |
| 4 | Real-data performance | ✅ Shipped | Public dashboard path already filtered in SQL (`dashboard_analysis_service.py`); `app/services/incident_query_service.py` (bbox + SQL date/offense prefilter) then replaced the three remaining full-table `CrimeIncident` loads — site buffer, route-corridor comparison, route-context summaries — so the legacy `_incident_rows` load is gone and `exposure.py`/`context.py` results are unchanged ([PR #20](https://github.com/jcscocca/crime-commute-safety-tool/pull/20)). |
| 5 | Public-beta hardening | ✅ Shipped | Legacy surface internal-gated ([PR #13](https://github.com/jcscocca/crime-commute-safety-tool/pull/13)); session required on public routers; geocode proxy ([PR #15](https://github.com/jcscocca/crime-commute-safety-tool/pull/15)); 401-without-session guard ([PR #16](https://github.com/jcscocca/crime-commute-safety-tool/pull/16)). The last item — personal-upload consent/caveat copy — shipped with epic A ([PR #21](https://github.com/jcscocca/crime-commute-safety-tool/pull/21), `frontend/src/components/PersonalUpload.tsx`). |
| 6 | Live routing provider | ✅ Shipped (code) | `app/routing/opentripplanner_provider.py` behind the provider interface; `MCA_ROUTING_PROVIDER` (default `mock`) + `MCA_OPENTRIPPLANNER_BASE_URL` in `app/config.py`; OTP2 GTFS GraphQL ([PR #20](https://github.com/jcscocca/crime-commute-safety-tool/pull/20) → GraphQL port [PR #26](https://github.com/jcscocca/crime-commute-safety-tool/pull/26)). Route UI wired: `RoutesTab.tsx` + map polylines (`MapCanvas.tsx`) over public `/routes/*` (`app/api/routes_public_routes.py`) ([PR #22](https://github.com/jcscocca/crime-commute-safety-tool/pull/22)). Fixture-validated only — not yet run against a live OTP2 server. |

The v1 lean public beta (saved places + neighborhood analysis + Tableau exports on read-only
SPD data) is complete, and the v2 epics below have since extended it.

---

## v2 epics (2026-06-26 backlog review)

The work, reframed as epics — **all now shipped**. A was the headline new feature; B–E hardened
what shipped. Only operational follow-ups remain (see the snapshot above and each epic below).

- **A — Personal data upload.** ✅ **Shipped, dark-launched ([PR #21](https://github.com/jcscocca/crime-commute-safety-tool/pull/21), merged 2026-06-26).**
  Google Timeline / CSV / GeoJSON / GPX ingest (`app/parsers/`), consent & caveat copy
  (`frontend/src/components/PersonalUpload.tsx`, this absorbed WS5's last item), and
  keep-only-clusters retention + delete-my-data enforced in
  `app/services/public_upload_service.py`, exposed via public `/uploads` endpoints behind the
  flag. Ships **disabled** — `MCA_PUBLIC_ENABLE_PERSONAL_UPLOADS=false` by default (documented in
  `README.md` / `.env.example`), so the endpoints 404 and the UI never renders until enabled.
  **Only remaining step:** the product/privacy decision to flip the flag in an env — or to
  formally park the feature. No code change is pending.
- **B — Live routing provider** (= WS6). ✅ **Shipped.** OpenTripPlanner behind the provider
  interface + `MCA_ROUTING_PROVIDER` (mock stays the default), OTP2 GTFS GraphQL ([PR #20](https://github.com/jcscocca/crime-commute-safety-tool/pull/20),
  GraphQL port [PR #26](https://github.com/jcscocca/crime-commute-safety-tool/pull/26)); the route-alternatives surface is wired into the UI ([PR #22](https://github.com/jcscocca/crime-commute-safety-tool/pull/22)).
  **Open item (ops, not code):** stand up a live OTP2 instance and smoke-test the GraphQL
  provider against it — fixture-validated only so far.
- **C — Real-data performance** (= WS4). ✅ **Shipped, [PR #20](https://github.com/jcscocca/crime-commute-safety-tool/pull/20).** `incident_query_service.py`
  replaced `_incident_rows`' full-table load with bbox + SQL date/offense-filtered queries
  across all three call sites; Python distance checks run only on the narrowed set, and
  `exposure.py`/`context.py` are unchanged so results match.
- **D — Neighborhood verdict methodology** (WS3 follow-up). ✅ **SHIPPED, [PR #18](https://github.com/jcscocca/crime-commute-safety-tool/pull/18)** —
  rest-of-beat baseline (#2) + coherent dual CI/p-value with supplementary exact p (#3),
  engine-wide. Spec: `docs/superpowers/specs/2026-06-26-neighborhood-verdict-methodology-design.md`.
- **E — Roadmap hygiene.** ✅ This document (first reconciled post-#18 in [PR #19](https://github.com/jcscocca/crime-commute-safety-tool/pull/19); refreshed 2026-06-28 to record A/B/C shipped).

**Sequence (all delivered):** D → E → **B + C together** → A. The build is complete; remaining
items are operational — enable epic A's flag (product/privacy decision) and stand up a live
OTP2 instance for epic B.

---

## Epic detail (all shipped — kept as the build record)

### B — Live routing provider ✅ shipped
- `MCA_ROUTING_PROVIDER` (default `mock`) + `MCA_OPENTRIPPLANNER_BASE_URL` /
  `MCA_OPENTRIPPLANNER_TIMEOUT_S` in `app/config.py` / `.env.example`.
- `app/routing/opentripplanner_provider.py` behind the provider interface in
  `app/routing/providers.py`; `mock_provider.py` stays the default. OTP1 REST was ported to
  OTP2 GTFS GraphQL ([PR #26](https://github.com/jcscocca/crime-commute-safety-tool/pull/26)).
- Route-alternatives + statistical route-comparison surface wired into the React UI
  (`RoutesTab.tsx`, map polylines via `MapCanvas.tsx`) over public `/routes/*`
  (`app/api/routes_public_routes.py`) ([PR #22](https://github.com/jcscocca/crime-commute-safety-tool/pull/22)).
- Provider contract tests with mocked httpx responses. **Not yet run against a live OTP2
  server** — that (plus a smoke test) is the one open ops item.

### C — Real-data performance ✅ shipped ([PR #20](https://github.com/jcscocca/crime-commute-safety-tool/pull/20))
- `app/services/incident_query_service.py` replaced the `_incident_rows` full-table load with
  bbox + SQL date/offense-filtered queries across all three call sites (site buffer,
  route-corridor comparison, route-context summaries); `_incident_rows` is gone.
- Python distance checks run only on the narrowed set; `exposure.py`/`context.py` unchanged,
  so results are identical. Filter indexes in `alembic/versions/0005_crime_filter_idx.py`.

### A — Personal upload ✅ shipped (dark-launched, [PR #21](https://github.com/jcscocca/crime-commute-safety-tool/pull/21), merged 2026-06-26)
All three former to-dos landed (4 commits — `dd8bb89`, `b933e57`, `557be3d`, `f80f1e0`):
- Parsers for Google Timeline JSON, point CSV, GeoJSON, GPX → place clusters — `app/parsers/`.
- User-facing consent + caveat copy (WS5's last item) — `frontend/src/components/PersonalUpload.tsx`.
- Privacy/retention model enforced — `app/services/public_upload_service.py` (keep only
  clusters; discard raw points + stops unless `MCA_RAW_UPLOAD_RETENTION=true`) plus delete-my-data.

Ships **disabled** behind `MCA_PUBLIC_ENABLE_PERSONAL_UPLOADS=false`. **Only remaining step:**
the product/privacy decision to flip the flag in an env — or to formally park the feature. No
code is pending.

---

## Verification gate

`make test-all` = `pytest` + `ruff check .` + frontend `npm test` + `npm run build`. Run it
before claiming any workstream complete. Work in a dedicated git worktree (concurrent agents).
