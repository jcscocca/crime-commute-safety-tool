# iOS shell + Tailscale reachability — "Waypoint in my pocket", Slice A

**Date:** 2026-07-10
**Status:** approved design, pre-implementation
**Parent effort:** Waypoint on iOS (personal device + demos), decomposed into:
Slice A (this spec) → Slice B (phone-first redesign, own brainstorm/spec) → Slice C
(niceties: haptics, share sheet, offline screen — parked).

## Goal

Waypoint launches from the user's iPhone home screen as a real app and works anywhere —
full-fidelity (map, layers, compare, Copper), talking to the personal instance on the
ThinkPad over Tailscale. No Apple review, no public hosting, no frontend rewrite.

## Decision trail (brainstorm answers)

| Question | Decision |
|---|---|
| Launch target | Personal device + demos (no App Store / TestFlight) |
| Motive | Full-fidelity "Waypoint in my pocket" — reuse the React app |
| Backend reach | Tailscale; ThinkPad + iPhone on the same tailnet |
| v1 mobile UX | Full phone redesign chosen — but split out as **Slice B**; this slice ships the shell |
| Shell approach | **Capacitor remote-URL mode** over bundled-frontend (CORS/skew) and bare WKWebView (no plugin path) |
| Ordering | A (shell) before B (redesign) — on-device feedback loop for B |

## 1. Architecture

A Capacitor iOS shell whose WKWebView loads the frontend **from the backend origin**
over the tailnet:

```
iPhone (Tailscale on)                    ThinkPad (tailnet)
┌───────────────────────┐   HTTPS        ┌──────────────────────────────┐
│ Waypoint.app          │  ─────────────▶│ tailscale serve :443         │
│  └ WKWebView          │  <hostname>.   │   └ proxy → 127.0.0.1:8000   │
│     (remote URL,      │  <tailnet>     │      └ uvicorn (personal     │
│      same-origin SPA) │  .ts.net       │         compose instance)    │
└───────────────────────┘                └──────────────────────────────┘
```

Consequences, all inherited for free because the origin is the backend itself:

- **Same-origin everything** — no CORS, no cookie changes. The session cookie
  (`credentials: "include"` fetches) lives in WKWebView's persistent store, so identity
  and saved places survive relaunches exactly like a browser profile.
- **SSE unchanged** — Copper's `/assistant/chat` stream rides the same proxied origin.
- **No ATS exceptions** — one HTTPS origin with a real Let's Encrypt cert
  (provisioned by `tailscale serve`); Waypoint serves its own map tiles, so there are
  no third-party hosts at all.
- **No version skew** — the phone always runs whatever the ThinkPad serves; shipping
  frontend changes to the app is `git pull` on the ThinkPad.
- **Private by construction** — `tailscale serve` is tailnet-only; nothing is exposed
  publicly. The demo-on-demand posture and rate limiter are untouched.

Runtime dependency: the Tailscale iOS app must be connected. Accepted.

## 2. Repo changes

- **`frontend/capacitor.config.ts`** — `server.url` read from `MCA_IOS_SERVER_URL` at
  `cap sync` time, with placeholder default `https://waypoint.example.ts.net`. The real
  tailnet hostname is never committed (public repo). `webDir` points at the built
  dashboard output solely to satisfy `cap sync`.
- **`frontend/ios/`** — committed Capacitor/Xcode platform project (standard convention;
  contains no secrets). Bundle id `com.jscocca.waypoint`, display name "Waypoint".
- **Branding** — app icon + splash generated with `@capacitor/assets` from a 1024×1024
  PNG of the Copper noir bust on the brand background, rendered from the existing
  `CopperAvatar` SVG paths by a small repo script (`scripts/render_ios_icon.mjs`). Copper
  is the home-screen icon.
- **`frontend/package.json`** — devDependencies `@capacitor/core`, `@capacitor/cli`,
  `@capacitor/ios`, `@capacitor/assets`; scripts `ios:sync` (build + `cap sync ios`) and
  `ios:open` (`cap open ios`).
- **`docs/IOS.md`** — ThinkPad `tailscale serve` setup, `MCA_IOS_SERVER_URL` usage,
  Xcode signing/run steps (free Apple ID = 7-day re-sign cycle; paid account = 1 year),
  troubleshooting (tailnet off → system error page).
- **CI safety** — `make test-all` must stay green: Capacitor packages are
  devDependencies; verify `tsc -b`/vitest don't sweep `capacitor.config.ts` or `ios/`
  (tsconfig include scope), and `npm run build` output is unchanged.

## 3. Shell minimalism (deliberate)

- Status bar style + shell background matched to the app theme; **no**
  `env(safe-area-inset-*)` layout work — that belongs to Slice B's phone-first redesign.
- Unreachable backend / tailnet off → system WKWebView error page. A friendly offline
  screen is Slice C.
- No push, no geolocation, no native plugins beyond splash/status-bar in this slice.

## 4. Out of scope

- Slice B: phone-first redesign of the React UI (navigation model, per-tab phone
  layouts, keyboard/safe-area/gesture work) — separate brainstorm → spec → plan.
- Slice C niceties: haptics, share-sheet exports, offline screen, app shortcuts.
- App Store / TestFlight distribution, bundled-frontend mode, auth hardening for public
  exposure — all unneeded for the device+demos target.

## 5. Verification

Repo side: `make test-all` green; a unit test pins `capacitor.config.ts`'s env-var
fallback (placeholder URL when `MCA_IOS_SERVER_URL` is unset, override when set).

On-device checklist (documented in `docs/IOS.md`, executed manually):

1. Cold boot on cellular with Tailscale connected → dashboard renders.
2. Save a place; force-quit; relaunch → session + place persist (cookie store).
3. Map pans/zooms; tiles load (same-origin, no console errors).
4. Copper chat streams token-by-token (SSE not buffered by `tailscale serve`);
   first-visit pulse appears on a fresh install and stops after the first send.
5. Light and night themes both render; status bar legible in both.
6. Tailnet disconnected → documented error page; reconnect + reload recovers.
