# Dashboard and collection handoff

Prepared October 22, 2026 for Lewis. This is a data contract for a future dashboard; no dashboard is built in this task.

## Verified entities and versions

The band name displayed by the sources is **[REDACTED]**. This is the source's literal artist name. The Stats™️ is the project name.

| Platform | Verified identity | Key |
|---|---|---|
| Spotify | [REDACTED] | Artist `6X14XfGTmB560PF063wXDk` |
| Facebook | Redacted OH, `@redactedbandoh` | Page `100091779409539` |
| Instagram | [REDACTED], `@redactedbandoh` | Account `17841454335424545` |
| TikTok | No verified analytics identity in retained evidence | Unavailable |

The original Spotify reporting cutoff is October 20, 2026. A cutoff is not a retrieval timestamp. Later Spotify supplements and October 22 Meta captures remain distinct retrieval vintages. Filter both the activity/reporting window and the snapshot class. Never backdate current follower stocks or lifetime post outcomes to the original baseline.

## Ready tables and aggregation contract

| Table | Grain/key and valid uses | Required caveat |
|---|---|---|
| `spotify/cleaned/artist_daily.csv` | Artist/date in the retained baseline. Sum streams, saves and playlist additions over complete intervals. Plot daily unique listeners as daily values. | Daily listeners do not sum to weekly people. Followers are a stock; differences are net change. Rolling measures require their explicit window bounds and cannot be summed. |
| `spotify/cleaned/artist_period_dashboard.csv` | Artist/metric/reporting period/retrieval. Use directly reported period-unique listeners and compatible period ratios. | Preserve displayed precision. Streams per listener is an aggregate activity ratio, not a repeat-listener or conversion rate. |
| `spotify/cleaned/track_daily_long.csv` | Recording ID/date/metric/retrieval vintage, with source-row lineage. Sum additive stream counts within verified complete coverage. Join `recordings.csv` many-to-one by `song_id`. | Same-title recordings retain distinct IDs. Six of 70 recording-metric histories are incomplete. Artist totals must not be repeated across tracks and then summed. |
| `spotify/cleaned/track_28day_comparison.csv` | One recording per equal-window comparison. Ready for catalog contribution and change. | All 14 tracks reconcile to the artist for these windows. This does not make tracks independent experiments. |
| `spotify/cleaned/recording_launch_windows.csv` | Recording/age window, requiring completeness. | Includes release calendar date; exact release time is unavailable. Release eras, audience size and promotion differ. |
| Spotify audience, country, city, playlist and stream-source tables | Entity/dimension/reporting period/retrieval; use the dictionary's per-table keys. | Top lists may be incomplete. Source parents and children overlap. Listener counts can overlap across categories. Do not add them into unique audience. Demographic displayed totals disagree slightly. |
| `social/account_daily.csv` | Selected account/platform scope/metric/date; canonical retrieval with lineage. Sum complete observed additive daily metrics; retain coverage count. | Pacific source dates. October 21 is partial. Keep 128 missing Instagram Follows cells null. Selected Instagram Views is **combined Facebook + Instagram**, not Instagram-only. |
| `social/account_daily_snapshots.csv` | Daily key plus retrieval/source; all source observations. | Overlapping exports are snapshots of the same activity, not additional activity. Canonical selection is documented in the cleaning log. |
| `social/posts_latest.csv` | Platform/post ID, latest structurally valid snapshot. Browse lifetime performance, post age and author scope. | Label lifetime as captured October 22 UTC. Separate band-authored content, verified collaborations and other-author associations. The 126 valid Stories are an incomplete selected subset. |
| `social/post_snapshots.csv`, `post_metrics_all_snapshots.csv` | Post/retrieval/source and, for the long metrics table, metric. Preserve historical snapshots. | Never sum snapshots or assign lifetime engagement to publication date. Current data cannot establish fixed-age format winners. |
| `social/publication_counts.csv` | Platform/post type/author scope/month. Count retained publication events; daily publication dates are in `posts_latest.csv`. | Counts describe the exported inventory; deleted/omitted content is unknown. October is partial. No lifetime performance is allocated to a publication date. |
| `social/audience_snapshots.csv` | Account/dimension/category/retrieval. Display reported percentages. | Lifetime-labelled audience distribution; top categories, not an exhaustive partition. Do not reconstruct exact counts from rounded percentages. |
| `social/manual_period_and_current_snapshots.csv` | Account/metric/reporting period/retrieval. Reconcile matching native periods. | Rounded strings stay rounded and numeric value may be null. Stocks and interval activity remain separate. |
| `cross_platform/*weekly_complete.csv` | Account/metric/nominal Monday–Sunday week with exactly seven observed dates. | Meta Pacific and Spotify UTC bins still differ. Only additive activity is used. These are exploratory analysis views, not attribution metrics. |
| `cross_platform/joined_week_pairs.csv` | Analysis ID/week pair. Each test is a separate view of reused weeks. | Do not pool the 12 test views as independent samples. Lag 1 means social week t with Spotify week t+1. |

All metric definitions, formulas, raw representations and valid aggregation rules are in `data_dictionary.csv`; domain dictionaries retain details. Use the cleaned data's actual keys and enforce uniqueness before every join. A missing CI or p-value means unavailable or not justified, never zero.

## Default dashboard behavior

1. Show activity window, retrieval vintage, timezone, platform scope, unit and coverage beside each metric. Compare equal, nonoverlapping complete windows.
2. Filter partial days/months by default; allow an explicit partial-period view with a visible label. Do not interpolate missing performance into zero.
3. Make stocks, interval activity, unique audience, rolling values and lifetime snapshots distinct metric classes. Block invalid aggregation in code.
4. Keep band-authored posts and collaborations separately selectable. Show post age and paid-status availability. No paid/organic split is supported where the export does not establish it.
5. Offer source file/row provenance and data-quality notes. Preserve genuine spikes. Show small starting values alongside percent changes.
6. Use cross-platform associations only in an exploratory analysis panel, with all planned tests and adjusted results visible. Do not label aggregate ratios as streaming conversion.

## Smallest additional data that would improve decisions

| Priority | Missing evidence | Minimum useful collection | Decision unlocked |
|---|---|---|---|
| 1 | Comparable content age, topic/song and paid status | For each new post: stable ID, publication timestamp/timezone, format, topic, Spotify recording ID, paid/organic flag, and outcomes at 24 hours and 7×24 hours | Fairer format/creative comparisons; see `MEASUREMENT_PLAN.md` |
| 2 | Marketing route and campaign context | A unique tagged destination link per post/campaign; time-stamped click counts, target recording, campaign/paid/show/playlist/release dates | Describe measured traffic and examine plausible lags; actual listening attribution needs a verified downstream link |
| 3 | Incomplete Instagram observations | Re-export malformed Stories with checked schema and missing Follows dates, or obtain the platform's explicit omission rule | Complete Story summaries and interpretable daily follower activity |
| 4 | Incomplete music history | Full available GOOMH! histories for all five metrics and older Son! streams; recheck all-time headers against identical scopes | Longer catalog comparisons and resolution of lifetime discrepancies |
| 5 | Paid and TikTok coverage | Ads Manager daily spend/impressions/placement/post mappings; verified TikTok Studio identity, timezone, native daily and post exports | Paid/organic separation and TikTok analysis; current Ad Center observation covers only its limited view |

## Future snapshot protocol

- Save every export as a new dated retrieval. Store its untouched bytes and SHA-256; never replace the October 20 baseline.
- Record source/account ID, native file, source URL, exact retrieval timestamp in UTC, source timezone, requested reporting start/end, actual coverage, metric scope/definition version and snapshot class.
- Keep activity date separate from reporting-window start/end, lifetime as-of timestamp, retrieval timestamp and historical-revision flag. Retain both old and revised historical values.
- Retain raw value text and a precision/status field: exact, rounded, zero, missing, suppressed, unavailable or not applicable. Do not infer omission means zero without source documentation.
- Validate export schema, record count, candidate-key uniqueness and overlap before ingestion. Save quarantined raw records and a reason rather than guessing column placement.
- Collect a concise event register: event ID/type/start/end/timezone, linked song/post/campaign IDs, paid spend and evidence link. Mark uncertain mappings instead of using title similarity as proof.
- Reconcile additive daily totals with matching reported periods, assess partial days and track gaps, and retain the resulting check log.

The collection queue currently has 43 entries: 3 complete, 22 partial, 9 blocked and 9 open. Update it only after validating actual files; its status does not establish analytical readiness.
