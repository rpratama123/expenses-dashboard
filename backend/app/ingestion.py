from __future__ import annotations

import hashlib
import os
import re
import shutil
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings
from .db import connect, get_state, set_state, utc_now
from .money import validate_amount

SNAPSHOT_RE = re.compile(r"^expenses-(\d{8}T\d{6}Z)\.sqlite3$")
REQUIRED_COLUMNS = {
    "id",
    "expense_at",
    "amount_minor",
    "currency",
    "bank",
    "payment_method",
    "merchant",
    "category",
    "note",
    "deleted_at",
}
MAX_FAILURE_REASON = 500
IMPORT_BATCH_SIZE = 1_000
REPLACEMENT_TABLE = "expenses_projection_replacement"


@dataclass(frozen=True, slots=True)
class Candidate:
    path: Path
    marker: Path
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class ValidatedSnapshot:
    candidate: Candidate
    staging_path: Path
    sha256: str
    source_identity: str
    row_count: int


def _regular_not_symlink(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink()
    except OSError:
        return False


def scan_ready_candidates(incoming_dir: Path) -> list[Candidate]:
    candidates: list[Candidate] = []
    try:
        entries = list(incoming_dir.iterdir())
    except OSError:
        return []
    for path in entries:
        match = SNAPSHOT_RE.fullmatch(path.name)
        if not match or not _regular_not_symlink(path):
            continue
        marker = path.with_name(path.name + ".ready")
        if not _regular_not_symlink(marker):
            continue
        try:
            timestamp = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError:
            continue
        candidates.append(Candidate(path, marker, timestamp))
    return sorted(candidates, key=lambda item: item.timestamp, reverse=True)


def _copy_bounded(candidate: Candidate, settings: Settings) -> tuple[Path, str, str]:
    before = candidate.path.stat(follow_symlinks=False)
    if before.st_size > settings.max_import_bytes:
        raise ValueError("snapshot exceeds MAX_IMPORT_BYTES")
    identity = f"{before.st_dev}:{before.st_ino}:{before.st_size}:{before.st_mtime_ns}"
    staging = settings.data_dir / "staging" / f"{candidate.path.name}.{os.getpid()}.tmp"
    digest = hashlib.sha256()
    total = 0
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(candidate.path, flags)
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as source, staging.open("xb") as target:
            while block := source.read(1024 * 1024):
                total += len(block)
                if total > settings.max_import_bytes:
                    raise ValueError("snapshot exceeds MAX_IMPORT_BYTES while copying")
                digest.update(block)
                target.write(block)
            target.flush()
            os.fsync(target.fileno())
    except Exception:
        staging.unlink(missing_ok=True)
        raise
    after = candidate.path.stat(follow_symlinks=False)
    after_identity = f"{after.st_dev}:{after.st_ino}:{after.st_size}:{after.st_mtime_ns}"
    if identity != after_identity or total != before.st_size:
        staging.unlink(missing_ok=True)
        raise ValueError("snapshot changed while being copied")
    return staging, digest.hexdigest(), identity


def _parse_expense_at(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("expense_at must be text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid expense_at timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("expense_at must include a UTC offset")
    return parsed


def _open_snapshot(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.enable_load_extension(False)
    connection.execute("PRAGMA trusted_schema=OFF")
    connection.execute("PRAGMA query_only=ON")
    return connection


def _validate_source_schema(connection: sqlite3.Connection) -> None:
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise ValueError(f"integrity check failed: {integrity}")
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('expenses', 'schema_migrations')"
        )
    }
    if tables != {"expenses", "schema_migrations"}:
        raise ValueError("required source tables are missing")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(expenses)")}
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise ValueError(f"required expense columns are missing: {', '.join(sorted(missing))}")
    migration_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(schema_migrations)")
    }
    if "version" not in migration_columns:
        raise ValueError("source migration version is unavailable")
    maximum = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    if maximum is None or not isinstance(maximum, int) or maximum < 1 or maximum > 3:
        raise ValueError(f"unsupported source schema migration: {maximum}")
    duplicate = connection.execute(
        "SELECT id FROM expenses WHERE deleted_at IS NULL "
        "GROUP BY id HAVING COUNT(*) > 1 LIMIT 1"
    ).fetchone()
    if duplicate is not None:
        raise ValueError("expense IDs must be unique")


def _normalized_rows(
    connection: sqlite3.Connection, settings: Settings
) -> Iterator[tuple[object, ...]]:
    source_rows = connection.execute(
        "SELECT id, expense_at, amount_minor, currency, bank, payment_method, merchant, "
        "category, note FROM expenses WHERE deleted_at IS NULL ORDER BY id"
    )
    jakarta = ZoneInfo(settings.report_timezone)
    for row in source_rows:
        if not isinstance(row["id"], str) or not row["id"]:
            raise ValueError("expense IDs must be nonempty text")
        currency = row["currency"]
        if not isinstance(currency, str):
            raise ValueError("currency must be text")
        validate_amount(row["amount_minor"], currency)
        instant = _parse_expense_at(row["expense_at"])
        merchant = row["merchant"]
        category = row["category"]
        if merchant is not None and not isinstance(merchant, str):
            raise ValueError("merchant must be text or null")
        if not isinstance(category, str) or not category.strip():
            raise ValueError("category must be nonempty text")
        for field in ("bank", "payment_method", "note"):
            if row[field] is not None and not isinstance(row[field], str):
                raise ValueError(f"{field} must be text or null")
        instant_utc = instant.astimezone(UTC)
        yield (
            row["id"],
            instant_utc.isoformat(),
            instant_utc.astimezone(jakarta).date().isoformat(),
            row["amount_minor"],
            currency,
            row["bank"],
            row["payment_method"],
            merchant,
            category,
            row["note"],
        )


def validate_snapshot(candidate: Candidate, settings: Settings) -> ValidatedSnapshot:
    staging, sha256, identity = _copy_bounded(candidate, settings)
    connection: sqlite3.Connection | None = None
    try:
        connection = _open_snapshot(staging)
        _validate_source_schema(connection)
        row_count = sum(1 for _ in _normalized_rows(connection, settings))
        return ValidatedSnapshot(candidate, staging, sha256, identity, row_count)
    except Exception:
        staging.unlink(missing_ok=True)
        raise
    finally:
        if connection is not None:
            connection.close()


def _record_failure(settings: Settings, candidate: Candidate, reason: str) -> None:
    try:
        stat = candidate.path.stat(follow_symlinks=False)
        identity = f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}"
    except OSError:
        identity = "source-disappeared"
    with connect(settings.database_path) as connection:
        connection.execute(
            "INSERT INTO imports(filename, source_timestamp, source_identity, status, "
            "failure_reason, imported_at) VALUES(?, ?, ?, 'failed', ?, ?)",
            (
                candidate.path.name,
                candidate.timestamp.isoformat(),
                identity,
                reason[:MAX_FAILURE_REASON],
                utc_now(),
            ),
        )


def activate_snapshot(snapshot: ValidatedSnapshot, settings: Settings) -> int:
    final_path = settings.data_dir / "snapshots" / snapshot.candidate.path.name
    if final_path.exists():
        final_path = final_path.with_name(f"{final_path.name}.{snapshot.sha256[:12]}")
    os.replace(snapshot.staging_path, final_path)
    _populate_replacement(final_path, snapshot.row_count, settings)
    with connect(settings.database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        replacement_count = connection.execute(
            f"SELECT COUNT(*) FROM {REPLACEMENT_TABLE}"
        ).fetchone()[0]
        if replacement_count != snapshot.row_count:
            raise RuntimeError("replacement row count changed before activation")
        revision = int(get_state(connection, "dataset_revision") or "0") + 1
        connection.execute("DELETE FROM expenses_projection")
        connection.execute(
            "INSERT INTO expenses_projection SELECT * FROM expenses_projection_replacement"
        )
        imported_at = utc_now()
        connection.execute(
            "INSERT INTO imports(filename, source_timestamp, source_identity, sha256, status, "
            "imported_at, row_count, dataset_revision, local_path) "
            "VALUES(?, ?, ?, ?, 'accepted', ?, ?, ?, ?)",
            (
                snapshot.candidate.path.name,
                snapshot.candidate.timestamp.isoformat(),
                snapshot.source_identity,
                snapshot.sha256,
                imported_at,
                snapshot.row_count,
                revision,
                str(final_path),
            ),
        )
        for key, value in {
            "dataset_revision": str(revision),
            "active_snapshot_filename": snapshot.candidate.path.name,
            "active_snapshot_timestamp": snapshot.candidate.timestamp.isoformat(),
            "active_snapshot_sha256": snapshot.sha256,
            "active_imported_at": imported_at,
        }.items():
            set_state(connection, key, value)
        connection.execute(f"DROP TABLE {REPLACEMENT_TABLE}")
        connection.commit()
    _prune_snapshots(settings)
    return revision


def _populate_replacement(snapshot_path: Path, expected_count: int, settings: Settings) -> None:
    source = _open_snapshot(snapshot_path)
    try:
        with connect(settings.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(f"DROP TABLE IF EXISTS {REPLACEMENT_TABLE}")
            connection.execute(
                f"CREATE TABLE {REPLACEMENT_TABLE} AS "
                "SELECT * FROM expenses_projection WHERE 0"
            )
            batch: list[tuple[object, ...]] = []
            inserted = 0
            for row in _normalized_rows(source, settings):
                batch.append(row)
                if len(batch) == IMPORT_BATCH_SIZE:
                    _insert_replacement_batch(connection, batch)
                    inserted += len(batch)
                    batch.clear()
            if batch:
                _insert_replacement_batch(connection, batch)
                inserted += len(batch)
            if inserted != expected_count:
                raise RuntimeError("validated snapshot row count changed before activation")
            connection.commit()
    except Exception:
        with connect(settings.database_path) as connection:
            connection.execute(f"DROP TABLE IF EXISTS {REPLACEMENT_TABLE}")
        raise
    finally:
        source.close()


def _insert_replacement_batch(
    connection: sqlite3.Connection, batch: list[tuple[object, ...]]
) -> None:
    connection.executemany(
        f"INSERT INTO {REPLACEMENT_TABLE} VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch
    )


def _record_duplicate(snapshot: ValidatedSnapshot, settings: Settings) -> None:
    final_path = settings.data_dir / "snapshots" / snapshot.candidate.path.name
    if final_path.exists():
        final_path = final_path.with_name(f"{final_path.name}.{snapshot.sha256[:12]}")
    os.replace(snapshot.staging_path, final_path)
    with connect(settings.database_path) as connection:
        revision = int(get_state(connection, "dataset_revision") or "0")
        imported_at = utc_now()
        connection.execute(
            "INSERT INTO imports(filename, source_timestamp, source_identity, sha256, status, "
            "imported_at, row_count, dataset_revision, local_path) "
            "VALUES(?, ?, ?, ?, 'duplicate', ?, ?, ?, ?)",
            (
                snapshot.candidate.path.name,
                snapshot.candidate.timestamp.isoformat(),
                snapshot.source_identity,
                snapshot.sha256,
                imported_at,
                snapshot.row_count,
                revision,
                str(final_path),
            ),
        )
        for key, value in {
            "active_snapshot_filename": snapshot.candidate.path.name,
            "active_snapshot_timestamp": snapshot.candidate.timestamp.isoformat(),
            "active_snapshot_sha256": snapshot.sha256,
            "active_imported_at": imported_at,
        }.items():
            set_state(connection, key, value)
    _prune_snapshots(settings)


def _prune_snapshots(settings: Settings) -> None:
    with connect(settings.database_path) as connection:
        rows = connection.execute(
            "SELECT local_path FROM imports WHERE status IN ('accepted', 'duplicate') "
            "ORDER BY id DESC"
        ).fetchall()
    for row in rows[settings.snapshot_retention :]:
        Path(row["local_path"]).unlink(missing_ok=True)


def clean_staging(settings: Settings) -> None:
    for path in (settings.data_dir / "staging").iterdir():
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)


def clean_orphan_snapshots(settings: Settings) -> None:
    with connect(settings.database_path) as connection:
        referenced = {
            Path(row["local_path"]).absolute()
            for row in connection.execute(
                "SELECT local_path FROM imports WHERE local_path IS NOT NULL"
            )
        }
        connection.execute(f"DROP TABLE IF EXISTS {REPLACEMENT_TABLE}")
    snapshots = settings.data_dir / "snapshots"
    for path in snapshots.iterdir():
        if (path.is_file() or path.is_symlink()) and path.absolute() not in referenced:
            path.unlink(missing_ok=True)


def ingest_newest(settings: Settings) -> bool:
    with connect(settings.database_path) as connection:
        active_timestamp = get_state(connection, "active_snapshot_timestamp")
        accepted_rows = connection.execute(
            "SELECT filename, sha256, source_identity FROM imports WHERE status='accepted'"
        ).fetchall()
        accepted = {row["filename"]: row["sha256"] for row in accepted_rows}
        accepted_identities = {row["filename"]: row["source_identity"] for row in accepted_rows}
        failed = {
            (row["filename"], row["source_identity"])
            for row in connection.execute(
                "SELECT filename, source_identity FROM imports WHERE status='failed'"
            )
        }
    active = datetime.fromisoformat(active_timestamp) if active_timestamp else None
    for candidate in scan_ready_candidates(settings.incoming_dir):
        stat = candidate.path.stat(follow_symlinks=False)
        identity = f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}"
        if candidate.path.name in accepted:
            if accepted_identities[candidate.path.name] == identity:
                continue
            try:
                reused = validate_snapshot(candidate, settings)
                reused.staging_path.unlink(missing_ok=True)
                if reused.sha256 != accepted[candidate.path.name]:
                    _record_failure(
                        settings,
                        candidate,
                        "accepted filename was reused with changed content",
                    )
                else:
                    with connect(settings.database_path) as connection:
                        connection.execute(
                            "UPDATE imports SET source_identity=? WHERE filename=? "
                            "AND status='accepted'",
                            (identity, candidate.path.name),
                        )
            except Exception as exc:
                _record_failure(settings, candidate, str(exc))
            continue
        if active and candidate.timestamp <= active:
            continue
        if (candidate.path.name, identity) in failed:
            continue
        try:
            snapshot = validate_snapshot(candidate, settings)
            prior_hash = accepted.get(candidate.path.name)
            if prior_hash and prior_hash != snapshot.sha256:
                snapshot.staging_path.unlink(missing_ok=True)
                raise ValueError("accepted filename was reused with changed content")
            if snapshot.sha256 in accepted.values():
                _record_duplicate(snapshot, settings)
                return True
            activate_snapshot(snapshot, settings)
            return True
        except Exception as exc:
            _record_failure(settings, candidate, str(exc))
            continue
    return False
