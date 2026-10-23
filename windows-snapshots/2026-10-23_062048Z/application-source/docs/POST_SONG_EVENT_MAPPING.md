# Retained post/song/event mapping

`scripts/build_post_song_event_map.py` reads the active immutable analysis package and writes a separate evidence bridge. It makes no network requests, updates no database or registry, and refuses an existing output directory.

Run from the project directory in PowerShell:

```powershell
& .\.venv\Scripts\python.exe scripts/build_post_song_event_map.py `
  --data-dir (Join-Path $env:LOCALAPPDATA 'TheStats') `
  --output 'data/collection/meta-20261023/mapping-next'
```

For another host, supply its configured data directory or `--database <path-to-immutable-analysis.sqlite3>`. The output name must be new. `coverage.json` records the input database before/after SHA-256, input asset hashes, script version/hash and generation timestamp. JSON preserves exact source text; CSV text beginning with spreadsheet formula characters receives a protective apostrophe.

The reviewed October 23 collection output is `data/collection/meta-20261023/mapping/`, version 1.1.0. `draft-v1/` is a preserved provisional output superseded after review found a caption that mentioned a release and a show together. Use only the top-level reviewed tables. No source database or export was replaced.

## Table grains and meanings

- `post_song_map.csv` / `.json`: one row per platform, selected account and post ID. Preserves author identity/scope, publication dates/timezone, native source/capture metadata, assigned IDs, candidates, unknowns and multiple references.
- `post_song_references.csv` / `.json`: many-to-many caption/link evidence rows. Never join performance metrics through this table without returning to the unique post grain; never allocate artist streams to posts.
- `post_evidence.csv` / `.json`: retained full caption and all source snapshot references for each canonical post, plus the selected native file's hash.
- `event_map.csv` / `.json`: source-reported release dates and caption promotion/event mentions. Publication/promotion date remains separate from event date. Repeated mentions of a show are evidence rows, not independently counted events.
- `review_queue.csv` / `.json`: recording-version ambiguity, generic/nickname/abbreviation candidates, unknown captions, unresolved dates and the 183 quarantined Story records. Unknown captions are optional inspection work, not evidence that the posts have no music.

An explicit title reference can identify a stable recording when the catalog has one matching version. It does not prove which audio played in the post. A `verified_spotify_link` would mean only an explicit retained link matched a catalog ID, not that the URL was opened or conversion occurred; no such links were present in this source. Titles shared by the album and Lab Tapes recordings stay ambiguous without an explicit version. “Meet Jude, The Funny Guy” stays a nickname candidate. Shortened titles such as “Docs” and “Son!” require review.

Fully specified caption dates remain source claims, not independently verified event occurrences. Missing years and relative dates stay unresolved. If one caption mentions multiple event types, an exact date is retained as a candidate until its event association is verified. Seven catalog release dates are retained separately from these claims; no source snapshot is relabelled as the original October 20 baseline.

## Verification performed

The run read 377 valid canonical posts, retained references to 434 snapshots and excluded/queued 183 malformed Story records. It resolved 62 explicit caption references across 60 posts, including two posts with multiple references. Eleven posts have unresolved identity/version/context candidates, and 306 have no identified catalog song in the retained text. This yields 379 reference rows, 120 event-evidence rows and 600 review rows. Twenty event rows have full dates (seven release metadata rows and thirteen caption claims); they are not twenty distinct events.

Nine focused tests passed, covering shared recording titles, nickname/generic contexts, multiple songs/unknowns, explicit links, missing years, relative dates, title text containing “Tomorrow”, mixed release/show captions and announcement dates. All twelve files listed by the final output manifest verified, canonical post keys were unique, and input database SHA-256 remained unchanged (`d78bcbce70fc8e8322555392c06031f3a40b2d4338cedcaf52aa271884defa65`). Source rows and native files were checked by the read-only repository before mapping.

No audio/video was viewed, no destination was opened, no new Meta data was collected by this script, and no stream-conversion or causal claim is established. Event-calendar completeness and human review of the unresolved queue remain outstanding.
