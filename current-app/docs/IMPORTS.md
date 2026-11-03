# Importing exports

Open **Import data**, upload a CSV, TSV or XLSX, or select a file from the folder configured by `STATS_IMPORT_DIR`. Select the worksheet for Excel. ZIP archives must first be extracted into a private folder. Source files are read without modification; the database retains the original bytes and SHA-256 hash.

Choose a named snapshot, verify the account and entity identity, select the format and mappings, then click **Validate and preview**. Review the normalized observations before **Save this preview to SQLite**. Changing form inputs does not change the saved preview until you validate again. Rows with errors block the entire file; they are not silently discarded.

The preview runs the actual importer against an isolated in-memory SQLite backup. It displays new observations and unchanged/duplicate rows; same-snapshot conflicts, sealed destinations and changed interpretations are rejected before save. The production database is not changed by preview. Saving validates again against the then-current database.

## Supported formats

| Format | Supported input and required context |
|---|---|
| Spotify daily timeline | Observed native `date` plus any of `listeners`, `monthly listeners`, `monthly active listeners`, `super listeners`, `streams`, `playlist adds`, `saves`, `followers`. Supply account, entity type and stable ID. Artist and track exports remain separate. |
| Meta daily export | Rectangular UTF-8 or BOM-marked UTF-16 table with `Date` or `Day`; one single-cell title immediately before a named daily header is supported. Ambiguous prefixes are rejected. Explicitly choose the value column, platform, account, entity, metric, unit, measurement type and definition. Dates must be ISO. Multisection audience/content reports need preparation as a separate canonical file. Installed native Meta collections use the separate versioned analysis pipeline; this generic adapter remains a distinct import path. |
| Canonical / mapped | The header-only `templates/observations.csv`, or a long-form table mapped to those fields. Use metadata fields only for columns absent from the file. Existing mapped cells, including blanks, take precedence over fallback metadata. |

The format suggestion is only a hint. Confirm platform and metric scope from the export's original metadata. For example, an Instagram-selected Meta Views report can combine Facebook and Instagram views. Preserve that combined scope; do not label it Instagram-only.

CSV requires comma separators; TSV requires tabs. Excel supports `.xlsx`. UTF-8 (with or without BOM) and BOM-marked UTF-16 are supported. IDs are read as text. Dates must use `YYYY-MM-DD`; Excel date cells are supported. Ambiguous dates, rounded `1.2K` values, malformed rows and duplicate headers are rejected. Prepare corrections in a separate file, retaining the original export and documenting changes. Numeric separators accept exact decimal numbers or valid US thousands groups such as `1,234.5`; decimal commas are not inferred. A `%` suffix requires unit `percent` and retains percentage points (`12%` becomes `12`, not `0.12`).

The first rectangular header remains authoritative. Ordinary data cells containing `Day` or `Date` do not become new headers or discard preceding rows. Very large integer counts and overprecise decimal inputs are refused if storage would lose their reported precision; a nonzero source value cannot be accepted as zero. Keep the original export rather than rounding it just to force an import.

## Observation fields

| Field | Meaning |
|---|---|
| `platform`, `account` | Exact platform and explicit account identity. Use `Spotify`, `Facebook`, `Instagram`, `TikTok` or `TikTok for Artists` for dashboard navigation. |
| `entity_type`, `entity_id` | Grain and stable platform ID, such as artist, track, account, post or video. If unavailable, use an explicit source-scoped ID; never merge by similar names. |
| `entity_name` | Optional display label. |
| `metric`, `value`, `unit` | Platform-native measure, exact numeric value or blank, and count/percent/seconds/ratio/currency with currency code in dimensions. |
| `period_start`, `period_end` | Inclusive reporting boundaries, independent of capture/import dates. Required. |
| `time_grain`, `measurement_type` | Daily/period/snapshot and period_count/distinct_count/point_in_time/rolling_count/cumulative/rate. See METRICS.md. |
| `source_timezone` | Report timezone if known; otherwise blank. Daily source buckets are not shifted. |
| `captured_at` | Known ISO capture date, or timestamp with explicit UTC offset. Blank when unknown. A date-only capture remains date-only. |
| `status` | `observed`, `missing`, `suppressed` or `unavailable`. If omitted, inferred from the value token. |
| `evidence_ref`, `definition` | Source URL/reference and metric definition, population and limitations. |
| `dimensions_json` | JSON object for reporting filters, geography, paid/organic scope or availability reasons; defaults to `{}`. |
| `source_row`, `worksheet` | Assigned by the reader from the actual source. Mapped values cannot replace these references. |

All required identity, period, unit, grain and measurement fields must be supplied by file or metadata. An `observed` value must be numeric, including genuine zero. Other statuses require a blank value. Blank/NA/dash means missing; `*`, `**` and threshold values such as `<5` remain suppressed. Their exact original tokens remain in archived bytes. For a known not-applicable observation, use `unavailable` and `{"availability_reason":"not_applicable"}`. Do not convert missing dates or absent rows to zero.

## Baseline, duplicates and corrections

**Load preserved native Spotify archive** verifies five native CSV hashes, imports the artist timeline plus four track timelines, and seals the snapshot. The reporting endpoint is October 20, 2026; collection occurred October 22. Exact individual CSV capture timestamps are unknown. Original October 20 baseline membership remains unverified; sealing is protection, not evidence of baseline membership.

This native subset has 1,024 daily endpoints per CSV (January 1, 2024–October 20, 2026), yielding 12,288 observations. It overlaps the separately registered recovered library, which includes broader Spotify data, Facebook/Instagram, and three Spotify extension snapshots. Do not sum snapshots. See [recovery scope](RECOVERY.md). TikTok is deferred.

Reimporting identical bytes and mappings into the same snapshot leaves observations unchanged. Equal overlapping observations from different files gain provenance without duplicate totals. Conflicting values or changed mappings reject the file. Use a new descriptive snapshot label for corrected interpretations, historical revisions or later captures. Sealed snapshots and registered archives cannot be overwritten by the import form.

Overlapping observations must also have matching metric definitions after surrounding whitespace is trimmed. A definition mismatch stops the entire file import, including its preview, rather than hiding one scope behind another. Represent verified paid/organic or other distinct reporting scopes in `dimensions_json`, or review a revised definition in a separate snapshot. Original-source downloads verify the retained byte count and SHA-256 before returning a file; a mismatch is an error, not an automatic source repair.

The generic upload form requires known reporting bounds. The recovered adapter separately supports lifetime and unknown-window evidence with NULL bounds, retaining publication and capture dates independently. Do not invent dates to make unknown-window evidence fit the generic form. Private Spotify artist analytics come from exports and verified readings, not consumer Spotify access. No live API connection is assumed.
