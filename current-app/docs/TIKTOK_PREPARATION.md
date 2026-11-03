# TikTok import preparation

**October 26 readiness extension:** The existing application now has an **Explore → TikTok** preparation page and a separate collection workspace workflow. See [the collection runbook](TIKTOK_COLLECTION_20261026.md). The inspector and staging tool described below remain preparation-only; no genuine performance collection or library activation is established by the new page.

Prepared October 25, 2026. TikTok now has a separate local preparation path for inspecting original CSV files, explicitly mapping fields, validating metric meaning and staging evidence. It does not connect an account, commit to SQLite, register an analysis, add a dashboard page or generate Spotify/Apple Music correlation results. A genuine export is still needed to verify native layouts and source definitions.

Read the [native collection checklist and official sources](TIKTOK_INTEGRATION_20261025.md) first. This pass accepts explicitly identified Studio, TikTok for Artists and Business Suite CSV evidence. It does not treat consumer watch history, Ads Manager, Shop, LIVE or public API counters as interchangeable sources.

## Inspect the original file

Preserve the download unchanged. Replace the example path with the real file and create a fresh working directory in project PowerShell:

```powershell
$tiktokExport = 'C:\path\to\original-export.csv'
$tiktokWork = Join-Path (Get-Location) ('data\tiktok_preparation_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $tiktokWork | Out-Null
.\.venv\Scripts\python.exe scripts\prepare_tiktok.py inspect --input $tiktokExport --output (Join-Path $tiktokWork 'schema.json')
```

Inspection preserves literal headers, source hash, size and a bounded sample. It guesses neither the native profile nor the meaning of a field. Explicit options are `--encoding`, `--delimiter comma|tab|semicolon` and one-based `--header-row`. The default is UTF-8 comma-separated input with the header in CSV record 1. Duplicate normalized headers and ragged records reject instead of silently losing fields. XLSX/ZIP/JSON inputs need a separately verified adapter or a documented derived copy; keep the original rather than resaving it as an assumed native CSV.

## Map the actual report

The templates below are **The Stats contracts, not TikTok's native headers or sample data**:

- `templates/tiktok.account_daily.mapping.template.json`: real dated account activity, net follower change and follower balances.
- `templates/tiktok.video_snapshot.mapping.template.json`: video counters and watch metrics captured as a snapshot, with optional caption, publication, link and sound fields.
- `templates/tiktok.song_daily.mapping.template.json`: real dated TikTok for Artists song-associated views and posts across creators.
- `templates/tiktok.metadata.template.json`: selected account, source family, source entity, content scope, report clock, capture evidence, bounds and filters.
- `templates/tiktok.sound_recording_crosswalk.template.csv`: an empty future identity-review worksheet. It is not an active sound/recording match.

For an actual daily account export, copy these into the new working directory:

```powershell
Copy-Item -LiteralPath templates\tiktok.account_daily.mapping.template.json -Destination (Join-Path $tiktokWork 'mapping.json')
Copy-Item -LiteralPath templates\tiktok.metadata.template.json -Destination (Join-Path $tiktokWork 'metadata.json')
```

Edit the copies after inspecting the native file and its selected view:

1. Replace placeholder headers with exact source strings. Remove mappings for unavailable columns and remove absent metric specifications. Do not fill absent metrics with zero or map a similarly named number without its reporting meaning.
2. Supply the real source account and stable entity ID, or map IDs from the file. IDs remain strings, including leading zeros. Set `entity_type` to `account`, `video` or `song` according to the source row grain. The default account template does not establish the identity of the band's TikTok account.
3. Set `source_family` to the actual `studio_csv`, `artists_csv` or `business_suite_csv`. Own account/video observations require `content_scope: band_owned`. Song-associated community observations require `artists_csv`, `entity_type: song` and `content_scope: all_creators`. Artist-source own-post/account exports remain labelled TikTok for Artists instead of being relabelled Studio.
4. Set actual report scope, filters and reporting timezone. Keep an unverified clock `unknown`; do not copy Apple's UTC assumption. Capture time is separate from reporting dates and stays blank when unknown. If supplied, it needs its actual offset.
5. Choose daily, period or snapshot grain. Daily activity requires real metric-date rows. Period data requires source or explicit metadata bounds. A mapped blank date never falls back to a metadata constant. Publication dates never supply metric coverage.
6. Map optional `caption`, `caption_status`, `publication_date`, `published_local`, `permalink`, `sound_id`, `sound_title`, `song_id`, `song_title` and `author_id` fields when present. A blank caption is missing source text, not a verified native no-text statement. Publication text remains raw; `publication_date_format` may separately parse an actual date without inferring timezone or within-day order.
7. Set exact date and number formats. Supported numeric formats are `plain` and `us_grouped`. Unknown tokens, abbreviated counts and duration strings are not guessed. Map exact missing/suppressed/unavailable tokens only after their meaning is verified.

For a period report, use `time_grain: period` and map `period_start` / `period_end`, or supply the actual inclusive bounds in metadata when those columns are absent. This is useful for an account or song summary whose date window appears only in the UI. Never create daily rows from a period total.

For video snapshots, set `entity_type: video`, keep the actual capture evidence and preserve the literal publication fields. Unknown metric bounds remain empty; a parsed publication day does not become the start of a lifetime metric. Such records may be valid review evidence while `canonical_import_eligible` remains false. Explicitly mapped blank snapshot bounds likewise remain unknown rather than borrowing metadata. This flag is not permission to activate a collection: all native semantics still require reconciliation.

## Metric and unit rules

| Internal metric IDs | Required interpretation |
|---|---|
| `video_views`, `profile_views`, `likes`, `comments`, `shares`, `saves` | Integer counts. Use `period_count` for daily/period activity and `cumulative_count` for snapshots. Profile views are account-level. |
| `followers` | Account balance, `point_in_time`; never summed as new follows. A known endpoint is one date. |
| `net_followers` | Explicitly reported signed `period_count` for an account. No other prepared metric accepts negative values. It does not mean gross new follows. |
| `unique_viewers` | `distinct_count`, non-additive across dates, content or platforms. |
| `total_watch_time` | `period_sum` for activity or `cumulative_sum` for a snapshot, with explicit seconds/minutes/hours retained. No automatic conversion. |
| `average_watch_time` | `average` in seconds. No unweighted averaging across videos. |
| `completion_rate`, `engagement_rate` | `rate`, with explicit `percent` (0–100) or `ratio` (0–1). The source definition must retain its denominator. A percent suffix requires `allow_percent_suffix: true` and unit percent. No rescaling is inferred. |
| `song_video_views`, `song_video_posts` | Artist-source song/community counts, with `period_count` or snapshot `cumulative_count`. These are not artist-authored publishing counts, unique creators or music-streaming plays. |

The first-pass song adapter does not assign an invented formula to creator engagements. Demographic, paid, campaign, revenue and further native metric families require their own reviewed definitions/adapters if supplied later.

## Preview, compare and stage

```powershell
.\.venv\Scripts\python.exe scripts\prepare_tiktok.py preview --input $tiktokExport --mapping (Join-Path $tiktokWork 'mapping.json') --metadata (Join-Path $tiktokWork 'metadata.json') --output (Join-Path $tiktokWork 'preview.json')
.\.venv\Scripts\python.exe scripts\prepare_tiktok.py stage --input $tiktokExport --mapping (Join-Path $tiktokWork 'mapping.json') --metadata (Join-Path $tiktokWork 'metadata.json') --output (Join-Path $tiktokWork 'stage-01')
```

Exit code 0 means the operation completed; exit code 2 means rejection or a failed operation. Inspect both `accepted` and `canonical_import_eligible`, all issues, retained source meaning, scope and dates. A snapshot with unknown metric bounds can be accepted as review evidence but ineligible for the generic canonical importer. Neither flag establishes native authenticity or a validated relationship to Spotify listening.

Every stage uses a new directory. It contains original bytes under `raw/`, exact mapping/metadata under `config/`, normalized review rows under `normalized/`, issues under `review/`, a preview and a hashed receipt. Rejected stages remain `accepted: false`; their partial rows are not accepted data. Existing outputs and AppData/live-library destinations are refused.

Compare a later file with a prior TikTok stage without copying prior observations into the new dataset:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_tiktok.py preview --input $tiktokExport --mapping (Join-Path $tiktokWork 'mapping.json') --metadata (Join-Path $tiktokWork 'metadata.json') --compare-observations 'C:\path\to\prior-stage\normalized\observations.csv' --output (Join-Path $tiktokWork 'comparison-preview.json')
```

Identity, source family, content ownership, definition, scope, reporting clock, dimensions and filters remain part of the comparison boundary. Fixed scope/filter ownership also travels in canonical `dimensions_json` under reserved `_tiktok_scope`; that key cannot be shadowed by a source dimension. New captures, possible replays, conflicting same-capture values and overlapping or unknown periods remain explicit. The tool neither sums snapshots nor chooses a preferred revision.

## Native-data integration gate

Start with the original native account/post export, profile/account identity, and evidence of the selected dates, filters and clock. If artist song data is available, retain it separately with the original song/sound IDs. Verify file layout, reporting grain, units, missing tokens and native reconciliation before registering a separate immutable TikTok collection.

Then prepare the dashboard views through the existing step-by-step design process. Publication/caption exploration can use verified content metadata; daily Spotify or Apple Music spike comparisons require compatible real dates and metrics. Native song/sound mapping must be reviewed before cross-platform joins, and views or song-associated posts cannot prove streaming conversion.

The [October 25 verification handoff](../handoff/TIKTOK_PREPARATION_20261025.md) records the implemented scope, executed tests and preservation checks. These checks use synthetic fixtures; actual account access, native export schema and reporting semantics remain unverified.
