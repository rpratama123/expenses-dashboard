# Recovery

## Backups

Back up `/mnt/user/appdata/expenses-dashboard` and independently retain producer snapshots. `/data/dashboard.sqlite3` may use WAL mode: copying only the main file while the service is writing can lose committed state. Use one of these approaches:

1. Stop the container, copy the complete `/data` directory, then start it again.
2. Use a SQLite-aware online backup procedure that captures a consistent database while preserving the rest of `/data`.

Record the running image digest/tag, application version, backup time, active dataset revision, FX revision, and source snapshot timestamp with each backup. Protect backups as financial data and test restoration periodically. Incoming-directory retention is external to the application and is not a substitute for `/data` backup because persisted FX and import metadata live only in `/data`.

## Failed import or FX refresh

A failed candidate or provider request must leave the last known good dataset and known rates serving. Inspect application status and redacted container logs, correct the producer/export or connectivity issue, and publish a new timestamped pair. Never edit an accepted file in place or reuse its filename with different contents. Missing FX may make converted totals incomplete and makes the digest fail closed; do not manually invent a rate.

## Restore

1. Stop the service and preserve the failed/current `/data` directory for diagnosis.
2. Restore the complete consistent backup with ownership matching `PUID:PGID`.
3. Deploy the exact compatible image recorded with that backup.
4. Start the service and verify readiness, active source timestamp, dataset revision, FX revision, and retained snapshots before restoring public traffic or digest automation.
5. Deliberately process any newer incoming snapshots; verify they are compatible rather than assuming automatic replay is safe after rollback.

If application state cannot be restored, a retained validated raw snapshot can reconstruct expense data, but persisted FX assignments and operational history may need to be rebuilt. Keep the service private until conversion completeness and revision metadata are verified. There is intentionally no public rollback or filesystem-download endpoint.

Browser offline views carry their own dataset/FX revisions and can outlive a server restore. After an incompatible rollback, clear cached financial views and refresh the service worker while online. A standalone stale view may be consulted as labeled historical information, but it must not be combined with pages from another revision.
