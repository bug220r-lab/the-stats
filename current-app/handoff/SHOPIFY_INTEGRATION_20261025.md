# Shopify collection and dashboard integration — October 25, 2026

Shopify is installed as a separate immutable collection in the existing Windows Streamlit application. The verified live dashboard is [http://127.0.0.1:8516/](http://127.0.0.1:8516/); select **Shopify**. A fresh invocation of `launch_windows.bat --port 8516 --no-browser` uses the normal private library. The existing port 8501 instance was occupied and left running. Normal future launches use the existing launcher; restarting an older instance loads the changed Python modules because file watching is disabled.

## Verified source and coverage

The signed-in Chrome session and connector both identify **[REDACTED]**, admin `https://admin.shopify.com/store/redacted-2971`, shop GID `65871708256`, primary domain `redacted-2971.myshopify.com`. Shopify reports canonical alias `fw00sb-21.myshopify.com` for this same shop; the browser's order links also use that alias. The store clock is **America/New_York**, reporting currency **USD**, plan **Starter**. The Stats™️ remains the analytics project name.

Collection began **2026-10-25T05:14:18Z** and completed **2026-10-25T05:23:48Z**. Store creation is `2025-12-23T23:23:15Z`. Completed historical reports cover **December 23, 2025 through October 24, 2026**, including **306 native daily dates**. Separate October 25 sales and traffic snapshots are explicitly incomplete. Full-history flags apply to each exact retained report scope and exhausted connections; they do not claim recovery of deleted metadata or a complete customer retention matrix.

The frozen package contains **47 dataset entries, 46 CSV tables, 5,702 heterogeneous CSV records and 92 assets including the manifest**. These are storage counts, not independent statistical samples. Dataset status counts are **38 collected, 5 partial, 3 verified empty, 1 blocked**. All original structured responses, executed operations, schema/documentation receipts and bounded browser observations remain retained. Normalized tables have literal source/file/row references where supplied by the collection. Stable row provenance is also available from the repository.

| Measure | Verified value | Scope |
| --- | ---: | --- |
| Orders | 3 | All accessible non-test orders; no test/cancelled filter applied; exact count and pagination exhausted |
| Gross product sales | USD 68.96 | Native completed-history sales report |
| Sales reversals | USD -21.98 | Native reversal dates retained |
| Net product sales | USD 46.98 | Excludes shipping/taxes |
| Shipping charges | USD 16.89 | Native net report value |
| Total sales | USD 63.87 | Net product sales plus shipping; reported tax/duty values zero |
| Net items sold | 3 | Separate from five original line-item records |
| Native period AOV | USD 22.986 | Displayed USD 22.99; before post-order adjustments |
| Sessions / period visitors | 284 / 210 | Online store; visitors are a directly queried distinct period count |
| Cart / checkout / completed-checkout sessions | 6 / 14 / 3 | Independently reported stages; not assumed a closed monotonic funnel |
| Completed-checkout session rate | 1.06% | 3 divided by 284; not an all-channel order conversion rate |
| Purchasing customers / current customer records | 3 / 4 | Distinct measures and periods |
| Current catalog / stock | 1 product, 5 variants, 25 units | Collection-time snapshot; current prices USD 24.99 |
| Gross payments / payment refunds / net payments | USD 97.84 / -33.97 / 63.87 | Native payment reporting |
| Processing fees / payouts | USD 5.80 / 58.07 | Separate report definitions and timing |

Installed channels are Online Store, Shop, Point of Sale and Spotify for Artists. Actual reported sales occurred through **Online Store and Spotify for Artists**. Installation does not prove activity. An initially empty publication API response does not establish absent channels.

Three historical order lines reference deleted products; their retained titles and missing current product IDs remain explicit. Historical inventory is a separate native report with 3,739 rows; current stock was not projected backward. Original UTC order timestamps, native report calendar days, browser transaction labels and payout schedule dates remain distinct. Browser payout dates and ShopifyQL payout reporting days differ while their net totals reconcile.

## Dashboard and persistence

The existing branding, SQLite storage and navigation are extended in place. Shopify is independent of the analysis-version selector and YouTube collections. Views cover **Sales & orders**, **Catalog & inventory**, **Traffic & conversion**, **Marketing & customers**, **Fulfillment & costs**, and **Coverage & sources**. Global Sources & provenance, Data quality and Coverage & cross-reference expose optional Shopify entries.

Daily sales/traffic support 7, 28 and 90 completed days, YTD and all available completed days. A complete unique date row and numeric metric are required for a window total or comparison. Current-day rows are separate. Zero-order AOV and zero-denominator rates are unavailable. Daily visitors are never summed; the 210 visitor card uses the exact full-period source summary. Report-specific details retain their printed native scope. Inventory filters update the stock card and downloaded records together. Exact source downloads and formula-neutralized filtered CSVs serve different purposes.

Frozen source: `data/collection/shopify-20261025/`. Live database: `%LOCALAPPDATA%\TheStats\collections\shopify-20261025\shopify.sqlite3`. New registry: `%LOCALAPPDATA%\TheStats\shopify_collections.json`. Existing archive/analysis registrations were not changed. Source package SHA-256 is `1d791d1eff6a6345803639e78897b0226a445264e3adc8ccf98dda142bc8ad81`; manifest SHA-256 is `603880e8130efa45e5d460798860e8127a0f0166c34aa2605d28b6fbc10d865f`; activated database SHA-256 is `dc589bbeedfdcee1ffc61e773f3d3c36e8f1d4366be0739fd410c2bcbc95ff35`.

Run/import/backup instructions: [Shopify](../docs/SHOPIFY.md). Exact replay is idempotent; changed source bytes require a new collection key. No Shopify store settings, products, stock, orders or customer records were modified. No credentials, customer contact details or financial account identifiers were saved in the collection. No public deployment was performed.

## Material limitations

- All current variant costs and all historical sales costs are unrecorded. Profit and margin remain unavailable; missing costs are not zero.
- Customer cohorts contain first-purchase/order-frequency groups, with partial status. A full month-by-month retention matrix was not collected.
- Three campaign reports are verified empty after separate parse-error/warning checks. Attribution windows were not exposed; unknown remains explicit. No causal marketing conclusion is made.
- The Admin Shopify Payments account endpoint is blocked by missing scope. Aggregate payments, fees and payout reports were collected through authorized ShopifyQL, plus four browser payout summaries. Browser schedule coverage is marked partial.
- Shopify's native notice marks a **September 21, 2026 session measurement change**. The dashboard warns when history spans it and withholds comparisons across the break.
- Native CSV export was attempted, but Chrome blocked the signed export-storage destination with `ERR_BLOCKED_BY_CLIENT`. No security bypass was attempted; preserved API responses supply the structured source instead.
- The connector hides its executed API version. Live introspection/execution and current official documentation are retained; documentation version is not presented as proof of execution version. The validation tool delegated validation to execution, and its receipt is preserved.

## Verification actually performed

- **48 tests passed in 11.78 seconds** in the final affected suite: Shopify repository/UI/backup, existing generic backup and navigation. Existing six YouTube backup regression tests also passed separately. No whole-project suite was run for this change. `pip check` passed.
- **166 independent checks passed** against both the staged and activated collection. They include exact readback of 92 assets and cell comparisons of 31 native tables / 5,658 native rows, Decimal accounting, identities, dates, pagination, current-day separation and missingness. Earlier 51 collection reconciliation checks overlap these and are not added as unique checks.
- Real registered staged-repository Streamlit AppTest inspected all six views and 46 report/table choices, source selection, CSV generation, current-day warnings, period visitors, missing costs and lineage. Live browser checks inspected all six views and representative controls/charts, sales-window reset, inventory filter/reset, empty campaign reporting, payment and missing-profit states, and the global provenance entry. Browser error log was empty. Browser download files were not round-tripped; repository bytes and CSV generation were checked separately.
- **All 95 preflight-enumerated library files (3,633,455,140 bytes) remained unchanged after import.** Two YouTube directories were inaccessible during that preflight and are outside the hash comparison. After browser checks, both existing registries and `stats.sqlite3` still matched their preflight hashes; the activated Shopify database and source identity also matched. Active analysis remains **meta-story-backfill-20261024**. The existing October 20 reporting history and its original baseline-membership qualification are preserved.
- A focused **staged Shopify-only portable backup** was relocated and read back: all 92 assets and 46 tables matched. The backup implementation now includes Shopify in future complete-library backups. This run did not create or restore a full backup of the existing 3.6 GB library.

Receipts and rerunnable verifiers are in `data/reconciliation/shopify_20261025/`, including `independent_acceptance.json`, `live_acceptance.json`, `live_replay.json`, `library_preservation_after.json`, `runtime_state.json`, `browser_verification.json` and `portable_backup_acceptance.json`. UI smoke receipts are in `test-results/shopify-ui-20261025-final/`.

New implementation: `stats_app/shopify_repository.py`, `stats_app/shopify_ui.py`; integration edits: `stats_app/ui.py`, `stats_app/navigation.py`, `stats_app/backup.py`. Tests are `tests/test_shopify_repository.py`, `tests/test_shopify_ui.py`, `tests/test_shopify_backup.py`, plus the extended navigation regression. Root UI/navigation/backup/README originals are retained beside the reconciliation receipts. Other recent Apple Music, TikTok and Meta work was preserved. Registered Spotify, Meta and YouTube sources supplied the existing dashboard; a collected Apple Music package existed on disk outside the active analysis, TikTok had preparation work, and Linktree had no populated source collection at initial inspection. Shopify was not merged into those sources or earlier analytical results.
