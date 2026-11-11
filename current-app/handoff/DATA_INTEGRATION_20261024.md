# October 24: current coverage and retained-data integration

The user authorized a first pass to correct outdated coverage notices, update Social and Decision content summaries to the expanded posts/Stories inventory, and surface Spotify audience evidence already retained. This extends the existing local Streamlit application and preserves its compact navigation/header/spike layout.

## Result

- **Data quality and Coverage & cross-reference** lead with coverage calculated from the selected immutable analysis. The repaired Instagram follows series is counted from actual complete numeric dates. Old assessment/readiness prose and snapshot issues remain explicitly historical; selecting an older version does not claim newer repairs.
- **Sources & provenance** identifies the selected analysis and its retained asset catalog separately from local/handoff imports. The historical October 23 inventory is labelled as predating expanded content.
- **Social → Content & publishing** uses the expanded library when present, including Stories by default. Publication cadence counts typed platform/account/post identities once, excluding unknown/conflicting dates. Capture outcomes remain in collapsed detail with account, scope, measurement, capture-day, metric and age controls. Older versions keep their inherited view and qualify its Story warnings.
- **Decision report → Content** uses the same expanded identity/capture logic. The active library contains 2,026 identities, including 1,373 Stories and 197 identities lacking numeric metrics in every retained capture. Numerical descriptions keep measurement types, metric scopes, authorship and capture-day groups distinct. Source receipts include all contributing content tables and verified identity bridges. The report schema is 1.1.0.
- **Spotify → Audience & sources → Audience segments** exposes the retained 28-day segment history, separate rolling super-listener history, and source-defined audience movement counts. Definitions and exact source/download records stay in collapsed detail. The Artist history metric menu also offers rolling super listeners.
- **Overview** uses the separately recovered direct 2025 listener total only when artist, population, dates and timezone exactly match its requested comparison. The matching prior-year YTD view now compares 9,419 listeners with 3,077; the incompatible native previous reading remains preserved in provenance. Decision's preceding-equal-period comparison retains its own date rules.

## Interpretation and source boundaries

No platform collection, import, analysis promotion or source-package rewrite is part of this pass. Raw lifetime captures are not added together or assigned to publication-day activity. Groups can contain overlapping identities across distinct metric scopes and must not be added. Numeric unknowns stay unavailable; observed zeros remain numeric. Historical statistical families keep their original inputs.

Selection of latest captures and conflict status is computed against full retained platform history before Social presentation filters. An old caption match cannot promote an older metric. Filtering one side of a same-time dispute cannot resolve that conflict. Four active identities with conflicting known publication dates remain visible as evidence but do not contribute publication cadence or age summaries.

The Spotify segment and super-listener series are audience stocks/overlapping windows, not additive daily activity. Movement categories can overlap and do not reconcile additively to audience growth. Conflicted release-engagement cohorts were not promoted to topline metrics in this pass.

The YouTube parent and daily supplement remain separate collections. The coverage view identifies the registered supplement without altering the parent's historical 243-date coverage or filling native blanks.

## Files

Shared transformations: `stats_app/content_summaries.py`, `stats_app/spotify_audience.py`, `stats_app/analysis_coverage.py`.

Presentation/report wiring: `stats_app/analysis_social_ui.py`, `stats_app/decision_report.py`, `stats_app/decision_ui.py`, `stats_app/analysis_spotify_audience_ui.py`, `stats_app/analysis_ui.py`, `stats_app/ui.py`. The shared `analysis_ui_common.chart` accepts optional layout overrides; the new segment chart places its legend above the plot to avoid narrow-screen date-label collisions. Other chart defaults are unchanged.

Focused regressions: `tests/test_content_summaries.py`, `tests/test_spotify_audience.py`, `tests/test_current_coverage.py`; existing Decision and legacy-search checks were adjusted for explicit source scope.

## Verification

The combined affected suite passed 77 tests before the final Social filtering-order regressions were added. The final Social/coverage/legacy subset passed 27 tests, and the final Spotify/shared-chart/backward-compatibility subset passed 16 tests. Browser observations, screenshots and unchanged source hashes are recorded in `test-results/data-integration-20261024/verification.json`. These runs overlap and must not be added as unique-test counts.

The real loopback launcher was restarted because file watching is disabled. Its first sandboxed start could not open the existing AppData library; restarting with the authorized existing-library access restored the running application. Live browser checks covered current Data quality, expanded Social and Decision content, sources/provenance, coverage/history, exact matching YTD audience, and the new Spotify audience view at desktop and 520-pixel widths. The viewport was restored and the audience page left open. Source packages remained unchanged; no collection or import was performed. See the receipt for exact checks and limitations.

The October 24 collection audit remains historical evidence of the pre-integration application. Its `AUDIT.md` and source packages were not rewritten to describe these later changes.
