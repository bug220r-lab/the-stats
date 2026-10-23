# Refreshing the decision report

The existing application and immutable analysis library remain authoritative. **Decision report** is a refreshable descriptive view of the selected **Analysis version**; it uses the same `stats_app/decision_report.py` functions as the command below. **Campaigns** adds an importable metadata log without modifying historical performance tables. Spotify, Social, Meta collection, YouTube collection, Cross-platform, imports and provenance remain available.

From PowerShell in the project directory:

```powershell
.\launch_windows.bat

.\.venv\Scripts\python.exe .\scripts\refresh_analysis.py `
  --output '.\data\reconciliation\decision-report-next'
```

Choose a new output directory for every run. Outputs are `decision_report.md`, `decision_report.json` and `coverage.csv`. Refresh reads the active immutable package, verifies its database hash before/after, recomputes descriptive decisions and saves the version and source-table hashes. It does not download new observations or update the original statistical testing family. Run against a historical registered version with `--analysis-key cleaned-20261022`, or relocate the library using `--data-dir <directory>`. Output inside the source library is rejected.

For new data, use the existing **Import data** preview-and-commit flow or the documented validated package importers. Generic uploads remain separately labelled snapshots; they are not silently promoted into the immutable analysis. Refresh only reports the selected registered analysis. The original October 20 baseline remains unverified; a reporting endpoint or later collection is not proof of membership. See [campaign log import](CAMPAIGNS.md), [metric rules](METRICS.md), [original pipeline reproduction](ANALYSIS_REPRODUCTION.md) and [source audit](SOURCE_AUDIT_2026-10-23.md).

## Definitions and selection rules

- Spotify additive daily streams, saves and playlist additions require a complete set of observed dates. Missing/failed/suppressed/partial values cannot produce complete period totals. Zero remains a measured zero.
- Unique listeners use an exactly matching direct platform period count. Weekly daily-listener sums are never used as weekly unique audiences. Streams divided by that compatible count measure listening intensity, not repeat-person retention.
- Follower growth uses the balance on the day before the requested interval and its final-day balance. Missing endpoints return unavailable; neither a sum of stocks nor social follow actions substitute for net change.
- Weeks are Monday–Sunday in the native reporting calendar. Twenty-eight-day blocks do not overlap and are anchored to the source reporting endpoint. Median and quartiles describe observed daily variation. Incomplete edges stay visible and have no period total.
- High-day screening uses the preceding complete 28 days' Q3 + 1.5 IQR, then compares the preceding and following 7 days excluding the event. Selected response windows do not overlap. This is a descriptive investigation queue, not statistical significance, causal lift, or retention. Selection and regression to the mean limit interpretation.
- Spotify recording IDs remain distinct even when titles match across releases. Joins validate unique keys; catalog shares use the whole artist total. Complete current catalog activity is reconciled to the artist total.
- The separately reviewed Instagram daily follows repair replaces only the same account/metric/scope in this new descriptive view. It does not overwrite `social/account_daily.csv` or recompute the old cross-platform tests. Its dated, source-level repair provenance remains available.
- Content distributions group by platform, selected account, native platform scope and format. They show counts, missingness, median, quartiles and maximum. Unequal lifetime ages and exposure prohibit first-week or controlled effectiveness claims. Hooks/excerpts are unknown unless explicitly logged with provenance.
- Top-country/city tables retain their own period and coverage fields. They are partial breakdowns. Demographic combinations must be explicitly present in the source.
- Source metrics with absent, nonfinite, negative or zero listener denominators are unavailable in ratio charts; raw source records remain unchanged.
- The most recent observed complete date describes loaded coverage, not a promise of platform freshness. UTC Spotify, Pacific Meta/YouTube and source-specific Ads calendars are not silently rebinned. Timestamps with known zones can be converted; daily aggregates cannot.

## Statistics and missing inputs

The earlier 12-test family remains pinned to its original weekly inputs, including four-week block bootstrap intervals, circular-shift uncertainty, first differences and BH adjustment. Six tests support its limited exploratory uncertainty; none survives adjustment. More recent repair rows do not count as independent samples or justify retroactively changing that family.

The report specifies three hypotheses and their missing inputs. Reliable song-event associations still need verified post/audio recording mappings, repeated separated events and a complete release/playlist/advertising/show calendar. First-week content comparisons need equal-age snapshots. Conversion requires measured tagged-link/landing-page actions and separate platform outcomes; no ordinary click identifies a confirmed stream. TikTok data and original October 20 archive membership remain unavailable.

The three proposed experiments include explicit outcomes, windows, matched/rotated repetition and practical thresholds. Thresholds are proposed decision criteria to agree before collection, not estimated effects or powered sample-size claims.

## Verification

Run the suite using a new temporary test directory when needed:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp '.\test-results\decision-workflow-next'
.\.venv\Scripts\python.exe -m pip check
```

Tests isolate synthetic fixtures and write no production imports. The decision tests reconcile real artist totals, period denominators, all 14 recordings, follower endpoints, the separately repaired follows series, preserved input hashes and all six new dashboard views. Campaign tests check repeat imports, revision order, conflicts, original bytes, timezone offsets and admin authorization. A failing optional YouTube file read is reported on its own and no longer hides usable Spotify/Meta data.
