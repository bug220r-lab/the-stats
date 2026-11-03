# Additional Spotify recovery integration

Plan recorded October 22, 2026, America/New_York. The supplied recovery and continuation packages are dated October 23 UTC. This is a new analysis version in the existing Windows application; no earlier database or source package is replaced.

## Inputs and authority

- Original cleaned analysis: `1Y21nrKj5ARqyCE9im36Ekg19XJndrmM7`; retained ZIP SHA-256 `18b8079945a45b41b2d211d35b4cacf33ecbd5f40f81c55b41858f6017949c21`.
- Recovery: `1k63vp8Tgjt7QjaBWnwPmrSI1BCeKCMAe`; ZIP SHA-256 `90e6e0525a8ac39935b8ea8a37758545ad1f37d4760f13de57372b37c1f59c60`.
- Continuation: `1qsvqB2W-4i8FpHHpC6tT9Bx7342jpfzz`; ZIP SHA-256 `73fec8f41207efdc2e73eb5b2846163c8215387db96dbf0c93ff2f92e377a5fb`.
- Current workbook: `1gfPLM_kj8mT1bNn0e3sv2udEU3644PR5z_20QMfl3Yc`. Recovery tabs corroborate the handoff; their status labels are not a substitute for archive and raw-capture validation.

Original ZIPs and extracted source bytes stay under `data/recovery/`. The new derived package and reports stay under `data/reconciliation/additional_20261023/`. Previous package files that need replacement in the new derived version remain archived with their input version. Raw captures retain source URLs, selected entity/country/window, capture timestamps and evidence type.

## Focused analysis and testing family

1. Verify archive member bytes and all supplied SHA-256 manifests; record hashes of every earlier live database before activation.
2. Reconcile stable recording/date/metric keys: compare the 66,631 retained observations, 5,049 reported additions and supplied 71,680-row complete master. Check dates, exact counts, duplicate values and all 70 series. Do not impute missing values.
3. Verify cumulative source tables contain earlier masters and exactly the reported additions. Check agreement at entity, country, reporting-window, metric and source grain before canonical selection. Retain evidence from duplicate captures and fail on unresolved numeric conflicts.
4. Independently check the source-period versus daily-stream reconciliation against retained chart labels and tables. Keep unavailable table cells distinct from explicit daily zero readings. Daily listeners, ratios, source parents/children and overlapping windows are never additive samples.
5. Recompute descriptive catalog history, artist/catalog daily reconciliation, eligible 7/28/90-day release-age windows, coverage, source summaries and affected readiness/findings. A complete history beginning January 2024 cannot establish missing 2023 launch activity or a lifetime total.
6. Preserve the original 12-test cross-platform family and its exact input version. No new significance tests are added. Check the unchanged artist/Meta inputs and clearly identify retained statistical results instead of presenting them as newly fitted analyses of recovery rows.
7. Stage a new immutable SQLite analysis package, verify saved tables and source bytes, and activate only after checks pass. Keep the old analysis selectable. Verify backup/restore includes all versions, along with startup, full-history comparisons, scoped source views, older-version switching and browser rendering.

## Scope that remains distinct

The October 20 historical reporting endpoint remains unchanged. Later capture timestamps are not backdated. October 21 geography/catalog readings and content/event snapshots stay outside that history. Browser chart-derived CSVs remain chart evidence; no additional native song exports succeeded. Earlier baseline-membership uncertainty remains historical metadata and is not resolved by a more complete retrospective collection.

Seven supplied collection limitations remain: La Cocaína Lab Tapes source windows/metrics, Method Acting album and Son 28-day playlists, THIS MACHINE 12-month playlists, Waste Away playlist failures, unresolved expanded song-country coverage for nine songs, and failed additional native exports. Meta missingness, Stories quarantine and TikTok unavailability remain in force unless separate evidence resolves them.

## Reproducibility and evidence

The integration command, final measured checks, changed findings and new version identity are recorded in the current [handoff](../handoff/HANDOFF.md). `preflight_preservation.json` captures the earlier databases. `workbook_audit.json` preserves exact bounded workbook reads and `workbook_audit.md` explains their limits. Independent raw-input checks and the integration change log accompany the staged package.

From the project folder, reproduce the integration into a **new output directory**:

```powershell
.\.venv\Scripts\python.exe scripts/integrate_spotify_recovery.py `
  --original data/recovery/cleaned_analysis_2026-10-22/analysis_2026-10-22 `
  --recovery data/recovery/additional_20261023/recovery/The_Stats_Collection_Recovery_2026-10-23 `
  --continuation data/recovery/additional_20261023/continuation/The_Stats_Collection_Continuation_2026-10-23 `
  --output data/reconciliation/additional_20261023/analysis_v2_reproduced `
  --archives data/recovery/The_Stats_Cleaned_Analysis_2026-10-22.zip data/recovery/The_Stats_Collection_Recovery_2026-10-23.zip data/recovery/The_Stats_Collection_Continuation_2026-10-23.zip

.\.venv\Scripts\python.exe scripts/audit_additional_inputs.py `
  --output data/reconciliation/additional_20261023/independent_input_audit_rerun.json
```

The integration refuses an existing output directory. It uses local sources and does not execute the downloaded package builders. Generated package documents identify the current version and archive superseded documents under `raw/previous_analysis_v1/`. Statistical and social files retain their original bytes and input version. The source receipts distinguish 252 numeric table/chart agreements from 45 unavailable-table/explicit-chart-zero cases.

The saved derived ZIP is `data/reconciliation/additional_20261023/The_Stats_Integrated_Spotify_Recovery_20261023.zip`; staging metadata is `analysis_stage_metadata.json` beside it. To create a new database copy from those exact inputs:

```powershell
.\.venv\Scripts\python.exe -m stats_app.analysis_repository `
  --package-root data/reconciliation/additional_20261023/analysis_v2 `
  --zip-path data/reconciliation/additional_20261023/The_Stats_Integrated_Spotify_Recovery_20261023.zip `
  --output-dir data/reconciliation/additional_20261023/staged_analysis_reproduced `
  --label "Spotify recovery · Oct 23 UTC capture · reporting through Oct 20" `
  --metadata-json data/reconciliation/additional_20261023/analysis_stage_metadata.json
```

Activation is separate from reproduction. `python -m scripts.promote_analysis` requires a new explicit version key and an independent audit. It verifies source tables and earlier database hashes before atomically updating the registry. Identical same-key replays are read-only; they do not silently reactivate an older analysis. Use the sidebar selector to inspect a retained version.
