CREATE TABLE IF NOT EXISTS app_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS expenses_projection (
    id TEXT PRIMARY KEY,
    expense_at_utc TEXT NOT NULL,
    jakarta_date TEXT NOT NULL,
    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
    currency TEXT NOT NULL CHECK(currency IN ('IDR', 'USD')),
    bank TEXT,
    payment_method TEXT,
    merchant TEXT,
    category TEXT NOT NULL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS expenses_projection_date_id
    ON expenses_projection(expense_at_utc DESC, id DESC);
CREATE INDEX IF NOT EXISTS expenses_projection_jakarta_date
    ON expenses_projection(jakarta_date, id);
CREATE INDEX IF NOT EXISTS expenses_projection_category ON expenses_projection(category);
CREATE INDEX IF NOT EXISTS expenses_projection_currency ON expenses_projection(currency);
CREATE INDEX IF NOT EXISTS expenses_projection_bank ON expenses_projection(bank);
CREATE INDEX IF NOT EXISTS expenses_projection_payment ON expenses_projection(payment_method);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    source_timestamp TEXT,
    source_identity TEXT,
    sha256 TEXT,
    status TEXT NOT NULL CHECK(status IN ('accepted', 'failed', 'duplicate')),
    failure_reason TEXT,
    imported_at TEXT NOT NULL,
    row_count INTEGER,
    dataset_revision INTEGER,
    local_path TEXT
);
CREATE INDEX IF NOT EXISTS imports_filename ON imports(filename, imported_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS imports_accepted_hash
    ON imports(sha256) WHERE status = 'accepted';

CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fx_rates (
    provider TEXT NOT NULL,
    base TEXT NOT NULL,
    quote TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    rate_text TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY(provider, base, quote, effective_date)
);

CREATE TABLE IF NOT EXISTS fx_day_assignments (
    requested_date TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('provisional', 'finalized')),
    policy_revision INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
