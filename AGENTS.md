# The Stats development guidance

- Primary Codex folder: `C:\Users\Jude\Documents\Codex\The-Stats` on
  `THIS-MACHINE` as `Jude`. Reuse this outer checkout and its existing environment.
  Maintained application code is in `current-app/`.
- Start with `CURRENT_APP.md`, `docs/CODEX_HANDOFF.md`, `current-app/README.md`,
  `current-app/docs/INTERLINKED.md`, and
  `current-app/docs/THIS_MACHINE_VALIDATION.md`. Verify machine/user, working
  directory, branch, local changes and active INTERLINKED/Stats sessions before
  work. Preserve newer edits; historical commits are references, not reset targets.
- Use `current-app/.venv/Scripts/python.exe` (Python 3.12). Do not recreate the
  environment or install/upgrade dependencies as routine setup. Launcher,
  interpreter or dependency-lock changes require reviewing the installed pinned
  Stats connection before runtime use; never relax pins to bypass a failure.
- Launch and stop Stats through the installed INTERLINKED Stats controls at
  `C:\Users\Jude\Documents\MSI-Project-Library`. Its adapter supplies the explicit
  local `STATS_DATA_DIR`, validates runtime files and owns the cache lock/process
  tree. Browser closure does not stop Stats. Never bypass a lock, open SQLite over
  SMB, or silently create an empty replacement library.
- Code and data have separate ownership: Git commit/push protects this checkout;
  INTERLINKED manages `stats-active` data and verified MSI versions. Stop all Stats
  writers before an explicitly requested save/verify. Saved versions can reference
  original library bytes and are not independent archival backups.
- Preserve selected analyses, registered collections and original evidence. No
  automatic imports, activation, synchronization, fetch/save, cache release,
  deployment or PR merge. An idle session is not authorization for these actions.
- Keep new private data, credentials, environments, logs, receipts and generated
  outputs outside Git. Reuse the existing ignored `.venv`; use OS temporary
  directories for tests and logs. Review `git status` and diffs before staging.
- Preserve root recovery assets, `windows-snapshots/`, manifests, checksum lists,
  `.gitattributes`, and backup verification semantics. Root `.gitignore` is one of
  the 176 checksummed historical files: do not edit it or reseal history for routine
  development. Use maintained scoped ignores or additive local Git exclusions.
- Run tests from `current-app/` with isolated temporary fixtures and data paths;
  never point tests at the managed cache or private exports. The portable command
  and historical-fixture exclusions are in `docs/CODEX_HANDOFF.md`. Report its
  scope, skips and deselection; do not fabricate excluded private fixtures or claim
  that the complete private-data suite passes.
