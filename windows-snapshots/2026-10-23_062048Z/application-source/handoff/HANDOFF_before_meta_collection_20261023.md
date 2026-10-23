# The Stats™️ — current Windows handoff

Saved October 22, 2026, America/New_York (October 23 UTC). The existing Windows application was extended in place. Lewis, Brandon and Samman remain the intended users. TikTok access and collection are deferred by Lewis. No hosting, deployment or new significance tests were performed.

## Launch and shutdown

Double-click `launch_windows.bat` in this project. It resolves its own folder, uses the project `.venv`, binds to `127.0.0.1`, and opens the default browser at http://127.0.0.1:8501/. Keep the console open; press Ctrl+C there to stop. Closing the browser does not stop the server. Run `setup_windows.bat` first only for initial environment setup.

From PowerShell in this folder:

```powershell
.\setup_windows.bat
.\launch_windows.bat
```

The dashboard is currently running on loopback. If port 8501 already belongs to this application, use the existing page rather than launching another instance. See [README](../README.md) and [Windows troubleshooting](../docs/WINDOWS.md).

## Active analysis and preservation

The default analytical version is **spotify-recovery-20261023**: “Spotify recovery · Oct 23 UTC capture · reporting through Oct 20”. The sidebar **Analysis version** selector also loads **cleaned-20261022**, the unchanged earlier analysis. Selection does not write data.

The local data root defaults to `%LOCALAPPDATA%\TheStats`, configurable with `STATS_DATA_DIR`. The relative registry now records both `analysis_versions` and the active `analysis_package` pointer.

| Store | State |
| --- | --- |
| `stats.sqlite3` | Existing Windows database: 12,288 observations, five native imports; byte-identical to preflight |
| `archives/handoff-20261022/data/stats.sqlite3` | Original Spotify snapshot 1 and social snapshot 2, plus prior additions 3–5; byte-identical to preflight |
| `analysis/cleaned-20261022/analysis.sqlite3` | Previous analysis: 1,036 files, 86 tables, 115,053 heterogeneous CSV records; byte-identical to preflight |
| `analysis/spotify-recovery-20261023/analysis.sqlite3` | New immutable analysis: 1,149 files, 104 tables, 161,144 heterogeneous CSV records, 738 verified raw-file hashes |

These file/table/record totals are not independent statistical samples. Browser storage and Streamlit session state are not authoritative. Original uploads and all three supplied ZIPs remain unchanged. Existing imports, snapshots, exports and source identities remain available.

The historical reporting endpoint remains **October 20, 2026**. Later historical recovery does **not** verify membership in the original October 20 archive. Original `original_baseline`, recovered `baseline_supplement`, and separate `newer_snapshot` labels retain that distinction. October 21 geography/catalog evidence and October 23 UTC capture times remain identifiable. No chart-derived evidence was relabelled a native export; only the four original native song exports are retained.

## Integration and before/after results

All three supplied packages were extracted and verified against their ZIP contents and manifests. The pipeline explicitly handles new recovery schemas and reconciles the cumulative source masters rather than appending supplements.

| Measure | Before | After |
| --- | ---: | ---: |
| Canonical song-day-metric values | 66,631 | 71,680 |
| Complete recording × metric histories | 64/70 | 70/70 |
| Catalog days matching artist streams | 365 | 1,024 |
| Additive song-period totals | 434 | 462 |
| Eligible complete release-age windows | 33 | 33 |
| Source comparison rows | 504 | 1,269 |
| Daily source rows | 11,678 | 37,311 |

All 14 recordings × five metrics now have 1,024 dates, January 1, 2024–October 20, 2026. GOOMH! and Son! history gaps are resolved within this interval. The 5,049 additions were independently parsed from raw chart evidence; all 66,631 older values and provenance agree. All 434 earlier additive totals agree; 28 new totals were recomputed.

Source overlap: **54 comparison rows and 1,516 daily rows agree**, with zero numeric conflicts; 765 comparison and 25,633 daily rows are additions. Existing source-row metadata also agrees. Of **297 stream-source checks, 252 are numeric table/chart matches and 45 have unavailable table values with explicitly zero chart sums**. Missing table values remain missing.

The separate live workbook audit observed all **16 supplied checks passing**, read the eight new tables, and corroborated counts/coverage/queue status. The integration script's own workbook-check note describes its offline scope; independent raw recalculation and the separate live workbook readback are different checks.

The queue is 36 complete, five partial and two blocked. “Complete” means the collected available scope, not every possible country, metric or window.

## Dashboard and calculation changes

- **Spotify → Catalog comparison:** full reconciled history, stable recording identities and explicit original/recovered provenance. Duplicate canonical grain is rejected.
- **Spotify → Recovered sources:** entity, population, exact reporting window, metric and hierarchy filters; comparison and daily charts with evidence and capture timestamps. Parent/child categories remain separate. Source audiences overlap and are not summed.
- **Spotify → Recovery evidence:** coverage, collection queue, seven limitations, separately dated snapshots/geography/content, recovered periods and reconciliation tables.
- **Data quality:** 70 histories, 71,680 canonical values, reporting endpoint, before/after changes and remaining limitations.
- Zero-denominator source ratios display as undefined gaps while original reported values are preserved. Unknown denominators remain qualified. Daily unique audiences, ratios and rolling measures are never summed.
- Analysis versioning preserves previous outputs; full-library backups include both registered versions.

Coverage, catalog reconciliation, source summaries, launch-window eligibility, current findings, dictionaries, inventories, cleaning logs, readiness assessments and dashboard caveats were regenerated. The focused analysis plan is in [ADDITIONAL_DATA.md](../docs/ADDITIONAL_DATA.md).

## Findings that changed or stayed the same

The complete bounded history now reconciles **101,342 catalog streams** over January 1, 2024–October 20, 2026. Funny Guy contributes 30,549 (30.1%); The Devil Wears Docs 11,872; Crawl 11,579. These are interval totals, not lifetime counters.

Latest 28-day momentum is unchanged: September 23–October 20 streams **4,246 vs 4,011 (+5.9%)**, while directly reported unique listeners are **1,062 vs 1,121 (−5.3%)**. Eleven of 14 recordings gained streams. Examples: album ¡La Cocaína! 154 vs 93 (+65.6%), Goodnight Mrs. Henderson 139 vs 87 (+59.8%), Son! 72 vs 44 (+63.6%), Waste Away 190 vs 157 (+21.0%). Funny Guy still leads with 1,488 streams (35.0% share) but is down 1.6%.

**No additional complete release-age windows became eligible.** Son!'s first 7/28/90-day totals were already supported and remain 68/135/220 streams. GOOMH! and the Lab Tapes releases still have incomplete 2023 launch histories; partial observed days are not promoted to complete windows.

All social and prior statistical outputs remain byte-identical and attached to **cleaned-20261022** inputs. All 12 original cross-platform comparisons and 53 saved result rows retain their old input version. No additional significance tests were run; none of the original planned comparisons survived adjustment (minimum BH-adjusted p 0.384615). This does not prove marketing has no effect.

The retained `The_Stats_Findings_Report.html` and `report/The_Stats_Findings_Report.html` inside the package are **historical v1 renderings**, not updated reports: they still describe the earlier 64/70 coverage. Use the current dashboard, regenerated findings, current quality/readiness documents and change log for the new version. The old HTML bytes remain preserved evidence.

## Seven remaining Spotify limitations

1. **¡La Cocaína! (Lab Tapes):** source metrics/windows incomplete; only 28-day source streams retained.
2. **Method Acting (album):** 28-day playlist window missing.
3. **Son!:** 28-day playlist window missing.
4. **THIS MACHINE:** 12-month playlist window missing.
5. **Waste Away:** playlist collection blocked; unsaved observations remain excluded.
6. **Expanded song-country sources:** US 12-month coverage exists for five songs; nine other song-country views remain unresolved.
7. **Additional native exports:** downloads failed; zero new native song exports.

## Unchanged Meta, TikTok and inference limits

The cleaned social input retains 3,528 canonical calendar-metric rows, 128 missing Instagram Follows values as null, 377 valid lifetime content records including 126 valid Stories, and 183 malformed Stories quarantined. October 21 Meta activity is partial and excluded by default. Lifetime content results stay separate from period activity and cannot be assigned to publication day.

Instagram-selected latest complete 90-day Views are **23,270 with Facebook + Instagram scope**. Do not add standalone Facebook views or subtract them to manufacture Instagram-only daily values. The older social snapshot 2's 23,322 reading remains a separate retrieval. Content age, author scope, paid exposure, incomplete exports, missing attribution and Spotify UTC/Meta Pacific date boundaries prevent a causal social-to-streaming conclusion. TikTok remains unavailable and deferred; no access attempt was made.

## Validation actually performed in this continuation

- Full native Windows suite: **187 passed in 160.82 seconds**, no skips reported. Covers ingestion validation, duplicates, sealed baseline protection, persistence, source hashes, recovery parsing, cumulative overlap, catalog reconciliation, aggregation restrictions, version switching, backup/restore, hosted fail-closed guards and Streamlit page rendering.
- Focused integration suite: 10 passed; storage/versioning/backup subset: 18 passed. These are included in the full-suite coverage, not additional unique tests. A focused source zero-denominator test also passed before the full suite.
- All three ZIP contents/manifests and 738 raw hashes verified; 1,149 final package files match the generated integrated ZIP. Independent source parsing, period recalculation and workbook readback are saved separately.
- Activated atomically into a new version directory, retaining the earlier registry entry. All three earlier database SHA-256 values still equal preflight; all four databases pass SQLite quick checks. Active database equals staged database and activation receipt.
- Restarted through the actual `launch_windows.bat --no-browser` command against persisted data. Verified HTTP health `ok` and the only port-8501 listener at **127.0.0.1**.
- Live Chrome inspection confirmed active version after restart, recovery coverage, full-history catalog chart, scoped source streams and preserved-version switching. Automated AppTests also checked full-history completeness, source ratio view, recovery evidence, original cross-platform input labels and old-version gaps.
- New full-library backup `backups/library-spotify-recovery-2026-10-22`: **66 files verified**, including all four databases, both analysis versions and active registry pointer. Restore behavior was exercised by the suite; no working library was replaced.

Python remains 3.12.14 x64 in project `.venv`; dependency pins remain in requirements files. Setup/launcher architecture, private-hosting guards and local import workflow were reused.

Unverified: Linux execution, real OIDC provider login, hosted multi-user behavior, physical double-click/Ctrl+C interaction and exhaustive browser/filter combinations. No private hosting was deployed. The server restart used targeted termination of the identified application process. Hosted operation still requires configured provider sign-in, explicit approved users and roles; no emails or passwords were invented.

## Backup, reproduction and evidence

```powershell
.\.venv\Scripts\python.exe -m stats_app.backup --bundle-dir .\backups\library-NEW-DATE
.\.venv\Scripts\python.exe -m stats_app.backup --verify-bundle .\backups\library-NEW-DATE
```

Use a fresh private backup directory, keep a protected copy elsewhere, and follow [complete restore instructions](../docs/ARCHIVE_BACKUP.md). The old `--output` command backs up only the upload database. [Additional-data instructions](../docs/ADDITIONAL_DATA.md) record source identities, checksums, integration, staging and activation commands.

Current evidence under `data/reconciliation/additional_20261023/`:

- `analysis_v2/`: final regenerated package. Earlier `analysis_v2_draft_*` folders are superseded working drafts.
- `independent_input_audit.json` / `.md`; `workbook_audit.json` / `.md`.
- `analysis_v2/audit/recovery_changes.json`, `final_validation.json`, `statistical_input_versions.json`.
- `preflight_preservation.json`, `final_preservation.json`, `analysis_stage_metadata.json`.
- `staged_analysis_v2/analysis.sqlite3` and `analysis_package_import.json`.
- `The_Stats_Integrated_Spotify_Recovery_20261023.zip`.

The active data folder contains `analysis/spotify-recovery-20261023/activation_receipt.json`. Test proof is in `test-results/full-recovery-pytest.txt`, `recovery-coverage.png`, `recovery-catalog.png` and `recovery-sources.png`.

The previous handoff is retained as [HANDOFF_before_spotify_recovery_20261023.md](HANDOFF_before_spotify_recovery_20261023.md), including details of the earlier archive imports and original analysis reproduction. Its missing-history descriptions are historical and superseded by this document.

Private exports, databases, ZIPs, `.venv`, credentials, backups, logs and test artifacts remain excluded from Git. Reuse the existing workspace and registry; never overwrite a working database with a recovery ZIP.
