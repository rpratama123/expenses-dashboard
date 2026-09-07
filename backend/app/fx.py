from __future__ import annotations

import sqlite3
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx

from .config import Settings
from .db import connect, get_state, set_state, utc_now
from .money import parse_rate

PROVIDER = "ECB"
BASE = "USD"
QUOTE = "IDR"
POLICY_REVISION = 1
PUBLICATION_GRACE_DAYS = 7
FRANKFURTER_ORIGIN = "https://api.frankfurter.dev"
_RECONCILE_LOCK = threading.Lock()


class FrankfurterClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch_rate(self, requested_date: date) -> tuple[date, Decimal]:
        owned = self._client is None
        client = self._client or httpx.Client(
            base_url=FRANKFURTER_ORIGIN,
            timeout=httpx.Timeout(10, connect=5),
            follow_redirects=False,
        )
        try:
            response = None
            for attempt in range(3):
                try:
                    response = client.get(
                        f"/v2/rate/{BASE}/{QUOTE}",
                        params={"providers": PROVIDER, "date": requested_date.isoformat()},
                    )
                    if response.status_code != 429 and response.status_code < 500:
                        break
                    response.raise_for_status()
                except (httpx.TransportError, httpx.HTTPStatusError):
                    if attempt == 2:
                        raise
                    time.sleep(0.25 * (2**attempt))
            assert response is not None
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("invalid Frankfurter response")
            effective = date.fromisoformat(payload["date"])
            if effective > requested_date:
                raise ValueError("provider returned a future rate")
            return effective, parse_rate(payload["rate"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid Frankfurter response") from exc
        finally:
            if owned:
                client.close()


def _store_rate(
    connection: sqlite3.Connection, effective: date, rate: Decimal, fetched_at: str
) -> None:
    existing = connection.execute(
        "SELECT rate_text FROM fx_rates WHERE provider=? AND base=? AND quote=? "
        "AND effective_date=?",
        (PROVIDER, BASE, QUOTE, effective.isoformat()),
    ).fetchone()
    if existing:
        # Finalized provider observations are intentionally immutable.
        return
    connection.execute(
        "INSERT INTO fx_rates(provider, base, quote, effective_date, rate_text, fetched_at) "
        "VALUES(?, ?, ?, ?, ?, ?)",
        (PROVIDER, BASE, QUOTE, effective.isoformat(), format(rate, "f"), fetched_at),
    )


def _best_stored_rate(connection: sqlite3.Connection, requested: date) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT effective_date, rate_text FROM fx_rates WHERE provider=? AND base=? AND quote=? "
        "AND effective_date<=? ORDER BY effective_date DESC LIMIT 1",
        (PROVIDER, BASE, QUOTE, requested.isoformat()),
    ).fetchone()


def reconcile_needed_rates(
    settings: Settings,
    client: FrankfurterClient | None = None,
    *,
    today: date | None = None,
    stop_event: threading.Event | None = None,
) -> int:
    if stop_event is None:
        _RECONCILE_LOCK.acquire()
    else:
        while not _RECONCILE_LOCK.acquire(timeout=0.1):
            if stop_event.is_set():
                return 0
    try:
        return _reconcile_needed_rates(
            settings, client, today=today, stop_event=stop_event
        )
    finally:
        _RECONCILE_LOCK.release()


def _reconcile_needed_rates(
    settings: Settings,
    client: FrankfurterClient | None = None,
    *,
    today: date | None = None,
    stop_event: threading.Event | None = None,
) -> int:
    if stop_event is not None and stop_event.is_set():
        return 0
    provider = client or FrankfurterClient()
    today = today or datetime.now(ZoneInfo(settings.report_timezone)).date()
    with connect(settings.database_path) as connection:
        requested_dates = [
            date.fromisoformat(row[0])
            for row in connection.execute(
                "SELECT DISTINCT jakarta_date FROM expenses_projection WHERE currency='USD'"
            )
        ]
        existing = {
            row["requested_date"]: row
            for row in connection.execute("SELECT * FROM fx_day_assignments")
        }
    observations: dict[date, tuple[date, Decimal] | None] = {}
    for requested in requested_dates:
        if stop_event is not None and stop_event.is_set():
            return 0
        old = existing.get(requested.isoformat())
        if old and old["status"] == "finalized":
            continue
        try:
            observations[requested] = provider.fetch_rate(requested)
        except (httpx.HTTPError, ValueError):
            observations[requested] = None
    changed = 0
    with connect(settings.database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        for observation in observations.values():
            if observation is not None:
                effective, rate = observation
                _store_rate(connection, effective, rate, utc_now())
        for requested in requested_dates:
            old = existing.get(requested.isoformat())
            if old and old["status"] == "finalized":
                continue
            selected = _best_stored_rate(connection, requested)
            if selected is None:
                continue
            old_effective = old["effective_date"] if old else None
            old_status = old["status"] if old else None
            status = (
                "finalized"
                if observations.get(requested) is not None
                and requested <= today - timedelta(days=PUBLICATION_GRACE_DAYS)
                else "provisional"
            )
            connection.execute(
                "INSERT INTO fx_day_assignments(requested_date, provider, effective_date, status, "
                "policy_revision, updated_at) VALUES(?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(requested_date) DO UPDATE SET provider=excluded.provider, "
                "effective_date=excluded.effective_date, status=excluded.status, "
                "policy_revision=excluded.policy_revision, updated_at=excluded.updated_at "
                "WHERE fx_day_assignments.status!='finalized'",
                (
                    requested.isoformat(),
                    PROVIDER,
                    selected["effective_date"],
                    status,
                    POLICY_REVISION,
                    utc_now(),
                ),
            )
            if old_effective != selected["effective_date"] or old_status != status:
                changed += 1
        if changed:
            revision = int(get_state(connection, "fx_revision") or "0") + 1
            set_state(connection, "fx_revision", str(revision))
    return changed


def collect_daily_rate(
    settings: Settings,
    client: FrankfurterClient | None = None,
    *,
    stop_event: threading.Event | None = None,
) -> bool:
    if stop_event is not None and stop_event.is_set():
        return False
    provider = client or FrankfurterClient()
    requested = datetime.now(ZoneInfo(settings.report_timezone)).date()
    try:
        effective, rate = provider.fetch_rate(requested)
    except (httpx.HTTPError, ValueError):
        return False
    if stop_event is not None and stop_event.is_set():
        return False
    with connect(settings.database_path) as connection:
        before = _best_stored_rate(connection, effective)
        _store_rate(connection, effective, rate, utc_now())
        return before is None


def maintain_fx(
    settings: Settings, *, stop_event: threading.Event | None = None
) -> None:
    collect_daily_rate(settings, stop_event=stop_event)
    reconcile_needed_rates(settings, stop_event=stop_event)
