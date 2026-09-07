import { AlertTriangle, CalendarDays, CircleDollarSign, Receipt, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { periodDates } from '../lib/dates'
import { chartNumber, formatIdr, formatOriginal } from '../lib/money'
import { getPreferences } from '../lib/preferences'
import { useForegroundRefresh } from '../lib/useForegroundRefresh'
import type { Summary, ViewResult } from '../lib/types'
import { ErrorState, Freshness, LoadingState } from '../components/ViewState'

const colors = ['#e3573e', '#3d7962', '#d89a3c', '#7c6ea8', '#4e8297', '#a85855']

export function SummaryPage() {
  const initial = periodDates(getPreferences().defaultPeriod)
  const [from, setFrom] = useState(initial.from)
  const [to, setTo] = useState(initial.to)
  const [query, setQuery] = useState(initial)
  const [result, setResult] = useState<ViewResult<Summary> | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [attempt, setAttempt] = useState(0)
  useForegroundRefresh(() => setAttempt((value) => value + 1))

  useEffect(() => {
    const controller = new AbortController()
    api.summary(query.from, query.to, controller.signal).then((value) => { setResult(value); setError(null) }).catch((value) => {
      if (!(value instanceof DOMException && value.name === 'AbortError')) setError(value)
    })
    return () => controller.abort()
  }, [query, attempt])

  return <div className="page">
    <header className="page-header">
      <div><p className="eyebrow">Spending overview</p><h1>Summary</h1><p>What moved through your accounts, without the noise.</p></div>
      <form className="period-control" onSubmit={(event) => { event.preventDefault(); setResult(null); setError(null); setQuery({ from, to }) }}>
        <label>From<input type="date" value={from} max={to} onChange={(event) => setFrom(event.target.value)} required /></label>
        <label>To<input type="date" value={to} min={from} onChange={(event) => setTo(event.target.value)} required /></label>
        <button className="button primary" type="submit"><CalendarDays /> Apply</button>
      </form>
    </header>
    {!result && !error && <LoadingState label="Loading summary" />}
    {Boolean(error) && <ErrorState error={error} retry={() => { setResult(null); setError(null); setAttempt((value) => value + 1) }} />}
    {result && <SummaryContent result={result} />}
  </div>
}

function SummaryContent({ result }: { result: ViewResult<Summary> }) {
  const { data, metadata } = result.envelope
  if (data.transaction_count === 0) return <>
    <Freshness meta={metadata} cachedAt={result.cachedAt} />
    <div className="empty-state"><span><Sparkles /></span><h2>No expenses in this period</h2><p>This date range is intentionally empty. Choose another range to review earlier activity.</p></div>
  </>
  const categories = data.categories.map((item) => ({ ...item, value: chartNumber(item.total_idr) }))
  const trend = data.trend.map((item) => ({ ...item, value: chartNumber(item.total_idr), label: formatTrendDate(item.period, data.trend_granularity) }))
  return <>
    <Freshness meta={metadata} cachedAt={result.cachedAt} />
    {!metadata.conversion.complete && <div className="warning" role="alert"><AlertTriangle />IDR totals exclude {metadata.conversion.missing_count} transaction(s) without an FX rate.</div>}
    {!!metadata.conversion.provisional_count && <div className="warning provisional" role="status"><CircleDollarSign />{metadata.conversion.provisional_count} conversion(s) use provisional historical rates.</div>}
    <section className="kpi-grid" aria-label="Period totals">
      <article className="kpi primary-kpi"><span>Total spending</span><strong>{formatIdr(data.total_idr)}</strong><small>Converted reporting total</small></article>
      <article className="kpi"><span>Transactions</span><strong>{data.transaction_count.toLocaleString()}</strong><small>{data.start_date} to {data.end_date}</small></article>
      <article className="kpi"><span>Original currencies</span><div className="subtotals">{data.original_subtotals.map((value) => <strong key={value.currency}>{formatOriginal(value.amount_minor, value.currency)}</strong>)}</div><small>Before historical conversion</small></article>
    </section>
    <div className="dashboard-grid">
      <section className="panel trend-panel"><PanelTitle title="Spending rhythm" subtitle={`${data.trend_granularity === 'day' ? 'Daily' : 'Monthly'} IDR totals`} />
        <div className="chart" role="img" aria-label="Spending trend chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={trend} margin={{ top: 10, right: 4, bottom: 0, left: 4 }}><CartesianGrid vertical={false} stroke="var(--line)" /><XAxis dataKey="label" tickLine={false} axisLine={false} /><YAxis hide /><Tooltip cursor={{ fill: 'var(--soft)' }} formatter={(value) => formatIdr(String(value))} /><Bar dataKey="value" fill="#3d7962" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer></div>
        <details className="data-alternative"><summary>View trend as a table</summary><table><thead><tr><th>Date</th><th>Amount</th><th>Count</th></tr></thead><tbody>{data.trend.map((item) => <tr key={item.period}><td>{item.period}</td><td>{formatIdr(item.total_idr)}</td><td>{item.transaction_count}</td></tr>)}</tbody></table></details>
      </section>
      <section className="panel category-panel"><PanelTitle title="By category" subtitle="Share of IDR spending" />
        <div className="chart category-chart" role="img" aria-label="Category spending chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={categories} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 8 }}><XAxis type="number" hide /><YAxis type="category" dataKey="name" width={90} axisLine={false} tickLine={false} /><Tooltip formatter={(value) => formatIdr(String(value))} /><Bar dataKey="value" radius={[0, 5, 5, 0]}>{categories.map((item, index) => <Cell key={item.key} fill={colors[index % colors.length]} />)}</Bar></BarChart></ResponsiveContainer></div>
        <table className="compact-table"><caption className="sr-only">Category spending values</caption><tbody>{data.categories.map((item, index) => <tr key={item.key}><td><i style={{ background: colors[index % colors.length] }} />{item.name}</td><td>{formatIdr(item.total_idr)}</td></tr>)}</tbody></table>
      </section>
      <section className="panel merchants-panel"><PanelTitle title="Largest merchants" subtitle="Ranked by converted total" />
        <ol className="merchant-list">{data.largest_merchants.map((item, index) => <li key={`${item.merchant}-${index}`}><span className="rank">{String(index + 1).padStart(2, '0')}</span><span><strong>{item.merchant}</strong><small>{item.transaction_count} transaction{item.transaction_count === 1 ? '' : 's'}</small></span><b>{formatIdr(item.total_idr)}</b></li>)}</ol>
      </section>
    </div>
  </>
}

function PanelTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return <header className="panel-title"><div><h2>{title}</h2><p>{subtitle}</p></div><Receipt aria-hidden="true" /></header>
}

function formatTrendDate(value: string, granularity: 'day' | 'month') {
  const date = new Date(`${value}${granularity === 'month' ? '-01' : ''}T00:00:00`)
  return new Intl.DateTimeFormat(undefined, granularity === 'month' ? { month: 'short' } : { day: 'numeric', month: 'short' }).format(date)
}
