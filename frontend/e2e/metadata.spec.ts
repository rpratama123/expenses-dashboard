import { expect, test } from '@playwright/test'

test('publishes one credentialed manifest and complete iOS metadata', async ({ page, request }) => {
  await page.goto('/')
  await expect(page).toHaveTitle('Expenses Dashboard')
  await expect(page.locator('link[rel="manifest"]')).toHaveCount(1)
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('crossorigin', 'use-credentials')
  await expect(page.locator('meta[name="apple-mobile-web-app-capable"]')).toHaveAttribute('content', 'yes')
  await expect(page.locator('meta[name="apple-mobile-web-app-status-bar-style"]')).toHaveAttribute('content', 'black-translucent')
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute('href', '/apple-touch-icon.png')
  const manifest = await (await request.get('/manifest.webmanifest')).json()
  expect(manifest).toMatchObject({ id: '/', start_url: '/', scope: '/', display: 'standalone' })
  for (const asset of ['/favicon.svg', '/favicon-16x16.png', '/favicon-32x32.png', '/apple-touch-icon.png', ...manifest.icons.map((icon: { src: string }) => icon.src)]) {
    const response = await request.get(asset)
    expect(response.ok()).toBeTruthy()
    expect(response.headers()['content-type']).not.toContain('text/html')
  }
})
