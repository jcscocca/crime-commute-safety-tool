# CompCat Rebrand (Slice 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebrand Waypoint → CompCat: new name/mark, dark-first "precinct board" theme (graphite + stat-green), Copper → Tabby assistant persona, and a copy sweep — no structural or API changes.

**Architecture:** Presentation-layer only. Theme is a token swap in the two CSS files that define the `mc-` design system; the assistant persona is one system-prompt string plus one avatar component; identity is a handful of strings. Spec: `docs/superpowers/specs/2026-07-13-compcat-resurface-design.md` (this plan is slice 1; the 3-tab restructure is slice 2, planned separately).

**Tech Stack:** React + TypeScript + Vite (frontend, vitest), FastAPI (backend, pytest), plain CSS custom properties for theming.

**Worktree:** Do this work in a dedicated worktree, not the main checkout (repo convention). Worktrees need two symlinks (`.venv`, `frontend/node_modules`) — see Task 0. Note: `npm run build` writes to `app/static/dashboard/` (vite `outDir`), which is committed — expect a bundle diff in the final commit.

**Verification gate:** `make test-all` (pytest + ruff + frontend `npm test` + `npm run build`) must pass before the PR.

---

### Task 0: Worktree setup

**Files:** none (environment)

- [ ] **Step 1: Create the worktree and symlinks**

```bash
cd /Users/jscocca/Repos/waypoint
git worktree add ../waypoint-compcat-rebrand -b compcat-rebrand-slice1 origin/main
cd ../waypoint-compcat-rebrand
ln -s /Users/jscocca/Repos/waypoint/.venv .venv
ln -s /Users/jscocca/Repos/waypoint/frontend/node_modules frontend/node_modules
echo ".venv" >> .git/info/exclude 2>/dev/null || true
```

(The worktree's `.git` is a file, not a dir — if the `info/exclude` append fails, use `git rev-parse --git-path info/exclude` to find the real path. The symlink form dodges the dir-form gitignore either way, so a failure here is non-blocking.)

- [ ] **Step 2: Sanity-check the toolchain**

```bash
cd /Users/jscocca/Repos/waypoint/../waypoint-compcat-rebrand
.venv/bin/python -m pytest -q -x tests -k "internal_surface" && (cd frontend && npx vitest run src/lib/useTheme.test.ts)
```

Expected: both pass. If pytest fails with a shebang/venv error, the venv needs recreating in the MAIN checkout (`rm -rf .venv && make install`) — known gotcha.

All subsequent tasks run inside `../waypoint-compcat-rebrand`.

---

### Task 1: Dark-first theme default

New sessions open in dark; a stored `wp-theme` choice still wins. The OS-scheme fallback and its change-listener are removed (dark is the brand default now, not a proxy for the OS).

**Files:**
- Modify: `frontend/src/lib/useTheme.ts`
- Test: `frontend/src/lib/useTheme.test.ts`

- [ ] **Step 1: Rewrite the test file to specify dark-first behavior**

Replace the entire contents of `frontend/src/lib/useTheme.test.ts` with:

```tsx
// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useTheme } from "./useTheme";

beforeEach(() => localStorage.clear());
afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
});

describe("useTheme", () => {
  it("defaults to dark when nothing is stored", () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("prefers the stored explicit choice over the dark default", () => {
    localStorage.setItem("wp-theme", "light");
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("persists an explicit choice and applies the attribute", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("light"));
    expect(localStorage.getItem("wp-theme")).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("ignores garbage stored values and falls back to dark", () => {
    localStorage.setItem("wp-theme", "sepia");
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("dark");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/useTheme.test.ts`
Expected: FAIL — "defaults to dark when nothing is stored" gets `light` (jsdom has no `matchMedia`, so the old `osTheme()` returns light).

- [ ] **Step 3: Implement dark-first in useTheme.ts**

Replace the entire contents of `frontend/src/lib/useTheme.ts` with:

```tsx
import { useCallback, useEffect, useState } from "react";

export type ThemeName = "light" | "dark";
const STORAGE_KEY = "wp-theme";

function stored(): ThemeName | null {
  const value = localStorage.getItem(STORAGE_KEY);
  return value === "light" || value === "dark" ? value : null;
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeName>(() => stored() ?? "dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const setTheme = useCallback((next: ThemeName) => {
    localStorage.setItem(STORAGE_KEY, next);
    setThemeState(next);
  }, []);

  return { theme, setTheme };
}
```

(Deliberately removed: `osTheme()` and the `matchMedia` change-listener effect. The `wp-theme` storage key is intentionally unchanged — identifier renames are out of scope.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/useTheme.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: Check nothing else consumed the removed pieces, then run the full frontend suite**

```bash
grep -rn "osTheme\|prefers-color-scheme" frontend/src --include="*.ts" --include="*.tsx"
cd frontend && npx vitest run
```

Expected: grep finds nothing outside CSS files; vitest fully green. (If `App.test.tsx` or `MapWorkspace.test.tsx` assumed a light default, fix those assertions to expect `data-theme="dark"` — but they assert on content, not theme, so no change is expected.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/useTheme.ts frontend/src/lib/useTheme.test.ts
git commit -m "feat(theme): dark is the default theme for new sessions"
```

---

### Task 2: Precinct-board tokens (stat-green on graphite)

Pure token swap. Light theme keeps today's cool neutrals but moves the accent family to a deep stat-green; dark theme gets graphite surfaces + brighter stat-green. No selector or layout changes.

**Files:**
- Modify: `frontend/src/styles/mapWorkspace.css` (light block ~lines 1–21, dark block ~lines 556–567)
- Modify: `frontend/src/styles.css` (`:root` + `[data-theme="dark"]`, lines 1–9)

- [ ] **Step 1: Swap the light accent family in mapWorkspace.css**

In the `.mc-scope{...}` block at the top, replace these two lines:

```css
  --accent:#0B6E99; --accent-deep:#095A7E;
  --accent-soft:rgba(11,110,153,.10); --accent-halo:rgba(11,110,153,.30);
```

with:

```css
  --accent:#0F6E56; --accent-deep:#0A5443;
  --accent-soft:rgba(15,110,86,.10); --accent-halo:rgba(15,110,86,.30);
```

Every other light token (surfaces, borders, text, danger, ok, slate, graphite) stays.

- [ ] **Step 2: Swap the dark block to graphite + stat-green**

Replace the token lines inside `[data-theme="dark"] .mc-scope{...}` (currently `--surface:#1B232B; ...` through `--scrim`) so the block reads:

```css
[data-theme="dark"] .mc-scope{
  --surface:#1A222B; --surface-raised:#12181F; --surface-sunken:#232C35;
  --border:#2A3540; --border-strong:#3A4754;
  --text-strong:#E8EDF2; --text:#B9C6D0; --text-dim:#7C8B99;
  --accent:#3FBF8F; --accent-deep:#7FE0BC;
  --accent-soft:rgba(63,191,143,.14); --accent-halo:rgba(63,191,143,.35);
  --on-accent:#0E1519;
  --danger:#F0937B; --danger-soft:rgba(240,147,123,.16);
  --ok:#5BBF87;
  --scrim:rgba(0,0,0,0.25);
  color-scheme:dark;
}
```

(Only surfaces/borders/accents change vs. today; text, danger, ok, scrim are carried over as-is. `--accent-deep` is the LIGHTER green here — same inversion the blue theme used, since dark-mode "deep" tokens are used for emphasized text.)

- [ ] **Step 3: Align the page background in styles.css**

In `frontend/src/styles.css` line 9, change the dark background to match the new graphite canvas:

```css
[data-theme="dark"]{color-scheme:dark;color:#E8EDF2;background:#12181F;--id-a:#6E64D9;}
```

(Light `:root` background `#EEF2F5` is unchanged.)

- [ ] **Step 4: Check identity-pin separation from the new accent**

The identity palette (`--id-a` purple, `--id-b` green `#1D9E75`, `--id-c` orange, `--id-d` blue, `--id-x` slate in `styles.css:7`) now has `--id-b` too close to the new green accents. A cyan/blue replacement would collide with `--id-d`, so keep `--id-b` green but push it lighter/yellower (leaf-green) so it separates from both the light accent `#0F6E56` and the dark accent `#3FBF8F`. In `styles.css:7`, change only the `--id-b` value:

```css
  --id-a:#534AB7;--id-b:#4CAF3F;--id-c:#C2410C;--id-d:#2E7DD1;--id-x:#74858E;
```

- [ ] **Step 5: Build and eyeball both themes**

```bash
cd frontend && npx vitest run && npm run build
```

Expected: tests green, build clean. Then from the MAIN checkout (Claude Preview is anchored there — verify visually after merge; in the worktree, rely on tests/build) or via `make dev` in the worktree if ports are free: open the app, toggle light/dark, confirm chrome is graphite, accents green, incident dots and A–E pins distinguishable in both themes.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/styles/mapWorkspace.css frontend/src/styles.css
git commit -m "feat(theme): precinct-board palette - graphite chrome + stat-green accent"
```

---

### Task 3: TabbyAvatar replaces CopperAvatar

Same component API (`variant: "mark" | "bust"`, `size`, `className`), new cat artwork, new file name. The pulse animation class renames `mc-copper-pulse` → `mc-tabby-pulse`.

**Files:**
- Create: `frontend/src/components/TabbyAvatar.tsx`
- Create: `frontend/src/components/TabbyAvatar.test.tsx`
- Delete: `frontend/src/components/CopperAvatar.tsx`, `frontend/src/components/CopperAvatar.test.tsx`
- Modify: `frontend/src/components/AssistantPanel.tsx` (import at line 6, usages at 118, 156)
- Modify: `frontend/src/styles/mapWorkspace.css` (lines 104–105 keyframes/class, line 317 reduced-motion list)

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/TabbyAvatar.test.tsx`:

```tsx
// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TabbyAvatar } from "./TabbyAvatar";

afterEach(cleanup);

describe("TabbyAvatar", () => {
  it("renders the decorative mark at the requested size", () => {
    const { container } = render(<TabbyAvatar variant="mark" size={20} />);
    const svg = container.querySelector('svg[data-variant="mark"]');
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).toHaveAttribute("width", "20");
    expect(svg).toHaveAttribute("height", "20");
  });

  it("renders the bust variant and forwards className", () => {
    const { container } = render(
      <TabbyAvatar variant="bust" size={72} className="mc-tabby-pulse" />,
    );
    const svg = container.querySelector('svg[data-variant="bust"]');
    expect(svg).not.toBeNull();
    expect(svg).toHaveClass("mc-tabby-pulse");
    expect(svg).toHaveAttribute("width", "72");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/components/TabbyAvatar.test.tsx`
Expected: FAIL — cannot resolve `./TabbyAvatar`.

- [ ] **Step 3: Create the component**

Create `frontend/src/components/TabbyAvatar.tsx`. Same warm palette family as Copper (fur `#b5793f`, shadow `#6b4520`, stripes `#8a5a2e`, muzzle `#e2c495`) so the assistant still reads as the same desk, different species; green eyes nod to the new accent.

```tsx
type Props = {
  variant: "mark" | "bust";
  size?: number;
  className?: string;
};

const HEAD = (
  <>
    <path d="M31 50 L26 20 L54 34 Z" fill="#b5793f" />
    <path d="M89 50 L94 20 L66 34 Z" fill="#b5793f" />
    <path d="M34 44 L31 27 L48 36 Z" fill="#6b4520" />
    <path d="M86 44 L89 27 L72 36 Z" fill="#6b4520" />
    <circle cx="60" cy="62" r="30" fill="#b5793f" />
    <path d="M53 34 Q54 41 52 46" stroke="#8a5a2e" strokeWidth="3.4" fill="none" strokeLinecap="round" />
    <path d="M60 33 L60 45" stroke="#8a5a2e" strokeWidth="3.4" strokeLinecap="round" />
    <path d="M67 34 Q66 41 68 46" stroke="#8a5a2e" strokeWidth="3.4" fill="none" strokeLinecap="round" />
    <path d="M32 56 L41 58" stroke="#8a5a2e" strokeWidth="3" strokeLinecap="round" />
    <path d="M88 56 L79 58" stroke="#8a5a2e" strokeWidth="3" strokeLinecap="round" />
    <circle cx="49" cy="58" r="3.6" fill="#2f6c4f" />
    <circle cx="71" cy="58" r="3.6" fill="#2f6c4f" />
    <circle cx="49" cy="58" r="1.5" fill="#1c1c1a" />
    <circle cx="71" cy="58" r="1.5" fill="#1c1c1a" />
    <ellipse cx="60" cy="72" rx="12" ry="9" fill="#e2c495" />
    <path d="M56.5 68.5 L63.5 68.5 L60 73 Z" fill="#8a4b3a" />
    <path d="M60 73 Q60 77 55 77.5" stroke="#6b4520" strokeWidth="1.6" fill="none" strokeLinecap="round" />
    <path d="M60 73 Q60 77 65 77.5" stroke="#6b4520" strokeWidth="1.6" fill="none" strokeLinecap="round" />
    <path d="M47 70 Q39 68 32 67" stroke="#e2c495" strokeWidth="1.5" fill="none" strokeLinecap="round" />
    <path d="M47 74 Q39 75 33 76" stroke="#e2c495" strokeWidth="1.5" fill="none" strokeLinecap="round" />
    <path d="M73 70 Q81 68 88 67" stroke="#e2c495" strokeWidth="1.5" fill="none" strokeLinecap="round" />
    <path d="M73 74 Q81 75 87 76" stroke="#e2c495" strokeWidth="1.5" fill="none" strokeLinecap="round" />
  </>
);

const MARK = HEAD;

const BUST = (
  <>
    <path d="M28 102 Q34 84 48 80 L60 86 L72 80 Q86 84 92 102 Z" fill="#9c6630" />
    <polygon points="60,86 54,93 60,100 66,93" fill="#e2c495" />
    <path d="M47 82 Q60 91 73 82 L73 87 Q60 96 47 87 Z" fill="#2f6c4f" />
    <circle cx="60" cy="93" r="3.2" fill="#d9b036" />
    {HEAD}
  </>
);

export function TabbyAvatar({ variant, size = 20, className }: Props) {
  return (
    <svg
      data-variant={variant}
      className={className}
      width={size}
      height={size}
      viewBox="0 0 120 120"
      aria-hidden="true"
      focusable="false"
    >
      {variant === "mark" ? MARK : BUST}
    </svg>
  );
}
```

(The bust draws shoulders + green collar with a brass tag first, then overlays the same head — unlike Copper, no second set of shifted coordinates to maintain.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/TabbyAvatar.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Swap usages in AssistantPanel and rename the pulse class**

In `frontend/src/components/AssistantPanel.tsx`:
- Line 6: `import { CopperAvatar } from "./CopperAvatar";` → `import { TabbyAvatar } from "./TabbyAvatar";`
- Line 118: `<CopperAvatar variant="mark" size={20} className={greeted ? undefined : "mc-copper-pulse"} />` → `<TabbyAvatar variant="mark" size={20} className={greeted ? undefined : "mc-tabby-pulse"} />`
- Line 156: `<CopperAvatar variant="bust" size={72} />` → `<TabbyAvatar variant="bust" size={72} />`

In `frontend/src/styles/mapWorkspace.css`:
- Lines 104–105: rename `@keyframes copper-pulse` → `@keyframes tabby-pulse` and `.mc-copper-pulse{animation:copper-pulse ...}` → `.mc-tabby-pulse{animation:tabby-pulse ...}`
- Line 317 (reduced-motion list): `.mc-copper-pulse` → `.mc-tabby-pulse`

- [ ] **Step 6: Delete the old component and verify no references remain**

```bash
git rm frontend/src/components/CopperAvatar.tsx frontend/src/components/CopperAvatar.test.tsx
grep -rn "CopperAvatar\|copper-pulse" frontend/src
```

Expected: grep finds nothing.

- [ ] **Step 7: Run the frontend suite**

Run: `cd frontend && npx vitest run`
Expected: everything green EXCEPT `AssistantPanel.test.tsx` name assertions ("Copper, case desk…", "shows Copper's header") — those strings are Task 4's job. If only those fail, proceed; Task 4 fixes them.

- [ ] **Step 8: Commit**

```bash
git add -A frontend/src/components frontend/src/styles/mapWorkspace.css
git commit -m "feat(assistant): TabbyAvatar replaces CopperAvatar"
```

---

### Task 4: Assistant strings — Tabby in the panel

**Files:**
- Modify: `frontend/src/components/AssistantPanel.tsx` (lines 18, 119, 157)
- Test: `frontend/src/components/AssistantPanel.test.tsx` (lines ~196, ~215, and any other "Copper"/"Waypoint" literals)

- [ ] **Step 1: Update the test assertions first**

In `frontend/src/components/AssistantPanel.test.tsx`:
- Line ~196: `"Copper, case desk. Point me at a place and I'll pull the reports near it."` → `"Tabby, case desk. Point me at a place and I'll pull the reports near it."`
- Line ~215: test name `"shows Copper's header with the idle status and avatar mark"` → `"shows Tabby's header with the idle status and avatar mark"`
- Search the file for any remaining `Copper` / `Waypoint` literals (e.g. header-name or offline-message assertions) and update to `Tabby` / `CompCat` with the exact strings from Step 3.

- [ ] **Step 2: Run to verify the updated assertions fail**

Run: `cd frontend && npx vitest run src/components/AssistantPanel.test.tsx`
Expected: FAIL on the renamed strings.

- [ ] **Step 3: Update the component strings**

In `frontend/src/components/AssistantPanel.tsx`:
- Line 18: `"Copper can't reach the case files right now. Your data is unaffected — the rest of Waypoint works."` → `"Tabby can't reach the case files right now. Your data is unaffected — the rest of CompCat works."`
- Line 119 (header label): `Copper` → `Tabby`
- Line 157 (greeting): `Copper, case desk. Point me at a place and I'll pull the reports near it.` → `Tabby, case desk. Point me at a place and I'll pull the reports near it.`

- [ ] **Step 4: Run the panel tests, then the full frontend suite**

```bash
cd frontend && npx vitest run src/components/AssistantPanel.test.tsx && npx vitest run
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AssistantPanel.tsx frontend/src/components/AssistantPanel.test.tsx
git commit -m "feat(assistant): Tabby name + copy in the chat panel"
```

---

### Task 5: Backend persona — Tabby prompt

The guardrail lines in the narration prompt are load-bearing (product invariant) and MUST be byte-identical after the edit; only the persona framing changes.

**Files:**
- Modify: `app/assistant/prompts.py` (lines 87–88 and the final "Voice:" line of `NARRATION_SYSTEM_PROMPT`)
- Modify: `app/config.py` (line 38 comment)

- [ ] **Step 1: Check whether any backend test pins the persona text**

```bash
grep -rn "Copper\|records hound\|case-desk" tests/ app/ --include="*.py"
```

Expected: only `app/assistant/prompts.py` and the `app/config.py` comment. If a test asserts on prompt text, update its expected string in the same edit as Step 2.

- [ ] **Step 2: Edit the prompt framing**

In `app/assistant/prompts.py`, change the opening of `NARRATION_SYSTEM_PROMPT`:

```python
NARRATION_SYSTEM_PROMPT = """You are Tabby, CompCat's case-desk analyst — a dry,
methodical records cat. Write the final chat reply to the user's last message.
```

and the closing voice line:

```python
Voice: terse, direct, a records clerk reading from the file."""
```

Every line in between — all seven "Non-negotiable rules" bullets — stays byte-for-byte identical.

- [ ] **Step 3: Update the config comment**

`app/config.py` line 38: `# Streamed Copper narration finals + turn status events.` → `# Streamed Tabby narration finals + turn status events.` (rest of comment unchanged).

- [ ] **Step 4: Run backend tests + lint**

```bash
.venv/bin/python -m pytest -q && .venv/bin/python -m ruff check .
```

Expected: green. (Assistant guard tests exercise the rules text, not the persona name — if one fails, its fixture quoted the old opening line; update the fixture to the new opening.)

- [ ] **Step 5: Commit**

```bash
git add app/assistant/prompts.py app/config.py
git commit -m "feat(assistant): Tabby persona in the narration prompt (guardrails unchanged)"
```

---

### Task 6: Identity — wordmark, mark, titles

**Files:**
- Modify: `frontend/src/components/MapWorkspace.tsx` (lines 368–372: logo SVG + wordmark)
- Modify: `frontend/index.html` (line 6 title)
- Modify: `frontend/src/components/PersonalUpload.tsx` (line 50)
- Modify: `frontend/capacitor.config.ts` (line 9 `appName`)
- Modify: `frontend/capacitor.config.test.ts` (line 16)
- Modify: `frontend/ios/App/App/Info.plist` (line 10 display name)
- Test: `frontend/src/App.test.tsx` (line 41), `frontend/src/components/MapWorkspace.test.tsx` (line 167)

- [ ] **Step 1: Update the brand assertions first**

- `frontend/src/App.test.tsx:41`: `expect(await screen.findByText("Waypoint"))` → `expect(await screen.findByText("CompCat"))`
- `frontend/src/components/MapWorkspace.test.tsx:167`: `expect(screen.getByText("Waypoint"))` → `expect(screen.getByText("CompCat"))`
- `frontend/capacitor.config.test.ts:16`: `expect(config.appName).toBe("Waypoint")` → `expect(config.appName).toBe("CompCat")`

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx vitest run src/App.test.tsx src/components/MapWorkspace.test.tsx capacitor.config.test.ts`
Expected: FAIL on all three brand assertions.

- [ ] **Step 3: Swap the mark and wordmark in the topbar**

In `frontend/src/components/MapWorkspace.tsx`, replace the brand block (currently the map-pin `<svg>` at ~369 and the wordmark at 371):

```tsx
          <div className="mc-brand">
            <span className="mc-logo">
              <svg width="16" height="16" viewBox="0 0 24 24"><path d="M4 9 L4 4 L9 7 Q12 6 15 7 L20 4 L20 9 Q21.5 11.5 21.5 14 Q21.5 20 12 20 Q2.5 20 2.5 14 Q2.5 11.5 4 9 Z" fill="var(--on-accent)" /><circle cx="8.5" cy="13" r="1.3" fill="var(--accent)" /><circle cx="15.5" cy="13" r="1.3" fill="var(--accent)" /></svg>
            </span>
            <span className="mc-wordmark">CompCat</span>
          </div>
```

(The `.mc-logo` chip already has `background:var(--accent)` — the cat face is knocked out in `--on-accent` with accent-colored eyes, so it recolors correctly in both themes.)

- [ ] **Step 4: Remaining identity strings**

- `frontend/index.html:6`: `<title>Waypoint</title>` → `<title>CompCat</title>`
- `frontend/src/components/PersonalUpload.tsx:50`: `Waypoint shows reported-incident context near these places.` → `CompCat shows reported-incident context near these places.` (rest of sentence — "It never claims you were…" — unchanged; that's invariant copy.)
- `frontend/capacitor.config.ts:9`: `appName: "Waypoint",` → `appName: "CompCat",`
- `frontend/ios/App/App/Info.plist:10`: `<string>Waypoint</string>` → `<string>CompCat</string>` (this is `CFBundleDisplayName` — confirm the key on the preceding line before editing).

- [ ] **Step 5: Run the frontend suite**

Run: `cd frontend && npx vitest run`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/MapWorkspace.tsx frontend/index.html frontend/src/components/PersonalUpload.tsx frontend/capacitor.config.ts frontend/capacitor.config.test.ts frontend/ios/App/App/Info.plist frontend/src/App.test.tsx frontend/src/components/MapWorkspace.test.tsx
git commit -m "feat(brand): CompCat wordmark, cat mark, app titles"
```

---

### Task 7: Copy sweep — README, CLAUDE.md, docs index

Scope guard: historical files under `docs/superpowers/specs/` and `docs/superpowers/plans/` are NOT rewritten — they're a dated record. GitHub badge/repo URLs stay `jcscocca/waypoint` for now (the repo rename is a post-merge manual step; GitHub redirects will keep them working, and URLs can be tidied later).

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `docs/README.md` (+ any other current docs found by grep)

- [ ] **Step 1: Sweep the name in current docs**

In `README.md`: `# Waypoint` → `# CompCat`, and each prose `Waypoint` → `CompCat`. Add one line under the heading: `*CompCat — a pun on CompStat. Formerly Waypoint.*` Leave all URLs untouched.

In `CLAUDE.md`: heading `# Waypoint — agent guide` → `# CompCat — agent guide`; prose `Waypoint is a privacy-first…` → `CompCat is a privacy-first…`; the **Product invariant** section keeps its wording exactly, with only the product-name token swapped (`Waypoint reports *reported incident context*` → `CompCat reports *reported incident context*`).

In `docs/README.md`: same name-token swap in headings/prose.

Then find stragglers in current (non-historical) docs and swap name tokens where they refer to the product:

```bash
grep -rln "Waypoint" docs --include="*.md" | grep -v "docs/superpowers"
```

(Expect `ROADMAP.md`, `DEPLOY.md`, `DEMO.md`, `IOS.md`, `docs/architecture/*`, `docs/reference/*` — sweep prose names; leave code identifiers like `waypoint.search.recent`, env examples, and file paths alone.)

- [ ] **Step 2: Audit — no user-facing "Waypoint"/"Copper" left in source**

```bash
grep -rn "Waypoint\|Copper" frontend/src app --include="*.ts" --include="*.tsx" --include="*.py" | grep -v "app/static/dashboard"
grep -rn "waypoint" frontend/src --include="*.ts" --include="*.tsx" | grep -v test
```

Expected: first grep returns nothing. Second returns ONLY the intentional identifier keys (`waypoint.search.recent` in `searchHistory.ts`, `waypoint.drawer.*` in `drawerStorage.ts`) — these stay (out of scope by design).

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md docs
git commit -m "docs: CompCat name sweep (historical specs/plans left as record)"
```

---

### Task 8: Verification gate + PR

- [ ] **Step 1: Full gate**

Run from the worktree root: `make test-all`
Expected: pytest ✓, ruff ✓, frontend vitest ✓, `npm run build` ✓. The build regenerates `app/static/dashboard/` — the new bundle (now saying CompCat/Tabby) is part of this slice.

- [ ] **Step 2: Commit the regenerated bundle (if the build changed it)**

```bash
git status --short app/static/dashboard
git add app/static/dashboard && git commit -m "chore(build): regenerate dashboard bundle for CompCat rebrand" || echo "bundle unchanged"
```

- [ ] **Step 3: Visual spot-check**

Run `make dev` (or the preview harness from the main checkout after merge) and confirm: dark loads by default; graphite chrome + green accents; CompCat wordmark + cat badge; Tabby name, avatar, and greeting in the chat dock; light theme still legible via the toggle.

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin compcat-rebrand-slice1
gh pr create --title "feat(brand): CompCat rebrand — precinct theme + Tabby persona (slice 1)" --body "$(cat <<'EOF'
Slice 1 of the CompCat resurface (spec: docs/superpowers/specs/2026-07-13-compcat-resurface-design.md).

- Waypoint → CompCat: wordmark, cat mark, page/app titles, docs sweep (historical specs untouched)
- Precinct-board theme: dark-first default (stored preference still wins), graphite chrome + stat-green accent, light theme kept
- Copper → Tabby: persona reframe in the narration prompt (all guardrail lines byte-identical), new TabbyAvatar, panel copy
- Out of scope (slice 2): 3-tab restructure + place chip strip. No API, env, or storage-key changes.

Post-merge manual step: rename the GitHub repo to `compcat` (Settings → General); redirects cover old URLs.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR opens; user squash-merges per repo cadence.
