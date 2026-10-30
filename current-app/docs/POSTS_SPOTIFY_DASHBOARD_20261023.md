# Posts, Stories and Spotify comparison

Open **Cross-platform → Posts & Spotify** in the existing Windows dashboard.
The active `meta-content-20261023` library supports this view. The earlier
account-activity analysis remains under **Account activity · saved analysis**;
older saved libraries retain their original Cross-platform screen.

## Timeline and exploration

- Aligned weekly publishing bars and Spotify activity, with optional release markers.
- Reviewed 2024–2025, available 2026, all Spotify history and custom date windows.
- Facebook posts, Instagram Stories, and optional incomplete Instagram feed history.
- Streams, average daily listeners, saves, playlist additions and net new followers.
- Same-week and following-week descriptive correlations of adjacent weekly changes.
- Week and caption/ID/link drill-down, with post text, retained publication dates,
  date-conflict flags and original links where supplied.
- Filtered weekly activity, calendar-aligned pairs and inspected content CSV downloads.

Each publication is counted once by platform, verified account identity and post ID.
Positive native band-author evidence can coexist with an unknown-author capture;
affirmative associated/other/collaboration authorship remains excluded. Conflicting
days count only when their week is unambiguous. Lifetime engagement is never
allocated to publication weeks. The existing Social content library retains those
capture metrics separately.

Only complete Monday–Sunday Spotify weeks entirely inside the selected period are
used. Streams, saves and playlist additions are summed; daily listeners are averaged,
not treated as weekly unique people. Net followers use seven consecutive daily
stock differences, including the preceding day's balance. Missing days and values
stay unavailable. Calendar reindexing prevents charts and lag calculations from
bridging missing weeks.

Publishing counts are unavailable outside each series' retained publication bounds,
including partial edge weeks. Interior zeros mean zero retained publications only.
The per-series status fields are included in weekly CSV exports, and the content
drill-down uses exactly the available publishing bins shown. Facebook Stories are
unavailable; older Instagram feed coverage and 2026 archive continuity remain
incomplete. No deferred Story audio mapping was changed.

## Reviewed analysis

The separate Reviewed results tab uses the immutable analysis in
`data/analysis/social_spotify_20261023`. It preserves the fixed 104-week window,
306 Facebook posts, 594 Instagram Stories and full 20-comparison testing family.
It displays four-week block-bootstrap pointwise intervals, BH-adjusted p-values,
annual subsets and release-window sensitivity for the selected Spotify outcome.
All comparisons and further sensitivity results remain downloadable.

Saved inference is withheld unless all six input asset hashes match the selected
library, and reviewed method/result hashes match the independent verification
receipt. Custom filter selections compute descriptive coefficients only; they do
not reuse saved intervals or rerun significance testing. These associations do not
estimate causal lift or post-to-stream conversion.

## Implementation and verification

- Pure measurements: `stats_app/analysis_correlation.py`.
- Native Streamlit/Plotly view: `stats_app/analysis_correlation_ui.py`.
- Existing Cross-platform dispatch: `stats_app/analysis_ui.py`.
- New tests: `tests/test_analysis_correlation.py` and
  `tests/test_analysis_correlation_ui.py`.
- Source checkpoint: `data/analysis/social_spotify_20261023/dashboard_checkpoint/`.
- Execution and browser receipt: `data/analysis/social_spotify_20261023/dashboard_verification.json`.

No source database or registered library version is edited by this feature.
The Windows launcher must be restarted after code changes because its file watcher
is disabled. The feature does not create a refresh schedule or contact platform APIs.
