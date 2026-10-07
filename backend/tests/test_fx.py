from __future__ import annotations

import httpx

from app.db import connect, set_state
from app.fx import FrankfurterClient, reconcile_needed_rates


def add_usd(settings, requested_date: str) -> None:
    with connect(settings.database_path) as connection:
        connection.execute(
            "INSERT INTO expenses_projection VALUES(?, ?, ?, 566, 'USD', NULL, NULL, "
            "'Shop', 'other', NULL)",
            (requested_date, f"{requested_date}T03:00:00+00:00", requested_date),
        )
        set_state(connection, "dataset_revision", "1")


def add_currency(settings, requested_date: str, currency: str, amount: int) -> None:
    with connect(settings.database_path) as connection:
        connection.execute(
            "INSERT INTO expenses_projection VALUES(?, ?, ?, ?, ?, NULL, NULL, "
            "'Shop', 'other', NULL)",
            (
                f"{currency}-{requested_date}",
                f"{requested_date}T03:00:00+00:00",
                requested_date,
                amount,
                currency,
            ),
        )
        set_state(connection, "dataset_revision", "1")


def test_persists_effective_weekend_rate_and_assignment(settings) -> None:
    add_usd(settings, "2026-09-06")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["providers"] == "ECB"
        return httpx.Response(200, json={"date": "2026-09-04", "rate": 16000})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://api.frankfurter.dev") as http:
        changed = reconcile_needed_rates(
            settings, FrankfurterClient(http), today=__import__("datetime").date(2026, 9, 20)
        )
    assert changed == 1
    with connect(settings.database_path) as connection:
        assignment = connection.execute("SELECT * FROM fx_day_assignments").fetchone()
        assert assignment["base"] == "USD" and assignment["quote"] == "IDR"
        assert assignment["effective_date"] == "2026-09-04"
        assert assignment["status"] == "finalized"
        assert connection.execute("SELECT rate_text FROM fx_rates").fetchone()[0] == "16000"


def test_failure_keeps_existing_provisional_rate(settings) -> None:
    add_usd(settings, "2026-09-06")
    with connect(settings.database_path) as connection:
        connection.execute(
            "INSERT INTO fx_rates VALUES"
            "('ECB','USD','IDR','2026-09-04','15900','2026-09-04T00:00:00Z')"
        )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.frankfurter.dev"
    ) as http:
        reconcile_needed_rates(
            settings, FrankfurterClient(http), today=__import__("datetime").date(2026, 9, 7)
        )
    with connect(settings.database_path) as connection:
        row = connection.execute("SELECT * FROM fx_day_assignments").fetchone()
        assert row["effective_date"] == "2026-09-04"
        assert row["status"] == "provisional"


def test_rejects_future_and_nonpositive_provider_rates(settings) -> None:
    add_usd(settings, "2026-09-06")
    responses = iter(
        [
            httpx.Response(200, json={"date": "2026-09-07", "rate": 16000}),
            httpx.Response(200, json={"date": "2026-09-06", "rate": 0}),
        ]
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda _request: next(responses)),
        base_url="https://api.frankfurter.dev",
    ) as http:
        assert reconcile_needed_rates(settings, FrankfurterClient(http)) == 0
        assert reconcile_needed_rates(settings, FrankfurterClient(http)) == 0
    with connect(settings.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fx_rates").fetchone()[0] == 0


def test_reconciles_each_currency_to_idr_independently(settings) -> None:
    add_usd(settings, "2026-09-06")
    add_currency(settings, "2026-09-06", "SGD", 138)
    add_currency(settings, "2026-09-06", "MYR", 250)

    def handler(request: httpx.Request) -> httpx.Response:
        base = request.url.path.split("/")[3]
        rates = {"USD": 16000, "SGD": 14026, "MYR": 4394.71}
        return httpx.Response(200, json={"date": "2026-09-04", "rate": rates[base]})

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.frankfurter.dev"
    ) as http:
        changed = reconcile_needed_rates(
            settings, FrankfurterClient(http), today=__import__("datetime").date(2026, 9, 20)
        )
    assert changed == 3
    with connect(settings.database_path) as connection:
        rates = {
            (row["base"], row["quote"]): row["rate_text"]
            for row in connection.execute("SELECT * FROM fx_rates")
        }
        assert rates == {
            ("USD", "IDR"): "16000",
            ("SGD", "IDR"): "14026",
            ("MYR", "IDR"): "4394.71",
        }
        assignments = {
            (row["base"], row["requested_date"]): row["status"]
            for row in connection.execute("SELECT * FROM fx_day_assignments")
        }
        assert assignments == {
            ("USD", "2026-09-06"): "finalized",
            ("SGD", "2026-09-06"): "finalized",
            ("MYR", "2026-09-06"): "finalized",
        }


def test_missing_rate_for_one_currency_does_not_block_others(settings) -> None:
    add_usd(settings, "2026-09-06")
    add_currency(settings, "2026-09-06", "SGD", 138)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.split("/")[3] == "SGD":
            return httpx.Response(422)
        return httpx.Response(200, json={"date": "2026-09-04", "rate": 16000})

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.frankfurter.dev"
    ) as http:
        reconcile_needed_rates(
            settings, FrankfurterClient(http), today=__import__("datetime").date(2026, 9, 20)
        )
    with connect(settings.database_path) as connection:
        assignments = {
            row["base"]: row["status"]
            for row in connection.execute("SELECT * FROM fx_day_assignments")
        }
        assert assignments == {"USD": "finalized"}
        assert connection.execute(
            "SELECT COUNT(*) FROM fx_rates WHERE base='SGD'"
        ).fetchone()[0] == 0
