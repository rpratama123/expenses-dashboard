from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.db import connect, set_state
from app.main import create_app
from app.queries import get_summary, get_transactions


def publish(settings, source_factory, rows) -> None:
    path = settings.incoming_dir / "expenses-20260906T000000Z.sqlite3"
    source_factory(path, rows)
    path.with_name(path.name + ".ready").touch()


def expense(identifier, timestamp, amount, merchant, category="food_drink", note=None):
    return (identifier, timestamp, amount, "IDR", "BCA", "card", merchant, category, note, None)


def test_summary_uses_full_dataset_and_transaction_filters(settings, source_factory) -> None:
    publish(
        settings,
        source_factory,
        [
            expense("a", "2026-08-31T17:00:00+00:00", 100, "100% Cafe", note="literal_value"),
            expense("b", "2026-09-01T01:00:00+07:00", 200, "Shop", category="travel"),
            expense("c", "2026-10-01T00:00:00+07:00", 300, "Outside"),
        ],
    )
    with TestClient(create_app(settings)) as client:
        summary = client.get(
            "/api/v1/summary", params={"start_date": "2026-09-01", "end_date": "2026-09-30"}
        )
        assert summary.status_code == 200
        assert summary.json()["data"]["total_idr"] == "300"
        assert summary.json()["data"]["transaction_count"] == 2
        page = client.get("/api/v1/transactions", params={"page_size": 1})
        assert page.json()["data"]["total_items"] == 3
        assert len(page.json()["data"]["items"]) == 1
        assert page.json()["data"]["filters"]["categories"] == [
            {"key": "food_drink", "name": "Food"},
            {"key": "travel", "name": "Travel"},
        ]
        literal = client.get("/api/v1/transactions", params={"search": "%"})
        assert literal.json()["data"]["total_items"] == 1
        injected = client.get("/api/v1/transactions", params={"search": "' OR 1=1 --"})
        assert injected.json()["data"]["total_items"] == 0
        assert summary.headers["cache-control"] == "no-store"


def test_stable_newest_sort_detail_and_sensitive_omission(settings, source_factory) -> None:
    publish(
        settings,
        source_factory,
        [
            expense("a", "2026-09-05T10:00:00+07:00", 100, "A", note="visible"),
            expense("b", "2026-09-05T10:00:00+07:00", 200, "B"),
        ],
    )
    with TestClient(create_app(settings)) as client:
        result = client.get("/api/v1/transactions").json()
        assert [item["id"] for item in result["data"]["items"]] == ["b", "a"]
        detail = client.get("/api/v1/transactions/a")
        assert detail.status_code == 200
        serialized = detail.text
        assert "receipt" not in serialized and "raw_input" not in serialized
        assert client.get("/api/v1/transactions/removed").status_code == 404


def test_no_snapshot_is_distinct_from_empty_and_bad_queries_are_422(settings) -> None:
    with TestClient(create_app(settings)) as client:
        status = client.get("/api/v1/status")
        assert status.status_code == 200
        assert not status.json()["snapshot_available"]
        application_settings = client.get("/api/v1/settings")
        assert application_settings.status_code == 200
        assert application_settings.json()["metadata"]["conversion"] == {
            "complete": True,
            "converted_count": 0,
            "missing_count": 0,
            "provisional_count": 0,
        }
        assert not application_settings.json()["data"]["source"]["snapshot_available"]
        unavailable = client.get(
            "/api/v1/summary", params={"start_date": "2026-09-01", "end_date": "2026-09-30"}
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["detail"]["code"] == "snapshot_unavailable"
        assert client.get("/api/v1/transactions", params={"page_size": 0}).status_code == 422
        unknown = client.get("/api/v1/not-real")
        assert unknown.status_code == 404
        assert "text/html" not in unknown.headers["content-type"]


def test_settings_is_typed_cacheable_envelope_with_source_and_fx_status(
    settings, source_factory
) -> None:
    publish(
        settings,
        source_factory,
        [expense("idr", "2026-09-05T10:00:00+07:00", 100, "Shop")],
    )
    with TestClient(create_app(settings)) as client:
        with connect(settings.database_path) as connection:
            connection.execute(
                "INSERT INTO expenses_projection VALUES("
                "'usd','2026-09-05T05:00:00+00:00','2026-09-05',100,'USD',"
                "NULL,NULL,'USD Shop','travel',NULL)"
            )
            connection.execute(
                "INSERT INTO imports(filename, source_timestamp, source_identity, status, "
                "failure_reason, imported_at) VALUES("
                "'bad.sqlite3',NULL,'test','failed','integrity check failed',"
                "'2026-09-06T01:00:00+00:00')"
            )
        response = client.get("/api/v1/settings")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        payload = response.json()
        assert set(payload) == {"metadata", "data"}
        assert payload["metadata"]["dataset_revision"] == 1
        assert payload["metadata"]["conversion"] == {
            "complete": False,
            "converted_count": 1,
            "missing_count": 1,
            "provisional_count": 0,
        }
        assert payload["data"]["source"]["snapshot_available"] is True
        assert payload["data"]["source"]["filename"] == (
            "expenses-20260906T000000Z.sqlite3"
        )
        assert payload["data"]["source"]["last_import_error"]["filename"] == "bad.sqlite3"
        assert payload["data"]["fx_coverage"]["status"] == "incomplete"
        assert payload["data"]["fx_coverage"]["missing_days"] == 1

        with connect(settings.database_path) as connection:
            connection.execute(
                "INSERT INTO fx_rates VALUES("
                "'ECB','USD','IDR','2026-09-05','16000','2026-09-06T00:00:00+00:00')"
            )
            connection.execute(
                "INSERT INTO fx_day_assignments VALUES("
                "'2026-09-05','ECB','2026-09-05','provisional',1,"
                "'2026-09-06T00:00:00+00:00')"
            )
            set_state(connection, "fx_revision", "1")
        updated = client.get("/api/v1/settings").json()
        assert updated["metadata"]["fx_revision"] == 1
        assert updated["metadata"]["conversion"]["complete"] is True
        assert updated["metadata"]["conversion"]["provisional_count"] == 1
        assert updated["data"]["fx_coverage"]["status"] == "provisional"
        assert updated["data"]["fx_coverage"]["assigned_days"] == 1

        openapi = client.get("/api/openapi.json").json()
        schema = openapi["paths"]["/api/v1/settings"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        assert schema["$ref"].endswith("/SettingsResponse")


def test_streamed_summary_matches_transaction_conversion_and_aggregate_semantics(
    settings,
) -> None:
    with connect(settings.database_path) as connection:
        set_state(connection, "dataset_revision", "7")
        set_state(connection, "fx_revision", "3")
        set_state(connection, "active_snapshot_timestamp", "2026-09-06T00:00:00+00:00")
        connection.executemany(
            "INSERT INTO expenses_projection VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "idr",
                    "2026-09-05T03:00:00+00:00",
                    "2026-09-05",
                    100,
                    "IDR",
                    None,
                    "cash",
                    "B Merchant",
                    "food_drink",
                    None,
                ),
                (
                    "usd-provisional",
                    "2026-09-05T04:00:00+00:00",
                    "2026-09-05",
                    1,
                    "USD",
                    None,
                    "card",
                    "A Merchant",
                    "food_drink",
                    None,
                ),
                (
                    "usd-missing",
                    "2026-09-06T04:00:00+00:00",
                    "2026-09-06",
                    1,
                    "USD",
                    None,
                    "card",
                    "C Merchant",
                    "travel",
                    None,
                ),
            ],
        )
        connection.execute(
            "INSERT INTO fx_rates VALUES("
            "'ECB','USD','IDR','2026-09-05','150','2026-09-05T12:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO fx_day_assignments VALUES("
            "'2026-09-05','ECB','2026-09-05','provisional',1,"
            "'2026-09-05T12:00:00+00:00')"
        )

    summary = get_summary(
        settings.database_path,
        settings.report_timezone,
        date(2026, 9, 1),
        date(2026, 9, 30),
    )
    transactions = get_transactions(
        settings.database_path,
        settings.report_timezone,
        page=1,
        page_size=10,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        search=None,
        categories=None,
        payment_methods=None,
        banks=None,
        currencies=None,
    )
    displayed = [
        int(item["converted_idr"])
        for item in transactions["data"]["items"]
        if item["converted_idr"] is not None
    ]
    assert displayed == [2, 100]
    assert summary["data"]["total_idr"] == str(sum(displayed)) == "102"
    assert summary["data"]["transaction_count"] == 3
    assert summary["metadata"]["conversion"] == {
        "complete": False,
        "converted_count": 2,
        "missing_count": 1,
        "provisional_count": 1,
    }
    assert summary["data"]["original_subtotals"] == [
        {"currency": "IDR", "amount": "100", "amount_minor": "100"},
        {"currency": "USD", "amount": "0.02", "amount_minor": "2"},
    ]
    assert summary["data"]["categories"] == [
        {"key": "food_drink", "name": "Food", "total_idr": "102"}
    ]
    assert summary["data"]["trend"] == [
        {"period": "2026-09-05", "total_idr": "102", "transaction_count": 2}
    ]
    assert summary["data"]["largest_merchants"] == [
        {"merchant": "B Merchant", "total_idr": "100", "transaction_count": 1},
        {"merchant": "A Merchant", "total_idr": "2", "transaction_count": 1},
    ]
