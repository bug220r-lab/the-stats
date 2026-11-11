# YouTube annual daily supplement — October 23, 2026

The requested continuation is complete: Studio access was available in the existing signed-in session, all four native daily exports were collected, and a separate dated supplement was installed and verified. No passkey prompt appeared, and no credential or authentication setting was changed. The original source package and saved analysis versions remain unchanged.

## Collected and installed

Collection `youtube-daily-20261023` belongs to `[REDACTED] TV`, `@redactedbandoh`, channel `UCkSoRiC9Pz9hEbJOOTYaq_w`. Scope is unfiltered channel-owned, all formats, daily. Reporting dates are **2025-10-22 through 2026-10-21 inclusive Pacific**. Retrieval occurred October 23 UTC; download-file LastWriteTimeUtc is explicitly labeled as a retrieval proxy, separate from UI capture times. Native filenames end October 22 because their endpoint is exclusive.

| Metric | Native dates | Numeric values | Explicit zeros | Unavailable values |
| --- | ---: | ---: | ---: | ---: |
| Watch time, hours | 365 | 365 | 173 | 0 |
| Average view duration, seconds | 365 | 353 | 164 | 12 |
| Subscribers gained | 365 | 365 | 315 | 0 |
| Subscribers lost | 365 | 365 | 357 | 0 |

There are **1,460 metric/day records**, 36 retained assets, six normalized tables and 1,488 heterogeneous CSV records. The latter is a storage count, not a sample size. Raw AVD `h:mm:ss` strings are retained beside parsed seconds. The 12 native blanks stay unavailable. No missing value is converted to zero, no missing calendar date is fabricated, and durations are not summed or averaged across days.

Each metric fills the 122 calendar dates absent from the original 243-date multi-metric table using actual native source rows. All 791 numeric observations shared with that earlier table agree. Daily watch-time rounding totals 59.8709 hours versus the native period-table 59.8703 hours; the 0.0006-hour difference is preserved without forced reconciliation. Selected-chart `Totals.csv` provides each complete daily series. Native `Table data.csv` is preserved as evidence only.

Frozen collection input: `data/collection/youtube-daily-20261023/`. It contains the four unchanged native ZIPs, collection manifest, download receipts, screenshots, accessibility captures and source URLs. Do not edit this tree after packaging; future evidence belongs in a new dated supplement.

Durable installation: `%LOCALAPPDATA%\TheStats\collections\youtube-daily-20261023\` with `youtube.sqlite3`, `supplement.zip`, and `youtube_daily_supplement_import.json`. The independent `youtube_collections.json` registry appends the new key. Runtime does not depend on Downloads or the staging copy.

- Supplement ZIP SHA-256: `e82de7ecea13b0f3ceca4468d702d7830003d6dc55171962803f2a8873a941a8`.
- Installed database SHA-256: `23e73b79e9f7789fe8ee6176ef7080b1bac8d2530322c6f3116adbb48956e8d8`.
- Pinned parent package SHA-256: `33da7c508f443ebc883a6c2f86425d1284917526ea5ba1cbbe7f1e0ad08ba6ef`.

## Preservation and verification

Independent audit verified all 1,460 source raw cells, values, statuses and source-row references; all 36 retained assets; and every normalized row/stable key. All nine pre-existing databases are byte-identical. Of 86 pre-existing library files, 85 are byte-identical; the only changed file is the YouTube registry, with its parent registration preserved and the supplement appended. Three new files bring the library to 89 files and ten databases. `archive_registry.json`, the six analysis versions, and active `instagram-story-owner-20261023` remain unchanged. Exact import replay left all 89 library files unchanged.

Verified full-library backup: `backups/library-youtube-daily-2026-10-23/`, **89 files, ten databases, six analysis versions, two YouTube collections**. Both YouTube collections were loaded from the backup; all 30 tables, stable keys and original ZIP bytes matched. Every backed-up database passed SQLite quick_check. The source-specific tests also exercise relocation into a different directory. No restore replaced the live library.

Actual launcher check used `.\launch_windows.bat --no-browser --port 8511`, bound to `127.0.0.1`. Live browser rendering showed full watch-time coverage and AVD **365 / 365 reported dates, 353 / 365 numeric values, zero omitted dates**. Parent navigation returned to the original 27-video inventory without changing analysis selection. The temporary tab and test server were closed; the existing port-8501 dashboard was not restarted.

Full suite: **359 passed in 370.15 seconds**. Focused checks also passed: 15 supplement repository/import/backup tests, six synthetic UI tests, 14 existing UI regressions, and an actual-source AppTest. A later 31-test final check had 30 passes and one warning-text assertion failure after the historical blocker wording was clarified. Restoring the expected “partial data” phrase while retaining the historical qualification resolved it; the affected test passed in 17.71 seconds. No failures remain. These runs overlap and must not be added as unique test totals. Results are retained in `data/youtube_daily_supplement_20261023/test_results.json`.

Receipts are in `data/youtube_daily_supplement_20261023/`: `preflight.json`, `source_gap_audit.json`, `source_validation.json`, `audit_notes.md`, `actual_ui_validation.json`, `live_import.json`, `live_replay.json`, `post_import_preservation.json`, `backup_verification.json`, and `runtime_verification.json`. Screenshots and live accessibility readbacks are under `test-results/youtube-daily-supplement-20261023/`.

## Use and implementation

Launch normally with `launch_windows.bat`. Choose **YouTube collection** in Explore and select **YouTube daily supplement — retrieved 2026-10-23** in the sidebar. Daily metrics, coverage, source downloads and parent navigation are available. The supplement overlaps the parent reporting window; never add the two collections together. Original package limitations remain historical facts; AVD's 12 unavailable values are the remaining numeric gap in these four series.

New modules: `stats_app/youtube_daily_supplement.py`, `stats_app/youtube_daily_ui.py`. Shared changes: dedicated registry/loader dispatch in `youtube_repository.py`, dynamic package filenames in `backup.py`, supplement UI dispatch and historical blocker wording in `youtube_ui.py`, independent collection selection in `ui.py`. New tests: `tests/test_youtube_daily_supplement.py`, `tests/test_youtube_daily_app.py`. Documentation: `docs/YOUTUBE.md` and this handoff.

This work adds source evidence only. No cross-platform analysis, Story song assignment, source-control upload, Drive publication or deployment was performed. The six October Story mappings remain deferred; original Spotify October 20 baseline membership remains unverified.
