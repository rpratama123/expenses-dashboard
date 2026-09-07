/// <reference lib="webworker" />
import { clientsClaim } from 'workbox-core'
import { cleanupOutdatedCaches, precacheAndRoute } from 'workbox-precaching'
import { registerRoute } from 'workbox-routing'

declare let self: ServiceWorkerGlobalScope & { __WB_MANIFEST: Array<{ url: string; revision?: string }> }

precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()
clientsClaim()

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') void self.skipWaiting()
})

registerRoute(
  ({ request, url }) => request.mode === 'navigate' && url.origin === self.location.origin && !url.pathname.startsWith('/api/') && !url.pathname.startsWith('/health/'),
  async ({ request }) => {
    try {
      const response = await fetch(request)
      const type = response.headers.get('content-type') ?? ''
      if (!response.ok || response.redirected || !type.includes('text/html')) throw new Error('Invalid navigation response')
      return response
    } catch {
      const fallback = await caches.match('/index.html') ?? await caches.match('/')
      return fallback ?? Response.error()
    }
  },
)
