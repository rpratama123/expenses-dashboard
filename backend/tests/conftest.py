from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.config import Settings
from app.db import initialize


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    incoming = tmp_path / "incoming"
    data = tmp_path / "data"
    static = tmp_path / "static"
    incoming.mkdir()
    static.mkdir()
    configured = Settings(
        incoming_dir=incoming,
        data_dir=data,
        poll_seconds=3600,
        fx_poll_seconds=3600,
        report_timezone="Asia/Jakarta",
        public_origin=None,
        max_import_bytes=10 * 1024 * 1024,
        snapshot_retention=2,
        static_dir=static,
    )
    configured.initialize_paths()
    initialize(configured.database_path)
    return configured


def create_source(path: Path, rows: list[tuple] | None = None, *, migration: int = 3) -> None:
    rows = rows or []
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, description TEXT NOT NULL
        );
        CREATE TABLE expenses (
            id TEXT PRIMARY KEY, expense_at TEXT NOT NULL, amount_minor INTEGER NOT NULL,
            currency TEXT NOT NULL, bank TEXT, payment_method TEXT, merchant TEXT,
            category TEXT NOT NULL, note TEXT, deleted_at TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO schema_migrations VALUES(?, '2026-01-01T00:00:00Z', 'test')",
        (migration,),
    )
    connection.executemany(
        "INSERT INTO expenses VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
    )
    connection.commit()
    connection.close()


@pytest.fixture
def source_factory():
    return create_source
