-- Allow additional ISO-4217 currency codes in the projection.
--
-- The original CHECK constraint restricted currencies to IDR and USD, so a
-- snapshot containing any other declared currency (for example SGD) failed
-- during atomic replacement and could not be activated. The projection is
-- rebuilt to drop that constraint while keeping the money invariant.
--
-- Column order must match 001_initial.sql because ingestion builds the
-- replacement table with `CREATE TABLE ... AS SELECT * FROM expenses_projection`.

BEGIN;

CREATE TABLE IF NOT EXISTS expenses_projection_migrated (
    id TEXT PRIMARY KEY,
    expense_at_utc TEXT NOT NULL,
    jakarta_date TEXT NOT NULL,
    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
    currency TEXT NOT NULL,
    bank TEXT,
    payment_method TEXT,
    merchant TEXT,
    category TEXT NOT NULL,
    note TEXT
);

INSERT INTO expenses_projection_migrated
    (id, expense_at_utc, jakarta_date, amount_minor, currency, bank,
     payment_method, merchant, category, note)
SELECT id, expense_at_utc, jakarta_date, amount_minor, currency, bank,
       payment_method, merchant, category, note
FROM expenses_projection;

DROP TABLE expenses_projection;

ALTER TABLE expenses_projection_migrated RENAME TO expenses_projection;

CREATE INDEX IF NOT EXISTS expenses_projection_date_id
    ON expenses_projection(expense_at_utc DESC, id DESC);
CREATE INDEX IF NOT EXISTS expenses_projection_jakarta_date
    ON expenses_projection(jakarta_date, id);
CREATE INDEX IF NOT EXISTS expenses_projection_category ON expenses_projection(category);
CREATE INDEX IF NOT EXISTS expenses_projection_currency ON expenses_projection(currency);
CREATE INDEX IF NOT EXISTS expenses_projection_bank ON expenses_projection(bank);
CREATE INDEX IF NOT EXISTS expenses_projection_payment ON expenses_projection(payment_method);

COMMIT;