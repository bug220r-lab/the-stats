# Exact 75-Story backfill — October 24, 2026

The user authorized collecting captions and statistics for the exact 75 remaining Instagram Story IDs, starting with August, June and July, and integrating source-qualified context into the dashboard and Spotify spike comparisons without duplicating publications. Root owns browser collection and final activation coordination; source acceptance and comparison checks are independently delegated.

## Collection result

Root's completion receipt is `data/collection/meta-story-backfill-20261024/evidence/browser_collection_complete.json`, at `2026-10-24T21:54:41.566Z`. The final raw source contains exactly 75 target IDs. No additional content identity was collected.

| Source check | Observed result |
|---|---:|
| Exact targeted Story IDs / accepted in-memory observations | 75 / 75 |
| Nonempty native description/caption strings | 17 |
| Native panels displaying no-text state | 58 |
| Native Views-layout panels / observed Views readings | 70 / 70 |
| Native legacy Reach/Impressions-layout panels | 5 |
| Legacy Views readings | Absent, not zero |
| Legacy Impressions readings | 1 observed; 4 unavailable |
| Interactions readings | 72 positive; 3 observed zeros |
| IDs with at least one numeric native metric | 75 |
| In-memory normalization quarantine | 0 |
| Unique retained browser captures | 86 |

All six overview labels remain native, alongside four extra detail fields: Likes, Reactions, Replies and Shares. Normalizer 1.2.0 accepts both layouts without renaming Impressions or filling Views. Its numeric-availability contract accepts Interactions-only evidence and explicit zero. Raw description/preview/account-evidence statuses remain retained; a missing preview does not invent media, a caption, authorship or a metric.

The final raw source SHA is `b91a38586f6adfc24d32237c98a216d3429d81e251ffcd672cc2bbd03255ea8e`. Completed independent source acceptance is retained in `data/collection/meta-story-backfill-20261024/evidence/raw_source_acceptance.json`; its documented AX limits remain explicit. All 271 input files were frozen before normalization; the final freeze contains 275 files, including four new normalized outputs. Normalizer 1.2.0 retained 75 observations with no quarantine.

## Date and scope semantics

Retain the four inherited publication-date conflicts and six additional target conflicts:

- `18065361644212778`, `18094398421729141`: inherited August 27 versus native August 28, 2025.
- `18082221025856155`, `18020021219685532`: inherited August 7 versus native August 8, 2025.
- `18035283224701387`, `17971591925782069`: inherited September 1 versus native September 2, 2025.

No publication timezone is inferred. Both source dates remain visible; single-day publication calculations exclude these six identities. Independent candidate comparison records the exact day/week consequences and Spotify-spike rankings. Lifetime capture metrics may add explanatory context to a Story, but cannot be assigned to a spike's activity window or added across captures/scopes.

Completed comparison confirms all six disputes remain within the same Monday–Sunday week. Weekly publication counts, Spotify daily sources/weekly outcomes and both Streams/listener spike rankings are unchanged. Exact-day eligible inventory falls from 2,022 to 2,016 solely because the six new disputes are excluded; no typed publication is removed.

The independent source audit distinguishes full AX value trees from delta/no-change AX captures. Exact metric/caption checks use the retained native DOM, panel text and labelled rectangles; do not claim every AX file contains every value. Final acceptance will pin the completed evidence set rather than an earlier incremental snapshot.

## Immutable pipeline and preservation

- Active predecessor at preflight: `meta-refresh-20261024`.
- Parent database SHA: `17dd0584462966c9e052bfc855f48fd931dc4288ac028aeb2f34f934e39dd4cd`.
- Verified active key: `meta-story-backfill-20261024`.
- Explicit domain namespace: `social/meta_story_backfill_20261024/`.
- Source root: `data/collection/meta-story-backfill-20261024/`.
- Pipeline root: `data/reconciliation/meta_story_backfill_20261024/`.
- Full preflight SHA: `962404b16fae1ff175c2b69a8d56d7f9a491e2621437297309629d89c2b6f554`; all 12 prior databases and both registries match the baseline.
- Exact retained 75-ID queue SHA: `955f6367eed542fc333f24e6c8a7efc5f591add2e2503ff00eeea287c5b12b43`.
- Both registered YouTube collections' six standalone source files are pinned in `evidence/youtube_source_preservation.json` and must remain unchanged.
- The preceding frozen Meta collection's 356 files matched its immutable inventory at start; proof is `parent_collection_preservation_start.json` in the pipeline root.

The all-75-attempt guards prevent early final statuses, normalization, freeze or staging. Only final reviewed captures are normalized; rejected/incomplete observations remain separately preserved. Builders add a new namespace and retain all predecessor asset bytes and statistical input lineage. Promotion must use `python -m scripts.promote_analysis`; the module form preserves project imports. It checks the full database inventory and coordinates with the YouTube import lock.

## Acceptance and runtime verification

Final raw-source acceptance and independent candidate semantic/storage acceptance passed. Exact receipts are under `data/reconciliation/meta_story_backfill_20261024/acceptance/`; the promotion-compatible receipt is `independent_analysis_audit.json`. It binds the sealed candidate database SHA `f013434eb7f24abc6ff138d9c9e0d02c6f42cec8df52530e8e325513a10f9b2b` and verifies all 12 prior databases, both registry constraints, all six standalone YouTube files, inherited assets/raw bytes, CSV/SQLite parity, ZIP contents, explicit missingness and independent latest-compatible selection.

The accepted staged SQLite candidate is `data/reconciliation/meta_story_backfill_20261024/candidate/staged/analysis.sqlite3`, with 158 parsed tables, now installed byte-identically as the active version. Candidate checks confirm exactly 2,026 typed identities, no new identities, 75 additional observations, 2,994 loaded observations and 2,740 selected captures. All 75 exact targets now have at least one numeric metric; the remaining metricless-identity count is zero, without filling unavailable fields. The prior 1,373-Story inventory is preserved through the exact same typed identities.

Independent comparison passed all 18 checks. Its receipts are `data/reconciliation/meta_story_backfill_20261024/comparison_audit/REPORT.md` and `comparison.json`, with exact per-identity coverage in `backfill_identity_drilldown.csv`, date evidence in `new_publication_date_evidence.csv` and spike-window comparisons in `spike_window_comparison.csv`. Parent analytical/source catalog paths and hashes are unchanged; only the three standard packaging metadata assets use the explicit predecessor namespace.

All 75 targets' numeric metrics and 17 native strings reach spike-context data. Seventy-one targets fall within at least one selectable preceding/selected/following rising-week window; structural eligibility is not an effectiveness ranking. Global text-covered identities remain 1,144 before/after, so the 17 native strings improve capture provenance rather than fill 17 new caption gaps. Observed Views coverage increases by 70 and Reach by 16; Link clicks coverage is unchanged. The complete per-metric coverage changes remain in `comparison.json`.

Root promoted the accepted candidate through `python -m scripts.promote_analysis`. The verified active key is `meta-story-backfill-20261024`, with database SHA `f013434eb7f24abc6ff138d9c9e0d02c6f42cec8df52530e8e325513a10f9b2b` and 158 parsed tables. The original launcher session `75655` was replaced by `82406` for the first acceptance restart, then the final UI restart uses loopback launcher session `63405` at `127.0.0.1:8501`.

Post-restart `verify_activation.py` passed at `2026-10-24T22:07:25.923654+00:00`. Receipt: `data/reconciliation/meta_story_backfill_20261024/activation_verification.json`. After the UI-only newest-first capture sort, verification passed again at `2026-10-24T22:13:11.284423+00:00` in `activation_verification_after_ui_restart.json` in that same directory. Both confirm the acceptance-pinned installed hash, all 12 prior database hashes unchanged, 13 live databases, both YouTube collections and all six standalone source files unchanged, all 275 new frozen collection files and 356 parent collection files unchanged, and earlier archive/analysis registrations preserved. The final presentation change passed 15 focused context/caption/UI tests; it changed no source data.

Live browser verification passed at `2026-10-24T22:14:03.354Z`. Its receipt is `test-results/meta-story-backfill-20261024/browser_verification.json`; final proof is `story-spike-final.dom.txt` and `story-spike-final.png` in the same directory. Earlier `social-inventory.dom.txt`/`.png` and `spike-overview.dom.txt`/`.png` are retained from the first restart.

The final view shows Cross-platform, Streams, week August 4, 2025, with a 1,703-stream increase. Target `18020021219685532` is expanded with native caption “Best band ever,” its original Story link, both source dates `2025-08-07`/`2025-08-08` and the date warning. The newest metric capture appears first. Screenshot spot checks verified Views 114, Likes 5, Reactions 5, Interactions 5 and Shares 0 with `observed_zero` status. These selected visual checks do not claim every rendered metric was visually inspected; the independent source/candidate audits remain the full-data evidence. The spike comparison is descriptive timing context, not an attribution of the 1,703 streams to this Story.

Stakeholder explanation: `docs/META_STORY_BACKFILL_20261024.md`. Detailed commands and review contract: `data/reconciliation/meta_story_backfill_20261024/PIPELINE.md`.
