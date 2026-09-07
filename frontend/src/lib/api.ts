import { canonicalViewKey, clearFinancialCache, getCachedView, saveCachedView } from './offline'
import type { ApiEnvelope, Settings, Summary, Transaction, TransactionFilters, TransactionPage, ViewResult } from './types'

export class ApiError extends Error {
  constructor(message: string, public kind: 'auth' | 'server' | 'invalid' | 'offline' | 'not-found', public status?: number) { super(message) }
}

function asEnvelope<T>(value: unknown, validate: (data: unknown) => data is T): ApiEnvelope<T> {
  if (!record(value) || !isMetadata(value.metadata) || value.data === undefined) {
    throw new ApiError('The server response is missing required revision metadata.', 'invalid')
  }
  if (!validate(value.data)) throw new ApiError('The server returned an invalid view payload.', 'invalid')
  return value as unknown as ApiEnvelope<T>
}

async function requestView<T>(endpoint: string, params: Record<string, string | number | undefined>, validate: (data: unknown) => data is T, signal?: AbortSignal): Promise<ViewResult<T>> {
  const key = canonicalViewKey(endpoint, params)
  const url = new URL(endpoint, window.location.origin)
  Object.entries(params).forEach(([name, value]) => { if (value !== undefined && value !== '') url.searchParams.set(name, String(value)) })
  try {
    const response = await fetch(url, { signal, credentials: 'same-origin', headers: { Accept: 'application/json' }, cache: 'no-store' })
    if (response.status === 401 || response.status === 403) {
      await clearFinancialCache()
      throw new ApiError('Authentication is required. Reopen the app online and sign in.', 'auth', response.status)
    }
    if (response.status === 404) throw new ApiError('This transaction is no longer in the active snapshot.', 'not-found', 404)
    if (!response.ok) throw new ApiError(`The server returned ${response.status}.`, 'server', response.status)
    if (response.redirected || !(response.headers.get('content-type') ?? '').toLowerCase().includes('application/json')) {
      await clearFinancialCache()
      throw new ApiError('Authentication or a valid JSON response is required.', 'auth', response.status)
    }
    const envelope = asEnvelope<T>(await response.json(), validate)
    await saveCachedView(key, endpoint, envelope)
    return { envelope, source: 'network' }
  } catch (error) {
    if (error instanceof ApiError || (error instanceof DOMException && error.name === 'AbortError')) throw error
    if (!(error instanceof TypeError)) throw new ApiError('The server returned invalid JSON.', 'invalid')
    const cached = await getCachedView<T>(key)
    if (cached) return { ...cached, source: 'cache' }
    throw new ApiError('This exact view is unavailable offline.', 'offline')
  }
}

export const api = {
  summary: (dateFrom: string, dateTo: string, signal?: AbortSignal) => requestView<Summary>('/api/v1/summary', { start_date: dateFrom, end_date: dateTo }, isSummary, signal),
  transactions: (filters: TransactionFilters, signal?: AbortSignal) => requestView<TransactionPage>('/api/v1/transactions', { ...filters }, isTransactionPage, signal),
  transaction: (id: string, signal?: AbortSignal) => requestView<Transaction>(`/api/v1/transactions/${encodeURIComponent(id)}`, {}, isTransaction, signal),
  settings: (signal?: AbortSignal) => requestView<Settings>('/api/v1/settings', {}, isSettings, signal),
}

function record(value: unknown): value is Record<string, unknown> { return Boolean(value) && typeof value === 'object' }
function strings(value: unknown): value is string[] { return Array.isArray(value) && value.every((item) => typeof item === 'string') }
function safeRevision(value: unknown): value is number { return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 }
function nullableString(value: unknown): value is string | null { return typeof value === 'string' || value === null }
function nonnegativeInteger(value: unknown): value is number { return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 }
function isMetadata(value: unknown): boolean {
  if (!record(value) || !record(value.conversion)) return false
  return safeRevision(value.api_schema_version) && safeRevision(value.cache_schema_version)
    && safeRevision(value.dataset_revision) && safeRevision(value.fx_revision)
    && typeof value.generated_at === 'string' && nullableString(value.source_timestamp)
    && typeof value.reporting_timezone === 'string' && typeof value.conversion.complete === 'boolean'
    && nonnegativeInteger(value.conversion.converted_count) && nonnegativeInteger(value.conversion.missing_count)
    && nonnegativeInteger(value.conversion.provisional_count)
}
function isTransaction(value: unknown): value is Transaction {
  if (!record(value)) return false
  return ['id', 'expense_at', 'jakarta_date', 'category_key', 'category_name', 'currency', 'amount_minor', 'original_amount'].every((key) => typeof value[key] === 'string')
    && nullableString(value.merchant) && nullableString(value.bank) && nullableString(value.payment_method)
    && nullableString(value.note) && nullableString(value.converted_idr) && nullableString(value.fx_rate)
    && nullableString(value.fx_rate_date) && nullableString(value.fx_source) && nullableString(value.fx_status)
}
function isSummary(value: unknown): value is Summary {
  if (!record(value)) return false
  return ['start_date', 'end_date', 'total_idr'].every((key) => typeof value[key] === 'string')
    && nonnegativeInteger(value.transaction_count)
    && Array.isArray(value.original_subtotals) && value.original_subtotals.every((item) => record(item) && typeof item.currency === 'string' && typeof item.amount === 'string' && typeof item.amount_minor === 'string')
    && Array.isArray(value.categories) && value.categories.every((item) => record(item) && typeof item.key === 'string' && typeof item.name === 'string' && typeof item.total_idr === 'string')
    && Array.isArray(value.trend) && value.trend.every((item) => record(item) && typeof item.period === 'string' && typeof item.total_idr === 'string' && nonnegativeInteger(item.transaction_count))
    && Array.isArray(value.largest_merchants) && value.largest_merchants.every((item) => record(item) && typeof item.merchant === 'string' && typeof item.total_idr === 'string' && nonnegativeInteger(item.transaction_count))
    && (value.trend_granularity === 'day' || value.trend_granularity === 'month')
}
function isTransactionPage(value: unknown): value is TransactionPage {
  if (!record(value) || !Array.isArray(value.items) || !value.items.every(isTransaction) || !record(value.filters)) return false
  return ['page', 'page_size', 'total_items', 'total_pages'].every((key) => typeof value[key] === 'number')
    && Array.isArray(value.filters.categories) && value.filters.categories.every((item) => record(item) && typeof item.key === 'string' && typeof item.name === 'string')
    && strings(value.filters.payment_methods)
    && strings(value.filters.banks) && strings(value.filters.currencies)
}
function isSettings(value: unknown): value is Settings {
  if (!record(value) || !record(value.currency_scales) || !record(value.source) || !record(value.fx_coverage)) return false
  const coverage = value.fx_coverage
  const importErrorValid = value.source.last_import_error === null
    || (record(value.source.last_import_error) && typeof value.source.last_import_error.filename === 'string' && typeof value.source.last_import_error.failure_reason === 'string' && typeof value.source.last_import_error.imported_at === 'string')
  return importErrorValid && typeof value.source.snapshot_available === 'boolean'
    && nullableString(value.source.filename) && nullableString(value.source.source_timestamp)
    && nullableString(value.source.imported_at) && typeof value.reporting_timezone === 'string'
    && typeof value.reporting_currency === 'string'
    && Object.values(value.currency_scales).every((scale) => nonnegativeInteger(scale))
    && typeof value.fx_provider === 'string' && typeof value.fx_policy === 'string'
    && nonnegativeInteger(value.fx_publication_grace_days) && typeof coverage.status === 'string'
    && nullableString(coverage.oldest_effective_date) && nullableString(coverage.newest_effective_date)
    && nullableString(coverage.last_fetched_at)
    && ['required_days', 'assigned_days', 'finalized_days', 'provisional_days', 'missing_days'].every((key) => nonnegativeInteger(coverage[key]))
}
