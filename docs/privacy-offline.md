# Privacy and Offline Behavior

## Security boundary

The application is single-user and has no login, authorization model, or encrypted per-user store. Cloudflare Tunnel and Nginx Proxy Manager Basic Auth are the online access boundary. Every route and asset, including APIs, manifest, icons, and service worker, must remain behind the same access list. Direct container, host-port, or LAN access bypasses authentication and must be blocked.

Basic Auth credentials are managed by NPM and the browser. The application cannot provide reliable logout or remotely revoke content already stored on a device. Keep credentials out of URLs and logs, use HTTPS, and use a dedicated automation credential where practical. NPM authentication failures may be non-JSON.

The source mount is read-only. The application projects only fields needed by the dashboard and does not expose uploaded files, receipt paths/hashes, raw email/input, audit data, or ingestion/classification internals. Logs must not contain transaction bodies, notes, credentials, or raw provenance. External FX requests contain only currency/provider/date information, never expense data.

## What works offline

The service worker can reopen the previously installed app shell. Application-controlled IndexedDB storage retains only validated successful API results for exact views that were visited, including every filter and page parameter. Each view carries cached-at time, dataset revision, FX revision, and source timestamp. A cached view is shown as offline/stale and is not merged with results from another revision.

Offline support does not promise:

- Full transaction history, arbitrary search, or filters/pages/details never visited
- Background refresh or FX collection while the app is closed
- Permanent storage, especially on iOS
- App-level encryption of cached financial records
- Remote deletion after NPM credential revocation
- A reliable browser-level Basic Auth logout

An unvisited exact view reports that it is unavailable offline rather than substituting another page or implying completeness. Normal HTTP/CDN caches remain disabled; the bounded IndexedDB copy is intentional and separately clearable. The initial policy limits it to 20 MiB or 200 entries with least-recently-used eviction, subject to browser quota and eviction behavior.

## Device guidance

Use only a trusted, passcode-protected device with platform encryption enabled. Anyone able to unlock the device may be able to read cached financial data without contacting NPM. Clearing browser/site data or the dashboard's financial cache reduces retained data but does not prove forensic erasure. Clearing data also does not log out Basic Auth.

On observed `401`/`403` authentication rejection, the online application should not display or cache that response as financial data and should clear its financial view cache. This behavior still cannot act while the device remains offline. Reconnect regularly to obtain current revisions and authentication state.

iOS can evict site data and has release-specific standalone authentication behavior. Test on the real target iPhone: authenticate in Safari, install, launch standalone, visit representative views, cold-launch in airplane mode, distinguish visited from unvisited views, reconnect after credential revocation, clear cache offline, and apply a service-worker update. Installation alone is not evidence that offline content will persist.
