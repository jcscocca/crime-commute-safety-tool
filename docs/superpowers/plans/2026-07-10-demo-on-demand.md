# Demo-on-Demand (Phase 7, Slice 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An on-demand public demo of Waypoint — env-gated rate limiting + hosted-LLM auth in the backend, plus a ThinkPad compose/tunnel overlay — per `docs/superpowers/specs/2026-07-10-demo-on-demand-design.md`.

**Architecture:** A new `app/ratelimit.py` module (token buckets + a global UTC-day counter, in-process, thread-safe, default OFF via `MCA_RATE_LIMIT_ENABLED`) enforced at three points: a pure-ASGI burst middleware, the `/sessions` route, and the `/assistant/chat` route. `OpenAiLlmClient` learns an optional `api_key` (Bearer header) so the Analyst can call Groq. Demo isolation comes free from a compose project name (`-p waypoint-demo` prefixes volumes/networks); the overlay adds only the port and env posture. Tunnel = `cloudflared` quick tunnel wrapped in PowerShell scripts.

**Tech Stack:** FastAPI/Starlette (pure ASGI middleware — NOT `BaseHTTPMiddleware`, which buffers and interferes with the SSE assistant stream), pydantic-settings, pytest + TestClient, Docker Compose overlay, cloudflared, PowerShell.

**Worktree:** `.worktrees/demo-on-demand-impl`, branch `demo-on-demand-impl`. Run backend tests as `.venv/bin/python -m pytest tests/... -q`.

---

### Task 1: Settings — rate-limit + LLM-key fields

**Files:**
- Modify: `app/config.py` (fields go after `llm_fallback_disable_thinking`, line ~47)
- Modify: `.env.example` (append after the LLM block)
- Test: `tests/test_config_demo.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config_demo.py
from __future__ import annotations

from app.config import Settings


def _settings(**env) -> Settings:
    return Settings(_env_file=None, **env)


def test_rate_limit_defaults_off() -> None:
    s = _settings()
    assert s.rate_limit_enabled is False
    assert s.trust_proxy_headers is False
    assert s.rate_limit_sessions_per_hour == 10
    assert s.rate_limit_assistant_per_hour == 20
    assert s.rate_limit_assistant_global_per_day == 100
    assert s.rate_limit_burst_per_minute == 120


def test_llm_api_key_defaults_empty() -> None:
    s = _settings()
    assert s.llm_api_key == ""
    assert s.llm_fallback_api_key == ""


def test_effective_fallback_api_key_inherits_primary() -> None:
    s = _settings(llm_api_key="gsk_primary")
    assert s.effective_llm_fallback_api_key == "gsk_primary"
    s2 = _settings(llm_api_key="gsk_primary", llm_fallback_api_key="gsk_other")
    assert s2.effective_llm_fallback_api_key == "gsk_other"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_config_demo.py -q`
Expected: FAIL — `Settings` has no field `rate_limit_enabled`.

- [ ] **Step 3: Add the fields**

In `app/config.py`, after the `llm_fallback_disable_thinking: bool = False` line:

```python
    # Bearer token for hosted OpenAI-compatible endpoints (e.g. Groq). Empty = no
    # Authorization header (the LAN llama-swap path). Fallback inherits the primary
    # key unless overridden.
    llm_api_key: str = ""
    llm_fallback_api_key: str = ""

    # Demo/public rate limiting (see docs/superpowers/specs/2026-07-10-demo-on-demand-design.md).
    # All enforcement is OFF unless rate_limit_enabled — dev and tests are unaffected.
    rate_limit_enabled: bool = False
    # Trust CF-Connecting-IP for client identity (set true only behind cloudflared;
    # otherwise the header is attacker-controlled).
    trust_proxy_headers: bool = False
    rate_limit_sessions_per_hour: int = 10
    rate_limit_assistant_per_hour: int = 20
    rate_limit_assistant_global_per_day: int = 100
    rate_limit_burst_per_minute: int = 120
```

And after the `effective_session_cookie_secure` property:

```python
    @property
    def effective_llm_fallback_api_key(self) -> str:
        return self.llm_fallback_api_key or self.llm_api_key
```

- [ ] **Step 4: Append to `.env.example`** (after the LLM lines):

```bash
# Bearer token for hosted OpenAI-compatible endpoints (e.g. Groq). Leave empty for
# local llama-swap. Fallback endpoint inherits MCA_LLM_API_KEY unless overridden.
MCA_LLM_API_KEY=
MCA_LLM_FALLBACK_API_KEY=

# Public-demo rate limiting (all enforcement off unless enabled; see docs/DEMO.md).
MCA_RATE_LIMIT_ENABLED=false
MCA_TRUST_PROXY_HEADERS=false
MCA_RATE_LIMIT_SESSIONS_PER_HOUR=10
MCA_RATE_LIMIT_ASSISTANT_PER_HOUR=20
MCA_RATE_LIMIT_ASSISTANT_GLOBAL_PER_DAY=100
MCA_RATE_LIMIT_BURST_PER_MINUTE=120
```

- [ ] **Step 5: Run tests, then commit**

Run: `.venv/bin/python -m pytest tests/test_config_demo.py -q` → PASS.

```bash
git add app/config.py .env.example tests/test_config_demo.py
git commit -m "feat(config): rate-limit and hosted-LLM-key settings (default off/empty)"
```

---

### Task 2: LLM client auth — Bearer header when a key is set

**Files:**
- Modify: `app/assistant/llm_client.py` (`OpenAiLlmClient.__init__` ~line 28, and the httpx post ~line 68)
- Modify: `app/api/routes_assistant.py` (`build_assistant_llm_client`, lines 34–51)
- Test: `tests/test_llm_client_auth.py` (new), `tests/test_assistant_client_builder.py` (extend)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_client_auth.py
from __future__ import annotations

from app.assistant.llm_client import OpenAiLlmClient


def test_no_key_no_auth_header() -> None:
    client = OpenAiLlmClient(base_url="http://x/v1", model="m")
    assert client.request_headers() == {}


def test_key_becomes_bearer_header() -> None:
    client = OpenAiLlmClient(base_url="http://x/v1", model="m", api_key="gsk_abc")
    assert client.request_headers() == {"Authorization": "Bearer gsk_abc"}
```

And in `tests/test_assistant_client_builder.py`: add `"llm_api_key": ""`, `"llm_fallback_api_key": ""` to the `_settings()` base dict, add a fake `effective_llm_fallback_api_key` (SimpleNamespace can't run properties — compute it in the helper):

```python
def _settings(**overrides):
    base = {
        "llm_base_url": "http://primary:8080/v1",
        "llm_model": "gemma",
        "llm_disable_thinking": False,
        "llm_fallback_base_url": "",
        "llm_fallback_model": "",
        "llm_fallback_disable_thinking": False,
        "llm_api_key": "",
        "llm_fallback_api_key": "",
    }
    base.update(overrides)
    ns = SimpleNamespace(**base)
    ns.effective_llm_fallback_api_key = ns.llm_fallback_api_key or ns.llm_api_key
    return ns
```

plus the new test:

```python
def test_api_keys_reach_both_clients() -> None:
    client = build_assistant_llm_client(
        _settings(
            llm_api_key="gsk_primary",
            llm_fallback_base_url="http://fb:8080/v1",
            llm_fallback_model="qwen",
        )
    )
    assert [c.api_key for c in client.clients] == ["gsk_primary", "gsk_primary"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_llm_client_auth.py tests/test_assistant_client_builder.py -q`
Expected: FAIL — unexpected keyword `api_key` / no `request_headers`.

- [ ] **Step 3: Implement**

`app/assistant/llm_client.py` — add the parameter and header helper, and use it in the post:

```python
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_s: float = 120.0,
        connect_timeout_s: float = 5.0,
        extra_body: dict[str, object] | None = None,
        api_key: str = "",
    ) -> None:
        ...existing assignments...
        # Bearer auth for hosted endpoints (Groq, etc.); empty for LAN llama-swap.
        self.api_key = api_key

    def request_headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}
```

and in `complete()`:

```python
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self.request_headers(),
                )
```

`app/api/routes_assistant.py` — pass the keys in `build_assistant_llm_client`:

```python
    primary = OpenAiLlmClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        extra_body=_no_think_body(settings.llm_disable_thinking),
        api_key=settings.llm_api_key,
    )
    ...
        fallback = OpenAiLlmClient(
            base_url=fallback_base_url,
            model=fallback_model,
            extra_body=_no_think_body(settings.llm_fallback_disable_thinking),
            api_key=settings.effective_llm_fallback_api_key,
        )
```

- [ ] **Step 4: Run tests** → PASS (also run `tests/test_assistant_api.py -q` to confirm nothing else broke).

- [ ] **Step 5: Commit**

```bash
git add app/assistant/llm_client.py app/api/routes_assistant.py tests/test_llm_client_auth.py tests/test_assistant_client_builder.py
git commit -m "feat(assistant): Bearer auth for hosted OpenAI-compatible LLM endpoints"
```

---

### Task 3: Rate-limit core — buckets, day counter, client IP

**Files:**
- Create: `app/ratelimit.py`
- Test: `tests/test_ratelimit.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ratelimit.py
from __future__ import annotations

from app.ratelimit import RateLimiterState, client_ip_from


class FakeRequest:
    def __init__(self, host: str = "1.2.3.4", headers: dict[str, str] | None = None):
        self.headers = headers or {}
        self.client = type("C", (), {"host": host})()


def test_bucket_allows_capacity_then_blocks() -> None:
    state = RateLimiterState()
    # capacity 3 per hour, no refill within the test instant
    for _ in range(3):
        assert state.try_take("sessions", "ip1", capacity=3, per_seconds=3600, now=1000.0) == 0.0
    wait = state.try_take("sessions", "ip1", capacity=3, per_seconds=3600, now=1000.0)
    assert wait > 0


def test_bucket_refills_over_time() -> None:
    state = RateLimiterState()
    for _ in range(3):
        state.try_take("sessions", "ip1", capacity=3, per_seconds=3600, now=1000.0)
    # one token refills after per_seconds/capacity = 1200s
    assert state.try_take("sessions", "ip1", capacity=3, per_seconds=3600, now=2200.5) == 0.0


def test_buckets_are_per_key_and_per_family() -> None:
    state = RateLimiterState()
    assert state.try_take("sessions", "ip1", capacity=1, per_seconds=3600, now=0.0) == 0.0
    assert state.try_take("sessions", "ip2", capacity=1, per_seconds=3600, now=0.0) == 0.0
    assert state.try_take("assistant", "ip1", capacity=1, per_seconds=3600, now=0.0) == 0.0


def test_global_day_counter_blocks_and_rolls_over() -> None:
    state = RateLimiterState()
    assert state.try_count_global(limit=2, day_key="2026-07-10") is True
    assert state.try_count_global(limit=2, day_key="2026-07-10") is True
    assert state.try_count_global(limit=2, day_key="2026-07-10") is False
    assert state.try_count_global(limit=2, day_key="2026-07-11") is True


def test_client_ip_ignores_header_without_trust() -> None:
    req = FakeRequest(host="9.9.9.9", headers={"cf-connecting-ip": "8.8.8.8"})
    assert client_ip_from(req, trust_proxy_headers=False) == "9.9.9.9"


def test_client_ip_uses_header_with_trust() -> None:
    req = FakeRequest(host="127.0.0.1", headers={"cf-connecting-ip": "8.8.8.8"})
    assert client_ip_from(req, trust_proxy_headers=True) == "8.8.8.8"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_ratelimit.py -q`
Expected: FAIL — `No module named 'app.ratelimit'`.

- [ ] **Step 3: Implement `app/ratelimit.py`**

```python
from __future__ import annotations

import threading
import time
from datetime import UTC, datetime

# In-process rate limiting for the public demo posture (single-host by design —
# see docs/superpowers/specs/2026-07-10-demo-on-demand-design.md). All enforcement
# is gated by MCA_RATE_LIMIT_ENABLED at the call sites; this module is pure state.

_MAX_TRACKED_KEYS = 10_000


class RateLimiterState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (family, key) -> [tokens, updated_at]
        self._buckets: dict[tuple[str, str], list[float]] = {}
        self._global_day_key: str = ""
        self._global_count: int = 0

    def try_take(
        self,
        family: str,
        key: str,
        *,
        capacity: int,
        per_seconds: float,
        now: float | None = None,
    ) -> float:
        """Take one token; return 0.0 on success, else seconds until a token refills."""
        now = time.monotonic() if now is None else now
        refill_per_second = capacity / per_seconds
        with self._lock:
            if len(self._buckets) > _MAX_TRACKED_KEYS:
                # Lazy prune: drop entries that have fully refilled (idle callers).
                self._buckets = {
                    k: v
                    for k, v in self._buckets.items()
                    if v[0] + (now - v[1]) * refill_per_second < capacity
                }
            tokens, updated_at = self._buckets.get((family, key), [float(capacity), now])
            tokens = min(float(capacity), tokens + (now - updated_at) * refill_per_second)
            if tokens >= 1.0:
                self._buckets[(family, key)] = [tokens - 1.0, now]
                return 0.0
            self._buckets[(family, key)] = [tokens, now]
            return (1.0 - tokens) / refill_per_second

    def try_count_global(self, *, limit: int, day_key: str | None = None) -> bool:
        """Count one global event against a per-UTC-day cap."""
        day_key = day_key or datetime.now(UTC).strftime("%Y-%m-%d")
        with self._lock:
            if day_key != self._global_day_key:
                self._global_day_key = day_key
                self._global_count = 0
            if self._global_count >= limit:
                return False
            self._global_count += 1
            return True


_state = RateLimiterState()


def get_rate_limiter() -> RateLimiterState:
    return _state


def reset_rate_limiter() -> None:
    """Test hook: fresh state so one test's exhaustion can't leak into another."""
    global _state
    _state = RateLimiterState()


def client_ip_from(request, *, trust_proxy_headers: bool) -> str:
    if trust_proxy_headers:
        header = request.headers.get("cf-connecting-ip")
        if header:
            return header
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"
```

- [ ] **Step 4: Run tests** → PASS.

- [ ] **Step 5: Add the conftest reset** — in `tests/conftest.py`, following the existing freshness-cache pattern:

```python
from app.ratelimit import reset_rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Rate-limit buckets are in-process state; reset per test."""
    reset_rate_limiter()
    yield
```

- [ ] **Step 6: Run the whole suite quickly** — `.venv/bin/python -m pytest tests -q -x` → PASS (limiter is default-off; nothing else changes).

- [ ] **Step 7: Commit**

```bash
git add app/ratelimit.py tests/test_ratelimit.py tests/conftest.py
git commit -m "feat(ratelimit): in-process token buckets + global day counter (state only)"
```

---

### Task 4: Session-creation cap

**Files:**
- Modify: `app/api/routes_sessions.py`
- Test: `tests/test_ratelimit_api.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ratelimit_api.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def limited_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("MCA_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("MCA_RATE_LIMIT_SESSIONS_PER_HOUR", "3")
    monkeypatch.setenv("MCA_TRUST_PROXY_HEADERS", "false")
    app = create_app(f"sqlite+pysqlite:///{tmp_path}/rl.sqlite3")
    return TestClient(app)


def test_session_creation_capped(limited_client: TestClient) -> None:
    for _ in range(3):
        assert limited_client.post("/sessions").status_code == 200
    response = limited_client.post("/sessions")
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    detail = response.json()["detail"].lower()
    # invariant-safe copy: about request limits, never place characteristics
    assert "request" in detail or "limit" in detail


def test_spoofed_proxy_header_ignored_without_trust(limited_client: TestClient) -> None:
    # All 4 calls come from the same socket peer; the spoofed header must NOT
    # give each call a fresh bucket.
    for i in range(3):
        assert (
            limited_client.post("/sessions", headers={"CF-Connecting-IP": f"8.8.8.{i}"}).status_code
            == 200
        )
    assert (
        limited_client.post("/sessions", headers={"CF-Connecting-IP": "8.8.9.9"}).status_code
        == 429
    )


def test_trusted_proxy_header_separates_clients(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MCA_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("MCA_RATE_LIMIT_SESSIONS_PER_HOUR", "1")
    monkeypatch.setenv("MCA_TRUST_PROXY_HEADERS", "true")
    app = create_app(f"sqlite+pysqlite:///{tmp_path}/rl2.sqlite3")
    client = TestClient(app)
    assert client.post("/sessions", headers={"CF-Connecting-IP": "8.8.8.1"}).status_code == 200
    assert client.post("/sessions", headers={"CF-Connecting-IP": "8.8.8.2"}).status_code == 200
    assert client.post("/sessions", headers={"CF-Connecting-IP": "8.8.8.1"}).status_code == 429


def test_limiter_off_by_default(tmp_path) -> None:
    app = create_app(f"sqlite+pysqlite:///{tmp_path}/rl3.sqlite3")
    client = TestClient(app)
    for _ in range(25):
        assert client.post("/sessions").status_code == 200
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_ratelimit_api.py -q`
Expected: the capped tests FAIL (all responses 200).

- [ ] **Step 3: Implement** — `app/api/routes_sessions.py` becomes:

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.config import get_settings
from app.ratelimit import client_ip_from, get_rate_limiter
from app.sessions import SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS, new_session_token

router = APIRouter()


@router.post("/sessions")
def create_public_session(request: Request, response: Response) -> dict[str, str]:
    settings = get_settings()
    if settings.rate_limit_enabled:
        ip = client_ip_from(request, trust_proxy_headers=settings.trust_proxy_headers)
        wait = get_rate_limiter().try_take(
            "sessions",
            ip,
            capacity=settings.rate_limit_sessions_per_hour,
            per_seconds=3600.0,
        )
        if wait > 0:
            raise HTTPException(
                status_code=429,
                detail="Session request limit reached — please retry later.",
                headers={"Retry-After": str(max(1, int(wait)))},
            )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=new_session_token(),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.effective_session_cookie_secure,
        samesite="lax",
    )
    return {"session_state": "created"}
```

- [ ] **Step 4: Run tests** → PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes_sessions.py tests/test_ratelimit_api.py
git commit -m "feat(ratelimit): per-IP session-creation cap (env-gated)"
```

---

### Task 5: Assistant caps (per-session + global daily)

**Files:**
- Modify: `app/api/routes_assistant.py` (the `assistant_chat` route)
- Test: `tests/test_ratelimit_api.py` (extend)

- [ ] **Step 1: Write the failing test** (append to `tests/test_ratelimit_api.py`)

The global-cap=0 case needs no LLM stub — the 429 fires before any model call. Creating a
session first requires the session cookie flow the other public routes use; reuse the app's
own `/sessions` endpoint and let TestClient carry the cookie.

```python
def test_assistant_global_daily_cap(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MCA_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("MCA_RATE_LIMIT_ASSISTANT_GLOBAL_PER_DAY", "0")
    app = create_app(f"sqlite+pysqlite:///{tmp_path}/rl4.sqlite3")
    client = TestClient(app)
    client.post("/sessions")
    response = client.post(
        "/assistant/chat",
        json={"messages": [{"role": "user", "content": "hi"}], "dashboard_state": None},
    )
    assert response.status_code == 429
    detail = response.json()["detail"].lower()
    assert "analyst" in detail and ("limit" in detail or "capacity" in detail)
```

NOTE: if `AssistantChatRequest` rejects `"dashboard_state": None`, check its schema in
`app/assistant/schemas.py` and use the minimal valid body the existing
`tests/test_assistant_api.py` uses — copy its request-body shape exactly.

- [ ] **Step 2: Run to verify failure** — expected: 200/validation status, not 429.

- [ ] **Step 3: Implement** — in `assistant_chat`, before building the LLM client:

```python
@router.post("/assistant/chat")
async def assistant_chat(
    request: AssistantChatRequest,
    http_request: Request,
    user_id_hash: Annotated[str, Depends(required_public_user_hash)],
    session: Annotated[Session, Depends(get_session)],
) -> StreamingResponse:
    settings = get_settings()
    if settings.rate_limit_enabled:
        limiter = get_rate_limiter()
        if not limiter.try_count_global(limit=settings.rate_limit_assistant_global_per_day):
            raise HTTPException(
                status_code=429,
                detail="The demo Analyst has reached its daily capacity — try again tomorrow.",
                headers={"Retry-After": "3600"},
            )
        wait = limiter.try_take(
            "assistant",
            user_id_hash,
            capacity=settings.rate_limit_assistant_per_hour,
            per_seconds=3600.0,
        )
        if wait > 0:
            raise HTTPException(
                status_code=429,
                detail="Analyst request limit reached for this session — please retry later.",
                headers={"Retry-After": str(max(1, int(wait)))},
            )
    llm_client = build_assistant_llm_client(settings)
    ...unchanged stream...
```

New imports: `from fastapi import APIRouter, Depends, HTTPException, Request` and
`from app.ratelimit import get_rate_limiter`. (`Request` here is `fastapi.Request`; the
name `request` is already taken by the body param — hence `http_request`, which is unused
by the caps but keeps the door open for IP-tier checks; if ruff flags it unused, drop it
and keep only the body param.)

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_ratelimit_api.py tests/test_assistant_api.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes_assistant.py tests/test_ratelimit_api.py
git commit -m "feat(ratelimit): assistant per-session and global daily caps"
```

---

### Task 6: General burst middleware (pure ASGI)

**Files:**
- Modify: `app/ratelimit.py` (add the middleware class)
- Modify: `app/main.py` (register it)
- Test: `tests/test_ratelimit_api.py` (extend)

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_burst_limit_on_api_routes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MCA_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("MCA_RATE_LIMIT_BURST_PER_MINUTE", "5")
    app = create_app(f"sqlite+pysqlite:///{tmp_path}/rl5.sqlite3")
    client = TestClient(app)
    statuses = [client.get("/input-modes").status_code for _ in range(7)]
    assert statuses[:5] == [200] * 5
    assert 429 in statuses[5:]


def test_burst_limit_exempts_health(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MCA_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("MCA_RATE_LIMIT_BURST_PER_MINUTE", "1")
    app = create_app(f"sqlite+pysqlite:///{tmp_path}/rl6.sqlite3")
    client = TestClient(app)
    for _ in range(5):
        assert client.get("/health").status_code == 200
```

- [ ] **Step 2: Run to verify failure** — all 200s.

- [ ] **Step 3: Implement** — append to `app/ratelimit.py`:

```python
import json

# Paths exempt from the burst tier: static assets, the SPA shell, health, docs, and
# internal/admin surfaces (not tunnel-exposed concerns; admin has its own token).
_BURST_EXEMPT_PREFIXES = (
    "/health",
    "/tiles",
    "/assets",
    "/basemaps-assets",
    "/fonts",
    "/dashboard-app",
    "/docs",
    "/openapi.json",
    "/internal",
    "/admin",
)


class BurstLimitMiddleware:
    """Pure ASGI middleware (BaseHTTPMiddleware would buffer the assistant's SSE
    stream). Applies a per-IP token bucket to public API routes."""

    def __init__(self, app, *, get_settings_fn) -> None:
        self.app = app
        self._get_settings = get_settings_fn

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        settings = self._get_settings()
        path = scope.get("path", "")
        if (
            not settings.rate_limit_enabled
            or path == "/"
            or path.startswith(_BURST_EXEMPT_PREFIXES)
        ):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        ip = "unknown"
        if settings.trust_proxy_headers and headers.get("cf-connecting-ip"):
            ip = headers["cf-connecting-ip"]
        elif scope.get("client"):
            ip = scope["client"][0]
        wait = get_rate_limiter().try_take(
            "burst",
            ip,
            capacity=settings.rate_limit_burst_per_minute,
            per_seconds=60.0,
        )
        if wait > 0:
            body = json.dumps({"detail": "Request limit reached — please retry shortly."}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"retry-after", str(max(1, int(wait))).encode()),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
```

In `app/main.py`, after the routers/mounts in `create_app` (import `BurstLimitMiddleware`
from `app.ratelimit`):

```python
    app.add_middleware(BurstLimitMiddleware, get_settings_fn=get_settings)
```

(Registered unconditionally; it self-gates on `rate_limit_enabled` per request, so tests
that flip the env var after app creation still behave.)

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_ratelimit_api.py -q` then the full `tests -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ratelimit.py app/main.py tests/test_ratelimit_api.py
git commit -m "feat(ratelimit): per-IP burst middleware over public API routes"
```

---

### Task 7: Demo compose overlay + env template

**Files:**
- Create: `docker-compose.demo.yml`
- Create: `.env.demo.example`
- Modify: `docker-compose.yml` (pass through the new env vars in the `api` service `environment` block)

- [ ] **Step 1: Pass the new vars through the base compose** — add to the `api:` service `environment:` block after the LLM lines:

```yaml
      MCA_LLM_API_KEY: ${MCA_LLM_API_KEY:-}
      MCA_LLM_FALLBACK_API_KEY: ${MCA_LLM_FALLBACK_API_KEY:-}
      MCA_RATE_LIMIT_ENABLED: "${MCA_RATE_LIMIT_ENABLED:-false}"
      MCA_TRUST_PROXY_HEADERS: "${MCA_TRUST_PROXY_HEADERS:-false}"
      MCA_RATE_LIMIT_SESSIONS_PER_HOUR: "${MCA_RATE_LIMIT_SESSIONS_PER_HOUR:-10}"
      MCA_RATE_LIMIT_ASSISTANT_PER_HOUR: "${MCA_RATE_LIMIT_ASSISTANT_PER_HOUR:-20}"
      MCA_RATE_LIMIT_ASSISTANT_GLOBAL_PER_DAY: "${MCA_RATE_LIMIT_ASSISTANT_GLOBAL_PER_DAY:-100}"
      MCA_RATE_LIMIT_BURST_PER_MINUTE: "${MCA_RATE_LIMIT_BURST_PER_MINUTE:-120}"
```

- [ ] **Step 2: Create `docker-compose.demo.yml`**

```yaml
# Demo-on-demand overlay. ALWAYS run with a distinct project name so volumes and
# networks never collide with the personal instance on the same machine:
#
#   docker compose -p waypoint-demo -f docker-compose.yml -f docker-compose.demo.yml \
#     --env-file .env.demo up -d --build
#
# See docs/DEMO.md. The -p prefix gives the demo its own db volume for free.
services:
  api:
    ports:
      - "8001:8000"
```

- [ ] **Step 3: Create `.env.demo.example`**

```bash
# Demo-on-demand posture (copy to .env.demo — gitignored — and fill in).
# production makes the app REFUSE to boot on placeholder secrets below.
MCA_ENVIRONMENT=production

# Fresh randoms — never reuse the personal instance's values:
#   openssl rand -hex 32
MCA_SESSION_SECRET=__run: openssl rand -hex 32__
MCA_USER_HASH_SALT=__run: openssl rand -hex 32__
#   openssl rand -hex 24
MCA_ADMIN_INGEST_TOKEN=__run: openssl rand -hex 24__

# Behind the Cloudflare tunnel: TLS terminates at Cloudflare; the local hop is HTTP.
MCA_SESSION_COOKIE_SECURE=false

# HARD demo posture — do not change these two:
MCA_PUBLIC_ENABLE_PERSONAL_UPLOADS=false
MCA_RATE_LIMIT_ENABLED=true

# Client identity comes from Cloudflare's header (safe: only cloudflared can reach
# this instance's port from outside).
MCA_TRUST_PROXY_HEADERS=true

# Analyst on Groq (free tier). Get a key at https://console.groq.com/keys
MCA_LLM_BASE_URL=https://api.groq.com/openai/v1
MCA_LLM_MODEL=llama-3.3-70b-versatile
MCA_LLM_API_KEY=__your groq key__

# Nominatim requires an identifiable contact in production.
MCA_GEOCODER_CONTACT_EMAIL=__your email__

# Optional: raise Socrata ingest rate limits.
SOCRATA_APP_TOKEN=
```

- [ ] **Step 4: Verify `.env.demo` is gitignored** — `grep -n "^\.env" .gitignore`; the
existing `.env` pattern does NOT cover `.env.demo` (gitignore `.env` matches only exactly
`.env`). Add a line `.env.demo` to `.gitignore`.

- [ ] **Step 5: Sanity check the merged compose config**

Run: `docker compose -p waypoint-demo -f docker-compose.yml -f docker-compose.demo.yml config 2>/dev/null | grep -nE "8001|waypoint" | head` (skip if docker isn't running locally — note it for the live bring-up).

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml docker-compose.demo.yml .env.demo.example .gitignore
git commit -m "feat(demo): compose overlay + env template for the demo-on-demand instance"
```

---

### Task 8: Tunnel scripts + runbook

**Files:**
- Create: `scripts/demo/start-demo.ps1`
- Create: `scripts/demo/stop-demo.ps1`
- Create: `docs/DEMO.md`

- [ ] **Step 1: Create `scripts/demo/start-demo.ps1`**

```powershell
# Start the Waypoint demo-on-demand instance and expose it via an ephemeral
# Cloudflare quick tunnel. Run from the repo root on the ThinkPad.
#   powershell -ExecutionPolicy Bypass -File scripts/demo/start-demo.ps1
param(
    [int]$Port = 8001,
    [int]$FreshnessMaxAgeDays = 14
)
$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env.demo")) {
    Write-Error "Missing .env.demo — copy .env.demo.example and fill in real values."
}
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Error "cloudflared not found — install with: winget install Cloudflare.cloudflared"
}

Write-Host "Starting demo compose project (waypoint-demo)..."
docker compose -p waypoint-demo -f docker-compose.yml -f docker-compose.demo.yml --env-file .env.demo up -d --build
if ($LASTEXITCODE -ne 0) { Write-Error "compose up failed" }

Write-Host "Waiting for /health..."
$deadline = (Get-Date).AddMinutes(3)
while ($true) {
    try {
        $null = Invoke-RestMethod -Uri "http://localhost:$Port/health" -TimeoutSec 5
        break
    } catch {
        if ((Get-Date) -gt $deadline) { Write-Error "API did not become healthy in 3 minutes" }
        Start-Sleep -Seconds 5
    }
}

# Refresh SPD data if stale (freshness endpoint needs a session cookie).
$ws = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$null = Invoke-RestMethod -Uri "http://localhost:$Port/sessions" -Method Post -WebSession $ws
$freshness = Invoke-RestMethod -Uri "http://localhost:$Port/dashboard/freshness" -WebSession $ws
$dataThrough = [datetime]$freshness.data_through
if ($dataThrough -lt (Get-Date).AddDays(-$FreshnessMaxAgeDays)) {
    Write-Host "Data through $dataThrough is older than $FreshnessMaxAgeDays days — ingesting recent SPD data..."
    $envLines = Get-Content ".env.demo" | Where-Object { $_ -match "^MCA_ADMIN_INGEST_TOKEN=" }
    $token = ($envLines -split "=", 2)[1]
    $start = (Get-Date).AddMonths(-24).ToString("yyyy-MM-dd")
    $end = (Get-Date).ToString("yyyy-MM-dd")
    Invoke-RestMethod -Method Post -Headers @{ "X-Admin-Token" = $token } `
        -Uri "http://localhost:$Port/admin/crime/ingest/socrata?limit=50000&offset=0&start_date=$start&end_date=$end"
} else {
    Write-Host "Data through $dataThrough — fresh enough."
}

Write-Host ""
Write-Host "Starting quick tunnel — the public URL appears below (Ctrl+C stops the tunnel):"
cloudflared tunnel --url "http://localhost:$Port"
```

- [ ] **Step 2: Create `scripts/demo/stop-demo.ps1`**

```powershell
# Tear down the demo instance (the tunnel dies with its Ctrl+C / window close).
$ErrorActionPreference = "Stop"
docker compose -p waypoint-demo -f docker-compose.yml -f docker-compose.demo.yml --env-file .env.demo down
Write-Host "Demo instance stopped. DB volume kept (docker volume rm waypoint-demo_* to wipe)."
```

- [ ] **Step 3: Verify the freshness response field name** — before trusting
`$freshness.data_through`, check the actual schema: `grep -n "data_through\|freshness" app/api/routes_public_dashboard.py app/services/crime_service.py | head`. Use the real
field name in the script (adjust if it's e.g. `data_through_date`).

- [ ] **Step 4: Create `docs/DEMO.md`**

```markdown
# Demo-on-demand runbook

Spin up a public, shareable Waypoint demo from the ThinkPad in ~2 minutes, and tear it
down when done. Design: `docs/superpowers/specs/2026-07-10-demo-on-demand-design.md`.

## What it is

- A **second, isolated compose project** (`waypoint-demo`) on the deploy machine: own
  Postgres volume, own port (8001), demo secrets, personal uploads OFF, rate limiting ON.
  The personal instance and its data are not reachable through the demo.
- An **ephemeral Cloudflare quick tunnel** (`https://<random>.trycloudflare.com`) — no
  account or domain; the URL changes every session and dies with the tunnel process.
- The **Analyst runs on Groq** (free tier) via `MCA_LLM_API_KEY`; if the key is absent or
  Groq is down, the app degrades to the built-in "analyst offline" panel.

## Prerequisites (one-time)

1. `winget install Cloudflare.cloudflared`
2. Groq API key: https://console.groq.com/keys
3. `cp .env.demo.example .env.demo` and fill in: two `openssl rand -hex 32` secrets, an
   admin token, the Groq key, and a geocoder contact email. The app refuses to boot in
   production mode with placeholders.

## Start / stop

    powershell -ExecutionPolicy Bypass -File scripts/demo/start-demo.ps1
    # ... share the printed trycloudflare.com URL; Ctrl+C kills the tunnel ...
    powershell -ExecutionPolicy Bypass -File scripts/demo/stop-demo.ps1

Start refreshes SPD data automatically when it's more than 14 days stale.

## Limits in force

Sessions 10/hour/IP · Analyst 20/hour/session and 100/day global · API burst 120/min/IP.
Tune via `MCA_RATE_LIMIT_*` in `.env.demo`.

## The "for-real" launch (deferred)

Same env vars and limiter on a small VPS, a named tunnel or plain TLS, a real domain, and
a durable README link. Nothing here needs rework for that move.
```

- [ ] **Step 5: Commit**

```bash
git add scripts/demo/ docs/DEMO.md
git commit -m "feat(demo): quick-tunnel start/stop scripts + runbook"
```

---

### Task 9: Verification gate + PR

- [ ] **Step 1: Full gate** — `make test-all` from the worktree → all four legs green.

- [ ] **Step 2: Push + PR**

```bash
git push -u origin demo-on-demand-impl
gh pr create --title "feat: demo-on-demand — rate limiting, hosted-LLM auth, tunnel overlay (Phase 7 slice 2)" --body "## What

Implements docs/superpowers/specs/2026-07-10-demo-on-demand-design.md:

- app/ratelimit.py: in-process token buckets + global UTC-day counter, pure-ASGI burst middleware (SSE-safe), env-gated OFF by default
- Caps: sessions 10/h/IP, assistant 20/h/session + 100/day global, burst 120/min/IP; CF-Connecting-IP trusted only when MCA_TRUST_PROXY_HEADERS=true
- MCA_LLM_API_KEY (+fallback) Bearer auth in the assistant LLM client — enables Groq
- Demo overlay: docker-compose.demo.yml (-p waypoint-demo isolation), .env.demo.example, start/stop-demo.ps1, docs/DEMO.md

Roadmap tick intentionally NOT included — it lands after the live ThinkPad bring-up (spec completion criteria 2–4).

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

---

### Task 10: Live ThinkPad bring-up (user-involved; after PR merge)

This is a runbook execution, not code. It satisfies spec completion criteria 2–4.

- [ ] **Step 1:** On the ThinkPad: pull main, complete docs/DEMO.md prerequisites (cloudflared, Groq key, `.env.demo`).
- [ ] **Step 2:** `start-demo.ps1`; confirm the personal instance (port 8000) is untouched and the demo answers on 8001.
- [ ] **Step 3:** From a phone/second network via the tunnel URL: address lookup → analyze → compare → export end-to-end.
- [ ] **Step 4:** Analyst over Groq through the tunnel: ask a grounded question; then temporarily blank `MCA_LLM_API_KEY` and confirm the graceful offline panel. **Groq JSON smoke:** the classify prompt was tuned on gemma — if Groq misbehaves on JSON, try a different `MCA_LLM_MODEL` first, prompt changes second (own PR).
- [ ] **Step 5:** From a second machine: hammer `POST /sessions` (>10 in a minute) and confirm 429 + `Retry-After`.
- [ ] **Step 6:** Tick the roadmap slice-2 box (with a one-line "live-verified <date>" note) in a small docs PR. Update project memory.

---

## Self-review notes (2026-07-10)

- **Spec coverage:** limiter core/caps/middleware (Tasks 3–6) ✓ · LLM auth (2) ✓ · settings (1) ✓ · compose overlay + env template (7) ✓ · scripts + runbook (8) ✓ · live criteria + tick-after-verify (10) ✓ · invariant-safe 429 copy asserted in tests (Task 4 Step 1) ✓.
- **Known judgment calls:** middleware registered unconditionally but self-gating (keeps env-var-driven tests honest); `_env_file=None` in config tests so a developer's local `.env` can't pollute them; freshness field name verified at Task 8 Step 3 rather than assumed.
- **Type consistency:** `RateLimiterState.try_take(family, key, *, capacity, per_seconds, now)` and `try_count_global(*, limit, day_key)` used identically in Tasks 3–6; `client_ip_from(request, *, trust_proxy_headers)` in Tasks 3–4; `request_headers()` in Task 2 only.
