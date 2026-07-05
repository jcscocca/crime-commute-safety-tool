# Shell Overhaul (Slice 3 of Map & UI Overhaul) — design

**Date:** 2026-07-05 · **Status:** SHIPPED (2026-07-05)
**Parent:** `docs/superpowers/specs/2026-07-04-map-ui-overhaul-design.md` (Slice 3 section — this doc
supersedes and details it; decisions re-confirmed with the user 2026-07-05).

## Why

The map became Civic Clear in slices 1–2, but the shell around it is still the old warm
"Field Atlas" chrome: dark clay-toned translucent panels, a floating unexplained Analyst box
bottom-left, an orphaned Add Pin button top-left, Fraunces/Google-Fonts typography, and no
dark mode. This slice delivers the visual language and layout the app was redesigned for.

## Decisions (user-confirmed)

| Decision | Choice |
|---|---|
| Scope | **Full Evolved Workspace restructure** + full Civic Clear re-theme + night mode + self-hosted fonts, one slice |
| Accent | **Confident blue `#0B6E99`** (light) / **`#4FB3D9`** (dark — `#0B6E99` fails contrast on dark surfaces). The clay identity is retired from the UI chrome. |
| Sequencing | **Theme foundation first, then layout** — the app is fully usable in both themes mid-branch; layout work styles against final tokens, never twice |
| Data marks | Dots/clusters stay **graphite `#3A3F46`** and beat lines **slate `#74858E`** in BOTH themes — the accent never touches data marks (a blue dot next to a blue selection would read as meaning) |

## Stage 1 — Theme foundation (layout untouched)

### Semantic tokens
Rewrite the `.mc-scope` custom-property block (`frontend/src/styles/mapWorkspace.css:1-18`)
from named colors (`--clay`, `--paper`, `--ink`, `--text`…) to semantic tokens:

| Token | Light | Dark (`[data-theme="dark"]`) |
|---|---|---|
| `--surface` | `#FFFFFF` | `#1B232B` |
| `--surface-raised` | `#F6F9FA` | `#151C23` |
| `--surface-sunken` | `#EEF2F5` | `#232C35` |
| `--border` | `#D5DEE4` | `#2C3742` |
| `--border-strong` | `#C3CFD8` | `#3A4754` |
| `--text-strong` | `#16232B` | `#E8EDF2` |
| `--text` | `#3D4C57` | `#B9C6D0` |
| `--text-dim` | `#8A99A3` | `#7C8B99` |
| `--accent` | `#0B6E99` | `#4FB3D9` |
| `--accent-deep` | `#095A7E` | `#7BC8E4` |
| `--accent-soft` | `rgba(11,110,153,.10)` | `rgba(79,179,217,.14)` |
| `--graphite` (data marks) | `#3A3F46` | `#3A3F46` |
| `--slate` (beat lines) | `#74858E` | `#74858E` |

Layout vars (`--panel-width`, `--panel-rail`) and their narrow-viewport overrides carry over
unchanged. The survey found many rules hardcode hexes instead of tokens — the rewrite sweeps
every color in `mapWorkspace.css` into tokens (exact values may be tuned during the token
sweep, but every color goes through a token; no hardcoded hex survives outside the token
block and the map-data constants). Dark values apply via `[data-theme="dark"]` scoped
overrides of the same custom properties — components never branch on theme.

`frontend/src/styles.css` (legacy `:root` Inter scope styling the PlaceForm/BulkPlaceEntry
modals and Notice, teal-accented) folds into the same system: its `:root` block is replaced
by the shared tokens (fonts included), and its teal accents become `--accent`, so the modals
theme correctly. One theme system, two files at most (or merged — implementer's call at plan
time, smallest coherent diff wins).

### Theme state
- `frontend/src/lib/useTheme.ts`: `theme: "light" | "dark"`; initial value = `localStorage`
  `wp-theme` if set, else `prefers-color-scheme: dark` ? dark : light; `setTheme` persists to
  localStorage and sets `data-theme` on `document.documentElement`. Listens for OS scheme
  changes only while no explicit choice is stored.
- `ThemeToggle` component in the topbar: sun/moon icon button, `aria-pressed` +
  `aria-label="Switch to dark theme"`/`"…light theme"`.
- MapCanvas gains a required `theme: MapTheme` prop. On change it calls
  `map.setStyle(buildMapStyle(theme, origin))` (or themed fallback/Carto variants).

### Map layer re-registration (slice-2 carry-in)
`setStyle()` wipes the beat/ring/incident layers and `"load"` does not re-fire (documented at
`MapCanvas.tsx` above `addRingLayers`). Therefore:
- Extract `addBeatLayers`, `addRingLayers`, `addIncidentLayers`, `incidentCardElement`, and
  the source-id constants from `MapCanvas.tsx` (451 lines) into
  `frontend/src/lib/mapLayers.ts` with one entry point `registerDataLayers(map)`.
- MapCanvas listens for `style.load` after every `setStyle` and calls
  `registerDataLayers(map)` followed by re-feeding current data (beats, rings, incident
  points, highlight filter) from the existing effect state. The initial `load` path and the
  swap path share this code.

### Self-hosted fonts
- Commit latin-subset woff2 files to `frontend/public/fonts/`: Archivo 400/500/600/700,
  IBM Plex Mono 400/500 (~150 KB total; both OFL — include the license file). These are
  committed to git (small, licensed), unlike the gitignored tile artifacts.
- `@font-face` rules with `font-display: swap`; `--f-ui`/`--f-mono` unchanged as var names.
- **Fraunces is dropped** — `--f-display` deleted; the `.mc-wordmark` becomes Archivo 700.
- Remove the three Google-Fonts `<link>` tags from `frontend/index.html`. After this the app
  makes **zero external requests**.
- Guard test (privacy): assert `frontend/index.html` contains no `fonts.googleapis.com` /
  `fonts.gstatic.com` / other external hosts (same spirit as the map-style no-external-hosts
  guard).

## Stage 2 — Layout restructure (Evolved Workspace)

### Search pill (top-left)
New persistent control replacing `.mc-controls`/`.mc-addpin`:
- Pill: "Search address or drop a pin". Input drives the existing `useAddressSearch`
  debounced geocode; selecting a result routes through the existing `handleLookup`
  (fly-to + single-address context on the Analyze tab).
- A pin-icon button inside the pill arms the existing `usePinDraft.startAddPin()`
  click-to-place mode. The armed helper hint ("Click the map to drop a pin — Esc to cancel")
  and Esc-cancel behavior are unchanged.
- The fresh-session `AddressLookup` landing inside the panel **stays** (approved phase-5C
  first-run flow), and the Places tab's scoped add-a-place search stays — all three share
  the existing handlers; no duplicated fetch logic.

### Analyst dock (in-panel)
`AssistantPanel` moves from the floating bottom-left card into the workspace panel's lower
section. The panel (`BottomSheet`) becomes a flex column: tab bar / tab body (scrolls) /
Analyst dock.
- Dock: always visible, titled header ("Analyst" + status), collapsible to header-only
  (component state, default expanded).
- Empty state: one-line explainer ("Ask about what the map is showing") plus two
  quick-action chips — "What's near this pin?" and "Compare my places" — that **send** the
  canned prompt through the existing SSE chat with the current dashboard state (one click =
  action, not prefill).
- SSE wiring, tool-result fan-out (`onToolResult` → `applyAssistantToolResult`), markdown
  rendering, error + Retry all unchanged. Aria labels ("Analyst message", "Send", "Retry")
  preserved so existing assistant tests survive.
- The `.mc-assistant` floating CSS dies.

### Topbar & bottom-right cluster
- Topbar: brand left (pin glyph in `--accent`, wordmark Archivo 700); right: `LayerToggle`,
  `DataFreshness`, session chip, `ThemeToggle`.
- Legend moves top-left → bottom-right, stacked above the attribution (panel-aware inset —
  the `.mc-attrib` `right:calc(var(--panel-width) + …)` pattern), joined by a MapLibre
  `NavigationControl` (zoom only, no compass) in the same corner cluster.
- Disclosure chip stays bottom-center; error/shared-view banners unchanged; mobile
  narrow-viewport `--panel-width`/`--panel-rail` overrides carry over.

## Invariant guards

- Copy: no new user-facing strings beyond the dock explainer, chip labels, and theme-toggle
  aria labels — all neutral; the output-guard vocabulary sweep applies to them.
- The accent never colors incident dots, clusters, beat lines, or any data mark — those stay
  graphite/slate in both themes. Selection/UI state is the only blue.
- Night mode changes surfaces, not meaning: the redaction disclosure, freshness pill, and
  "reported incidents" framing render identically in both themes.

## Accessibility

- Token pairs meet WCAG AA for text in both themes (checked at plan time with a contrast
  matrix over the table above; adjust values not semantics if a pair fails).
- ThemeToggle: `aria-pressed`, descriptive label, visible focus ring both themes.
- Dock collapse button: `aria-expanded`. Focus rings audited on dark surfaces.

## Testing & rollout

- Unit: `useTheme` (localStorage precedence, prefers fallback, OS-change listener gating),
  ThemeToggle, `mapLayers.registerDataLayers` (mocked map: layers re-added after a simulated
  `style.load`; data re-fed), SearchPill (result select → lookup handler; pin button arms
  draft mode), dock (chips send canned prompts with dashboard state; collapse toggles),
  no-external-fonts guard.
- Updates: the class-coupled assertions flagged in the survey (`MapWorkspace.test.tsx`
  `.mc-frame`/`.mc-workspace-panel`/stale `.mc-sheet`; `BottomSheet.test.tsx` panel classes;
  `mapWorkspaceStyle.test.ts` selector/token renames). Role/label-based assertions should
  largely survive by design.
- `make test-all` green per task; no migrations; frontend-only (zero backend changes).
- Live verification (final task): both themes screenshotted; **toggle night mode while dots +
  beat outlines + a ring are on screen** (proves re-registration); popup/chip/legend contrast
  in dark; fonts render from `/fonts/` with a network audit expecting **zero external
  requests app-wide**; pin-drop and lookup flows through the new pill; dock chips fire the
  assistant; mobile-width pass.
- After landing: roadmap Phase 6 slice-3 tick; the deferred coalesce expression index and
  Postgres soak notes remain open items elsewhere.

## Out of scope (recorded)

- Assistant behavior changes (routing, prompts, latency) — the dock relocates the same chat.
- The "Command Deck" bottom-bar promotion — recorded as a possible future evolution if local
  LLM latency improves materially.
- Additional geographic layers, per-category dot filtering, heatmaps (rejected — invariant).
- Any backend change.

## Shipped deviations (verified during build)

- Backend touched after all: a `/fonts` StaticFiles mount in `app/main.py` (vite dev masks
  missing prod mounts — same seam as the slice-2 glyphs bug) + a pinning test in
  `tests/test_tiles_static.py`. The "zero backend changes" line was wrong by one mount.
- Archivo ships as ONE variable font (`archivo-var.woff2`, `font-weight:100 900`) instead of
  four fixed weights — css2 serves a variable file; also fixes 650/750 weights the fixed faces
  couldn't interpolate.
- New `--on-accent` token (light `#fff`, dark `#10181F`) — the plan's `#fff`-on-accent failed
  AA on the dark accent `#4FB3D9`; `--text-dim` light darkened to `#64747F` for AA.
- Analyzed-ring paint is theme-aware in `mapLayers.ts` (`#4FB3D9` dark / `#0B6E99` light,
  literal hexes — canvas paint can't read CSS vars). Accent-colored selection marks are UI
  state, allowed by the invariant (data marks stay graphite/slate).
- SearchPill results list `z-index:1101`; legend `bottom:100px` (the plan's 64px collided with
  the zoom/attribution cluster); topbar right edge inset by `--panel-width` (was occluded by
  the panel).
- Known eyeball items accepted: sub-second basemap blink on theme toggle (setStyle diff
  repaint; revisit with `transformStyle` if it reads janky on deploy); colorful POI icons
  visible in the dark basemap style but not light (slice-1 style artifact — follow-up);
  disclosure chip can overlap attribution when the panel is WIDE on narrow desktops; mobile
  dock max-heights (44vh/200px) unscaled; log auto-scroll absent (pre-existing).
