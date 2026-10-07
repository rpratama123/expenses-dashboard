from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    else:
        connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    if readonly:
        connection.execute("PRAGMA query_only=ON")
    return connection


def initialize(path: Path) -> None:
    migrations_dir = Path(__file__).with_name("migrations")
    with connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        # Create the ledger before consulting it so it exists on a fresh database.
        connection.executescript(
            "CREATE TABLE IF NOT EXISTS app_migrations ("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {
            row[0] for row in connection.execute("SELECT version FROM app_migrations")
        }
        for migration in sorted(migrations_dir.glob("*.sql")):
            version = int(migration.name.split("_", 1)[0])
            if version in applied:
                continue
            connection.executescript(migration.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT OR IGNORE INTO app_migrations(version, applied_at) VALUES(?, ?)",
                (version, utc_now()),
            )
            applied.add(version)


@contextmanager
def read_transaction(path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(path, readonly=True)
    try:
        connection.execute("BEGIN")
        yield connection
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def get_state(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_state(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        "INSERT INTO app_state(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
