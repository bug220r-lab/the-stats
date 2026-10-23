# Source audit — October 23, 2026

This audit verifies the current stored source evidence before implementation. Source inputs and registered immutable databases were read only. It accompanies `data/reconciliation/decision_20261023_source_audit.json`, which contains per-source SHA-256 hashes, schemas/coverage and calculation evidence.

## Current source authority

Active analysis is **instagram-story-owner-20261023**, SHA-256 `5aa85bb3efa84a8a759ecf544414a5c067b9f25b9cf4a886a45d3385b0e344ef`. Six registered analysis versions remain separate. The live registry supersedes the stale audio-review handoff. The literal band name is **[REDACTED]**; The Stats™️ is the analytics project. Spotify artist `6X14XfGTmB560PF063wXDk`; Instagram `@redactedbandoh` / `17841454335424545`; Facebook **Redacted OH**, Page `100091779409539` (MBS asset `118246571240106` is distinct); YouTube **[REDACTED] TV**, `@redactedbandoh`, `UCkSoRiC9Pz9hEbJOOTYaq_w`. No verified TikTok account/export is available.

Historical Spotify activity ends October 20, 2026. The source collection occurred October 22–23. Original October 20 collection membership remains **unverified**, including rows whose inherited internal label says `original_baseline`. Reporting endpoint, label and later recollection are not proof of original snapshot membership.

## Collection claims checked

- Current 43-row Spotify queue recomputes to **36 complete, 5 partial, 2 blocked**.
- **765 source comparisons and 25,633 daily source rows are continuation additions.** Current cumulative tables contain **1,269 comparisons and37,311 daily source rows**.
- The 16 passing workbook checks are a retained prior live-read receipt, captured 2026-10-23 03:14:10 UTC. They were not rerun here. Root separately reports current connected queue 36/5/2 and 22 initial reconciliation rows with zero differences; that bounded read is not a rerun of all 16 historical checks.
- The preserved independent input audit records 297 source-stream reconciliations: 252 matches and 45 unavailable table cells with explicit zero chart histories. It preserves 54 duplicate comparison agreements and 1,516 duplicate daily agreements. These audit counts are not independent statistical observations.
- Seven partial/blocked queue items concern Lab Tapes ¡La Cocaína! source metrics, Method Acting(album)/Son!/THIS MACHINE playlist windows, Waste Away playlists, expanded country source scope, and native download failures.

## Available analytical coverage

| Source | Coverage | Meaning and limits |
| --- | --- | --- |
| Spotify artist history | Jan 1, 2024–Oct 20, 2026; 1,024 dates | UTC. Add streams, saves, playlist adds; followers are stocks; audience counts and rolling windows are nonadditive. |
| Spotify recording history |14 recordings × 5 metrics × 1,024 dates =71,680 rows | Same-title recordings retain distinct IDs. Daily listener counts are not period unique listeners. |
| Facebook/Instagram inherited history | Jan 1–Oct 21, 2026; 294 nominal dates per metric | Pacific dates; partial Oct 21 excluded from complete comparisons. Instagram selected-account views explicitly include Facebook+Instagram. |
| Repaired Instagram follows | Jan1–Oct 20, 2026;293 observed dates | Dedicated supplement; 15 vs 15 follow events in latest/prior 28 days. Not net follower growth; do not append to inherited series. |
| YouTube source ZIP | Annual Oct 22, 2025–Oct 21, 2026; historicalOct21,2025–Oct 20, 2026 |365 views/engaged-view dates. Most other daily metrics 243 reported dates; preserve missing values and traffic filters. |
| Content |377 retained social posts, 6 reviewed owner Stories; 27 YouTube videos | Mixed-age lifetime snapshots; no equivalent-age social post histories. 19 regular YouTube videos and 8 Shorts. |

YouTube original ZIP was freshly hashed and inspected at the path in the structured audit; SHA-256 `33da7c508f443ebc883a6c2f86425d1284917526ea5ba1cbbe7f1e0ad08ba6ef`. Root reported Windows access denied for the live YouTube database. These package findings therefore establish source availability, not successful runtime database access.

The owner Story supplement verifies **six archive identities, zero songs and four third-party source-post links**. No native music label was displayed; no listening or fingerprinting was performed. Absence of a visible label does not prove silence. Links establish meme provenance, not Spotify destinations or soundtrack use.

## Supported findings

### Spotify Depth — descriptive

Sep 23–Oct 20 Spotify streams increased 235 (+5.86%) to 4,246 while distinct listeners decreased 59 (-5.26%) to 1,062; intensity 3.998 vs 3.578. Followers 1,616→1,644 (+28).

Period: 2026-09-23/2026-10-20 vs2026-08-26/2026-09-22 UTC. Evidence: `spotify/cleaned/artist_daily.csv`, `spotify/cleaned/artist_period_dashboard.csv`, `raw/spotify_baseline/raw/artist_timeline_2024-01-01_2026-10-20.csv`, `raw/spotify_baseline/captured/period_metrics.json`.

Limitation: More streams per period listener establishes listening intensity, not individual returning-listener retention. Exact descriptive source totals, no sampling CI.

Next action: Pair listening-depth work with discovery-focused content; monitor period unique listeners separately.

### Songs — descriptive

Funny Guy leads current demand: 1,488 streams, 35.04% of 4,246 artist streams, 624 period listeners, 70 save actions; streams down 24 from 1,512. Waste Away rose 33 to190 (+21.0%) with 54 listeners and 3.519 streams/listener.

Period: 2026-09-23/2026-10-20 vs2026-08-26/2026-09-22 UTC. Evidence: `spotify/cleaned/track_28day_comparison.csv`, `spotify/cleaned/track_28day_activity_ratios.csv`, `spotify/cleaned/track_daily_long.csv`.

Limitation: Recording IDs remain separate. Small listener count for Waste Away; exposure and promotion differ. Save actions/listeners is not unique-saver conversion.

Next action: Use Funny Guy as established-demand reference and test a Waste Away excerpt in a matched content experiment.

### Instagram Follows — descriptive

Resolved Instagram follow-event series has 293 observed dates Jan 1–Oct 20; recent 28-day and prior 28-day totals both 15.

Period: 2026-09-23/2026-10-20 vs2026-08-26/2026-09-22 Pacific Time. Evidence: `social/meta_collection/follows_daily_resolved.csv`.

Limitation: Follow events are not net follower-stock growth. Inherited analysis tables still show missing follows; dedicated repair is the current evidence.

Next action: Use repaired series for prospective baseline and collect follower totals/unfollows before claiming net growth.

### Geography — descriptive

United States 777 of 1,062 period listeners (73.16%) ; 637 active US listeners. Top displayed cities Cleveland 24, Columbus 23, Akron 23.

Period: 2026-09-23/2026-10-20 UTC. Evidence: `spotify/cleaned/audience_top_countries.csv`, `spotify/cleaned/audience_top_cities.csv`.

Limitation: Top 23 countries/top 50 cities are displayed coverage, not exhaustive partitions. Locations do not establish ticket demand or combined demographic cohorts.

Next action: Investigate Ohio opportunities with show history and repeated location measurements.

### Youtube Scope — descriptive

Channel-owned annual unfiltered source total is 10,548 views and 6,334 engaged views, with full 365-day coverage for these two series; most other daily metrics have 243 reported dates.

Period: 2025-10-22/2026-10-21 America/Los_Angeles. Evidence: `normalized/channel_period.csv`, `normalized/channel_daily.csv`, `normalized/daily_coverage.csv`, `extracted/annual_date_full/Table data.csv`.

Limitation: Original ZIP verified. Live YouTube DB was inaccessible to root audit (Windows access denied), so source-package inspection is not runtime verification. Views and engaged views differ; package records additional 2026 definition markers. Channel filtered traffic totals must not be added to unfiltered totals.

Next action: Use engaged views and native attention measures for comparable content testing; complete missing daily exports after owner authentication.

## Calculation readback

Raw Spotify timeline records 998–1025 and 970–997 reproduce current/prior streams 4,246/4,011, saves 217/129 and playlist additions 362/366. Cleaned artist values and the sum of distinct recording stream rows match exactly for both windows. Median daily streams are 146 vs 139.5; interquartile ranges 133.25–169.5 vs 128.5–158.25. These are descriptive variation summaries, not confidence intervals. Platform-reported period unique listeners supply 1,062/1,121; they were not constructed from daily sums. Follower stocks at Sep 22/Oct 20 are 1,616/1,644.

Content format summaries already retain medians and counts, but the mixed post ages and differing exposure prevent a causal format ranking. Existing cross-platform screens retain their original cleaned-20261022 input lineage; repaired follows, owner Stories and YouTube do not retroactively strengthen those statistics.

## Missing inputs

- **Original October 20 baseline membership:** Original dated archive or manifest linking exact source bytes to collection on October20; reporting endpoint alone is insufficient.
- **Six October Story song attributions:** Native music label tied to exact Story identity, or original Story audio with reliable identification. No audio listening/fingerprinting performed.
- **Causal social-to-Spotify conversion:** Prospective tagged post/campaign log, measured landing/outbound actions, reliable song identity and sufficiently repeated comparable events; platform attribution/cohort evidence for stream conversion.
- **First-week social content performance:** Metrics snapshots at equivalent post ages (e.g. 7 days), with paid/organic and account scopes. Current mixed-age lifetime totals do not supply first-week outcomes.
- **Instagram net follower growth:** Comparable follower stocks or daily follows plus unfollows; repaired follows are gross events.
- **YouTube other daily metrics:** Four blocked supplemental daily exports: watch time, average view duration, subscribers gained, subscribers lost. Owner passkey verification pending in source evidence.
- **TikTok:** Verified account ID and dated native exports; no verified TikTok collection available.
- **Exhaustive geography/demographic joint segment:** Complete unsuppressed partitions or actual joint dimensions; top-N and marginal distributions are insufficient.

## Official definitions checked on October 23, 2026

- [Spotify listeners, followers and timezone](https://support.spotify.com/us/artists/article/understanding-your-listener-and-follower-stats/): Listeners are unique within the selected period; followers are profile followers. Spotify reporting uses UTC. Do not sum daily or per-song audiences to create artist period unique listeners.
- [Spotify audience segments](https://support.spotify.com/us/artists/article/audience-segments-on-spotify/): Monthly active listeners intentionally stream from active sources in 28 days. Super listeners have 15+ intentional streams; moderate 3–14; light 1–2. These definitions do not turn streams/listener into repeat-person retention.
- [YouTube Shorts view definitions](https://support.google.com/youtube/answer/10059070?hl=en): Since 2025-03-31 Shorts views include starts/replays without minimum watch time; engaged views retains the earlier continued-watching measure. Applicable to collected 2026 Shorts; other package 2026 markers remain separately sourced.
- [Forecasting Principles and Practice: time-series regression](https://otexts.com/fpp3/regression.html): Check trends, seasonality, residual autocorrelation, influential observations and spurious regression. Predictor selection and repeated testing affect inference; observational correlation is not causation.
- [NIST autocorrelation](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35c.htm): Autocorrelation compares a series with its lagged values and assumes equally spaced observations. Dependent daily rows cannot be treated as independent samples; missing dates need explicit handling.
- [Google Analytics campaign URL parameters](https://support.google.com/analytics/answer/10917952?hl=en): Use utm_source, utm_medium, utm_campaign consistently; utm_content distinguishes creatives. Parameters identify referred traffic in Analytics, not downstream Spotify listening.

These official pages agree with the metric interpretation used above. The Shorts change explicitly predates the 2026 observations. Undated current documentation does not alone certify historic definitions for every earlier collection. Package-specific 2026 YouTube definition markers remain source-qualified.

## Source hashes

The structured companion contains hashes for every input below; hash validation occurs on repository read. Exact paths refer to retained package assets,not files to replace.

| Container | Asset | SHA-256 |
| --- | --- | --- |
| active_analysis | `spotify/cleaned/current_queue.csv` | `0aa239c3e5b1b588e37b9f943b57e299bca23a4f52af461849047f9bf21a7d6b` |
| active_analysis | `spotify/cleaned/artist_daily.csv` | `99d6893eb304d695f5ecf5e9499e59a10f34f7a9766f87c5d82297802d018858` |
| active_analysis | `spotify/cleaned/artist_period_dashboard.csv` | `021b41fe9ff43768ca5ff85acea7b1ced52e73ee264e19c60d24e43d9e091d20` |
| active_analysis | `spotify/cleaned/track_daily_long.csv` | `818a0986a808442cffcaf4cd0e110bd1b69c40c4574647d016f6ce54c62f226e` |
| active_analysis | `spotify/cleaned/track_28day_comparison.csv` | `0c6172f362f542a9b4d18687d8ab61642a2dccc4c9327ac084d784057f0c27d8` |
| active_analysis | `spotify/cleaned/track_28day_activity_ratios.csv` | `68291d8e58269ce74ae47cb867e4c1befbff7afbed97c3963567bc77c92207fe` |
| active_analysis | `spotify/cleaned/recording_launch_windows.csv` | `2e694cb2af423500bd8c61d4a4ae4e4bc07561cd8a89235ae2d0ff30b8ccc162` |
| active_analysis | `spotify/cleaned/audience_top_countries.csv` | `7440878231c916e5e2340f429b793502585a1131c1795eafbb194f22d412b126` |
| active_analysis | `spotify/cleaned/audience_top_cities.csv` | `8c29746388066905ec7276857a4d1d0ead1f57af5fb317b2eac14ccca5a08c6e` |
| active_analysis | `spotify/cleaned/source_recovery.csv` | `83a456f0679fbf5ac46cd161f727485e441937110750db2ec144ecc235bd3ed9` |
| active_analysis | `spotify/cleaned/source_history.csv` | `197e1bb0c0e05b2fae802e8567b285b19299d88be3768493caf4fe8be2a77341` |
| active_analysis | `spotify/cleaned/source_stream_reconciliation.csv` | `7aadf30fd5eca49c26fbb99df747721382ed6cb52b34d21406691e5d3ab87068` |
| active_analysis | `social/account_daily.csv` | `808ee6b5935bde800334a53c1d119d1b4c6f02400f2eda6caa09b6ffcab9fd55` |
| active_analysis | `social/account_period_comparisons.csv` | `c74b4aa6c730c0f25074d37f706c044b52843c28d99178a07469f8dd1e8b9bb0` |
| active_analysis | `social/content_format_summary.csv` | `3d3f12f0dc4c5335049471b2b610f9ebc8616db71416a8ed8ae98bf2bff6134c` |
| active_analysis | `social/meta_collection/follows_daily_resolved.csv` | `da66982888542772b93b305f24ed258bb89a3e941c63751fddd6f2c3bdfbe53d` |
| active_analysis | `social/meta_collection/facebook_daily_recheck.csv` | `2e63d1ce46ede23119fd694257bbeb5cf58adb898b27b2c71e981533d77feafe` |
| active_analysis | `social/instagram_story_owner_20261023/story_owner_review.csv` | `d3e21881caa0ddeecad3cc7d24da60bada00ead85ffb50e25ff06e83758b7b21` |
| active_analysis | `social/instagram_story_owner_20261023/story_source_links.csv` | `751f0a5348f27a754961d0438049ffb6e6eff7f182f0aafe57451fb1e7a0d459` |
| active_analysis | `cross_platform/statistical_results.csv` | `e740c71b698b932286eb6a80363e7c815d3cedeefef29ca39b1cda59858643ee` |
| active_analysis | `raw/spotify_baseline/raw/artist_timeline_2024-01-01_2026-10-20.csv` | `6b4f56d8d9fc7d4ae93e06157b6a4cb1ea0d978094bb72d49ffdceb02377eebe` |
| active_analysis | `raw/spotify_baseline/captured/period_metrics.json` | `2ece8bdc540dabdfae3fc0b7de846c1ce8b98f5610b9f484de1a3a836bf76ea9` |
| active_analysis | `raw/spotify_baseline/captured/song_3QVtuSBGLC9fTmLfF6qP7Z_28day.txt` | `c25fde97b887fda840024c56c12196b33eba451388a6041f428889cc532ba6f4` |
| active_analysis | `raw/recovery_evidence/continuation/manifest.json` | `0466b89c3e5c8e758a52418eaf3ee975413cf22ba80b9464a3e8fbfa8f072703` |
| active_analysis | `raw/recovery_evidence/continuation/normalized/added_source_collection.csv` | `b2e2fde3cf718cbd036a1866a14154312469d596de1af189b6755f903ab8f52c` |
| active_analysis | `raw/recovery_evidence/continuation/normalized/added_source_daily_collection.csv` | `c3b6d40f22a3ed75e6c4af56d4b599cae4f1c512f57a444f46b683087bf349bc` |
| active_analysis | `audit/workbook_audit.json` | `c8c0896e481a1fe320aff3fdde9dc6fd7c930ee408e2213787d8916f812c5300` |
| active_analysis | `audit/independent_input_audit.json` | `0f33f6f31be42a74b5e7aa520c27df58bf44afb80092b4b02aa05fe0f7d1954d` |
| active_analysis | `raw/meta/meta_account_identity_evidence.json` | `fe5a05b86da0c8cc7f4672a27fc5361b6ee30a3fe791f4821abcfb51a7e68418` |
| youtube_original_zip | `normalized/channel_period.csv` | `c392d33eb2cd4d6bd109e461ceabe11372a57de883171e7feb8993578bc27429` |
| youtube_original_zip | `normalized/channel_daily.csv` | `fb33cfd4fa84a84fbd0fc4488b79f92d998491de7162cc72c077d198f1215f8c` |
| youtube_original_zip | `normalized/daily_coverage.csv` | `c9e9cfdfaaaa3314e15fb20ef68aa9a968e074b8705297dc3faa7adf61ea089b` |
| youtube_original_zip | `normalized/collection_status.csv` | `39dd6c502fef9abb9ec5d69be6de93ff990b38aa768e3784389cfe7112eef734` |
| youtube_original_zip | `normalized/video_inventory.csv` | `86adc47a9be2dad1ada66ac5d9fb4e94d88806e699df2f76060235be077b0ab3` |
| youtube_original_zip | `normalized/video_song_mapping.csv` | `d938f665d8a55e32fd7aeb025605c89ef6f8ce34b2a116ac24d76b2c91dd9faa` |
| youtube_original_zip | `normalized/metric_dictionary.csv` | `70577243aae64ee854a4dc5383ed34d0f2ebb2760a7f073f7d700afdf71dc5cb` |
| youtube_original_zip | `extracted/annual_date_full/Table data.csv` | `5432842ba13515384202088aaea6bf7175ab4a31876271cfde143e114aa37e36` |
