# CompCat resurface — design

**Date:** 2026-07-13
**Status:** Approved
**Scope:** Rebrand Waypoint → CompCat (pun on CompStat), retheme to a dark-first
"precinct board" look, replace the Copper assistant persona with Tabby, and
restructure the drawer around Analyze + Compare. Frontend + assistant-prompt only;
no backend/API changes.

## Decisions (from brainstorm)

| Question | Decision |
|---|---|
| How far does the cat pun go? | Mascot cat, serious app — assistant becomes a cat; UI copy and theme stay data-first. No paw-print whimsy in the UI. |
| Assistant name | **Tabby** (tabby cat / tabular data / UI tabs) |
| Theme direction | **Precinct board** — graphite chrome + stat-green accent, mono numerals |
| Light theme | Dark-first, light kept — dark becomes the default; light survives behind the existing toggle, restyled with the green accent |
| Tab focus | Three tabs: **Analyze · Compare · Export**; Places demoted from peer tab to a chip strip |
| Places relocation | Chip strip at the top of Analyze and Compare; add/manage flows stay in the existing modal |
| Rename depth | Presentation + GitHub repo rename to `compcat` (user performs in GitHub UI; redirects preserve old URLs). `MCA_*` env vars, API paths, `waypoint.*` localStorage keys, Python package names unchanged. |

## 1. Identity

- Wordmark `Waypoint` → `CompCat` in `MapWorkspace.tsx` (`mc-wordmark`), `<title>`
  in `frontend/index.html`, iOS app display name, README/docs headline.
- New mark: flat cat-face badge (round face, notched ears, dot eyes) as inline SVG
  filled with `var(--accent)`, replacing the map-pin logo. Same slot/size in the
  topbar (`mc-logo`).
- Repo rename `waypoint` → `compcat` is a manual GitHub-UI step performed by the
  user after slice 1 merges. Local remotes keep working via GitHub redirects.
- Explicitly unchanged: `MCA_*` env prefix, API paths, `waypoint.*` localStorage
  keys, Python package/module names, database identifiers.

## 2. Theme — "precinct board"

- Token-level change in `frontend/src/styles/mapWorkspace.css` (the `mc-` system)
  plus the root defaults in `styles.css`.
- Accent family blue → stat-green:
  - Dark (new default): accent `#3FBF8F` on graphite chrome (`#12181F` canvas,
    `#1A222B` panels, `#2A3540` borders); accent-deep/soft/halo derived from the
    green.
  - Light (kept): deepened green ≈ `#0F6E56` on today's cool light neutrals so
    text/border contrast holds (WCAG AA on chips, tabs, buttons).
- Dark becomes the default theme for new sessions; a stored user preference still
  wins. The existing ThemeToggle is unchanged.
- Stat chips, verdict counts, and numeric badges use the existing `--f-mono`.
- Map canvas check: identity-pin palette (`--id-a`…`--id-x`) and incident-dot
  colors must remain distinguishable from the green accent in both themes; adjust
  individual values only if they collide (no wholesale repalette).

## 3. Assistant — Copper → Tabby

- Persona rewrite in `app/assistant/prompts.py`: Tabby, CompCat's records clerk —
  same dry, methodical register as Copper, feline instead of hound flavor.
- **All guardrails carry over verbatim**: no safety/risk scores, no ranking places
  as safe/unsafe/dangerous, no claims the user was present at an incident.
- `CopperAvatar.tsx` → `TabbyAvatar.tsx`: new cat artwork, same slot, size, and
  animation hooks; tests renamed alongside.
- Offline copy in `AssistantPanel.tsx` reworded: "Tabby can't reach the case files
  right now. Your data is unaffected — the rest of CompCat works."
- `Copper` references in `app/config.py` renamed. The built bundle under
  `app/static/dashboard/` regenerates on build — no hand-edit.

## 4. Structure — three tabs + chip strip

- Tab bar becomes **Analyze · Compare · Export**; Analyze is the default tab.
- `PlacesTab` is removed as a tab. Its responsibilities relocate:
  - **PlaceChipStrip** (new component) renders at the top of Analyze and Compare:
    one chip per saved place — identity letter + identity color + display label.
    Click toggles the place in/out of `selected`; hover fires the existing
    pin-hover sync callback.
  - Trailing **+ Add** chip opens the existing modal (PlaceForm / Bulk CSV /
    Upload panes unchanged, including the drop-a-pin entry).
  - A **Manage** view inside that modal hosts the current place list with
    rename/delete (the list UI relocated from PlacesTab, not rebuilt).
- Selection state, identity indexing, and map-pin rendering in `MapWorkspace.tsx`
  are unchanged — only the display surface moves.

## 5. Copy sweep

- All user-facing strings and docs: Waypoint → CompCat; remove residual
  navigation/journey framing (the routing goal is retired).
- Guardrail: CompStat connotes police performance statistics. Copy must not drift
  toward scoring, ranking, or performance claims. The product invariant —
  *reported-incident context only; never safety scores, never presence claims* —
  stays word-for-word in CLAUDE.md, docs, and the assistant prompt.

## 6. Out of scope / follow-ups

- "Analysis greets you on load" (auto-run analysis for saved places so first
  paint shows verdicts): next slice after this ships, building on the chip strip.
- No backend or API-tier changes anywhere in this resurface.
- No `MCA_*`/localStorage/package identifier renames (decided against).

## 7. Slicing and verification

- **Slice 1 — rebrand:** identity + theme + Tabby + copy sweep (§1, §2, §3, §5).
- **Slice 2 — restructure:** three-tab bar + PlaceChipStrip + modal manager (§4).
- Each slice: dedicated worktree, `make test-all` (pytest + ruff + npm test +
  build) before PR; user squash-merges.
- Test updates land with their slice: renamed strings ("Waypoint"/"Copper") in
  slice 1; PlacesTab-removal fallout plus new PlaceChipStrip tests (chip toggle,
  add-modal open, hover-sync callback, manage rename/delete) in slice 2.
