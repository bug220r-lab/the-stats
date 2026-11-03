# Meta collection and integration — October 24, 2026

The user authorized a collection pass prioritizing recent Instagram/Facebook Stories and link metrics, then older Instagram posts and missing post statistics. The user separately approved enabling Facebook Story insights and archiving.

## Data outcome

| Check | Verified result |
|---|---:|
| Distinct typed publication identities | 2,026, unchanged |
| New content observations | 268 |
| Total retained observations | 2,919 |
| Selected observations, including unresolved chronology | 2,665 |
| Story identities | 1,373, unchanged |
| Previously metricless Facebook posts recovered | 55 |
| Previously metricless December 2025 Stories recovered | 67 |
| Remaining metricless Story targets | 75, not collected in this pass |
| Quarantined new observations | 0 |
| Inherited publication-date conflicts | 4, retained |

All 480 Facebook identities now have at least one observed numeric metric. This does not mean every Facebook metric is available. Three posts have newly recovered native Link Clicks values of 1, 4 and 1. Total clicks, sticker taps and Link Clicks remain distinct fields. No Instagram Story identity has numeric link-click evidence.

Recent Instagram collection returned six existing Story IDs in a September 26–October 23 request, with actual publication dates October 1–16. Their native metrics were unchanged. The six direct recent-detail rechecks also matched earlier evidence. The December direct captures provide 67 view values, 67 interaction values, 10 reach values and eight sticker-tap values. The source explicitly reports two interaction zeros. Eleven native descriptions refresh existing text evidence.

Facebook Story insights activation was applied; the previous activation notice was absent after reload. The Facebook archive returned no results in the selected July 26–October 23 window. Earlier Instagram feed retries returned no results for January–March 2025, April–June 2025 and October–December 2024. These outcomes do not establish zero historical content or complete history.

## Immutable integration and provenance

- Predecessor: `meta-content-20261023`, SHA-256 `a055587589c82f49cd9b6554a978588964824ef3fc77696ed1cc9732dead60e3`.
- Verified active key: `meta-refresh-20261024`; explicit namespace `social/meta_refresh_20261024/`; 154 parsed tables.
- Installed active database SHA-256: `17dd0584462966c9e052bfc855f48fd931dc4288ac028aeb2f34f934e39dd4cd`, identical to the accepted candidate.
- Full preservation preflight: all 11 existing databases, both registries, and the same active predecessor. Sandbox escalation permitted the two YouTube database reads that were denied in the initial partial preflight. No ACL changes were made.
- Corrected frozen collection: 356 files; inventory receipt SHA-256 `c828ea4878c8c23bb3dbdd009b1eed27f031bdc0b0ba01ad81a28317cc48b4ec`.
- Three native CSVs and 73 accepted manual Story observations retain exact IDs, source hashes, original bytes, dates, capture times and scope. Collection statuses explicitly separate successful recoveries, unavailable fields, no-result windows and unperformed recovery work.
- Three incomplete visual captures were replaced; all original records and DOM/AX/PNG bytes remain retained. Their later direct-navigation recaptures carry no archive picker filter. Initially carried-over filter metadata was corrected with exact before-correction JSON bytes retained.
- Native publication timezone remains unknown unless independently labelled. The December 31, 2023 boundary row from the January 2024 Facebook request remains retained.

Loader support combines explicitly allowlisted content tables and verified bridges. The identity inventory remains unique; later captures are selected within the same metric scope/measurement type rather than added together. Older versions remain selectable. Normalizer 1.2.0 also projects supplied native descriptions/permalinks and distinguishes direct captures from archive-filtered captures.

The first promotion attempt correctly refused the full acceptance inventory because the promotion routine omitted the separately registered YouTube collection databases. It failed before copying the target or changing the registry. The routine was corrected to include verified YouTube registrations in its database inventory, validate their database/ZIP hashes, preserve their registry bytes and hold the existing YouTube import lock across new activation. The acceptance inventory retained all 11 prior databases; no preservation check was removed to permit activation.

## Verification and receipts

- 74 focused tests passed: content supplement loading, content summaries, content views and Meta normalization.
- 70 analysis-versioning tests passed after the promotion fix, including nine new regressions for separate collection inventories, stale hashes, concurrent registry changes, read-only replay and collection-import contention. This is a separate suite, not an additional unique-test total to combine with the focused run.
- `data/collection/meta-refresh-20261024/evidence/final_manual_source_acceptance_v2.json`: independent native identity/metric/heading/layout and corrected navigation-context acceptance.
- `data/reconciliation/meta_refresh_20261024/actual_candidate_content_profile_v2.json`: actual candidate content checks summarized above.
- `data/reconciliation/meta_refresh_20261024/source_review.json`: root semantic review pinned to the full corrected collection inventory.
- `data/reconciliation/meta_refresh_20261024/acceptance/`: final independent semantic/storage acceptance passed for the exact candidate, including all 11 prior database hashes.
- `data/reconciliation/meta_refresh_20261024/activation_verification.json`: post-activation verification passed at `2026-10-24T21:17:37.527058+00:00`; active key and database SHA match, all 11 prior databases are unchanged, both YouTube collections are verified and all 356 frozen collection files remain unchanged.
- `test-results/meta-refresh-20261024/verification.json`: live browser verification receipt at `2026-10-24T21:22:42Z`, recording the exact UI checks and proof filenames below.
- `docs/META_COLLECTION_PASS_20261024.md`: stakeholder-readable collection result and limitations.

Activation and live browser verification passed. The real Windows launcher was restarted in session `75655` and is serving `127.0.0.1:8501`.

Live browser evidence is under `test-results/meta-refresh-20261024/`:

- `social-inventory.dom.txt` and `social-inventory.png`: expanded Social inventory rendered with 2,026 distinct identities.
- `story-recovery.dom.txt` and `story-recovery.png`: a recovered Story displayed the caption “Hey it’s us @animunch” with 976 views and 831 reach.
- `facebook-link-click-recovery.dom.txt` and `facebook-link-click-recovery.png`: Facebook post `543468245389151` displayed its caption, four Link Clicks and an Open post link. The presence of the link was checked; an outbound navigation check is not claimed.
- `decision-content.dom.txt` and `decision-content.png`: Decision content displayed 2,026 identities, including 1,373 Stories, and the October 24 UTC capture cohort.
- `social-final.dom.txt`: the dashboard was restored to Social, unfiltered, One row per post, showing 2,026 identities and marked as the browser deliverable.

Visual metric checks cover the stated Story views/reach and Facebook Link Clicks. Other metric values are supported by the independent source/candidate audit; this browser pass does not claim an exhaustive visual check of every rendered value.

## Remaining collection targets

The exact 75 uncollected IDs are in `data/collection/meta-refresh-20261024/evidence/remaining75_final_queue.csv`: January 2024 five; January 2025 one; May seven; June 13; July 10; August 24; September seven; October two; November six. Prioritize August, June and July for the next targeted manual pass. A new pass needs a fresh namespace/key and new source directory; do not overwrite this frozen collection.

Older Instagram feed coverage, Facebook Story history, Story clicks, artwork text and the six earlier unresolved soundtrack assignments remain unresolved. This collection establishes descriptive lifetime observations, not social-to-Spotify causal effects.
