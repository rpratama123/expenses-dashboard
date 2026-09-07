# Source Data Contract

## Publication

The incoming directory contains complete replacement snapshots, not deltas:

```text
expenses-YYYYMMDDTHHMMSSZ.sqlite3
expenses-YYYYMMDDTHHMMSSZ.sqlite3.ready
```

The timestamp is a real UTC timestamp and controls candidate ordering. File and marker names must match exactly. Publish the database first and create the zero-content marker only after the upload is complete. Temporary files, malformed names, missing pairs, directories, and symlinks are ignored. The application does not delete incoming files; retention there belongs to the producer.

Use SQLite's backup API, `VACUUM INTO`, or a stopped/checkpointed database to create a consistent standalone file. Copying only a live WAL-mode main file can omit committed records; a marker cannot repair such a copy. Upload to a temporary name, atomically rename to the final database name when possible, and publish the marker last.

Snapshots are authoritative and complete. A newer valid snapshot may edit records, soft-delete them, omit formerly present records, or contain no expenses. Activation replaces the entire projection so all those cases are reflected. Reusing an accepted filename with different bytes is a producer contract violation. Do not depend on file modification time.

## Required expense semantics

The source must be a valid SQLite database with compatible source migrations and an `expenses` table containing the required fields represented by the current source contract:

- Stable, unique `id`
- `expense_at`, a valid instant with an offset
- `amount_minor`, a positive integer using the explicit currency scale
- `currency`, currently `IDR` or `USD`
- `bank`, `payment_method`, `merchant`, `category`, and nullable `note`
- `deleted_at`, where non-null records are excluded

Unknown additive columns may be ignored. Missing required columns, unsupported migration semantics, malformed timestamps, duplicate IDs, unsupported currencies, invalid integer amounts, corruption, or a failed integrity check reject the candidate. A rejected snapshot never replaces the active dataset.

Only dashboard fields are projected. Receipt locations and hashes, raw email/input, audit records, ingestion provenance, and classification internals are not exposed. Uploaded databases and retained copies are never served as files.

## Money and dates

Currency scale is fixed rather than inferred:

| Currency | Source integer | Meaning |
| --- | ---: | --- |
| IDR | `5000` | Rp5,000 |
| USD | `566` | US$5.66 |

The reporting timezone is `Asia/Jakarta`. Historical conversion selects the most recent stored USD-to-IDR ECB reference rate published on or before the expense's Jakarta calendar date; it never uses a future rate. USD conversion is `(amount_minor / 100) * rate`, rounded per transaction to whole rupiah with decimal `ROUND_HALF_UP`. IDR is already whole rupiah. Aggregates sum the same rounded per-transaction values shown by the dashboard.

Recent assignments can be provisional during the publication grace period and may change after reconciliation. Finalized assignments remain fixed. If no applicable rate is stored, the original USD amount remains available but converted totals identify the excluded count rather than using zero or an invented rate.

## Adoption and retention

The service copies a candidate to `/data` under the configured import-size bound, verifies that the source did not change during copying, validates the local copy read-only, and activates a normalized replacement transactionally. Readers see either the old revision or the new revision, never a partial replacement. The default scan interval is 30 seconds and the default local retention is two successful raw snapshots.

Keep source exports until the dashboard has accepted a newer one and independent backup policy permits deletion. Application metadata records filename, source timestamp, hash, import result, active dataset revision, and bounded failure details. Review status after every producer or schema change.
