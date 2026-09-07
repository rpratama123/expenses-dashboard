export interface ConversionCompleteness {
  complete: boolean
  converted_count: number
  missing_count: number
  provisional_count: number
}

export interface ApiMetadata {
  api_schema_version: number
  cache_schema_version: number
  dataset_revision: number
  fx_revision: number
  generated_at: string
  source_timestamp: string | null
  reporting_timezone: string
  conversion: ConversionCompleteness
}

export interface ApiEnvelope<T> { metadata: ApiMetadata; data: T }

export interface OriginalSubtotal { currency: string; amount: string; amount_minor: string }
export interface CategoryTotal { key: string; name: string; total_idr: string }
export interface TrendPoint { period: string; total_idr: string; transaction_count: number }
export interface MerchantTotal { merchant: string; total_idr: string; transaction_count: number }

export interface Summary {
  start_date: string
  end_date: string
  total_idr: string
  transaction_count: number
  original_subtotals: OriginalSubtotal[]
  categories: CategoryTotal[]
  trend_granularity: 'day' | 'month'
  trend: TrendPoint[]
  largest_merchants: MerchantTotal[]
}

export interface Transaction {
  id: string
  expense_at: string
  jakarta_date: string
  merchant: string | null
  category_key: string
  category_name: string
  bank: string | null
  payment_method: string | null
  note: string | null
  currency: string
  amount_minor: string
  original_amount: string
  converted_idr: string | null
  fx_rate: string | null
  fx_rate_date: string | null
  fx_source: string | null
  fx_status: string | null
}

export interface TransactionPage {
  items: Transaction[]
  page: number
  page_size: number
  total_items: number
  total_pages: number
  filters: FilterOptions
}

export interface CategoryOption { key: string; name: string }

export interface FilterOptions {
  categories: CategoryOption[]
  payment_methods: string[]
  banks: string[]
  currencies: string[]
}

export interface ImportError {
  filename: string
  failure_reason: string
  imported_at: string
}

export interface SourceSettings {
  snapshot_available: boolean
  filename: string | null
  source_timestamp: string | null
  imported_at: string | null
  last_import_error: ImportError | null
}

export interface FxCoverage {
  status: string
  oldest_effective_date: string | null
  newest_effective_date: string | null
  last_fetched_at: string | null
  required_days: number
  assigned_days: number
  finalized_days: number
  provisional_days: number
  missing_days: number
}

export interface Settings {
  reporting_timezone: string
  reporting_currency: string
  currency_scales: Record<string, number>
  fx_provider: string
  fx_policy: string
  fx_publication_grace_days: number
  source: SourceSettings
  fx_coverage: FxCoverage
}

export interface TransactionFilters {
  search: string
  start_date: string
  end_date: string
  category: string
  payment_method: string
  bank: string
  currency: string
  page: number
  page_size: number
}

export interface ViewResult<T> {
  envelope: ApiEnvelope<T>
  source: 'network' | 'cache'
  cachedAt?: string
}
