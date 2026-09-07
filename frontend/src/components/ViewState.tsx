import { AlertTriangle, CloudOff, LoaderCircle } from 'lucide-react'
import { ApiError } from '../lib/api'
import type { ApiMetadata } from '../lib/types'

export function LoadingState({ label = 'Loading view' }: { label?: string }) {
  return <div className="state-panel" role="status"><LoaderCircle className="spin" /><strong>{label}</strong></div>
}

export function ErrorState({ error, retry }: { error: unknown; retry: () => void }) {
  const apiError = error instanceof ApiError ? error : null
  return <div className="state-panel error" role="alert">
    {apiError?.kind === 'offline' ? <CloudOff /> : <AlertTriangle />}
    <strong>{apiError?.kind === 'offline' ? 'Not saved for offline use' : 'Unable to load this view'}</strong>
    <p>{error instanceof Error ? error.message : 'Try again.'}</p>
    <button className="button secondary" onClick={retry}>Try again</button>
  </div>
}

export function Freshness({ meta, cachedAt }: { meta: ApiMetadata; cachedAt?: string }) {
  return <div className={`freshness ${cachedAt ? 'stale' : ''}`} role="status">
    <span>{cachedAt ? 'Saved offline view' : 'Live data'}</span>
    <span>{cachedAt ? `Cached ${formatTime(cachedAt)}` : `Updated ${formatTime(meta.generated_at)}`}</span>
    <span>Dataset {meta.dataset_revision} / FX {meta.fx_revision}</span>
    <span>{meta.conversion.complete ? `${meta.conversion.converted_count} converted` : `${meta.conversion.missing_count} missing conversions`}</span>
  </div>
}

function formatTime(value: string) {
  try { return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) }
  catch { return value }
}
