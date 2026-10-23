# Metric dictionary and calculation contract

`stats/metrics.py` is the shared calculation layer for displayed KPIs, daily charts, comparisons and deterministic Markdown summaries. Raw record downloads retain the same filtered canonical observations; they are observations with provenance, not an instruction to add every row together.

The dictionary supplies conservative canonical descriptions. An imported source's explicit definition and measurement type take precedence. A source-reported lifetime view count must be imported as `cumulative_total`, even though a dated views export can contain `period_count`. Unknown units, populations and windows must be resolved during preview rather than guessed.

## Platform-native metrics

| Metric | Default type | Unit | Definition and aggregation |
| --- | --- | --- | --- |
| `streams` | Period count | count | Spotify or another explicitly identified source's qualifying stream events. Sum only disjoint complete reporting windows. TikTok for Artists song activity remains a different platform/population. |
| `listeners` | Distinct audience count | count | Unique listeners within the source's precise window. Never sum daily listeners into weekly/monthly listeners. |
| `monthly_listeners` | Rolling window count | count | Platform-reported rolling monthly audience, distinct from a selected calendar period. Never add rolling snapshots. Preserve the actual reported window. |
| `monthly_active_listeners` | Rolling window count | count | Source-reported active listeners within the rolling window. Retain the source's definition of intentional/active listening. |
| `super_listeners` | Rolling window count | count | Source-reported highly active audience within the rolling window. Retain the source's threshold; do not invent one. |
| `followers` | Point-in-time count | count | Reported follower balance. Use the latest reported balance in the selection, with its actual date. Never add balances. |
| `new_followers` | Period count | count | Newly acquired followers during the source window. This is different from the follower balance or net follower change. |
| `saves` | Period count | count | Save actions in the specified window. Not necessarily unique people. Lifetime saves require a cumulative type. |
| `playlist_adds` | Period count | count | Playlist additions in the specified window under the source's counting definition. |
| `views`, `video_views` | Period count | count | Source-defined views in a reporting window. Platform thresholds and replay rules differ. Lifetime content snapshots require a cumulative type. |
| `reach` | Distinct audience count | count | Distinct accounts or people reached in the exact source population and window. Never sum overlapping periods, segments, posts or platforms. |
| `impressions` | Period count | count | Source-defined displays, which may include repeat displays. Not distinct people. |
| `likes`, `comments`, `shares` | Period count | count | Source-defined actions in the reporting window. Lifetime content snapshots require a cumulative type. |
| `watch_time` | Period count | seconds | Total viewing duration. If the source unit is minutes/hours, retain that unit explicitly or use a documented conversion at import. Average watch time requires a rate/average measurement, not an additive total. |
| `profile_visits` | Period count | count | Visits reported by the source, not necessarily distinct visitors. |
| `link_clicks` | Period count | count | Click events under the source's specified click definition. Keep outbound, all-link and attribution-specific definitions distinct. |
| `engagements` | Period count | count | Source-defined engagement actions. The exact included action types belong in the definition. Do not automatically add likes/comments/shares to a reported engagement total. |
| `spend` | Period count | currency | Advertising spend in the reporting window. Currency and attribution settings must be retained in dimensions. Different currencies are incompatible. |
| `engagement_rate` | Rate | percent | A source-reported rate requiring its denominator in the source definition. Never sum or average rates without their compatible base totals. |
| `streams_per_listener` | Derived ratio | ratio | Stream events / distinct listeners for the same source population and window. This is frequency, not conversion. |
| `saves_per_listener` | Derived ratio | ratio | Save actions / distinct listeners for the same population and window. Not unique-person conversion. |

Definitions also depend on platform, account, entity and dimensions. Facebook, Instagram, TikTok account analytics, TikTok for Artists and Spotify are separate measurement populations even when metric names match. Names alone never establish identity.

## Supported measurement types

- `period_count`: additive events or durations within explicitly bounded periods, only when those periods are disjoint and cover every day in the requested range.
- `distinct_audience_count`: exact-window audiences only. Daily or segment counts cannot establish the union of people.
- `point_in_time_count`: a reported balance as of a date. The latest observed point may be shown with its actual date; no interpolation or addition.
- `rolling_window_count`: one explicitly reported rolling window. Daily display dates do not turn a rolling audience into daily unique listeners.
- `cumulative_total`: a source-defined lifetime count at capture. One exact observation can be displayed; it cannot be added to other snapshots or compared as equal-exposure period performance.
- `rate`: an explicitly defined reported ratio/percentage. One exact observation can be displayed. Recomputed rates use compatible raw totals; reported rates are not summed or simply averaged.

## Selection and overlap rules

One KPI requires a single platform, account ID, entity type and ID, dimensions, definition, unit, measurement type and snapshot. An artist/account total and track/post breakdown cannot be added together. Paid/organic categories, countries, currencies and audience segments remain separate unless the source provides an authoritative combined observation. Dimensions JSON is canonicalized for key order; malformed JSON blocks calculations.

An exact observation for the full requested window takes precedence over its daily or other constituent rows. Otherwise, a complete daily partition can supply the total while coarser summaries are excluded; coverage reports how many coarser rows were ignored. Identical copies of the same period collapse to one measurement with all source references retained. Conflicting values for the same period are unavailable until active versions are resolved by storage. Other overlapping intervals are never added. A period partly outside the selected window is not prorated.

If disjoint count observations cover only part of the requested period, the KPI is unavailable. `partial_value` is exposed only as a clearly labelled partial count, and coverage records expected/observed days and the missing dates. Genuine numeric zeros remain zeros. Missing, suppressed, rejected, ambiguous, invalid and unverified observations are unavailable; infinity and nonnumeric values are unavailable.

Source date buckets are retained without timezone conversion. Different source timezones, or a mix of known and unknown timezones within one calculation, block combination. Two unknown timezones remain explicitly unknown; a chart aligns source date labels, not verified simultaneous instants.

## Ratios and comparisons

`derived_ratio` computes `numerator / denominator × multiplier`, normally multiplier 1 for a ratio or 100 for a percentage. Both inputs must produce available complete totals, use identical platform/account/entity/dimensions, snapshot, date window and source timezone, and be period counts or exact distinct audiences. A zero/negative denominator is unavailable. Engagements/reach and engagements/impressions are different ratios and must be labelled with their denominator.

`compare_metrics(..., mode="revision")` requires the identical historical reporting window in two different identified snapshots. It describes a data revision, not new performance. Baseline selection is controlled by immutable snapshot storage; later files cannot redefine the original October 20 membership.

`compare_metrics(..., mode="performance")` requires equal-length nonoverlapping reporting windows and equivalent definitions, units, populations and measurement types. Cumulative lifetime totals are refused because content exposure is not established. A zero earlier value allows an absolute difference but never a fabricated percentage change. Point balances compare reported dates and are balance changes, not acquired-follower counts.

## Charts, indexing and exploratory association

`daily_series` uses only explicit one-day observations marked daily/day/date when a time grain is supplied. It keeps a daily grid with NaN gaps and never splits a period total into invented daily values. Rolling audiences, lifetime totals and reported rates do not become daily activity series. An authoritative period KPI can differ from a visible daily breakdown; its sources and aggregation method explain that distinction.

`asof_series` provides a separate trend for source-reported balances, rolling audiences and lifetime observations. Each point is plotted at its reporting end/as-of date while the original reported start and end remain in the returned table. Missing points remain gaps. Its `daily=False` metadata makes it ineligible for daily lag correlation. An export containing only an as-of date does not establish a reconstructed rolling reporting window.

`indexed_series` starts at 100 on the first date with a nonzero observed value in every selected series. Earlier indices and missing values stay missing. The returned table always retains absolute values; zero starts are skipped, and if no valid common date exists the index is unavailable.

`lag_correlation` computes Pearson correlation only for pairs with observed daily values. It defaults to 30 matched days, permits a configurable minimum of at least 3, reports the sample size and matched date ranges, and does not fill gaps. A positive lag means **left(t) is compared with right(t + lag)**: the left series leads the right. Inputs must retain a daily grid, source timezones must agree (or both remain unknown), and constant series are unavailable. Different native units are allowed for association and remain labelled; they are never added together.

Correlation is exploratory. Trends, seasonality, common causes and selection of a lag can affect it. It does not establish attribution, listener conversion, revenue or ROI. No artist benchmark or percentile is calculated without a suitable documented comparison dataset.

## Public API

```python
filter_observations(df, start=None, end=None, platforms=None, accounts=None, entity_type=None)
aggregate_metric(df, metric, start=None, end=None)
derived_ratio(df, numerator, denominator, start=None, end=None, multiplier=1.0)
daily_series(df, metric, start=None, end=None)
asof_series(df, metric, start=None, end=None)
compare_metrics(current, previous, metric, mode="performance", start=None, end=None,
                previous_start=None, previous_end=None)
indexed_series({"label": daily_dataframe})
lag_correlation(left_daily_dataframe, right_daily_dataframe, lag=0, min_observations=30)
summarize_results({"KPI label": calculation_result})
```

Aggregate results contain `value`, `partial_value`, `reason`, `unit`, `definition`, `measurement_type`, `period_start`, `period_end`, `sources`, `snapshot`, `snapshot_name`, `scope`, `source_timezone` and `coverage`. `None` means unavailable; UI code must not use `value or 0`. Series contain `date,value`; indexed series contain `date,series,value,index`. DataFrame `attrs` retain explanatory reasons and the index reference date. Summary prose is deterministic and based on these same calculation results.
