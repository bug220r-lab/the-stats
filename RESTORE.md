# Restore The Stats™️ backup

## Verify the snapshot

Extract the complete project-backup ZIP into a new folder. From that folder, run:

```powershell
py -3 verify_backup.py
```

This reads `SHA256SUMS.txt` and verifies every listed backup payload. It does not execute the dashboard, change the database, or download dependencies. The SHA-256 file does not list itself. Original source and nested archive hashes are also retained in `SOURCE_MANIFEST.json` and `verification/`.

## Recover the saved populated dashboard on Windows

1. Locate `sources/drive/Project/The_Stats_Handoff_2026-10-22.zip`.
2. Extract it into a **new, separate directory**. Keep all relative paths, especially `data/stats.sqlite3`, `stats/`, `scripts/`, and the dependency lockfile. Do not overwrite a running workspace or active database.
3. In PowerShell, change to the extracted directory containing `app.py`. With Python 3.12 installed, run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

The original saved `HANDOFF.md`/README and `docs/` describe the October 22 application state. Its archived Spotify and separate social snapshots are historical. The saved package's original October 20 baseline provenance remains unverified.

The `application-source/` directory in this backup is a convenient source extraction, **not a complete populated application restore**. Use the complete handoff ZIP for the database and raw files. Later Spotify recovery/continuation data and YouTube files remain separate collection packages and need their documented import/integration work. No imports were performed as part of this backup.

## Recover version-control state

The accompanying `The_Stats_Git_Backup_2026-10-23.bundle` is a portable local Git backup with a dated recovery commit and tag. It contains the same repository files as the project ZIP, including the preserved original archives. It does not contain pre-existing development history that was absent from the saved application package.

```powershell
git clone .\The_Stats_Git_Backup_2026-10-23.bundle The-Stats-recovery
cd The-Stats-recovery
git log -1 --oneline
```

To publish, create or choose a private repository in the verified account and replace the bundle's local origin with that exact repository URL. Push normally; do not force-push over an existing development branch. Keep the repo private because the snapshot includes private analytics and its database recovery archive. GitHub remote upload is a separate step and must be verified before treating it as a second hosted backup.

## Complete the latest Windows backup

The active Windows/Codex working directory was not mounted in this session. Back up that current directory separately, including uncommitted source changes and a consistent SQLite backup, before declaring the newest local state protected. Exclude credentials, browser profiles, `.venv`, and caches. Preserve the already captured October 22 recovery package and later collection ZIPs as dated originals.

## Native Google files

The Drive backup folder contains editable native copies of the collection workbook, YouTube collection workbook, and project index. Portable XLSX/DOCX exports are included in this snapshot. Native document histories/comments were not comprehensively exported.
