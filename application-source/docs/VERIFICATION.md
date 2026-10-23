# Delivery verification

Verified October 22, 2026 (America/New_York), using Python 3.12.14 on macOS.

## Executed checks

`python -m pytest -q` — **105 passed in 7.75 seconds**. `python -m pip check` — **No broken requirements found**. Exact installed package versions are recorded in `requirements-lock.txt`.

| Acceptance behavior | Evidence |
| --- | --- |
| Empty start and import screen | Streamlit AppTest starts with an isolated empty data directory, creates a snapshot and keeps the import workflow open. |
| Real dataset reconciles | Preserved native artist CSV equals normalized artist daily rows; database KPI values and daily chart totals match direct source values. Private source integration test passed. |
| Same-snapshot reimport | All six full canonical imports replayed; every result was idempotent. Observations remained 82,878 and source references 82,889. |
| Overlap and revisions | Tests cover same-value source overlaps, newest committed revisions, status conflicts, retired import restoration and timezone-specific identities. |
| Immutable baseline | Tests cover staging conflicts, sealed import/retirement refusal and separate newer snapshots. No unverified source was labeled the original baseline. |
| Missing versus zero | Tests cover empty/suppressed values, status preservation, incomplete dates, numeric separators and Excel percentage formats. |
| Correct rates | Tests cover compatible distinct denominators, exact windows, snapshot and population matching, named engagement denominators, zero denominators and incompatible scopes. |
| Charts/tables/downloads agree | Cards and KPI downloads use the same calculation results; daily chart sums reconcile under complete compatible filters. AppTest changes reporting windows and checks resulting displayed numbers. Conflicting exact-window versus daily evidence is explicitly disclosed. |
| Restart persistence | SQLite reopen tests retain observations, mappings, local annotations and source queue notes. UI folder import is verified after a fresh AppTest instance. |
| Main views | All six views rendered without exceptions with the full real dataset. Automated smoke checks exercise all views with isolated fixtures, empty filters, annotations and local-folder preview/commit. The running local browser displayed the real overview and source-backed KPIs. |

## Real-source results

The separate archived source snapshot has **82,878 active observations** and **82,889 source references** across six canonical datasets: artist daily/periods, track daily/periods, releases and selected audience breakdowns. A seventh audit import retains inventory exclusions and baseline warnings. The collection queue has **43 recorded Pending browser access rows**; application development did not complete them.

The source ZIP is unchanged. All **580 listed member checksums and byte counts** passed; the ZIP has 581 members including its manifest. Account-specific verification artifacts live in ignored `data/connected/` and `data/verification.json`.

For September 23–October 20, 2026:

| Measure | Verified value |
| --- | ---: |
| Streams | 4,246 |
| Exact-window unique listeners | 1,062 |
| Saves | 217 |
| Playlist additions | 362 |
| Followers as of October 20 | 1,644 |

All 28 daily stream buckets sum to 4,246. The previous equal 28-day stream window reports 4,011, so the valid comparison is +235 (+5.86%). Unique listeners come from the source's period total, not a sum of daily listeners.

SQLite `PRAGMA integrity_check` returned `ok` after the identity migration. Migration was first tested on a temporary backup of all 82,878 records with unchanged observation values/metadata, snapshots, imports and provenance, then applied transactionally to the live local database.

## Limits retained in the delivered application

The archive documents collection on October 22 and a reporting endpoint of October 20. It does not prove membership in the original October 20 baseline. That baseline remains **unavailable/unverified**, and the archived package is a separate ordinary snapshot.

The displayed artist name is redacted in the supplied sources. A stable Spotify artist ID is present. Facebook, Instagram, TikTok account/content and TikTok for Artists exports and verified account handles are absent. Social UI behavior was checked with isolated test fixtures, not invented production analytics. Exact capture timestamps remain absent where the retained manifests do not establish them.

Playlist tables without exact reporting bounds stay in the preserved original package and are excluded from period-aligned KPIs. No artist benchmark, attribution-based conversion, revenue, ROI, live API connector, source writeback or external publication was delivered or claimed.
