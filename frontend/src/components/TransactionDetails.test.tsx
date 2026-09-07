import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { TransactionDetails } from './TransactionDetails'

const transaction = vi.hoisted(() => vi.fn())
vi.mock('../lib/api', () => ({ api: { transaction }, ApiError: class ApiError extends Error {} }))

const data = { id: 'one', expense_at: '2026-09-05T03:00:00Z', jakarta_date: '2026-09-05', merchant: 'Hidden merchant', category_key: 'food_drink', category_name: 'Food', bank: null, payment_method: null, note: 'Hidden note', currency: 'IDR', amount_minor: '5000', original_amount: '5000', converted_idr: '5000', fx_rate: null, fx_rate_date: null, fx_source: null, fx_status: null }
const metadata = { api_schema_version: 1, cache_schema_version: 1, dataset_revision: 8, fx_revision: 4, generated_at: '2026-09-07T00:00:00Z', source_timestamp: null, reporting_timezone: 'Asia/Jakarta', conversion: { complete: true, converted_count: 1, missing_count: 0, provisional_count: 0 } }

afterEach(() => { cleanup(); transaction.mockReset() })

it('does not present detail fields when list and detail revisions differ', async () => {
  transaction.mockResolvedValueOnce({ envelope: { metadata, data }, source: 'network' })
  const onRefresh = vi.fn()
  const onClose = vi.fn()
  render(<TransactionDetails id="one" expectedDatasetRevision={7} expectedFxRevision={4} onRefresh={onRefresh} onClose={onClose} />)

  expect(await screen.findByText('Data changed')).toBeInTheDocument()
  expect(screen.queryByText('Hidden merchant')).not.toBeInTheDocument()
  expect(screen.queryByText('Hidden note')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Refresh transactions' }))
  expect(onRefresh).toHaveBeenCalledOnce()
})

it('presents detail when both revisions match', async () => {
  transaction.mockResolvedValueOnce({ envelope: { metadata, data }, source: 'network' })
  render(<TransactionDetails id="one" expectedDatasetRevision={8} expectedFxRevision={4} onRefresh={vi.fn()} onClose={vi.fn()} />)
  expect(await screen.findByText('Hidden merchant')).toBeInTheDocument()
  expect(screen.queryByText('Data changed')).not.toBeInTheDocument()
})
