# TikTok collection runbook — October 26, 2026

The Stats is being prepared to connect discovery, content engagement, music listening, and commerce questions for **[REDACTED]**. The collection target is the user-supplied profile [@funnyguycrawl](https://www.tiktok.com/@funnyguycrawl). That URL identifies the requested target; account ownership, stable account ID, analytics access, and artist/catalog association remain unverified.

This is preparation. No TikTok performance data has been collected or imported, and no TikTok account or API has been connected by this workflow. Empty worksheets and mapping templates are not observations. Keep the original October 20 baseline designation and all existing source collections unchanged.

Use the [existing collection research](TIKTOK_INTEGRATION_20261025.md), [CSV inspection and staging instructions](TIKTOK_PREPARATION.md), and [metric definitions](METRICS.md) alongside this runbook. Implementation and validation results belong in the current handoff; commands below describe the intended operating procedure and do not themselves establish a successful collection or import.

## Prepare the collection workspace

Run from the project folder in PowerShell. Initialize only a new directory; if the dated workspace already exists, inspect it with `status` instead of replacing it.

```powershell
.\.venv\Scripts\python.exe scripts\manage_tiktok_collection.py init --output data\collection\tiktok-20261026 --profile-url 'https://www.tiktok.com/@funnyguycrawl' --prepared-on 2026-10-26
.\.venv\Scripts\python.exe scripts\manage_tiktok_collection.py status --collection data\collection\tiktok-20261026
```

For a saved status receipt, choose a new output filename outside the source-evidence directory:

```powershell
New-Item -ItemType Directory -Path outputs\tiktok_readiness_20261026 -Force | Out-Null
.\.venv\Scripts\python.exe scripts\manage_tiktok_collection.py status --collection data\collection\tiktok-20261026 --output outputs\tiktok_readiness_20261026\readiness-01.json
```

| Collection item | Purpose |
|---|---|
| `collection.json` | Preparation identity, readiness state, and planned snapshot ages. A supplied handle is not proof of account access. |
| `collection_queue.csv` | Resumable checks, outcomes, limitations, and evidence references. |
| `post_log.csv` | Header-only worksheet for verified post identity, publication evidence, and content/song notes. No posts are claimed by the scaffold. |
| `snapshot_schedule.csv` | Header-only worksheet for proposed capture timing and actual snapshot evidence; it does not schedule an automated job. |
| `config/` | Copies of the existing mapping, metadata, and sound/recording crosswalk templates for review. |
| `raw/` | Untouched original source files; retain original filenames and separate repeated downloads. |
| `evidence/` | Report selections, definition/clock notices, identity evidence, and new receipts. |
| `stages/` | A new subdirectory for every reviewed file/staging attempt. |

Keep configuration separate for each source file and report family. The initial copies are `account_daily.mapping.json`, `video_snapshot.mapping.json`, `song_daily.mapping.json`, corresponding `.metadata.json` files, and `sound_recording_crosswalk.csv`. The templates use The Stats' internal contract, not verified TikTok export headers. Metadata retains `user_supplied_unverified` identity status until source identity is reviewed.

A readiness receipt inventories preparation evidence; it is not proof that a source is authentic, complete, or ready for live-library activation. Its states are `preparation_only`, `collection_in_progress`, and `needs_review`; `integration_ready` remains false. Even a fully populated queue still requires native evidence review.

## Collect three source families separately

| Source family | First collection request | Boundary |
|---|---|---|
| **TikTok Studio** (`studio_csv`) | Owned-account trends, owned-post inventory/performance, and available viewer/follower reports. Start with one short recent report to establish its actual layout, then retain the widest useful available history. | Studio distinguishes account, content, viewer, and follower analytics. Tool availability differs between app/web and regions. Record the actual selected surface; do not assume every metric is downloadable. [TikTok Studio](https://support.tiktok.com/en/using-tiktok/creating-videos/tiktok-studio), [creator tools](https://support.tiktok.com/en/using-tiktok/creating-videos/creator-tools-on-tiktok) |
| **TikTok for Artists** (`artists_csv`) | Available song/sound summaries and genuine dated trends, plus native track identifiers and catalog evidence. | Daily-updated dashboards include track views, posts, and creator engagements. Song-associated activity across creators is a separate population from the band's own posts. A daily dashboard update does not establish daily rows in an export. [Artist platform](https://newsroom.tiktok.com/tiktok-for-artists?lang=en-GB) |
| **Web Business Suite** (`business_suite_csv`) | If this account already has access, retain downloaded Overview/Audience reports and observed video coverage separately. | Official documentation describes downloadable Overview/Audience data and selected report windows; it does not establish universal CSV headers or a downloadable full video inventory. Preserve overlap with Studio rather than adding their counts. [Business Suite](https://ads.tiktok.com/resources/help/article/navigate-web-business-suite?lang=en) |

TikTok for Artists requires a certified Artist Account in a supported registered country; the US is included. This profile's eligibility is unverified. Check access before treating artist reports as available; changing account type, certifying an account, or inviting a team is outside preparation. [Artist eligibility](https://artists.tiktok.com/help-center/eligible-users)

Audience breakdowns, creator-engagement definitions, paid/Promote, Ads, Shop, LIVE, and revenue can be retained as source evidence when available, but their metrics need a reviewed mapping before integration. The existing first-pass adapter does not implement every documented TikTok metric. See [supported metrics and units](TIKTOK_PREPARATION.md#metric-and-unit-rules).

## Complete the collection checklist

1. **Verify identity and access.** Record the selected profile, handle, stable account ID when supplied, account/report type, locale, and the account shown on the analytics page. Save bounded evidence of the selected account. Do not infer ownership from a public profile or the supplied URL alone.
2. **Record report context before download.** Capture exact inclusive start/end dates, selected filters, row grain, metric labels/units, population, organic/paid/combined scope, source clock, and completeness/processing notices. Mark unverified values unknown.
3. **Preserve originals.** Retain original filename, bytes, size, SHA-256, source URL/surface, actual collection timestamp with offset, and evidence references. Keep each later download as a separate capture. A derived CSV must retain a link to the untouched original and its transformation; XLSX/ZIP/JSON needs a verified conversion or adapter.
4. **Record coverage honestly.** Use exact queue statuses: `not_collected`, `collected`, `partial`, `verified_empty`, `unavailable`, `blocked`, or `not_applicable`. `collected` has evidence for the requested scope; `partial` states the missing portion. `verified_empty` requires a successfully checked scope with explicit empty evidence. `unavailable` means the source does not expose the requested data; `blocked` records an access or technical obstacle. Unchecked work stays `not_collected`; `not_applicable` is for optional items only. None of these outcomes supplies a numeric zero.
5. **Reconcile the first file.** Inspect literal headers and a bounded sample, review definitions, and compare a matching native total where the metric is additive. Record any mismatch. A follower balance, unique audience, rate, or average cannot be reconciled by blindly summing rows.
6. **Resume by queue item.** Preserve completed evidence; retry blocked/partial work in a new capture and note what changed. Do not erase a failed attempt or convert “not collected” to “unavailable” without an actual check.

The queue requires account identity, daily account activity, owned posts, sound mapping, and reconciliation; song/community activity and audience reports are optional acquisition lanes. `collected`, `partial`, and `verified_empty` require an existing evidence reference contained within the collection directory. An evidence file's presence does not establish its authenticity or semantic correctness. If the native source cannot provide daily rows, record that limitation; never manufacture daily data to satisfy the queue.

Keep three clocks distinct: publication time, reporting-window time, and retrieval/capture time. Preserve the source's timezone or explicit unknown status. A UTC API publication timestamp does not establish the analytics report timezone. A collection made today may describe older activity; current lifetime totals cannot be assigned to publication day. No universal history limit, export schema, latency rule, or reporting timezone was verified for this account.

## Record posts, songs, and equal-age snapshots

For each verified owned post, retain its ID as text, original permalink, native caption and caption availability, publication timestamp as supplied, duration when available, sound ID/URL/title, and any source-supported song or campaign context. Preserve unknown song, hook, format, CTA, destination, and paid status rather than inventing classifications. The [campaign metadata workflow](CAMPAIGNS.md) and [post/song/event mapping](POST_SONG_EVENT_MAPPING.md) explain existing metadata boundaries.

For future posts, target captures at approximately **24 hours, 72 hours, 7 days, and 28 days after publication**. These are recommended comparison ages, not a promise of TikTok historical availability. Retain the planned time, actual capture timestamp, actual post age, and source reporting lag. If publication time or its offset is unknown, leave exact age unknown; do not manufacture a backdated snapshot for an older post. The schedule worksheet is a collection aid, not a running automation.

Review the copied sound/recording crosswalk before joining to music outcomes. Preserve distinct TikTok song IDs, sound IDs, original sounds, recording versions, ISRCs, Spotify track IDs, and Apple song/group IDs, with relationship, verification status, and evidence. A matching title or caption alone does not prove the same recording. Do not roll up multiple sounds or distribute community usage to owned posts until the relationship and counting boundaries are established.

## Inspect, preview, and stage the first native file

After replacing the example path with a genuine CSV, use the established preparation tool. Make reviewed per-file copies of metadata and the appropriate mapping under `config/`; remove unsupported or absent mappings and replace placeholder headers with exact source labels.

```powershell
$tiktokCollection = 'data\collection\tiktok-20261026'
$tiktokExport = Join-Path $tiktokCollection 'raw\original-export.csv'
.\.venv\Scripts\python.exe scripts\prepare_tiktok.py inspect --input $tiktokExport --output (Join-Path $tiktokCollection 'evidence\schema-01.json')
.\.venv\Scripts\python.exe scripts\prepare_tiktok.py preview --input $tiktokExport --mapping (Join-Path $tiktokCollection 'config\mapping-01.json') --metadata (Join-Path $tiktokCollection 'config\metadata-01.json') --output (Join-Path $tiktokCollection 'evidence\preview-01.json')
.\.venv\Scripts\python.exe scripts\prepare_tiktok.py stage --input $tiktokExport --mapping (Join-Path $tiktokCollection 'config\mapping-01.json') --metadata (Join-Path $tiktokCollection 'config\metadata-01.json') --output (Join-Path $tiktokCollection 'stages\stage-01')
```

Review `accepted`, `canonical_import_eligible`, issues, lineage, and retained semantics. Accepted review evidence can still be ineligible for canonical import; neither flag authorizes activation. Use `--compare-observations` against an earlier stage when applicable to expose replay, conflict, or overlap without merging rows. Full option and scope details are in [TikTok preparation](TIKTOK_PREPARATION.md#preview-compare-and-stage).

Before live integration, require verified source identity and ownership scope, native-file reconciliation, reviewed units/definitions, preserved blanks/suppression/zeros, sound mapping where needed, overlap/replay review, and a separate immutable collection. Keep staging and library activation distinct. No parser pass alone establishes completeness, causality, or equivalence between platforms.

## Three first measurement priorities for the wider suite

These are measurement questions and candidate KPIs. There are no TikTok performance values, validated targets, or claimed results yet.

| Priority and decision | Candidate KPI concept | Required evidence and guardrail |
|---|---|---|
| **1. Discovery: which posts and songs are gaining exposure?** | Owned-post views at a comparable capture age; separately, artist-reported song-associated posts/views over matched periods. | Compare the same metric, content population, age/window, and delivery scope. Views are not unique people or music streams. Community use and owned-post performance remain separate. |
| **2. Engagement: which creative sustains attention and prompts response?** | Source-reported completion/average watch time, with available shares and saves considered separately. | Preserve units, denominator, post duration, and capture age. Do not invent a composite engagement score, treat missing saves as zero, or average rates without valid weights. Use comparable post cohorts before drawing content recommendations. |
| **3. Listening and commerce: what downstream activity accompanies promotion?** | Parallel matched-window readings of song streams/listeners/saves, measured outbound destination clicks, and Shopify orders/net sales where available. | Verify song/destination/campaign identity and each platform's reporting clock and status. Retain Spotify, Apple, Linktree, and Shopify as separate outcomes; a click is not a confirmed listen or purchase. No inferred attribution or combined cross-platform audience total. |

Select complete comparable windows only after checking source coverage and clocks. Keep daily versus aggregate Apple snapshots separate, do not add overlapping collections, and preserve Spotify's baseline uncertainty. Document release, playlist, show, posting, and paid-promotion context when explaining changes. Association across windows is descriptive; it does not establish that TikTok caused listening or sales. See [decision workflow](DECISION_WORKFLOW.md), [Apple integration](APPLE_MUSIC_INTEGRATION_20261025.md), and [Shopify scope](SHOPIFY.md).

## Future connection boundary

Native export and documented manual evidence are the initial collection route. The Display API offers authorized profile/video information and documented video counters, but its video object does not list watch time, completion, private audience breakdowns, or artist-wide sound usage; it also requires developer/product approvals and account authorization. [Display setup](https://developers.tiktok.com/docs/en/display-api-get-started), [video fields](https://developers.tiktok.com/docs/en/tiktok-api-v2-video-object)

API for Business includes a separate Organic API with account-insight capabilities; this account's entitlement and endpoint semantics remain unverified. Research Tools are not the ordinary creator/commercial-analytics route. [API for Business](https://ads.tiktok.com/resources/help/article/marketing-api?lang=en), [Research FAQ](https://developers.tiktok.com/docs/en/research-api-faq)

The personal “Download your data” archive includes account/activity information and may omit the latest data in some categories. It is a different source from a native analytics report, and unrelated personal activity is not needed for this collection. [Requesting your data](https://support.tiktok.com/en/account-and-privacy/personalized-ads-and-data/requesting-your-data)

Official-source review date: October 26, 2026. Some Help Center content was available only through indexed official text; Creator Academy and authenticated analytics/export screens were not verified. Capture actual account capabilities, file layouts, limits, and report definitions during collection instead of assuming a generic export contract.
