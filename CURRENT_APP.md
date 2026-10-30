# Maintained Windows application

`current-app/` contains the reviewed application source migrated from the MSI
published `stats-active` library on October 30, 2026. The root backup and dated
`windows-snapshots/` remain historical recovery material, byte-for-byte intact.

Use `current-app/setup_windows.bat` to build its pinned local environment.
INTERLINKED launches the app with an explicit `STATS_DATA_DIR` pointing to its
owned, fetched library on THIS-MACHINE. Code alone does not contain that data.
Do not launch against an empty default library when continuing existing work.

Git commits/pushes protect maintained code. INTERLINKED Save library to MSI +
verify protects its managed data workspace; it does not save this checkout.
See `current-app/docs/INTERLINKED.md` for the managed launcher contract.

The dedicated monochrome Windows view is maintained under
[`current-app/desktop/`](current-app/desktop/README.md). It displays the existing
INTERLINKED-managed dashboard in its own window; INTERLINKED retains ownership
of backend startup, shutdown and the data cache lock.
