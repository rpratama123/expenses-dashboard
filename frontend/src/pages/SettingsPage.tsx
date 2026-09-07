import { Check, Database, Download, HardDrive, Info, RefreshCw, ShieldCheck, Smartphone, Sun, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ErrorState, Freshness, LoadingState } from '../components/ViewState'
import { api } from '../lib/api'
import { clearFinancialCache, getCacheStats } from '../lib/offline'
import { getPreferences, savePreferences, type PeriodPreference, type Preferences, type ThemePreference } from '../lib/preferences'
import type { Settings, ViewResult } from '../lib/types'
import { useForegroundRefresh } from '../lib/useForegroundRefresh'

export function SettingsPage() {
  const [result, setResult] = useState<ViewResult<Settings> | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [attempt, setAttempt] = useState(0)
  useForegroundRefresh(() => setAttempt((value) => value + 1))
  useEffect(() => {
    const controller = new AbortController()
    api.settings(controller.signal).then((value) => { setResult(value); setError(null) }).catch((value) => {
      if (!(value instanceof DOMException && value.name === 'AbortError')) setError(value)
    })
    return () => controller.abort()
  }, [attempt])
  return <div className="page settings-page">
    <header className="page-header"><div><p className="eyebrow">Device & data</p><h1>Settings</h1><p>Preferences live on this device. Source data remains read-only.</p></div></header>
    <PreferencesPanel />
    {!result && !error && <LoadingState label="Loading system status" />}
    {Boolean(error) && <ErrorState error={error} retry={() => { setError(null); setAttempt((value) => value + 1) }} />}
    {result && <><Freshness meta={result.envelope.metadata} cachedAt={result.cachedAt} /><StatusPanels settings={result.envelope.data} /></>}
    <CachePanel />
    <InstallPanel />
  </div>
}

function PreferencesPanel() {
  const [preferences, setPreferences] = useState(getPreferences)
  const update = (next: Preferences) => { setPreferences(next); savePreferences(next) }
  return <section className="settings-panel"><header><Sun /><div><h2>Appearance & defaults</h2><p>Stored only in this browser.</p></div></header><div className="settings-fields">
    <label>Theme<select value={preferences.theme} onChange={(event) => update({ ...preferences, theme: event.target.value as ThemePreference })}><option value="system">Use device setting</option><option value="light">Light</option><option value="dark">Dark</option></select></label>
    <label>Default summary period<select value={preferences.defaultPeriod} onChange={(event) => update({ ...preferences, defaultPeriod: event.target.value as PeriodPreference })}><option value="current-month">Current month</option><option value="last-30-days">Last 30 days</option><option value="current-year">Current year</option></select></label>
  </div></section>
}

function StatusPanels({ settings }: { settings: Settings }) {
  const { source, fx_coverage: coverage } = settings
  return <div className="settings-grid">
    <section className="settings-panel"><header><Database /><div><h2>Snapshot</h2><p>{source.snapshot_available ? 'Active and ready' : 'Waiting for the first snapshot'}</p></div>{source.snapshot_available && <Check className="status-check" />}</header><dl className="status-list"><div><dt>Source file</dt><dd>{source.filename || 'Unavailable'}</dd></div><div><dt>Source timestamp</dt><dd>{displayDate(source.source_timestamp)}</dd></div><div><dt>Imported</dt><dd>{displayDate(source.imported_at)}</dd></div>{source.last_import_error && <div className="error-text"><dt>Latest import issue</dt><dd>{source.last_import_error.failure_reason}</dd></div>}</dl></section>
    <section className="settings-panel"><header><RefreshCw /><div><h2>Exchange rates</h2><p className={`fx-label ${coverage.status}`}>{coverage.status.replace('_', ' ')}</p></div></header><dl className="status-list"><div><dt>Source</dt><dd>{settings.fx_provider}</dd></div><div><dt>Coverage</dt><dd>{coverage.oldest_effective_date && coverage.newest_effective_date ? `${coverage.oldest_effective_date} to ${coverage.newest_effective_date}` : 'Unavailable'}</dd></div><div><dt>Required days</dt><dd>{coverage.assigned_days} of {coverage.required_days} assigned</dd></div><div><dt>Last fetched</dt><dd>{displayDate(coverage.last_fetched_at)}</dd></div><div><dt>Policy</dt><dd>{settings.fx_policy} ({settings.fx_publication_grace_days}-day grace)</dd></div></dl></section>
    <section className="settings-panel"><header><ShieldCheck /><div><h2>Reporting policy</h2><p>Consistent across dashboard views.</p></div></header><dl className="status-list"><div><dt>Currency</dt><dd>{settings.reporting_currency}</dd></div><div><dt>Timezone</dt><dd>{settings.reporting_timezone}</dd></div><div><dt>Currency scales</dt><dd>{Object.entries(settings.currency_scales).map(([currency, scale]) => `${currency}: ${scale}`).join(' / ')}</dd></div></dl><p className="fine-print"><Info /> USD is valued using the most recent historical rate on or before its Jakarta transaction date. Per-row values are rounded to whole rupiah before totals.</p></section>
  </div>
}

function CachePanel() {
  const [stats, setStats] = useState<{ entries: number; bytes: number; newest?: string }>({ entries: 0, bytes: 0 })
  const [cleared, setCleared] = useState(false)
  const [persistent, setPersistent] = useState<boolean | null>(null)
  const refresh = () => void getCacheStats().then(setStats)
  useEffect(() => { refresh(); void navigator.storage?.persisted?.().then(setPersistent) }, [])
  const clear = async () => { await clearFinancialCache(); refresh(); setCleared(true) }
  const requestPersistence = async () => setPersistent(await navigator.storage?.persist?.() ?? false)
  return <section className="settings-panel cache-panel"><header><HardDrive /><div><h2>Offline financial cache</h2><p>Exact views you successfully opened, up to 200 entries / 20 MiB.</p></div></header><div className="cache-stats"><strong>{stats.entries}</strong><span>saved views</span><strong>{formatBytes(stats.bytes)}</strong><span>used</span></div>{stats.newest && <p className="fine-print">Most recently accessed cache: {displayDate(stats.newest)}</p>}<div className="cache-actions">{persistent === false && <button className="button secondary" onClick={() => void requestPersistence()}><Download /> Protect storage</button>}<button className="button danger" onClick={() => void clear()}><Trash2 /> Clear saved financial data</button></div>{persistent && <p className="fine-print"><ShieldCheck />Persistent storage was granted by this browser. The operating system may still remove app data.</p>}{cleared && <span className="success-message" role="status"><Check /> Cache cleared. This does not sign out browser-managed Basic Auth.</span>}</section>
}

function InstallPanel() {
  return <section className="settings-panel install-panel"><header><Smartphone /><div><h2>Install on iPhone or iPad</h2><p>Use Safari while connected and authenticated.</p></div></header><ol><li><span>1</span>Open the Share menu in Safari.</li><li><span>2</span>Choose <strong>Add to Home Screen</strong>.</li><li><span>3</span>Open saved views once online before relying on them offline.</li></ol><p className="fine-print"><Download /> Offline storage is best-effort and can be removed by iOS. Only previously visited exact filters, pages, and details are available; background refresh is not promised.</p></section>
}

function displayDate(value?: string | null) { if (!value) return 'Unavailable'; try { return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) } catch { return value } }
function formatBytes(bytes: number) { return bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KiB` : `${(bytes / 1024 / 1024).toFixed(1)} MiB` }
