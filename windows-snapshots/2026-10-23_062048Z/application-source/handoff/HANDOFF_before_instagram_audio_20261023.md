# The Stats™️ — October 23 Meta follow-up

The active immutable analysis is **meta-followup-20261023**, labelled **Meta follow-up · October 23, 2026 · Stories, Ads coverage and links**. Continue the existing Windows workspace. TikTok remains excluded. No deployment, ad edits, spending, or new correlation/significance calculations were performed.

The [previous handoff](HANDOFF_before_meta_followup_20261023.md) is preserved, including Spotify recovery and earlier collection history. Its historical paid-marketing interpretations require the correction below. Do not replace any working database with a recovery ZIP.

## Main findings and correction

- **The historical ad account contains mixed identities.** The maximum report's USD 661.02 partitions into **USD 554.52 band-identified**, **USD 99.79 Rialto**, and **USD 6.71 unresolved**. The earlier February generic band-promotion interpretation is withdrawn. June band-identified spend is **USD 199.94**, not USD 202.43; USD 2.49 belongs to an unresolved deleted ad. Current exact-ID configurations establish identity at capture, not unchanged historical creative. See [ADS_SCOPE_CORRECTION](../data/reconciliation/meta_followup_20261023/ADS_SCOPE_CORRECTION.md).
- **2026 coverage:** one accessible account, `582351779816254`. Jan 1–Oct 22 inclusive ad and campaign exports return “No data available”; payment activity says “No transactions.” Five current published rows display zero spend, and their schedules are in 2023–2024. One unpublished draft is separate. This does not establish zero daily spend across inaccessible accounts or reconstruct missing exports.
- **Six October Stories:** all visually reviewed, **zero audio/song assignments confirmed**. Oct 11 is an unconfirmed The Cut (Starts Tomorrow) candidate; Oct 10 is album/brand artwork only; remaining content identifies no recording. There are 36 lifetime metric/status cells, 14 observed and 22 unavailable. All six link-click values remain unavailable. User does not know the songs. The expired Instagram Story route redirects to the profile; available browser session still shows personal `jude__lewis`. User said they would sign in to `redactedbandoh`; owner archive/audio inspection remains pending. Do not turn visual references into audio matches.
- **Destinations:** both social bios point to the official Linktree. Six music cards and 15 destination rows are retained. The card labelled **[REDACTED] - Debut Album currently points to Funny Guy**, track `3QVtuSBGLC9fTmLfF6qP7Z`. Three other destination track IDs lack exact canonical-catalog matches and remain unaliased. Four band ad configurations link to the Instagram profile, not Spotify. The August 26 Facebook post `998829296519708` links to Blimp City Beats, not a song. Linktree click history and historical destination revisions were not available in the public view; no link-to-stream conversion is established.

Full source-qualified findings: [READOUT](../data/reconciliation/meta_followup_20261023/READOUT.md). Earlier organic correlation calculations remain unchanged; the prior 14-comparison extension found no association surviving its correction (minimum BH q 0.449). That is not proof that marketing has no effect.

## Branding

The dashboard uses the original **COUCH STICKER.png** from Google Drive, corroborated against the band's Instagram and Facebook branding. Source ID `1bG_KQYyHeBIrL1HcSpZlro6P8pBWQmLo`; original SHA-256 `8f79cb00debaaf1d5eaf7a6eb4953b4da2263bb3b100a54819beee230fa62b66`. Local assets, provenance and license/context notes are in [assets/branding](../assets/branding/README.md). No authoritative font/palette guide was found; the retained gold accent is a dashboard design choice. Header/sidebar branding loads locally after the access gate. No generated replacement logo or remote image dependency was introduced.

## Launch and shutdown

Double-click **launch_windows.bat** in this project. It resolves its own folder, uses `.venv`, binds to **127.0.0.1:8501**, and opens the default browser. Keep the launcher console open; **Ctrl+C** stops the application. Closing the browser alone does not stop it. Initial setup only: `setup_windows.bat`.

```powershell
.\launch_windows.bat
```

For verification without opening another tab, use `.\launch_windows.bat --no-browser`. See [README](../README.md) and [Windows troubleshooting](../docs/WINDOWS.md). Native Windows Python 3.12.14, Streamlit, Plotly, pandas and SQLite remain in use. No WSL, Docker, cloud database or API key is required locally. This workspace is not a Git repository; `.gitignore` exclusions exist, but tracked-file status cannot be verified.

## Storage and preservation

Data lives in `%LOCALAPPDATA%\TheStats`, configurable with `STATS_DATA_DIR`. There are **six databases and four selectable analysis versions**. The five earlier databases exactly match the preflight SHA-256 hashes; all six pass SQLite quick checks. New version activation succeeded, and identical promotion replay was idempotent without registry changes.

New database: `analysis/meta-followup-20261023/analysis.sqlite3`; SHA-256 `ad9c253ac9a2b3d6f1621bea9e5f0e6a43ce48314eea4a5e91e245ef4e5c6efa`.

The package contains **1,651 assets, 137 tables, 168,871 heterogeneous CSV records, and 1,203 verified raw-file hashes**. These are storage counts, not independent statistical samples. Eleven new tables include a generated catalog. All **1,565 predecessor assets** and **70 collected source files** remain byte-identical. Predecessor package metadata alone is retained under `raw/meta_followup_predecessor_metadata/`; other inherited asset paths are unchanged.

Archived Spotify snapshot 1 and social snapshot 2 remain unchanged. The historical Spotify endpoint is October 20, 2026; **membership in the original October 20 baseline remains unverified**. Newer collection is not baseline verification. Preserve explicit missing statuses, source/account identities, capture versus acquisition timestamps, reporting windows and source references.

Keep lifetime content metrics separate from period activity. Never sum daily unique audiences. Instagram-selected crossposted Views retain Facebook + Instagram scope. Spotify dates are UTC, Business Suite dates Pacific, Ads dates Eastern; daily aggregates cannot be exactly rebinned. Inherited statistical results retain their original inputs.

## Verification actually performed

- Full native Windows suite: **246 passed in 210.48 seconds**, before the final link provenance and display corrections. No final full-suite rerun is claimed.
- After final link provenance correction: **5 focused link-normalization tests passed**. After Story display ordering: **2 UI smoke tests passed**. After currency rendering correction: **1 focused UI test passed**. These overlap broader coverage and must not be added as unique test totals.
- Independent semantic and storage acceptance passed: all six Story identities/publication fields; 36 status cells; 15 exact destination rows; 96 native ad configuration fields; 3,161 historical delivery rows; nine coverage evidence hashes; all candidate CSV rows/ZIP assets and predecessor bytes checked.
- Actual Windows launcher, restart, loopback binding, persistence and live dashboard rendering were checked. Browser evidence and final runtime details are in the linked receipt below.
- Portable library backup verified **74 files, six databases and four analysis versions**. All four analyses loaded from the relocated backup with matching table data and original ZIP bytes. No live-library replacement was performed.

Still unverified: Story audio labels/owner archive access, unavailable-account paid coverage, historical creative/destination revisions, per-link analytics and conversion attribution, Linux execution, real hosted identity-provider sign-in/concurrency, physical double-click/Ctrl+C interaction and narrow-screen manual rendering.

## Evidence and continuation

- Frozen collection: `data/collection/meta-followup-20261023/`. **Do not edit it after activation.** Any later Instagram audio evidence belongs in a new collection and version.
- Package/stage/audits: `data/reconciliation/meta_followup_20261023/` — [independent acceptance](../data/reconciliation/meta_followup_20261023/independent_acceptance_audit.json), [preservation and backup](../data/reconciliation/meta_followup_20261023/final_preservation_and_backup.json), [runtime verification](../data/reconciliation/meta_followup_20261023/runtime_verification.json).
- Browser evidence: `test-results/meta-followup-20261023/`; branded result `final-dashboard.png`.
- Verified backup: `backups/library-meta-followup-2026-10-23/`. Follow [ARCHIVE_BACKUP](../docs/ARCHIVE_BACKUP.md); keep a protected copy elsewhere. `--output` only backs up the writable upload database.
- Reproduction workflow: [META_FOLLOWUP_STORAGE](../docs/META_FOLLOWUP_STORAGE.md). Original preflight refers to the preceding active version; do not rewrite it to force a rebuild after activation.

Local access remains unauthenticated on loopback only. Future hosting must retain fail-closed provider authentication, an explicit approved-user list and viewer/admin permissions, durable storage, backups and concurrency planning. No invented email addresses or homemade password system were added.
