# Connected-source inventory

Account-specific data and the live inventory are kept locally under the ignored
`data/connected/` directory. The private `source_inventory.json` records observed
accounts, source URLs, archive and canonical file hashes, capture date evidence,
verification counts, dataset membership, omissions, and reconciliation results.

The source archive is retained unchanged in `originals/`; extracted members stay
unchanged in `source_archive/`. The archive supplies a per-file manifest whose
checksums and byte counts are verified before canonical staging. Bounded Google
Sheets read responses are retained separately in `workbook_capture/`, including
the collection queue. `collection_queue.csv` preserves its recorded status and
source review date separately from retrieval time.

Canonical imports in `archive_snapshot/` cover artist daily and period values,
track daily and period values, release daily and period values, Canvas views,
and selected audience/source breakdowns. Each observation retains its source
CSV row and evidence reference. Exact capture timestamps are copied only when
the retained capture manifest identifies that evidence; unknown times remain
blank. Reporting days use the archive's documented UTC basis.

The archived package reports through October 20, 2026 and documents collection
on October 22. This alone does not identify the original October 20 baseline
membership. The baseline therefore stays **unverified**; the package is a
separate archived source snapshot. A new source covering an older reporting
date must never be substituted into a frozen baseline.

The package contains Spotify data. No Meta or TikTok datasets or verified social
account handles are established by this package. Their app views must remain
empty until real exports are imported. Playlist tables and other retained
tables without exact period bounds remain available as original source files,
but are excluded from period-aligned metrics. Missing, suppressed, unavailable,
and conflicting measurements remain distinguishable from explicit zeros.

To reproduce local staging without network access or source changes:

```sh
python scripts/stage_connected.py
```
