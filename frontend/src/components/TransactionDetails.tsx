import { X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { formatDateTime } from '../lib/date-format'
import { formatIdr, formatOriginal } from '../lib/money'
import type { ViewResult, Transaction } from '../lib/types'
import { ErrorState, Freshness, LoadingState } from './ViewState'

interface TransactionDetailsProps {
  id: string
  expectedDatasetRevision: number
  expectedFxRevision: number
  onClose: () => void
  onRefresh: () => void
}

export function TransactionDetails({ id, expectedDatasetRevision, expectedFxRevision, onClose, onRefresh }: TransactionDetailsProps) {
  const [result, setResult] = useState<ViewResult<Transaction> | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    api.transaction(id, controller.signal).then(setResult).catch((value) => {
      if (!(value instanceof DOMException && value.name === 'AbortError')) setError(value)
    })
    return () => controller.abort()
  }, [id, attempt])

  return <div className="drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="drawer" role="dialog" aria-modal="true" aria-labelledby="detail-title">
      <header><div><p className="eyebrow">Transaction record</p><h2 id="detail-title">Details</h2></div><button className="icon-button" onClick={onClose} aria-label="Close transaction details"><X /></button></header>
      {!result && !error && <LoadingState />}
      {Boolean(error) && <ErrorState error={error} retry={() => { setResult(null); setError(null); setAttempt((value) => value + 1) }} />}
      {result && (result.envelope.metadata.dataset_revision !== expectedDatasetRevision || result.envelope.metadata.fx_revision !== expectedFxRevision)
        ? <RevisionMismatch onRefresh={onRefresh} onClose={onClose} />
        : result && <><DetailContent transaction={result.envelope.data} /><Freshness meta={result.envelope.metadata} cachedAt={result.cachedAt} /></>}
    </section>
  </div>
}

function RevisionMismatch({ onRefresh, onClose }: { onRefresh: () => void; onClose: () => void }) {
  return <div className="state-panel revision-mismatch" role="alert">
    <strong>Data changed</strong>
    <p>The snapshot or exchange rates changed after this transaction list loaded. Refresh the list before opening details.</p>
    <div className="state-actions"><button className="button primary" onClick={onRefresh}>Refresh transactions</button><button className="button secondary" onClick={onClose}>Close</button></div>
  </div>
}

function DetailContent({ transaction: item }: { transaction: Transaction }) {
  return <div className="detail-content">
    <div className="detail-hero"><span>{item.category_name}</span><strong>{formatOriginal(item.amount_minor, item.currency)}</strong>{item.currency !== 'IDR' && <small>{item.converted_idr ? formatIdr(item.converted_idr) : 'IDR conversion unavailable'}</small>}</div>
    <dl className="detail-list">
      <div><dt>Merchant</dt><dd>{item.merchant || 'Unknown merchant'}</dd></div>
      <div><dt>Date</dt><dd>{formatDateTime(item.expense_at)}</dd></div>
      <div><dt>Payment</dt><dd>{[item.bank, item.payment_method].filter(Boolean).join(' / ') || 'Not recorded'}</dd></div>
      <div><dt>Note</dt><dd>{item.note || 'No note'}</dd></div>
      {item.currency === 'USD' && <><div><dt>Rate</dt><dd>{item.fx_rate ? `1 USD = ${item.fx_rate} IDR` : 'Unavailable'}</dd></div><div><dt>Rate source</dt><dd>{[item.fx_source, item.fx_rate_date, item.fx_status].filter(Boolean).join(' / ')}</dd></div></>}
      <div><dt>Record ID</dt><dd className="mono">{item.id}</dd></div>
    </dl>
  </div>
}
