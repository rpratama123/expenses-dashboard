from __future__ import annotations

import sqlite3
from pathlib import Path

import app.ingestion as ingestion
from app.db import connect, get_state
from app.ingestion import (
    activate_snapshot,
    clean_orphan_snapshots,
    ingest_newest,
    scan_ready_candidates,
    validate_snapshot,
)


def row(identifier: str, amount: int = 100, deleted: str | None = None) -> tuple:
    return (
        identifier,
        "2026-09-05T10:00:00+07:00",
        amount,
        "IDR",
        "Bank",
        "card",
        "Merchant",
        "food_drink",
        "private note",
        deleted,
    )


def row_currency(identifier: str, amount: int, currency: str, deleted: str | None = None) -> tuple:
    return (
        identifier,
        "2026-09-05T10:00:00+07:00",
        amount,
        currency,
        "Bank",
        "card",
        "Merchant",
        "food_drink",
        "private note",
        deleted,
    )


def publish(settings, source_factory, stamp: str, rows: list[tuple], **kwargs) -> Path:
    path = settings.incoming_dir / f"expenses-{stamp}.sqlite3"
    source_factory(path, rows, **kwargs)
    (path.with_name(path.name + ".ready")).touch()
    return path


def test_scan_requires_strict_regular_pair_and_ignores_symlinks(settings, source_factory) -> None:
    valid = publish(settings, source_factory, "20260905T000000Z", [row("1")])
    source_factory(settings.incoming_dir / "expenses-latest.sqlite3", [row("2")])
    (settings.incoming_dir / "expenses-20260906T000000Z.sqlite3").symlink_to(valid)
    (settings.incoming_dir / "expenses-20260906T000000Z.sqlite3.ready").touch()
    assert [item.path for item in scan_ready_candidates(settings.incoming_dir)] == [valid]


def test_atomic_full_replacement_soft_delete_and_empty_snapshot(settings, source_factory) -> None:
    publish(settings, source_factory, "20260905T000000Z", [row("1"), row("2", deleted="x")])
    assert ingest_newest(settings)
    with connect(settings.database_path) as connection:
        assert connection.execute("SELECT id FROM expenses_projection").fetchall()[0][0] == "1"
        assert get_state(connection, "dataset_revision") == "1"
    publish(settings, source_factory, "20260906T000000Z", [])
    assert ingest_newest(settings)
    with connect(settings.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM expenses_projection").fetchone()[0] == 0
        assert get_state(connection, "dataset_revision") == "2"


def test_bad_newest_falls_back_and_preserves_last_good(settings, source_factory) -> None:
    first = publish(settings, source_factory, "20260905T000000Z", [row("old")])
    assert ingest_newest(settings)
    middle = publish(settings, source_factory, "20260906T000000Z", [row("new")])
    corrupt = settings.incoming_dir / "expenses-20260907T000000Z.sqlite3"
    corrupt.write_bytes(b"not sqlite")
    corrupt.with_name(corrupt.name + ".ready").touch()
    assert ingest_newest(settings)
    with connect(settings.database_path) as connection:
        assert connection.execute("SELECT id FROM expenses_projection").fetchone()[0] == "new"
        assert connection.execute(
            "SELECT COUNT(*) FROM imports WHERE status='failed'"
        ).fetchone()[0] == 1
    assert not ingest_newest(settings)
    first.unlink()
    middle.unlink()


def test_invalid_values_and_schema_do_not_replace_data(settings, source_factory) -> None:
    publish(settings, source_factory, "20260905T000000Z", [row("good")])
    assert ingest_newest(settings)
    publish(settings, source_factory, "20260906T000000Z", [row("bad", amount=0)])
    publish(settings, source_factory, "20260907T000000Z", [row("future")], migration=4)
    assert not ingest_newest(settings)
    with connect(settings.database_path) as connection:
        assert connection.execute("SELECT id FROM expenses_projection").fetchone()[0] == "good"
        assert get_state(connection, "dataset_revision") == "1"


def test_projection_omits_sensitive_source_fields(settings, source_factory) -> None:
    publish(settings, source_factory, "20260905T000000Z", [row("1")])
    ingest_newest(settings)
    with sqlite3.connect(settings.database_path) as connection:
        columns = {
            entry[1] for entry in connection.execute("PRAGMA table_info(expenses_projection)")
        }
    assert not {"receipt_path", "receipt_sha256", "raw_input", "source_ref"} & columns


def test_duplicate_content_advances_source_freshness_without_revision(
    settings, source_factory
) -> None:
    publish(settings, source_factory, "20260905T000000Z", [row("1")])
    assert ingest_newest(settings)
    publish(settings, source_factory, "20260906T000000Z", [row("1")])
    assert ingest_newest(settings)
    with connect(settings.database_path) as connection:
        assert get_state(connection, "dataset_revision") == "1"
        assert get_state(connection, "active_snapshot_filename") == (
            "expenses-20260906T000000Z.sqlite3"
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM imports WHERE status='duplicate'"
        ).fetchone()[0] == 1


def test_validation_streams_and_activation_uses_fixed_batches(
    settings, source_factory, monkeypatch
) -> None:
    rows = [row(f"expense-{index:04d}", amount=index + 1) for index in range(7)]
    publish(settings, source_factory, "20260905T000000Z", rows)
    candidate = scan_ready_candidates(settings.incoming_dir)[0]
    validated = validate_snapshot(candidate, settings)
    assert validated.row_count == 7
    assert not hasattr(validated, "rows")

    observed_batch_sizes: list[int] = []
    observed_connections: set[int] = set()
    original_insert = ingestion._insert_replacement_batch

    def observe_batch(connection, batch) -> None:
        observed_batch_sizes.append(len(batch))
        observed_connections.add(id(connection))
        assert connection.in_transaction
        original_insert(connection, batch)

    monkeypatch.setattr(ingestion, "IMPORT_BATCH_SIZE", 3)
    monkeypatch.setattr(ingestion, "_insert_replacement_batch", observe_batch)
    assert activate_snapshot(validated, settings) == 1
    assert observed_batch_sizes == [3, 3, 1]
    assert len(observed_connections) == 1
    with connect(settings.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM expenses_projection").fetchone()[0] == 7
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='expenses_projection_replacement'"
        ).fetchone() is None


def test_startup_cleanup_removes_only_unreferenced_snapshot_artifacts(
    settings, source_factory
) -> None:
    publish(settings, source_factory, "20260905T000000Z", [row("1")])
    assert ingest_newest(settings)
    with connect(settings.database_path) as connection:
        referenced = Path(
            connection.execute(
                "SELECT local_path FROM imports WHERE status='accepted'"
            ).fetchone()[0]
        )
        connection.execute(
            "CREATE TABLE expenses_projection_replacement AS "
            "SELECT * FROM expenses_projection"
        )
    orphan = settings.data_dir / "snapshots" / "crash-orphan.sqlite3"
    orphan.write_bytes(b"orphan")

    clean_orphan_snapshots(settings)

    assert referenced.is_file()
    assert not orphan.exists()
    with connect(settings.database_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='expenses_projection_replacement'"
        ).fetchone() is None


def test_batch_population_failure_preserves_active_projection(
    settings, source_factory, monkeypatch
) -> None:
    publish(settings, source_factory, "20260905T000000Z", [row("active")])
    assert ingest_newest(settings)
    publish(
        settings,
        source_factory,
        "20260906T000000Z",
        [row(f"replacement-{index}") for index in range(5)],
    )
    original_insert = ingestion._insert_replacement_batch
    calls = 0

    def fail_second_batch(connection, batch) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic write interruption")
        original_insert(connection, batch)

    monkeypatch.setattr(ingestion, "IMPORT_BATCH_SIZE", 2)
    monkeypatch.setattr(ingestion, "_insert_replacement_batch", fail_second_batch)
    assert not ingest_newest(settings)
    with connect(settings.database_path) as connection:
        assert connection.execute("SELECT id FROM expenses_projection").fetchone()[0] == "active"
        assert get_state(connection, "dataset_revision") == "1"
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='expenses_projection_replacement'"
        ).fetchone() is None


def test_replacement_population_keeps_wal_readers_on_active_projection(
    settings, source_factory
) -> None:
    publish(settings, source_factory, "20260905T000000Z", [row("active")])
    assert ingest_newest(settings)
    publish(
        settings,
        source_factory,
        "20260906T000000Z",
        [row("new-1"), row("new-2")],
    )
    validated = validate_snapshot(scan_ready_candidates(settings.incoming_dir)[0], settings)
    reader = connect(settings.database_path, readonly=True)
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT id FROM expenses_projection").fetchone()[0] == "active"
        ingestion._populate_replacement(
            validated.staging_path, validated.row_count, settings
        )
        assert reader.execute("SELECT id FROM expenses_projection").fetchone()[0] == "active"
        reader.execute("COMMIT")
    finally:
        reader.close()
    with connect(settings.database_path) as connection:
        assert connection.execute("SELECT id FROM expenses_projection").fetchone()[0] == "active"
        assert connection.execute(
            "SELECT COUNT(*) FROM expenses_projection_replacement"
        ).fetchone()[0] == 2
    clean_orphan_snapshots(settings)


def test_foreign_currency_row_does_not_abort_snapshot(settings, source_factory) -> None:
    publish(
        settings,
        source_factory,
        "20260905T000000Z",
        [row("idr"), row_currency("sgd", 138, "SGD"), row_currency("myr", 250, "MYR")],
    )
    assert ingest_newest(settings)
    with connect(settings.database_path) as connection:
        rows = {
            row["id"]: (row["amount_minor"], row["currency"])
            for row in connection.execute(
                "SELECT id, amount_minor, currency FROM expenses_projection ORDER BY id"
            )
        }
        assert rows == {"idr": (100, "IDR"), "myr": (250, "MYR"), "sgd": (138, "SGD")}
        assert connection.execute(
            "SELECT COUNT(*) FROM imports WHERE status='failed'"
        ).fetchone()[0] == 0


def test_projection_accepts_new_currency_codes_after_migration(settings, source_factory) -> None:
    # The v1 schema restricted currency to IDR/USD; migration 002 must relax it.
    with connect(settings.database_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM app_migrations WHERE version=2"
        ).fetchone() is not None
        connection.execute(
            "INSERT INTO expenses_projection VALUES("
            "'x','2026-09-05T03:00:00+00:00','2026-09-05',138,'SGD',"
            "NULL,NULL,'M','food_drink',NULL)"
        )
        assert connection.execute(
            "SELECT currency FROM expenses_projection WHERE id='x'"
        ).fetchone()[0] == "SGD"
