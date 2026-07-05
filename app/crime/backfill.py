"""Socrata backfill orchestrator: page through the dataset with retry, instead of the
manual one-page-per-admin-call offset loop. Layers paging + retry/backoff + an optional
incremental watermark over the existing (already-deduping) ingest_crime_incidents.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date
from urllib.error import HTTPError, URLError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crime.seattle_socrata import SeattleSocrataClient
from app.crime.sources import SOURCE_SPD_CRIME
from app.models import CrimeIncident
from app.services.crime_ingestion_service import ingest_crime_incidents

DEFAULT_PAGE_SIZE = 5000
# Backstop so a misbehaving "short page never arrives" loop can't run unbounded; at the
# default page size this covers ~5M rows, well past the SPD dataset.
DEFAULT_MAX_PAGES = 1000
RETRYABLE_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})


def latest_observed_date(
    session: Session, source_dataset: str = SOURCE_SPD_CRIME
) -> date | None:
    """The newest observed incident date already stored for this source — the watermark an
    incremental run starts from so it doesn't re-walk the whole dataset from offset 0."""
    observed = func.coalesce(CrimeIncident.offense_start_utc, CrimeIncident.report_utc)
    value = session.scalar(
        select(func.max(observed)).where(CrimeIncident.source_dataset == source_dataset)
    )
    if value is None:
        return None
    if hasattr(value, "date"):
        return value.date()
    return date.fromisoformat(str(value)[:10])  # SQLite may return an ISO string


def _fetch_keyset_with_retry(
    client: SeattleSocrataClient,
    *,
    since_iso: str | None,
    end_date: date | None,
    limit: int,
    attempts: int,
    backoff_s: float,
    sleep: Callable[[float], None],
) -> tuple[list, str | None]:
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return client.fetch_page_keyset(
                since_iso=since_iso, end_date=end_date, limit=limit
            )
        except HTTPError as exc:
            if exc.code not in RETRYABLE_HTTP_STATUS:
                raise  # 4xx (other than 429) won't get better on retry
            last_exc = exc
        except URLError as exc:  # connection refused, timeout, DNS, ... (HTTPError's base)
            last_exc = exc
        if attempt + 1 < attempts:
            sleep(backoff_s * (2**attempt))  # exponential backoff
    assert last_exc is not None
    raise last_exc


def backfill_socrata(
    session: Session,
    client: SeattleSocrataClient,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = DEFAULT_MAX_PAGES,
    attempts: int = 3,
    backoff_s: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, int]:
    """Keyset-page forward through the date window (ordered by date ASC, cursored on the last
    row's date), ingesting each page until a short/empty page (or max_pages). Keyset paging is
    stable under concurrent inserts — unlike ``$offset``, it can't skip rows that shift position
    mid-walk — and the ingest dedupe absorbs the boundary re-reads the inclusive cursor causes.
    Each fetch is retried on transient network / 429 / 5xx errors. Returns aggregate
    inserted/skipped counts plus the number of pages fetched.
    """
    inserted_total = 0
    skipped_total = 0
    pages = 0
    cursor = None if start_date is None else f"{start_date.isoformat()}T00:00:00"
    for _ in range(max_pages):
        incidents, next_cursor = _fetch_keyset_with_retry(
            client,
            since_iso=cursor,
            end_date=end_date,
            limit=page_size,
            attempts=attempts,
            backoff_s=backoff_s,
            sleep=sleep,
        )
        if not incidents:
            break
        result = ingest_crime_incidents(session, incidents)
        inserted_total += result["inserted_count"]
        skipped_total += result["skipped_count"]
        pages += 1
        if next_cursor is None:
            break  # a short page means we've reached the end of the dataset/window
        if next_cursor == cursor:
            # A full page sharing one timestamp equal to the cursor can't advance without
            # re-reading it forever; stop rather than loop. Only reachable if a single instant
            # holds more than page_size incidents — astronomically unlikely for SPD data.
            break
        cursor = next_cursor
    return {
        "inserted_count": inserted_total,
        "skipped_count": skipped_total,
        "pages": pages,
    }
