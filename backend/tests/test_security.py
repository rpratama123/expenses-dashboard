from __future__ import annotations

import threading
import time
from dataclasses import replace

from fastapi.testclient import TestClient

from app.main import create_app


def test_trusted_host_keeps_local_health_probes_and_public_origin(settings) -> None:
    configured = replace(settings, public_origin="https://expenses.example.com")
    with TestClient(create_app(configured)) as client:
        for host in ("127.0.0.1:8000", "localhost:8000", "expenses.example.com"):
            response = client.get("/health/ready", headers={"host": host})
            assert response.status_code == 200
        rejected = client.get("/health/ready", headers={"host": "attacker.example"})
        assert rejected.status_code == 400


def test_csp_allows_built_ui_resources_without_unsafe_scripts(settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/live")
    policy = response.headers["content-security-policy"]
    directives = {part.strip() for part in policy.split(";") if part.strip()}
    assert "default-src 'none'" in directives
    assert "script-src 'self'" in directives
    assert "style-src 'self' 'unsafe-inline'" in directives
    assert "connect-src 'self'" in directives
    assert "worker-src 'self'" in directives
    assert "manifest-src 'self'" in directives
    assert "object-src 'none'" in directives
    assert "frame-ancestors 'none'" in directives
    script_policy = next(item for item in directives if item.startswith("script-src"))
    assert "'unsafe-inline'" not in script_policy
    assert "'unsafe-eval'" not in script_policy


def test_slow_initial_fx_reconciliation_does_not_block_readiness(
    settings, monkeypatch
) -> None:
    started = threading.Event()
    finished = threading.Event()

    def blocked_reconciliation(_settings, *, stop_event=None) -> int:
        started.set()
        assert stop_event is not None
        stop_event.wait(timeout=2)
        finished.set()
        return 0

    monkeypatch.setattr("app.main.reconcile_needed_rates", blocked_reconciliation)
    before = time.monotonic()
    with TestClient(create_app(settings)) as client:
        startup_elapsed = time.monotonic() - before
        assert startup_elapsed < 1
        assert started.wait(timeout=1)
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}
    assert finished.wait(timeout=1)
