from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator

SAFE_INTEGER = 2**53 - 1


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversionCompleteness(ApiModel):
    complete: bool
    converted_count: int
    missing_count: int
    provisional_count: int


class Metadata(ApiModel):
    api_schema_version: int = 1
    cache_schema_version: int = 1
    dataset_revision: int
    fx_revision: int
    generated_at: datetime
    source_timestamp: datetime | None
    reporting_timezone: str
    conversion: ConversionCompleteness


class OriginalSubtotal(ApiModel):
    currency: str
    amount: str
    amount_minor: str


class CategoryTotal(ApiModel):
    key: str
    name: str
    total_idr: str


class TrendPoint(ApiModel):
    period: str
    total_idr: str
    transaction_count: int


class MerchantTotal(ApiModel):
    merchant: str
    total_idr: str
    transaction_count: int


class SummaryData(ApiModel):
    start_date: date
    end_date: date
    total_idr: str
    transaction_count: int
    original_subtotals: list[OriginalSubtotal]
    categories: list[CategoryTotal]
    trend_granularity: str
    trend: list[TrendPoint]
    largest_merchants: list[MerchantTotal]


class SummaryResponse(ApiModel):
    metadata: Metadata
    data: SummaryData


class TransactionItem(ApiModel):
    id: str
    expense_at: datetime
    jakarta_date: date
    merchant: str | None
    category_key: str
    category_name: str
    bank: str | None
    payment_method: str | None
    note: str | None
    currency: str
    amount_minor: str
    original_amount: str
    converted_idr: str | None
    fx_rate: str | None
    fx_rate_date: date | None
    fx_source: str | None
    fx_status: str | None


class CategoryOption(ApiModel):
    key: str
    name: str


class FilterOptions(ApiModel):
    categories: list[CategoryOption]
    payment_methods: list[str]
    banks: list[str]
    currencies: list[str]


class TransactionsData(ApiModel):
    items: list[TransactionItem]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    filters: FilterOptions


class TransactionsResponse(ApiModel):
    metadata: Metadata
    data: TransactionsData


class TransactionResponse(ApiModel):
    metadata: Metadata
    data: TransactionItem


class ImportErrorInfo(ApiModel):
    filename: str
    failure_reason: str
    imported_at: datetime


class SourceSettings(ApiModel):
    snapshot_available: bool
    filename: str | None
    source_timestamp: datetime | None
    imported_at: datetime | None
    last_import_error: ImportErrorInfo | None


class FxCoverage(ApiModel):
    status: str
    oldest_effective_date: date | None
    newest_effective_date: date | None
    last_fetched_at: datetime | None
    required_days: int
    assigned_days: int
    finalized_days: int
    provisional_days: int
    missing_days: int


class SettingsData(ApiModel):
    reporting_timezone: str
    reporting_currency: str
    currency_scales: dict[str, int]
    fx_provider: str
    fx_policy: str
    fx_publication_grace_days: int
    source: SourceSettings
    fx_coverage: FxCoverage


class SettingsResponse(ApiModel):
    metadata: Metadata
    data: SettingsData


class DigestTopCategory(ApiModel):
    name: str
    total: int

    @field_validator("total")
    @classmethod
    def safe_total(cls, value: int) -> int:
        if abs(value) > SAFE_INTEGER:
            raise ValueError("amount exceeds the interoperable JSON safe-integer bound")
        return value


class DailyDigestResponse(ApiModel):
    date: date
    timezone: str
    currency: str = "IDR"
    total: int
    transaction_count: int
    top_category: DigestTopCategory | None
    generated_at: datetime

    @field_validator("total")
    @classmethod
    def safe_total(cls, value: int) -> int:
        if abs(value) > SAFE_INTEGER:
            raise ValueError("amount exceeds the interoperable JSON safe-integer bound")
        return value
