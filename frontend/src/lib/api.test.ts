import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api } from './api'
import { canonicalViewKey, offlineDb, saveCachedView } from './offline'
import type { ApiEnvelope, Summary } from './types'

const data: Summary = { start_date: '2026-09-01', end_date: '2026-09-07', total_idr: '5000', transaction_count: 1, original_subtotals: [], categories: [], trend: [], trend_granularity: 'day', largest_merchants: [] }
const metadata = { api_schema_version: 1, cache_schema_version: 1, dataset_revision: 4, fx_revision: 2, generated_at: '2026-09-07T00:00:00Z', source_timestamp: '2026-09-06T00:00:00Z', reporting_timezone: 'Asia/Jakarta', conversion: { complete: true, converted_count: 1, missing_count: 0, provisional_count: 0 } }
const envelope: ApiEnvelope<Summary> = { metadata, data }

beforeEach(async () => { await offlineDb.views.clear() })
afterEach(() => vi.unstubAllGlobals())

describe('API safety and fallback', () => {
  it('accepts the authoritative nested envelope and sends backend date names', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope), { status: 200, headers: { 'content-type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    expect((await api.summary('2026-09-01', '2026-09-07')).envelope.data.total_idr).toBe('5000')
    expect(String(fetchMock.mock.calls[0][0])).toContain('start_date=2026-09-01&end_date=2026-09-07')
  })

  it('rejects flat envelopes and unsafe numeric revisions', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...metadata, data }), { headers: { 'content-type': 'application/json' } })))
    await expect(api.summary('2026-09-01', '2026-09-07')).rejects.toMatchObject({ kind: 'invalid' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ metadata: { ...metadata, dataset_revision: Number.MAX_SAFE_INTEGER + 1 }, data }), { headers: { 'content-type': 'application/json' } })))
    await expect(api.summary('2026-09-01', '2026-09-07')).rejects.toMatchObject({ kind: 'invalid' })
  })

  it('validates backend-shaped transaction and settings payloads', async () => {
    const transaction = { id: 'one', expense_at: '2026-09-05T03:00:00Z', jakarta_date: '2026-09-05', merchant: null, category_key: 'food_drink', category_name: 'Food', bank: null, payment_method: null, note: null, currency: 'USD', amount_minor: '566', original_amount: '5.66', converted_idr: '90560', fx_rate: '16000', fx_rate_date: '2026-09-05', fx_source: 'ECB', fx_status: 'finalized' }
    const settings = { reporting_timezone: 'Asia/Jakarta', reporting_currency: 'IDR', currency_scales: { IDR: 1, USD: 100 }, fx_provider: 'Frankfurter / ECB', fx_policy: 'Historical Jakarta transaction date; no future rates', fx_publication_grace_days: 7, source: { snapshot_available: true, filename: 'expenses.sqlite3', source_timestamp: '2026-09-07T00:00:00Z', imported_at: '2026-09-07T00:01:00Z', last_import_error: null }, fx_coverage: { status: 'finalized', oldest_effective_date: '2026-09-01', newest_effective_date: '2026-09-07', last_fetched_at: '2026-09-07T00:00:00Z', required_days: 1, assigned_days: 1, finalized_days: 1, provisional_days: 0, missing_days: 0 } }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ metadata, data: transaction }), { headers: { 'content-type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ metadata, data: settings }), { headers: { 'content-type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    expect((await api.transaction('one')).envelope.data.amount_minor).toBe('566')
    expect((await api.settings()).envelope.data.fx_coverage.status).toBe('finalized')
  })

  it('accepts backend category option labels without local derivation', async () => {
    const page = { items: [], page: 1, page_size: 25, total_items: 0, total_pages: 0, filters: { categories: [{ key: 'food_drink', name: 'Food' }], payment_methods: [], banks: [], currencies: ['IDR'] } }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ metadata: { ...metadata, conversion: { ...metadata.conversion, converted_count: 0 } }, data: page }), { headers: { 'content-type': 'application/json' } })))
    const result = await api.transactions({ search: '', start_date: '', end_date: '', category: '', payment_method: '', bank: '', currency: '', page: 1, page_size: 25 })
    expect(result.envelope.data.filters.categories).toEqual([{ key: 'food_drink', name: 'Food' }])
  })

  it('uses an exact saved view on network failure', async () => {
    const key = canonicalViewKey('/api/v1/summary', { start_date: '2026-09-01', end_date: '2026-09-07' })
    await saveCachedView(key, '/api/v1/summary', envelope)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network failed')))
    expect((await api.summary('2026-09-01', '2026-09-07')).source).toBe('cache')
    await expect(api.summary('2026-08-01', '2026-08-31')).rejects.toMatchObject({ kind: 'offline' })
  })

  it('rejects auth responses and clears financial data', async () => {
    await saveCachedView('private', '/api/v1/settings', envelope)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Unauthorized', { status: 401 })))
    await expect(api.settings()).rejects.toBeInstanceOf(ApiError)
    expect(await offlineDb.views.count()).toBe(0)
  })
})
