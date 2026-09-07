import Dexie, { type EntityTable } from 'dexie'
import type { ApiEnvelope } from './types'

export const CACHE_SCHEMA = '2'
export const MAX_ENTRIES = 200
export const MAX_BYTES = 20 * 1024 * 1024

export interface CachedView {
  key: string
  schema: string
  endpoint: string
  datasetRevision: number
  fxRevision: number
  cachedAt: string
  accessedAt: number
  bytes: number
  envelope: ApiEnvelope<unknown>
}

class OfflineDatabase extends Dexie {
  views!: EntityTable<CachedView, 'key'>
  constructor() {
    super('expenses-dashboard')
    this.version(1).stores({ views: '&key, accessedAt, schema, datasetRevision, fxRevision' })
  }
}

export const offlineDb = new OfflineDatabase()

export function canonicalViewKey(endpoint: string, params: Record<string, string | number | undefined> = {}): string {
  const query = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== '')
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join('&')
  return query ? `${endpoint}?${query}` : endpoint
}

export async function getCachedView<T>(key: string): Promise<{ envelope: ApiEnvelope<T>; cachedAt: string } | null> {
  try {
    const view = await offlineDb.views.get(key)
    if (!view || view.schema !== CACHE_SCHEMA) {
      if (view) await offlineDb.views.delete(key)
      return null
    }
    await offlineDb.views.update(key, { accessedAt: Date.now() })
    return { envelope: view.envelope as ApiEnvelope<T>, cachedAt: view.cachedAt }
  } catch { return null }
}

export async function saveCachedView<T>(key: string, endpoint: string, envelope: ApiEnvelope<T>): Promise<void> {
  try {
    const serialized = JSON.stringify(envelope)
    const bytes = new Blob([serialized]).size
    if (bytes > MAX_BYTES) return
    await offlineDb.transaction('rw', offlineDb.views, async () => {
      await offlineDb.views.put({
        key, endpoint, schema: CACHE_SCHEMA, datasetRevision: envelope.metadata.dataset_revision,
        fxRevision: envelope.metadata.fx_revision, cachedAt: new Date().toISOString(), accessedAt: Date.now(),
        bytes, envelope: envelope as ApiEnvelope<unknown>,
      })
      const entries = await offlineDb.views.orderBy('accessedAt').toArray()
      let total = entries.reduce((sum, entry) => sum + entry.bytes, 0)
      let count = entries.length
      for (const entry of entries) {
        if (count <= MAX_ENTRIES && total <= MAX_BYTES) break
        await offlineDb.views.delete(entry.key)
        total -= entry.bytes
        count -= 1
      }
    })
  } catch { /* Storage is best-effort; online requests must remain usable. */ }
}

export async function clearFinancialCache(): Promise<void> {
  try { await offlineDb.views.clear() } catch { /* Storage can be denied. */ }
  window.dispatchEvent(new CustomEvent('expenses:cache-cleared'))
}

export async function getCacheStats(): Promise<{ entries: number; bytes: number; newest?: string }> {
  try {
    const entries = await offlineDb.views.toArray()
    return {
      entries: entries.length,
      bytes: entries.reduce((sum, item) => sum + item.bytes, 0),
      newest: entries.sort((a, b) => b.accessedAt - a.accessedAt)[0]?.cachedAt,
    }
  } catch { return { entries: 0, bytes: 0 } }
}
