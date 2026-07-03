# Waypoint documentation

Canonical, current-state reference for **maintainers and AI agents working this repo**. Each
architecture doc states the commit it was last verified against; when you change a subsystem,
update its doc in the same PR.

## Canonical docs

| Doc | What it covers |
|---|---|
| [Architecture overview](architecture/overview.md) | System map: layers, the public/internal/admin API tiers, the subsystem index, an end-to-end request walkthrough, and the backend↔frontend boundary. **Start here.** |
| [Data model](architecture/data-model.md) | The 11 SQLAlchemy entities, the upload→stop→cluster lifecycle, coordinate generalization, and the Alembic migration approach. |
| [API contract](architecture/api.md) | Auth model (session cookie, demo identity, admin token), the three-tier endpoint reference, the internal-surface invariant, and upload/SSE transport notes. |
| [Assistant / agent design](architecture/assistant.md) | The Waypoint Analyst: the single-LLM-call decision-tree turn, the tool toolbox + frontend bridge, deterministic summaries, and the safety-refusal guard. |
| [Roadmap](ROADMAP.md) | Where Waypoint is going: a subsystem maturity snapshot and phased work, refreshed against current `main`. |

## Also under `docs/`

- **`superpowers/specs/` and `superpowers/plans/`** — point-in-time design specs and
  implementation plans, one pair per feature. A historical record of *how* things were built;
  not a description of current state.
- **`reference/`** — background and source material (the SPD crime-analysis suite).
- **`DEPLOY.md`** — deployment guide for the single-host stack.
