# Meta collection pass — October 24, 2026

This pass collected native Meta exports and direct Instagram Story detail observations for the verified Instagram account `redactedbandoh` (`17841454335424545`) and Facebook Page `Redacted OH` (`100091779409539`). The Business Suite asset is `118246571240106`; it is a separate identifier with an existing verified identity bridge.

## Collected and recovered

- Three exact native CSV exports: 189 Facebook post observations and six recent Instagram Story observations. The recent Story export covers October 1–16 within a requested September 26–October 23, 2026 window; it supplies no link-click column.
- Six recent Instagram Story detail rechecks, with exact native IDs and retained DOM, accessibility and screenshot evidence. Their link-click, sticker-tap and follow metrics are unavailable markers.
- Direct detail captures for all 67 December 2025 Stories in the preflight missing-stat queue. Every Story has observed views and interactions; 10 have observed reach and eight have observed sticker taps. Two interaction values are explicit zeros. Link clicks and follows remain unavailable for all 67.
- Both Facebook exports together recover numeric metrics for all 55 previously metricless Facebook targets. The second export contains five supplied Link Clicks values; three were previously missing. Total clicks remains a separate metric.
- The baseline missing-stat queue therefore falls from 197 identities to 75. Those 75 remaining Instagram Stories were not collected in this pass; their exact IDs remain in the evidence queue. No missing value is imputed as zero.
- Every collected identity was already present. This pass adds later captures and metric backfills, not new publication identities. Lifetime snapshots must not be added together.

Eleven December Story descriptions were read directly from native headings. Those identities already had retained text, so this refresh improves dated provenance rather than establishing 11 newly filled caption gaps. Image-only text and soundtracks were not inferred from these headings.

## Collection limits and setting change

The user explicitly approved enabling Facebook Story insights and archiving. The activation notice disappeared after the setting was applied and the page reloaded. The Facebook-only archive returned no results for July 26–October 23, 2026. This does not establish complete Facebook Story history, recover older expired Stories, or demonstrate future collection coverage.

Fresh Instagram feed export requests for January–March 2025, April–June 2025 and October–December 2024 returned “No results found.” These are scoped collection outcomes, not evidence that no posts existed. The December 2025 Story export form became disabled without a corresponding new export job; direct Story panels supplied the December recoveries instead. Earlier Instagram feed history remains unresolved.

The first Facebook request selected January 1–March 31, 2024, but its native filename starts December 31, 2023 and it includes one December 31 boundary row. Both requested dates and actual publication dates are retained. The date-picker's Pacific Time notice does not establish a publication timezone.

## Source preservation and verification

Sources, sidecars, checksums, selection evidence, collection statuses and independent comparisons are under `data/collection/meta-refresh-20261024/`. The preflight records all 11 existing database hashes and the active predecessor `meta-content-20261023`.

Three incomplete visual captures were replaced with stable rendered observations. Their original DOM, accessibility text and screenshots remain unchanged; the original manual input bytes and exception records are retained. Corrected captures are 092, 093 and 094.

The collection is active as `meta-refresh-20261024`, with 154 parsed tables, integrated additively under `social/meta_refresh_20261024/`. Its installed database SHA-256 is `17dd0584462966c9e052bfc855f48fd931dc4288ac028aeb2f34f934e39dd4cd`, identical to the accepted candidate. The loader uses an explicit supplement allowlist, preserves older selectable analyses, validates account-bridge conflicts, and selects the latest compatible observation within each metric scope and measurement type. Distinct source scopes remain separate.

The three direct-navigation recaptures do not inherit an archive date-picker filter. Their initially carried-over picker bounds were corrected to unknown/not applied, with the exact pre-correction source bytes retained. Native publication labels and metric values are unchanged. Normalizer 1.2.0 labels these captures explicitly as direct detail observations.

Focused validation: 74 tests passed across content supplement loading, summaries, content views and Meta normalization. A separate 70-test analysis-versioning suite passed after correcting promotion to include and preserve the separately registered YouTube collections. The correction retains the full independent acceptance inventory, verifies the collection database/ZIP hashes and registry bytes, and coordinates new promotion with the existing YouTube import lock.

Final independent candidate acceptance and activation verification passed. The post-activation receipt at `data/reconciliation/meta_refresh_20261024/activation_verification.json`, timestamp `2026-10-24T21:17:37.527058+00:00`, confirms the active key/hash, all 11 prior databases unchanged, both YouTube collections verified and all 356 frozen source files unchanged. The real launcher was restarted in session `75655` on `127.0.0.1:8501`.

Live browser verification also passed. Social displayed the full 2,026-identity inventory; a recovered Story showed “Hey it’s us @animunch,” 976 views and 831 reach; Facebook post `543468245389151` showed its caption, four Link Clicks and an Open post link. Decision displayed 2,026 identities, including 1,373 Stories, with the October 24 UTC capture cohort. These specific metrics were checked visually; the independent source/candidate audit supports the other values. The dashboard was left on Social, unfiltered, One row per post, and marked as the browser deliverable.

Browser proof pairs are `test-results/meta-refresh-20261024/social-inventory.dom.txt` and `social-inventory.png`, `story-recovery.dom.txt` and `story-recovery.png`, `facebook-link-click-recovery.dom.txt` and `facebook-link-click-recovery.png`, and `decision-content.dom.txt` and `decision-content.png`, all in that same directory. The final unfiltered state is retained in `test-results/meta-refresh-20261024/social-final.dom.txt`. The exact UI checks and proof names are recorded in `test-results/meta-refresh-20261024/verification.json` at `2026-10-24T21:22:42Z`. The accompanying handoff lists each check and its limits.

## Evidence entry points

- `data/collection/meta-refresh-20261024/PREFLIGHT.md`
- `data/collection/meta-refresh-20261024/captures/manifest.json`
- `data/collection/meta-refresh-20261024/collection_status_additions.json`
- `data/collection/meta-refresh-20261024/evidence/facebook_combined_recovery.json`
- `data/collection/meta-refresh-20261024/evidence/missing_142_story_month_queue.csv`
- `data/reconciliation/meta_refresh_20261024/PIPELINE.md`

These results describe content coverage and lifetime engagement. They do not establish that social activity caused Spotify listening.
