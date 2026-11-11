# TikTok Studio in The Stats

Open **Explore → TikTok** and select the dated Studio collection for **@funnyguycrawl**. It is independent of the saved analysis selector. Existing Spotify/Meta analyses and baseline designations retain their original inputs.

The account page charts video views, profile views, likes and shares over selected reporting days. Owned posts provides caption/ID search, exact-count sorting and post detail with watch/completion metrics, viewers, demographic/discovery breakdowns and capture provenance. Audience reports keep daily viewers, follower stocks, net changes, hourly activity, period summaries and native snapshots separate. Rankings and recent comments retain their original scope. Coverage and sources expose date decisions, limitations and hash-verified original downloads.

## Date resolution

The preferred source-labeled account window is **October 26, 2025–October 25, 2026**. The initial annual calendars contain 365 distinct contiguous labels. All 197 rows from seven shorter first-capture exports agree with the annual tails. The initial follower changes match adjacent follower stocks for all 364 checkable days.

Later exports repeat the same underlying value sequences while changing date labels: 126 Overview labels and 239 Viewer labels differ, with duplicated November 2 and omitted March 8. Later follower changes shift one row, and later hourly activity repeats all 168 values with dates advanced one day. The custom October 26 control exports the initial October 25 row again.

The import therefore selects the initial sources and retains later files as excluded evidence. It does not rewrite dates, merge overlapping exports, or add an October 26 observation. The reporting timezone and absolute event-day boundary remain unknown. Saved calendar controls also differ at the earliest boundary, so this is **source precedence**, not a certified platform calendar correction.

Detailed independent checks and the executable notebook are in [the date resolution report](../outputs/tiktok_integration_20261027/date_audit/DATE_RESOLUTION.md). `source_dispositions.csv` records a decision and hashes for each of the 33 native CSV members across 18 ZIP archives.

## Metric interpretation

- Daily account activity is distinct from lifetime/stated post snapshots. Never assign a post's current lifetime views to its publication date.
- Daily comments include 14 negative values. Preserve the signed source series; it is excluded from default activity KPIs because its interpretation as new comment events is unverified.
- The final total-viewer cell is literally `undefined`, retained as missing. Explicit new/returning viewer zeros remain zero. Daily unique viewers are not additive into a period-unique audience.
- Follower stock and daily net change are separate measures. The native +1,108 daily-change sum includes the first day's +1 change from a preceding unobserved stock; last-minus-first stock is +1,107.
- Rounded displays such as `60K` and percentage bounds such as `<1%` keep their original precision. Exact-only sorting does not rank every post's true count.
- The 615 posts have 1,845 distinct analytics panels; the 1,846 receipts include one preserved superseded capture. Use readiness flags when inspecting receipts.
- Viewer affinity lists describe third-party content/accounts, not the user's owned posts. Viewer and follower demographics describe different populations.
- Recent comment observations include repeated captures and have no native unique comment IDs. A row fingerprint is not proof of a unique comment. Raw expanded-reply evidence remains available.
- Raw interactive chart-point series, all-time comments, mobile-only LIVE details and verified recording mappings are not supplied by this collection. Partial public sound labels do not establish recording identity.

**TikTok for Artists remains pending by user instruction.** No Business account is created or linked by the integration.

## Reproduce, validate and import

Use the project's Windows virtual environment. All commands require a new output directory when creating a package or receipt; immutable history must not be overwritten.

```powershell
.\.venv\Scripts\python.exe outputs\tiktok_integration_20261027\date_audit\audit_dates.py
.\.venv\Scripts\python.exe scripts\build_tiktok_studio_collection.py --output outputs\a-new-tiktok-package
.\.venv\Scripts\python.exe scripts\import_tiktok_studio.py --package-dir outputs\a-new-tiktok-package
```

The builder verifies the sealed acquisition manifest and all 4,252 original manifest entries before copying bytes. Original workspace-relative source references remain valid within the new package. Derived tables have separate definitions and row keys; all native CSV members are retained unmerged.

Actual registration uses an explicit durable library path, avoiding shell-specific `LOCALAPPDATA` redirection:

```powershell
.\.venv\Scripts\python.exe scripts\activate_tiktok_studio_collection.py --package-dir outputs\tiktok_integration_20261027\package-v2 --data-dir C:\Users\jlewi\AppData\Local\TheStats --output outputs\a-new-tiktok-activation-receipt
```

Activation validates the package, makes a consistent SQLite backup, imports and replays the same package, checks every declared table, and verifies existing library file hashes are unchanged. Identical replays add no records; conflicting data under an existing collection key are rejected. The new `tiktok_collections.json` registry and `collections/tiktok-20261027-studio/` directory do not alter the canonical observation database or saved analysis pointers. Complete-library backups include the TikTok registry and all retained assets.

The sealed acquisition's historical `integration_ready: false` and preparation metadata remain unchanged as acquisition-time evidence. The current registered package and activation receipt describe the later integration status.

## Verification

See the dated [integration handoff](../handoff/TIKTOK_STUDIO_INTEGRATION_20261027.md) for the actual activated package, replay result, preservation checks, test results and browser verification. A documented command by itself does not claim successful execution.
