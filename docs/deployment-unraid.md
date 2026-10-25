# Unraid Deployment

## Prerequisites

- Docker support on Unraid (Unraid hosts are amd64-only, and the published image targets `linux/amd64`)
- A GitHub Actions publish run completed on the repository, so the image exists at `ghcr.io/rpratama123/expenses-dashboard`
- An existing Nginx Proxy Manager container attached to the shared Docker network `proxynet`
- A Cloudflare Tunnel whose public hostname routes to NPM, never directly to this application
- A consistent snapshot producer following the [data contract](data-contract.md)
- The final HTTPS hostname and an appdata owner for the container

The application has no authentication. Restrict direct LAN and Docker access so NPM Basic Auth cannot be bypassed.

If this repository (or its GHCR package) is private, Unraid cannot pull the image anonymously; in that case log in to GHCR once from the Unraid Docker Console or make the package public.

## Directories and permissions

Create the directories from an Unraid terminal. The defaults use Unraid's `nobody:users` identity, UID/GID `99:100`, which is also the identity baked into the image:

```sh
mkdir -p /mnt/user/webdav/expenses /mnt/user/appdata/expenses-dashboard
chown 99:100 /mnt/user/appdata/expenses-dashboard
chmod 750 /mnt/user/appdata/expenses-dashboard
```

The selected identity needs read/traverse access to `/mnt/user/webdav/expenses`; it must not need write access there. It needs read/write/traverse access to appdata. Do not make either directory world-writable to work around ownership errors. The container mounts are:

| Host | Container | Mode |
| --- | --- | --- |
| `/mnt/user/webdav/expenses` | `/incoming` | read-only |
| `/mnt/user/appdata/expenses-dashboard` | `/data` | read/write |

`/data` contains application state, WAL files, import metadata, persisted FX rates, staging data, and retained validated snapshots. The baked user in the image is `app` (UID/GID 99:100); `99:100` covers both the Unraid default and the image default.

## Install the published image

The repository ships an Unraid Docker template at `unraid/expenses-dashboard.xml`. Install flow:

1. Copy that file to `/boot/config/plugins/dockerMan/templates-user/` (or create a template of the same contents through Docker &rightarrow; Add Container &rightarrow; Template Finder) and refresh the Docker templates.
2. Docker &rightarrow; Add Container and select `expenses-dashboard`.
3. Set `PUBLIC_ORIGIN` to the exact externally visible HTTPS origin with no path, and point the two path mappings at the directories above (the template fills `POLL_SECONDS`, `FX_POLL_SECONDS`, `REPORT_TIMEZONE`, `MAX_IMPORT_BYTES`, and `SNAPSHOT_RETENTION` with the documented defaults). No application secrets belong in these settings.

| Variable | Purpose | Default |
| --- | --- | --- |
| `PUBLIC_ORIGIN` | Required canonical browser HTTPS origin | none |
| `POLL_SECONDS` | Completed-upload polling interval | `30` |
| `FX_POLL_SECONDS` | Stored-rate refresh interval | `3600` |
| `REPORT_TIMEZONE` | Dashboard and FX-date policy | `Asia/Jakarta` |
| `MAX_IMPORT_BYTES` | Maximum candidate size in bytes | `536870912` |
| `SNAPSHOT_RETENTION` | Successful local raw copies retained | `2` |

The image runs a single non-root Uvicorn worker on port 8000 and publishes no host port: it is reachable only through the `proxynet` Docker network, and NPM's forwarding destination is `expenses-dashboard:8000` with scheme `http`.

Template capabilities vary per Unraid release, and the template cannot express every hardening control that the local compose file uses (read-only root filesystem, `cap_drop: ALL`, `no-new-privileges`, the bounded `/tmp` tmpfs). Verify the generated `docker run` command (or `docker inspect` of the created container) actually preserves the two mounted paths, the `proxynet` network, the restart policy, and no published host port. Apply Extra Arguments such as `--read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:rw,noexec,nosuid,size=64m,mode=1777` only if they appear verbatim in the inspected command; remove them again if the container fails to start and treat the difference as a known gap, not a reason to weaken `/data` or `/incoming` permissions.

## If NPM cannot join the same Docker network

The less-preferred alternative is to publish port 8000 on a private Unraid interface and firewall it so only NPM can connect. Add a ports mapping such as `192.0.2.10:8000:8000` using the actual private Unraid address, never `0.0.0.0`, and point NPM to that private address. Test from another LAN host that direct access is denied. Do not publish a public router port.

## NPM and Cloudflare

1. Create an NPM Proxy Host for the exact dashboard hostname, forwarding to `http://expenses-dashboard:8000` on the shared network.
2. Attach an NPM Access List with Basic Auth to the entire proxy host. It must cover HTML, `/api`, health routes, the web manifest, icons/assets, and service worker; do not configure public bypass locations.
3. Install a valid certificate in NPM, force HTTPS, and enable WebSocket support only if later required. Do not enable NPM asset/proxy caching.
4. Configure narrowly trusted forwarding headers. Replace incoming client-supplied forwarding headers at the edge; do not treat arbitrary forwarded identity headers as authentication.
5. Configure Cloudflare Tunnel's public hostname to the NPM listener. Do not target port 8000 or the application container directly.
6. Create a Cloudflare Cache Rule that bypasses cache for the entire dashboard hostname. Disable transformations that could rewrite the manifest, JavaScript, API JSON, or security headers.
7. Verify an unauthenticated request is rejected and an authenticated request reaches the app. Verify `/api` responses retain `Cache-Control: no-store` and are not cached (`CF-Cache-Status` must not indicate a cached financial response).

Use a dedicated NPM credential for automation, stored in the automation platform's secret manager. NPM access-list credentials are generally host-wide, not restricted to the digest path. See the [digest API](api-digest.md) for response handling.

Basic Auth behavior in an installed iOS PWA is release-gating. Test authentication, standalone relaunch, service-worker updates, and offline startup on the actual target iPhone. Do not change authentication providers silently if standalone credential behavior is unacceptable.

## Health and smoke checks

The image defines a healthcheck against `/health/ready`. Process liveness is separately available at `/health/live`; no first snapshot should be shown as an explicit data state rather than causing a restart loop.

After deployment, publish a known valid snapshot pair and confirm that status reports its exact source timestamp and a new dataset revision. Then test Summary, Transactions, Settings, and the authenticated digest through the public Cloudflare hostname. Confirm direct container/LAN access is unavailable, bad credentials fail, manifest/icons have their correct content types, and financial responses are never cached.

## Upgrade and rollback

Before upgrades, record the current image reference (retain the digest of the running container as the immutable rollback point) and take a consistent `/data` backup as described in [recovery](recovery.md). Then:

```sh
docker pull ghcr.io/rpratama123/expenses-dashboard:latest
```

or let Unraid check for updates (it pulls from the same GHCR repository; Unraid's "force update" performs a pull before re-updating the container). To pin instead, edit the template's `Repository` field to a specific `v*` or `sha-*` tag published by the workflow.

Do not run an older binary against an application database migrated to an incompatible newer schema. Roll back the image together with its compatible pre-upgrade `/data` backup. Clear incompatible browser financial caches and refresh/reinstall the compatible service worker online. Pause digest automation while deploying an image that does not provide its stable endpoint.

## Local build and validation (compose)

`compose.yaml` at the repository root is a local build/validation fixture, not the Unraid deployment path. It builds the image locally, sets `pull_policy: build` so an explicit `docker compose pull` (or Unraid-style force update, if you actually attach its `/docker-compose.yml`) never tries to fetch a nonexistent `expenses-dashboard:local` from a registry, and reflects the container contract (read-only root FS, dropped capabilities, bounded tmpfs, single worker) for local checks. Do not add a `pull_policy` that pulls this service.

Create a local `.env` from `.env.example` (set `PUBLIC_ORIGIN`, `PUID`/`PGID` only as build arguments here, and `NPM_NETWORK`), then:

```sh
docker network inspect proxynet
docker compose config
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs --no-log-prefix expenses-dashboard
```

Do not pass `--platform`; Docker should select the host architecture.
