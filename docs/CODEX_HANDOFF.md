# The Stats: local Codex handoff

Prepared October 30, 2026 (America/New_York). Recheck live state before each task;
this document records setup observations, not continuing authority for data work.

## Entry points

- Primary project: `C:\Users\Jude\Documents\Codex\The-Stats` (outer Git root).
  Codex's existing local **The Stats** project already points here; reuse it.
- Machine/user: `THIS-MACHINE\Jude`. Maintained application: `current-app/`.
- Interpreter: `C:\Users\Jude\Documents\Codex\The-Stats\current-app\.venv\Scripts\python.exe`.
- Source: [private repository](https://github.com/bug220r-lab/the-stats).
  Branch observed at setup: `codex/this-machine-integration`;
  HEAD: `9b4d5a54dd464087d679200b5b1be3b2714a23bd`.
  Initial working tree was clean and matched its local upstream reference.
  No network fetch or GitHub authentication check was needed for setup.
- [PR 1](https://github.com/bug220r-lab/the-stats/pull/1) was supplied as the
  existing draft PR; its remote status was not revalidated. No merge is requested.
- Read [root guidance](../AGENTS.md), [current app pointer](../CURRENT_APP.md),
  [application README](../current-app/README.md),
  [INTERLINKED contract](../current-app/docs/INTERLINKED.md), and
  [migration validation](../current-app/docs/THIS_MACHINE_VALIDATION.md).

## Installed runtime and data boundary

Use `C:\Users\Jude\Documents\MSI-Project-Library\INTERLINKED.cmd`, select
`stats-active`, and use its Stats **Start** / **Stop** controls. Do not use the
README's standalone launcher instructions for this existing managed library.
Setup does not require launching Stats or rerunning `setup_windows.bat`.

The installed connection is
`C:\Users\Jude\Documents\MSI-Project-Library\INTERLINKED-GUI-State\stats\connection.json`.
It selects `current-app`, its existing interpreter, and loopback port `8501`;
it pins `scripts/launch.py`, the interpreter executable and
`requirements.lock.txt`. All three pinned hashes matched during setup.
Review this connection when changing those files;
do not change pins merely to pass a guard. The installed adapter owns process
containment and the original cache lock, sets the explicit local data directory,
and refuses missing data. Leave installed files and session records in place.

Existing managed data:

```text
C:\Users\Jude\AppData\Local\ProjectLibrary\Cache\stats-active\Files\Drive_C\Users\jlewi\AppData\Local\TheStats
```

The retained `jlewi` path is intentional library identity, not a path to rewrite.
Never open SQLite over SMB, instantiate writable storage just to inspect it,
or substitute an empty `%LOCALAPPDATA%\TheStats` library. Use local consistent
snapshots for SQL inspection. Registry JSON can be inspected without opening a
database. Browser closure leaves the managed server running.

At setup the installed session journal was `IDLE`, `exitCode: 0`, last written
October 30 at 4:35:55 p.m. EDT (`2026-10-30T20:35:55.675524+00:00`). MASTER's
current controller and Stats workspace observations also reported idle; Codex
development activity is a separate signal. Preserve other active chats/sessions.

Registry readback found nine analysis versions with selected key
`meta-story-backfill-20261024`, two YouTube collections, and one each of Shopify,
Linktree and TikTok. All five registry hashes remained unchanged during setup.
Preserve registry files, selections, registrations and evidence.
The earlier Overview/TikTok browser acceptance and 14 database
integrity checks remain dated migration evidence; setup does not repeat them.

Git commit/push protects source only. INTERLINKED **Save library to MSI + verify**
protects its managed data, with all writers stopped. Release is a separate explicit
action requiring current verification and the exact project confirmation. Versions
can reference original MSI bytes and are not independent archival backups. No
import, activation, sync, transfer, release, deployment or PR merge is part of setup.

## Development validation

Reuse the existing Python 3.12.14 environment; dependency compatibility passed
`python -B -m pip check`. Tests must use an isolated temporary `STATS_DATA_DIR`
and synthetic fixtures, with logs/results outside Git. Isolate Windows profile
and temporary directories too when checking source-only behavior.

In a new disposable PowerShell process, start in `current-app/` and run this
portable scope. The profile/temp guards prevent optional tests discovering real
private exports; this also removes inherited import/auth/test-source overrides.

```powershell
$ErrorActionPreference = 'Stop'
$fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('ts-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $fixtureRoot | Out-Null
foreach ($name in @('data-guard', 'local-appdata', 'roaming-appdata', 'profile', 'temp')) {
    New-Item -ItemType Directory -Path (Join-Path $fixtureRoot $name) | Out-Null
}
$env:STATS_DATA_DIR = Join-Path $fixtureRoot 'data-guard'
$env:STATS_MODE = 'local'
$env:LOCALAPPDATA = Join-Path $fixtureRoot 'local-appdata'
$env:APPDATA = Join-Path $fixtureRoot 'roaming-appdata'
$env:USERPROFILE = Join-Path $fixtureRoot 'profile'
$env:TEMP = Join-Path $fixtureRoot 'temp'
$env:TMP = $env:TEMP
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
foreach ($name in @('STATS_IMPORT_DIR', 'STATS_APPROVED_USERS_FILE', 'STATS_EXPECTED_ISSUER', 'STATS_YOUTUBE_TEST_ZIP')) {
    Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
}
.\.venv\Scripts\python.exe -u -B -m pytest -q -p no:cacheprovider --basetemp "$fixtureRoot\pytest" --ignore=tests/test_analysis_correlation.py --ignore=tests/test_saved_insights.py --ignore=tests/test_saved_insights_ui.py --deselect=tests/test_growth_ui.py::test_saved_diagnosis_is_a_fixed_manifest_verified_view *> "$fixtureRoot\portable-tests.log"
$LASTEXITCODE
```

Use a disposable PowerShell process or restore environment values afterwards;
never persist the temporary `STATS_DATA_DIR` as the application's configuration.
The setup rerun passed with exit code 0: **968 passed, 99 skipped, one deselected**
in 63.20 seconds, matching the migration baseline. The successful run used native
Windows socket access and a short OS-temp fixture path. Sandboxed asyncio
loopback initialization stalled before the first synthetic UI test; a long
diagnostic fixture path also exceeded a Windows ZIP path limit. Neither required
application changes or additional test exclusions. Logs and setup readbacks are
outside Git under the Codex visualization artifacts for this setup chat.

Historical correlation and fixed-report fixtures require optional private packages deliberately
excluded from this checkout. Do not reconstruct them or describe the complete
private-data suite as passing. Skips and unavailable report views remain explicit.

## Recovery and Git hygiene

Keep new private payloads, credentials, logs, generated outputs and receipts outside
the checkout; the existing `.venv` remains ignored. `current-app/.gitignore` covers
maintained app artifacts. Additive local exclusions were installed in
`.git/info/exclude` for root private/generated directories, environments, logs,
databases and credentials; they protect this checkout without changing the
historical root `.gitignore`. These local rules do not travel with a Git clone.

Do not alter the dated recovery snapshots, historical manifests, checksum inventory,
`.gitattributes` or backup verification contract. The root `.gitignore` is itself
checksummed. New guidance is additive and does not replace those historical bytes.
From the outer root, `current-app/.venv/Scripts/python.exe -B verify_backup.py`
checks the original 176 entries without importing the app or opening its databases.
All 176 checksum checks passed during this setup.

Setup leaves the existing checkout and environment ready for the next development
task. Initial setup left these guidance files uncommitted. Subsequent source
changes follow explicit Git commit/push requests. Recheck Git changes and installed
sessions before editing or runtime use.

## Dedicated monochrome Windows view — October 30, 2026

The user's desktop identity is Matrix / [REDACTED] in **black and white**.
The original couch artwork is unchanged. Dashboard presentation uses neutral
surfaces, terminal headings, white focus states and a static line texture;
explicit analytical series colors and missing-data behavior remain intact.

Desktop source, offline build instructions and isolated checks are in
[`current-app/desktop/`](../current-app/desktop/README.md). The tested local package
is `current-app/outputs/desktop/The-Stats-20261030-r2/TheStats.exe`, with a
`DESKTOP-CHECKSUMS.json` identifying every delivered file and its source hashes.
Its source base is `a876726ad04a183ea49e3e743073af84e9ebc836` plus the explicitly
recorded uncommitted feature changes. Binaries remain ignored and outside source
control. A **The Stats** shortcut on Jude's desktop targets this package.

This is a dedicated view of the existing protected session. **Open INTERLINKED**
activates the installed controls; **Reload** revalidates and reconnects. Closing
the desktop view leaves the backend running. It never becomes a second launcher
or cache owner. Production uses the reviewed machine/source/connection, current
process identity and local readiness endpoint; it accepts no arbitrary URL or
data-directory override. The separate InPrivate WebView2 profile is under
`%LOCALAPPDATA%\TheStatsDesktop\WebView2`.

The package bundles the pinned WebView2 SDK libraries and notices. THIS-MACHINE
supplies .NET Framework 4.8, the installed WebView2 Runtime, INTERLINKED and the
existing Python environment. This is local-machine delivery evidence, not a
self-contained Python distribution or clean-machine portability claim.

Validation: the revised dashboard's isolated portable scope passed **968 tests,
99 skipped, one deselected**, exit 0, in 84.23 seconds. The package passed **34
refusal/policy/copy/health checks and ten native WebView2 checks**, with nine payload
hashes verified. The native fixtures never opened the managed library. Detailed
receipts and logs remain outside Git in this chat's visualization artifacts.
The corrected header uses separate logo, title/tagline and control columns.
Native checks verify text fit and non-overlap at the default width and the
980-pixel minimum. The delivered executable SHA-256 is
`f79583e18ac5800a0c98ef871ec4271684003668ed192fc96ffdface2d1f6247`.

Live acceptance on October 30: the installed INTERLINKED controls restarted
Stats against the same local library (backend PID `47392`). The delivered native
window (PID `54300`) displayed the full band header without overlap and the
populated Overview with `meta-story-backfill-20261024` selected. The observed
Overview showed 4,246 streams and 1,062 period-unique listeners for its unchanged
latest-28-day comparison. No source selector, import or registration action was
performed. All five registry hashes and all three runtime pins matched the
fresh pre-launch snapshot; nine analyses, two YouTube collections and one each
of Shopify, Linktree and TikTok remained registered. The Stats desktop shortcut
was read back pointing at the corrected package. This is an agent walkthrough
of Overview and header rendering, not acceptance of every analytical view or a
user-confirmed review of all results. Stats was left running with the native
window open. At the end of that walkthrough, source changes were local and
uncommitted. Subsequent publication follows explicit Git commit/push requests.
