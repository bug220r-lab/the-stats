# The Stats™️ — current Windows handoff

Saved October 23, 2026. Continue this workspace in place. Intended users: Lewis, Brandon and Samman. The active analysis is **meta-collection-20261023**. TikTok collection is excluded by the user. No hosting or new correlation/significance tests were performed.

This document supersedes [the preserved pre-Meta handoff](HANDOFF_before_meta_collection_20261023.md), which retains Spotify recovery history and earlier source/recovery references. Do not overwrite a working database with a recovery ZIP.

## Subsequent cross-reference analysis — October 23

The user's next request authorized a new exploratory Meta/Spotify analysis. Its [readout](../data/reconciliation/meta_spotify_crossref_20261023/READOUT.md), predeclared plan, scripts, all comparisons and independent validation receipts are saved separately. The 14-comparison extension adds repaired Instagram Follows to the original six predictors; no corrected-significant association was found (minimum BH q 0.449). Song/post and historical paid comparisons are descriptive and retain release/overlap/attribution caveats. All five database hashes remain unchanged. The active dashboard package and its earlier statistical outputs were not replaced. Statements below about no new tests refer to the preceding collection pass.

## Launch and shutdown

Double-click **launch_windows.bat** in the project folder. It resolves its own directory, uses the project `.venv`, binds only to **127.0.0.1**, and opens the default browser at **http://127.0.0.1:8501/**. Keep the console open; press **Ctrl+C** there to stop. Closing the browser does not stop the server. Run `setup_windows.bat` only for initial setup.

From PowerShell in the project folder:

```powershell
.\launch_windows.bat
```

`launch_windows.bat --no-browser` starts the same server without opening a tab. The actual launcher was restarted twice during final verification; persisted Meta data loaded successfully and the dashboard was ready on loopback. If the application already owns port 8501, use that page rather than launching another instance. See [README](../README.md) and [Windows troubleshooting](../docs/WINDOWS.md).

## Active storage and preservation

Default data root: `%LOCALAPPDATA%\TheStats`, configurable through `STATS_DATA_DIR`. The registry uses relative paths. SQLite is authoritative; browser storage and Streamlit session state are not the database.

| Relative database | Current state |
|---|---|
| `stats.sqlite3` | Existing local import database; unchanged from Meta preflight |
| `archives/handoff-20261022/data/stats.sqlite3` | Earlier archive snapshots, including Spotify snapshot 1 and social snapshot 2; unchanged |
| `analysis/cleaned-20261022/analysis.sqlite3` | Preserved earlier analysis; unchanged |
| `analysis/spotify-recovery-20261023/analysis.sqlite3` | Preserved Spotify recovery analysis; unchanged |
| `analysis/meta-collection-20261023/analysis.sqlite3` | New active immutable analysis; equals staged database |

There are **five databases and three selectable analysis versions**. All five passed SQLite quick checks; the four earlier database hashes equal preflight. Activation succeeded, and duplicate replay was idempotent. The registry's active pointer changed intentionally. The package has **1,565 files, 126 tables, 168,754 heterogeneous CSV records and 1,130 verified raw-file hashes**; these counts are not independent statistical samples.

The historical reporting endpoint remains **October 20, 2026**, but membership in the original October 20 baseline archive is **unverified**. Later collection/recovery is not baseline verification. Original source files, old snapshots, identities, periods and provenance remain preserved; new captures carry their own reporting windows and timestamps.

## What the Meta pass added

Full details and reproduction commands: [META_COLLECTION.md](../docs/META_COLLECTION.md). New package tables are under `social/meta_collection/`; raw collection evidence is under `raw/meta_collection/`.

| Dataset | Verified new evidence | Limits retained |
|---|---|---|
| Instagram Follows | **293/293 complete dates, Jan 1–Oct 20**, in `follows_daily_resolved.csv`: 166 inherited observations plus **127 individually verified zero-day repairs**. Five fresh native values match prior values. Total: 326 follows events. | Oct 21 remains a separate unresolved partial day. This is a new resolved view; inherited canonical rows are unchanged. Follows events are not net follower growth. |
| Instagram Stories | All **183 quarantined IDs** captured in current native detail views; **1,098 metric/status rows**. Views and interactions available for all 183, reach for 11, sticker taps for 18. | Link clicks and follows unavailable for all 183. Export Generate remained disabled. Fresh lifetime fields do not reconstruct the original malformed rows, which remain quarantined. Publication timezone is unknown. |
| Facebook recheck | **586/586** fresh daily interaction/visit values match prior evidence for Jan 1–Oct 20: 654 interactions and 1,082 visits. | Interactions: 653 Jan–May, 1 Jun–Oct; visits: 557 and 525. The break is reproduced but unexplained. Interaction scope includes ads. |
| Meta Ads | **3,161 ad-day rows**, **8 separate campaign rows**, four export-coverage records. | Native windows, level, IDs, currency, timezone and missing fields stay explicit. Never add campaign totals to ad totals. |
| Post/song/event map | 377 canonical posts: **60 posts with 62 explicit caption references**, **11 unresolved candidates**, **306 unknowns**. Two posts mention multiple songs. | No explicit Spotify track links. Caption references do not prove audio use/exposure/conversion. Unknown is not “no song.” Dates and recording versions remain unresolved where ambiguous. |

Ads account `582351779816254` maximum CSV actually covers **Sep 23, 2023–Jul 9, 2024**: eight ad IDs, 2,328 ad-days, **$661.02 USD and 77,954 impressions**. Campaign totals reconcile but remain separate. Known link clicks total 805 across 55 populated daily cells; 2,273 blanks remain unavailable. The later **Jul 10, 2024–Oct 20, 2026** export covers only **one ad ID**, with 833 explicit zero-spend/impression days and blank clicks. The separate **Jan 1–Oct 20, 2026** export says “No data available”: zero rows, not inferred spend zero. This does not establish complete paid scope across all ads/accounts. Ads timezone is Eastern Time; attribution is 7-day click or 1-day view.

## Preserved analytical boundaries

Spotify recovery remains intact: 14 recordings × five metrics across 1,024 dates, Jan 1, 2024–Oct 20, 2026; 71,680 canonical song-day-metric values. Its original source evidence, remaining playlist/geography/native-export gaps and recovery receipts are documented in the [prior handoff](HANDOFF_before_meta_collection_20261023.md) and [ADDITIONAL_DATA.md](../docs/ADDITIONAL_DATA.md).

Inherited **social, cross-platform and statistical results retain `cleaned-20261022` input lineage**; Spotify history retains `spotify-recovery-20261023`; new Meta evidence has `meta-collection-20261023` lineage. Old tests were not silently recalculated using repaired data. Historical v1 HTML findings remain preserved renderings, not refreshed current reports.

Meta account days use Pacific Time; Spotify days use UTC; Ads uses Eastern Time. Keep lifetime content results separate from period activity. Never sum daily unique audiences, reach or ratios. Instagram-selected crossposted Views retain explicit **Facebook + Instagram** scope; do not add standalone Facebook views or subtract them to invent Instagram-only values. Preserve parent/child source categories and author scopes.

No marketing-to-streaming causation is established. Next analysis needs compatible period exposure/click data, reliable post/recording/audio and destination mapping, paid-scope completeness and a dated event/release calendar. Missing clicks, audio identity, event dates and attribution cannot be manufactured from captions or blanks.

## Verification actually completed

- Full native Windows suite: **226 passed in 178.95 seconds**, before final UI polish and the final normalizer metadata-merge correction. Successful log: `logs/meta-full-tests-20261023-b.txt`; one pytest cache-permission warning, no test failures in that run. The unsuffixed earlier log is a failed attempt, not the success receipt.
- After final corrections: **19 focused normalization/audit tests** and **14 focused collection UI tests** passed. These overlap the full-suite coverage; do not add them as unique test counts. No final full-suite rerun is claimed.
- Normalization audit: 16 rectangular CSVs, **357 input hashes**, **7,256 provenance references**, exact raw/manual values and unchanged predecessor database verified.
- Independent second implementation: 183 exact Story IDs/1,098 cells, 127 daily Follows panels, Ads rows/IDs, 586 Facebook cells and mapping identities passed. Package audit verified **1,149 inherited assets byte-for-byte**.
- Actual launcher restart and persistence passed. Live browser verified active Meta after restart; Overview, Ads, resolved Follows, Story metric evidence and mapping rows rendered without observed app exceptions. Switching to the earlier Spotify version and back to Meta succeeded.
- Full-library backup verified **70 files, five databases and three analysis versions**. Relocated readback matched the live collection. No working library was replaced.

Unverified: Linux execution, real provider sign-in, hosted simultaneous-user behavior, physical double-click/Ctrl+C interaction, and exhaustive browser/filter combinations. The programmatic restart used the actual launcher with `--no-browser`. Local operation remains unauthenticated only on loopback. Hosted mode must require configured provider authentication, an explicit approved-user list and viewer/admin roles; no email addresses or password system were invented.

## Evidence, backup and safe continuation

Current frozen collection: `data/collection/meta-20261023/` (`raw/`, `normalized/`, reviewed `mapping/`). Preserve `mapping/draft-v1/` as superseded history; do not ingest it.

Current receipts under `data/reconciliation/meta_20261023/`:

- `package/`, `meta-collection-20261023.zip`, `staged_analysis/analysis.sqlite3`, `staging_result.json`.
- `normalization_acceptance_audit.json`, `independent_acceptance_audit.json`, `independent_package_acceptance_audit.json`.
- `promotion_result.json`, `final_preservation_and_backup.json`, `runtime_verification.json`.

Live browser screenshots/accessibility evidence: `test-results/meta-20261023/`; final dashboard image: `final-dashboard.png`. The runtime receipt records final restart health and the completed browser checks. Active version receipt: `%LOCALAPPDATA%\TheStats\analysis\meta-collection-20261023\activation_receipt.json`.

Verified backup: `backups/library-meta-collection-2026-10-23/`. For a new complete-library backup, use a fresh private directory:

```powershell
.\.venv\Scripts\python.exe -m stats_app.backup --bundle-dir .\backups\library-NEW-DATE
.\.venv\Scripts\python.exe -m stats_app.backup --verify-bundle .\backups\library-NEW-DATE
```

Follow [complete restore instructions](../docs/ARCHIVE_BACKUP.md); the old `--output` option backs up only the upload database. Keep a protected backup copy elsewhere. Reproduction must explicitly select the preserved predecessor, not accidentally use the new active version. The frozen collection preflight records the registry before activation; do not edit it to bypass rebuild checks. For future collection, create a new dated collection directory and fresh preflight, then stage and verify a new version.

The existing native Windows Python + Streamlit + Plotly/pandas/SQLite architecture and project `.venv` remain in use. No WSL, Docker, paid service, cloud database or API key is required locally. Reuse current setup, ingestion and storage code. `.gitignore` is configured to exclude private exports, databases, ZIPs, backups, logs, credentials and `.venv`; this workspace is currently **not a Git repository**, so tracked-file exclusion has not been established by Git status.
