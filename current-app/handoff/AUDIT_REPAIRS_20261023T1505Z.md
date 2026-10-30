# The Stats audit repairs — October 23, 2026

The targeted fixes are installed in the existing MSI project. The default local dashboard is running again at http://127.0.0.1:8501. No production snapshot was promoted, no original dataset or registry was replaced, and nothing was uploaded or published.

## Installed changes

- `stats_app/ingestion.py` and `tests/test_ingestion.py`: reject blank or duplicate headers under the same strip/casefold normalization used for parsing, including direct DataFrames and CSV/TSV/XLSX sources. Ambiguous values cannot silently replace each other.
- `scripts/promote_analysis.py` and `tests/test_analysis_versioning.py`: require a passing compatible semantic acceptance receipt bound to the exact candidate hash, version and predecessor database inventory. Reject malformed, failed, mismatched and storage-only receipts. Check copied bytes and concurrent changes. Refuse nonempty SQLite WAL/rollback journals without checkpointing. Exact legacy replays are read-only and never switch the active pointer.
- `docs/PROMOTION_APPROVAL.md`: documents accepted receipt contracts and their limits. The gate checks receipt structure and bytes; it does not authenticate reviewer identity or independently re-audit externally referenced receipt contents.
- `data/reconciliation/meta_spotify_crossref_20261023/READOUT.md`: prominent superseded notice corrects June spend to $199.94 band-identified plus $2.49 unresolved, and withdraws February's band-promotion interpretation ($99.79 Rialto plus $0.15 unresolved). The prior report body follows unchanged, with exact original bytes backed up.

The existing `stats_app/ui.py`, `scripts/launch.py`, README and main handoff are byte-for-byte unchanged. Newer YouTube daily-supplement and navigation work was retained.

## Separate correction artifact

`data/reconciliation/post-song-map-normalization-20261023T1505Z-v1.1.1/` is additive and **not promoted**. It pins the original `spotify-recovery-20261023` input. All five JSON files match their frozen predecessors exactly; 1,805 CSV cells change only from erroneous apostrophes to empty cells, including 317 missing song IDs and 100 missing event dates. All 24 nonempty formula-leading values retain protection. See its `correction_lineage.json` and `PLACEMENT_STATUS.md`.

The active immutable analysis retains its historical CSV bytes. A future data-version promotion would need its own review and approval; this repair did not activate the corrected tables. All six deferred Story assignments remain unknown. Original October 20 baseline membership remains unverified; later retrievals remain distinct.

## Validation actually performed

- **Installed focused regression suite: 111 passed**, 10.46 seconds, including seven journal/inventory regression cases.
- **Installed aggregate suite: 431 passed, 1 skipped, 13 deselected**, 193.30 seconds. The 13 exclusions prevent retries of protected YouTube source reads.
- **Installed current-version report suite: 11 passed**, 15.94 seconds, against a byte-identical isolated copy of the active owner snapshot. This includes the repaired-follows check skipped by the aggregate fixture's older snapshot. These test counts overlap and must not be added.
- `pip check`: no broken requirements found.
- Tests used temporary libraries, fixtures, caches and outputs under the repair workspace. They did not import into or promote the production library.
- Eight accessible production databases have unchanged SHA-256 hashes and pass integrity checks. Both registries and the original audit are unchanged. Two protected YouTube databases could not be independently hashed. External raw files were not exhaustively rehashed; the mapping correction separately verified 19 preservation anchors, native-input hashes and all six unresolved Story rows.

## Actual runtime evidence

The previous default 8501 browser tab displayed a connection error. A fresh project-venv launcher started at 2026-10-23T15:05:09Z, PID 22544, bound to 127.0.0.1:8501 with the existing `%LOCALAPPDATA%\TheStats` library. Browser reload verified Overview, Decision report and Campaigns; the active version is still `instagram-story-owner-20261023`. Decision report displays 4,246 streams and the baseline caveat. Campaigns displays the honest empty metadata state; no import was submitted.

The older 8513 process remains untouched because listener/process mapping inspection was denied. Use **8501** for the newly installed code. The normal launcher remains `launch_windows.bat`; if 8501 is already running, use its browser tab rather than starting a duplicate.

## Remaining blockers and limits

- **Denied:** read/hash `C:/Users/jlewi/AppData/Local/TheStats/collections/youtube-20261023/youtube.sqlite3` and `collections/youtube-daily-20261023/youtube.sqlite3`. Windows returned WinError 5. The fresh dashboard separately displays `PermissionError` for the optional YouTube collection, so its views are unavailable in this runtime. No direct read was retried, alternate source used to bypass the denial, or access permission changed.
- **Denied:** listener enumeration via `Get-NetTCPConnection`; no retry or unknown process termination. Exact old-process ownership is unverified.
- The initial project installation was denied because approval review cited the earlier read-only restriction. After new specific user approval, the one permitted guarded retry succeeded. There is no remaining installation-approval blocker.
- No clean-machine setup, new collection, live authentication, external deployment or full YouTube acceptance was performed.

## Evidence and rollback

Repair workspace: `C:\Users\jlewi\Documents\Codex\2026-10-22\task\stats-fixes-20261023T1437Z`.

- `originals/` and `source_before.json`: exact pre-edit source backups and hashes. Restoring code is a separate deliberate action; never restore over subsequent edits blindly.
- `installed_20261023.json`, `installed_candidate_manifest.json`, `installed-review.patch`: final installed paths and hashes. Earlier `review.patch` and candidate-overlay receipts are preliminary, superseded by installed evidence.
- `installed-aggregate-tests-150411/results.xml`, `installed-focused-tests-150337/results.xml`, `installed-current-report-tests-150822/results.xml`: test receipts.
- `preservation_before.json`, `preservation_after_installed.json`, `FINAL_REPAIR_RECEIPT.json`: preservation and final state.
- `installed-dashboard-process.json`, launcher logs, `runtime-installed-*.txt` and `runtime-installed-*.png`: real dashboard evidence, distinct from AppTest.

![Installed Decision report](<C:/Users/jlewi/Documents/Codex/2026-10-22/task/stats-fixes-20261023T1437Z/runtime-installed-decision.png>)
