# The Stats™️ — saved handoff

Saved October 22, 2026, America/New_York. Work stopped at the user's request after saving and uploading this handoff.

## Current outcome

The local Python/Streamlit dashboard is functional. Facebook and Instagram data has been collected, validated and imported into a new, separate snapshot. TikTok analytics remains blocked by sign-in.

- Workspace: `/Users/judelewis/Documents/ChatGPT/The Stats™️`
- Dashboard: http://127.0.0.1:8501/
- Python: 3.12.14 in `.venv`; dependencies pinned in `requirements-lock.txt`.
- No Git repository was initialized. Source changes are saved on disk and included in the recovery ZIP.
- Latest complete suite: **127 passed in 10.05 seconds**.
- Live browser verification displayed the new social snapshot, Facebook 28-day Views **194**, and the Instagram Results combined-platform Views **1,649** for September 24–October 21.
- The dashboard imports data; it does not automatically authenticate to or synchronize social services.

## Persisted snapshots

| Snapshot | Contents | Status |
| --- | --- | --- |
| 1 — Archived source package · Oct 20 reporting endpoint · collected Oct 22 | 82,878 active Spotify observations; 82,889 source references; 7 imports | Preserved unchanged. Ordinary unverified archive, not a proven original baseline. |
| 2 — Social captures · Oct 22, 2026 · separate from Oct 20 archive | 1,812 Facebook + 585 Instagram observations = **2,397 active source observations**; 20 imports including the acquisition manifest | Imported successfully and editable. Separate from snapshot 1. |

The 19 social source files provide 2,453 source observations. Fifty-six identical overlapping daily readings attach additional source references rather than duplicate counts. Replaying all 19 files and the manifest was verified idempotent. There were zero rejected source observations. Recorded warnings retain collaborator accounts, prepublication source zeros, sparse dates, and excluded rounded UI text.

The original October 20 baseline remains **unavailable/unverified**. A reporting endpoint is not proof of original baseline membership. Do not relabel snapshot 1 or snapshot 2 as that baseline.

## What was collected

- 17 native Meta CSV exports: Facebook daily Page audience, daily post video metrics, Instagram lifetime post performance, and account Results series for both platforms.
- Two evidence JSON files: 23 exact period readings plus 2 follower balances. Five rounded UI readings were retained in source evidence but excluded from exact observations.
- Account daily exports cover **July 24–October 21, 2026**. Additional period readings cover **September 24–October 21**. Source date picker explicitly uses Pacific Time; dates were not shifted.
- Facebook follower balance: **144** as of October 21. Instagram follower balance: **1,408** as of October 21. These are balances, not new follows.
- Native raw files, acquisition timestamps, checksums, settings, screenshots and account evidence are in `data/social_captures/2026-10-22/`.

Important source semantics:

1. Instagram Results Views include Facebook crossposts: 90-day combined views **23,322**, with source components **22,652 Instagram** and **670 Facebook**. Combined and component populations remain distinct. Do not call the combined total Instagram-only.
2. Instagram exact 28-day reach is **347**, while daily reach sums to 681. Facebook exact 28-day viewers is **35**, while daily viewers sum to 38. Distinct audiences must use a matching exact source window, never daily sums.
3. Instagram 90-day follows export contains only 38 dated rows. Missing dates remain missing; the exact source 90-day total **76** is separately retained.
4. Instagram posts are explicitly lifetime measurements. Their measurement cutoff is unknown; publication selection dates are not reporting bounds. The app has a separate lifetime-content table with publication filters and CSV download.
5. Native post/Page IDs, source-scoped Meta asset IDs and collaborator identities remain distinct. Results files lack embedded account IDs, so the observed Meta asset context `meta_asset:118246571240106` is retained and distinguished by platform. Do not merge identities by name.
6. The Facebook post Performance export contains one selected shared post and all-zero video-threshold measures. It does not prove zero Facebook account activity. Its 198 prepublication zero cells remain source evidence with unavailable status for calculations.

## Outstanding work and access blockers

- **TikTok Studio:** login required. No private analytics collected or imported.
- **TikTok for Artists:** login required. No private analytics collected or imported. Keep this distinct from TikTok account analytics.
- The user was asked to sign in to the two Chrome tabs. No confirmation of sign-in was received before stopping. If tabs no longer exist, open the official TikTok Studio and TikTok for Artists login pages and let the user complete authentication. Do not ask for passwords or codes in chat.
- **Instagram Stories:** Generate remained disabled in Meta's native export dialog for the selected account with both 90-day and 30-day ranges. Screenshots record the blocker. No invented zero rows were imported.
- Instagram 90-day exact reach was shown only as rounded 2.6K. It remains unavailable as an exact 90-day KPI.
- A newer Spotify supplement was inspected from Drive and saved under `data/collection_attempts/2026-10-22/drive/`. It is Spotify-only and was not imported during the social task. Its current collection queue differs from the historical 43 Pending rows stored with the original package. Do not overwrite historical queue records silently.
- `docs/VERIFICATION.md` describes the initial delivery and still includes its original 105-test/Spotify-only state. Current social evidence is in this handoff, `docs/SOCIAL_COLLECTION.md`, and the JSON reports below. Refresh that historical document only when work is resumed.

## Verification and recovery evidence

- `data/collection_attempts/2026-10-22/app_preflight.json` — pre-import exact SQL, columns and SHA-256 hashes.
- `data/collection_attempts/2026-10-22/post_social_verification.json` — preservation audit passed for every original observation, value, membership, source reference, import, metadata row and archived source file. Schema, queue, mappings and annotations unchanged. SQLite quick check passed.
- `data/social_captures/2026-10-22/import_result.json` — committed snapshot 2 and per-file counts.
- `data/social_captures/2026-10-22/replay_result.json` — every source and manifest replay idempotent.
- `data/social_captures/2026-10-22/kpi_verification.json` — verified calculation results from persisted data.
- `handoff/dashboard-at-handoff.png` — live dashboard state saved at handoff.
- Local pre-import backup: `backups/pre-social-2026-10-22/`.

The uploaded recovery ZIP includes saved application code, tests, documentation, dependency locks, a consistent SQLite backup, archived source bytes, connected-source evidence and the new social captures. It excludes the virtual environment, caches, credentials and redundant backups. `HANDOFF_SHA256SUMS.txt` hashes the packaged files.

## Resume locally

The server was running on loopback port 8501 when this handoff was saved. If it is no longer running:

```sh
cd '/Users/judelewis/Documents/ChatGPT/The Stats™️'
.venv/bin/python -m streamlit run app.py
```

For a fresh machine, extract the recovery ZIP into a new directory, create a Python 3.12 virtual environment, install `requirements-lock.txt`, and run the app. Do not overwrite a running workspace/database.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m streamlit run app.py
```

Select the social snapshot for Facebook/Instagram and the archived snapshot for Spotify. Source-scoped accounts may appear separately from native content accounts; this is deliberate pending a verified identity crosswalk.

Replay tooling, if needed:

```sh
python scripts/load_social.py data/social_captures/2026-10-22/capture_manifest.json
python scripts/load_social.py data/social_captures/2026-10-22/capture_manifest.json --commit
```

The first command is read-only validation. The second reuses the separate social snapshot and was verified idempotent. For genuinely new captures, use a new acquisition key and snapshot. Preserve the original raw files and capture evidence.

## Implementation ownership and files

- `app.py`: UI, live metric dictionary, source coverage/gaps, friendly account selection, combined-view scope labels, lifetime content evidence.
- `stats/social.py`: explicit native Meta CSV and exact UI-reading parsers, conservative schemas and scopes.
- `scripts/load_social.py`: checksum validation, preview and idempotent separate-snapshot import.
- `stats/metrics.py`: metric definitions, aggregation and lifetime evidence helpers.
- `stats/storage.py`: SQLite snapshot/version/provenance persistence.
- `tests/test_social.py`, `tests/test_ui.py`: native parsing, scopes, rounded/missing values, lifetime behavior, account selection and coverage tests.

No new analysis or collection should proceed until the user asks to resume.
