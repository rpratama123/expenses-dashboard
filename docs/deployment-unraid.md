# Unraid Deployment

## Prerequisites

- Docker/Compose support on Unraid and an architecture supported by the official Node, uv, and Python multi-architecture images
- An existing Nginx Proxy Manager container attached to the shared Docker network `proxynet`
- A Cloudflare Tunnel whose public hostname routes to NPM, never directly to this application
- A consistent snapshot producer following the [data contract](data-contract.md)
- The final HTTPS hostname and a UID/GID selected for the container

The application has no authentication. Restrict direct LAN and Docker access so NPM Basic Auth cannot be bypassed.

## Directories and permissions

Create the directories from an Unraid terminal. The defaults use Unraid's `nobody:users` identity, UID/GID `99:100`:

```sh
mkdir -p /mnt/user/webdav/expenses /mnt/user/appdata/expenses-dashboard
chown 99:100 /mnt/user/appdata/expenses-dashboard
chmod 750 /mnt/user/appdata/expenses-dashboard
```

The selected identity needs read/traverse access to `/mnt/user/webdav/expenses`; it must not need write access there. It needs read/write/traverse access to appdata. Do not make either directory world-writable to work around ownership errors. The compose mounts are:

| Host | Container | Mode |
| --- | --- | --- |
| `/mnt/user/webdav/expenses` | `/incoming` | read-only |
| `/mnt/user/appdata/expenses-dashboard` | `/data` | read/write |

`/data` contains application state, WAL files, import metadata, persisted FX rates, staging data, and retained validated snapshots. The root filesystem is read-only and `/tmp` is a bounded 64 MiB tmpfs.

## Build and start

Create a local `.env` from `.env.example`. Set `PUBLIC_ORIGIN` to the exact externally visible HTTPS origin with no path, set `PUID`/`PGID`, and set `NPM_NETWORK` to the existing external network name. No application secrets belong in this file.

```sh
docker network inspect proxynet
docker compose config
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs --no-log-prefix expenses-dashboard
```

Do not pass `--platform`; Docker should select the host architecture. The service exposes port 8000 only to the shared Docker network and publishes no host port. NPM's forwarding destination is `expenses-dashboard:8000` with scheme `http`.

Configuration:

| Variable | Purpose | Default |
| --- | --- | --- |
| `PUBLIC_ORIGIN` | Required canonical browser HTTPS origin | none |
| `PUID`, `PGID` | Build/runtime identity matching appdata ownership | `99`, `100` |
| `NPM_NETWORK` | Existing network shared with NPM | `proxynet` |
| `IMAGE_TAG` | Local image tag | `local` |
| `POLL_SECONDS` | Completed-upload polling interval | `30` |
| `FX_POLL_SECONDS` | Stored-rate refresh interval | `3600` |
| `REPORT_TIMEZONE` | Dashboard and FX-date policy | `Asia/Jakarta` |
| `MAX_IMPORT_BYTES` | Maximum candidate size in bytes | `536870912` |
| `SNAPSHOT_RETENTION` | Successful local raw copies retained | `2` |

The image has a non-root default user. Compose passes the same UID/GID as build arguments and runtime identity. Rebuild after changing them.

## Unraid template equivalent

If using an Unraid Docker template instead of Compose, configure one container with repository/image `expenses-dashboard:local`, WebUI `https://expenses.example.com/`, network type `Custom: proxynet`, and no host port. Add the two path mappings above, all application environment variables from the table, and container port 8000 only as metadata if the UI requires it. Set the container to run as UID/GID `99:100`, drop all capabilities, enable no-new-privileges and read-only root filesystem, and provide a size-limited writable tmpfs at `/tmp`.

Unraid template capabilities vary. Verify the generated `docker run` command actually preserves read-only mounts, read-only root, tmpfs, user, restart policy, and network settings. Compose is preferred when the template cannot express these controls.

If NPM cannot join the same Docker network, the less-preferred alternative is to publish port 8000 on a private Unraid interface and firewall it so only NPM can connect. Add a `ports` mapping such as `192.0.2.10:8000:8000` using the actual private Unraid address, never `0.0.0.0`, and point NPM to that private address. Test from another LAN host that direct access is denied. Do not publish a public router port.

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

The container healthcheck calls `/health/ready`. Process liveness is separately available at `/health/live`; no first snapshot should be shown as an explicit data state rather than causing a restart loop.

After deployment, publish a known valid snapshot pair and confirm that status reports its exact source timestamp and a new dataset revision. Then test Summary, Transactions, Settings, and the authenticated digest through the public Cloudflare hostname. Confirm direct container/LAN access is unavailable, bad credentials fail, manifest/icons have their correct content types, and financial responses are never cached.

## Upgrade and rollback

Before upgrades, record the current immutable image reference and take a consistent `/data` backup as described in [recovery](recovery.md). Then:

```sh
docker compose build --pull
docker compose up -d
docker compose ps
```

Do not run an older binary against an application database migrated to an incompatible newer schema. Roll back the image together with its compatible pre-upgrade `/data` backup. Clear incompatible browser financial caches and refresh/reinstall the compatible service worker online. Pause digest automation while deploying an image that does not provide its stable endpoint.
