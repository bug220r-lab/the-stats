# The Stats™️

A private music and social reporting dashboard for Lewis, Brandon, and Samman. Python runs the application backend on this Windows PC; your browser provides the interface. The existing Streamlit, Plotly, pandas, and SQLite application now includes the audited music and marketing analysis. Local use needs no account, API key, cloud database, Docker, WSL, or paid service.

**October 26 Spotify Growth Analysis release:** The spacious interface, grouped navigation, source-backed findings, Apple Music and Linktree views are available. The [dated release handoff](outputs/gui_growth_release_20261026/HANDOFF.md) includes final checks, screenshots and rollback instructions. The 200% zoom check is explicitly deferred and unverified at the user's request.

**October 24 data integration:** Data quality and Coverage show coverage derived from the selected analysis, with older assessments retained as historical receipts. Social publishing and Decision content summaries use the expanded posts-and-Stories inventory with distinct identities, compatible metric scopes and separate capture-day groups. Spotify → Audience & sources → Audience segments exposes retained segment history, audience movement and rolling super listeners. Overview can use a separately recovered listener total only when its dates and scope exactly match the comparison. See the [implementation and verification handoff](handoff/DATA_INTEGRATION_20261024.md).

**October 23 re-audit and dashboard update:** The [historical audit and corrections](docs/REAUDIT_2026-10-23.md) and [verified handoff](handoff/REAUDIT_20261023.md) describe their acquisition-time source state. Overview and Decision report support explicit reporting periods; song, content and video filters are preserved across navigation. Instagram follows use the approved repair, incompatible prior audiences are withheld, and import preview reports exact changes without saving production records. Use the source selector beside each page's context to select saved versions, and **Data & tools → Sources & provenance** to inspect sources.

The native sidebar groups **Overview**, **Explore**, **Analysis**, and **Data & tools**. Explore includes Spotify, Apple Music, YouTube, Social, TikTok, Linktree, and Shopify. Analysis includes Growth diagnostics, Cross-platform, Decision report, Saved diagnosis, and TikTok insights. Data & tools keeps Data quality, Sources & provenance, Snapshot explorer, Coverage & cross-reference, Meta collection, Campaigns, and Import data reachable. Unavailable sources retain stable routes with an explanation; the current page is highlighted.

**October 23 decision workflow:** **Decision report** recomputes source-backed growth, follower changes, complete weeks, post-spike activity, songs, content distributions and audience opportunities for the selected immutable analysis version. **Campaigns** adds a validated CSV metadata log with preserved originals and deterministic revisions. See the [decision workflow and refresh command](docs/DECISION_WORKFLOW.md), [historical source assessment](docs/SOURCE_AUDIT_2026-10-23.md) and [campaign log](docs/CAMPAIGNS.md). The app's selected version and live registry determine which saved inputs are active; six reviewed October Story identities have verified ownership, while their soundtracks remain unresolved.

## Start on Windows

1. Open this project folder in File Explorer. Double-click **setup_windows.bat**. Initial setup needs internet access to download the pinned Python packages. It reuses the project's compatible `.venv` or creates one with 64-bit Python 3.12.
2. After setup succeeds, double-click **launch_windows.bat**. Keep its console window open. Your default browser opens when the server is ready at **http://127.0.0.1:8501**.
3. To stop the application, return to the launcher console and press **Ctrl+C**. Closing a browser tab does not stop the application. Restarting the launcher or browser keeps imported records.

From PowerShell opened in the project folder, the equivalent commands are:

```powershell
.\setup_windows.bat
.\launch_windows.bat
```

The launcher resolves its own folder, so a shortcut or double-click works regardless of the current directory. It always uses `.venv`, binds to `127.0.0.1`, and rejects an occupied port. Setup does not install or upgrade system Python, open firewall ports, or change system-wide security settings. The setup batch uses a PowerShell execution-policy override for that one process only.

If Python is missing, install **64-bit Python 3.12** from the [official Windows downloads page](https://www.python.org/downloads/windows/), including the Python launcher, then run setup again. The existing development environment was created with Python 3.12.14. The setup script also recognizes a compatible Codex-provided Python when available; that runtime is optional. See [Windows setup and troubleshooting](docs/WINDOWS.md).

## Import and inspect data

**Shopify merchandise — October 25, 2026:** A separately dated collection adds native sales, orders, products and variants, inventory, traffic, marketing/customer summaries and accessible payment evidence to **Shopify** in the existing sidebar. Coverage and missingness remain explicit; saved analysis versions and the October 20 reporting history retain their original inputs. See [Shopify collection, interpretation and import](docs/SHOPIFY.md) and the [collection handoff](handoff/SHOPIFY_INTEGRATION_20261025.md).

**Program audit repairs — October 25, 2026:** CSV imports preserve ordinary `Day`/`Date` values, conflicting metric definitions stop the import, original-source downloads verify their hashes, and analysis promotion/staging have stronger recovery and completeness checks. See the [repair record and validation](docs/PROGRAM_AUDIT_REPAIRS_20261025.md).

**TikTok insights — October 27, 2026:** **Analysis → TikTok insights** (`/tiktok-insights`) presents the saved cross-platform findings, trends, song priorities, post examples, other-platform findings, and sources. This fixed October 27 report is independent of the analysis selector. Downloads include a complete offline HTML report, Markdown, provenance, and evidence CSVs. The report now runs inside The Stats without the unavailable reporting plugin; the earlier draft and verification receipts are preserved. See the [TikTok insights and strongest-post guide](docs/TIKTOK_INSIGHTS_20261027.md).

**TikTok Studio integration — October 27, 2026:** **Explore → TikTok** supports the authenticated **@funnyguycrawl** collection: account activity, 615 owned-post snapshots, audience reports, content rankings, recent comments, and retained source evidence. **Strongest posts** separates TikTok's native 7/28/60/365-day rankings from cumulative post snapshots, with scoped CSV downloads and verified links where captions resolve unambiguously. The initial exports supply the preferred source-labeled October 26, 2025–October 25, 2026 calendar; conflicting later relabelings remain inspectable and are excluded from daily activity. Reporting timezone is unknown. The separate dated collection preserves existing analyses and original exports. **TikTok for Artists remains pending.** See [date decisions, import and interpretation](docs/TIKTOK_STUDIO_INTEGRATION_20261027.md). The [preparation commands](docs/TIKTOK_PREPARATION.md) remain available for future captures; an empty library keeps the preparation view.

**Apple Music imported — October 25, 2026:** **Data & tools → Snapshot explorer** now exposes Apple Music in two sealed, non-baseline snapshots: `apple-music-20261025-daily` (25,738 observations) and `apple-music-20261025-aggregate` (950 observations). Daily Plays and daily unique listeners remain separate from period/monthly facts. Latest-28 artist Plays is 507 in each compatible scope; these overlapping views must not be added together. See the [import and verification handoff](handoff/APPLE_MUSIC_IMPORT_20261025.md). Existing baseline records and analysis versions were preserved.

**Apple Music native-export preparation:** The separate export inspector and staging tool remains available for future raw CSV mappings. Literal column mappings, original bytes, reporting bounds, listener definitions and missing-value states stay inspectable. See the [source collection checklist](docs/APPLE_MUSIC_INTEGRATION_20261025.md) and [local preparation commands](docs/APPLE_MUSIC_PREPARATION.md). That earlier preparation-only verification is separate from the verified canonical collection import above.

Use **Import data** to upload a CSV, TSV, or XLSX file. Keep the original export unchanged. For this generic uploader, ZIP archives must be extracted first; choose a data file inside the extracted copy. For XLSX, choose the worksheet explicitly. The verified YouTube collection ZIP uses its dedicated importer described below.

**YouTube collection** provides the October 23, 2026 collection for **[REDACTED] TV / @redactedbandoh**, independently of the analysis-version selector. It retains the channel, video, discovery/audience, retention, song-mapping, source and coverage tables with their exact reporting scopes. Reporting dates are Pacific calendar dates; retrieval timestamps are separate download-modification proxies. The historical report ending October 20 is newly retrieved history, and does not establish Spotify baseline membership. See [YouTube import and interpretation](docs/YOUTUBE.md) for the idempotent ZIP command, private storage, coverage limitations and validation.

The separate **YouTube daily supplement — retrieved 2026-10-23** adds four complete 365-date native series for watch time, average view duration, and subscribers gained/lost. Average duration retains 12 source blanks; reported zeros remain distinct. Select it beside the YouTube page source context. The original package and all analysis versions remain unchanged; see the [supplement handoff](handoff/YOUTUBE_DAILY_SUPPLEMENT_20261023.md).

On this PC, **Overview**, **Spotify**, **Social**, **Cross-platform**, and **Data quality** use the separately persisted cleaned analysis package. They provide matched-period KPIs, recording comparisons, complete-period social activity, lifetime content and publishing filters, all 12 planned exploratory comparisons, and quarantine/source inspection. The literal band name is **[REDACTED]**; The Stats™️ is the project name.

**Cross-platform → Posts & Spotify → Spotify spikes** ranks absolute increases in weekly streams or average daily listeners. Click a bar or select a rising week to inspect the daily Spotify trend and nearby posts and Stories. Choose the previous, selected, and optionally following week; filter content types or search captions, IDs and links. Expand an item for its full retained caption and original permalink. CSV downloads preserve the filtered content, ranking and displayed daily activity. The selected saved analysis version supplies all values; no source is modified. Missing captions and disputed dates remain explicit, and these alignments do not establish that a post caused a Spotify increase.

The spike chart follows a compact summary of the metric, period, selected week and increase. **Edit filters** opens the metric, period and week controls; chart clicks update the summary automatically. Custom periods show their exact dates, and incomplete or empty selections remain explicit. The chart starts with five spikes; **Show 12 spikes** expands it on the page and **Show fewer** collapses it. Counts adapt to the available increases. A selected week outside the displayed bars stays selected and shows its rank; chart size does not change nearby posts or CSV downloads. **How to read this chart**, collapsed below the chart controls, contains the introduction, weekly comparison definitions, listener-count explanation, and interaction instructions.

Below the chart, a compact weekly strip shows streams and average daily listeners with their changes and previous values. One shared date line identifies both comparison weeks. The percentage change appears beside the selected metric; a zero baseline is explicitly marked as unavailable for percentage calculation.

After recovery activation, **Analysis version** switches between the original cleaned analysis and the expanded Spotify version without changing either. **Spotify → Recovered sources** filters cumulative source evidence by entity, country, window, metric and hierarchy. **Recovery evidence** and **Data quality** show current coverage, remaining limitations and the before/after change log. See [additional-data integration](docs/ADDITIONAL_DATA.md). Earlier statistical results retain their original input version; new source rows do not create independent statistical samples.

**Snapshot explorer** preserves the earlier Windows and recovered Spotify/Facebook/Instagram snapshots plus three additional Spotify snapshots. **Coverage & cross-reference** shows the earlier archive's source gaps and reconciliation evidence. These snapshots remain separate from the newer cleaned analysis and must not be summed together. Registered archives and analysis are read-only; new uploads go into the existing local database. See [recovery and snapshot scope](docs/RECOVERY.md) and the [current handoff](handoff/HANDOFF.md).

In **Import data**, **Load preserved native Spotify archive** loads only the five native daily CSVs. It verifies source hashes and seals this small archive, without establishing original baseline membership. The equivalent command is `.\.venv\Scripts\python.exe -m stats_app.seed`; repeating it leaves existing observations unchanged. A fresh checkout without private sources or a registered archive shows an honest empty state.

1. Choose **Spotify daily timeline**, **Meta daily export**, or **Canonical / mapped CSV or Excel**. The canonical profile is also the explicit route for TikTok and unsupported export layouts. There is no live platform connection.
2. Supply the actual account and entity identity, reporting meaning, provenance, and a descriptive snapshot label. For canonical data, map source columns to the documented fields. Use ISO dates (`YYYY-MM-DD`); leave an unknown capture timestamp blank.
3. Review the normalized preview and validation results before committing. A rejected import makes no partial database change. Missing, suppressed, or unavailable values remain absent; only an explicit observed `0` is zero.
4. Import the validated preview. Use **Snapshot explorer** (or **Overview** when no analysis package is installed) to filter an imported snapshot and inspect its chart. Use **Sources & provenance** to review source files, reporting coverage, and import history.

Importing the same source and interpretation again into the same snapshot is handled as a duplicate. Matching overlapping observations are not counted twice. Contradictory observations require a separately labeled snapshot; the application does not silently overwrite an existing value. A genuinely newer export belongs in a new snapshot even when its reporting dates overlap earlier history.

The Spotify source package was **collected October 22, 2026**, with a common **reporting endpoint of October 20, 2026**. The original October 20 baseline remains **unavailable/unverified**. A reporting endpoint and a sealed snapshot do not prove baseline membership. The earlier Windows database label remains unchanged as historical metadata; the dashboard displays it as an unverified legacy archive. Newer snapshots remain separate, including observations whose reporting bounds are unknown.

## Persistence and backups

The authoritative store is SQLite, not browser storage or Streamlit session state. By default the Windows database is `%LOCALAPPDATA%\TheStats\stats.sqlite3`, outside the OneDrive project directory. Keep this database on a local disk, not in a synchronizing folder or network share. Original files remain unchanged; committed imports retain source bytes and provenance in the database.

Back up the database using SQLite's consistent backup API. From the project folder:

```powershell
New-Item -ItemType Directory -Force .\backups | Out-Null
.\.venv\Scripts\python.exe -m stats_app.backup --output .\backups\the-stats-backup.sqlite3
```

The command above backs up local uploads only. The recovered archive is a separate database, with source files and evidence under `archives/` and an `archive_registry.json` alongside the writable database. Use the [complete library backup procedure](docs/ARCHIVE_BACKUP.md) to retain all snapshots together. Keep dated backups on another protected disk or backup service. Restore into a **new empty** data directory and set `STATS_DATA_DIR` before launching. Do not overwrite an active database or combine a backup with old `-wal`/`-shm` files.

## Configuration

Environment variables are optional for normal local use. They can be set in the PowerShell session that starts the batch launcher. Example:

```powershell
$env:STATS_PORT = '8502'
$env:STATS_DATA_DIR = Join-Path $env:LOCALAPPDATA 'TheStats'
.\launch_windows.bat
```

| Variable | Purpose / default |
| --- | --- |
| `STATS_MODE` | `local` by default. `hosted` activates required authentication and authorization; the Windows launcher accepts only `local`. |
| `STATS_PORT` | Local port, default `8501`; valid range `1024`–`65535`. |
| `STATS_DATA_DIR` | Durable data directory. Default Windows `%LOCALAPPDATA%\TheStats`; Linux `$XDG_DATA_HOME/the-stats` or `~/.local/share/the-stats`. |
| `STATS_IMPORT_DIR` | Optional source location for the import workflow. |
| `STATS_PYTHON` | Optional complete path to a 64-bit Python 3.12 executable when creating `.venv`. |
| `STATS_APPROVED_USERS_FILE` | Hosted-only JSON approved-user list; see placeholder example. |
| `STATS_EXPECTED_ISSUER` | Hosted-only exact HTTPS provider issuer; must match authenticated claims and the approved-user list. |

Relative data/configuration paths resolve against the project folder. Environment variables persist only for the current PowerShell session unless you explicitly configure them elsewhere. The application does not automatically load a `.env` file.

## Development and future hosting

`requirements.in` records direct dependencies; `requirements.lock.txt` pins the full installed dependency set, and `requirements.txt` includes that lock. Setup uses the lock file. Do not commit `.venv`, local databases, private exports, actual approved-user identity files, secrets, or backups. Placeholder examples are safe to edit into local ignored configuration files.

The code separates ingestion (`stats_app/ingestion.py`), validation (`validation.py`), persistence (`storage.py`, `archive_repository.py`, `analysis_repository.py`), calculations (`calculations.py`, `analysis_metrics.py`, `analysis_social_metrics.py`), configuration/access control, and presentation (`ui.py`, `analysis_ui.py`, `analysis_social_ui.py`). Storage access is confined to repository layers so the dashboard can later use a different database implementation. The audited statistical outputs are retained as delivered, rather than recomputed on each filter change. [Reproduce the pipeline](docs/ANALYSIS_REPRODUCTION.md) in a separate output copy.

Run the automated checks from PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

To run without opening a browser, use `launch_windows.bat --no-browser`. The tests use temporary data. Actual test execution and remaining limitations are reported in the milestone handoff; a command documented here is not a claim that it ran.

Nothing is deployed by this project. [Private hosting requirements](docs/HOSTING.md) cover Linux, durable storage, backups, simultaneous users, provider sign-in, and approved viewer/admin roles. See the [import reference](docs/IMPORTS.md), [metric rules](docs/METRICS.md), and [milestone verification](docs/VALIDATION.md) for exact scope and evidence.


## Spotify growth analysis release — October 26, 2026

The native sidebar groups Overview, Explore, Analysis, and Data & tools. Every destination has a stable route, including unavailable sources. Overview starts with the latest 28 loaded Spotify days; it is not a live platform refresh. Streams, exact period-unique listeners, and net followers retain separate definitions. Findings open their supporting diagnostics and retained source evidence.

Growth diagnostics compares signed recording contributions, explicit playback-source panels, and release-age means. Nearby social evidence keeps its native dates and typed identities. The October 25 diagnosis is a separate fixed historical reference. Changing live filters never relabels its dates or inputs.

Apple Music uses the registered sealed snapshots. Linktree uses a separately registered verified copy of the existing October 25 package. Daily/period listeners, configured destinations, clicks, and downstream streams remain distinct. Linktree's unknown timezone prevents silent daily alignment, and its unavailable service-click cells, partial day, rates above 100%, and discrepancies remain visible.

Reset this view preserves saved source choices and selections on other pages. Advanced evidence is opened on demand; filtered CSVs retain their original-compatible fields. The Windows launcher, project-local environment and loopback binding remain unchanged.

Linktree validation and explicit registration (registration is already complete for this release):

```powershell
.\.venv\Scripts\python.exe scripts/import_linktree_collection.py --package-dir data/collection/linktree-20261025
.\.venv\Scripts\python.exe scripts/import_linktree_collection.py --package-dir data/collection/linktree-20261025 --data-dir "$env:LOCALAPPDATA\TheStats" --execute
```

The importer verifies the manifest and checksum inventory independently, copies retained bytes, and checks idempotent replay. Opening the app never runs package normalization or finalization scripts. Complete library backups include the Linktree registry and exact package. See the [dated handoff](outputs/gui_growth_release_20261026/HANDOFF.md) for release checks, screenshots, source receipts and guarded rollback instructions.
