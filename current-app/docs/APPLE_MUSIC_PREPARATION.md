# Apple Music import preparation

Prepared October 25, 2026. The local groundwork can inspect, explicitly map, validate, compare and stage an Apple Music for Artists CSV. It does not connect to Apple, import into the live SQLite library, activate an analysis version, add a dashboard page or calculate new cross-platform results. No genuine Apple export has been supplied for native-schema verification.

Use the [collection checklist and source definitions](APPLE_MUSIC_INTEGRATION_20261025.md) to obtain the first untouched file and its selected artist, dates, metric labels and filters. The first pass accepts **artist-dashboard CSVs** only. Provider API and Sales and Trends reports require separate adapters.

## Inspect the original

Keep the downloaded file unchanged. In project PowerShell, replace the example export path with the actual original, then use a fresh working directory:

```powershell
$appleExport = 'C:\path\to\original-export.csv'
$appleWork = Join-Path (Get-Location) ('data\apple_music_preparation_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $appleWork | Out-Null
.\.venv\Scripts\python.exe scripts\prepare_apple_music.py inspect --input $appleExport --output (Join-Path $appleWork 'schema.json')
```

Inspection records source identity/hash, literal headers and a bounded row preview. It does not guess which columns represent plays or listeners. For a known different layout, set `--encoding`, `--delimiter comma|tab|semicolon`, or the one-based `--header-row`. The default is a UTF-8 comma-separated table with its header on row 1. Native BOM-marked UTF-16 requires explicitly selecting the appropriate encoding. Unsupported or ambiguous layouts are rejected; do not fix them by modifying the original.

## Record the interpretation

These JSON templates are **The Stats mapping contracts, not examples of Apple's native headers**. Copy the appropriate one and the metadata template into the new working directory:

```powershell
Copy-Item -LiteralPath templates\apple_music.daily.mapping.template.json -Destination (Join-Path $appleWork 'mapping.json')
Copy-Item -LiteralPath templates\apple_music.metadata.template.json -Destination (Join-Path $appleWork 'metadata.json')
```

Use `apple_music.period.mapping.template.json` instead when the export contains selected-period totals. Select the actual source row grain before mapping. The period template includes content ID/name columns for a catalog breakdown; set `entity_type` to the verified content type. For a genuine artist-only period summary, remove the content-column mappings and supply its artist entity ID in metadata.

Edit the copies using the actual export and its captured report context:

- Replace placeholder mappings with exact literal source headers. Do not add an absent metric; remove its metric specification. A source column labelled only Listeners needs evidence that it is daily unique, average daily or period unique.
- Supply the actual Apple artist identity in `account`. Supply the actual source entity type and stable ID, or map IDs from the export. Apple song/track groups, release variants, ISRCs and Spotify IDs are not interchangeable. Do not join by title or infer an artist ID from the project name.
- Set `date_format` and `number_format` to the actual source formats. `plain` numeric mode accepts exact ungrouped numbers; use a supported explicit numeric mode only after inspection. Rounded K/M abbreviations are not exact counts.
- For period data without date columns, supply the actual inclusive `period_start` and `period_end` in metadata. Explicitly mapped date cells take precedence; a mapped blank does not fall back to metadata. Daily values require real dated rows and cannot be fabricated from a period summary.
- Record the actual report scope and filters, including geography or content filters. Use `UTC` for a verified Apple Music for Artists report; keep unknown reporting context explicit. An unknown capture time stays blank, while a known timestamp needs its actual offset.
- Configure exact source status tokens only after their meaning is established. Blank, suppressed, unavailable and observed zero are different. Unknown nonnumeric tokens block acceptance; the raw source text remains available.

First-pass metric IDs are `plays`, `daily_unique_listeners`, `average_daily_listeners`, `period_unique_listeners`, `shazams`, `radio_spins`, `song_purchases`, `album_purchases`, and `video_views`. Their measurement bases are checked. `daily_unique_listeners` requires daily grain; the two period listener measures require period grain. An unqualified `listeners` or a renamed Spotify `streams` field is not accepted. Listening Now remains outside this historical adapter.

The header-only `templates/apple_music.recording_crosswalk.template.csv` is a project worksheet for later identity review, not an Apple export or an active mapping. Preserve every Apple group/release relationship and source evidence. A shared title does not verify that an Apple reporting group equals a Spotify recording; do not combine their totals or listeners through this worksheet.

## Preview and stage

```powershell
.\.venv\Scripts\python.exe scripts\prepare_apple_music.py preview --input $appleExport --mapping (Join-Path $appleWork 'mapping.json') --metadata (Join-Path $appleWork 'metadata.json') --output (Join-Path $appleWork 'preview.json')
.\.venv\Scripts\python.exe scripts\prepare_apple_music.py stage --input $appleExport --mapping (Join-Path $appleWork 'mapping.json') --metadata (Join-Path $appleWork 'metadata.json') --output (Join-Path $appleWork 'stage-01')
```

Exit code `0` means the operation succeeded; exit code `2` means parsing/validation failed or the preview was not accepted. Review `accepted`, all errors and warnings, source scope and period meaning before treating a package as ready. Successful validation of a project mapping does not independently verify the native export's semantics.

Staging creates a new directory containing the original bytes under `raw/`, mapping and metadata under `config/`, normalized review rows under `normalized/`, issues under `review/`, a preview and a hashed stage receipt. A rejected review can also be preserved, with `accepted: false`; its partial normalized rows are not an approved import. Source row references and raw metric tokens are retained. Existing output paths are refused rather than overwritten.

For a later retrieval, compare it with a prior stage's normalized CSV:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_apple_music.py preview --input $appleExport --mapping (Join-Path $appleWork 'mapping.json') --metadata (Join-Path $appleWork 'metadata.json') --compare-observations 'C:\path\to\prior-stage\normalized\observations.csv' --output (Join-Path $appleWork 'comparison-preview.json')
```

The comparison reports compatible duplicate or overlapping observations without adding prior rows to the new output. It does not merge captures, pick a preferred revision or sum unique listeners. Repeated captures belong in separately retained stages until an explicit revision-selection policy is verified.

Report scope and fixed filters also travel inside the reserved `_apple_music_scope` object in canonical `dimensions_json`, alongside source row dimensions. Mapping a source dimension to that reserved key is rejected. This preserves the series boundary when inspecting the standard canonical columns.

## Next integration gate

With a genuine export available, verify the literal schema, reporting periods, metric labels, status tokens and entity IDs against the selected native view. Reconcile suitable on-screen totals with the accepted file and review all overlaps. Then implement a separate immutable Apple collection and its dashboard view, following the existing step-by-step GUI design process. Social/spike comparisons require compatible actual daily data; period summaries alone do not support them. Cross-platform listener counts must not be added into unique people.

Preparation verification is recorded in [the October 25 handoff](../handoff/APPLE_MUSIC_PREPARATION_20261025.md). All native-schema and account-access claims remain pending the genuine export.
