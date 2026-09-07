# Daily Digest API

`GET /api/digest/daily` is the stable, unversioned automation interface. It reads only already imported expenses and stored FX data. It does not ingest snapshots, fetch exchange rates, schedule messages, deliver notifications, retry delivery, or deduplicate automation runs.

## Request

Both query parameters are required:

| Parameter | Contract |
| --- | --- |
| `date` | Strict `YYYY-MM-DD` calendar date |
| `timezone` | Valid IANA timezone identifier |

Example using credentials supplied by an automation secret store, not embedded in a URL or source file:

```sh
curl --fail-with-body --silent --show-error \
  --user "$AUTOMATION_USER:$AUTOMATION_PASSWORD" \
  --get 'https://expenses.example.com/api/digest/daily' \
  --data-urlencode 'date=2026-09-05' \
  --data-urlencode 'timezone=Asia/Jakarta'
```

Use a dedicated NPM access-list credential for automation so it can be rotated independently. NPM credentials are not route-scoped by default: that credential can access every location covered by the same access list, not only this endpoint. Never put credentials in query strings, logs, images, compose files, or the repository.

## Success

`200 OK` returns a flat object. The values below illustrate the shape and are not claims about a deployed dataset:

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

`total` and `top_category.total` are JSON integers in whole rupiah. They are not strings, minor USD units, or formatted text. Values above `2^53 - 1` are rejected with `422` rather than rounded. An active snapshot with no matching expenses returns zero totals, a zero count, and `top_category: null`.

The requested timezone determines expense membership in inclusive local midnight through exclusive next local midnight. Each boundary is converted independently to UTC, so daylight-saving transitions and skipped local dates are not assumed to last 24 hours. `generated_at` is the actual generation time rendered with that timezone's offset.

FX valuation does not change with the request timezone. Every USD expense continues to use its own `Asia/Jakarta` expense date and the persisted historical policy. Every active matching expense is counted, while totals require all matching expenses to be convertible. `top_category` is ranked by converted IDR spend, with ties resolved by ascending canonical category key. Categories are grouped by canonical source key; `food_drink` displays as `Food`, and unknown keys use a deterministic human-readable fallback.

## Response headers

Every successful response includes:

| Header | Meaning |
| --- | --- |
| `X-Dataset-Revision` | Active replacement revision read for the result |
| `X-FX-Revision` | FX valuation revision read for the result |
| `X-Snapshot-Timestamp` | Timestamp encoded by the active source snapshot |
| `X-FX-Status` | `finalized` or `provisional` |
| `Cache-Control` | `no-store` |

The data and metadata are read in one consistent SQLite transaction. The snapshot timestamp communicates freshness but cannot prove that the producer included every real-world expense. Historical results can change after an authoritative replacement or provisional-rate reconciliation. Automations should record and inspect these headers and own delivery idempotency.

## Errors

Missing or invalid parameters, unsupported timezone identifiers, unrepresentable local-day boundaries, and safe-integer overflow return structured JSON with status `422`. No active snapshot returns `503` with error code `snapshot_unavailable`. If any matching USD transaction lacks an applicable stored rate, the endpoint returns `503` with error code `fx_rates_unavailable` and a missing-conversion count; it never returns a successful partial digest.

NPM rejects absent or incorrect credentials before the application. Those `401` or `403` responses may be HTML or otherwise non-JSON. Automation must inspect HTTP status and content type before parsing JSON. Treat redirects to authentication as failures. Cloudflare and NPM must not cache successful or error responses.
