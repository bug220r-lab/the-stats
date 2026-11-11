# The Stats™️ — current Windows handoff

Saved October 23, 2026. Active immutable analysis: **instagram-audio-20261023**, labelled **Instagram audio review · October 23, 2026 · post evidence; Stories unresolved**. Continue this workspace in place. Intended users remain Lewis, Brandon and Samman. TikTok remains excluded.

The [preceding handoff](HANDOFF_before_instagram_audio_20261023.md) preserves the full Meta follow-up, branding, Ads correction and earlier recovery history. Do not overwrite working data with a recovery ZIP.

## Latest request and result

**Continuation in progress:** a separate owner Chrome profile is now available, and the root agent is inspecting it. This document records the completed personal-account post-review snapshot only. No owner-profile or Story-archive outcome is claimed yet; any new verified evidence requires a separate snapshot.

The user said they had signed into the band account, then clarified that it was in another browser/profile and instructed us to **search the posts with the current personal account**. The completed post-review collection used Chrome as `jude__lewis`; that collection did not establish owner Story archive access. Do not repeatedly request band login as if no personal-account inspection occurred.

- The current band Posts/Reels grids showed **August 16** as the latest visible feed post and **August 14** as the latest Reel. Retained exports agree; their selected reporting window extending into October does not mean October feed posts are present.
- The [August 14 Reel](https://www.instagram.com/reel/DcCDTzAT3F7/) exposes native audio **[REDACTED] • The Cut (Starts Tomorrow)**, [Instagram audio ID 960372056504905](https://www.instagram.com/reels/audio/960372056504905/). Its Meta post ID is `18056229809716887`. This is a verified native label on that Reel at capture. The unique Spotify title/artist candidate is `3HqynH6ObSuDPZM0RMnFxN`; identical recording equivalence and historical audio revisions remain unverified.
- The August 16 carousel `18190026088396913` and March 20 pinned carousel `18010602779835784` expose no native audio label in the inspected views. The pinned caption mentions The Cut and The Devil Wears Docs, already retained in the earlier caption map. Missing labels do not prove silence.
- **All six October Story audio matches remain unresolved.** No feed-to-Story identity bridge was found. October 11's The Cut candidate and October 10's album artwork qualification remain intact; no song was assigned from a different post's label.

The new version adds **three inspected-post rows**, **six unresolved Story status rows**, collection status and a generated catalog. Use **Meta collection → Instagram audio review** in the dashboard. Older collection views and all original maps remain available. [Detailed readout](../data/reconciliation/instagram_audio_20261023/READOUT.md).

## Preservation and interpretation

All **six earlier databases** match the preflight SHA-256 hashes. All **1,651 predecessor assets** and **21 newly collected files** are retained exactly. The new package contains **1,681 assets, 141 tables, 168,888 heterogeneous CSV records and 1,227 verified raw-file hashes**. These are storage counts, not statistical sample sizes.

New data: `social/instagram_audio_20261023/`; raw evidence: `raw/instagram_audio_20261023/`. Only three predecessor packaging metadata files are relocated to `raw/instagram_audio_20261023_predecessor_metadata/`; their bytes are unchanged. Inherited `meta_followup`, Spotify, social and statistical input lineage remains pinned to its original versions.

New DB SHA-256: `26c834263a538da47d4fc7ef0a762dab598c39cb179e4f3f92de8c0410676111`. SQLite is authoritative. There are now **seven databases and five selectable analysis versions**. The registry active pointer changed intentionally; no previous database was overwritten.

Archived Spotify snapshot 1 and social snapshot 2 remain unchanged. Historical Spotify reporting ends October 20, 2026; **original October 20 baseline membership is still unverified**. No lifetime metric, period series, correlation, significance result or stream attribution was recomputed. Never sum daily unique audiences, mix lifetime metrics with period activity, collapse recording variants, or remove the Facebook + Instagram scope of crossposted views. Current native labels do not establish historical delivery or conversion.

The preceding paid-data correction remains important: historical account-wide USD 661.02 separates into **USD 554.52 band**, **USD 99.79 Rialto**, **USD 6.71 unresolved**. The February generic-band interpretation is withdrawn. No 2026 delivery/transactions were found for Jan 1–Oct 22 in the one accessible account; this is not a zero series for every possible account. The Linktree Debut Album card currently points to Funny Guy. See the prior handoff for evidence and scope.

## Verification and files

- **22 focused tests passed**, covering the new supplement, namespace/lineage preservation, invalid Story transfers, recording uncertainty and existing Meta follow-up regression behavior. No full-suite rerun is claimed for this pass.
- Actual staged UI smoke: three inspected posts, one native label, six unresolved Stories and no app exception.
- Independent semantic review compared JSON, native accessibility captures and all three screenshots against retained post/source identities and publication times. Independent direct SQLite/CSV/ZIP audit checked every staged row and asset, predecessor bytes, source hashes, all six old databases and the registry before activation.
- Actual launcher restart and live browser readback verify the new active version and separate post/Story tables. See the runtime receipt for exact checks and limitations.
- Verified portable backup: **78 files, seven databases and five analysis versions**. All five analyses loaded from the relocated backup with equal source tables and ZIPs; all six earlier live database hashes remain unchanged.
- Backup/promotion readback results: [final preservation and backup](../data/reconciliation/instagram_audio_20261023/final_preservation_and_backup.json). No live-library restore/replacement was performed.

Frozen source collection: `data/collection/instagram-story-audio-20261023/`. Package and receipts: `data/reconciliation/instagram_audio_20261023/`, including `independent_acceptance_audit.json`, `semantic_acceptance_audit.json`, `direct_sql_storage_audit.json`, `stage_result.json`, `runtime_verification.json`. Browser proof: `test-results/instagram-audio-20261023/`. Backup target: `backups/library-instagram-audio-2026-10-23/`.

Do not mutate this frozen source collection after packaging. New owner-archive audio evidence requires a new dated supplement and fresh preflight. A direct Story audio label tied to the exact Story ID is still needed to finish those six assignments. The guarded current builder deliberately rejects confirmed Story assignments because this particular review did not acquire any; a future verified-Story workflow must separately validate its evidence.

Implementation: shared `build_evidence_supplement` in `stats_app/meta_followup.py`; scoped wrapper `stats_app/instagram_audio.py`; separate UI view in `stats_app/analysis_meta_ui.py`; [storage workflow](../docs/INSTAGRAM_AUDIO_STORAGE.md). Original Meta builder defaults remain compatible.

## Launch and operation

Double-click **launch_windows.bat** in this project, or run:

```powershell
.\launch_windows.bat
```

It resolves its own folder, uses `.venv`, binds only to **127.0.0.1:8501**, and opens the default browser. Keep the console open; **Ctrl+C** shuts down the app. Closing the browser alone does not stop it. `setup_windows.bat` is for initial setup. Runtime checks used the actual launcher with `--no-browser`; physical double-click/Ctrl+C interaction was not manually tested.

Default storage: `%LOCALAPPDATA%\TheStats`, configurable with `STATS_DATA_DIR`. Native Windows Python 3.12.14 + Streamlit + Plotly + pandas + SQLite remain in place. No WSL, Docker, API key, cloud database or paid service is required locally. Current band branding comes from the original Drive couch asset, documented in `assets/branding/README.md`.

Local authentication is omitted only on loopback. Future hosting must require provider sign-in, an explicit approved-user list and viewer/admin permissions, durable storage, backups and concurrency handling. No deployment occurred. Linux, hosted identity/concurrency and narrow-screen manual rendering remain unverified. Credentials/private exports/databases/backups/ZIPs/.venv are excluded in `.gitignore`; this folder is not currently a Git repository.
