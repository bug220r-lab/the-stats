# Shopify merchandise collection

Shopify is an independent immutable collection in the existing Windows Streamlit dashboard. It does not add merchandise rows to Spotify, social, YouTube, the upload database, or an earlier analysis version. The October 20 reporting endpoint and baseline qualification remain unchanged.

Open **Shopify** in the sidebar. Sales and traffic offer the last 7, 28 and 90 completed store days, year to date, and all available completed days. Windows are anchored to the collection timestamp in the verified store timezone, rather than the computer's current date. A required missing date or unavailable metric withholds the affected total and comparison. The current day is excluded. Distinct daily visitors are never summed into a period audience.

Other views retain sales and order details, the catalog and current inventory, traffic breakdowns, marketing and aggregate customer evidence, fulfillment and costs, and coverage/source downloads. The exact availability of each report is in the collection manifest and **Coverage & sources**. An empty selection, an empty report and a denied report have different meanings.

## Import a collected package

The October 25 package is `data/collection/shopify-20261025/`. It contains native connector responses, exact validated operations and documentation receipts, browser observation receipts, normalized CSVs, and `manifest.json`. Source contact details and payment-account identifiers are excluded. Historical line items retain titles even when a deleted product no longer has a current catalog ID.

Use the project's Python environment from PowerShell:

```powershell
.\.venv\Scripts\python.exe -m stats_app.shopify_repository --package-dir .\data\collection\shopify-20261025 --data-dir "$env:LOCALAPPDATA\TheStats"
```

For a review import, replace the destination with a new workspace staging directory. Exact replay verifies the registered bytes and reports `idempotent: true`. A changed package cannot replace an existing collection key. A new collection belongs in a new dated package and key.

The importer validates status, identity, timestamps, bounds, CSV shape, literal headers, declared keys, source references and hashes. It writes a dedicated `collections/<key>/shopify.sqlite3`, an exact `package/` copy and `shopify_collections.json`. Registered reads verify the database and evidence hashes. Raw strings preserve negative money, source zeros and blank values. Original order timestamps remain retained, and reporting dates retain Shopify's store calendar.

## Interpretation

- Native sales reports control sales accounting. Payment charges, payment refunds, processing fees and payout timing are separate measures. An order's original total is not its net sales after later returns.
- Current inventory is a dated snapshot. Any historical inventory report retains its own source date grain and available coverage; it is not reconstructed from today's stock.
- All-channel orders differ from online-store checkout sessions. The derived completed-checkout session rate uses completed-checkout sessions divided by online-store sessions. A zero or unavailable denominator produces unavailable rate.
- Shopify warns that sessions and related metrics may change from September 21, 2026. Traffic history crossing that boundary requires care; no unqualified comparison across it should be interpreted as a pure behavior change.
- Native AOV and unique-customer/visitor measures retain their definitions. No causal marketing conclusion follows from attribution rows. Missing product costs or fees do not imply zero expense or establish profit.
- Installed channels establish configuration, while reported order and sales channel fields establish actual use. An empty publication API response does not establish that the store has no channels.

Filtered CSV downloads neutralize spreadsheet formula text. **Download unchanged retained source** returns the archived source bytes. Source files and normalized rows remain separate so transformations can be inspected.

## Backups and operation

The normal launcher remains `launch_windows.bat` and binds only to `127.0.0.1`. A source reload clears local caches and does not collect new Shopify data. No Shopify credentials are required to read a saved local collection.

The complete library backup now includes registered Shopify collections and their registry, alongside existing archives, analyses and YouTube collections:

```powershell
.\.venv\Scripts\python.exe -m stats_app.backup --bundle-dir .\backups\library-with-shopify-NEW-DATE
.\.venv\Scripts\python.exe -m stats_app.backup --verify-bundle .\backups\library-with-shopify-NEW-DATE
```

Use a new destination. Restore into a new directory; preserve the active library. Collection-specific verification and actual checks performed are recorded in the dated handoff.
