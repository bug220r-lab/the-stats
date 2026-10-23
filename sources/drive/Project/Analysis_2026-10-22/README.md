# The Stats™️ — cleaned data and statistical analysis

Prepared for Lewis on October 22, 2026 (America/New_York). The Spotify activity baseline ends **October 20, 2026**. Later observations and supplemental collection remain separate. This package analyzes the preserved exports; it is not a live connection or a dashboard.

## Start here

- Open `The_Stats_Findings_Report.html` for the findings, charts, uncertainty, and recommended next steps.
- Read `DASHBOARD_HANDOFF.md` before loading the CSVs into a future dashboard.
- `statistical_results.csv` contains the combined analysis record, including blocked and exploratory questions. A blank confidence interval or p-value is **not zero**; read the status and limitations.
- `analysis_readiness.csv`, `data_dictionary.csv`, `source_inventory.csv`, and `cleaning_log.csv` document the analytical contract. Domain-specific versions retain additional detail.

## Folder layout

| Folder | Contents |
|---|---|
| `raw/spotify_baseline/` | Preserved original native Spotify exports, rendered source captures, and earlier derived tables. The previous derived files are inputs to audit, not automatically trusted results. |
| `raw/spotify_supplement/` | Later source captures, supplemental baseline records, and newer snapshots; never silently substituted for the baseline. |
| `raw/meta/` | Preserved Facebook and Instagram exports, account evidence, manual snapshots, and access records. TikTok has access-status records only. |
| `raw/current_workbook.xlsx` | A read-only snapshot of the collection workbook retrieved during this analysis. |
| `spotify/cleaned/` | Rebuilt Spotify artist/track activity and separately retained period, audience, source, release, and geography tables. |
| `social/` | Separate account-day, post-snapshot, audience-snapshot, and reported-period data; quality flags and excluded raw rows. |
| `cross_platform/` | Predeclared plan, comparable weekly view, join audit, all planned statistical questions, diagnostics and sensitivity analyses. |
| `code/` | Python transformation, analysis, and validation scripts. |
| `audit/` | Original-file checksums, current queue, file duplicates, independent review, and final validation. |

## Reproduce on Windows

Use Python 3.12 or a compatible interpreter. Unzip the whole package and keep the directory structure. From this directory in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe code\run_all.py
```

If your interpreter is named `python`, use it in place of `py -3.12`. On macOS/Linux, the equivalent commands are `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt`, and `.venv/bin/python code/run_all.py`.

The analysis scripts run offline after dependencies are installed. They use paths relative to the package, contain no credentials, and do not edit `raw/` or any connected account. `openpyxl` is used only to read the source workbook. CSVs, JSON, and PNG figures are regenerated in the output folders. The delivered HTML report is a reviewed snapshot; rebuilding the analytical CSVs does not automatically rewrite its narrative.

## Rules that must survive future work

- Daily Spotify listeners and Meta reach/viewers are unique counts **within their own day**. Do not sum them into weekly or monthly unique people.
- Spotify followers are a stock. Their difference is net change, not gross new followers. Rolling audience metrics are overlapping windows.
- Meta selected “Instagram views” is a combined Facebook + Instagram measure where explicitly flagged. Keep its scope visible.
- Post metrics describe lifetime/per-export snapshots. Publication dates support posting-cadence counts, not assignment of all later engagement to publication day.
- Missing values, suppressed/undefined values, unavailable metrics, and reported zeros remain distinct. Malformed Story rows remain quarantined.
- Artist and track tables have different grains. Join by verified keys with cardinality checks. Do not multiply account totals across tracks/posts.
- Meta uses the source’s Pacific day; Spotify uses UTC. Weekly comparisons reduce but cannot eliminate boundary mismatch. No exact timezone re-binning of aggregate daily values was attempted.
- This analysis measures associations and observed changes. It does not identify individual listeners, measure a social-to-streaming conversion rate, or establish causal marketing lift.

## Sources and versions

The source folder is [The Stats project folder](https://drive.google.com/drive/folders/1sE3oczZadl04Ro2HDf0GQ51oxuNxiLdR). The [collection queue](https://docs.google.com/spreadsheets/d/1gfPLM_kj8mT1bNn0e3sv2udEU3644PR5z_20QMfl3Yc/edit#gid=82074406) was read during this run. Additional Meta data was recovered from the project’s saved collection archive. Detailed file/source/row lineage lives in the inventories and cleaned tables. All original raw bytes are checked against `raw_sha256.json`.

New collection should create a new dated input snapshot and update provenance intentionally. Do not change raw bytes to make validation pass or overwrite historical baselines.
