# Geocode Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the browser's direct call to public Nominatim with a session-required backend geocode proxy that caches results in the DB and is polite to the upstream — keeping the search UX identical.

**Architecture:** A new `app/geocoding` package (provider protocol + Nominatim adapter) and an `app/services/geocoding_service.py` orchestrator (normalize → DB cache → rate gate → provider → cache write) sit behind a new `GET /dashboard/geocode` endpoint guarded by `required_public_user_hash`. The frontend's existing `GeocodingProvider` interface gets a new `createBackendProvider` implementation; nothing else in the UI changes.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic/pydantic-settings, httpx (sync `Client`), pytest, React + TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-06-26-geocode-proxy-design.md`

---

## File Structure

**New files:**
- `app/geocoding/__init__.py` — package marker.
- `app/geocoding/providers.py` — `GeocodeHit` dataclass, `GeocoderUpstreamError`, `GeocodeProvider` protocol, `NominatimProvider`, `build_provider()`.
- `app/services/geocoding_service.py` — `normalize_query()`, `RateGate`, `search_addresses()`, cache read/write helpers.
- `alembic/versions/0007_geocode_cache.py` — `geocode_cache` table migration.
- `tests/test_geocoding_providers.py` — provider mapping + error wrapping + factory.
- `tests/test_geocoding_service.py` — normalize, cache hit/miss/stale, propagation, rate gate.
- `tests/test_dashboard_geocode_api.py` — endpoint auth + results + 502 + empty query.
- `tests/test_config_geocoder.py` — prod requires contact email.

**Modified files:**
- `app/config.py` — `geocoder_*` settings + prod contact-email validator.
- `app/models.py` — `GeocodeCache` model.
- `app/api/dashboard_schemas.py` — `GeocodeResultSchema`.
- `app/api/routes_public_dashboard.py` — `get_geocode_provider` dependency + `dashboard_geocode` endpoint.
- `tests/test_public_sessions.py` — set `MCA_GEOCODER_CONTACT_EMAIL` in the production-cookie test.
- `frontend/src/lib/geocoding.ts` — add `createBackendProvider`, swap singleton, remove `createNominatimProvider`.
- `frontend/src/lib/geocoding.test.ts` — retarget tests to `createBackendProvider`.
- `.env.example`, `.env.deploy.example` — document `MCA_GEOCODER_*`.
- `README.md` — note geocoding is backend-proxied; prod requires `MCA_GEOCODER_CONTACT_EMAIL`.

Canonical signatures (used consistently across tasks):
- `GeocodeHit(label: str, latitude: float, longitude: float, source: str)` (frozen dataclass)
- `class GeocodeProvider(Protocol): def search(self, query: str) -> list[GeocodeHit]: ...`
- `search_addresses(session, settings, query, *, provider=None) -> list[GeocodeHit]`
- `GeocodeResultSchema(BaseModel)` fields: `label, latitude, longitude, source`

---

## Task 1: Geocoder config + production contact-email guard

**Files:**
- Modify: `app/config.py`
- Create: `tests/test_config_geocoder.py`
- Modify: `tests/test_public_sessions.py`
- Modify: `.env.example`
- Modify: `.env.deploy.example`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_geocoder.py`:

```python
from __future__ import annotations

import pytest

from app.config import Settings


def test_local_settings_allow_empty_geocoder_contact_email():
    settings = Settings(environment="local")
    assert settings.geocoder_provider == "nominatim"
    assert settings.geocoder_contact_email == ""


def test_production_settings_require_geocoder_contact_email():
    with pytest.raises(ValueError, match="MCA_GEOCODER_CONTACT_EMAIL"):
        Settings(
            environment="production",
            user_hash_salt="prod-salt",
            session_secret="prod-secret",
            geocoder_contact_email="",
        )


def test_production_settings_accept_geocoder_contact_email():
    settings = Settings(
        environment="production",
        user_hash_salt="prod-salt",
        session_secret="prod-secret",
        geocoder_contact_email="ops@example.com",
    )
    assert settings.geocoder_contact_email == "ops@example.com"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_config_geocoder.py -q`
Expected: FAIL — `Settings` has no `geocoder_provider` / no contact-email validator (`AttributeError` or no `ValueError` raised).

- [ ] **Step 3: Add the settings fields**

In `app/config.py`, inside `class Settings`, add these fields after the `assistant_max_tool_calls` line:

```python
    geocoder_provider: str = "nominatim"
    geocoder_base_url: str = "https://nominatim.openstreetmap.org/search"
    geocoder_user_agent: str = "Waypoint/0.1"
    geocoder_contact_email: str = ""
    geocoder_cache_ttl_days: int = 30
    geocoder_max_results: int = 5
    geocoder_timeout_s: float = 5.0
    geocoder_min_interval_s: float = 1.0
```

- [ ] **Step 4: Add the production validator**

In `app/config.py`, add a second validator directly below the existing `require_production_secret_overrides` method (do not modify the existing one):

```python
    @model_validator(mode="after")
    def require_production_geocoder_contact(self) -> Settings:
        if self.environment.lower() not in {"prod", "production"}:
            return self
        if not self.geocoder_contact_email.strip():
            raise ValueError(
                "Production deployments must set MCA_GEOCODER_CONTACT_EMAIL "
                "(Nominatim requires an identifiable contact)."
            )
        return self
```

- [ ] **Step 5: Keep the existing production session test green**

In `tests/test_public_sessions.py`, find `test_public_session_cookie_defaults_secure_in_production` and add the contact-email env var alongside the other production env setup (after the `MCA_SESSION_SECRET` setenv line):

```python
    monkeypatch.setenv("MCA_GEOCODER_CONTACT_EMAIL", "ops@example.com")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config_geocoder.py tests/test_public_sessions.py -q`
Expected: PASS (all).

- [ ] **Step 7: Document the env vars**

Append to `.env.example`:

```bash
# Geocoding (address search proxy)
MCA_GEOCODER_PROVIDER=nominatim
MCA_GEOCODER_BASE_URL=https://nominatim.openstreetmap.org/search
MCA_GEOCODER_USER_AGENT=Waypoint/0.1
MCA_GEOCODER_CONTACT_EMAIL=
MCA_GEOCODER_CACHE_TTL_DAYS=30
MCA_GEOCODER_MAX_RESULTS=5
MCA_GEOCODER_TIMEOUT_S=5.0
MCA_GEOCODER_MIN_INTERVAL_S=1.0
```

Append to `.env.deploy.example` (note the required contact email for production):

```bash
# Geocoding — REQUIRED in production: an identifiable contact per Nominatim policy.
MCA_GEOCODER_PROVIDER=nominatim
MCA_GEOCODER_BASE_URL=https://nominatim.openstreetmap.org/search
MCA_GEOCODER_USER_AGENT=Waypoint/0.1
MCA_GEOCODER_CONTACT_EMAIL=ops@example.com
MCA_GEOCODER_CACHE_TTL_DAYS=30
MCA_GEOCODER_MAX_RESULTS=5
MCA_GEOCODER_TIMEOUT_S=5.0
MCA_GEOCODER_MIN_INTERVAL_S=1.0
```

- [ ] **Step 8: Commit**

```bash
git add app/config.py tests/test_config_geocoder.py tests/test_public_sessions.py .env.example .env.deploy.example
git commit -m "feat: add geocoder settings and production contact-email guard"
```

---

## Task 2: GeocodeCache model + migration

**Files:**
- Modify: `app/models.py`
- Create: `alembic/versions/0007_geocode_cache.py`

- [ ] **Step 1: Add the model**

In `app/models.py`, append a new model at the end of the file:

```python
class GeocodeCache(Base):
    __tablename__ = "geocode_cache"
    __table_args__ = (
        UniqueConstraint(
            "provider", "query_normalized", name="uq_geocode_cache_provider_query"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(Text, index=True)
    query_normalized: Mapped[str] = mapped_column(Text, index=True)
    results_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
```

(`UniqueConstraint`, `String`, `Text`, `DateTime`, `Mapped`, `mapped_column`, `new_id`, `utc_now` are already imported/defined at the top of `app/models.py`.)

- [ ] **Step 2: Create the migration**

Create `alembic/versions/0007_geocode_cache.py`:

```python
"""geocode cache

Revision ID: 0007_geocode_cache
Revises: 0006_analysis_runs
Create Date: 2026-06-26
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_geocode_cache"
down_revision = "0006_analysis_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geocode_cache",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("query_normalized", sa.Text(), nullable=False),
        sa.Column("results_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "provider", "query_normalized", name="uq_geocode_cache_provider_query"
        ),
    )
    op.create_index("ix_geocode_cache_provider", "geocode_cache", ["provider"])
    op.create_index("ix_geocode_cache_query_normalized", "geocode_cache", ["query_normalized"])


def downgrade() -> None:
    op.drop_index("ix_geocode_cache_query_normalized", table_name="geocode_cache")
    op.drop_index("ix_geocode_cache_provider", table_name="geocode_cache")
    op.drop_table("geocode_cache")
```

- [ ] **Step 3: Verify the migration applies cleanly**

Run: `.venv/bin/python -m alembic upgrade head`
Expected: output includes `Running upgrade 0006_analysis_runs -> 0007_geocode_cache`.

- [ ] **Step 4: Verify the model imports and the table registers**

Run: `.venv/bin/python -c "from app.models import GeocodeCache; print(GeocodeCache.__tablename__)"`
Expected: prints `geocode_cache`.

- [ ] **Step 5: Commit**

```bash
git add app/models.py alembic/versions/0007_geocode_cache.py
git commit -m "feat: add geocode_cache model and migration"
```

---

## Task 3: Geocoding provider layer

**Files:**
- Create: `app/geocoding/__init__.py`
- Create: `app/geocoding/providers.py`
- Create: `tests/test_geocoding_providers.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_geocoding_providers.py`:

```python
from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.geocoding.providers import (
    GeocodeHit,
    GeocoderUpstreamError,
    NominatimProvider,
    build_provider,
)


def _provider_with_transport(handler) -> NominatimProvider:
    return NominatimProvider(
        base_url="https://nominatim.example/search",
        user_agent="Waypoint/0.1 (ops@example.com)",
        max_results=5,
        timeout_s=5.0,
        transport=httpx.MockTransport(handler),
    )


def test_nominatim_provider_maps_rows_to_hits():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "pike place"
        assert request.url.params["format"] == "jsonv2"
        assert request.headers["User-Agent"] == "Waypoint/0.1 (ops@example.com)"
        return httpx.Response(
            200,
            json=[{"display_name": "Pike Place Market, Seattle", "lat": "47.6097", "lon": "-122.3331"}],
        )

    provider = _provider_with_transport(handler)
    hits = provider.search("pike place")

    assert hits == [
        GeocodeHit(
            label="Pike Place Market, Seattle",
            latitude=47.6097,
            longitude=-122.3331,
            source="nominatim",
        )
    ]


def test_nominatim_provider_wraps_transport_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    provider = _provider_with_transport(handler)
    with pytest.raises(GeocoderUpstreamError):
        provider.search("anything")


def test_nominatim_provider_wraps_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    provider = _provider_with_transport(handler)
    with pytest.raises(GeocoderUpstreamError):
        provider.search("anything")


def test_build_provider_returns_nominatim():
    settings = Settings(geocoder_contact_email="ops@example.com")
    provider = build_provider(settings)
    assert isinstance(provider, NominatimProvider)


def test_build_provider_rejects_unknown():
    settings = Settings(geocoder_provider="mystery")
    with pytest.raises(ValueError, match="mystery"):
        build_provider(settings)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_geocoding_providers.py -q`
Expected: FAIL — `app.geocoding` does not exist (`ModuleNotFoundError`).

- [ ] **Step 3: Create the package marker**

Create `app/geocoding/__init__.py` (empty file):

```python
```

- [ ] **Step 4: Implement the providers**

Create `app/geocoding/providers.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import httpx

if TYPE_CHECKING:
    from app.config import Settings


@dataclass(frozen=True)
class GeocodeHit:
    label: str
    latitude: float
    longitude: float
    source: str


class GeocoderUpstreamError(RuntimeError):
    """The upstream geocoder was unreachable or returned an error/bad shape."""


class GeocodeProvider(Protocol):
    def search(self, query: str) -> list[GeocodeHit]:
        ...


class NominatimProvider:
    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        max_results: int,
        timeout_s: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url
        self.user_agent = user_agent
        self.max_results = max_results
        self.timeout_s = timeout_s
        self._transport = transport

    def search(self, query: str) -> list[GeocodeHit]:
        params = {"format": "jsonv2", "limit": self.max_results, "q": query}
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        try:
            with httpx.Client(timeout=self.timeout_s, transport=self._transport) as client:
                response = client.get(self.base_url, params=params, headers=headers)
                response.raise_for_status()
                rows = response.json()
        except httpx.HTTPError as exc:
            raise GeocoderUpstreamError(f"Geocoder upstream unavailable: {exc}") from exc
        try:
            return [
                GeocodeHit(
                    label=row["display_name"],
                    latitude=float(row["lat"]),
                    longitude=float(row["lon"]),
                    source="nominatim",
                )
                for row in rows
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise GeocoderUpstreamError(
                f"Geocoder returned an unexpected response shape: {exc}"
            ) from exc


def _user_agent(settings: Settings) -> str:
    email = settings.geocoder_contact_email.strip()
    if email:
        return f"{settings.geocoder_user_agent} ({email})"
    return settings.geocoder_user_agent


def build_provider(settings: Settings) -> GeocodeProvider:
    if settings.geocoder_provider == "nominatim":
        return NominatimProvider(
            base_url=settings.geocoder_base_url,
            user_agent=_user_agent(settings),
            max_results=settings.geocoder_max_results,
            timeout_s=settings.geocoder_timeout_s,
        )
    raise ValueError(f"Unknown geocoder provider: {settings.geocoder_provider!r}")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_geocoding_providers.py -q`
Expected: PASS (all 5).

- [ ] **Step 6: Commit**

```bash
git add app/geocoding/__init__.py app/geocoding/providers.py tests/test_geocoding_providers.py
git commit -m "feat: add geocoding provider layer with nominatim adapter"
```

---

## Task 4: Geocoding service (normalize, cache, rate gate)

**Files:**
- Create: `app/services/geocoding_service.py`
- Create: `tests/test_geocoding_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_geocoding_service.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.db import get_sessionmaker
from app.geocoding.providers import GeocodeHit, GeocoderUpstreamError
from app.main import create_app
from app.models import GeocodeCache
from app.services.geocoding_service import (
    RateGate,
    normalize_query,
    search_addresses,
)


class FakeProvider:
    def __init__(self, hits, *, error=None):
        self.hits = hits
        self.error = error
        self.calls = 0

    def search(self, query):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return list(self.hits)


# `pytest` is imported above for `pytest.approx` in the rate-gate tests.
def _settings() -> Settings:
    # min_interval 0 keeps tests from sleeping on the rate gate.
    return Settings(geocoder_min_interval_s=0.0)


def _session(tmp_path):
    create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'geo.sqlite3'}")
    return get_sessionmaker()()


def test_normalize_query_collapses_whitespace_and_case():
    assert normalize_query("  Pike   PLACE  ") == "pike place"
    assert normalize_query("   ") == ""


def test_blank_query_returns_empty_without_calling_provider(tmp_path):
    session = _session(tmp_path)
    provider = FakeProvider([])
    assert search_addresses(session, _settings(), "   ", provider=provider) == []
    assert provider.calls == 0


def test_cache_miss_calls_provider_and_writes_cache(tmp_path):
    session = _session(tmp_path)
    hit = GeocodeHit(label="Pike Place", latitude=47.6, longitude=-122.3, source="nominatim")
    provider = FakeProvider([hit])

    result = search_addresses(session, _settings(), "Pike Place", provider=provider)

    assert result == [hit]
    assert provider.calls == 1
    rows = session.query(GeocodeCache).all()
    assert len(rows) == 1
    assert rows[0].query_normalized == "pike place"


def test_cache_hit_returns_cached_without_calling_provider(tmp_path):
    session = _session(tmp_path)
    hit = GeocodeHit(label="Pike Place", latitude=47.6, longitude=-122.3, source="nominatim")
    provider = FakeProvider([hit])

    search_addresses(session, _settings(), "Pike Place", provider=provider)
    second = FakeProvider([])  # would return [] if called
    result = search_addresses(session, _settings(), "  pike   place ", provider=second)

    assert result == [hit]
    assert second.calls == 0


def test_stale_cache_refetches(tmp_path):
    session = _session(tmp_path)
    stale = GeocodeCache(
        provider="nominatim",
        query_normalized="pike place",
        results_json="[]",
        created_at=datetime.now(UTC) - timedelta(days=40),
    )
    session.add(stale)
    session.commit()

    hit = GeocodeHit(label="Fresh", latitude=1.0, longitude=2.0, source="nominatim")
    provider = FakeProvider([hit])
    result = search_addresses(session, _settings(), "Pike Place", provider=provider)

    assert result == [hit]
    assert provider.calls == 1


def test_provider_error_propagates(tmp_path):
    session = _session(tmp_path)
    provider = FakeProvider([], error=GeocoderUpstreamError("down"))
    try:
        search_addresses(session, _settings(), "Pike Place", provider=provider)
    except GeocoderUpstreamError:
        pass
    else:
        raise AssertionError("expected GeocoderUpstreamError")


def test_rate_gate_waits_only_when_needed():
    sleeps = []
    clock = {"t": 100.0}
    gate = RateGate()

    def now():
        return clock["t"]

    def sleep(seconds):
        sleeps.append(seconds)

    gate.wait(1.0, now=now, sleep=sleep)  # first call: no prior, no wait
    clock["t"] = 100.2
    gate.wait(1.0, now=now, sleep=sleep)  # 0.2s elapsed -> wait ~0.8s

    assert sleeps == [pytest.approx(0.8)]


def test_rate_gate_disabled_when_interval_zero():
    sleeps = []
    gate = RateGate()
    gate.wait(0.0, now=lambda: 0.0, sleep=lambda s: sleeps.append(s))
    assert sleeps == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_geocoding_service.py -q`
Expected: FAIL — `app.services.geocoding_service` does not exist (`ModuleNotFoundError`).

- [ ] **Step 3: Implement the service**

Create `app/services/geocoding_service.py`:

```python
from __future__ import annotations

import json
import threading
import time
from datetime import UTC, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.geocoding.providers import GeocodeHit, GeocodeProvider, build_provider
from app.models import GeocodeCache, utc_now

if TYPE_CHECKING:
    from app.config import Settings


def normalize_query(query: str) -> str:
    return " ".join(query.split()).lower()


class RateGate:
    """Process-local politeness gate: ensure at least ``min_interval_s`` between
    upstream calls. ``now``/``sleep`` are injectable for deterministic tests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self, min_interval_s: float, *, now=time.monotonic, sleep=time.sleep) -> None:
        if min_interval_s <= 0:
            return
        with self._lock:
            remaining = min_interval_s - (now() - self._last)
            if remaining > 0:
                sleep(remaining)
            self._last = now()


_rate_gate = RateGate()


def _read_cache(
    session: Session, provider: str, normalized: str, ttl_days: int
) -> list[GeocodeHit] | None:
    row = session.execute(
        select(GeocodeCache).where(
            GeocodeCache.provider == provider,
            GeocodeCache.query_normalized == normalized,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    if created < utc_now() - timedelta(days=ttl_days):
        return None
    return [GeocodeHit(**item) for item in json.loads(row.results_json)]


def _write_cache(
    session: Session, provider: str, normalized: str, hits: list[GeocodeHit]
) -> None:
    payload = json.dumps([hit.__dict__ for hit in hits])
    row = session.execute(
        select(GeocodeCache).where(
            GeocodeCache.provider == provider,
            GeocodeCache.query_normalized == normalized,
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            GeocodeCache(provider=provider, query_normalized=normalized, results_json=payload)
        )
    else:
        row.results_json = payload
        row.created_at = utc_now()
    session.commit()


def search_addresses(
    session: Session,
    settings: Settings,
    query: str,
    *,
    provider: GeocodeProvider | None = None,
) -> list[GeocodeHit]:
    normalized = normalize_query(query)
    if not normalized:
        return []
    provider = provider or build_provider(settings)
    cached = _read_cache(
        session, settings.geocoder_provider, normalized, settings.geocoder_cache_ttl_days
    )
    if cached is not None:
        return cached
    _rate_gate.wait(settings.geocoder_min_interval_s)
    hits = provider.search(query.strip())
    _write_cache(session, settings.geocoder_provider, normalized, hits)
    return hits
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_geocoding_service.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add app/services/geocoding_service.py tests/test_geocoding_service.py
git commit -m "feat: add geocoding service with db cache and rate gate"
```

---

## Task 5: Schema + GET /dashboard/geocode endpoint

**Files:**
- Modify: `app/api/dashboard_schemas.py`
- Modify: `app/api/routes_public_dashboard.py`
- Create: `tests/test_dashboard_geocode_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_geocode_api.py`:

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.routes_public_dashboard import get_geocode_provider
from app.geocoding.providers import GeocodeHit, GeocoderUpstreamError
from app.main import create_app


class FakeProvider:
    def __init__(self, hits, *, error=None):
        self.hits = hits
        self.error = error

    def search(self, query):
        if self.error is not None:
            raise self.error
        return list(self.hits)


@pytest.fixture()
def app_and_client(tmp_path, monkeypatch):
    monkeypatch.setenv("MCA_GEOCODER_MIN_INTERVAL_S", "0")
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'geo.sqlite3'}")
    client = TestClient(app)
    return app, client


def test_geocode_requires_public_session(app_and_client):
    _, client = app_and_client
    response = client.get("/dashboard/geocode", params={"q": "pike place"})
    assert response.status_code == 401


def test_geocode_returns_results(app_and_client):
    app, client = app_and_client
    client.post("/sessions")
    hit = GeocodeHit(label="Pike Place Market", latitude=47.6097, longitude=-122.3331, source="nominatim")
    app.dependency_overrides[get_geocode_provider] = lambda: FakeProvider([hit])
    try:
        response = client.get("/dashboard/geocode", params={"q": "pike place"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
        {"label": "Pike Place Market", "latitude": 47.6097, "longitude": -122.3331, "source": "nominatim"}
    ]


def test_geocode_empty_query_returns_empty_list(app_and_client):
    app, client = app_and_client
    client.post("/sessions")
    app.dependency_overrides[get_geocode_provider] = lambda: FakeProvider([])
    try:
        response = client.get("/dashboard/geocode", params={"q": "   "})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == []


def test_geocode_upstream_error_returns_502(app_and_client):
    app, client = app_and_client
    client.post("/sessions")
    app.dependency_overrides[get_geocode_provider] = lambda: FakeProvider(
        [], error=GeocoderUpstreamError("down")
    )
    try:
        response = client.get("/dashboard/geocode", params={"q": "pike place"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_dashboard_geocode_api.py -q`
Expected: FAIL — `get_geocode_provider` cannot be imported (`ImportError`).

- [ ] **Step 3: Add the response schema**

In `app/api/dashboard_schemas.py`, append:

```python
class GeocodeResultSchema(BaseModel):
    label: str
    latitude: float
    longitude: float
    source: str
```

- [ ] **Step 4: Add the dependency + endpoint**

In `app/api/routes_public_dashboard.py`, add these imports near the top (after the existing imports):

```python
from dataclasses import asdict

from app.api.dashboard_schemas import GeocodeResultSchema
from app.config import get_settings
from app.geocoding.providers import GeocodeProvider, GeocoderUpstreamError, build_provider
from app.services.geocoding_service import search_addresses
```

Then append the dependency and endpoint at the end of the file:

```python
def get_geocode_provider() -> GeocodeProvider:
    return build_provider(get_settings())


@router.get("/dashboard/geocode")
def dashboard_geocode(
    q: str,
    user_id_hash: Annotated[str, Depends(required_public_user_hash)],
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[GeocodeProvider, Depends(get_geocode_provider)],
) -> list[GeocodeResultSchema]:
    try:
        hits = search_addresses(session, get_settings(), q, provider=provider)
    except GeocoderUpstreamError as exc:
        raise HTTPException(status_code=502, detail="Geocoding upstream unavailable.") from exc
    return [GeocodeResultSchema(**asdict(hit)) for hit in hits]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_dashboard_geocode_api.py -q`
Expected: PASS (all 4).

- [ ] **Step 6: Confirm the endpoint stays on the public surface**

Run: `.venv/bin/python -m pytest tests/test_internal_surface.py -q`
Expected: PASS (the new public path does not violate the internal-surface guard).

- [ ] **Step 7: Commit**

```bash
git add app/api/dashboard_schemas.py app/api/routes_public_dashboard.py tests/test_dashboard_geocode_api.py
git commit -m "feat: add GET /dashboard/geocode proxy endpoint"
```

---

## Task 6: Frontend — point search at the backend proxy

**Files:**
- Modify: `frontend/src/lib/geocoding.ts`
- Modify: `frontend/src/lib/geocoding.test.ts`

- [ ] **Step 1: Rewrite the test for the backend provider**

Replace the entire contents of `frontend/src/lib/geocoding.test.ts` with:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { createBackendProvider } from "./geocoding";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("createBackendProvider", () => {
  it("queries the backend endpoint and returns its GeocodeResult rows", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify([
          { label: "Pike Place Market, Seattle", latitude: 47.6097, longitude: -122.3331, source: "nominatim" },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const provider = createBackendProvider();
    const results = await provider.search("pike place");

    expect(results).toEqual([
      { label: "Pike Place Market, Seattle", latitude: 47.6097, longitude: -122.3331, source: "nominatim" },
    ]);
    const calledUrl = String(fetchMock.mock.calls[0][0]);
    expect(calledUrl).toContain("/dashboard/geocode");
    expect(calledUrl).toContain("q=pike%20place");
  });

  it("returns an empty list for a blank query without calling fetch", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const provider = createBackendProvider();

    expect(await provider.search("   ")).toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("throws when the backend responds with an error status", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("nope", { status: 502 }));
    const provider = createBackendProvider();

    await expect(provider.search("x")).rejects.toThrow("Search failed with status 502");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- geocoding`
Expected: FAIL — `createBackendProvider` is not exported from `./geocoding`.

- [ ] **Step 3: Implement the backend provider and swap the singleton**

Replace the entire contents of `frontend/src/lib/geocoding.ts` with:

```ts
import type { GeocodeResult } from "../types";

export interface GeocodingProvider {
  search(query: string, signal?: AbortSignal): Promise<GeocodeResult[]>;
}

// The browser no longer calls a public geocoder directly. It calls the
// session-required backend proxy (GET /dashboard/geocode), which caches results
// and is polite to the upstream provider. Same-origin in production; the Vite
// dev server proxies /dashboard to the backend.
export function createBackendProvider(endpoint = "/dashboard/geocode"): GeocodingProvider {
  return {
    async search(query, signal) {
      const trimmed = query.trim();
      if (!trimmed) {
        return [];
      }
      const url = `${endpoint}?q=${encodeURIComponent(trimmed)}`;
      const response = await fetch(url, {
        signal,
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(`Search failed with status ${response.status}`);
      }
      return (await response.json()) as GeocodeResult[];
    },
  };
}

export const geocodingProvider = createBackendProvider();
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- geocoding`
Expected: PASS (all 3).

- [ ] **Step 5: Confirm the whole frontend suite + build are green**

Run: `cd frontend && npm test`
Expected: PASS (no remaining references to `createNominatimProvider`).

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/geocoding.ts frontend/src/lib/geocoding.test.ts
git commit -m "feat: point address search at the backend geocode proxy"
```

---

## Task 7: README note + full verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the behavior**

In `README.md`, find the geocoding/address-search reference (search for "Nominatim"; if absent, add under the environment/config section) and state:

```markdown
Address search is served by the backend proxy `GET /dashboard/geocode` (session-required),
which caches results and rate-limits the upstream. Production must set
`MCA_GEOCODER_CONTACT_EMAIL` (an identifiable contact is required by Nominatim's usage
policy). The browser never calls the geocoder directly.
```

- [ ] **Step 2: Run the full verification gate**

Run: `make test-all`
Expected: PASS — pytest (including the new geocoding tests), ruff, frontend tests, and frontend build all green.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: note backend-proxied geocoding and prod contact-email requirement"
```

---

## Self-Review

- **Spec coverage:** upstream provider seam + Nominatim adapter (Task 3) ✓; DB-backed cache + migration (Task 2, Task 4) ✓; GET endpoint, session-required, 502 mapping (Task 5) ✓; config knobs + prod contact-email guard (Task 1) ✓; frontend provider swap, manual-pin fallback preserved via unchanged error path (Task 6) ✓; tests across service/provider/API/frontend ✓; README + env docs (Task 1, Task 7) ✓. The "Deferred to a later release" cache-lifecycle item is intentionally NOT implemented.
- **Type consistency:** `GeocodeHit(label, latitude, longitude, source)` is defined in Task 3 and consumed identically in Tasks 4/5; `GeocodeResultSchema` fields match `GeocodeHit` and the frontend `GeocodeResult`; `search_addresses(session, settings, query, *, provider=None)` signature is identical across Tasks 4 and 5; `get_geocode_provider` defined in Task 5 and overridden by the same name in its test.
- **No placeholders:** every code and test block is complete; commands have expected output.
```
