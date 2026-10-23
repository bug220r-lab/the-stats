# The Stats backup completion — October 23, 2026

Completed and verified at: 2026-10-23 06:57:13 UTC (2026-10-23 02:57:13 AM EDT America/New_York).

## Destinations and restore entry points

- Private GitHub repository: https://github.com/bug220r-lab/the-stats
- Historical Drive backup and native editable Google copies: https://drive.google.com/drive/folders/122KQIiOGFl_h0ZpthM-333__r1bVd2_N
- New Windows snapshot on Drive: https://drive.google.com/drive/folders/1sm3iFsDs7SEgA7x4qnDfHBRIU2CmaGFT
- Windows restore instructions: https://github.com/bug220r-lab/the-stats/blob/windows-snapshot-2026-10-23-062048Z/windows-snapshots/2026-10-23_062048Z/README_DELTA.md

The repository is private and the Drive backup folders have owner-only permission metadata for bug220r@gmail.com. No original Drive files, existing dated backup contents, or existing application files were replaced.

## Historical prepared recovery snapshot

The original prepared snapshot was published on `main` and tagged `snapshot-2026-10-23`. Its commit is `7ab715160f5f68fcd87424fce4b2a1c281c952bf`, tree `c808c36ce2be3a19644039776c0c3343afb238f0`, with 177 tracked files. The `main` branch subsequently adds the dated Windows snapshot directory, this completion record and verification receipts; the original tag and all original files remain unchanged. Its assembly-time "GitHub pending" note is preserved as historical context.

The Drive bundle (59,022,040 bytes) matched SHA-256 `adf1bcc191d03526db5c67aff2411d33ad948730dbb57169a0e5da6610507dd3`. The Drive ZIP (81,069,770 bytes) matched SHA-256 `a230d4126cf7aa924fd1cec7db0912e916cb41949ab3a84b4a7b6733be752d18`. All 177 ZIP member contents matched the repository. The included verifier passed all 176 listed checksums. Git bundle verification, object integrity, remote branch/tag readback, and a fresh GitHub clone matched the expected commit, tree and inventory.

## Newer Windows work

The base capture finished at 2026-10-23 06:37:01 UTC (02:37:01 EDT). A separate seven-file supplement captured the known later README, YouTube UI, handoff and audit updates through 2026-10-23 06:41:42 UTC (02:41:42 EDT). The final enumeration at that cutoff found no further additions or modifications. Work after the cutoff is not claimed included.

The base represents 14,652 original file paths and 21,262,258,333 restored bytes, storing 2,301 unique contents once. It includes the current Windows workspace, its authoritative `%LOCALAPPDATA%\TheStats` library, active database, six analysis versions, both YouTube collections, source packages, and all eight discovered previous library-backup generations. The Windows workspace had no `.git` repository or nested Git history; no unavailable development history was invented.

Windows branch: `windows-snapshot-2026-10-23-062048Z`.

Windows tag: `snapshot-windows-2026-10-23-062048Z`.

Windows snapshot commit: `7825dee4362f0d9dee193833a098721a713827d6`.

Windows tree: `1f6bfb4b1a7e1bc70b2840d5ecfb0bdd5aa05d24`.

The snapshot adds 181 files under `windows-snapshots/2026-10-23_062048Z/`, including browsable application source and complete recovery data. All added files were checked against the frozen staging inventory and read back from GitHub after publication. The original historical files remain intact.

The base ZIP is 642,332,722 bytes with SHA-256 `65b72ef865e5038de3718bae70e94d6b418257c9eb1f6662cbaa19ed105bae27`. Both Drive and GitHub carry the same 14 parts of at most 45 MiB, with `PARTS_MANIFEST.json` and `restore_snapshot.py`. This avoids GitHub blob limits and the Drive connector's 512 MiB upload limit. Rejoin the parts, verify, and restore into a new directory, then apply the separate delta using `README_DELTA.md`. The delta ZIP is 28,386 bytes, SHA-256 `077f2bf9298e8149a3a57ab7e07770f2a356d54ea624260c155f3cd97cbc49b6`.

All 29 Windows payload/support files uploaded to Drive were downloaded and matched local lengths and SHA-256 hashes. Those downloaded parts reconstructed the exact base ZIP and passed its complete verifier; the downloaded seven-file delta also passed verification. All 13 unique SQLite databases passed integrity checks. Live writable SQLite content was captured with the backup API. Registry references and declared database/package hashes matched captured files. Credential scans found no unresolved matches. Actual part reconstruction and controlled delta apply, replay, and conflict-rejection checks passed.

Capture was file by file rather than a globally atomic filesystem snapshot. Source stability checks and database-consistent capture were used. A full 21 GB filesystem restore, application launch, and application test suites were not performed during this backup.

## Exclusions and preserved qualifications

- `workspace/data/youtube_daily_supplement_20261023/staged_validation/` could not be read, including with elevated read access. Its bytes are excluded. This was an intermediate validation directory; its audit receipts and the authoritative live supplement database and source ZIP are preserved.
- Credentials/authentication files, browser sessions, virtual environments, runtime caches, disposable test fixtures, SQLite sidecars, and this operation's recursive generated outputs were excluded. See `EXCLUSIONS.json` for individual paths. Project browser-capture evidence is retained; browser session profiles are not backup targets.
- Full ChatGPT/Codex conversations and unsaved drafts were not exported. Native Google copies preserve current content rather than all historical revisions or comments.
- The original October 20 application baseline remains unavailable/unverified. No independent baseline proof is claimed.
- Later collection packages retain their original scopes; this backup did not import them into the historical October 22 application database. The Meta/TikTok package name does not prove private TikTok analytics were collected.
- Archived prompts and handoffs remain records. The rejected historical branding prompt was not executed as a current specification.
- Pattern scans reduce credential risk but are not exhaustive proof that arbitrary hidden secrets are absent. No historical application test result is represented as a test run performed here.

Verification receipts are stored separately in `verification/publication-2026-10-23/`. The original snapshot's checksums remain valid.
