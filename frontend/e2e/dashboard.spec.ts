import { expect, test, type Page } from '@playwright/test'

const metadata = { api_schema_version: 1, cache_schema_version: 1, dataset_revision: 1, fx_revision: 1, generated_at: '2026-09-07T10:00:00+07:00', source_timestamp: '2026-09-07T00:00:00Z', reporting_timezone: 'Asia/Jakarta', conversion: { complete: true, converted_count: 7, missing_count: 0, provisional_count: 0 } }

async function mockApi(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let data: unknown
    if (path.endsWith('/summary')) data = { start_date: '2026-09-01', end_date: '2026-09-07', total_idr: '185500', transaction_count: 7, original_subtotals: [{ amount: '185500', amount_minor: '185500', currency: 'IDR' }], categories: [{ key: 'food_drink', name: 'Food', total_idr: '92000' }], trend: [{ period: '2026-09-05', total_idr: '185500', transaction_count: 7 }], trend_granularity: 'day', largest_merchants: [{ merchant: 'Warung', total_idr: '92000', transaction_count: 3 }] }
    else if (path.endsWith('/transactions')) data = { items: [transaction], page: 1, page_size: 25, total_items: 1, total_pages: 1, filters: { categories: [{ key: 'food_drink', name: 'Food' }], payment_methods: ['card'], banks: ['BCA'], currencies: ['IDR'] } }
    else if (path.endsWith('/transactions/one')) data = transaction
    else data = { reporting_timezone: 'Asia/Jakarta', reporting_currency: 'IDR', currency_scales: { IDR: 1, USD: 100 }, fx_provider: 'Frankfurter / ECB', fx_policy: 'Historical Jakarta transaction date; no future rates', fx_publication_grace_days: 7, source: { snapshot_available: true, filename: 'expenses-20260907T000000Z.sqlite3', source_timestamp: '2026-09-07T00:00:00Z', imported_at: '2026-09-07T00:01:00Z', last_import_error: null }, fx_coverage: { status: 'finalized', oldest_effective_date: '2026-09-01', newest_effective_date: '2026-09-07', last_fetched_at: '2026-09-07T00:00:00Z', required_days: 1, assigned_days: 1, finalized_days: 1, provisional_days: 0, missing_days: 0 } }
    await route.fulfill({ json: { metadata, data } })
  })
}

const transaction = { id: 'one', expense_at: '2026-09-05T03:00:00Z', jakarta_date: '2026-09-05', merchant: 'Warung', category_key: 'food_drink', category_name: 'Food', bank: 'BCA', payment_method: 'card', note: 'Lunch', currency: 'IDR', amount_minor: '5000', original_amount: '5000', converted_idr: '5000', fx_rate: null, fx_rate_date: null, fx_source: null, fx_status: null }

test.beforeEach(async ({ page }) => { await mockApi(page) })

test('summary, transactions, details, and settings are navigable', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Summary' })).toBeVisible()
  await expect(page.getByText('Rp185,500').first()).toBeVisible()
  await page.getByRole('link', { name: 'Transactions' }).click()
  await expect(page.getByRole('heading', { name: 'Transactions' })).toBeVisible()
  await page.getByText('Warung').last().click()
  await expect(page.getByRole('dialog')).toContainText('Lunch')
  await page.getByLabel('Close transaction details').click()
  await page.getByRole('link', { name: 'Settings' }).click()
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
  await expect(page.getByText('expenses-20260907T000000Z.sqlite3')).toBeVisible()
})

test('mobile uses bottom navigation and desktop uses sidebar', async ({ page, isMobile }) => {
  await page.goto('/')
  const bottom = page.locator('.bottom-nav')
  const sidebar = page.locator('.sidebar')
  if (isMobile) { await expect(bottom).toBeVisible(); await expect(sidebar).toBeHidden() }
  else { await expect(sidebar).toBeVisible(); await expect(bottom).toBeHidden() }
})

test('cold-start offline distinguishes visited and unvisited exact views', async ({ page, context }) => {
  await page.goto('/')
  await expect(page.getByText('Rp185,500').first()).toBeVisible()
  await page.evaluate(async () => { await navigator.serviceWorker.ready })
  await page.reload()
  await page.unroute('**/api/v1/**')
  await context.setOffline(true)
  await page.reload()
  await expect(page.getByText('Saved offline view')).toBeVisible()
  await page.getByRole('link', { name: 'Transactions' }).click()
  await expect(page.getByRole('heading', { name: 'Not saved for offline use' })).toBeVisible()
})
