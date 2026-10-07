from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.db import connect, set_state
from app.main import create_app
from app.queries import local_day_bounds


def publish(settings, source_factory, rows) -> None:
    path = settings.incoming_dir / "expenses-20260906T000000Z.sqlite3"
    source_factory(path, rows)
    path.with_name(path.name + ".ready").touch()


def row(identifier: str, amount: int, category: str, timestamp="2026-09-05T12:00:00+07:00"):
    return (identifier, timestamp, amount, "IDR", None, "cash", "Merchant", category, None, None)


def test_exact_flat_contract_headers_and_category_total(settings, source_factory) -> None:
    publish(
        settings,
        source_factory,
        [
            row("1", 40_000, "food_drink"),
            row("2", 30_000, "food_drink"),
            row("3", 22_000, "food_drink"),
            row("4", 20_000, "travel"),
            row("5", 18_000, "travel"),
            row("6", 30_000, "shopping"),
            row("7", 25_500, "other"),
        ],
    )
    with TestClient(create_app(settings)) as client:
        response = client.get(
            "/api/digest/daily", params={"date": "2026-09-05", "timezone": "Asia/Jakarta"}
        )
        assert response.status_code == 200
        payload = response.json()
        assert set(payload) == {
            "date",
            "timezone",
            "currency",
            "total",
            "transaction_count",
            "top_category",
            "generated_at",
        }
        assert payload["total"] == 185_500 and isinstance(payload["total"], int)
        assert payload["transaction_count"] == 7
        assert payload["top_category"] == {"name": "Food", "total": 92_000}
        assert response.headers["x-dataset-revision"] == "1"
        assert response.headers["x-fx-status"] == "finalized"
        assert response.headers["cache-control"] == "no-store"


def test_empty_day_tie_break_and_unknown_label(settings, source_factory) -> None:
    publish(
        settings,
        source_factory,
        [row("1", 100, "zebra_category"), row("2", 100, "alpha_category")],
    )
    with TestClient(create_app(settings)) as client:
        tied = client.get(
            "/api/digest/daily", params={"date": "2026-09-05", "timezone": "Asia/Jakarta"}
        ).json()
        assert tied["top_category"] == {"name": "Alpha Category", "total": 100}
        empty = client.get(
            "/api/digest/daily", params={"date": "2026-09-06", "timezone": "Asia/Jakarta"}
        ).json()
        assert empty["total"] == 0
        assert empty["transaction_count"] == 0
        assert empty["top_category"] is None


def test_missing_and_provisional_fx_are_explicit(settings, source_factory) -> None:
    publish(settings, source_factory, [row("idr", 100, "other")])
    with TestClient(create_app(settings)) as client:
        with connect(settings.database_path) as connection:
            connection.execute(
                "INSERT INTO expenses_projection VALUES('usd','2026-09-05T05:00:00+00:00',"
                "'2026-09-05',1,'USD',NULL,NULL,'Shop','food_drink',NULL)"
            )
        missing = client.get(
            "/api/digest/daily", params={"date": "2026-09-05", "timezone": "Asia/Jakarta"}
        )
        assert missing.status_code == 503
        assert missing.json()["detail"]["code"] == "fx_rates_unavailable"
        assert missing.json()["detail"]["missing_conversion_count"] == 1
        with connect(settings.database_path) as connection:
            connection.execute(
                "INSERT INTO fx_rates VALUES('ECB','USD','IDR','2026-09-05','150',"
                "'2026-09-05T00:00:00Z')"
            )
            connection.execute(
                "INSERT INTO fx_day_assignments VALUES('2026-09-05','USD','IDR','ECB',"
                "'2026-09-05','provisional',1,'2026-09-05T00:00:00Z')"
            )
            set_state(connection, "fx_revision", "1")
        provisional = client.get(
            "/api/digest/daily", params={"date": "2026-09-05", "timezone": "Asia/Jakarta"}
        )
        assert provisional.status_code == 200
        assert provisional.json()["total"] == 102  # USD rounds half-up to two rupiah.
        assert provisional.headers["x-fx-status"] == "provisional"


def test_timezone_membership_dst_skipped_day_and_validation(settings, source_factory) -> None:
    publish(
        settings,
        source_factory,
        [row("utc", 100, "other", timestamp="2026-09-05T00:30:00+00:00")],
    )
    spring_start, spring_end, _ = local_day_bounds(date(2026, 3, 8), "America/New_York")
    fall_start, fall_end, _ = local_day_bounds(date(2026, 11, 1), "America/New_York")
    assert (spring_end - spring_start).total_seconds() == 23 * 3600
    assert (fall_end - fall_start).total_seconds() == 25 * 3600
    with TestClient(create_app(settings)) as client:
        jakarta = client.get(
            "/api/digest/daily", params={"date": "2026-09-05", "timezone": "Asia/Jakarta"}
        ).json()
        new_york = client.get(
            "/api/digest/daily", params={"date": "2026-09-04", "timezone": "America/New_York"}
        ).json()
        assert jakarta["transaction_count"] == new_york["transaction_count"] == 1
        assert client.get("/api/digest/daily").status_code == 422
        assert client.get(
            "/api/digest/daily", params={"date": "bad", "timezone": "Nowhere/Invalid"}
        ).status_code == 422
        skipped = client.get(
            "/api/digest/daily", params={"date": "2011-12-30", "timezone": "Pacific/Apia"}
        )
        assert skipped.status_code == 422


def test_no_snapshot_and_safe_integer_overflow(settings, source_factory) -> None:
    with TestClient(create_app(settings)) as client:
        unavailable = client.get(
            "/api/digest/daily", params={"date": "2026-09-05", "timezone": "Asia/Jakarta"}
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["detail"]["code"] == "snapshot_unavailable"

    # A separate initialized app is unnecessary; activate state directly for the overflow check.
    with connect(settings.database_path) as connection:
        set_state(connection, "dataset_revision", "1")
        set_state(connection, "active_snapshot_timestamp", "2026-09-06T00:00:00+00:00")
        connection.execute(
            "INSERT INTO expenses_projection VALUES('huge','2026-09-05T05:00:00+00:00',"
            "'2026-09-05',?,'IDR',NULL,NULL,'Shop','other',NULL)",
            (2**53,),
        )
    with TestClient(create_app(settings)) as client:
        overflow = client.get(
            "/api/digest/daily", params={"date": "2026-09-05", "timezone": "Asia/Jakarta"}
        )
        assert overflow.status_code == 422
