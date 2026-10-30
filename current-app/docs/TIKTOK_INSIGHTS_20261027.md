# TikTok insights and strongest posts — October 27, 2026

Open **Analysis → TikTok insights** at `/tiktok-insights` for the saved TikTok, Spotify, and other-platform readout. It is a fixed October 27 report using analysis version `meta-story-backfill-20261024` and TikTok collection `tiktok-20261027-studio`. Changing the dashboard's analysis selector does not recalculate or change this report.

The six views are:

- **Findings & actions:** the main conclusions and next experiments.
- **Trends:** comparable activity windows and longer-term movement.
- **Song priorities:** the evidence for promoting Funny Guy first and testing The Cut.
- **Post examples:** recent and historical posts, with their different measurement scopes retained.
- **Other platforms:** Apple Music, YouTube, Meta, Linktree, and Shopify findings and limits.
- **Sources & downloads:** reporting periods, retained source receipts, and the complete report.

The principal recent comparison is September 23–October 20 against August 26–September 22, 2026. The longer daily comparison has 360 common calendar labels through October 20. TikTok's reporting timezone remains unknown; platform calendars and cumulative post counters are not interchangeable. Associations do not establish that a TikTok post caused streams, listeners, or sales. **TikTok for Artists remains pending.**

## Strongest-post rankings

Open **Explore → TikTok → Strongest posts** to inspect the collected rankings. Choose a metric and scope, search captions or verified post IDs, and download the matching evidence as CSV. The download includes all matching rows in that scope, even when the chart shows only the top few.

**Reporting-window rankings** retain TikTok's native 7-, 28-, 60-, and 365-day windows and their source labels. These are retained top lists, not a complete list of every post published during each window. The selected-period metric stays separate from the cumulative “All views” value.

**Cumulative post snapshots** use the separate inventory of 615 owned posts. Posts have unequal ages and capture times, so this ordering is not a controlled creative comparison or activity within the selected reporting window. Rounded K/M labels remain rounded; chart positions are approximate and identical rounded labels do not establish exact ties. Missing metrics remain missing. Public post links appear only when the retained evidence resolves the post unambiguously; duplicate or unmatched captions remain unlinked.

## Downloads and preservation

The complete **HTML** report works offline and includes all eight report sections, tables, embedded charts, links, reporting periods, and source receipts. It needs no report plugin or network connection. **Markdown** provides the same findings and relative references to the packaged chart images. The provenance JSON retains the package manifest and source receipts. The evidence selector provides individual query tables as CSV.

The native report package is `data/reports/tiktok-cross-platform-20261027/`. Its manifest and asset hashes are checked before display; absent or invalid content is reported explicitly. Original collections, analytical outputs, the earlier React draft, and the original verification receipt remain unchanged. The initial native package is separately retained at `outputs/tiktok_cross_platform_native_initial_package_20261027/`.

The unavailable reporting plugin was bypassed by integrating the completed analysis into The Stats' existing local dashboard. No plugin reconnection or TikTok for Artists access is required to read it.

## Reproduce and verify

The analytical scripts and executed notebook remain in `outputs/tiktok_cross_platform_analysis_20261027/`. Package the reviewed outputs with the project's Windows Python environment:

```powershell
.\.venv\Scripts\python.exe scripts\build_tiktok_insights_report.py
```

The optional arguments are `--source <analysis-output-folder>` and `--output <new-package-folder>`. Replaying the unchanged inputs verifies the existing package without rewriting it. Changed inputs cannot replace a sealed report; a future analysis requires a separate version.

After the final package revision, all 16 saved-report tests passed. The 25 strongest-post ranking tests also passed during integration. These checks cover integrity, source scope, identifier precision, ranking semantics, and downloads; live dashboard acceptance is recorded separately by the integration verification.
