# Meta collection normalization and evidence audit

The Oct 23 collection is separate evidence. Original CSVs, existing SQLite
snapshots, malformed Story records and the unverified Oct 20 baseline designation
remain unchanged.

After all capture files are final, run from the project folder in PowerShell:

```powershell
$env:PYTHONUTF8 = '1'
.venv\Scripts\python.exe scripts/normalize_meta_collection.py --collection data/collection/meta-20261023 --output data/collection/meta-20261023/normalized --data-dir "$env:LOCALAPPDATA\TheStats" --collection-complete
.venv\Scripts\python.exe scripts/audit_meta_collection.py --collection data/collection/meta-20261023 --normalized data/collection/meta-20261023/normalized --report data/reconciliation/meta_20261023/normalization_acceptance_audit.json --require-collection-targets
.venv\Scripts\python.exe -m pytest tests/test_normalize_meta_collection.py tests/test_audit_meta_collection.py -q
```

The normalizer refuses an existing output directory. The audit report also needs
a new path. Neither script writes to a database. Do not run normalization while
capture JSON files are being appended: changed inputs cause validation to fail.
The optional target gate requires 293 observed complete Follows dates from Jan 1
through Oct 20 and captures for all 183 known quarantined Story IDs. It does not
mean every Story metric is available.

Key tables:

| Table | Grain and interpretation |
|---|---|
| `ads_campaigns.csv` | Native campaign reporting windows; never add to ad-level delivery totals. Native IDs may be absent, so source-row identities are retained. |
| `ads_history.csv` | Native ad-day observations with account, IDs, reporting window, timezone, currency and source lineage. Blank link clicks remain unavailable. |
| `ads_export_coverage.csv` | One export and its actual native dates, requested dates, entity/date coverage and observed-cell coverage. Header-only/no-data exports do not become zero-spend observations. |
| `ads_level_reconciliation.csv` | Matching-window comparison of known campaign and daily-ad totals. Agreement does not make missing cells observed. |
| `instagram_follows.csv` | Native sparse export rows and explicit single-day UI observations, retained as evidence. |
| `follows_daily_resolved.csv` | New complete-day view: old observed daily values plus verified repairs for exact matching dates/account/timezone. Every row has predecessor and selected evidence lineage; unresolved dates remain blank. |
| `follows_daily_partial.csv` | Partial reporting day kept outside the complete-day view. |
| `instagram_follows_comparison.csv` | Each new observation compared with prior evidence; conflicts remain explicit. |
| `instagram_follows_missing_date_status.csv` | Every originally missing date and its resolution status. |
| `instagram_stories_manual.csv` | One fresh Story detail capture per known post, retaining exact available fields and unavailable markers. Publication timezone remains unknown when the source does not label it. |
| `instagram_story_metrics.csv` | One post/capture/metric; fresh lifetime values are not period activity or reconstructed old export rows. |
| `facebook_daily_recheck.csv` | Fresh native interactions and visits, compared with compatible prior dates/asset/timezone. Agreement confirms the exported series, not the cause of its June shift. |
| `repair_status.csv`, `collection_status.csv` | Explicit collection and repair scope. |

Capture timestamps and acquisition bounds are distinct. Filesystem modification
times are retained as evidence bounds and never invented as exact captures.
MBS asset IDs and platform-native account IDs are labelled separately. Link clicks
do not identify Spotify destinations. Daily unique audiences, reach and ratios
are not summed. No correlation or significance tests are run by these scripts.

The independent audit reads all normalized CSVs strictly, verifies manifests and
input hashes, checks exact native cells and manual AX overview values, compares
wide and per-field Story tables, checks daily-ad grain with SQL, validates Follows
lineage, and verifies the predecessor database and retained canonical assets.
