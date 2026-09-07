from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request, Response

from .queries import (
    FxUnavailableError,
    SnapshotUnavailableError,
    UnsafeIntegerError,
    get_daily_digest,
)
from .schemas import DailyDigestResponse

router = APIRouter()


@router.get(
    "/api/digest/daily",
    response_model=DailyDigestResponse,
    responses={
        503: {"description": "Snapshot or FX rates unavailable"},
        422: {"description": "Invalid date, timezone, or unsafe monetary total"},
    },
)
def daily_digest(request: Request, response: Response, date: date, timezone: str) -> dict:
    settings = request.app.state.settings
    try:
        result = get_daily_digest(settings.database_path, date, timezone)
    except SnapshotUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "snapshot_unavailable", "message": "No valid snapshot is active"},
        ) from exc
    except FxUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "fx_rates_unavailable",
                "message": "Required currency conversions are unavailable",
                "missing_conversion_count": exc.missing_count,
            },
        ) from exc
    except (ValueError, UnsafeIntegerError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_query", "message": str(exc)},
        ) from exc
    metadata = result["metadata"]
    response.headers["X-Dataset-Revision"] = str(metadata["dataset_revision"])
    response.headers["X-FX-Revision"] = str(metadata["fx_revision"])
    response.headers["X-Snapshot-Timestamp"] = metadata["snapshot_timestamp"]
    response.headers["X-FX-Status"] = result["fx_status"]
    return result["body"]
