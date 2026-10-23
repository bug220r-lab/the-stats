# The Stats Windows snapshot — October 23, 2026

This distinct snapshot captures the current Windows workspace and its authoritative local data library. It preserves the earlier October 22 recovery material unchanged and separately from this newer work.

Capture began 2026-10-23T06:29:21.378025+00:00 and ended 2026-10-23T06:37:01.058908+00:00 UTC. Sources were captured file by file, not as a globally atomic filesystem snapshot. Per-file hashes and stable-read checks passed. The writable active SQLite database and any database with journal sidecars were captured using SQLite's online backup API, which includes committed WAL content without changing the source database. Immutable databases and source archives were retained byte for byte. Original paths are mapped under `workspace/` and `active-library/`.

The package represents 14,652 file paths, 21,262,258,333 restored bytes and 2,301 unique contents (3,181,360,782 bytes before ZIP compression). Duplicate content is stored once in `objects/` and reconstructed from `MANIFEST.json`. All 8 discovered dated library-backup directories and the standalone October 22 SQLite backup remain represented. The active library includes its writable database, archive registry, six analysis versions, recovered handoff archive, and 2 registered YouTube collections, including the daily supplement installed during capture. Registry database references and declared database/package hashes were checked against captured content.

## Restore

Use Python 3.10 or newer. The backup utilities use only the Python standard library. Do not launch the application directly from this backup.

Both Google Drive and GitHub contain the same split portable ZIP. The Drive connection has a 512 MiB upload limit, so retain its `parts/` subfolder beside `PARTS_MANIFEST.json` when downloading. Reassemble from this directory:

```powershell
python restore_snapshot.py join PARTS_MANIFEST.json The_Stats_Windows_Snapshot_2026-10-23_062048Z.zip
```

Verify the complete ZIP, then restore to a new directory (the destination must not exist and needs approximately 21.3 GB free):

```powershell
python restore_snapshot.py verify The_Stats_Windows_Snapshot_2026-10-23_062048Z.zip
python restore_snapshot.py restore The_Stats_Windows_Snapshot_2026-10-23_062048Z.zip C:\TheStats-Restored-2026-10-23_062048Z
```

The result contains `workspace/` (current application, data, handoffs, and previous backups) and `active-library/` (complete live library). Preserve this restored copy as evidence. Copy `workspace/` into a new working project folder and `active-library/` into a new private data folder on local disk, outside OneDrive or other synchronization services. Read the application's `README.md` and `docs/ARCHIVE_BACKUP.md`. Install its pinned environment using `setup_windows.bat`, then point `STATS_DATA_DIR` at the restored private library before `launch_windows.bat`. Never merge this snapshot into an active database or reuse old WAL/SHM files.

## Provenance and limits

The current Windows workspace has no `.git` repository, and no nested Git history was found. Its files were captured without editing or discarding local work. `application-source/` in the published Git snapshot is a convenient browsable copy; the portable ZIP is the complete populated backup. The separate historical recovery bundle has its own original prepared commit and tag.

Credentials, authentication tokens/files, browser sessions, virtual environments, dependency/runtime caches, disposable test fixture outputs, and recursively generated outputs from this operation are excluded. `EXCLUSIONS.json` records each excluded subtree or file. SQLite sidecars are omitted because the backup API captures committed content. Existing source ZIPs and package evidence are preserved; archived prompts and AGENTS files are records, not current instructions.

One validation-only intermediate, `workspace/data/youtube_daily_supplement_20261023/staged_validation/`, was inaccessible even with elevated read and a direct attempt at its known SQLite path. Its staged bytes are not included. The source audit receipts, authoritative live supplement database, registered original supplement ZIP, and collected evidence are included; the staged database is not claimed to be byte-identical to the live database.

Full ChatGPT/Codex conversation histories and unsaved drafts were not exported. Native Google copies in the existing Drive backup preserve current content rather than all past revisions/comments. The original October 20 application baseline remains unavailable/unverified. Later source packages must retain their documented separate scopes; this backup operation did not import them into the old October 22 application database. Package names do not establish that private TikTok analytics were collected. Historical rejected branding prompts remain historical material.

Backup verification includes source hashes, nested archive scans, SQLite integrity checks, complete ZIP object/checksum verification, and split-part hashes. Application tests and the historical 127-test suite were not run during this backup. Remote publication is recorded separately after upload and readback; local assembly alone is not evidence of remote completion.

## Post-capture update

Seven files added or modified after the base cutoff are preserved separately in `The_Stats_Windows_PostCapture_Delta_2026-10-23_064142Z.zip`. Follow [README_DELTA.md](README_DELTA.md) to apply it after restoring the immutable base. The browsable application source includes the delta. Delta capture ended 2026-10-23T06:41:42.301335+00:00.
