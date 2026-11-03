# TikTok Studio integrated — @funnyguycrawl

Verified **October 27, 2026, at 11:32 a.m. Eastern**. Open [The Stats → TikTok](http://127.0.0.1:8501/tiktok). The running app uses the real local library at `C:\Users\jlewi\AppData\Local\TheStats` and binds only to loopback.

**TikTok for Artists remains pending.** No Business account was created or linked.

## What is available

| View | Integrated evidence |
|---|---|
| Account activity | 365 source-labeled days of video views, profile views, likes and shares; signed comment values retained separately |
| Owned posts | 615 searchable posts, lifetime/stated-scope counters, watch/completion metrics, post viewers and 18,615 displayed breakdown rows |
| Audience reports | Daily viewers, follower stocks and net changes, 168 hourly activity rows, native report snapshots, 37 panel metrics, 162 account breakdowns, 10 notices and 72 third-party affinity observations |
| Rankings & comments | 159 ranked rows across 16 UI reports; 397 recent-comment observations with explicit repeated-capture and identity limits |
| Coverage & sources | All 33 native CSV members from 18 ZIPs, per-export date decisions, 4,312 hash-verified assets and original downloads |

The collection contains **51 separate tables / 28,781 stored rows**, including raw and normalized overlapping representations. These are not 28,781 unique events and must not be added together. The 1,846 post-panel receipts include one preserved superseded capture; there are 1,845 distinct panels across the 615 posts.

## Export date decision

The initial exports control the preferred **source-labeled October 26, 2025–October 25, 2026** calendar. All 197 rows from seven shorter first-capture reports agree with their annual histories; initial follower changes reconcile against follower stocks for all 364 checkable days.

Later annual exports repeat the same numeric sequences while changing dates, duplicating November 2 and omitting March 8. The later follower deltas shift one row, and hourly follower activity repeats all 168 values under dates advanced by one day. The custom October 26 export repeats the initial October 25 row.

These later files are retained as **excluded conflict evidence**. They are not merged, rewritten or appended to daily activity. **Reporting timezone and absolute event-day boundaries remain unknown.** This resolves source precedence for integration; it does not claim to fix or diagnose TikTok's calendar logic.

See the [independent date report](../outputs/tiktok_integration_20261027/date_audit/DATE_RESOLUTION.md), [33-member disposition table](../outputs/tiktok_integration_20261027/date_audit/source_dispositions.csv), and [executed audit notebook](../outputs/tiktok_integration_20261027/date_audit/date-resolution.ipynb).

## Preservation and activation

- Registered key: `tiktok-20261027-studio`, stored in the separate `tiktok_collections.json` registry.
- Activated source: `outputs/tiktok_integration_20261027/package-v2/`. The earlier v1 remains a superseded build draft and was never registered.
- All **4,252 files in the original acquisition manifest** remain byte-identical. The historical preparation and collection receipts retain their original status text.
- All **534 preexisting library files** remain unchanged after import, replay and browser verification. The existing **38,976 local observations**, saved analyses and baseline designations are preserved.
- SQLite integrity passed. A consistent backup is retained at `outputs/tiktok_integration_20261027/activation/local-database-before.sqlite3`.
- Replaying the same package was idempotent: no additional collection or observations. Complete-library backups now include the TikTok registry and evidence.
- The browser's unchanged-source ZIP download matched the original byte for byte.

Manifest SHA-256: `d0c51a9cfa4cf885b79e0bc3a27a30efc484b913fe80e0f8867c690f3a96ba85`  
Package SHA-256: `898fae6fb6627131ef298b3fd718124fe9edcbee5d2906bbc419cfa6cb22f59e`

## Verification

The focused repository/backup checks passed 46 tests; normalization passed 20 tests; UI/navigation passed 18 tests. Eleven checks against the real sealed package passed, followed by live browser checks of all five Studio views and an original ZIP download. The app health endpoint returned HTTP 200 / `ok`; the launcher log shows no application errors.

The broader suite initially reported **1,015 passed, 41 skipped, 2 failed and 2 setup errors**. One failure was an obsolete assertion that TikTok remained uncollected; it was updated to preserve the distinction between historical receipts and current collections. The other three outcomes were disk-full failures while building temporary YouTube test copies. Those disposable copies were removed and all three affected YouTube checks passed on rerun. A preparation-route test was also isolated from the user's large private acquisition workspace after a concurrent-run timeout; the final UI/archive rerun passed all 12 checks. **No unresolved failures remain.** The full suite was not repeated after these targeted test corrections; production source hashes remained unchanged across the full run and final verification. Dependency checks passed.

Only disposable test copies from this run were removed to recover space. Original exports, acquisition history, registered collections, backups and test logs remain preserved. Approximately 1.64 GB was free at the final readback.

Verification receipts:

- [Activation and replay](../outputs/tiktok_integration_20261027/activation/activation.json)
- [Independent package review](../outputs/tiktok_integration_20261027/repository-review-v2.json)
- [Real-package UI checks](../outputs/tiktok_integration_20261027/ui-smoke-v2.json)
- [Live browser checks](../outputs/tiktok_integration_20261027/browser-verification.json)
- [Final live-library readback](../outputs/tiktok_integration_20261027/final-verification.json)
- [Full-suite log](../outputs/tiktok_integration_20261027/verification/pytest.txt), [corrected UI rerun](../outputs/tiktok_integration_20261027/final-rerun-tests.txt), [YouTube rerun](../outputs/tiktok_integration_20261027/youtube-rerun-tests.txt)

## Remaining source limits

Rounded counts and bounded percentages retain their displayed precision. Native `undefined` viewer totals remain missing; observed zeros stay zero. Signed daily comments are preserved but excluded from default activity totals. Daily unique viewers, follower stocks and overlapping exports are not additive. Recent comments are partial and fingerprints are not native unique comment IDs. Interactive chart-point histories, mobile-only LIVE details and verified recording/sound mappings remain unavailable. Existing cross-platform analyses retain their original inputs; this collection does not establish causal attribution or automatic timezone alignment.

[Import/reproduction guide](../docs/TIKTOK_STUDIO_INTEGRATION_20261027.md)

![Verified TikTok activity view](../outputs/tiktok_integration_20261027/live-tiktok-activity-chart.jpg)
