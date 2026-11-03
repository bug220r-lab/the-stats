# TikTok integration preparation — October 25, 2026

Status: official-source research and collection checklist. No TikTok account, native export, performance values, credentials, or connection were accessed. Source identity, actual access, file layouts, history, and report clocks remain to be verified from a genuine export. This document changes no dashboard or stored dataset.

## Keep three analytical families separate

| Family | Officially documented capability | Required boundary |
|---|---|---|
| Artist song/sound performance | TikTok for Artists updates daily and reports views, posts, and creator engagements per track. Its post reporting includes views, likes, comments, shares, and completion; follower insights include self-declared demographic information. [Artist launch](https://newsroom.tiktok.com/tiktok-for-artists?lang=en-GB) | Song-associated community activity is distinct from the artist account's own posts. Do not call sound views music streams, unique listeners, or Spotify/Apple conversions. |
| Artist-owned account and content | TikTok Studio separates Overview, Content, Viewers, and Followers, with individual-post metrics and account/audience insights. [Studio](https://support.tiktok.com/en/using-tiktok/creating-videos/tiktok-studio) | Confirm post ownership and account identity. Retain captions, original post URLs/IDs, publication evidence, and each metric's actual scope. Viewer demographics and follower demographics are different populations. |
| Business-account analytics | Web Business Suite documents downloadable Overview and Audience data with 7/28/60-day or custom windows; its Video section lists content for selected windows. [Business Suite](https://ads.tiktok.com/resources/help/article/navigate-web-business-suite?lang=en) | This page does not establish a daily row grain, native CSV headers, or a downloadable video inventory. Record the actual file and selected report. Do not substitute Ads Manager or leads exports. |

TikTok for Artists supports certified Artist Accounts and team access; this account's eligibility and music mapping are not yet checked. [Artist launch](https://newsroom.tiktok.com/tiktok-for-artists?lang=en-GB) Do not change the account type or request access merely to prepare the importer.

## Metric contract for the first files

These are analytical concepts, **not invented TikTok export headers**. Exact native labels and units must survive mapping.

| Concept to collect | Interpretation and acceptance rule |
|---|---|
| Song-associated posts / sound uses | Preserve the source track/sound identity, metric name, and window. Do not assume a per-track post count equals unique creators, original recordings, or only posts made by the artist. A title match does not prove that an unofficial/original sound belongs to the same recording. |
| Song-associated views and creator engagements | Keep separate from owned-post metrics. The public launch confirms these metric categories but does not specify creator-engagement arithmetic, deduplication, detailed view counting, or sound-version rollup rules. Await actual definitions/evidence. |
| Owned-post views, likes, comments, shares, saves | Preserve each available counter. Views are not proven unique people. Do not create a composite engagement metric or count missing saves as zero. Organic, paid, and combined scope must remain explicit or unknown. |
| Total watch time, average watch time, completion/retention | Preserve units, denominator, interval, and the actual label. An average or percentage is non-additive; never sum it across posts. Do not infer seconds from a duration string or scale a fraction to percent without evidenced mapping. |
| Viewers and reach | Keep unique/returning/new-viewer labels distinct from repeated views and follower counts. Preserve the interval and population; do not sum unique audiences across posts or days. Exact Studio definitions remain subject to the actual source. |
| Followers | Separate a total at capture, new follows, lost follows, and net change. A current total cannot supply historical daily growth. Do not label new follows as net follows unless the source establishes that meaning. |
| Captions, IDs, links, dates | Capture the full native description when available, plus an explicit empty/unavailable/truncated status. Keep IDs as text. Retain the original URL and raw publication date/time without deriving a timezone from the computer clock or an ID. |

TikTok's separate **TikTok One project reporting** documents total watch time as accumulated viewing time, average view time as play time divided by views, and completion as completed views divided by views. It distinguishes paid from organic delivery and supports CSV/XLSX/ZIP report exports. [TikTok One reporting](https://ads.tiktok.com/resources/help/article/about-tiktok-one-campaign-reporting?lang=en) These verified definitions belong to that product: do not automatically apply its denominators, export format, or update schedule to Studio, Business Suite, or artist-song reports.

## API and consumer-data boundaries

- [Display API](https://developers.tiktok.com/docs/en/display-api-overview) exposes authorized profile/public-video information. Its [Video Object](https://developers.tiktok.com/docs/en/tiktok-api-v2-video-object) documents IDs, a UTC publication epoch, share links, description, duration, and views/likes/comments/shares counters. That schema does not list watch time, completion, private audience breakdowns, or artist-wide sound performance. Its API fields are not proof of native CSV headers or historical daily counts; description length limits also prevent assuming a complete native caption.
- [API for Business](https://ads.tiktok.com/resources/help/article/marketing-api?lang=en) explicitly includes an Organic API with Accounts and other services. Therefore, do not claim TikTok has no account-insights API or that Display API is the only possible route. Access, permissions, eligible account types, exact endpoint metric semantics, and this user's entitlement are unverified. The preparation remains native-export-first; no API is connected.
- [Research Tools](https://developers.tiktok.com/docs/en/research-api-faq) are not a general commercial creator-analytics substitute: TikTok's FAQ excludes creators, advertisers, and commercial users from that route.
- Consumer watch history, screen time, a personal data archive, public trend/chart counts, and catalog/search results do not establish artist-owned performance or a complete community-use history. Ads, Shop, LIVE gifts, Creator Rewards, campaign revenue, and attribution reports need separate explicitly identified datasets if requested later.

## Collect this first

1. Record the actual account's handle, original profile URL, stable account ID if supplied, account/report type, locale, and the artist/catalog identity. Confirm which report families are actually available without changing account settings.
2. Obtain untouched native files for **account trends** and **owned-post performance** first. Preserve original filenames and bytes. Use a short recent range for schema validation, then collect the widest useful history the native picker permits. Capture screenshots/text of selected dates, filters, grain, clock/timezone, and any scope or freshness notices.
3. Include post IDs/URLs, captions, publication dates, sound IDs/URLs where offered, and available views/engagement/watch metrics. If the export omits these, retain the missingness and provide corresponding native post-detail evidence; do not invent identifiers or fetch substitute statistics from an unofficial scraper.
4. If TikTok for Artists is available, collect song/sound summaries and any native dated trend exports separately. Preserve each track/sound mapping and the artist-versus-community population. A daily dashboard refresh does not prove the downloaded file contains one row per day.
5. Collect audience/follower breakdowns only with their report period, population, percentages/counts, and source privacy annotations. No universal demographic threshold or unmodelled-demographics guarantee was verified for these three families.
6. Record each file's SHA-256, size, original filename, actual retrieval timestamp, source page, selected account, date bounds, metric/scope, timezone evidence, source-status tokens, and capture reference. Keep a later download as another dated capture rather than overwriting an earlier export.

The minimum useful handoff is one untouched native analytics file, one owned-post inventory/performance file if offered, the original profile URL, and evidence of dates and filters. Song-performance integration additionally needs real artist-song evidence; it cannot be reconstructed from the account's own post totals.

## What remains unverified

| Item | Import requirement |
|---|---|
| Native CSV/XLSX layout | Inspect literal headers, encoding, delimiter, date format, row grain, identifier fields, units, and status tokens. No production parser should depend on guessed native headers. |
| Lifetime versus daily versus selected-period values | Record the actual measurement window on every observation. Never distribute a lifetime total across days or turn a current total into activity on its publication date. |
| Timezone and latency | Verify each report family's clock and latest completed date in the actual source. The Display API's UTC publication epoch does not establish the analytics reporting timezone. Do not copy Apple's UTC/48-hour rule into TikTok. |
| History, download limits, and completeness | Read the actual picker, export notice, and coverage. Business Suite's documented preset/custom windows are not a universal retention guarantee. Do not promise every older, private, deleted, Story, photo, or video record. |
| Privacy and missing cells | Preserve blank, N/A, unavailable, suppressed, and explicit zero separately. Unknown availability or a missing row does not prove zero. |
| Organic versus paid | Preserve evidenced scope. If a source does not explain promotion inclusion, mark it unknown; do not relabel all account views organic. |
| Song/sound identity | Retain distinct sound IDs, versions, original sounds, and mappings. Review equivalence before combining uses or views. |

Some primary documentation could not be fully read in this research tool: the English [Creator Academy analytics article](https://www.tiktok.com/creator-academy/en/article/tool-analytics-intro) returned only its navigation shell; detailed download/missing-data FAQ pages and the [Business API endpoint page](https://business-api.tiktok.com/portal/docs?id=1762228421622786) were unreadable. Consequently, commonly repeated numeric history limits, timezone exceptions, processing delays, privacy cutoffs, and native header lists are **not promoted to verified requirements here**. Studio capabilities were cross-checked against TikTok's indexed English support content. No authenticated screens or exports were examined.

## Acceptance before dashboard integration

Use a separate immutable TikTok collection/namespace. Retain raw source hashes and row lineage; existing Apple preparation, Spotify, Meta, YouTube, and historical analyses stay intact. Exact replay adds no duplicate observations; later captures and conflicting scopes remain distinguishable.

Require reviewed account/post/sound identity, exact units and scope, no guessed missing values, duplicate/overlap checks, and reconciliation against a matching native total. Accept daily comparisons only when genuinely dated daily evidence and compatible reporting days exist. Lifetime post stats can describe posts around a Spotify increase, but cannot establish what those views were during that increase or attribute listening to TikTok.

## Primary references

Reviewed October 25, 2026. All substantive platform claims above use official TikTok sources; third-party search results were used only to discover primary URLs.

- [TikTok for Artists announcement](https://newsroom.tiktok.com/tiktok-for-artists?lang=en-GB) — artist metrics, daily refresh, access.
- [TikTok Studio](https://support.tiktok.com/en/using-tiktok/creating-videos/tiktok-studio) — account/content/viewer/follower families; direct text retrieval limited as described above.
- [Web Business Suite](https://ads.tiktok.com/resources/help/article/navigate-web-business-suite?lang=en) — current downloadable account/audience analytics and date selectors.
- [TikTok One reporting](https://ads.tiktok.com/resources/help/article/about-tiktok-one-campaign-reporting?lang=en) — explicitly scoped watch/completion definitions and export formats.
- [Display API](https://developers.tiktok.com/docs/en/display-api-overview) and [Video Object](https://developers.tiktok.com/docs/en/tiktok-api-v2-video-object) — metadata/counter boundary.
- [API for Business](https://ads.tiktok.com/resources/help/article/marketing-api?lang=en) — distinct Organic API capability.
- [Research API FAQ](https://developers.tiktok.com/docs/en/research-api-faq) — access restrictions.
