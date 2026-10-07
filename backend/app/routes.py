from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request

from .db import connect, get_state, read_transaction
from .fx import PUBLICATION_GRACE_DAYS
from .money import CURRENCY_SCALES
from .queries import (
    SnapshotUnavailableError,
    current_month,
    get_summary,
    get_transaction,
    get_transactions,
)
from .schemas import (
    SettingsResponse,
    SummaryResponse,
    TransactionResponse,
    TransactionsResponse,
)

router = APIRouter(prefix="/api/v1")


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": "snapshot_unavailable", "message": "No valid snapshot is active"},
    )


def _last_import_error(connection) -> dict | None:
    # A failure only matters until the next successful import supersedes it.
    row = connection.execute(
        "SELECT filename, failure_reason, imported_at FROM imports "
        "WHERE status='failed' AND id > COALESCE("
        "(SELECT MAX(id) FROM imports WHERE status IN ('accepted', 'duplicate')), 0) "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


@router.get("/status")
def status(request: Request) -> dict:
    settings = request.app.state.settings
    with connect(settings.database_path, readonly=True) as connection:
        revision = get_state(connection, "dataset_revision")
        last_failure = _last_import_error(connection)
        return {
            "api_schema_version": 1,
            "cache_schema_version": 1,
            "dataset_revision": int(revision or "0"),
            "fx_revision": int(get_state(connection, "fx_revision") or "0"),
            "snapshot_available": revision is not None,
            "source_filename": get_state(connection, "active_snapshot_filename"),
            "source_timestamp": get_state(connection, "active_snapshot_timestamp"),
            "imported_at": get_state(connection, "active_imported_at"),
            "last_import_error": last_failure,
            "reporting_timezone": settings.report_timezone,
        }


@router.get("/settings", response_model=SettingsResponse)
def application_settings(request: Request) -> dict:
    settings = request.app.state.settings
    with read_transaction(settings.database_path) as connection:
        revision = get_state(connection, "dataset_revision")
        source_timestamp = get_state(connection, "active_snapshot_timestamp")
        imported_at = get_state(connection, "active_imported_at")
        last_failure = _last_import_error(connection)
        fx = connection.execute(
            "SELECT MIN(effective_date) AS oldest, MAX(effective_date) AS newest, "
            "MAX(fetched_at) AS last_fetch FROM fx_rates"
        ).fetchone()
        coverage = connection.execute(
            """
            WITH required AS (
                SELECT DISTINCT jakarta_date
                FROM expenses_projection
                WHERE currency!='IDR'
            )
            SELECT
                COUNT(*) AS required_days,
                COUNT(a.requested_date) AS assigned_days,
                COALESCE(SUM(a.status='finalized'), 0) AS finalized_days,
                COALESCE(SUM(a.status='provisional'), 0) AS provisional_days,
                COALESCE(SUM(a.requested_date IS NULL OR r.rate_text IS NULL), 0) AS missing_days
            FROM required q
            LEFT JOIN fx_day_assignments a ON a.requested_date=q.jakarta_date
            LEFT JOIN fx_rates r ON r.provider=a.provider AND r.base='USD' AND r.quote='IDR'
              AND r.effective_date=a.effective_date
            """
        ).fetchone()
        conversion = connection.execute(
            """
            SELECT
                COUNT(*) AS total_count,
                COALESCE(SUM(e.currency!='IDR' AND r.rate_text IS NULL), 0) AS missing_count,
                COALESCE(SUM(
                    e.currency!='IDR'
                    AND a.status='provisional'
                    AND r.rate_text IS NOT NULL
                ), 0)
                    AS provisional_count
            FROM expenses_projection e
            LEFT JOIN fx_day_assignments a
              ON e.currency='USD' AND a.requested_date=e.jakarta_date
            LEFT JOIN fx_rates r
              ON r.provider=a.provider AND r.base='USD' AND r.quote='IDR'
             AND r.effective_date=a.effective_date
            """
        ).fetchone()
        missing_count = int(conversion["missing_count"])
        total_count = int(conversion["total_count"])
        required_days = int(coverage["required_days"])
        missing_days = int(coverage["missing_days"])
        provisional_days = int(coverage["provisional_days"])
        if missing_days:
            fx_status = "incomplete"
        elif provisional_days:
            fx_status = "provisional"
        elif required_days:
            fx_status = "finalized"
        else:
            fx_status = "not_required"
        return {
            "metadata": {
                "api_schema_version": 1,
                "cache_schema_version": 1,
                "dataset_revision": int(revision or "0"),
                "fx_revision": int(get_state(connection, "fx_revision") or "0"),
                "generated_at": datetime.now(ZoneInfo(settings.report_timezone)),
                "source_timestamp": source_timestamp,
                "reporting_timezone": settings.report_timezone,
                "conversion": {
                    "complete": missing_count == 0,
                    "converted_count": total_count - missing_count,
                    "missing_count": missing_count,
                    "provisional_count": int(conversion["provisional_count"]),
                },
            },
            "data": {
                "reporting_timezone": settings.report_timezone,
                "reporting_currency": "IDR",
                "currency_scales": dict(CURRENCY_SCALES),
                "fx_provider": "Frankfurter / ECB",
                "fx_policy": "Historical Jakarta transaction date; no future rates",
                "fx_publication_grace_days": PUBLICATION_GRACE_DAYS,
                "source": {
                    "snapshot_available": revision is not None,
                    "filename": get_state(connection, "active_snapshot_filename"),
                    "source_timestamp": source_timestamp,
                    "imported_at": imported_at,
                    "last_import_error": last_failure,
                },
                "fx_coverage": {
                    "status": fx_status,
                    "oldest_effective_date": fx["oldest"],
                    "newest_effective_date": fx["newest"],
                    "last_fetched_at": fx["last_fetch"],
                    "required_days": required_days,
                    "assigned_days": int(coverage["assigned_days"]),
                    "finalized_days": int(coverage["finalized_days"]),
                    "provisional_days": provisional_days,
                    "missing_days": missing_days,
                },
            },
        }


@router.get("/summary", response_model=SummaryResponse)
def summary(
    request: Request,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    settings = request.app.state.settings
    default_start, default_end = current_month(settings.report_timezone)
    start = start_date or default_start
    end = end_date or default_end
    try:
        return get_summary(settings.database_path, settings.report_timezone, start, end)
    except SnapshotUnavailableError as exc:
        raise _unavailable() from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_query", "message": str(exc)}
        ) from exc


@router.get("/transactions", response_model=TransactionsResponse)
def transactions(
    request: Request,
    page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    start_date: date | None = None,
    end_date: date | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    category: Annotated[list[str] | None, Query()] = None,
    payment_method: Annotated[list[str] | None, Query()] = None,
    bank: Annotated[list[str] | None, Query()] = None,
    currency: Annotated[list[str] | None, Query()] = None,
) -> dict:
    settings = request.app.state.settings
    try:
        return get_transactions(
            settings.database_path,
            settings.report_timezone,
            page=page,
            page_size=page_size,
            start_date=start_date,
            end_date=end_date,
            search=search,
            categories=category,
            payment_methods=payment_method,
            banks=bank,
            currencies=currency,
        )
    except SnapshotUnavailableError as exc:
        raise _unavailable() from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_query", "message": str(exc)}
        ) from exc


@router.get("/transactions/{expense_id}", response_model=TransactionResponse)
def transaction_detail(request: Request, expense_id: str) -> dict:
    if len(expense_id) > 200:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_id", "message": "ID is too long"}
        )
    settings = request.app.state.settings
    try:
        result = get_transaction(settings.database_path, settings.report_timezone, expense_id)
    except SnapshotUnavailableError as exc:
        raise _unavailable() from exc
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Transaction not found"},
        )
    return result
