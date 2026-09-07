import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { SummaryPage } from './SummaryPage'

afterEach(() => vi.unstubAllGlobals())

it('renders exact total, accessible controls, and text chart alternatives', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    metadata: { api_schema_version: 1, cache_schema_version: 1, dataset_revision: 7, fx_revision: 4, generated_at: '2026-09-07T10:00:00+07:00', source_timestamp: '2026-09-07T00:00:00Z', reporting_timezone: 'Asia/Jakarta', conversion: { complete: true, converted_count: 1, missing_count: 0, provisional_count: 0 } },
    data: { start_date: '2026-09-01', end_date: '2026-09-07', total_idr: '90560', transaction_count: 1, original_subtotals: [{ amount: '5.66', amount_minor: '566', currency: 'USD' }], categories: [{ key: 'food_drink', name: 'Food', total_idr: '90560' }], trend: [{ period: '2026-09-07', total_idr: '90560', transaction_count: 1 }], trend_granularity: 'day', largest_merchants: [{ merchant: 'Cafe', total_idr: '90560', transaction_count: 1 }] },
  }), { headers: { 'content-type': 'application/json' } })))
  render(<SummaryPage />)
  expect((await screen.findAllByText('Rp90,560')).length).toBeGreaterThan(0)
  expect(screen.getByText('US$5.66')).toBeInTheDocument()
  expect(screen.getByLabelText('From')).toHaveAttribute('type', 'date')
  expect(screen.getByText('View trend as a table')).toBeInTheDocument()
})
