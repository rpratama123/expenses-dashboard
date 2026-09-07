import { ChevronLeft, ChevronRight, Filter, Search, SlidersHorizontal } from 'lucide-react'
import { useDeferredValue, useEffect, useState } from 'react'
import { TransactionDetails } from '../components/TransactionDetails'
import { ErrorState, Freshness, LoadingState } from '../components/ViewState'
import { api } from '../lib/api'
import { formatDateTime } from '../lib/date-format'
import { formatIdr, formatOriginal } from '../lib/money'
import type { FilterOptions, Transaction, TransactionFilters, TransactionPage, ViewResult } from '../lib/types'
import { useForegroundRefresh } from '../lib/useForegroundRefresh'

const emptyOptions: FilterOptions = { categories: [], payment_methods: [], banks: [], currencies: [] }
const defaults: TransactionFilters = { search: '', start_date: '', end_date: '', category: '', payment_method: '', bank: '', currency: '', page: 1, page_size: 25 }

export function TransactionsPage() {
  const [filters, setFilters] = useState(defaults)
  const [search, setSearch] = useState('')
  const deferredSearch = useDeferredValue(search)
  const [result, setResult] = useState<ViewResult<TransactionPage> | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [showFilters, setShowFilters] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useForegroundRefresh(() => setAttempt((value) => value + 1))

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setResult(null); setError(null)
      setFilters((current) => ({ ...current, search: deferredSearch, page: 1 }))
    }, 300)
    return () => clearTimeout(timer)
  }, [deferredSearch])

  useEffect(() => {
    const controller = new AbortController()
    api.transactions(filters, controller.signal).then((value) => { setResult(value); setError(null) }).catch((value) => {
      if (!(value instanceof DOMException && value.name === 'AbortError')) setError(value)
    })
    return () => controller.abort()
  }, [filters, attempt])

  const options = result?.envelope.data.filters ?? emptyOptions
  const setFilter = (key: keyof TransactionFilters, value: string) => { setResult(null); setError(null); setFilters((current) => ({ ...current, [key]: value, page: 1 })) }
  return <div className="page">
    <header className="page-header transactions-heading"><div><p className="eyebrow">Read-only ledger</p><h1>Transactions</h1><p>Search and inspect the active snapshot.</p></div></header>
    <div className="transaction-tools">
      <label className="search-box"><Search aria-hidden="true" /><span className="sr-only">Search merchant or note</span><input type="search" value={search} maxLength={100} placeholder="Search merchant or note" onChange={(event) => setSearch(event.target.value)} /></label>
      <button className="button filter-toggle" onClick={() => setShowFilters((value) => !value)} aria-expanded={showFilters}><SlidersHorizontal /> Filters</button>
    </div>
    <section className={`filters ${showFilters ? 'open' : ''}`} aria-label="Transaction filters">
      <label>From<input type="date" value={filters.start_date} onChange={(event) => setFilter('start_date', event.target.value)} /></label>
      <label>To<input type="date" value={filters.end_date} onChange={(event) => setFilter('end_date', event.target.value)} /></label>
      <FilterSelect label="Category" value={filters.category} options={options.categories.map((item) => [item.key, item.name])} onChange={(value) => setFilter('category', value)} />
      <FilterSelect label="Payment" value={filters.payment_method} options={options.payment_methods.map((value) => [value, value])} onChange={(value) => setFilter('payment_method', value)} />
      <FilterSelect label="Bank" value={filters.bank} options={options.banks.map((value) => [value, value])} onChange={(value) => setFilter('bank', value)} />
      <FilterSelect label="Currency" value={filters.currency} options={options.currencies.map((value) => [value, value])} onChange={(value) => setFilter('currency', value)} />
      <button className="text-button" onClick={() => { setResult(null); setError(null); setFilters(defaults); setSearch('') }}><Filter /> Clear filters</button>
    </section>
    {!result && !error && <LoadingState label="Loading transactions" />}
    {Boolean(error) && <ErrorState error={error} retry={() => { setResult(null); setError(null); setAttempt((value) => value + 1) }} />}
    {result && !error && <>
      <Freshness meta={result.envelope.metadata} cachedAt={result.cachedAt} />
      <TransactionResults page={result.envelope.data} select={setSelected} />
      <Pagination page={result.envelope.data} change={(page) => { setResult(null); setError(null); setFilters((current) => ({ ...current, page })) }} />
    </>}
    {selected && result && <TransactionDetails id={selected} expectedDatasetRevision={result.envelope.metadata.dataset_revision} expectedFxRevision={result.envelope.metadata.fx_revision} onClose={() => setSelected(null)} onRefresh={() => { setSelected(null); setResult(null); setError(null); setAttempt((value) => value + 1) }} />}
  </div>
}

function FilterSelect({ label, value, options, onChange }: { label: string; value: string; options: string[][]; onChange: (value: string) => void }) {
  return <label>{label}<select value={value} onChange={(event) => onChange(event.target.value)}><option value="">All</option>{options.map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
}

function TransactionResults({ page, select }: { page: TransactionPage; select: (id: string) => void }) {
  if (!page.items.length) return <div className="empty-state compact"><span><Search /></span><h2>No matching transactions</h2><p>The active snapshot has no results for these exact filters.</p></div>
  return <>
    <div className="transaction-count">{page.total_items.toLocaleString()} result{page.total_items === 1 ? '' : 's'}</div>
    <div className="transaction-cards">{page.items.map((item) => <button key={item.id} onClick={() => select(item.id)}><TransactionRow item={item} /></button>)}</div>
    <div className="table-wrap"><table className="transactions-table"><thead><tr><th>Date</th><th>Merchant</th><th>Category</th><th>Payment</th><th className="amount">Original</th><th className="amount">IDR value</th></tr></thead><tbody>{page.items.map((item) => <tr key={item.id} onClick={() => select(item.id)} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') select(item.id) }}><td>{formatDateTime(item.expense_at)}</td><td><strong>{item.merchant || 'Unknown merchant'}</strong></td><td><span className="category-pill">{item.category_name}</span></td><td>{[item.bank, item.payment_method].filter(Boolean).join(' / ') || '—'}</td><td className="amount">{formatOriginal(item.amount_minor, item.currency)}</td><td className="amount">{item.converted_idr ? formatIdr(item.converted_idr) : <span className="missing">Unavailable</span>}</td></tr>)}</tbody></table></div>
  </>
}

function TransactionRow({ item }: { item: Transaction }) {
  return <><span className="card-date">{formatDateTime(item.expense_at)}</span><span className="card-main"><strong>{item.merchant || 'Unknown merchant'}</strong><small>{item.category_name} · {[item.bank, item.payment_method].filter(Boolean).join(' / ')}</small></span><span className="card-amount"><strong>{formatOriginal(item.amount_minor, item.currency)}</strong>{item.currency !== 'IDR' && <small>{item.converted_idr ? formatIdr(item.converted_idr) : 'IDR unavailable'}</small>}</span></>
}

function Pagination({ page, change }: { page: TransactionPage; change: (value: number) => void }) {
  return <nav className="pagination" aria-label="Transaction pages"><button disabled={page.page <= 1} onClick={() => change(page.page - 1)} aria-label="Previous page"><ChevronLeft /></button><span>Page <strong>{page.page}</strong> of {Math.max(1, page.total_pages)}</span><button disabled={page.page >= page.total_pages} onClick={() => change(page.page + 1)} aria-label="Next page"><ChevronRight /></button></nav>
}
