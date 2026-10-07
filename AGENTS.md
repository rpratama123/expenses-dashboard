# AGENTS.md

Mobile-first, read-only expenses dashboard. One FastAPI process serves the API and the
built React app; SQLite only. No CI, no pre-commit, no workspace tooling at the root.
Commands are run from the repository root with explicit project/prefix flags.

## Layout

- `backend/` — FastAPI app (`app/`), stdlib `sqlite3`, `uv` project, `uv.lock`. Tests in `backend/tests/`.
- `frontend/` — React 19 + Vite + TypeScript, PWA/Workbox, Dexie offline cache, `npm`. Unit tests (Vitest) live beside sources; e2e in `frontend/e2e/`.
- `docs/` — authoritative contracts. Read the relevant one before changing behavior: `data-contract.md`, `api-digest.md`, `deployment-unraid.md`, `recovery.md`, `privacy-offline.md`, `performance.md`.
- `sample/` — `favicon.svg` is the icon source of truth; `sample/expenses.sqlite3` is the only committed database (gitignored `*.sqlite3` has an exception for it).
- `Dockerfile` / `compose.yaml` — multi-stage image; final image has no Node and no sample DB. Compose targets Unraid behind Nginx Proxy Manager Basic Auth.

## Commands (run from root)

```sh
uv sync --project backend --frozen
uv run --project backend ruff check backend
uv run --project backend pytest backend/tests
uv run --project backend pytest backend/tests/test_digest.py   # single file
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test -- --run    # `--run` is required; bare `test` is Vitest watch mode
npm --prefix frontend run generate:icons
npm --prefix frontend run build            # prebuild regenerates icons, then tsc -b && vite build
npm --prefix frontend exec playwright install --with-deps
npm --prefix frontend run test:e2e
```

- No lint/format task runner: Ruff from the backend venv, ESLint via npm. There is no `make`.
- E2E (`playwright.config.ts`) mocks `**/api/v1/**` and runs `vite preview` on `:4173`; it does not need the backend. Browser binaries must be installed first.
- Icons are generated from `sample/favicon.svg` by `scripts/generate-icons.mjs` (path resolved relative to the script, not cwd). Do not hand-edit generated PNGs; rerun `generate:icons`.

## Architecture facts that are easy to get wrong

- **Single Uvicorn worker is a correctness requirement.** `--workers 1` (Dockerfile) because lifespan starts snapshot-polling and FX-reconciliation tasks; more workers duplicate schedulers.
- FastAPI serves `/api/v1/*`, `/health/*`, static assets, and an SPA fallback that must never return HTML for `/api/*`. See `backend/app/main.py`.
- App and source schemas are separate: dashboard tables live in `backend/app/migrations/001_initial.sql`; producer snapshots carry their own `schema_migrations` (supported versions 1–3).
- Snapshot ingestion (`backend/app/ingestion.py`) accepts only exact `expenses-YYYYMMDDTHHMMSSZ.sqlite3` + `.ready` pairs, copies to `/data`, validates read-only, and atomically replaces the whole `expenses_projection`. It never mutates or deletes `/incoming`.
- Money is integer/Decimal only. Scales are fixed: IDR 1 (`5000` = Rp5,000), USD 100 (`566` = US$5.66). USD uses stored historical ECB rates by the expense's Asia/Jakarta date, `ROUND_HALF_UP` per transaction; never invent or use a future rate. Centralized in `backend/app/money.py`.
- `GET /api/digest/daily` (no `/v1`) is an intentional exception to the dashboard envelope: a flat body with **numeric** whole-rupiah totals and required `date`/`timezone` params. Do not "unify" it with `/api/v1` responses. Contract in `docs/api-digest.md`.
- Every UI API response is a revisioned envelope (`api_schema_version`, `dataset_revision`, `fx_revision`, `source_timestamp`, `conversion`). Cached offline views must never mix revisions; financial responses are `Cache-Control: no-store`.
- `PUBLIC_ORIGIN` drives `TrustedHostMiddleware`; it is required by `compose.yaml` and must be an exact `http(s)` origin with no path.

## Conventions and constraints

- Python 3.12+; Ruff `line-length = 100`, lint rules `E,F,I,UP,B,SIM`. TypeScript strict, `noUnusedLocals`/`noUnusedParameters`.
- `pytest` pythonpath is set to `backend` (see `pyproject.toml`), so tests import `app.*`; fixture `source_factory` in `backend/tests/conftest.py` builds synthetic source snapshots.
- Never commit runtime state or real financial data: `.env`, `*.sqlite3` (except the sample), `/data` staging/snapshots, `frontend/dist`, test artifacts. `.dockerignore`/`.gitignore` already encode this.
- Application is unauthenticated by design; NPM Basic Auth is the only boundary. Do not add login, write, filesystem-download, SQL, or debug endpoints.
- Keep logs free of transaction bodies, notes, and credentials.

## Deploy / ops

- Validate compose changes with `docker compose config`; build with `docker compose build`. Do not pass `--platform`.
- Container runs non-root with a read-only root FS, `/data` writable, `/incoming` read-only, and a bounded `/tmp` tmpfs.
- Backup/restore and FX-failure behavior are documented in `docs/recovery.md`; a WAL database must not be backed up by copying only the main file.
