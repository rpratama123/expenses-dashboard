from __future__ import annotations

import calendar
import math
import sqlite3
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .categories import category_label
from .db import get_state, read_transaction
from .money import original_amount_text, to_idr
from .schemas import SAFE_INTEGER


class SnapshotUnavailableError(RuntimeError):
    pass


class FxUnavailableError(RuntimeError):
    def __init__(self, missing_count: int) -> None:
        self.missing_count = missing_count
        super().__init__(f"{missing_count} conversion(s) unavailable")


class UnsafeIntegerError(ValueError):
    pass


def local_day_bounds(day: date, timezone_name: str) -> tuple[datetime, datetime, ZoneInfo]:
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA timezone identifier") from exc
    try:
        start_local = datetime.combine(day, time.min, timezone)
        end_local = datetime.combine(day + timedelta(days=1), time.min, timezone)
        start = start_local.astimezone(UTC)
        end = end_local.astimezone(UTC)
    except (OverflowError, ValueError) as exc:
        raise ValueError("local-day boundary is not representable") from exc
    if (
        start.astimezone(timezone).date() != day
        or start.astimezone(timezone).time() != time.min
        or end.astimezone(timezone).date() != day + timedelta(days=1)
        or end.astimezone(timezone).time() != time.min
        or end <= start
    ):
        raise ValueError("the requested local calendar day does not exist")
    return start, end, timezone


def _metadata_from_counts(
    connection: sqlite3.Connection,
    timezone: str,
    transaction_count: int,
    missing_count: int,
    provisional_count: int,
) -> dict:
    return {
        "api_schema_version": 1,
        "cache_schema_version": 1,
        "dataset_revision": int(get_state(connection, "dataset_revision") or "0"),
        "fx_revision": int(get_state(connection, "fx_revision") or "0"),
        "generated_at": datetime.now(ZoneInfo(timezone)),
        "source_timestamp": get_state(connection, "active_snapshot_timestamp"),
        "reporting_timezone": timezone,
        "conversion": {
            "complete": missing_count == 0,
            "converted_count": transaction_count - missing_count,
            "missing_count": missing_count,
            "provisional_count": provisional_count,
        },
    }


def _metadata(connection: sqlite3.Connection, timezone: str, rows: list[dict]) -> dict:
    missing = sum(item["converted_idr"] is None for item in rows)
    provisional = sum(item.get("fx_status") == "provisional" for item in rows)
    return _metadata_from_counts(connection, timezone, len(rows), missing, provisional)


SELECT_EXPENSES = """
SELECT e.*, a.status AS fx_status, a.effective_date AS fx_rate_date,
       r.rate_text AS fx_rate, r.provider AS fx_source
FROM expenses_projection e
LEFT JOIN fx_day_assignments a
  ON e.currency='USD' AND a.requested_date=e.jakarta_date
LEFT JOIN fx_rates r
  ON r.provider=a.provider AND r.base='USD' AND r.quote='IDR'
 AND r.effective_date=a.effective_date
"""

SELECT_SUMMARY = """
SELECT e.amount_minor, e.currency, e.merchant, e.category, e.jakarta_date,
       a.status AS fx_status, r.rate_text AS fx_rate
FROM expenses_projection e
LEFT JOIN fx_day_assignments a
  ON e.currency='USD' AND a.requested_date=e.jakarta_date
LEFT JOIN fx_rates r
  ON r.provider=a.provider AND r.base='USD' AND r.quote='IDR'
 AND r.effective_date=a.effective_date
"""


def _item(row: sqlite3.Row) -> dict:
    rate = row["fx_rate"]
    converted = to_idr(row["amount_minor"], row["currency"], rate)
    return {
        "id": row["id"],
        "expense_at": row["expense_at_utc"],
        "jakarta_date": row["jakarta_date"],
        "merchant": row["merchant"],
        "category_key": row["category"],
        "category_name": category_label(row["category"]),
        "bank": row["bank"],
        "payment_method": row["payment_method"],
        "note": row["note"],
        "currency": row["currency"],
        "amount_minor": str(row["amount_minor"]),
        "original_amount": original_amount_text(row["amount_minor"], row["currency"]),
        "converted_idr": str(converted) if converted is not None else None,
        "fx_rate": rate,
        "fx_rate_date": row["fx_rate_date"],
        "fx_source": row["fx_source"],
        "fx_status": row["fx_status"],
    }


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _where(
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    search: str | None = None,
    categories: list[str] | None = None,
    payment_methods: list[str] | None = None,
    banks: list[str] | None = None,
    currencies: list[str] | None = None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    values: list[object] = []
    if start_date:
        clauses.append("e.jakarta_date>=?")
        values.append(start_date.isoformat())
    if end_date:
        clauses.append("e.jakarta_date<=?")
        values.append(end_date.isoformat())
    if search:
        clauses.append("(e.merchant LIKE ? ESCAPE '\\' OR COALESCE(e.note, '') LIKE ? ESCAPE '\\')")
        escaped = f"%{_escape_like(search)}%"
        values.extend((escaped, escaped))
    for column, selected in (
        ("category", categories),
        ("payment_method", payment_methods),
        ("bank", banks),
        ("currency", currencies),
    ):
        if selected:
            clauses.append(f"e.{column} IN ({','.join('?' for _ in selected)})")
            values.extend(selected)
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), values


def _require_snapshot(connection: sqlite3.Connection) -> None:
    if get_state(connection, "dataset_revision") is None:
        raise SnapshotUnavailableError


def get_summary(path: Path, timezone: str, start: date, end: date) -> dict:
    if end < start or (end - start).days > 3660:
        raise ValueError("date range must be ordered and no longer than 10 years")
    where, values = _where(start_date=start, end_date=end)
    total = 0
    transaction_count = 0
    missing_count = 0
    provisional_count = 0
    original: dict[str, int] = defaultdict(int)
    category_totals: dict[str, int] = defaultdict(int)
    merchant_totals: dict[str, int] = defaultdict(int)
    merchant_counts: dict[str, int] = defaultdict(int)
    monthly = (end - start).days > 92
    trend_totals: dict[str, int] = defaultdict(int)
    trend_counts: dict[str, int] = defaultdict(int)
    with read_transaction(path) as connection:
        _require_snapshot(connection)
        for row in connection.execute(SELECT_SUMMARY + where, values):
            transaction_count += 1
            original[row["currency"]] += row["amount_minor"]
            if row["fx_status"] == "provisional":
                provisional_count += 1
            amount = to_idr(row["amount_minor"], row["currency"], row["fx_rate"])
            if amount is None:
                missing_count += 1
                continue
            total += amount
            category_totals[row["category"]] += amount
            merchant = row["merchant"] or "Unknown merchant"
            merchant_totals[merchant] += amount
            merchant_counts[merchant] += 1
            period = row["jakarta_date"][:7] if monthly else row["jakarta_date"]
            trend_totals[period] += amount
            trend_counts[period] += 1
        metadata = _metadata_from_counts(
            connection,
            timezone,
            transaction_count,
            missing_count,
            provisional_count,
        )
    return {
        "metadata": metadata,
        "data": {
            "start_date": start,
            "end_date": end,
            "total_idr": str(total),
            "transaction_count": transaction_count,
            "original_subtotals": [
                {
                    "currency": currency,
                    "amount": original_amount_text(amount, currency),
                    "amount_minor": str(amount),
                }
                for currency, amount in sorted(original.items())
            ],
            "categories": [
                {"key": key, "name": category_label(key), "total_idr": str(value)}
                for key, value in sorted(
                    category_totals.items(), key=lambda pair: (-pair[1], pair[0])
                )
            ],
            "trend_granularity": "month" if monthly else "day",
            "trend": [
                {
                    "period": period,
                    "total_idr": str(trend_totals[period]),
                    "transaction_count": trend_counts[period],
                }
                for period in sorted(trend_totals)
            ],
            "largest_merchants": [
                {
                    "merchant": merchant,
                    "total_idr": str(value),
                    "transaction_count": merchant_counts[merchant],
                }
                for merchant, value in sorted(
                    merchant_totals.items(), key=lambda pair: (-pair[1], pair[0].casefold())
                )[:10]
            ],
        },
    }


def get_transactions(
    path: Path,
    timezone: str,
    *,
    page: int,
    page_size: int,
    start_date: date | None,
    end_date: date | None,
    search: str | None,
    categories: list[str] | None,
    payment_methods: list[str] | None,
    banks: list[str] | None,
    currencies: list[str] | None,
) -> dict:
    if start_date and end_date and end_date < start_date:
        raise ValueError("end_date must not precede start_date")
    where, values = _where(
        start_date=start_date,
        end_date=end_date,
        search=search,
        categories=categories,
        payment_methods=payment_methods,
        banks=banks,
        currencies=currencies,
    )
    with read_transaction(path) as connection:
        _require_snapshot(connection)
        total = connection.execute(
            "SELECT COUNT(*) FROM expenses_projection e" + where, values
        ).fetchone()[0]
        rows = connection.execute(
            SELECT_EXPENSES
            + where
            + " ORDER BY e.expense_at_utc DESC, e.id DESC LIMIT ? OFFSET ?",
            [*values, page_size, (page - 1) * page_size],
        )
        items = [_item(row) for row in rows]
        options = {
            "categories": [
                {"key": row[0], "name": category_label(row[0])}
                for row in connection.execute(
                    "SELECT DISTINCT category FROM expenses_projection ORDER BY category"
                )
            ],
            "payment_methods": [row[0] for row in connection.execute(
                "SELECT DISTINCT payment_method FROM expenses_projection "
                "WHERE payment_method IS NOT NULL ORDER BY payment_method"
            )],
            "banks": [row[0] for row in connection.execute(
                "SELECT DISTINCT bank FROM expenses_projection WHERE bank IS NOT NULL ORDER BY bank"
            )],
            "currencies": [row[0] for row in connection.execute(
                "SELECT DISTINCT currency FROM expenses_projection ORDER BY currency"
            )],
        }
        metadata = _metadata(connection, timezone, items)
    return {
        "metadata": metadata,
        "data": {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": math.ceil(total / page_size),
            "filters": options,
        },
    }


def get_transaction(path: Path, timezone: str, identifier: str) -> dict | None:
    with read_transaction(path) as connection:
        _require_snapshot(connection)
        row = connection.execute(SELECT_EXPENSES + " WHERE e.id=?", (identifier,)).fetchone()
        if row is None:
            return None
        item = _item(row)
        metadata = _metadata(connection, timezone, [item])
    return {"metadata": metadata, "data": item}


def get_daily_digest(path: Path, requested_date: date, timezone_name: str) -> dict:
    start, end, timezone = local_day_bounds(requested_date, timezone_name)
    with read_transaction(path) as connection:
        _require_snapshot(connection)
        rows = connection.execute(
            SELECT_EXPENSES
            + " WHERE e.expense_at_utc>=? AND e.expense_at_utc<?",
            (start.isoformat(), end.isoformat()),
        )
        items = [_item(row) for row in rows]
        metadata = {
            "dataset_revision": int(get_state(connection, "dataset_revision") or "0"),
            "fx_revision": int(get_state(connection, "fx_revision") or "0"),
            "snapshot_timestamp": get_state(connection, "active_snapshot_timestamp") or "",
        }
    missing = sum(item["converted_idr"] is None for item in items)
    if missing:
        raise FxUnavailableError(missing)
    total = sum(int(item["converted_idr"]) for item in items)
    categories: dict[str, int] = defaultdict(int)
    for item in items:
        categories[item["category_key"]] += int(item["converted_idr"])
    if abs(total) > SAFE_INTEGER or any(abs(value) > SAFE_INTEGER for value in categories.values()):
        raise UnsafeIntegerError("amount exceeds the interoperable JSON safe-integer bound")
    winning = min(categories, key=lambda key: (-categories[key], key)) if categories else None
    provisional = any(item["fx_status"] == "provisional" for item in items)
    return {
        "body": {
            "date": requested_date,
            "timezone": timezone_name,
            "currency": "IDR",
            "total": total,
            "transaction_count": len(items),
            "top_category": (
                {"name": category_label(winning), "total": categories[winning]}
                if winning is not None
                else None
            ),
            "generated_at": datetime.now(timezone),
        },
        "metadata": metadata,
        "fx_status": "provisional" if provisional else "finalized",
    }


def current_month(timezone_name: str) -> tuple[date, date]:
    today = datetime.now(ZoneInfo(timezone_name)).date()
    return today.replace(day=1), today.replace(day=calendar.monthrange(today.year, today.month)[1])
