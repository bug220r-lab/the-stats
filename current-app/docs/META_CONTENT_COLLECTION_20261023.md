# Meta content collection — October 23, 2026

This collection adds source-backed Facebook and Instagram content observations while preserving the previous library and its statistics. It does **not** establish complete account history.

## Dashboard flow and acceptance

Open **Social → Collected posts & Stories** to inspect the content library. Use its platform, content, date, and search controls, and inspect capture timestamps, metric scope, source kind, and selection status alongside the values. Distinct content and retained observations are separate counts; captures are not added together.

- **Activation:** Active version **`meta-content-20261023`**. The independent [post-activation verification passed](../data/reconciliation/meta_content_20261023/audit/post_activation_verification.json): the installed database matches the audited candidate, all ten prior database hashes and the YouTube registry are unchanged, and activation replay is idempotent.
- **Tests:** The full run recorded **529 passed and one navigation-assumption failure**. That test was corrected to select **Account activity** explicitly; **12 targeted tests then passed**. The focused normalizer suite passed **45 tests**. The performance optimization passed **11 tests**, and [real-data equivalence checks](../data/reconciliation/meta_content_20261023/performance/after_equivalence.json) confirmed exact loaded data, all/latest/unknown-capture selections, and their inventories. A second complete suite run is not claimed.
- **Dashboard browser verification:** **PASS** after restarting the actual Windows launcher. The dashboard shows **2,026 distinct identities** and **2,537 capture observations**. Its downloaded inventory has exactly **2,026 rows and 2,026 unique identity keys**, byte-identical before and after optimization. Live searches found the August 7, 2022 Instagram Story and a December 31, 2023 Facebook post; a conflicting Story retained both December 30 and 31, 2022. Capture observations rendered correctly, and the final view was restored to the full inventory. See the [browser verification receipt](../data/reconciliation/meta_content_20261023/browser/verification.json) and [dashboard screenshot](../data/reconciliation/meta_content_20261023/browser/dashboard_verified.png). The final post-optimization targeted rerun passed **12 tests in 8.78 seconds**.

## Verified counts

The newly frozen collection contains **2,091 observations covering 2,026 distinct content identities**. All **560** identities in the preflight baseline remain represented; **1,466** identities are new.

The loaded library also includes **560 inherited observations**, giving **2,651 loaded observations** in total. The latest-compatible-capture view selects **2,537 observations**, retaining separate metric scopes and measurement types. These observation counts are not unique-content counts; the [semantic acceptance audit](../data/reconciliation/meta_content_20261023/audit/candidate_semantic_acceptance.json) records **2,026 distinct identities**.

| New identities | Count |
|---|---:|
| Facebook posts from 2023–2025 | 367 |
| Instagram feed content returned for the 2025 window | 34 |
| Older associated Instagram feed post, June 6, 2024 | 1 |
| Instagram Stories from 2022–2025 | 1,064 |
| **Total new identities** | **1,466** |

These are content identities associated with the selected accounts, not a claim that every item was authored by the band. The 2025 feed group includes associated content; the separately counted 2024 post is explicitly attributed to **blindboxingband**. Original author fields remain intact.

The **2,091 newly collected observations** comprise 2,025 native CSV records, 31 manual Story detail captures, and 35 feed-grid observations. Repeated identical rows from overlapping grid pages were deduplicated. Different captures, metric scopes, and measurement types remain separate.

## Observed coverage and gaps

| Source | Retained coverage |
|---|---|
| Facebook posts | 2023: 59 IDs, April 18–December 31; 2024: 161 IDs, January 5–December 31; 2025: 147 IDs, January 1–December 31; 2026: 113 existing IDs, January 5–August 26. |
| Instagram Stories | 2022: 67 distinct IDs, including the August 7 manual boundary; 2023: 398 IDs; 2024: 290 IDs; 2025: 309 IDs; 2026: 309 existing IDs. Source observations span August 7, 2022 through October 16, 2026, with gaps and conflicts retained. |
| Instagram feed | The 2025 export plus boundary overlap and grid returned 34 IDs dated August 20–December 31. Earlier 2025 coverage is unproven. The 2022–2024 grid returned only the associated June 6, 2024 post. Annual 2023 and 2024 native feed exports failed. |
| Facebook Stories | **Uncollected.** The native UI offered “Turn on Facebook story insights.” Insights were not enabled and settings were not changed. |

The Facebook 2022 export returned “No results found”; this is a request outcome, not proof of zero historical posts. Some Instagram export filenames differ from the selected UI dates. Sidecars preserve both endpoints, while row coverage uses the explicit publication fields. The December 31, 2025 feed boundary was collected in an overlapping request.

## Data rules and unresolved dates

Deduplication uses **platform + verified selected-account identity + post ID**, with IDs retained as strings. The approved Instagram bridge connects Business Suite asset `118246571240106` to native account `17841454335424545`; it changes neither authorship nor metric scope. No lifetime captures are summed.

**409 malformed native CSV originals** remain quarantined: 55 Facebook and 354 Instagram rows. Their verified identity prefixes support separate identity-only observations. Every metric on those observations is unavailable; no missing column was guessed and no zero was imputed. Rounded manual displays remain raw-only. The original inherited assets, mappings, and statistical outputs remain immutable.

Four Story identities have conflicting explicit publication dates:

| Post ID | Native export date | Detail-panel date |
|---|---|---|
| 17938760384419916 | 2022-12-30 | 2022-12-31 |
| 17866811784407895 | 2025-06-23 | 2025-06-24 |
| 17844902355501776 | 2025-06-23 | 2025-06-24 |
| 17849515764507169 | 2025-07-08 | 2025-07-09 |

Both source dates are preserved. Publication timezones are unconfirmed, so no offset is inferred and neither date overwrites the other. Exclude these four identities from counts requiring one unambiguous publication date. The 2022 December 31 manual capture overlaps a native December 30 identity; it is not an additional distinct Story.

## Provenance and reproducibility

- [Frozen identity and date audit](../data/collection/meta-content-20261023/evidence/frozen_identity_dates.json): 2,026 identities, 1,466 new, all 560 baseline identities retained, four date conflicts.
- [Manual and grid semantics audit — PASS](../data/collection/meta-content-20261023/evidence/manual_grid_semantics_frozen_v2.json): keyed metric values, missingness, dates, and associated authorship checked against retained evidence.
- [Normalization report](../data/collection/meta-content-20261023/normalized/normalization_report.json), [content observations](../data/collection/meta-content-20261023/normalized/content_snapshots.csv), [quarantined originals](../data/collection/meta-content-20261023/normalized/quarantined_records.csv), and [31 collection status rows](../data/collection/meta-content-20261023/normalized/collection_status.csv).
- [Approved account bridge](../data/collection/meta-content-20261023/normalized/identity_bridges.csv) and [preflight identity baseline](../data/reconciliation/meta_content_20261023/preflight/content_identity_baseline.csv).
- [Normalizer](../stats_app/meta_content.py), [command-line entry point](../scripts/normalize_meta_content.py), and [focused tests](../tests/test_meta_content_normalizer.py).

The frozen collection retains exact native downloads, hashes, metadata sidecars, capture timestamps, screenshots, DOM/accessibility captures, and raw manual observations. Reproduction must write to a new output directory. Explicit coverage limitations are retained in `collection_status_additions.json`. The package is built and active as `meta-content-20261023`; independent storage and replay checks passed. Final live dashboard browser acceptance passed as recorded above.
