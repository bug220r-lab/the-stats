# Portable library backups

Run from the project folder in PowerShell. Use a **new private destination directory** for every complete backup:

```powershell
.\.venv\Scripts\python.exe -m stats_app.backup --bundle-dir ".\backups\library-2026-10-22"
```

The bundle contains the configured local SQLite database, its original source bytes, the relative `archive_registry.json`, and only the registered archive databases, source folders and evidence roots. It includes every registered `analysis_versions` database and evidence root, with the active `analysis_package` pointer retained; legacy single-package registries still work. Each analysis database contains its original ZIP and package file bytes. The writable database uses SQLite's consistent backup API, including committed WAL data. Fixed archives and analysis packages are copied unchanged. Unregistered folders, credentials and application code are not automatically included.

Every saved file has its size and SHA-256 recorded in `BACKUP_MANIFEST.json`. Archive files and the registry must remain unchanged while copying; the tool refuses overwrite, escaping paths, symbolic links/junctions and archive databases with pending journal data. An interrupted or failed bundle is not a verified backup. The original library is never replaced or checkpointed by this command.

Registered YouTube collections are included through their separate `youtube_collections.json`: each immutable collection database, original ZIP and dedicated evidence directory is copied unchanged. `youtube_collections_included` records the count. This does not change the archive registry or active analysis version. Restore the entire bundle so both registries and all referenced sources stay together.

Registered Shopify collections are included through `shopify_collections.json`, with their immutable database and exact retained package. The backup validates the registered database and evidence hashes before creating the destination; `shopify_collections_included` records the count. Restore this registry together with its dedicated collection directory. See [Shopify import and interpretation](SHOPIFY.md).

Verify before restore:

```powershell
.\.venv\Scripts\python.exe -m stats_app.backup --verify-bundle ".\backups\library-2026-10-22"
```

To restore, stop the dashboard, verify the bundle, then **copy the complete bundle to a new private working data folder**. Keep the backup unchanged. Point `STATS_DATA_DIR` at that restored folder and launch the existing application. The relative registry paths work together without editing old database source paths. For a one-session PowerShell launch:

```powershell
$env:STATS_DATA_DIR = (Resolve-Path ".\restored-library").Path
.\launch_windows.bat
```

After checking the restored snapshots and sources, keep or change the usual configured data location deliberately; do not overwrite a working database. The source code and pinned environment setup are restored separately from the project/recovery package. Linux can use the same data bundle with a compatible Python environment and `STATS_DATA_DIR` set to its location.

The existing command remains a **local-database-only** backup and excludes separately registered archive folders:

```powershell
.\.venv\Scripts\python.exe -m stats_app.backup --output ".\backups\local-only-2026-10-22.sqlite3"
```

Backups contain private exports and analytics. Store them in a private location with appropriate access and keep a separate copy on reliable storage.
