# Apple Music live import — October 25, 2026

The collected [REDACTED] Apple Music package is imported into the existing Windows local library at `C:\Users\jlewi\AppData\Local\TheStats\stats.sqlite3`. The actual local launcher was started on `http://127.0.0.1:8501`; the browser was left on the Apple Music daily Plays view in **More → Snapshot explorer**.

## Saved snapshots

| Snapshot label | Observations | Grain and status |
| --- | ---: | --- |
| `apple-music-20261025-daily` | 25,738 | Daily Plays and daily unique listeners; all observed |
| `apple-music-20261025-aggregate` | 950 | 813 period and 137 monthly facts; 731 observed and 219 missing |

Both are new non-baseline snapshots, sealed after verification. All 26 daily batches were imported into one daily snapshot; the aggregate master was imported into the separate aggregate snapshot. The equivalent daily master, derived comparisons and supporting provenance tables were not added as extra observations. Source evidence remains in the unchanged [collection package](../data/collection/apple-music-20261025/README.md).

The 12,288 previously stored observations remain unchanged, bringing the local writable database to 38,976 observations. Original snapshot metadata, baseline flags, source bytes, imports and provenance were checked using logical row fingerprints. Sixteen protected registry and registered database files retained their hashes. The active analysis pointer and historical baseline designation were not changed. The original October 20 baseline's existing unverified status remains visible.

## Verification

The import first ran against a consistent workspace copy of the local library. The same verified operation then ran against the live database using the project's actual parser, validator and repository. The [live receipt](../outputs/apple_music_import_20261025_live/import_receipt.json) records the inputs, hashes, before/after fingerprints, import results, calculations and replay results.

- All 27 actual input files replayed with **0 new observations** and **26,688 duplicate rows**. All five database tables were unchanged by replay, including imports and provenance.
- Exact replay also passed after both snapshots were sealed.
- Equal-overlap and mixed new/conflicting-row probes ran through the real repository's disposable preview. Equal overlap added no fact; conflicting input was rejected atomically. No synthetic probe data was committed to the live library.
- SQLite integrity was `ok`. All inventoried collection files remained unchanged.
- The necessary Apple Music platform-selector repair and its UI regression test passed the targeted app, calculations and storage suite: **75 tests passed**.

The actual browser displayed these source-backed results:

| View | Verified result |
| --- | --- |
| Daily artist Plays, September 26–October 23 | 507; 28 observed days; latest endpoint value 23 |
| Daily artist Plays, May 1, 2023–October 23, 2026 | 16,495; 1,272 observed days |
| Daily unique listeners, latest 28 days | Period aggregation unavailable; 28 observed records; latest daily value 12 |
| Aggregate artist Plays, September 26–October 23 | 507; one source record |
| Aggregate Average Daily Listeners, same period | 11; one source record |
| Monthly artist Plays, October 1–23 | 430; retained separately from the daily sum of 428 |

The live calculation receipt additionally checks latest-7 Plays 154, latest-90 Plays 1,828, 2026 YTD Plays 8,147, and latest-28 source Shazams 3, Radio Spins 1 and Purchases 0. These extra values were checked through the dashboard's calculation functions, not individually clicked in the browser.

Browser evidence and screenshots are in [the live import output directory](../outputs/apple_music_import_20261025_live/). An optional upload-based duplicate-preview attempt was unavailable because the browser extension did not allow local file-URL uploads. No extension setting was changed. Duplicate protection was verified by replaying every actual source against the live importer and checking all database tables.

## Viewing the data

Open **More → Snapshot explorer**, select either Apple snapshot, then choose **Apple Music → All Songs · artist** and the desired metric. The daily snapshot supports Latest 7/28/90 days, All available and Custom windows. For aggregate Plays, choose **Period · Period count · Entity scope: artist · count**, then the exact source period. Monthly, geography, demographics, station and listener scopes remain distinct. Do not sum daily unique listeners into period-unique people or combine the overlapping daily and aggregate snapshots.

The source collection's known rounding, filename-date, geography, demographic and monthly/daily discrepancies remain documented in its [validation notes](../data/collection/apple-music-20261025/VALIDATION.md). Importing did not resolve or silently adjust them.

## Backup and repeat behavior

The consistent pre-import backup is [pre_import_library.sqlite3](../outputs/apple_music_import_20261025_live/pre_import_library.sqlite3), with its SHA-256 in the live receipt. A separate rehearsal database is retained alongside it. Do not replace the running database with these files; use a new data directory for any future restore.

[import_apple_music_collection.py](../scripts/import_apple_music_collection.py) defaults to backup/rehearsal only; `--execute` is the explicit live step. It refuses existing target labels, so rerunning the whole collection command cannot create an accidental second import. The repository itself accepts exact replays of the existing source interpretation without adding rows. Later changed captures belong in a new dated package and new snapshot labels.
