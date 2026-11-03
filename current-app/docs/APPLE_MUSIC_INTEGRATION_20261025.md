# Apple Music integration preparation — October 25, 2026

Status: official-source research and collection plan. No Apple account was opened, export collected, API credential created, dataset imported, or dashboard changed by this preparation. Actual artist identity, account access, export schema, coverage, and values remain unverified.

The first integration should use preserved Apple Music for Artists exports. A genuine export must establish its layout before a native parser or daily comparison is accepted. The contract below describes intended analytical meaning; its internal metric names are **not claimed Apple CSV headers**.

## Confirmed source choices

| Source family | Verified purpose and access boundary | Integration treatment |
|---|---|---|
| Apple Music for Artists | Artist performance analytics. Admins and Analysts can view artist data; a Profile Editor role has a different purpose. [Account roles](https://artists.apple.com/support/1102-manage-access) | Preferred first collection. Confirm the selected artist page and actual export permission in the account. |
| MusicKit / Apple Music API | Playback, catalog information, and authorized users' personal music-library features. [MusicKit](https://developer.apple.com/musickit/), [Apple Music API](https://developer.apple.com/documentation/applemusicapi/) | Catalog IDs may later support reviewed identity mapping. A catalog response or a user's listening history does not establish artist-wide plays or listeners. |
| Music Analytics API | Separate provider analytics product. Apple documents aggregated anonymized plays/listeners; iTunes Connect Legal/Admin users manage access, a Legal user accepts terms, and API keys are generated there. [API access](https://itunespartner.apple.com/music/support/5241-music-analytics-api) | Optional future route. Eligibility, organization access, credentials, and permitted content scope are unverified. No credentials or automation are required for the export-first plan. |
| Provider Sales and Trends / financial reports | Separate operational and financial report families with their own timing and schemas. [Provider reporting](https://itunespartner.apple.com/music/support/5240-reporting-availability) | If supplied later, identify the exact report family and retain it separately from artist-dashboard CSVs. Do not inherit artist-dashboard assumptions. |

Apple's July 6, 2026 announcement expands Music Analytics API Engagement and Overlap endpoints to all Apple Music **label partners**, including audience segmentation. This does not prove an ordinary artist-dashboard account has that access. Do not describe Apple as having no analytics API, and do not promise an automatic connection for this account. [Announcement](https://itunespartner.apple.com/5603-music-analytics-api-access-audience-segmentation)

## Confirmed metric meanings and proposed contract

The definition column is grounded in Apple's [artist analytics guide](https://artists.apple.com/support/1105-understand-your-analytics), except daily listeners and Shazam details, which have their own sources below. The handling column is this project's proposed interpretation rule.

| Source metric / concept | Confirmed meaning | Proposed handling |
|---|---|---|
| Plays | Song playback exceeding 30 seconds; includes Apple Music station plays. | Retain as Apple plays, distinct from other services' streams. Sum only non-overlapping rows with identical entity and dimension scope. |
| Daily Listeners | Unique listeners per day, exposed by hovering the Listeners trend. [Trends](https://artists.apple.com/support/1107-see-your-song-stats-and-listener-trends) | Accept a daily series only when actual dated source evidence establishes it. Never sum daily unique counts into weekly/monthly unique people. |
| Average Daily Listeners | Mean daily unique listeners across the selected interval. | Retain the interval. Recompute a weekly mean only from all seven compatible daily counts; do not substitute an interval-level average for daily values. |
| Shazam Count | Song recognitions by Shazam. [Shazam details](https://artists.apple.com/support/1109-shazam-in-apple-music-for-artists) | Discovery metric, separate from listening and clicks. Do not treat recognitions as distinct people or conversions. |
| Radio Spins | Monitored terrestrial/digital station plays, excluding Apple Music Radio. | Keep separate from Apple Music Plays; do not add the two into a streaming total. Preserve station/geography filters. |
| Song Purchases | iTunes Store song purchases. | Separate count and entity type; no inferred revenue or royalty amount. |
| Album Purchases | iTunes Store album purchases. | Separate from song purchases and plays; no conversion of albums into song-equivalent units. |
| Video Views | Apple Music music-video viewing exceeding 30 seconds. | Separate video entity and metric; do not relabel as song plays. |
| Listening Now | Online playback initiators; a separate real-time view with a 48-hour history and privacy minimum. | Exclude from historical daily ingestion initially. Do not mix concurrent listeners with daily unique counts or interval averages. |

Artist analytics covers primary-artist music. Apple groups song performance across releases and distributor deliveries; playlists in this scope are editorial. [Artist analytics](https://artists.apple.com/support/1105-understand-your-analytics) Consequently, a track-group total and its release variants must not be added together. Capture source IDs and group labels before deciding whether an ISRC or catalog ID represents the same reporting entity.

Shazam can assign an audio match to one version when recordings share audio; its artist-dashboard and app systems update on different schedules. [Shazam details](https://artists.apple.com/support/1109-shazam-in-apple-music-for-artists) Preserve version attribution and source family rather than forcing those totals to agree.

Trends offers Plays, Listeners, Radio Spins, Shazam Count, Song Purchases, Album Purchases, and Video Views, with content, demographic, geography, and station filters. [Trends](https://artists.apple.com/support/1107-see-your-song-stats-and-listener-trends) Places exposes geographic views for listeners, plays, radio spins, and Shazam. [Places](https://artists.apple.com/support/1106-get-a-global-view-of-listeners) These are verified UI capabilities, not proof that every combination is downloadable or that all rows are additive.

## Dates, freshness, history, and privacy

Artist-dashboard dates use UTC, update daily, and can take 48 hours to appear. [Artist analytics](https://artists.apple.com/support/1105-understand-your-analytics) Store `UTC` as reporting context for a verified artist-dashboard report; store retrieval time separately as an actual UTC timestamp. The user's New York clock does not redefine those reporting days.

Preparation rules:

- Record the latest date with source data. Treat the recent delay window as potentially incomplete, not observed zero. The 48-hour documentation is not proof that any particular download is final.
- Inspect date parsing, inclusive bounds, row frequency, missing calendar dates, and any partial final period in the real file. Preserve the literal source date text.
- Ask for the earliest date the actual account permits, but do not promise a universal history start, lifetime coverage, or an unlimited download. No universal artist-dashboard history/retention limit was verified in the support pages reviewed.
- Where source cells are blank, dashed, suppressed, or unavailable, preserve that raw token and an explicit status. Unknown tokens remain unresolved until their meaning is evidenced. Only explicit source zero becomes observed zero.
- Listening Now's privacy minimum is documented, but its numeric cutoff is not given in the artist guide. Do not apply its rule to every historical export. [Artist analytics](https://artists.apple.com/support/1105-understand-your-analytics)
- If provider API data is supplied, retain its own privacy flags and precision. Apple documents demographic-query minimum thresholds and rounding to multiples of 50; do not silently apply this API rule to artist CSV values. [Music Analytics API](https://itunespartner.apple.com/music/support/5241-music-analytics-api)

Provider Sales and Trends differs: Apple documents next-day daily reports, Monday weekly delivery, later monthly/yearly delivery, territory-based reporting time zones, and one-year download retention except indefinite yearly reports. Worldwide agreements use PST/PDT. [Provider reporting](https://itunespartner.apple.com/music/support/5240-reporting-availability) These rules belong to that report family; they do not replace the artist-dashboard UTC/48-hour contract.

## Collection checklist

1. Confirm the artist name and original Apple Music artist-page URL. Record any visible artist ID, account role, account view (artist versus provider/label), and catalog ownership exceptions. Use an existing authorized account; this preparation does not require access changes.
2. Capture the visible date range, metric, aggregation interval, selected song/album/playlist/video, territory, and all other filters before downloading. Capture the display language/locale and reporting context too. This provenance is required even if the export omits it.
3. Download an untouched native catalog CSV. Apple documents **Music → See All**, with the desired date range selected before CSV download. [Download instructions](https://artists.apple.com/support/1105-understand-your-analytics) Preserve its original filename and bytes; do not open and resave the original through Excel.
4. Request artist-level daily Plays and daily Listeners for the widest available matching period. Inspect Trends for a native download option; its availability and layout must be verified in the account. If no daily export exists, report that limitation. Do not fabricate a daily CSV from a catalog-period summary or interpret an average as a dated series.
5. Prioritize song-level play history and a matching catalog summary for reconciliation. Then collect Shazam, purchases, video, radio, playlists, and geography where the account offers useful native evidence. Keep each distinct metric/dimension/period file separately identified.
6. For each file, record actual collection timestamp, original filename, byte length, SHA-256, source URL/page, selected account/entity, date bounds, timezone, scope/filters, export type, and evidence capture reference. Mark any unavailable field unknown rather than filling a plausible value.
7. Retain one matching on-screen total and its scope for each accepted series. Compare the sum or mean appropriate to the source metric; do not force subtotals to equal totals when entity groups overlap, privacy rules apply, or the source has different precision.
8. Stop at a reviewable import preview. Validate the real schema and dates, missing tokens, identity mapping, duplicate keys, overlaps, and raw-to-normalized lineage before any activation. Keep a repeated retrieval as a new capture when historical values change; do not overwrite earlier exports.

The minimum useful handoff is the original catalog CSV, any available artist daily Plays/Listeners exports, the original artist-page URL/ID, and capture evidence of their dates and filters. If only the catalog CSV is obtainable, import preparation can still profile it, but social/spike timeline comparisons remain pending daily evidence.

## File-schema boundary

Confirmed publicly: a date-range-selected full-catalog CSV download exists. The cited artist support pages do **not** provide a versioned file specification establishing exact header names, order, delimiter/encoding, ID fields, date layout, missing-value tokens, row grain, maximum date window, daily-export availability, or the completeness of catalog rows.

Pending real export:

| Question | Required evidence before native mapping |
|---|---|
| Does one row mean a day, a song, a selected-period total, or another grouping? | Literal headers, sample rows, visible report context, and reconciliation. |
| Are listeners daily unique, period unique, or average daily? | Exact source label and selected grain/interval; no name-based guess. |
| Which IDs and grouping levels exist? | Original field values plus reviewed artist/track-group/release mapping. Title-only matching is insufficient. |
| What does an omitted row or empty cell mean? | Source status/help or retained UI evidence. Omission alone does not prove zero activity. |
| Is an apparent total rounded or privacy-limited? | Source precision and status evidence for the actual report family. |
| Does a newer file revise old dates or duplicate them? | Source hashes, complete business keys, capture times, and explicit overlap comparison. |
| Can geography, playlists, releases, or songs be added? | Disjointness and scope evidence. Unique listeners are non-additive across those groups. |

Do not ship a sample file with guessed native headers as an Apple export. If an internal template is provided by the implementation, label it **project canonical input**, and retain a separate reviewed mapping from the genuine Apple file.

## Integration acceptance contract

This is the project recommendation, not an Apple file specification:

- New immutable source namespace and collection identity; retain original source bytes, file hashes, parser version, actual capture time, and source/filter evidence. Existing Spotify, Meta, YouTube, and saved analyses remain unchanged.
- Candidate observations preserve platform, artist/account, entity type and ID/group identity, metric, raw and parsed values, status, reporting date or interval, timezone, unit, dimensions, source scope, file/row lineage, and capture. Scope and interval participate in identity; they are not cosmetic labels.
- Exact replay must add no duplicate observations. Conflicting later captures remain distinguishable. Overlapping date windows, releases, and breakdown reports are never blindly added.
- Series intended for comparison require complete compatible daily evidence. Weekly Apple Plays may be summed across seven complete days; weekly average daily listeners may be averaged across those days. Label both as Apple metrics, preserve UTC alignment, and compare only matching complete periods.
- Keep purchases, Shazam, Radio Spins, videos, and Listening Now outside the plays/listeners total. Do not add Apple and Spotify unique listeners into a cross-service audience count.
- Social alignment is descriptive. Native listening totals do not establish post attribution, click conversion, or campaign lift. A future attribution dataset would need its own verified source and scope.
- Acceptance checks must cover untouched source hashes, parser/schema validation, key uniqueness, explicit missingness, date continuity, source-total reconciliation, exact replay, conflicting-capture handling, and preservation of the existing library. Live activation remains a later implementation step.

## Official sources reviewed

Reviewed October 25, 2026 for this preparation. Exact source URLs are retained here so later implementation can recheck definitions without treating this document as a native export.

- [Understand your analytics](https://artists.apple.com/support/1105-understand-your-analytics) — artist metric meanings, content scope, UTC/freshness, native CSV route.
- [See your song stats and listener trends](https://artists.apple.com/support/1107-see-your-song-stats-and-listener-trends) — activity types, daily listener hover, filters.
- [Get a global view of listeners](https://artists.apple.com/support/1106-get-a-global-view-of-listeners) — geography capabilities.
- [See how Shazam works for artists](https://artists.apple.com/support/1109-shazam-in-apple-music-for-artists) — version attribution and reporting differences.
- [Manage users on your account](https://artists.apple.com/support/1102-manage-access) — artist account roles.
- [MusicKit](https://developer.apple.com/musickit/) and [Apple Music API](https://developer.apple.com/documentation/applemusicapi/) — catalog/library/playback product boundary.
- [Music Analytics API](https://itunespartner.apple.com/music/support/5241-music-analytics-api) — separate provider analytics, access, privacy, limits.
- [Music Analytics API Access and Audience Segmentation](https://itunespartner.apple.com/5603-music-analytics-api-access-audience-segmentation) — July 6, 2026 label-partner rollout.
- [Reporting, Availability, and Charts Eligibility](https://itunespartner.apple.com/music/support/5240-reporting-availability) — provider-report timing, territory clocks, retention.

The provider API's linked [full guide](https://help.apple.com/itc/musicanalyticsapi/) required JavaScript in the web-text reader; endpoint schemas were not independently inspected. The Apple Music API reference also returned a JavaScript-required shell when opened; its scope was cross-checked against Apple's public MusicKit page and indexed official reference summary. No endpoint schema or authenticated access claim depends on those unavailable page bodies.
