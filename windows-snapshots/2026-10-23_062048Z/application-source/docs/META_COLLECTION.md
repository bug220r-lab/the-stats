# Meta collection — October 23, 2026

`meta-collection-20261023` is active. Activation and duplicate replay succeeded;
the replay was idempotent and all four earlier databases remained unchanged.
This version adds separate Meta evidence and a new resolved Follows view while
retaining inherited canonical tables and statistical results byte-for-byte.
Original October 20 baseline membership remains **unverified**. Nothing was
relabeled as that baseline. TikTok was excluded.

The collection is preserved under `data/collection/meta-20261023/`; normalized
tables are in `normalized/`, reviewed mappings in `mapping/`, and original
exports, screenshots, accessibility text and capture metadata remain intact.
The built package is `data/reconciliation/meta_20261023/package/`, with 1,565
files, 126 tables, 168,754 CSV records and 1,130 retained raw-file hashes.
New dashboard tables are under `social/meta_collection/` inside the package.

| Evidence | Verified result | Remaining limit |
|---|---|---|
| Instagram Follows | All **293 complete days, Jan 1–Oct 20**, are observed in `follows_daily_resolved.csv`: 166 inherited native observations plus **127 individually verified zero-day repairs**. Five fresh native values match prior values. The complete-day total is 326 follows events. | Oct 21 stays a separate unresolved partial day. Follows events are not net follower growth or Spotify conversions. |
| Instagram Stories | All **183 previously quarantined post IDs** were opened individually. `instagram_stories_manual.csv` has 183 fresh lifetime captures; `instagram_story_metrics.csv` has **1,098 field observations/statuses**. | Views and interactions are available for 183 each, reach for 11, sticker taps for 18. Link clicks and follows are unavailable for all 183. Native export generation stayed disabled. These are partial metric recoveries, not reconstructed original rows; the original malformed records remain quarantined. |
| Facebook recheck | **586/586** newly exported daily values match the prior series for Jan 1–Oct 20: 654 interactions and 1,082 visits. | Interactions are 653 in Jan–May and only 1 in Jun–Oct; visits are 557 and 525. Fresh exports reproduce the break but do not explain it. The interaction definition includes ads, so it is not organic-only activity. |
| Paid Meta reporting | **3,161 ad-day rows** and **8 separate campaign rows**, with four export-coverage records. | Exact scope and missing-field limitations below apply. |
| Post/song references | 377 canonical posts reviewed: **60 posts with 62 explicit caption references**, **11 unresolved candidates**, **306 unknowns**; two posts reference multiple songs. | No explicit Spotify track links were found. A title reference does not prove audio use, exposure or listening. Unknown does not mean no song. |

Ads account `582351779816254` was collected with deleted items included. The
native maximum export actually spans **Sep 23, 2023–Jul 9, 2024**, despite a later
UI-selected end date. Its 2,328 ad-days cover eight stable ad IDs and contain
**$661.02 USD spend and 77,954 impressions**. The eight campaign rows reconcile
with those known totals; do not add campaign totals to ad totals. Link clicks
sum to 805 across 55 populated daily cells; 2,273 daily cells are blank and remain
unavailable. These clicks do not identify Spotify destinations.

A second daily export spans **Jul 10, 2024–Oct 20, 2026**, but covers only **one
ad ID** across 833 days, with explicit zero spend/impressions and blank link
clicks. The separately requested **Jan 1–Oct 20, 2026** export contains the native
message “No data available.” It produces zero data rows, not an inferred
zero-spend result. These sources do not establish complete paid delivery across
all ads or accounts. Currency is USD; the observed Ads reporting timezone is
Eastern Time and attribution is 7-day click or 1-day view.

`mapping/event_map.csv` contains release metadata and caption-based event or
promotion evidence. Seven release-metadata rows and thirteen caption claims
have full dates; those twenty rows are not twenty distinct verified events.
Publication/promotion dates remain distinct from event dates. Missing years,
relative dates and recording-version ambiguity remain unresolved. Mapping rows
must not multiply lifetime metrics or allocate aggregate Spotify streams.

Meta account-day evidence uses Pacific Time, Spotify daily evidence uses UTC,
and Ads uses Eastern Time. Story publication timezone was not labelled and
remains unknown. Lifetime content readings cannot be assigned to publication
days as period activity. Daily unique audiences, reach and ratios are not
summed. The explicit combined Facebook/Instagram scope of inherited
Instagram-selected crossposted views remains intact.

No new correlation or significance tests were run for this collection, and no
causal or stream-conversion claim is established. Evaluating marketing effects
still needs reliable post-to-recording/audio and destination mapping, compatible
period-level exposure/click data, complete paid scope and a dated release/event
calendar. Missing Story clicks and historical link destinations cannot be
recovered by treating blanks as zero.

Verification records are under `data/reconciliation/meta_20261023/`:

- `normalization_acceptance_audit.json`: passed; all 16 normalized CSVs are rectangular, 357 input hashes and 7,256 provenance references verify, exact native/manual values match, and the predecessor database is unchanged.
- `independent_acceptance_audit.json`: a second implementation passed all 183 Story IDs/1,098 cells, 127 daily Follows panels, Ads cells/IDs, Facebook values, mapping identities and preservation of all four databases plus the pre-activation registry.
- `independent_package_acceptance_audit.json`: also verifies 1,149 inherited package assets byte-for-byte.
- `promotion_result.json`: active version and idempotent duplicate replay, with earlier databases unchanged. The active registry change is intentional.

The full suite passed **226 tests** before the last UI polish and final
normalizer metadata-merge correction. The **19 focused normalization/audit
tests** passed after that correction and final output generation. The final UI
filter fixes passed **14 focused collection tests**. The actual Windows launcher
restarted successfully with the new snapshot persisted. The complete backup
verified **70 files, five databases and three analysis versions**; relocated
readback from that backup matched the live collection. All four earlier database
hashes still match preflight. See the current handoff for live browser checks.

To reproduce normalization without touching active storage, use a **new output
directory** and explicitly select the preserved predecessor. Run from the
project folder in PowerShell:

```powershell
$env:PYTHONUTF8 = '1'
$statsPrior = Join-Path $env:LOCALAPPDATA 'TheStats\analysis\spotify-recovery-20261023\analysis.sqlite3'
$statsRecheck = 'data/reconciliation/meta_20261023/reproduced-normalized'
.venv\Scripts\python.exe scripts/normalize_meta_collection.py --collection data/collection/meta-20261023 --output $statsRecheck --database $statsPrior --collection-complete
.venv\Scripts\python.exe scripts/audit_meta_collection.py --collection data/collection/meta-20261023 --normalized $statsRecheck --require-collection-targets
.venv\Scripts\python.exe -m pytest tests/test_normalize_meta_collection.py tests/test_audit_meta_collection.py -q
```

The normalizer refuses an existing output directory. Capture/acquisition times
and source hashes are retained; generation timestamps will differ on reruns.
See [normalization details](META_COLLECTION_NORMALIZATION.md) and
[mapping definitions](POST_SONG_EVENT_MAPPING.md). Package construction uses
`python -m stats_app.meta_collection` with an explicit `--parent-database`, new
`--output-dir` and new `--zip-path`; construction itself does not activate a
version. Reproduction needs the locally retained private evidence and
predecessor snapshot, not just the public source files.

The frozen collection preflight includes the registry before activation. The
package builder deliberately refuses to rebuild against a changed live registry.
Do not edit that frozen evidence to bypass the check. For a future new collection,
create a new dated collection directory and preservation preflight; the existing
package ZIP and staged database are the exact reproducible artifacts for this pass.
