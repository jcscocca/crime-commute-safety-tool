# Handoff: run the full Waypoint stack on the ThinkPad (used from the Mac's browser)

This is a deployment handoff for a Claude Code session running **on the Windows ThinkPad**.
Goal: bring up the **entire Waypoint stack on this one machine** — the app (UI + API), Postgres,
the analyst LLM, and OpenTripPlanner (OTP) routing — expose it on the LAN, and verify it
end-to-end. The **Mac is only a browser**: you use the app by visiting `http://<THINKPAD_IP>:8000`
from it, like any website. Nothing is served from or installed on the Mac.

## Read first

- `CLAUDE.md` — repo conventions, the product invariant, and the verification gate.
- `docs/DEPLOY.md` → the **"Single host: everything on the ThinkPad"** section, plus the
  **"Routing (OpenTripPlanner)"** section under *Notes / hardening*.
- `scripts/otp_thinkpad_setup.ps1` — the OTP setup those docs reference.

Everything is on `main`.

## Current state on this ThinkPad

- **llama-swap** (the analyst LLM gateway) is already serving on `:8080` — a Gemma model
  (`gemma-4-26b-a4b-it-ud-q4-k-m`); a Qwen model is also available. Nothing to start here.
- An **OTP Docker container** was set up earlier. `scripts/otp_thinkpad_setup.ps1` is
  idempotent — re-running is safe (it skips the download/build when the data + graph exist).
- **Waypoint** (the app itself) is *not* running here yet — that is the main thing to bring up.

## Pre-flight

- Docker Desktop is running, with file sharing enabled for the OTP data folder (`C:\otp`).
- This repo is cloned and on `main` (`git pull`).

## Bring-up (PowerShell)

```powershell
# 1. Routing / maps: download data, build the graph, serve OTP on :8090 (restart-on-boot).
./scripts/otp_thinkpad_setup.ps1
#    Confirm it serves: open http://localhost:8090/graphiql

# 2. Waypoint env: copy the template, then edit .env.deploy.
cp .env.deploy.example .env.deploy
```

In `.env.deploy`, set the secrets and the wiring. Generate secrets with `openssl rand -hex 32`
(salt + session secret) and `openssl rand -hex 24` (admin token). The Waypoint **container**
reaches the host-port services via `host.docker.internal`:

```
MCA_LLM_BASE_URL=http://host.docker.internal:8080/v1
MCA_LLM_MODEL=gemma-4-26b-a4b-it-ud-q4-k-m-ctx32k
MCA_ROUTING_PROVIDER=opentripplanner
MCA_OPENTRIPPLANNER_BASE_URL=http://host.docker.internal:8090/otp/gtfs/v1
MCA_SESSION_COOKIE_SECURE=false
```

`MCA_SESSION_COOKIE_SECURE=false` is **required** here (and keep `MCA_ENVIRONMENT` non-prod): the
Mac reaches this over **plain HTTP at a non-localhost IP**, so a `Secure` session cookie would be
dropped by the browser and every login would silently fail. (The cookie is `SameSite=Lax`, which
is fine — the page and its API calls share one origin, so requests are same-site.)

```powershell
# 3. Waypoint: API + UI + Postgres on :8000 (the container binds 0.0.0.0, so it's LAN-reachable).
docker compose --env-file .env.deploy up -d --build
```

Then load crime data (the Socrata `for offset` loop in `docs/DEPLOY.md` step 3) and smoke-test
locally at `http://localhost:8000`. If `host.docker.internal` doesn't resolve from the container,
substitute the ThinkPad's LAN IP (e.g. `http://10.0.0.76:8080/...`).

```powershell
# 4. Open the Windows firewall so the Mac can reach the app (elevated PowerShell).
New-NetFirewallRule -DisplayName "Waypoint 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow

# 5. Print this ThinkPad's LAN IP — the address to type into the Mac's browser.
(Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
  Select-Object -First 1).IPAddress
```

## Use it from the Mac

On the Mac, just open a browser to **`http://<THINKPAD_IP>:8000`** (the IP from step 5). That is
the whole app — UI and API are served together from this ThinkPad on one origin, so it behaves
like any website: no dev server, no proxy, nothing installed on the Mac. Because the page and its
API calls share that origin, there is **no CORS and no cross-origin-cookie problem**; the only
requirement is the non-`Secure` cookie from the env step above (plain HTTP).

Quick check from the Mac before declaring victory: `curl http://<THINKPAD_IP>:8000/health` should
return `{"status":"ok"}`. If the page loads but you can't get past the first screen, open browser
devtools → Application → Cookies and confirm `mca_session` exists for `<THINKPAD_IP>` with **no**
Secure flag.

## Success criteria — verify all three end-to-end

From the Mac's browser at `http://<THINKPAD_IP>:8000` (or locally on the ThinkPad at
`http://localhost:8000`):

1. **App** — the map + place analysis load.
2. **Analyst** — the chat panel answers a question (proves the `MCA_LLM_*` wiring to llama-swap).
3. **Routing** — the **Routes** tab returns real route alternatives (proves OTP).

## ⚠️ The one real risk: first live test of the OTP2 GraphQL provider

`app/routing/opentripplanner_provider.py` speaks OTP2's GTFS GraphQL API but has only been
validated against a recorded fixture — never a live OTP server. The Routes tab is that first
live test. If `/routes` errors or returns nothing:

- Check `docker logs otp` (is the graph loaded? did it log `Grizzly server running`?).
- Hit the endpoint directly and compare the response shape to the provider's parser:
  ```
  curl http://localhost:8090/otp/gtfs/v1 -X POST -H "Content-Type: application/json" -d '{"query":"{ plan(from:{lat:47.62,lon:-122.32}, to:{lat:47.61,lon:-122.33}, transportModes:[{mode:TRANSIT},{mode:WALK}]) { itineraries { duration legs { mode route { shortName } legGeometry { points } } } } }"}'
  ```
- The provider reads `data.plan.itineraries[].{duration, walkDistance, legs[...]}`. If OTP2's
  field names / mode enums differ, adjust the query + parser in
  `app/routing/opentripplanner_provider.py` and update `tests/test_opentripplanner_provider.py`.

Any code change: do it in a **dedicated git worktree** (per CLAUDE.md), **test-first**, and run
the gate (`make test-all`, or `pytest` + `ruff check .` + the frontend `npm test` / `npm run
build` if `make` isn't available on Windows) before opening a PR.

## Constraint

The entire deployment runs on this ThinkPad — API, UI, Postgres, the analyst LLM, and OTP. The
Mac is only a browser pointed at `http://<THINKPAD_IP>:8000`: a client, not part of the runtime.
Don't run any Waypoint service on the Mac.
