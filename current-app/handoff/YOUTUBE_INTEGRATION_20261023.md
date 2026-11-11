# YouTube integration handoff — October 23, 2026

The verified package is installed as **youtube-20261023** in the existing Streamlit application. Use **Explore → YouTube collection**. Channel/video/discovery tables, retention, manual UI summaries, song relationships, coverage and provenance remain separate from saved analyses. Existing Sources & provenance, Coverage & cross-reference and Data quality views also expose the collection.

## Durable storage and import

Configured data directory: `C:\Users\jlewi\AppData\Local\TheStats`, the existing default outside OneDrive. The separate `youtube_collections.json` registry points to `collections/youtube-20261023/youtube.sqlite3`. The unchanged `The_Stats_YouTube_Collection_2026-10-23.zip` is retained in that collection directory. Runtime never depends on Temp.

- ZIP SHA-256: `33da7c508f443ebc883a6c2f86425d1284917526ea5ba1cbbe7f1e0ad08ba6ef`.
- Installed database SHA-256: `42ae8a8e8905048299e6d5d198de5b9fbf532ff64aaa9ed698baaf9f1e27b139`.

The importer copies the source into durable private staging before parsing, validates package/original hashes and canonical keys, creates an immutable database and atomically registers it. Repeating import passed with `idempotent: true`; no rows were added or replaced. Conflicting contents, unsafe paths and invalid registries are rejected. All 471 package assets are unchanged. The 24 parsed tables contain 81,245 heterogeneous CSV records, including evidence and wide representations. This is a storage count, not a statistical sample size. Raw `observations.csv` and the overlapping aggregate canonical file remain evidence assets, not additional parsed fact tables.

## Preservation and concurrent work

All **seven databases present at preflight** match their original hashes. Of 78 prior durable files, 77 remain unchanged. Another ongoing workflow changed `archive_registry.json` to add/activate `instagram-story-owner-20261023`; this importer never writes that registry. Comparison against the exact preflight registry in an earlier backup verified that all five earlier analysis registrations and all archive registrations remain identical. The owner version is a sixth analysis version. That concurrent change and its current handoff were preserved.

Existing Spotify baseline metadata and its unverified classification remain intact. No cross-platform analysis, statistical conclusion, conversion attribution or deployment was performed. The YouTube source collection is independent of the analysis-version selector.

## Validation performed

- Expected ZIP hash, 470 manifest entries, 67 native ZIP hashes and 348 exact native CSV members verified.
- Independent direct read-only SQLite audit compared all 471 assets, 24 parsed tables and 81,245 stored CSV row arrays/stable keys with their source bytes.
- 27 unique video IDs: 19 regular videos and eight Shorts. Exactly 9,855 annual video-days and 19,710 separate views/engaged-view metric pairs verified.
- Core canonical rows preserve `zero` (36,945), `observed` (6,833) and `unavailable` (1,699). Retention preserves `reported` (20,110) and `unavailable` (139). Raw cells, lineage and normalized unavailable overrides remain intact.
- 2,700 main retention points: exactly bins 0–99 per video. Segment/member/metric distinctions, negative comparisons, values above 100 and separate manual summaries verified.
- Full-suite invocation: **267 passed** in 371.87 seconds. Final targeted YouTube repository/UI/backup and existing backup checks: **37 passed** in 108.03 seconds, with one non-failing pytest cache-permission warning. These runs overlap in existing backup coverage; do not add them as unique tests. Separate YouTube/existing UI regressions: **23 passed**. `pip check`: no broken requirements.
- Actual `launch_windows.bat --no-browser` smoke on loopback port 8511: browser readback verified the channel, Pacific dates, historical-retrieval qualification, 27-video inventory and a native 100-point retention chart with a 0–99 elapsed-video axis. Screenshots and accessibility evidence are retained. The temporary tab/server were closed and port 8511 has no listener. Other application instances were left in place.
- Complete private backup: `backups/library-youtube-2026-10-23/`, verified with **86 files, nine databases, six analysis versions and one YouTube collection**. All six analysis repositories and all 24 YouTube tables/stable keys loaded from that backup. No live-library restore/replacement occurred.

Receipts: `data/youtube_integration_20261023/` (`preflight.json`, `source_audit.json`, `installed_audit.json`, `live_import.json`, `live_replay.json`, `backup_verification.json`, `runtime_verification.json`). Test XML, screenshots and retention accessibility readback: `test-results/youtube-integration-20261023/`. These remain ignored private evidence.

## Run and repeat import

From the project folder:

```powershell
.\launch_windows.bat
```

For an app instance predating these code changes, stop it normally and relaunch when its current work is finished. Choose **YouTube collection** independently of Analysis version.

To repeat import from the durable source on this PC:

```powershell
.\.venv\Scripts\python.exe -m stats_app.youtube_repository --zip-path "$env:LOCALAPPDATA\TheStats\collections\youtube-20261023\The_Stats_YouTube_Collection_2026-10-23.zip"
```

The CLI uses `STATS_DATA_DIR` when configured and rejects an active destination under OneDrive. See [YouTube instructions](../docs/YOUTUBE.md) and [complete-library backups](../docs/ARCHIVE_BACKUP.md). Generic CSV imports retain their existing workflow.

## Remaining source limitations

The annual multi-metric table has 243 reported dates. Full daily supplemental watch-time, average-duration, subscribers-gained and subscribers-lost exports were blocked by Google passkey verification; these metrics retain partial data. Missing days were not zero-filled, and authentication was not attempted during integration.

Short-window demographic exports are suppressed/header-only. The four blocked demographic reports in the core index are distinct from the four passkey-blocked supplemental exports, which have no files and are recorded at task-status level. Some New viewers raw zeros are normalized unavailable. Livestream-scoped not-applicable rows do not establish observed zero activity. Retention includes 100 header-only native members and 139 unavailable numeric cells. Artist-wide reporting remains unexposed; unresolved mappings/Spotify recording IDs remain unresolved.

Reporting dates remain inclusive `America/Los_Angeles` calendar days; retrieval timestamps are download-modification proxies. Historical October 20 reporting is newly retrieved history, never an original October 20 snapshot. Watch time remains hours and parsed average duration remains seconds. Nonadditive metrics are not summed, aggregates are not forced to reconcile, and documented view-definition dates remain available.

## Files changed

- Added `stats_app/youtube_repository.py`: immutable import, validation, registry and source-compatible read API.
- Added `stats_app/youtube_ui.py`; extended `stats_app/ui.py` navigation and source/coverage/quality entry points.
- Updated `stats_app/backup.py` to include the separate collection and verify registered hashes. Explicit SQLite connection closure fixes a Windows handle leak that prevented immediate backup relocation.
- Added `tests/test_youtube_repository.py`, `tests/test_youtube_app.py`, `tests/test_youtube_backup.py`.
- Updated `README.md`, `docs/ARCHIVE_BACKUP.md`; added `docs/YOUTUBE.md`, this handoff and a link in the current handoff.

This workspace is not a Git repository. No commit, deployment or private export inclusion in source control occurred. Existing ignore rules cover private data, exports, databases, ZIPs, backups and test evidence.
