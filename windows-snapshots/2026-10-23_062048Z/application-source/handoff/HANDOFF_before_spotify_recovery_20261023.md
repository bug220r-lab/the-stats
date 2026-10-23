# The Stats™️ — current Windows handoff

Saved October 22, 2026, America/New_York (October 23 UTC). Lewis is the user; Brandon and Samman are future private users. The band name **[REDACTED]** is literal. The existing Windows application was extended in place. No deployment, public sharing, account scraping or scheduled collection was performed. TikTok access/collection is deferred by Lewis.

## Run the application

Workspace: `C:\Users\jlewi\OneDrive\Documents\ChatGPT\The Stats™️`.

Double-click `launch_windows.bat` in this folder. It uses the project `.venv`, binds only to `127.0.0.1`, and opens the default browser at http://127.0.0.1:8501/. Keep the console open. Press Ctrl+C in that console to stop it; closing the browser does not stop the server. Run `setup_windows.bat` first only when the environment needs initial setup.

Equivalent PowerShell commands from the project folder:

```powershell
.\setup_windows.bat
.\launch_windows.bat
```

The dashboard is currently running. If it already owns port 8501, open its existing browser page; do not launch a second copy. See [README](../README.md) and [Windows troubleshooting](../docs/WINDOWS.md).

## What is now available

- **Overview:** audited matching 7-, 28-, 90-day and matched-year comparisons; separately reported period-unique listeners; daily stream history.
- **Spotify:** date filters, daily metrics with valid aggregation, complete-month view, recording comparisons and artist shares, release-age windows, audience and stream-source scopes, all retained Spotify evidence tables and retrieval-vintage selection.
- **Social:** complete account activity by platform/metric/scope, equal-window comparisons, explicit partial-day opt-in, lifetime content with age and author filters, retained publishing cadence, audience percentages, native period/stock evidence, and TikTok unavailable state.
- **Cross-platform:** all 12 planned comparisons, six eligible uncertainty estimates, blocked/undefined cases, adjusted results, marginal intervals, saved paired-week plots, methods and sensitivities.
- **Data quality:** coverage/readiness, raw lineage, quarantined records, all 53 analysis results, independent package identity and collection priorities.
- **Snapshot explorer / Coverage & cross-reference:** the older Windows and recovered archive snapshots remain available without being blended into the cleaned analysis.
- **Import data:** existing preview/validation/SQLite commit workflow remains available for new named local snapshots. Original exports are preserved.

## Three separate persistent stores

Default data root: `%LOCALAPPDATA%\TheStats`, configurable with `STATS_DATA_DIR`. All paths in `archive_registry.json` are relative to that root.

1. `stats.sqlite3`: existing Windows database, **12,288 observations / five native imports**, unchanged. Its old baseline label and sealing are historical metadata. The UI explains that original baseline membership was unverified.
2. `archives/handoff-20261022/data/stats.sqlite3`: separate recovered archive with original snapshots 1 and 2 unchanged, plus additions. The dashboard reads this archive without migrations or writes.
3. `analysis/cleaned-20261022/analysis.sqlite3`: immutable cleaned analysis package, with **1,036 exact package files, 86 parsed tables and 115,053 CSV records**, plus original ZIP bytes. These tables have different grains and are not one additive observation dataset. This is the default analytical view.

No browser storage or Streamlit session state is authoritative. New uploads remain in the first store. Registered archives and cleaned analysis are read-only. Sources are recovered by hash or stored original bytes, not stale Mac paths. All earlier stores remained byte-identical through activation and final verification.

### Earlier archive additions

| Snapshot | Active observations | Preservation |
| --- | ---: | --- |
| 1 — Archived source package · Oct 20 reporting endpoint · collected Oct 22 | 82,878 | Original rows, imports, provenance, issues and metadata unchanged |
| 2 — Social captures · Oct 22, 2026 · separate from Oct 20 archive | 2,397 | Original Facebook/Instagram snapshot unchanged |
| 3 — Spotify archive additions · Oct 20 endpoint · baseline unverified | 1,755 | New named snapshot |
| 4 — Spotify historical-window supplement · Oct 20 endpoint · baseline unverified | 12,448 | New named retrieval vintage |
| 5 — Spotify newer capture · Oct 21 endpoint or bounds unavailable | 1,472 | New named snapshot, 62 rows with unknown reporting bounds |

Added **15,675 observations**, with **758 matching duplicate source references**, zero revised/rejected readings. Original 27 source files and recovery DB bytes verified unchanged. Derived/QA/metadata tables remain catalogued evidence instead of duplicate activity. Do not add these snapshots or the legacy native subset together.

All 12,288 legacy Windows readings match recovered values/statuses. Of them, 3,072 rolling audience observations have explicit 28-day bounds in Windows versus an endpoint plus rolling semantics in the recovered archive. This metadata discrepancy remains preserved, not silently harmonized.

### Cleaned package and baseline meaning

The later [cleaned analysis ZIP](https://drive.google.com/file/d/1Y21nrKj5ARqyCE9im36Ekg19XJndrmM7/view) was supplied after archive reconciliation began. All **652 retained raw inputs** passed hashes, including **32 native Meta CSVs**. Delivered files and raw source inputs remain unchanged.

The package's `original_baseline`, `baseline_supplement` and `newer_snapshot` classifications are retained verbatim. Its Spotify reporting cutoff is October 20. This does not rewrite the earlier archive's unverified historical baseline membership or pretend an activity cutoff is retrieval time. Later Meta and Spotify retrievals remain distinct.

The package expands social coverage: **3,528 canonical calendar-metric rows**, **128 missing Instagram Follows values kept null**, **377 valid lifetime content records** including **126 valid Stories**, and **183 malformed Story records quarantined**. The earlier disabled Stories export record remains historical evidence; it does not describe all data in this newer package.

## Verified results

- Spotify September 23–October 20 streams **4,246**, prior 28 days **4,011**, **+5.9%**; exact period listeners **1,062 vs 1,121**, **−5.3%**.
- **11 of 14 recordings** gained streams; Funny Guy supplied **35.0%** of latest 28-day streams. All 14 recordings reconcile across 365 common complete dates.
- January 1–October 20 streams **58,175 (2026) vs 22,825 (2025)**, **+154.9%**. Latest/prior 90-day streams **13,775 vs 19,832**, **−30.5%**.
- Cleaned Instagram-selected latest complete 90-day Views **23,270**, explicitly **Facebook + Instagram combined**. Standalone Facebook views must not be added or subtracted to synthesize daily Instagram-only views. This package's retrieval differs from older social snapshot 2's 23,322 reading; neither overwrites the other.
- All 12 planned cross-platform comparisons remain visible; six support exploratory uncertainty. None survives multiple-testing adjustment; minimum BH-adjusted p **0.384615**. This is not proof of no marketing effect. Marginal intervals do not override adjusted tests.

## Validation actually performed

- Full Windows suite: **165 passed in 139.69 seconds**. It covers startup guards, import validation, duplicates, sealed-record protection, persistence, source hashes, archive adapters, full-library backup/restore, clean table types and IDs, matched periods, invalid audience aggregation, join cardinality, partial dates, author/content filters, quarantine, all planned comparisons and Streamlit page rendering.
- After final presentation adjustments, the four analytical AppTests were rerun separately: **4 passed in 11.20 seconds**. Final integrity checks passed and all three database hashes matched their preservation/activation receipts.
- Audited `code/run_all.py` reproduced in a **separate copy**, exit 0 in **45.27 seconds**. Two path-identity expressions needed `.as_posix()` on Windows; UTF-8 was enabled. Original package and raw files were untouched. Twelve core output CSVs matched delivered outputs numerically; independent coefficients and adjusted p-values also matched.
- Python **3.12.14 x64**; project `.venv`; Streamlit **1.64.0**, pandas **2.3.3**, NumPy **2.5.4**, Plotly **6.3.1**, SciPy **1.17.0**, matplotlib **3.10.8**, openpyxl **3.1.5**. Exact installed versions are pinned. `pip check` passed. pandas/NumPy differ from package pins, but reproduced outputs matched; deprecation warnings did not fail calculations.
- Launched the actual Windows batch launcher and restarted the server against persisted data. Socket verified **127.0.0.1:8501 only**. Browser charts, labels and representative filters were inspected, including the data-quality assessment and cross-platform uncertainty chart. The overview was visually checked at 1920×863 and 760×1000; KPI labels and the chart remained readable, and the normal viewport was restored. An actual downloaded catalog CSV had 14 unique IDs and totals **4,246/4,011**.
- Created `backups/library-analysis-2026-10-22`; **58 files verified**. It includes all three databases, registered sources/evidence, relative registry and checksum manifest.

## Back up and reproduce

```powershell
.\.venv\Scripts\python.exe -m stats_app.backup --bundle-dir .\backups\library-NEW-DATE
.\.venv\Scripts\python.exe -m stats_app.backup --verify-bundle .\backups\library-NEW-DATE
```

Use a new directory for each backup and retain a protected copy elsewhere. The older `--output` backup command covers only local uploads and omits registered libraries. See [complete backup and restore](../docs/ARCHIVE_BACKUP.md).

Use [analysis reproduction instructions](../docs/ANALYSIS_REPRODUCTION.md) to rerun the audited pipeline in a fresh output copy. Do not run transformations against preserved raw or delivered package directories.

## Remaining limits and next work

- TikTok Studio and TikTok for Artists remain unavailable and deferred; no login attempts or collection are needed now.
- GOOMH has only 365 stream days and lacks four other daily histories; Son has 730 stream days. Incomplete series remain unavailable for full-history comparisons.
- October 21 Meta data is partial; October is an incomplete month. Defaults exclude them from complete-period results. Daily unique audiences, rolling measures and stocks are never summed into period activity.
- Lifetime content is not assigned to publication day. Retained publication counts are an incomplete exported inventory. Different ages/author scopes/paid exposure prevent a fair retrospective format contest.
- Quarantined Stories, missing Follows, audience/all-time discrepancies, incomplete paid/events/attribution data and timezone mismatch remain unresolved evidence limitations.
- Cross-platform results are saved exploratory analyses, not dynamically refit after filters. New uploads do not automatically rerun the audited pipeline or overwrite this analysis snapshot.
- Generic upload requires known reporting bounds. Unknown-window/lifetime evidence is handled by the recovered/cleaned adapters; do not invent dates to force it into generic imports.
- Linux runtime, real OIDC provider sign-in, private hosting, simultaneous hosted users and exhaustive browser/filter combinations remain unverified. Hosted configuration still fails closed without authentication and explicit approved-user authorization. No emails or homemade passwords were invented.
- Physical double-click and Ctrl+C on this user's console were not automated in this continuation. The batch launcher ran successfully; restart verification used targeted termination of the identified app process. See the original milestone's precise acceptance limits.

## Evidence locations

- `data/recovery/`: unchanged original ZIPs and extracted packages, including original Mac `HANDOFF.md`.
- `data/reconciliation/cross_reference.json`, `independent_staging_audit.json`, `cleaned_analysis_audit.json`.
- `data/reconciliation/staged_handoff/`: Spotify import/coverage reports and staging copy.
- `data/reconciliation/staged_analysis/`: cleaned SQLite staging copy and import manifest.
- `data/reconciliation/analysis_reproduction_2026-10-22/`: regenerated pipeline outputs and logs.
- Local data `archives/handoff-20261022/promotion_receipt.json` and `analysis/cleaned-20261022/activation_receipt.json`.
- `test-results/full-analysis-pytest.txt` and browser captures `analysis-overview.png`, `analysis-overview-narrow.png`, `analysis-quality.png`, and `analysis-cross-platform.png`.

Private exports, databases, ZIPs, `.venv`, credentials, logs, backups and test artifacts are excluded from Git. Future work should reuse this workspace and data registry, never replace a working database with a recovery ZIP.
