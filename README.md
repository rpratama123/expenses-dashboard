# Expenses Dashboard

A mobile-first, read-only dashboard for complete SQLite expense snapshots. A single FastAPI process serves the API and built React application; SQLite application state, snapshot ingestion, and historical FX reference rates require no external database or worker.

The intended production path is Cloudflare Tunnel to Nginx Proxy Manager (NPM) to the container. NPM Basic Auth is the access control boundary. The application itself has no login and must not be exposed around that boundary.

## Documentation

- [Unraid deployment](docs/deployment-unraid.md)
- [Source data contract](docs/data-contract.md)
- [Daily digest API](docs/api-digest.md)
- [Recovery](docs/recovery.md)
- [Privacy and offline behavior](docs/privacy-offline.md)
- [Performance baseline](docs/performance.md)

## Local development

Requirements are Python 3.12+, [uv](https://docs.astral.sh/uv/), and Node.js/npm. From the repository root:

```sh
uv sync --project backend --frozen
uv run --project backend ruff check backend
uv run --project backend pytest backend/tests
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test -- --run
npm --prefix frontend run generate:icons
npm --prefix frontend run build
```

For local-only data, use directories outside the repository and do not commit source snapshots. In separate terminals, start the API and Vite development server:

```sh
INCOMING_DIR=/absolute/path/to/incoming \
DATA_DIR=/absolute/path/to/dashboard-data \
PUBLIC_ORIGIN=http://localhost:5173 \
PYTHONPATH=backend \
uv run --project backend uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

```sh
npm --prefix frontend run dev
```

Vite serves `http://localhost:5173` and proxies `/api` and `/health` to the local API. The production defaults and complete variable names are in `.env.example`.

## Container

Create `.env` from `.env.example`, set the real HTTPS `PUBLIC_ORIGIN`, UID/GID, and existing NPM network, then validate and build:

```sh
docker compose config
docker compose build
docker compose up -d
```

The architecture-neutral base image tags allow Docker to select the host architecture; the Dockerfile does not force `amd64` or another platform. The final image contains neither Node.js nor the sample database. It runs one non-root Uvicorn worker on port 8000 with a read-only root filesystem. Only `/data` and the bounded `/tmp` tmpfs are writable; `/incoming` is read-only.

## Operating model

The producer publishes a consistent standalone database and then its exact-name `.ready` marker. The application polls for completed pairs, validates and copies a candidate, and atomically replaces its projection. It never modifies or removes incoming files. Failed imports or FX refreshes leave the last known good data available. See the data contract before configuring a producer.

IDR amounts have scale 1; USD, SGD, and MYR have scale 100 and are converted with stored historical ECB reference rates by the expense's Asia/Jakarta date. Conversion rounds each transaction to whole rupiah using decimal `ROUND_HALF_UP`; aggregates sum those rounded transaction values. Each currency is fetched independently, and missing or provisional FX states remain visible.

Offline support is deliberately bounded to the app shell and exact API views that were successfully visited. It is not a full offline copy, and browser storage can be evicted. Cached financial data remains on a trusted device after NPM credentials are revoked until it is cleared or evicted. See [privacy and offline behavior](docs/privacy-offline.md).

## API

Dashboard endpoints are under `/api/v1`. The stable automation exception is `GET /api/digest/daily`; it is protected by the same NPM Basic Auth and intentionally has a flat response with numeric whole-rupiah totals. See [the digest contract](docs/api-digest.md).

Health endpoints are `/health/live` and `/health/ready`. A missing first snapshot is an application state rather than a reason to restart the process.
