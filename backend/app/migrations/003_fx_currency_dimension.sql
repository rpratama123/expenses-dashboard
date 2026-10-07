-- Give FX day assignments a currency dimension.
--
-- The original table was keyed by requested_date alone, so it could only
-- record a single rate assignment per calendar day. Supporting more than USD
-- requires one assignment per (currency, day). Existing rows are all USD/IDR.

BEGIN;

CREATE TABLE IF NOT EXISTS fx_day_assignments_v2 (
    requested_date TEXT NOT NULL,
    base TEXT NOT NULL,
    quote TEXT NOT NULL,
    provider TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('provisional', 'finalized')),
    policy_revision INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (requested_date, base, quote)
);

INSERT INTO fx_day_assignments_v2
    (requested_date, base, quote, provider, effective_date, status,
     policy_revision, updated_at)
SELECT requested_date, 'USD', 'IDR', provider, effective_date, status,
       policy_revision, updated_at
FROM fx_day_assignments;

DROP TABLE fx_day_assignments;

ALTER TABLE fx_day_assignments_v2 RENAME TO fx_day_assignments;

COMMIT;