# TikTok Studio collection — @funnyguycrawl

Collected through the authenticated **Jude** Chrome profile during October 26–27, 2026. TikTok for Artists remains **pending by user instruction**. No Business account was created or linked. No TikTok observations were activated in The Stats' live library.

## Collection and verification

**615 of 615 posts verified, with all 1,845 distinct analytics panels saved.** There are 1,846 panel receipts including the preserved/repeated capture, 18 native ZIP exports containing 33 CSV members, and 945 verified images. All post IDs match the inventory, all loaded-panel and caption checks pass, and all ZIPs match the original downloads and pass CRC checks. The acquisition queue remains in progress for identity/mapping reconciliation and deferred Artists data; live integration is not ready.

| Source family | Preserved coverage |
|---|---|
| Owned posts | 615 unique post IDs; native captions, publication displays, post links where exposed, privacy/pinned indicators, duration where displayed, and snapshot counters. Four captionless posts retain explicit missing-caption status and unknown public URLs. |
| Post analytics | Overview, Viewers, and Engagement for each post. Summary watch time, completion, new followers, saves, viewer counts, traffic sources, search queries, and audience breakdowns are retained wherever displayed. Native suppression notices and viewport chart images are preserved. |
| Account activity | Initial native 365-day overview, labeled October 26, 2025–October 25, 2026, plus the seven-day export. A later annual export and custom-day check are preserved separately because their date labels conflict. |
| Viewers and followers | Native 7-, 28-, 60-, and 365-day reports; visible demographics and activity panels. Later annual repeats remain separate snapshots. Follower activity exports contain 168 hourly records for a seven-day window, regardless of the longer history filter. |
| Content rankings | Four ranking views—views, new viewers, likes, new followers—at 7, 28, 60, and 365 days: 16 UI reports. The native content ZIPs contain a top-post subset, not the complete 615-post inventory. |
| Comments | Visible recent Studio comment list and expanded reply groups. 397 repeated row observations produce 50 distinct row fingerprints; these are **not asserted unique comment IDs**. Thirteen expanded-reply snapshots are preserved. The observed date picker exposed about 30 days, not all-time comments. |
| Monetization | Visible 7-, 30-, and 60-day reward summaries. Detailed LIVE access led to a mobile QR handoff and remains unavailable in the desktop collection. |
| Sound identity | 369 public-profile sound-label observations were preserved separately. Sound IDs and recording mappings remain unresolved; a label such as “original sound” does not establish a specific recording. |

## Review gates before integration

- **Date conflicts:** Later Overview and Viewers exports repeat all 365 numeric row vectors in their original order while changing some date labels. The later files duplicate “November 2” and omit “March 8.” The custom October 26 selection exports an “October 25” row. Follower history also changes its daily-difference field. Preserve these snapshots separately; do not append, overwrite, or automatically repair dates. The report timezone is unknown. See `data/collection/tiktok-20261026/evidence/studio-20261027-supplement/date-reconciliation-v2.json`.
- **Signed and missing source values:** The initial overview has 14 negative daily comment cells. The viewer export has a literal `undefined` total at its final row. Preserve these native values; neither is zero. Daily unique viewers are not additive into a period-unique audience.
- **Scope and precision:** Post summary counters are snapshots with native lifetime/stated scope. Ranking-window metrics, “All views,” account daily activity, viewer populations, and follower populations remain separate. Abbreviated counts and percentage bounds retain their raw display text and are not promoted to exact values.
- **Charts and unavailable history:** Saved panel text and viewport images do not constitute exported raw interactive chart series. Some older charts are limited to 365 days after publication, and some retention or comment-insight panels are suppressed. The collection does not assert every historical comment or inaccessible mobile-only data.
- **Identity:** Authenticated access confirms the handle and profile link. Studio did not expose a stable numeric account ID. The historical preparation manifest remains unchanged; collection evidence and the acquisition queue record the later access verification.

The earlier structurally accepted account stage contains **1,460 observations**: 365 days each of video views, profile views, likes, and shares. All daily comments remain in raw source rows but are excluded from that accepted metric stage. This is a preparation artifact, not activation approval; date, identity, and mapping review remain open.

## Files

- Original ZIPs, raw captures, screenshots, and acquisition worksheets: `data/collection/tiktok-20261026/`.
- Reconciled inventory: `outputs/tiktok_collection_20261026/posts-inventory-observed-615.csv` and `.json`.
- Final coverage, per-post summaries, displayed percentage breakdowns, and native export checks: `outputs/tiktok_collection_20261026/audit-final/`.
- Recent-comment observations, content-ranking rows, and public sound labels: `outputs/tiktok_collection_20261026/supporting-index-01/`.
- Final package status and SHA-256 manifest: `data/collection/tiktok-20261026/evidence/collection-results.json` and `collection-file-manifest.json`.

Original failed writes from the earlier full-disk interruption remain preserved and are distinguished from successful resumed captures. A few early images contain JPEG bytes under `.png` filenames; their bytes and hashes are retained, with the mismatch listed in verification. New captures use the matching extension.
