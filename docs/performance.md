# Performance baseline

The initial implementation was checked with a generated, complete 100,000-row IDR snapshot. Rows covered one month, 12 categories, and 100 merchants. The measurement included source integrity validation, normalized replacement population, and atomic activation; the summary measurement covered the full month after one warm-up request.

| Environment | Import | Warm full-month summary |
| --- | ---: | ---: |
| Linux x86_64, Intel Core i3-7100 (2 cores / 4 threads), local workspace storage | 2.85 s | 0.47 s |

These numbers are a development baseline, not a guarantee for Unraid. Repeat the same generated 100,000-row check against `/mnt/user/appdata/expenses-dashboard` on the target machine because filesystem, FUSE/user-share, cache, and concurrent workload behavior can differ. The acceptance target is a warm common query below one second with readers observing no partial replacement.

The generated database was temporary and contained no real financial data. Do not add performance fixtures containing personal data to the repository.
