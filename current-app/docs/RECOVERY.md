# Recovery and Spotify reconciliation

The original cleaned analysis remains a separate immutable SQLite snapshot at `analysis/cleaned-20261022/analysis.sqlite3`. It stores all 1,036 package files unchanged, 86 parsed tables, 115,053 source CSV records and the original ZIP. These heterogeneous records are not a single additive observation dataset. All 652 raw source hashes passed. The registry now supports `analysis_versions` plus an active `analysis_package` pointer, so later reconciled analyses can be selected without overwriting earlier results. See [additional Spotify recovery](ADDITIONAL_DATA.md), the current [handoff](../handoff/HANDOFF.md), and [original analysis reproduction](ANALYSIS_REPRODUCTION.md).

The sections below describe the earlier recovered archive, which remains unchanged and available in Snapshot explorer. Its historical collection gaps are not silently rewritten by the newer package. In particular, the later package adds 32 verified Meta native files, 377 valid content records including 126 Stories, and 183 quarantined malformed Story records; its coverage supersedes the earlier Stories export blocker for current analytical use.

The Windows application remains the working application. The Mac recovery bundle supplies missing source data and a separate archived database; its application files do not replace the Windows project. The original recovery ZIP and extracted source files remain unchanged under ignored `data/recovery/`.

## Registered snapshots

| Archive snapshot | Active observations | Meaning |
| --- | ---: | --- |
| 1 — Archived source package | 82,878 | Original recovered Spotify snapshot, unchanged. October 20 endpoint, October 22 collection; baseline unverified. |
| 2 — Social captures | 2,397 | Original recovered Facebook/Instagram snapshot, unchanged. |
| 3 — Spotify archive additions | 1,755 | Recording geography, audience segments, engagement cohorts, playlists, lifetime counters and feature evidence from the preserved archive. |
| 4 — Spotify historical-window supplement | 12,448 | Later-captured evidence for older windows through October 20, plus the source's exact 2025 YTD audience reading. |
| 5 — Spotify newer capture | 1,472 | Through October 21 where established, with unknown-window catalog and playlist evidence kept separately. |

The 15,675 new observations have 758 additional duplicate source references. Import reported zero revised/rejected observations. The 12,288-record legacy Windows snapshot is unchanged in its own database and overlaps recovered snapshot 1; never add these snapshots together. All 12,288 readings match recovered values and statuses. Of these, 3,072 rolling audience records express their reporting window differently: Windows has explicit 28-day bounds; the recovered source stores an endpoint with rolling semantics. This discrepancy remains visible and does not imply identical metadata.

The original October 20 baseline remains unavailable/unverified. Historical labels are preserved verbatim in storage. Display aliases explain their status without rewriting source evidence.

## Data locations

Under the configured `STATS_DATA_DIR` (default `%LOCALAPPDATA%\TheStats`):

- `stats.sqlite3`: original writable Windows database and future local uploads.
- `archive_registry.json`: explicit relative paths to registered archives.
- `archives/handoff-20261022/data/stats.sqlite3`: verified staged copy of the recovered database, including the three additions; read-only through the dashboard.
- `archives/handoff-20261022/data/sources/`: unchanged hash-addressed imported source bytes.
- `archives/handoff-20261022/evidence/`: complete recovery ZIP containing raw exports, evidence screenshots, manifests and original handoff.
- `archives/handoff-20261022/spotify_coverage.json`, `spotify_import_report.json`, `reconciliation/cross_reference.json` and `promotion_receipt.json`: coverage and preservation evidence.

The registry is portable with the whole data directory. Recorded historical paths in provenance are evidence, not runtime source locations. Source downloads resolve relocated files by hash and verify their bytes.

## Historical coverage limits of this earlier archive

These limits describe the unchanged archive, not the current recovery version. The October 23 UTC recovery resolves the earlier GOOMH and Son daily-history gaps. Use the active analysis version's Data quality page for current coverage and the seven remaining collection limitations.

- Original baseline membership is unverified. Artist history starts January 1, 2024 and is not lifetime.
- GOOMH has 365 stream days and lacks four other daily metrics. Son has 730 stream days. Missing full histories were not fabricated.
- Original recording geography covers 7 of 14 recordings; newer John Doe geography is a distinct capture. Top locations and playlist lists are not exhaustive.
- Playlist and newer catalog bounds are not established. There are 244 newly imported unknown-window readings (182 archive additions and 62 newer capture); they remain outside dated activity.
- The additions retain 76 nonavailable observations, including 66 missing source-period values. Missing data never becomes zero.
- Demographic counts, release lifetime versus available history, and engagement cohorts have unresolved source disagreements. Hierarchical stream-source totals overlap their child categories.
- Social daily exports cover July 24–October 21, Pacific Time. Instagram follows has only 38 dated observations; absent dates are missing.
- Instagram Results combined views explicitly include Facebook crossposts. Exact period reach/viewers are separate from daily unique readings. The 84 lifetime post readings have no reporting bounds; 198 Facebook prepublication zero cells are unavailable for calculation while original zeros remain in `source_value`.
- TikTok Studio and TikTok for Artists collection are deferred by user. Instagram Stories export generation was previously disabled; this was not retested and is not zero activity.

Derived totals, QA tables and metadata remain catalogued evidence instead of being counted again as independent activity. Coverage details are available in **Coverage & cross-reference**. Cumulative engagement can currently be inspected by exact source period; a complete cumulative curve is not yet provided.

## Reproducing the staged import

Only needed when rebuilding from the preserved recovery package. Do not run against a working archive in place. Use a new staging directory:

```powershell
.\.venv\Scripts\python.exe -m stats_app.spotify_archive --recovery-root .\data\recovery\mac_handoff_2026-10-22 --staging-dir .\data\reconciliation\new-stage
```

Inspect its coverage/import reports and run the tests before registration. `scripts/promote_handoff.py` copies a verified stage into a new named archive, verifies source hashes, and registers relative paths; it refuses to replace an existing archive. A full [library backup](ARCHIVE_BACKUP.md) is the supported way to move the already registered state to another machine.
