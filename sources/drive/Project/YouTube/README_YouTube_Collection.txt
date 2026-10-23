THE STATS - YOUTUBE COLLECTION
Retrieved October 23, 2026

ACCOUNT AND SCOPE
[REDACTED] TV, @redactedbandoh
Channel ID: UCkSoRiC9Pz9hEbJOOTYaq_w
Identity was verified in the signed-in Studio account switcher, selected channel,
and public header. Access was Manager. Standard-channel reporting was observed:
no Official Artist Channel badge or artist-only reporting was exposed. Scope is
the selected channel's analytics, not artist-wide Total Reach or Other Channels.
Public channel: https://www.youtube.com/@redactedbandoh
Saved project area: https://drive.google.com/drive/folders/1SJDyZ545GHtloK0n296Z7GUcaw6fYVni

COVERAGE
- Current annual: October 22, 2025 through October 21, 2026 (365 days).
- Historical Spotify match: October 21, 2025 through October 20, 2026.
- Lifetime: January 25, 2024 through October 21, 2026.
- Audience: September 24-October 21, 2026 (28 days) and July 24-October 21,
  2026 (90 days), subject to the specific availability notes below.
- 67 native ZIP exports: 40 core reports plus 27 per-video retention reports.
  348 original CSV members: 105 core and 243 retention.
- 27 distinct video IDs: 8 shorts, 19 videos.
- Annual per-video views: 9,855 distinct video-days across 27 videos.
- Annual per-video engaged views: 9,855 distinct video-days across 27 videos.
- 45,477 core canonical metric observations. These are long-form
  metric rows, not a count of videos or distinct calendar days.
- Core report export statuses: 4 blocked, 24 complete, 1 not applicable, 11 partial; all 27 retention exports complete.
  See the collection index for limitations.
- Requested collection items: 2 blocked, 10 complete, 1 not applicable, 1 not yet collected, 6 partial.

Reporting dates are inclusive Pacific calendar dates (America/Los_Angeles),
preserved as reported. The native ZIP filename end date is exclusive. Retrieval
time is recorded separately using download-file LastWriteTimeUtc as an explicit
proxy; the exact browser export-click timestamp was not retained. Reports ending
October 20 are NEWLY RETRIEVED HISTORICAL reports, never original October 20
snapshots. Existing Spotify files and baseline were not changed.

FILES AND LOADING
All paths below are relative to this package root.
originals/             Unchanged native ZIP exports, organized by report ID.
extracted/             Exact CSV members extracted from each ZIP.
report_manifest.json   Channel, periods, filters, scope, timestamps and hashes.
normalized/collection_index.csv  Report statuses and original-export links.
normalized/channel_daily.csv    Canonical daily channel metrics, including
                               explicitly filtered scopes.
normalized/video_daily.csv      Canonical daily metrics keyed by video ID.
normalized/video_daily_wide_365.csv  9,855 annual video-days with views and
                                   engaged views, statuses and source IDs.
normalized/channel_daily_wide.csv   Wide channel data with reporting periods
                                   separate and omitted metrics left blank.
normalized/channel_period.csv and video_period.csv  Period summaries.
normalized/dimension_period.csv and dimension_daily.csv  Discovery/audience.
normalized/video_inventory.csv and video_song_mapping.csv  Stable IDs/mapping.
normalized/field_dictionary.csv, metric_dictionary.csv, value_status_dictionary.csv
normalized/source_files.csv, daily_coverage.csv, validation_checks.csv
normalized/collection_status.csv  Task-level complete/partial/blocked/not-applicable items.
normalize_youtube.py   Reproducible standard-library normalization/validation.
verify_collection.py   Independent source-to-output checks.
independent_validation.json  Saved verification result.

Rebuild with `python normalize_youtube.py build`; verify with
`python verify_collection.py`. Verification passed all 40 original hashes and
all 27 x 365 x 2 annual video/metric pairs against the native source.

Example Python import (run from the package root):

    from pathlib import Path
    import json
    import pandas as pd

    base = Path('.')
    daily = pd.read_csv(base / 'normalized/channel_daily.csv',
                        dtype={'channel_id': 'string', 'video_id': 'string'},
                        keep_default_na=False)
    unfiltered = daily['filters_json'].map(lambda x: json.loads(x or '{}') == {})
    annual = daily.loc[(daily['period_kind'] == 'annual_current') &
                       (daily['report_content_format'] == 'all') & unfiltered].copy()
    annual['value_numeric'] = pd.to_numeric(annual['value'], errors='coerce')
    annual['activity_date'] = pd.to_datetime(annual['activity_date'])

Keep value_status, source_value_raw, source_file and source_row_number. Blank
values are not zero. Do not sum overlapping report periods, filtered channel
totals, or raw observations. Use canonical tables with the intended scope and
filters. Stable keys include channel/video ID, period or activity date, metric,
content format, filters, reporting scope and snapshot class.

LIMITATIONS
- The annual native date table contains observed dates only for several metrics.
  Missing days remain missing. Full views/engaged-view series do not establish
  complete daily coverage for watch time, subscribers, or engagement measures.
  Four supplemental daily chart exports (watch time, average view duration,
  subscribers gained and lost) were blocked when Google requested passkey
  verification at the date chooser. Verification remained pending at handoff.
- Native detail can differ from aggregate totals (including deleted/unattributed
  activity or withheld detail). Preserve source totals; do not force equality.
  Search terms and external-source detail do not cover every reported source view.
- Annual age/gender detail is available (6 age groups, 2 gender groups). The
  28/90-day exports were header-only with insufficient-data messages. Geography
  has partial or no short-window detail. Missing rows are not zero.
- In captured 28/90-day reports, New viewers was a dash in Studio but 0 in the
  CSV. Raw 0 is preserved; normalized value is unavailable with a quality note.
- Unique/returning viewers are distinct-person estimates. Do not add across
  overlapping videos/windows. The New and Returning Viewers breakdown reports
  views and watch time, not unique-person counts. Unique viewers support up to
  90-day windows.
- Views and engaged views are separate. Shorts views changed March 31, 2025.
  The all-format first-frame rollout was announced from August 24, 2026; this
  channel's observed UI marks August 27, 2026. Preserve both source facts rather
  than imposing a single universal breakpoint. AVD, percentage viewed and CTR
  are nonadditive source metrics. Average percentage viewed can legitimately
  exceed 100% with replays; do not cap it at 100.
  Source watch time is hours; parsed average duration is seconds with raw retained.
- Music-specific song/Art Track/Other Channels artist-wide rollups were not
  exposed in this standard-channel account. YouTube product breakdowns cover
  only this channel, not the band's full distributed music catalog.
- Retention ZIPs can contain several overlapping viewer/subscriber/traffic
  segments and a relative comparison. Preserve each segment and source metric;
  do not add curves together or treat their elapsed-video axis as calendar days.
- Song links are title-evidenced relationships, not proof of an identical audio
  recording. Spotify recording IDs remain unverified; live performances are not
  automatically livestreams. No individual conversions or causal claims are made.
- No API application was created and no new API access was granted.

REFERENCES
Native export limits and deleted-video treatment:
https://support.google.com/youtube/answer/9717005?hl=en
Pacific day boundaries:
https://developers.google.com/youtube/analytics/dimensions
Views and engaged views:
https://blog.youtube/inside-youtube/engaged-views-youtube-explained/
Unique viewers:
https://support.google.com/youtube/answer/7577916?hl=en
Artist reporting scopes:
https://support.google.com/youtube/answer/18736729?hl=en

RETENTION FILES
The 27 per-video retention reports use each video's Since uploaded lifetime
window through October 21, 2026. Upload and public publication dates can differ.
All.csv provides 2,700 points: 100 elapsed-video percentage bins (0-99) for each
video. No endpoint at 100 is fabricated. Across all native segment members,
there are 17,349 source rows and 20,249 long-form metric observations.
100 header-only members and 139 blank numeric cells are unavailable, with no
inferred zero or specific suppression cause. Absolute retention can exceed
100%; compared-to-other-videos percentages may be negative. Preserve both.

retention/retention_observations.csv     Native curves and detailed activity.
retention/retention_ui_summary.csv       27 manual UI average-duration/percentage
                                       summaries; 8 Shorts Stayed-to-watch values.
retention/retention_collection_index.csv Dates, scopes and original ZIP URLs.
retention/retention_data_dictionary.csv  Units and distinct source metric meanings.
retention/retention_source_files.csv     Member hashes/rows and header-only flags.
retention/retention_validation_checks.csv 57 checks, zero failures.
retention/retention_independent_validation.json 27 ZIP hashes, 243 member bytes
                                       and all 20,110 numeric values checked.
retention/retention_manifest.json        Full per-video provenance.
retention/originals/ and retention/extracted/ preserve the native evidence.

Load retention_observations.csv with pandas and keep report_id, video_id,
member_name, segment_dimension, segment_value, video_position_percent and
metric in the key. Join video_id to normalized/video_inventory.csv. Keep manual
UI summaries separate from native exports; their rounded display values and
transcription method are explicit. Curves cannot be added across positions,
overlapping segments or videos.

SAVED COLLECTION
Native collection index:
https://docs.google.com/spreadsheets/d/1KU_Ky0r1MeoJe_QQ20VeuImO48GCRg722Sx7IuQLhrI/edit
The native index's 67 reporting periods and retrieval timestamps were verified
against keyed source manifests after import. See delivery_links.json for all
folder and primary dataset links. The original Spotify files were unchanged.
