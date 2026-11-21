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

