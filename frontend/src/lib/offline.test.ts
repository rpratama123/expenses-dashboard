import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CACHE_SCHEMA, canonicalViewKey, clearFinancialCache, getCachedView, getCacheStats, offlineDb, saveCachedView } from './offline'
import type { ApiEnvelope } from './types'

const envelope = (revision = 1): ApiEnvelope<{ value: number }> => ({
  metadata: { api_schema_version: 1, cache_schema_version: 1, dataset_revision: revision, fx_revision: 3, generated_at: '2026-09-07T10:00:00+07:00', source_timestamp: null, reporting_timezone: 'Asia/Jakarta', conversion: { complete: true, converted_count: 1, missing_count: 0, provisional_count: 0 } },
  data: { value: revision },
})

beforeEach(async () => { await offlineDb.views.clear() })

describe('offline exact-view cache', () => {
  it('canonicalizes every query field independently of insertion order', () => {
    expect(canonicalViewKey('/api/v1/transactions', { page: 2, search: 'a & b', bank: '' }))
      .toBe('/api/v1/transactions?page=2&search=a%20%26%20b')
  })

  it('returns only the exact saved key and replaces numeric revisions atomically', async () => {
    const key = canonicalViewKey('/api/v1/summary', { start_date: '2026-09-01' })
    await saveCachedView(key, '/api/v1/summary', envelope())
    expect((await getCachedView<{ value: number }>(key))?.envelope.data.value).toBe(1)
    expect(await getCachedView('/api/v1/summary?start_date=2026-08-01')).toBeNull()
    await saveCachedView(key, '/api/v1/summary', envelope(2))
    expect((await getCachedView<{ value: number }>(key))?.envelope.metadata.dataset_revision).toBe(2)
  })

  it('discards incompatible entries and clears explicitly', async () => {
    await offlineDb.views.put({ key: 'old', endpoint: '/api/v1/summary', schema: `${CACHE_SCHEMA}-old`, datasetRevision: 1, fxRevision: 1, cachedAt: 'x', accessedAt: 1, bytes: 1, envelope: envelope() })
    expect(await getCachedView('old')).toBeNull()
    await saveCachedView('current', '/api/v1/settings', envelope())
    await clearFinancialCache()
    expect((await getCacheStats()).entries).toBe(0)
  })

  it('keeps online use working when browser storage is denied', async () => {
    const put = vi.spyOn(offlineDb.views, 'put').mockRejectedValueOnce(new DOMException('Quota exceeded', 'QuotaExceededError'))
    await expect(saveCachedView('denied', '/api/v1/summary', envelope())).resolves.toBeUndefined()
    expect(put).toHaveBeenCalled()
    put.mockRestore()
  })
})
