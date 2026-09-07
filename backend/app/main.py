from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .db import initialize
from .digest_routes import router as digest_router
from .fx import maintain_fx, reconcile_needed_rates
from .ingestion import clean_orphan_snapshots, clean_staging, ingest_newest
from .routes import router as api_router

LOGGER = logging.getLogger("expenses_dashboard")


def _ingest_and_backfill(
    settings: Settings, *, stop_event: threading.Event | None = None
) -> None:
    if ingest_newest(settings):
        reconcile_needed_rates(settings, stop_event=stop_event)


async def _run_background(action, settings: Settings, stop_event: threading.Event) -> None:
    try:
        await asyncio.to_thread(action, settings, stop_event=stop_event)
    except asyncio.CancelledError:
        raise
    except Exception:
        LOGGER.exception("background maintenance failed")


async def _periodic(
    interval: int, action, settings: Settings, stop_event: threading.Event
) -> None:
    while True:
        await asyncio.sleep(interval)
        await _run_background(action, settings, stop_event)


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.ready = False
        configured.initialize_paths()
        initialize(configured.database_path)
        clean_staging(configured)
        clean_orphan_snapshots(configured)
        await asyncio.to_thread(ingest_newest, configured)
        app.state.ready = True
        stop_event = threading.Event()
        tasks = [
            asyncio.create_task(
                _run_background(reconcile_needed_rates, configured, stop_event),
                name="initial-fx-reconciler",
            ),
            asyncio.create_task(
                _periodic(
                    configured.poll_seconds,
                    _ingest_and_backfill,
                    configured,
                    stop_event,
                ),
                name="snapshot-poller",
            ),
            asyncio.create_task(
                _periodic(
                    configured.fx_poll_seconds, maintain_fx, configured, stop_event
                ),
                name="fx-reconciler",
            ),
        ]
        try:
            yield
        finally:
            app.state.ready = False
            stop_event.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(
        title="Expenses Dashboard API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = configured
    app.state.ready = False
    if configured.public_origin:
        hostname = urlparse(configured.public_origin).hostname
        allowed_hosts = ["127.0.0.1", "localhost"]
        if hostname and hostname not in allowed_hosts:
            allowed_hosts.append(hostname)
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    @app.middleware("http")
    async def privacy_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; manifest-src 'self'; "
            "worker-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; "
            "form-action 'self'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = []
        for error in exc.errors():
            details.append(
                {
                    "location": [str(part) for part in error["loc"]],
                    "message": error["msg"],
                    "type": error["type"],
                }
            )
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "details": details}},
        )

    @app.get("/health/live", include_in_schema=False)
    def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready", include_in_schema=False)
    def ready(request: Request) -> JSONResponse:
        status = 200 if request.app.state.ready else 503
        return JSONResponse(
            {"status": "ready" if status == 200 else "initializing"}, status_code=status
        )

    app.include_router(api_router)
    app.include_router(digest_router)

    assets = configured.static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            return JSONResponse(
                {"detail": {"code": "not_found", "message": "API route not found"}},
                status_code=404,
            )
        static_root = configured.static_dir.resolve()
        requested = (static_root / path).resolve()
        if requested.is_relative_to(static_root) and requested.is_file():
            return FileResponse(requested)
        index = static_root / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse({"detail": "Frontend is not installed"}, status_code=404)

    return app


app = create_app()
