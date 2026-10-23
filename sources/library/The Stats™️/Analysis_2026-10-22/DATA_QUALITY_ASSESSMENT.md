# Data quality assessment

The evidence supports descriptive Spotify trends, complete-window Meta activity comparisons and limited exploratory weekly associations. It does not support causal marketing lift, individual social-to-streaming conversion, a fair retrospective fixed-age content contest, or TikTok performance analysis.

## Coverage and preservation

- All 652 retained input files are listed and SHA-256 checked; source bytes remain unchanged. Fifteen duplicate-file instances are documented without deleting evidence. Earlier derived files are comparison evidence, not independent authoritative observations.
- Spotify has 1,024 continuous artist dates, January 1, 2024–October 20, 2026. The rebuilt 66,631 recording-day-metric rows match retained native/chart evidence. All 14 recordings reconcile to artist streams for each of 365 common complete dates. Sixty-four of 70 recording-metric histories are complete.
- Thirty-two native Meta CSV hashes were verified. Canonical activity has 3,528 calendar rows. There are 1,028 overlapping daily groups with no value conflict. All snapshots remain available.
- The canonical post inventory has 377 distinct structurally valid posts/Stories: 113 Facebook, 138 Instagram feed, 126 Stories. All 434 valid source snapshot rows remain available; 57 duplicate snapshots are collapsed only in the canonical view.
- The original Spotify activity baseline ends October 20. Later Spotify evidence and October 22 Meta retrievals are separately identified; the latter are not claimed as original baseline snapshots. October 21 Meta daily data is partial and excluded from complete-window analysis.

## Material issues and disposition

| Severity | Issue | Evidence and treatment | Analytical consequence |
|---|---|---|---|
| High | Malformed Story rows | 183 records have 19 values against a 20-column schema. All raw fields are quarantined; no positional repair is guessed. | Surviving Stories are incomplete and cannot represent the full Story population. |
| High | Missing history | GOOMH! has 365 stream dates and no four other metric histories; Son! has 730 stream dates. Missing values are not zero-filled. | Restrict catalog comparisons to complete coverage. Do not equate observed history with lifetime. |
| High | Incompatible all-time totals | Funny Guy history 30,549 versus header 29,786; The Devil Wears Docs 11,872 versus 11,861. Both retained. | Use bounded daily totals for bounded trends; do not label those totals lifetime. |
| High | Instagram-selected Views includes Facebook | Latest 90 days combined 23,270; manual UI components 22,591 Instagram and 679 Facebook. Independently scoped Facebook Page Views is 1,050. | Keep combined scope visible; do not add Page Views or subtract it to synthesize Instagram daily views. |
| High | Incomplete attribution/event/paid data | No measured listening journey, complete show/promotion/playlist calendar or full ad-account history. | No conversion rate, causal social effect or fully adjusted marketing model is justified. |
| Medium | Missing daily Follows | 128 Instagram Follows cells in the January 1–October 21 calendar are null. Observed sums matching a UI total do not prove omitted dates are zero. | Show observation coverage; median is conditional on observed dates. |
| Medium | Audience disagreement | Gender counts sum to 1,064 and age counts to 1,063 versus 1,062 period listeners. | Retain reported values and disclose discrepancy, with no balancing adjustment. |
| Medium | Timezone mismatch | Spotify UTC and Meta Pacific daily bins. | Nominal complete weeks and ±1-day sensitivities reduce boundary concerns but cannot create exact alignment. |
| Medium | Lifetime content age and author scope | Formats differ in post age; collaborations and other authors are present. | Separate author scope and show age; use new fixed-age snapshots for content decisions. |
| Medium | Sparse/discontinuous predictors | Facebook clicks: 3 across 2 weeks; Instagram clicks: zero; Facebook interactions collapse in later months. | Six of 12 planned comparisons have no justified inferential uncertainty. Retain all planned rows. |
| Medium | Limited geography, sources and rounded displays | Top lists, overlapping audience/source categories, displayed percentages and rounded UI numbers. | Preserve scope and precision; do not sum overlapping unique people or fabricate exact counts. |
| Blocked | TikTok | Access records exist but no verified analytics identity or retained analytics exports. | No TikTok finding is claimed. |

## Checks and practical interpretation

`audit/final_validation.json` records the full rerun's checks. `audit/independent_review.md` and `.json` document a separate recomputation of native totals, join uniqueness, lag direction, coefficients and multiplicity. Domain validation and reconciliation files supply the detailed record.

The weekly analysis retains 41 complete weeks, yielding 40 same-week and 39 next-week change pairs. Only six tests are eligible for exploratory uncertainty. None survives the planned multiple-testing correction; minimum BH-adjusted p is 0.385. This is insufficient evidence of a relationship, not proof that meaningful marketing effects are absent. The marginal block intervals and circular-shift tests are different uncertainty constructions; an interval excluding zero does not override corrected tests.

All supported period comparisons are observed descriptions, not randomized estimates. Genuine spikes and negative net follower changes are retained. No artificial p-values or confidence intervals are attached to fixed-period totals. Source reliability and platform measurement errors are not estimated by the statistical intervals.
