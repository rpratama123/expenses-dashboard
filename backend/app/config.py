from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    incoming_dir: Path
    data_dir: Path
    poll_seconds: int
    fx_poll_seconds: int
    report_timezone: str
    public_origin: str | None
    max_import_bytes: int
    snapshot_retention: int
    static_dir: Path

    @classmethod
    def from_env(cls) -> Settings:
        timezone = os.getenv("REPORT_TIMEZONE", "Asia/Jakarta")
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"REPORT_TIMEZONE is not an IANA timezone: {timezone}") from exc
        origin = os.getenv("PUBLIC_ORIGIN") or None
        if origin:
            parsed = urlparse(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise ValueError("PUBLIC_ORIGIN must be an http(s) origin without a path")
        return cls(
            incoming_dir=Path(os.getenv("INCOMING_DIR", "/incoming")),
            data_dir=Path(os.getenv("DATA_DIR", "/data")),
            poll_seconds=_positive_int("POLL_SECONDS", 30),
            fx_poll_seconds=_positive_int("FX_POLL_SECONDS", 3600),
            report_timezone=timezone,
            public_origin=origin.rstrip("/") if origin else None,
            max_import_bytes=_positive_int("MAX_IMPORT_BYTES", 512 * 1024 * 1024),
            snapshot_retention=_positive_int("SNAPSHOT_RETENTION", 2),
            static_dir=Path(os.getenv("STATIC_DIR", "/app/static")),
        )

    @property
    def database_path(self) -> Path:
        return self.data_dir / "dashboard.sqlite3"

    def initialize_paths(self) -> None:
        if not self.incoming_dir.is_dir():
            raise RuntimeError(f"INCOMING_DIR is not a directory: {self.incoming_dir}")
        for path in (self.data_dir, self.data_dir / "staging", self.data_dir / "snapshots"):
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write-test"
            try:
                probe.touch(exist_ok=False)
                probe.unlink()
            except OSError as exc:
                raise RuntimeError(f"path is not writable: {path}") from exc
