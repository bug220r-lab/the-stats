# Windows milestone verification — October 22, 2026

> Historical milestone record. The later [reconciliation handoff](../handoff/HANDOFF.md) supersedes the baseline and unloaded-data statements below. Original October 20 baseline membership is unverified. The legacy database is unchanged; the recovered social and expanded Spotify datasets are now separately registered. The 98-test result below belongs to the initial milestone only.

## October 23 re-audit addendum

Use the [current re-audit](REAUDIT_2026-10-23.md) and [handoff](../handoff/HANDOFF.md) for the current implementation, test receipts and browser acceptance status. Results below remain evidence for the October 22 code state; they are not a current regression total.

The re-audit records source scope and coverage in [source_inventory.csv](../data/reconciliation/reaudit_20261023/source_inventory.csv), with [storage checks](../data/reconciliation/reaudit_20261023/storage_audit/storage_audit_backup.json) and [coverage/key/join checks](../data/reconciliation/reaudit_20261023/storage_audit/coverage_and_joins.json). The two live YouTube files were inaccessible to the storage auditor's normal sandbox; that auditor inspected their exact immutable copies in the authorized consistent checkpoint. This is separate from the live application/browser verification recorded in the current re-audit. The writable SQLite backup can have different header bytes; its complete logical table contents and retained source-blob hashes matched live storage.

Current regression risks include exact current/prior listener periods, shared canonical Social repair selection, missing versus zero values, custom-date report/download agreement, persisted filters, native Pacific YouTube daily selections and parent navigation. Source-period and lifetime outputs retain their original windows. Historical cross-platform inference retains its original input hashes and testing family; filter changes do not create a new inferential result.

The new import-preview tests in `tests/test_import_preview.py` exercise new and duplicate observations, identical replay, changed interpretations, conflicting values, sealed snapshots and distinct account/dimension keys. Preview runs the real importer on an in-memory SQLite backup opened from a read-only source connection. The checks compare complete source contents before/after; the WAL case also verifies unchanged source database and WAL bytes while reading committed WAL observations. Save-time validation still applies because data can change after a preview.

No production test campaigns or synthetic observations belong in the live library. Fixtures and write-path checks use isolated storage. No new analysis version is implied by these calculation/display changes, and original exports and immutable versions remain preserved. TikTok remains unavailable, six October Story song/audio mappings remain deferred, and October 20 Spotify baseline membership remains unverified. See the current re-audit for checks actually completed and any remaining unverified steps.

The selected workspace was initially empty. After inspection, Lewis confirmed that no application had been built and authorized this implementation here. No existing application was replaced. No ancestor AGENTS.md was found. Project context and the earlier dashboard specification supplied the source-folder references.

## Environment and setup actually verified

- Native Windows / PowerShell, Python **3.12.14 x64** in the project-local `.venv`.
- Streamlit **1.64.0**, pandas **2.3.3**, Plotly **6.3.1**, openpyxl **3.1.5**, SQLite **3.53.1**.
- Normal PATH `python` was a nonworking WindowsApps alias and `py` was absent. Setup can discover the compatible Codex runtime, use `STATS_PYTHON`, or use a separately installed Python 3.12.
- Dependencies were downloaded into `.venv`; every installed package version is in `requirements.lock.txt`. `pip check` returned **No broken requirements found**.
- The actual setup PowerShell script and `setup_windows.bat` both ran successfully using the existing `.venv`. The PowerShell parser was also checked. A fresh-machine double-click setup was not performed.

## Tests actually run

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

Final suite: **98 passed in 14.52 seconds**. The suite includes:

- Empty dashboard and import-screen rendering with Streamlit AppTest.
- Folder import through preview and commit; duplicate retry; reopening the dashboard against the same database.
- CSV/XLSX parsing, worksheet selection, column mapping, bad dates/numbers/headers, percent units, and missing/suppressed values distinct from zero.
- Atomic conflict rollback, equal overlapping exports, changed mappings, independent workbook worksheets, and original-byte recovery.
- Sealed baseline protection, separate newer snapshots, fresh-process persistence, concurrent import handling, and SQLite backup restoration.
- Safe daily aggregation; no sum of unique audiences, follower balances or rolling windows; missing dates remain gaps.
- Local non-loopback denial before data access, hosted missing-configuration denial, explicit issuer/subject/expiry checks, and viewer import denial.
- Launcher refusals for occupied/invalid ports, wrong virtual environment and nonlocal modes, with guards proving no browser or server started in those cases.
- An optional real-source integration test ran (was not skipped): independently read the five private CSVs, verified hashes and source totals, imported **12,288 observations**, repeated without duplicates, read them in a fresh Python process, and verified original bytes unchanged.

## Live Windows and browser verification

- Executed `launch_windows.bat`; it opened the default **Chrome** browser at `http://127.0.0.1:8501/` after health readiness.
- Inspected the listening socket: **127.0.0.1:8501 only**. No firewall or system security settings were changed.
- Inspected the real dashboard and Plotly chart in Chrome. The selected artist-stream window September 23–October 20 displays **4,246 streams**, latest endpoint **182**, and **28 observed days**. Daily unique listeners show unavailable period aggregation rather than a misleading sum.
- Stopped the test Streamlit process and started the batch launcher from a different working directory using `--no-browser`. Reloaded the existing Chrome tab and confirmed the same values, **12,288 observations**, **five imports**, and a sealed baseline.
- The restart test used targeted process termination. The automated terminal did not deliver a verifiable physical Ctrl+C event, so interactive console Ctrl+C shutdown remains unverified. The launcher implements interrupt handling and child cleanup.
- Screenshot: `test-results/dashboard.png` (private, ignored by Git).
- Created a consistent backup with `python -m stats_app.backup --output .\backups\the-stats-2026-10-22.sqlite3`. Backup restoration is separately covered by the automated storage tests.

## Data scope and limits

The original source archive and the October 22 supplement were retrieved read-only from the project's known Google Drive folder. The original package identifies the reporting endpoint as **October 20, 2026** and collection date as **October 22, 2026**. The supplement explicitly identifies the original archive as the historical baseline. Source SHA-256 checks matched the original archive manifest.

Imported baseline scope: **one native artist timeline and four native track-stream exports**, 1,024 dates each. Artist observations include eight metrics, yielding 8,192 records, plus 4,096 track records. Independent full-history artist stream sum: **101,342**. The four tracks are not the entire catalog and must not be added to the artist total.

The full original ZIP is preserved under ignored `data/source`; other chart-derived/manual tables are not yet normalized into this dashboard. The supplement stays separately labeled and unimported. Exact per-CSV capture timestamps remain unknown instead of using the import time as a substitute.

No real Meta or TikTok export was available in the accessible local/Drive source folder during this build. A related collection chat mentions Meta work, but that does not establish a locally imported dataset. Meta parsing was tested with isolated fixtures; TikTok uses explicit canonical mapping. Their actual-export reconciliation remains unverified.

The app's production database is in `%LOCALAPPDATA%\TheStats\stats.sqlite3`, outside the OneDrive project folder. Synthetic fixtures were confined to temporary test databases. Source files, database, secrets, `.venv`, backups and screenshots are excluded from Git.

No Linux run, real OIDC provider login, hosted deployment, external HTTPS access, or live platform API access was performed. Hosted identity-provider setup, actual approved identities and final viewer/admin assignments still require future configuration and acceptance. No fabricated accounts or email addresses were created.
