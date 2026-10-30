# The Stats desktop window

`TheStats.exe` gives The Stats its own monochrome Windows window, native taskbar
identity and band header. It displays the original couch logo without changing its
bytes. The maintained dashboard runs inside Microsoft WebView2; the ordinary
Windows title bar provides minimize, maximize, resizing and close.

INTERLINKED remains the owner of the running Stats backend, its data directory,
runtime pins and cache lock. Start The Stats using its installed Stats controls,
then open `TheStats.exe`. **Open INTERLINKED** activates the existing installed
program; **Reload** reconnects after checking the current managed session. Closing
this desktop window leaves Stats running. Use INTERLINKED's **Stop The Stats**
before an explicitly requested library save or release.

This first desktop version attaches to the protected session. It does not fetch,
initialize, import, save, release or synchronize a library, and does not start or
stop Python. If the session is missing, stale, changed or unavailable, it shows
the existing INTERLINKED route instead of opening a replacement library.

## Offline build

Requires Windows x64, .NET Framework 4.8 and Microsoft WebView2 Evergreen Runtime.
The existing Framework C# compiler builds the shell; no .NET SDK or Python package
installation is needed. Supply the already reviewed official WebView2 SDK archive
and extracted directory. The archive is `webview2.nupkg`, beside `webview2/`.

- SDK: `Microsoft.Web.WebView2` **1.0.4314.35**.
- Archive SHA-256: `90778deb1b77e36292828b4b5833c9255c27533f40e0ddd55891ae718944edc4`.
- Existing reviewed dependency directory on THIS-MACHINE:
  `C:\Users\Jude\Documents\Codex\INTERLINKED\.handoff\desktop-build\deps\webview2`.

From `current-app/`:

```powershell
.\desktop\Build-Desktop.ps1 -DependencyRoot 'C:\Users\Jude\Documents\Codex\INTERLINKED\.handoff\desktop-build\deps\webview2' -OutputDirectory '.\outputs\desktop\build-001'
```

Use a new empty output directory. The build verifies the pinned NuGet archive and
every extracted dependency member before copying. Its `DESKTOP-CHECKSUMS.json`
records source hashes, the base Git commit, dirty working-tree state, SDK provenance
and hashes for every delivered executable, library, configuration and branding
file. A dirty build is explicitly not represented as code contained in that Git
commit. The original logo is copied byte for byte; the `[S]` icon is drawn by build
code. Generated binaries, profiles and receipts stay outside Git.

The shell reads only the installed Stats connection/owner/session metadata, pinned
runtime files, process identity and loopback readiness endpoint. It does not open
SQLite or obtain a library lease. The process PID, executable and creation time
must match the current `RUNNING` journal. Changed sessions require a fresh validated
Reload. Production accepts no alternate URLs or data paths.

## Isolated validation

```powershell
.\desktop\Test-Desktop.ps1 -PackageDirectory '.\outputs\desktop\build-001' -FixtureDirectory 'C:\private\new-stats-desktop-fixture'
```

The fixture directory must be new and outside the source, installed kit and managed
cache. Self-tests cover origin/resource/download restrictions, changed pins, stale
sessions, process identity and refusal of production URL overrides. The native
smoke check starts its own in-process loopback server with conspicuously synthetic
values and an isolated WebView2 profile, then exits its own preview window. It never
opens the existing library, starts/stops its backend, or invokes INTERLINKED.
Windows socket and WebView2 initialization may require native execution outside a
restricted sandbox. Timeout preserves the preview process for inspection.

For a visible synthetic preview, run the built executable with:

```powershell
.\outputs\desktop\build-001\TheStats.exe --preview --fixture-directory 'C:\private\new-stats-preview'
```

Production WebView2 uses an InPrivate profile under
`%LOCALAPPDATA%\TheStatsDesktop\WebView2`, outside the managed cache and Git.
Host objects, web messages, developer tools, password/autofill storage and browser
permissions are disabled. Documents/resources remain on the exact validated local
origin. Deliberate public HTTPS links open in the default browser;
credential-bearing query parameters and suspicious fragments are
refused while ordinary documentation anchors remain usable. Local report downloads use an explicit native Save dialog. The dedicated
window cannot publish or change the INTERLINKED control service's authenticated
state and never reads its private token.

Synthetic checks, a source build and actual populated-library visual acceptance
are separate evidence. Building does not replace or reseal the installed
INTERLINKED kit, alter Stats' interpreter/dependency lock/launcher, or deploy a new
backend connection.
