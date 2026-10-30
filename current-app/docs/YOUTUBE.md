# YouTube collection import

The October 23, 2026 collection belongs to **[REDACTED] TV**, **@redactedbandoh**, channel ID `UCkSoRiC9Pz9hEbJOOTYaq_w`. The Stats™️ is the project name. Standard-channel reporting was available; artist-wide Official Artist Channel, Total Reach and Other Channels reporting was not exposed. Core scope is `channel_owned`; retention has its own selected-video scope.

## Import and storage

Run from the project directory using its existing environment:

```powershell
.\.venv\Scripts\python.exe -m stats_app.youtube_repository --zip-path "C:\path\to\The_Stats_YouTube_Collection_2026-10-23.zip"
.\launch_windows.bat
```

The importer uses the same `STATS_DATA_DIR` configuration as the app, normally `%LOCALAPPDATA%\TheStats`, outside OneDrive. It copies the package into a dedicated private `collections/youtube-20261023/` directory and stores exact source bytes plus parsed canonical tables in `youtube.sqlite3`. Runtime reads use this durable store, with no dependency on the download's temporary location. The original ZIP is unchanged. Expected SHA-256:

```text
33da7c508f443ebc883a6c2f86425d1284917526ea5ba1cbbe7f1e0ad08ba6ef
```

The collection has a separate `youtube_collections.json` registry. Repeating the same import is idempotent; conflicting source content is rejected. Existing SQLite databases, `archive_registry.json`, analysis versions and active analysis selection remain separate. No statistical outputs are recomputed. Source exports, databases, evidence receipts and backups are private and excluded from source control.

Use **YouTube collection** to inspect canonical source data, retention, song relationships, coverage and provenance. YouTube evidence is also available from the existing source/coverage views. Collection selection is independent of **Analysis version**. The importer is dedicated to this verified collection format; do not import raw `observations.csv` through the generic uploader or concatenate overlapping source tables.

## Reporting and interpretation

| Report | Inclusive Pacific dates |
| --- | --- |
| Current annual | 2025-10-22–2026-10-21 |
| Historical comparison | 2025-10-21–2026-10-20 |
| Lifetime channel | 2024-01-25–2026-10-21 |
| Audience 28 days | 2026-09-24–2026-10-21 |
| Audience 90 days | 2026-07-24–2026-10-21 |

Dates retain their `America/Los_Angeles` calendar-day meaning. Native export filename end dates are exclusive; normalized reporting bounds are inclusive. Retrieval occurred October 23 and uses download-file modification times as a proxy, not a known export-click time. Historical October 20 reports are newly retrieved historical data. Original Spotify October 20 baseline membership remains unverified.

Tables preserve IDs, period, snapshot class, reporting scope, content format, filters, metric, dimensions, units, raw values, value statuses and source references. Channel source aggregates can differ from attributed videos/dimensions. The app preserves those differences. Views and engaged views remain distinct; watch time is hours and parsed average view duration is seconds. Unique/returning viewers, durations, percentage viewed and CTR must not be summed. Explicit zero, unavailable, missing, suppressed and not applicable remain distinct where reported.

There are 27 videos: 19 regular videos and eight Shorts, with 9,855 annual video-days. A live-performance upload is not automatically a livestream. Song-title evidence does not prove identical recording equivalence; unverified Spotify IDs and unresolved mappings remain unresolved.

Retention has 2,700 main curve points: bins 0–99 for every video. The axis is elapsed-video percentage, not calendar dates. Segment, member and metric keys remain separate; curves are not summed and no 100% endpoint is added. Absolute retention and average percentage viewed can exceed 100%; relative comparison values can be negative. Manual UI summaries are labeled separately from native curve exports.

## Annual daily supplement

The four full daily exports were collected from the existing signed-in Studio session on October 23, 2026; no passkey prompt appeared. They are retained as the separate `youtube-daily-20261023` collection, linked to the original package by its SHA-256. The original collection and its historical partial-coverage statuses are unchanged.

Each selected metric's native `Totals.csv` supplies all 365 dates, October 22, 2025 through October 21, 2026 inclusive Pacific. Watch time, subscribers gained and subscribers lost have 365 numeric values each. Average view duration has 353 numeric values and 12 native blanks. Source-reported zeros stay explicit; blanks are not filled. Native `Table data.csv` members are retained as evidence and are not used to manufacture the complete series. Daily watch-time rounding may differ from the source period total; no equality is forced. Average durations are not summed or averaged across days.

Select **YouTube collection → YouTube daily supplement — retrieved 2026-10-23** to inspect daily metrics, coverage and sources. Collection selection is independent of saved analysis selection. Do not add overlapping base and supplement records together.

```powershell
.\.venv\Scripts\python.exe -m stats_app.youtube_daily_supplement --source-root "data\collection\youtube-daily-20261023" --data-dir "$env:LOCALAPPDATA\TheStats"
```

The importer requires the registered original collection, verifies its database and ZIP hashes, and atomically appends the supplement registration. Identical replay is read-only; changed source content under the same key is rejected. Evidence, original native ZIPs, exact extracted bytes, normalized rows and package hashes remain together in durable storage and full-library backups. See [supplement acceptance and handoff](../handoff/YOUTUBE_DAILY_SUPPLEMENT_20261023.md).

## Remaining collection limits

- The original annual multi-metric date table has 243 reported dates. Its historical export blocker is recorded in the frozen package; the separate supplement above resolves full calendar coverage for the four requested metrics. Twelve average-duration source values remain unavailable.
- Short-window demographics are suppressed/header-only. Some New viewers CSV cells contain raw zero while Studio showed unavailable; the normalized unavailable status governs display.
- Retention includes 139 unavailable numeric cells and 100 header-only native members. No zero or specific suppression cause is inferred.
- Channel, video, dimension and overlapping period totals are distinct populations. Do not force reconciliation or infer YouTube-to-Spotify conversions.
- Preserve the Shorts definition change on March 31, 2025, the all-format rollout announcement from August 24, 2026 and the channel UI marker on August 27, 2026 as separate source facts.

Use each package's dictionaries, collection indexes, statuses, coverage and validation tables for its source-specific limitations. No cross-platform analysis or deployment is part of this integration.

## Validation and backup

The import validates package/member integrity, canonical keys, IDs, annual video-day coverage, separate views/engaged views and retention coverage. Tests exercise replay and invalid inputs, source preservation, UI bindings and portable backups. Current execution results and private evidence paths are recorded in `handoff/YOUTUBE_INTEGRATION_20261023.md`.

Use the existing [complete-library backup command](ARCHIVE_BACKUP.md) to include YouTube with all older archives and analysis versions. A local-database-only `--output` backup does not include this collection.

Source delivery: [complete package](https://drive.google.com/file/d/1_vRFRVCXJ2dONKFS39nHFMb_Tf02irRm/view), [project folder](https://drive.google.com/drive/folders/1SJDyZ545GHtloK0n296Z7GUcaw6fYVni), [collection index and validation workbook](https://docs.google.com/spreadsheets/d/1KU_Ky0r1MeoJe_QQ20VeuImO48GCRg722Sx7IuQLhrI/edit).
