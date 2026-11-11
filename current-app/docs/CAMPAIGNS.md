# Content and campaign log

Open **Campaigns** in the existing application. The log stores source-backed metadata in separate `campaign_*` tables inside the writable `stats.sqlite3`. It does not modify registered analysis snapshots, raw exports, archived baselines or performance observations. Existing database and complete-library backups include these tables automatically. No records are invented or seeded from uncertain caption/audio mappings.

Download the empty CSV template (also saved as `templates/content_campaign_log.csv`), add real records, then upload the UTF-8 CSV (maximum 5 MiB). The application validates and previews the entire file before an approved admin commits it. Viewers can inspect and download the log. All retained source bytes, hashes, filenames, import times, importing principals and CSV record numbers remain available. CSV record numbers start at 2 after the header; embedded multiline fields count as one record.

## Fields and interpretation

| Fields | Meaning |
| --- | --- |
| `platform`, `account_id`, `post_id` | Required exact source identity; IDs stay strings, including leading zeros. Platform is Spotify, Instagram, Facebook, TikTok, YouTube or Offline. Adding a manually documented TikTok event does not imply a collected TikTok analytics account. |
| `event_type` | post, release, show, playlist, campaign, other or unknown. For a non-post event use a stable `manual:` post_id, source-grounded account scope and the appropriate event type. |
| `publication_timestamp`, `publication_timezone` | Original timestamp with explicit UTC offset and a matching IANA zone, such as `2026-10-20T12:00:00-07:00` / `America/Los_Angeles`. The offset and local clock are checked, including daylight-saving transitions. Known timestamps also receive a derived UTC value for the timeline. Unknown timestamps stay unknown; put a date-only observation in notes rather than inventing midnight. |
| `revision_timestamp` | Required offset-aware time when the metadata was recorded or corrected. Distinct from publication, collection and import times; normalized to UTC for deterministic revision selection. |
| `song_id`, `song_title`, `excerpt`, `opening_hook`, `content_format`, `call_to_action` | Creative metadata. Assign only evidence-supported values. Unknown fields remain unknown. Recording IDs must not be inferred from title alone. |
| `duration_seconds`, `production_effort_minutes` | Optional nonnegative values; unknown is blank, not zero. |
| `distribution`, `spend`, `currency` | organic, paid, mixed or unknown. Spend is optional, nonnegative and requires a three-letter currency code. A logged amount is contextual metadata, not an automatically summed Ads total or verified delivery. |
| `campaign_id`, `release_id`, `related_events` | Documented associations and context such as other promotion, shows or playlist events. A mention does not confirm the event occurred; qualify it in notes. |
| `destination_link`, `utm_source`, `utm_medium`, `utm_campaign`, `utm_content` | Intended destination and campaign tags. No measured click or stream is inferred from a URL. |
| `tag_status`, `tag_provenance` | Assigned creative tags require verified or inferred status and a supporting reference or explanation. Status applies to all assigned creative tags in the row; use inferred if any is inferred, and describe field-specific qualifications in notes. |
| `source_reference`, `notes` | Required source reference plus optional caveats. Known identity must come from a source; a typed ID is not independent verification by the importer. |

All optional empty or `unclassified` strings become explicit `unknown` in cleaned records. Numeric unknowns remain null. Original source bytes are unchanged and hash-verified before download. The spreadsheet-safe inspection export neutralizes formula-leading text and includes derived fields. The separate editable-current export contains only template columns and preserves exact text for round-trip import; edit it as text or explicitly import all spreadsheet columns as text. Give corrected rows a later revision timestamp. Reimporting unchanged rows adds no metadata revision.

## Deterministic revisions and safe joins

The identity key is `(platform, account_id, post_id)`. A complete replacement row with a later explicit `revision_timestamp` becomes current, even if an older file is imported afterward. An exact repeated file is skipped; identical overlapping revisions add provenance without multiplying current events. Different values at the same identity and revision time reject the entire file. Earlier revisions remain in history. Carry forward all metadata that should survive a correction; an omitted field in a newer revision means unknown.

The timeline and current table use one row per identity. History can have multiple source receipts for the same revision and must not be used as an independent sample or joined directly to performance totals. The application deliberately performs no joins between log rows and artist daily totals, no summation of spend and no attribution model.

Existing retained post/song/event evidence is available separately below the log. Do not transfer Reel audio labels to Stories, collapse uncertain song mappings, or count multiple song references as multiple deliveries.

## Tracking observed outcomes

Use stable campaign/post tags and preserve the destination configuration when publishing. Keep landing-page sessions, outbound clicks, platform link clicks and confirmed music streams as separate outcomes. Import actual exported measurements through **Import data** with account scope, reporting period, timezone, metric definition and source. Comparable 7-day or 28-day post-age measurements require repeated snapshots at those ages; this log alone cannot manufacture them. Cross-platform user identity or conversion is unavailable unless a source directly measures it.

Run the isolated checks from PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_campaign_log.py
.\launch_windows.bat
```

Campaigns refreshes its table immediately after a save. No server restart is needed to read committed metadata. Optional unreadable YouTube collections show a scoped warning; other dashboard pages remain usable and the source is not silently replaced or permission-modified.
