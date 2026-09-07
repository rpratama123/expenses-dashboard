# Objective

Build a clean, mobile-first, read-only expenses dashboard with Summary, Transactions, and Settings pages. Deploy one Docker container on Unraid, behind Nginx Proxy Manager (NPM) Basic Auth and a Cloudflare Tunnel. Support installation on the iOS Home Screen and offline viewing of previously visited data.

# Current State

- Repository has `LICENSE`, `sample/expenses.sqlite3`, and local OpenCode tooling. There is no application, application build configuration, test suite, or existing UI convention to preserve. OpenCode dependencies are not application dependencies.
- `sample/favicon.svg` is the user-selected source artwork: a 64×64 receipt illustration with a rounded dark-green (`#17221d`) background, warm-white paper, green strokes, and an orange accent. Preserve this file and use its artwork for browser favicons and generated installation icons.
- Sample SQLite was inspected read-only and passes `PRAGMA quick_check`. It has schema migrations 1–3 and uses WAL mode.
- `expenses` contains `id`, `expense_at`, `amount_minor`, `currency`, `bank`, `payment_method`, `merchant`, `category`, `note`, receipt/provenance fields, creation/update timestamps, and `deleted_at`. Existing indexes cover date, category, and receipt hash.
- Other tables: `audit_log`, `email_ingestion`, `expense_classifications`, `merchant_category_rules`, and `schema_migrations`. These are not required for the initial dashboard and contain unnecessary sensitive information.
- Sample has 16 expenses, no deleted rows, 15 IDR rows and one USD row. Expense timestamps use UTC+7. Despite its name, `amount_minor` has currency-specific semantics: IDR 5000 is Rp5,000; USD 566 is US$5.66. This was confirmed with the user.
- User confirmed complete, consistent replacement snapshots, read-only transactions, historical exchange rates, Asia/Jakarta reporting, previously viewed offline data, and single-user NPM Basic Auth.
- Incoming host directory: `/mnt/user/webdav/expenses`. Completed uploads have matching names `expenses-YYYYMMDDTHHMMSSZ.sqlite3` and `expenses-YYYYMMDDTHHMMSSZ.sqlite3.ready`.
- Persistent application host directory: `/mnt/user/appdata/expenses-dashboard`.
- Frankfurter documentation at `https://frankfurter.dev/` describes a free, no-key daily/historical API. The endpoint `https://api.frankfurter.dev/v2/rate/USD/IDR?providers=ECB&date=2026-08-28` was verified to return a dated USD/IDR rate. Provider availability is not an SLA.

# Requirements

## Functional

- Summary: current-month default, date-range selection, IDR total, transaction count, category breakdown, daily/monthly trend, and largest merchants. Also show original-currency subtotals and FX completeness. Empty current months must be explicitly empty, not silently replaced by another month.
- Transactions: server-side pagination, newest-first deterministic sorting, merchant/note search, date/category/payment-method/bank/currency filters, and a read-only details drawer. Mobile cards; desktop table. Show original amount and converted IDR amount with rate date/source for USD.
- Settings: local theme and default-period preferences, reporting timezone/currency-policy information, snapshot status, FX status, cache usage/clear controls, and iOS installation/offline guidance. Do not add expense mutation or source-management controls.
- Detect completed uploads automatically and adopt the newest valid snapshot without restarting. Full replacement must reflect source edits, deletions, and records omitted from later snapshots.
- Persist daily USD→IDR reference rates and backfill dates needed by uploaded expenses. Use transaction date in Asia/Jakarta; weekends/holidays use the most recent published rate on or before that date. Never use a future rate.
- Offline: reopen the app shell and exact previously viewed summary/filter/page/detail results, with cached-at and dataset-version labels. Unvisited views must say they are unavailable offline. No promise of full offline search or complete offline history.
- Daily digest automation: expose `GET /api/digest/daily?date=2026-09-05&timezone=Asia%2FJakarta`, returning the requested day's IDR total, transaction count, top category, and generation timestamp in the flat JSON contract below. Automation calls remain protected by NPM Basic Auth.

## Daily digest API contract

The exact public path is `/api/digest/daily`, without a `/v1` segment. Preserve it as a stable automation interface alongside the dashboard's versioned endpoints. Both query parameters are required: `date` is a strict `YYYY-MM-DD` calendar date; `timezone` is a valid IANA timezone identifier.

Successful response (`200 OK`, illustrative values supplied by the user, not assertions about the sample database):

```json
{
  "date": "2026-09-05",
  "timezone": "Asia/Jakarta",
  "currency": "IDR",
  "total": 185500,
  "transaction_count": 7,
  "top_category": {
    "name": "Food",
    "total": 92000
  },
  "generated_at": "2026-09-06T06:55:00+07:00"
}
```

- This is deliberately a flat response, not the dashboard's response envelope. `total` and `top_category.total` are JSON integers in whole rupiah, not formatted text or decimal strings. Calculate using the existing exact-money policy. Reject values above JSON's interoperable safe-integer bound (`2^53 - 1`) with a structured `422` error rather than silently losing precision.
- Select active, non-deleted expenses in the requested timezone's local day: inclusive local midnight to exclusive next local midnight, converted independently to UTC. Do not assume every day lasts 24 hours. `generated_at` is the actual request-generation timestamp with the requested timezone's UTC offset, not the expense date or import timestamp.
- The timezone parameter controls day membership and timestamp presentation. Historical FX valuation continues to use each expense's Asia/Jakarta date, matching the dashboard and avoiding different valuations solely because an automation requests another timezone.
- Count every matching active expense; totals cover all matches, not a transaction-list page. `top_category` is the category with the greatest converted IDR spending, not the most transactions. Resolve ties by ascending canonical category key for reproducibility.
- Use a shared explicit category-label mapping, initially `food_drink` → `Food`, with deterministic human-readable fallback for unknown keys. Group by canonical source key before formatting labels; share labels with the dashboard.
- A valid active snapshot with no matching expenses returns `total: 0`, `transaction_count: 0`, and `top_category: null`. No active snapshot is not an empty day: return `503` with error code `snapshot_unavailable`.
- If any matching USD expense lacks an applicable stored rate, return `503` with error code `fx_rates_unavailable` and a missing-conversion count. Do not return a successful partial digest, since the requested success body has no completeness field. Use available provisional rates under the existing FX policy, but expose `X-FX-Status: provisional`; otherwise return `X-FX-Status: finalized`.
- Return snapshot revision, FX revision, and source snapshot timestamp in `X-Dataset-Revision`, `X-FX-Revision`, and `X-Snapshot-Timestamp` headers without changing the requested success body. Read all contributing data and metadata in one consistent SQLite read transaction. A timestamp communicates freshness but does not prove the producer has uploaded every expense for the day.
- Missing/invalid parameters, unsupported timezone identifiers, and unrepresentable local-day boundaries return structured `422` JSON errors. Pin/install IANA timezone data in the container rather than relying on the host timezone.
- Set `Cache-Control: no-store`. Do not add the automation endpoint to browser offline storage, shared proxy caching, or SPA fallback. Requests use already imported expenses and stored FX data; never synchronously call the provider or ingest a snapshot in the request handler.
- The endpoint generates data only; scheduling, delivery, retry/backoff, and duplicate-message prevention remain the external automation's responsibility. Results can change after authoritative snapshot replacements or provisional-rate reconciliation.

## Non-functional

- One non-root Docker container; no PostgreSQL, Redis, Node server, or separate job container at runtime. Browser assets and API share one origin.
- Touch-friendly responsive layouts from 320px mobile widths through desktop, accessible labels/contrast/focus states, safe-area support, light/dark themes, and no third-party fonts/scripts.
- Use `sample/favicon.svg` as the favicon source and derive proper raster Apple touch/PWA icons from it. Provide iOS Home Screen metadata for the app name, standalone launch, status bar, and safe-area layout; do not rely on an SVG favicon as the iOS installation icon.
- Financial calculations use integer/decimal arithmetic, never binary floating-point totals. Currency scaling is explicit, not inferred from a currency library.
- Source mount is read-only. Uploaded databases and application data are never served directly. Logs omit transaction bodies, notes, credentials, and email/raw provenance.
- Last-known-good data remains usable if an upload, exchange-rate fetch, or later import fails.

# Assumptions and Open Questions

## Confirmed decisions

- Single user and shared dataset; no app login, editing, bank integrations, receipt hosting, budgets, or write-back in v1.
- IDR scale 1, USD scale 100; historical rates; Asia/Jakarta timezone.
- Producer supplies consistent standalone SQLite backups and publishes a marker only after the database is completely uploaded. A `.ready` marker alone does not guarantee SQLite consistency; copying a live WAL database without its uncheckpointed data is not a valid export.

## Proposed defaults / deployment checks

- Poll incoming files every 30 seconds; retain two successful local raw snapshots; do not delete incoming uploads. Source-directory retention is an external responsibility.
- Cache only successfully viewed responses, bounded initially to 20 MiB / 200 entries, with least-recently-used eviction. Cached data stays until cleared, evicted, or invalidated by a cache-schema update; its age is always visible. Validate actual browser quota behavior.
- Poll the daily FX provider periodically with backoff; historical downloads are bounded and only cover required USD dates. Pin ECB to avoid changing blended-provider semantics.
- Confirm target Unraid CPU architecture, public hostname, NPM network connectivity, and writable UID/GID before deployment. Do not assume an existing Compose manager.
- Expected production database size and upload frequency are unknown. Measure import time and query performance with a generated 100,000-row fixture; revisit limits if real history is substantially larger.
- NPM Basic Auth in an installed iOS PWA is a release-gating device test. Do not silently switch authentication providers if standalone-session behavior is unacceptable.
- Offline data remains accessible without contacting NPM. Revoking online credentials cannot remotely erase an offline device. Device passcode/encryption and trusted-device use are required assumptions. No misleading claim of app-level encrypted offline storage or reliable Basic Auth logout.
- Historical totals stabilize after their rates are finalized. Recent dates can initially use a clearly marked provisional prior-day rate while that day's publication is pending. Finalization must not permanently lock yesterday's rate merely because a user viewed today's data before publication.
- Daily digest defaults proposed for implementation: accept valid IANA timezones for day selection while retaining Jakarta FX valuation; empty-day `top_category` is null; ties use canonical category keys; missing FX fails the digest rather than returning partial totals; provisional FX is allowed and flagged in response headers. These edge-case policies extend the user's example and were not separately confirmed. No schema migration or new scheduler is needed for digest generation.

# Implementation Steps

All application paths below are new; preserve the sample and existing OpenCode configuration.

## 1. Scaffold the smallest deployable application

- [ ] `backend/pyproject.toml`, `backend/uv.lock`: define Python 3.12+, FastAPI, Uvicorn, HTTPX, pytest, and Ruff; use standard-library SQLite, Decimal, and zoneinfo. Lock dependencies. Avoid ORM and database-server dependencies for this small read-only projection.
- [ ] `frontend/package.json`, `frontend/package-lock.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`: define React, TypeScript, Vite, React Router, Tailwind CSS, Recharts, Dexie, and `vite-plugin-pwa`/Workbox; add Vitest and Playwright. Use supported mutually compatible versions at implementation time. Avoid a second server-side rendering framework: SEO is irrelevant and same-origin static delivery is simpler.
- [ ] `backend/app/main.py`: implement `create_app()` and lifespan management; serve `/api/v1/*`, built static files, and SPA route fallback. API errors must never fall through to HTML. Run exactly one Uvicorn worker so import/FX schedulers are not duplicated.
- [ ] `backend/app/config.py`, `.env.example`: validate `INCOMING_DIR=/incoming`, `DATA_DIR=/data`, `POLL_SECONDS=30`, `REPORT_TIMEZONE=Asia/Jakarta`, `PUBLIC_ORIGIN`, configurable import-size limits and retention. Fail clearly on invalid writable paths; do not store secrets in committed environment files.

## 2. Define local storage and API contracts

- [ ] `backend/app/db.py`, `backend/app/migrations/001_initial.sql`: create `/data/dashboard.sqlite3` with dashboard-owned tables: `expenses_projection`, `imports`, `app_state`, `fx_rates`, and `fx_day_assignments`. Separate application migrations from source `schema_migrations`.
- [ ] `expenses_projection`: preserve IDs, original integers/currency, normalized UTC instant and Jakarta date, bank/payment/merchant/category/note. Exclude soft-deleted rows, raw email/input, receipt paths/hashes, and internal classification/audit content. Index normalized date plus ID, category, currency, and useful filter columns. Do not mutate uploaded schemas.
- [ ] `imports`/`app_state`: record filename, upload timestamp, SHA-256, status, bounded failure reason, active dataset revision, and import time. Store active replacement and revision in the same transaction.
- [ ] `fx_rates`: unique provider/base/quote/effective-date records with decimal rate text and fetched-at timestamp. Existing finalized rates are immutable. `fx_day_assignments` records requested Jakarta date, selected published date, provisional/final status, and policy revision.
- [ ] `backend/app/schemas.py`: define typed response envelopes containing API/cache schema version, dataset revision, FX revision, generated-at, source timestamp, reporting timezone, and conversion completeness. Return monetary values as decimal/integer strings with documented units so JSON/JavaScript cannot lose precision. Publish FastAPI OpenAPI contracts.

## 3. Safely adopt uploaded snapshots

- [ ] `backend/app/ingestion.py`: implement `scan_ready_candidates()`, `validate_snapshot()`, and `activate_snapshot()`; perform startup scan and serial polling without blocking the API event loop.
- [ ] Recognize only strict timestamped filenames with valid UTC timestamps and exact companion markers. Ignore temporary files, directories, symlinks, missing pairs, and already processed hashes. Order by embedded UTC timestamp, not mtime; never automatically downgrade an active snapshot. Reject changed content under an already accepted filename as a producer-contract violation.
- [ ] Copy a candidate into `/data/staging/` with bounded size and I/O; verify source identity/size/mtime before and after copying and hash the local copy. Open the copy read-only with extension loading disabled and `trusted_schema=OFF`; require real expected tables, required columns, supported source migration compatibility, valid timestamps/currencies/integer amounts, unique IDs, and successful integrity checks. Unknown additive columns are harmless; incompatible required semantics fail closed.
- [ ] Populate a normalized replacement in bounded batches, then atomically replace the projection and active revision in a SQLite transaction. Preserve imports and FX tables. Readers use a consistent read transaction for multi-query responses; never expose half an import. Configure WAL/busy timeout for the dashboard-owned database only.
- [ ] Move validated raw copies into `/data/snapshots/` before activation; database state is the authority if a crash leaves an unreferenced file. Clean orphan staging files on restart and prune local raw copies only after successful activation. Keep two good copies for recovery.
- [ ] If the newest candidate is bad, record a bounded error and try the next valid candidate newer than the active one; keep existing data serving throughout. An empty but valid snapshot is authoritative and clears expenses. Make failed-candidate retry bounded rather than rehashing the same corrupt upload every poll.

## 4. Implement reproducible historical conversion

- [ ] `backend/app/money.py`: centralize currency scales and Decimal arithmetic. USD conversion is `(amount_minor / 100) * IDR_per_USD`; IDR is unchanged. Round each converted transaction to whole rupiah using `ROUND_HALF_UP`, then sum those same displayed values in every aggregate. Original USD displays with two decimals.
- [ ] `backend/app/fx.py`: implement a fixed-host Frankfurter client using `providers=ECB`, USD base, IDR quote, bounded historical date ranges, timeouts, rate/response validation, and retry backoff. Send only currency/date requests, never expense content. Do not accept a user-supplied arbitrary provider URL.
- [ ] Backfill USD transaction dates on import and startup; collect daily rates independently of uploads. Persist the provider's returned effective date rather than mislabeling it as the requested date. Fetch a preceding interval to resolve weekends/holidays; do not assume the latest quote is valid for historical expenses.
- [ ] Freeze known historical assignments after a completed backfill. Keep current/recent assignments provisional during a documented publication-grace window (initially seven calendar days), retry during that window, and finalize only following a successful reconciliation after the window. Keep failed reconciliations provisional and visible. Increment FX revision whenever effective displayed valuations change.
- [ ] If no appropriate stored rate exists, show original USD and an unavailable conversion, plus a clearly incomplete IDR subtotal and excluded count. Never use zero, a future rate, or an invented rate. Provider failure must not reject a valid expense snapshot or overwrite known rates.

## 5. Add read-only query endpoints

- [ ] `backend/app/queries.py`: parameterized filters over active rows; timezone-normalized date boundaries; deterministic `(expense_at_utc, id)` ordering; consistent detail/list/summary conversion. Compute summaries over the entire requested dataset, never only the returned page. Escape literal search wildcard characters; bound search length, page size, and date inputs.
- [ ] `backend/app/routes.py`: expose `GET /api/v1/status`, `/summary`, `/transactions`, `/transactions/{id}`, and `/settings`; transaction/filter endpoints include required filter options and metadata in their response so each cached view is self-contained. Page-number pagination is sufficient initially; return dataset revision to detect concurrent replacements.
- [ ] `GET /health/live` and `/health/ready`: separate process liveness from storage initialization; lack of a first snapshot is an explicit application empty state, not a restart loop. No expense-write, filesystem browse/download, SQL, or unauthenticated debug endpoints.
- [ ] `backend/app/main.py`: use `Cache-Control: no-store` for financial API responses; enforce expected host/origin configuration, disable unnecessary CORS, redact logs, and apply security headers. Do not trust arbitrary forwarded identity headers or treat Basic Auth as an app-managed session.

### 5a. Add the daily digest automation interface

- [ ] `backend/app/schemas.py`: add `DailyDigestResponse` and `DigestTopCategory` with the exact flat success fields above, nullable top category, integer rupiah amounts, safe-integer validation, and offset-aware generation timestamp. Document success and structured error examples in OpenAPI. This is an explicit exception to the UI API's envelope/string-money convention, not a change to those endpoints.
- [ ] `backend/app/queries.py`: add `get_daily_digest(date, timezone)` and shared local-day UTC-boundary calculation. Reuse active-record filtering, exact per-transaction conversion, and category aggregation from Summary. Query the UTC instant index rather than the precomputed Jakarta date when selecting other timezones. Fetch totals, count, winning category, FX completeness, and revision metadata consistently in one read transaction; do not duplicate conversion formulas or aggregate paginated results.
- [ ] `backend/app/categories.py`: define the shared canonical-key-to-display-label mapping and fallback, including `food_drink` → `Food`. Use it for summary category labels and digest names, preserving source category keys for grouping and tie-breaking.
- [ ] `backend/app/digest_routes.py`: define an `APIRouter` for `GET /api/digest/daily`, validate required query parameters, call `get_daily_digest`, and serialize the exact success contract plus metadata headers. Map no-snapshot/missing-FX conditions to distinct structured `503` responses. Never fetch FX synchronously, return an incomplete success, or introduce digest delivery side effects.
- [ ] `backend/app/main.py`: register the digest router outside the `/api/v1` prefix and ensure all `/api/*` failures remain API responses rather than SPA HTML. Apply the same privacy headers and access deployment model as other financial endpoints.
- [ ] `backend/pyproject.toml`, `backend/uv.lock`, `Dockerfile`: ensure an explicit, reproducible IANA timezone-data dependency is available to `zoneinfo`; validate timezone names and local-day boundary round trips, including nonexistent/skipped dates. Do not change the dashboard's default Asia/Jakarta reporting configuration.
- [ ] `docs/api-digest.md`, `README.md`, `docs/deployment-unraid.md`: document the exact URL, query fields, success/error bodies, header semantics, timezone versus FX-date distinction, category mapping, and an HTTPS Basic Auth request example using automation-managed secrets. Recommend a dedicated NPM automation credential; do not embed credentials in URLs, logs, or source control. NPM credentials are not route-scoped by default, so do not claim this credential can access only the digest. Explain that NPM authentication failures may be non-JSON `401/403` responses and automation must inspect status before parsing.

## 6. Build the responsive interface

- [ ] `frontend/src/App.tsx`, `frontend/src/components/AppShell.tsx`, `frontend/src/styles.css`: implement Summary/Transactions/Settings routes; bottom navigation on mobile, sidebar on desktop, safe-area spacing, keyboard access, and reusable loading/empty/error/offline/stale states.
- [ ] `frontend/src/pages/SummaryPage.tsx`: render IDR KPIs, category/trend charts with text/table alternatives, merchant ranking, period controls, original subtotals, and missing/provisional FX warnings. Use exact amount formatting; chart-number conversion must not become the financial calculation source.
- [ ] `frontend/src/pages/TransactionsPage.tsx`, `frontend/src/components/TransactionDetails.tsx`: filterable mobile cards/desktop table, pagination, original and converted amounts, and details fetched/cached separately. Clear distinction between no results, uncached offline query, removed transaction, and failed request.
- [ ] `frontend/src/pages/SettingsPage.tsx`: local preferences, source filename/import time/errors, FX source/date/status, offline-cache usage and clear action, and iOS Add to Home Screen instructions. No claim that clearing data logs out Basic Auth.
- [ ] `frontend/src/lib/api.ts`, `frontend/src/lib/money.ts`: typed API validation, canonical query keys, safe decimal-string formatting, debounced searches, and foreground/status polling while visible. Cancel obsolete requests so older filters cannot overwrite newer results. Reset paging on filter or dataset changes.

## 7. Add deliberate, bounded offline support

- [ ] `frontend/scripts/generate-icons.mjs`, `frontend/package.json`, `frontend/package-lock.json`: add a reproducible `generate:icons` command using a pinned build-time SVG rasterizer such as Sharp. Resolve `sample/favicon.svg` relative to the script, not the shell working directory. Generate the assets below from that single source without modifying it; no rasterizer is needed in the runtime image. Include icon generation in the frontend build and make the SVG and generator available in the Docker build stage without copying the sample SQLite database.
- [ ] `frontend/public/favicon.svg`, `frontend/public/favicon-16x16.png`, `frontend/public/favicon-32x32.png`: copy the selected SVG unchanged as the scalable favicon and generate small PNG fallbacks. Reference the SVG with `rel="icon" type="image/svg+xml" sizes="any"` and the PNGs with their explicit dimensions in `frontend/index.html`.
- [ ] `frontend/public/apple-touch-icon.png`: generate a 180×180 opaque PNG for iOS Home Screen installation. Use a full-bleed `#17221d` background beneath the source artwork so transparent rounded corners do not become unwanted borders; let iOS apply its own icon mask. Reference it with `rel="apple-touch-icon" sizes="180x180"`; do not use the SVG as the Apple touch icon.
- [ ] `frontend/public/icons/icon-192.png`, `frontend/public/icons/icon-512.png`, `frontend/public/icons/icon-maskable-512.png`: generate standard 192×192 and 512×512 PNGs plus a distinct opaque full-bleed maskable icon. Scale the complete receipt illustration inside the maskable safe-zone circle (centered radius 40% of canvas width), with the dark-green background extending to all edges. Do not merely declare the unpadded ordinary icon maskable; verify the receipt remains visible under circle and rounded-square masks.
- [ ] `frontend/public/manifest.webmanifest`: define stable root-hosted identity `id: "/"`, `name: "Expenses Dashboard"`, `short_name: "Expenses"`, `start_url: "/"`, `scope: "/"`, `display: "standalone"`, `theme_color: "#17221d"`, and `background_color: "#17221d"`. Declare generated PNG icon URLs, MIME types and sizes, with `purpose: "any"` for standard icons and `purpose: "maskable"` for the separate maskable asset. Link this single manifest from HTML; configure the PWA plugin not to emit a competing manifest. Because NPM Basic Auth protects the manifest, use `crossorigin="use-credentials"` on its link and verify fetching on the actual deployment.
- [ ] `frontend/index.html`: set document title and `apple-mobile-web-app-title` to `Expenses Dashboard`; include `apple-mobile-web-app-capable=yes`, `apple-mobile-web-app-status-bar-style=black-translucent`, `theme-color=#17221d`, and viewport `width=device-width, initial-scale=1, viewport-fit=cover`. Provide a generic description without financial data, and `robots=noindex,nofollow` (not a substitute for authentication). Do not disable zoom. `frontend/src/styles.css` must reserve `env(safe-area-inset-*)` space so the translucent status bar and home indicator cannot cover controls. The manifest is the primary install contract; Apple-specific tags supplement it for iOS.
- [ ] `frontend/src/sw.ts`: include generated icon assets and the linked manifest in the intended app-asset build/precache handling. Test URLs and MIME types; a missing icon must not silently return SPA HTML. Do not add speculative device-specific splash-image sets in v1. Do not depend on an iOS install prompt or background sync.
- [ ] `frontend/src/sw.ts`, `frontend/vite.config.ts`: precache versioned app assets and an authenticated-success app shell; navigation fallback offline. Never runtime-cache API calls, auth errors, redirected login pages, opaque responses, or arbitrary origins. Prompt before activating an update; remove obsolete shell caches.
- [ ] `frontend/src/lib/offline.ts`: store only explicitly validated successful API view envelopes in IndexedDB/Dexie. This application-controlled copy is intentional even though normal HTTP/CDN caches are disabled. Canonical keys include endpoint and every filter/page parameter; storage includes schema/dataset/FX revisions and timestamps.
- [ ] Prefer network when online; use an exact saved view on network failure, with conspicuous offline/stale status. Do not fall back on 401/403; show authentication-required and clear financial cache to honor observed access rejection. Detect non-JSON/redirected auth responses and never store them. Classify server errors separately from offline network failures.
- [ ] Never combine pages, summaries, or details from different dataset/FX revisions into a purported coherent result. A standalone stale view may display its own revision clearly; do not merge old/new pagination. A successful response replaces its exact cached view atomically. Cache-schema migrations either validate old entries or clear incompatible entries.
- [ ] Enforce size/entry LRU limits, catch quota/storage-denial errors without breaking online use, expose last fetch time and cache clearing, and request persistent storage only as a best effort. Cache clearing also works offline. On foreground/reconnect, retry visible queries; do not promise iOS background refresh or permanent storage retention.

## 8. Package and document Unraid deployment

- [ ] `Dockerfile`, `.dockerignore`: multi-stage frontend build and Python runtime, locked dependencies, non-root user, no build tools/secrets/sample databases in final image, writable data only, and SIGTERM-safe scheduler shutdown.
- [ ] `compose.yaml`: one `expenses-dashboard` service, internal port 8000, restart policy, healthcheck, configurable UID/GID, `/mnt/user/webdav/expenses:/incoming:ro`, and `/mnt/user/appdata/expenses-dashboard:/data:rw`. Prefer a shared Docker network with NPM and no published public host port. Document private-host-port alternative if NPM cannot join that network. Use read-only root filesystem plus writable `/tmp` where supported.
- [ ] `docs/deployment-unraid.md`: directory permissions, image build/run/upgrade commands, Unraid Compose and Docker-template field equivalents, mounts, persistent backups, environment keys, and hostname-specific NPM setup. Route Cloudflare Tunnel to NPM, not directly to the application. NPM Basic Auth must protect HTML, API, manifest, assets, and service worker.
- [ ] Document HTTPS on the browser origin, no bypass routes, restricted direct LAN/container exposure, Cloudflare cache bypass for the dashboard hostname, no NPM proxy caching of private content, and narrowly trusted proxy headers. Keep platform credentials in platform configuration.
- [ ] `README.md`, `docs/data-contract.md`: local development, source backup/marker contract, schema compatibility, currency scales, rounding, FX finalization, offline limitations, privacy model, and recovery. Add `.gitignore` entries for runtime databases, staging, environment secrets, generated bundles, and test artifacts. Never commit real financial fixtures.

# Tests

No application validation commands exist yet. The scaffold must provide these exact commands, run from the repository root unless noted:

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
npm --prefix frontend exec playwright install --with-deps
npm --prefix frontend run test:e2e
docker compose config
docker compose build
docker compose up -d
```

The last two commands are implementation/deployment validation, not commands executed during planning. `test:e2e` must start or document its isolated backend and frontend test services without touching host financial data.

- `backend/tests/test_ingestion.py`: missing marker/file, invalid names, symlinks, interrupted copy, corruption, unsupported schema, invalid values, hash idempotency, timestamp order, failed newest candidate, soft-deletes, omitted rows, empty snapshot, concurrent reads, crash recovery, and last-good preservation.
- `backend/tests/test_money.py`: IDR 5000 → Rp5,000; USD 566 → US$5.66; at synthetic rate 16,000, conversion → Rp90,560. Cover half-up rounding, large values, nonpositive/noninteger amounts, and unsupported currencies.
- `backend/tests/test_fx.py`: historical backfill, no future rates, weekend/long-holiday fallback, effective versus requested dates, provisional reconciliation/finalization, restart persistence, immutable finalized rates, missing historical coverage, invalid/nonpositive rates, timeout/429/5xx, and partial total labeling. Mock providers for deterministic tests.
- `backend/tests/test_api.py`: full-dataset aggregates, filter combinations, UTC+7 day/month boundaries, equivalent timestamps with different offsets, stable sorting, date/query validation, removed records, empty/no-snapshot states, SQL-injection strings, sensitive-field omission, cache headers, and consistent dataset/FX revisions.
- `backend/tests/test_digest.py`: exact unversioned path and flat response shape; a synthetic seven-transaction fixture totaling Rp185,500 with `Food` totaling Rp92,000; numeric JSON amount types; zero-transaction day/null category; no active snapshot; deleted/omitted records; category ties and fallback labels; IDR/USD conversion and half-up rounding; missing versus provisional FX and metadata headers; safe-integer overflow; required/invalid date and timezone parameters; inclusive/exclusive Jakarta midnight; another timezone, DST 23/25-hour days, and skipped local dates; Jakarta FX dates unchanged by selection timezone; frozen-clock offset-aware `generated_at`; snapshot/FX replacement consistency; `no-store`; and absence of synchronous provider calls. Run `uv run --project backend pytest backend/tests/test_digest.py` in addition to the full backend suite.
- Deployment digest smoke test through actual NPM + Cloudflare: credentials absent/incorrect are rejected, automation credentials return the expected JSON, query-string timezone encoding survives proxying, financial responses are not cached, and `503`/non-JSON authentication failures are handled safely by the caller. Store credentials in the automation's secret store, not in test fixtures.
- `frontend/src/**/*.test.tsx`: exact amount formatting, accessibility, responsive state rendering, canonical cache keys, missing cached views, quota eviction/failures, explicit cache clearing, incompatible cache migration, auth-response rejection, and mixed-revision prevention.
- `frontend/e2e/dashboard.spec.ts`: online Summary/Transactions/Settings; cold start offline after a successful visit; visited versus unvisited filters/pages/details; refresh after new snapshot; FX revision change; network failure versus 401/403; update prompt; 320px/mobile and desktop layouts.
- `frontend/scripts/generate-icons.test.mjs`, `frontend/e2e/metadata.spec.ts`: verify generated PNG dimensions, opaque Apple/maskable backgrounds, source SVG preservation, manifest icon declarations, unique manifest link with credential mode, favicon/Apple metadata links, titles, viewport and standalone settings. Check that each asset URL returns the correct asset/MIME type rather than SPA HTML, and that builds generate all icons from a clean checkout. Include generator tests in the frontend test command. Visually inspect 16px/32px readability and maskable safe-zone previews; image dimensions alone cannot establish correct composition.
- Real iPhone acceptance through actual Cloudflare Tunnel + NPM: authenticate in Safari, install, launch standalone, reopen after closing, cold-launch in airplane mode, inspect previously viewed routes, reconnect after credential expiry/revocation, clear cache offline, and test service-worker update behind Basic Auth. Playwright WebKit is useful but not a substitute.
- During that iPhone test, verify the receipt artwork appears in the Add to Home Screen preview and installed icon, the proposed name is correct, launch is standalone, and status-bar/notch/home-indicator safe areas work in portrait and landscape. Reinstall when validating updated artwork because iOS may retain an older installed icon. Confirm desktop browser tab favicons separately.
- Measure generated 100,000-row import/query performance and bounded offline storage. Proposed baseline on target Unraid: warm common queries under one second and no API-visible partial replacement; record actual measurements and hardware.

# Risks

- **Privacy:** offline financial data survives network authentication expiry; same-origin script compromise can read it. Minimize fields, self-host assets, use a strict tested CSP, and rely on trusted-device security. Basic Auth logout is browser-controlled.
- **iOS compatibility:** standalone authentication/session handling and storage eviction differ by iOS release. Installation does not guarantee persistent offline storage; real-device testing gates release.
- **Input security:** an untrusted SQLite file is parser input. Use bounded local copies, current SQLite/runtime versions, read-only query restrictions, strict schema validation, and non-root isolation.
- **Source correctness:** ready markers do not fix an inconsistent live SQLite copy; verify the producer's backup contract. Source schema/currency additions must not silently reinterpret money.
- **FX accuracy/availability:** reference rates are estimates, not bank settlement rates. Historical provider revisions are intentionally not applied to finalized records. Missing/provisional conversions must remain visible.
- **Regression/consistency:** projection replacement and FX updates can invalidate cached views; revisioned atomic response envelopes prevent silent mixtures. Do not imply partial offline pages represent complete history.
- **Performance/storage:** full snapshots incur copy/validation/replacement I/O; incoming retention is external, raw-local retention is bounded, and notes/search may require later indexing only if measurements justify it.
- **Deployment:** bypassing NPM exposes an unauthenticated application. Public tunnel routing, port exposure, UID/GID permissions, and CDN-cache policy require explicit verification.
- **Automation contract:** the digest intentionally differs from the UI API in path, envelope, and numeric-money serialization; contract tests must prevent accidental unification. Historical digests may change with later source corrections or provisional rates. A successful response describes the current snapshot, not guaranteed upload completeness; automation must inspect freshness/FX headers and own delivery idempotency.

# Rollback

- Pin the previously working container image before upgrades. Stop the service and take a consistent backup of `/data/dashboard.sqlite3` and retained snapshots before schema changes; never back up only a live WAL main file.
- Revert image plus a compatible pre-migration application database backup. Do not run an older binary against an incompatible newer schema. Incoming snapshots are read-only and unaffected.
- Recover data from retained validated snapshots if needed; record the restored active revision and handle subsequent newer uploads deliberately. Do not add a public rollback endpoint.
- Version browser/API cache schemas. On incompatible rollback, clear cached financial views and reinstall/refresh the compatible service worker online; inform the user that previously cached views may be discarded.
- The digest adds no persistent schema. Reverting it removes the endpoint; pause dependent automation before deploying an image without it, then resume only after the contract is restored. Do not redirect missing digest routes to the SPA.

# Acceptance Criteria

- [ ] One container starts on Unraid with the specified mounts, survives restart, and needs no external database service.
- [ ] Public access traverses Cloudflare Tunnel and NPM Basic Auth; direct application bypass and shared financial caching are prevented.
- [ ] Three polished, accessible pages work at mobile and desktop sizes; source records cannot be edited.
- [ ] Only completed, valid snapshots activate; replacement includes updates/deletions, is idempotent, and never exposes partial data. A bad upload preserves the last good dataset.
- [ ] Currency scaling matches confirmed source semantics; USD uses persisted historical rates and Jakarta dates; displayed per-row IDR sums match aggregates.
- [ ] FX outages preserve known conversions, while missing/provisional coverage is explicit. Daily collection and historical backfill survive restart.
- [ ] The actual iPhone can install and open the PWA offline after a successful online visit; visited data is labeled and unvisited queries are not misrepresented as complete.
- [ ] Browser favicons and installed iOS/PWA icons derive from `sample/favicon.svg`; generated sizes, opaque Apple icon, maskable safe area, manifest identity, and iOS metadata are verified. The Home Screen name/artwork and standalone safe-area layout pass an actual iPhone test behind NPM.
- [ ] Cached data is bounded, clearable offline, never mixed across revisions, and never populated from failed authentication responses.
- [ ] Automated tests, build/container validation, real-device Basic Auth tests, and recovery checks pass; deployment and data contracts are documented.
- [ ] `GET /api/digest/daily?date=2026-09-05&timezone=Asia%2FJakarta` is available behind NPM and matches the requested flat JSON contract with numeric whole-IDR totals and a correctly offset generation timestamp.
- [ ] Digest day boundaries, historical FX, category ranking, empty days, and failure behavior match the documented contract; successful digests never silently omit unconverted expenses, and metadata identifies source freshness and provisional rates.
- [ ] Digest totals match Summary for the same Jakarta day and dataset/FX revisions; contract/unit tests and a real authenticated automation smoke test pass.
