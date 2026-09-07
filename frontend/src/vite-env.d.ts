/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

declare const self: ServiceWorkerGlobalScope

interface WindowEventMap {
  'expenses:cache-cleared': CustomEvent
}
