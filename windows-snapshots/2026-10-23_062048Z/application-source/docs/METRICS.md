# Metric rules

Every dashboard selection keeps platform, account, entity, snapshot, unit, grain, measurement type, timezone and dimensions separate. Source references and definitions are available behind the displayed records. Activity dates, capture dates and import timestamps have different meanings.

| Measurement type | Aggregation rule |
|---|---|
| `period_count` | Sum only compatible, nonoverlapping periods at one entity grain. Incomplete coverage must remain visible. |
| `distinct_count` | Do not sum daily listeners or reach into unique people for a longer period. Obtain that period's unique count directly. |
| `point_in_time` | A balance at an endpoint, such as followers. Show endpoints, not a sum. A difference is net change, not gross acquisitions. |
| `rolling_count` | Overlapping windows, such as monthly listeners. Never add snapshots. |
| `cumulative` | Lifetime/running totals. Do not add them across capture dates or assume a change is clean activity without checking revisions/resets. |
| `rate` | Retain the source definition and denominator. Aggregate only by recomputing from compatible numerator/denominator totals; zero or unavailable denominators produce unavailable results. |

## Loaded Spotify native metrics

| Metric | Unit / measurement |
|---|---|
| `streams` | Count / daily period_count. |
| `saves` | Count / daily period_count; activity, not distinct saving people. |
| `playlist_adds` | Count / daily period_count. |
| `listeners` | Count / daily distinct_count. |
| `followers` | Count / daily endpoint point_in_time. |
| `monthly_listeners` | Count / rolling_count over 28 days. |
| `monthly_active_listeners` | Count / rolling_count over 28 days, intentional listening. |
| `super_listeners` | Count / rolling_count over 28 days, active audience subsegment. |

Spotify source dates use UTC. The original source archive's `analysis/definitions_notes.md`, section 5, records the 28-day audience definitions and links Spotify's primary documentation. Rolling rows preserve their as-of endpoint and inclusive start 27 days earlier. Historical rolling windows can begin before the first exported endpoint; that does not create new daily observations.

The recovered archive uses source-native equivalents such as `distinct_audience_count`, `rolling_window_count`, `point_in_time_count`, `cumulative_count` and `lifetime_count`; these remain nonadditive. Only one compatible daily `period_count` series with an approved additive metric is summed by the dashboard. Recovered rolling rows retain their original endpoint representation; the 28-day start in the older Windows subset is not imposed on recovered data.

Artist totals are separate from track and release breakdowns. The four native track CSVs are only part of the catalog; recovered snapshots include broader but still incomplete histories. Do not add artist totals to tracks, or sum overlapping releases into artist totals. Missing saves or listeners cannot be inferred from stream values. Source-specific corrections and quality limitations stay attached to their evidence.

## Social and comparison limits

Views, impressions, reach, followers and streams are different measures. Do not construct a combined cross-platform audience total. Keep paid and organic populations distinct where known. Content lifetime performance is not daily performance on its publication date. Comparing a newly published post with an older lifetime snapshot needs an explicit age limitation.

The first milestone displays selected metrics and their source records. Missing or incompatible comparisons stay unavailable. A social/streaming association does not establish listener conversion, campaign revenue, ROI or causation. No average-artist benchmark or statistical significance is invented.
