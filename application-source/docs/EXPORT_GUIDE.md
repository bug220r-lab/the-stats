Use **Import data** for CSV/XLSX files; choose the actual worksheet and header row, review the mapping, and supply missing metadata. Choose an explicit snapshot before committing. Platform/account identity cannot be inferred from the project title.

| Platform or section | Required source fields |
| --- | --- |
| Spotify artist trends | Daily export with Date, Streams, Listeners and available Saves / Playlist adds / Followers. Supply verified artist ID and source date-bucket timezone if documented. |
| Spotify selected-period listeners | An exact-window total with start/end dates. Daily unique listeners cannot supply a monthly unique total. |
| Spotify tracks/releases | Stable track/release ID, title, metric, date or exact window; retain audio-only or other population definitions. |
| Spotify rolling monthly listeners | Reported rolling window or explicit as-of date, rolling audience definition, capture date and evidence reference. |
| Spotify audiences and geography | Population/segment/country/city dimensions, metric, exact window, count versus percentage unit and denominator. |
| Spotify playlists | Playlist ID, title, reporting bounds, stream count/contribution definition and source reference. Missing reporting bounds block a selected-period KPI. |
| Facebook / Instagram account | Account ID, date/window, reach/impressions/views/followers/profile visits/link clicks, source definitions and capture date. |
| Facebook / Instagram content | Post ID, URL, publish date, title/caption, format, metric window or lifetime designation, paid/organic dimensions. |
| TikTok account/content | Account and video IDs, publish date, view/watch-time/engagement metrics, exact windows or lifetime designation. Use platform `tiktok`. |
| TikTok for Artists | Export or verified manual readings with artist/song ID, exact period, metric definition and evidence. Use platform `tiktok_artists`; do not treat these as TikTok account metrics. |
| Paid campaigns | Campaign ID, period, currency, attribution window/model, paid population, spend and outcome definitions. |
| Collection queue | Export the actual recorded task rows including source status and timestamp. Import through Data & collection → Collection queue. |

For unavailable exports use `templates/manual_readings.csv`. The template has no invented example analytics. One row represents one metric, entity, population and reporting window. Use ISO dates (`YYYY-MM-DD`); `captured_at` can be a date or ISO timestamp with its original offset. Leave unknown capture dates and timezones blank. Keep date-only source buckets intact. Record the evidence URL or local file and row/page in `evidence_ref`. Use `status=available` only when the reading is verified; `missing`, `suppressed`, `unverified` and genuine numeric zero remain distinct.

Use `dimensions` as a JSON object, for example `{"country":"US"}` or `{"distribution":"paid","currency":"USD","attribution_window":"7-day click"}`. Preserve source definitions; do not invent attribution or currency. Counts use `count`; percentages use `percent`; ratios use `ratio`; watch duration needs an explicit unit. Measurement types: `period_count`, `distinct_audience_count`, `cumulative_total`, `point_in_time_count`, `rolling_window_count`, `rate`.

Generic mapping defaults describe the metric's usual semantics. For a lifetime post export, explicitly set its measurement type to `cumulative_total` and its definition/window appropriately. Do not accept a period-count default for lifetime counts. Rates should be recomputed from compatible numerator and denominator totals where available, never averaged across rows. Ambiguous metadata belongs in the issue log until resolved.

No consumer Spotify connection is used to access private artist analytics. Core use needs no API key, paid service or cloud database. No live platform adapter is delivered; exports and verified manual readings are the supported inputs.
