# TikTok collection readiness — October 26, 2026

The Stats now provides **Explore → TikTok** (`/tiktok`) for collection preparation and future integration. The user supplied https://www.tiktok.com/@funnyguycrawl. The workspace records this as a supplied target, not verified account ownership or analytics access.

## Delivered

- `data/collection/tiktok-20261026/`: a fresh collection manifest, seven-step resumable queue, header-only post/campaign and equal-age snapshot worksheets, copied source-specific mapping/metadata contracts, and a sound/recording crosswalk. Original sources, evidence and stages have separate folders.
- `stats_app/tiktok_collection.py` and `scripts/manage_tiktok_collection.py`: new-folder initialization and read-only assessment, SHA-256 source inventory, explicit outcomes, contained evidence references, no-overwrite protection, and refusal of AppData/live-library destinations. Relative library paths follow the application's project-root semantics. Console JSON works under Windows legacy encodings; saved JSON remains UTF-8.
- `stats_app/tiktok_ui.py`: Collect, Review & stage, and Analysis plan tabs, source-status visibility and downloadable worksheets/guide. This page is independent of saved-analysis selection and has no activation action.
- Existing navigation and README link to the new destination. The historical Social view no longer describes all current collection work as deferred; it still reports that its saved package contains no TikTok analytics.
- `docs/TIKTOK_COLLECTION_20261026.md`: source-backed collection runbook, metric priorities, three source families, reporting/snapshot boundaries, capture cadence, and cross-platform interpretation limits.

The existing `stats_app/tiktok.py` inspector/mapper and `scripts/prepare_tiktok.py` staging tool are unchanged. No dependency, credential, API connection, account setting, scheduled task, live-library registration or historical analysis was added or changed.

## Verified state

The actual collection assessment is `preparation_only`, with seven `not_collected` queue items, zero raw files, zero evidence files, no assessment issues, and `integration_ready: false`. Empty worksheets and preparation receipts do not establish performance observations. Readiness receipts are saved outside source evidence.

- **102 tests passed in 16.89 seconds** across collection safety/CLI, existing TikTok parsing/staging, new UI, native navigation, Social, source integration and application/import regressions. Receipt: `outputs/tiktok_readiness_20261026/final-tests.xml`.
- Windows `launch_windows.bat --no-browser --port 8514` started successfully using an isolated smoke-test library. `/_stcore/health` returned `ok`. The real browser rendered the supplied profile, pending queue and all three tabs. The temporary browser tab and server were closed afterward; the production library was not used for this smoke test.
- **53 tracked existing library SQLite/JSON files retained their original SHA-256**, with no unreadable files and no new library SQLite/JSON files. Existing TikTok parser/CLI hashes also remain unchanged. Final source hashes are recorded in `preservation_after.json`.
- Independent review identified and helped resolve the relative-library path guard issue. Unicode console output was also repaired and regression-tested.

Verification artifacts are under `outputs/tiktok_readiness_20261026/`: `preservation_before.json`, `preservation_after.json`, `readiness-initial.json`, `readiness-final.json`, `final-tests.xml`, `tiktok-collect.png`, and browser text observations. Tests use synthetic fixtures and do not validate a genuine TikTok export. These are targeted regressions, not a claim that the entire repository suite was executed.

## Next collection

Restart The Stats normally and open **Explore → TikTok**. Start with the native account identity/access screen and one untouched account analytics export with evidence of the selected dates, metric definitions, filters and reporting clock. Then collect owned-post inventory/performance and, if available, TikTok for Artists song activity separately. Preserve unverified clocks and missing metrics explicitly.

Inspect and stage files with the existing mapping workflow. Reconcile matching native totals and review post/sound/recording identity before designing performance views and registering a separate immutable TikTok collection. Account activity, cumulative post snapshots, community song usage, clicks, music listening and sales remain distinct. Cross-platform relationships are descriptive until supported by an appropriate attribution design.

No authenticated TikTok screen, actual export layout, reporting timezone/history, native performance metric, or account-specific Artist eligibility was verified in this preparation task. There is no automatic collector or import/activation path in the new readiness tool.
