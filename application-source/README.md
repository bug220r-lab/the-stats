# The Stats™️

A local Streamlit dashboard for music and social analytics. Python, pandas, Plotly and SQLite keep the workflow on your computer. Data is never published or written back to the source workbook.

## Install and run

Tested on Python **3.12.14** on macOS. Use Python 3.11 or newer (the system Python 3.9 is too old). Streamlit's supported Python versions are documented in its [installation guide](https://docs.streamlit.io/get-started/installation/command-line). This workspace has an installed `.venv`; use it directly:

```sh
cd '/Users/judelewis/Documents/ChatGPT/The Stats™️'
source .venv/bin/activate
python -m streamlit run app.py
```

Open [localhost:8501](http://localhost:8501). The server binds to loopback. For a new checkout, create a virtual environment with Python 3.12 and install the tested lock file:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pytest -q
python -m streamlit run app.py
```

`requirements.txt` gives compatible top-level ranges; `requirements-lock.txt` pins the environment actually tested. `.streamlit/config.toml` controls the dark theme and UI accent. The sidebar's Appearance control saves the chart accent locally. Set `STATS_DATA_DIR=/absolute/private/folder` to use a separate database and source directory. No demo data is automatically loaded.

## Import workflow

1. Open **Import data** and create a clearly named snapshot. Upload CSV/XLSX or configure a local folder; each selected file gets its own preview. Select the actual worksheet and header row.
2. Review platform, account and entity identity, exact reporting dates, units, types and mappings. Canonical long files map automatically; known wide columns are suggested. The [export guide](docs/EXPORT_GUIDE.md) explains needed fields per platform.
3. Supply IDs from the source. If unavailable, use an explicit source-scoped account key. Missing entity IDs are assigned a file-and-row-scoped identity, never joined by name across rows or files. To intentionally link the same entity across exports, supply its explicit canonical `entity_id` in the mapping. `identity_scope` in defaults can explicitly define a shared source scope for corresponding worksheet rows, but should be used only after verifying identical row identity; stable platform IDs are preferable.
4. Review source rows, validation messages and overlapping stored observations. Commit only after acknowledging the preview. Rejected rows remain in the issue log; partial import requires an explicit choice. Contradictory rows within the same file block commit.
5. Save useful mapping profiles. They persist in SQLite. For corrections, retire the mistaken import under **Data & collection → Maintenance**, then reimport with the corrected mapping. History and original bytes remain available; earlier retained versions become active when appropriate. Sealed snapshots cannot be retired or revised.

The canonical [manual-reading CSV](templates/manual_readings.csv) is intentionally empty. Every manual reading needs its reporting window, capture date when known, and evidence reference. `templates/mapping_example.json` illustrates a wide daily export mapping; its placeholder ID must be replaced.

Parsing defaults to ISO dates and decimal-point numbers. Set `date_format` to `MDY` or `DMY` and `numeric_locale` to `en_US` or `de_DE` explicitly when appropriate. Missing cells, `N/A` and em dashes remain missing; `<5` and suppressed values remain suppressed, not zero. Percent signs convert to a fraction only when the unit is `ratio` or `fraction`.

## Snapshots and the October 20 baseline

The original October 20, 2026 baseline is an identified snapshot, not a cutoff filter. An export collected later with an October 20 reporting endpoint does **not** prove original baseline membership. This build retains the retrieved source package as a separate archived snapshot and leaves original baseline status unverified.

To load an independently identified original baseline, create a baseline snapshot with its membership evidence, stage only original files, then **Seal snapshot**. Existing baseline values cannot be revised even during staging; sealing blocks all further imports. Later captures belong in new snapshots even when values match. SQLite transactions and application checks enforce immutability. Keep backups; direct manual editing of SQLite bypasses application safeguards.

Within an editable snapshot, observation identity comprises platform, account, entity, metric, unit, definition, dimensions, reporting window, time grain, measurement type and source timezone. Exact repeats do not add counts. Same readings from different files attach source references. Revisions retain previous values and explicitly select the latest committed active version. Capture time does not silently reorder authority. Unknown capture times and source timezones remain unknown; import time is separate. Unknown and known timezones remain distinct identities, so date buckets are never silently reassigned.

Use the sidebar snapshot selector. **Compare snapshots** in the platform views compares revisions of the identical historical window. Overview previous-period comparisons use equal-length, disjoint reporting windows and compatible definitions. Unavailable comparisons explain why.

## Views and calculation rules

- **Overview:** supported native KPIs, daily trends, prior-window comparisons, freshness, coverage and deterministic observations.
- **Spotify:** account/track/release/segment drill-down, source rows, supported ratios, snapshots and CSV/Markdown downloads.
- **Social media:** separate Facebook, Instagram, TikTok and TikTok for Artists filters, content metadata and paid/organic dimensions. Lifetime content has a separate evidence table with publication-date filters; it never becomes activity for the sidebar reporting period. Empty states identify missing exports.
- **Cross-platform:** aligned absolute series, optional common-date index, matched-day correlation and lag analysis (default minimum 30 days), and local annotations.
- **Data & collection:** import inventory, original-source statuses, local queue notes, metric definitions, annotations, mapping correction and backup instructions.

All KPI cards, comparison results, summary text and KPI downloads use `stats.metrics`. A selected period requires complete coverage or an exact-window source observation. Daily charts show source daily observations; they do not spread period totals over days. If an exact-window total differs from daily readings, the card uses the authoritative window and the chart remains daily evidence with an explicit reconciliation notice. Source-row downloads are evidence tables, not additive totals.

Never add daily unique listeners, overlapping reach, lifetime totals, rolling audiences or follower balances. Account totals and content breakdowns are separate populations. Distinct listeners for a selected month require a native exact-window total. Ratios use compatible numerator/denominator totals, handle zero denominators as unavailable and expose the denominator. Saves per listener is not a unique-person conversion rate. Native reported rates retain their definition; no rows of rates are averaged.

Different platforms' views, streams, impressions and reach are not a combined audience score. Content age, attribution and paid/organic dimensions matter. Correlation omits missing pairs, never fills missing values with zero, reports sample size and lag direction, and does not establish causation. Indexing starts at a common nonzero observed date; absolute values remain available. No revenue, ROI, listener conversion or artist benchmark is invented.

## Persistence, privacy and backups

SQLite, source archives, canonical imports, exports and local settings live under ignored `data/`. Original files are hashed and copied unchanged. The `.gitignore` also excludes credentials, `.env`, Streamlit secrets, logs and virtual environments. Keep sensitive uploads in `data/` or an external private folder; do not put them beside source code. No credentials are needed. No cloud deployment or source writeback is included.

The cache key changes after imports, revisions, mapping changes and local edits. Restart uses persisted records without reuploading. Use an online backup including archived source files:

```sh
python -c "from stats.storage import Store; Store('data/stats.sqlite3').backup('backups/manual-backup')"
```

Also preserve `data/connected/` for the inspected original archive and reconciliation evidence, and `data/settings.json` for UI preferences. To restore, stop Streamlit, move the current data folder aside, restore the backup database and sources to `data/`, then restart. Never overwrite a running database.

## Connected-source acquisition and reproducibility

The supplied workbook and source folder were inspected through read-only connected tools. The original ZIP and read responses are retained under `data/connected/`; original workbook tabs were not modified. The display name is redacted in the source. The original package supplied a stable Spotify artist ID but no social exports.

`scripts/stage_connected.py` validates every listed archive member before generating canonical source files. `scripts/load_connected.py` validates previews, commits into the separate archived snapshot and records the current queue without changing its status. These are local offline replay tools, not live connectors. They require the private retrieved package; ordinary users can use the import screen without it. `data/connected/source_inventory.json` and `reconciliation.json` retain the exact acquisition inventory and source totals.

Fresh Meta exports collected on October 22 are preserved separately in `data/social_captures/2026-10-22/`, together with settings, account identity evidence, timestamps and checksums. Preview or replay that capture with:

```sh
python scripts/load_social.py data/social_captures/2026-10-22/capture_manifest.json
python scripts/load_social.py data/social_captures/2026-10-22/capture_manifest.json --commit
```

The loader validates every source before importing, uses an independently identified social snapshot, and treats identical replays as duplicates. It does not change the archived October 20 reporting package. `stats/social.py` accepts explicitly supported native schemas; unexpected columns fail validation. Source-scoped Meta asset IDs, native Page IDs and collaborator account IDs remain distinct. Native lifetime content keeps an unknown reporting cutoff when the source does not supply one. Capture time records acquisition, not an invented metric cutoff.

The dashboard runs locally from imported data. It does not automatically sign in to or synchronize social accounts. TikTok Studio and TikTok for Artists require an authenticated source session or supplied export; a login block is recorded as missing coverage, never as zero activity.

## Tests

```sh
python -m pytest -q
```

Tests cover consequential calculations, imports, snapshot immutability, versions, restart persistence and focused Streamlit AppTest flows. Private-data reconciliation tests skip in checkouts without the preserved source package. See `docs/VERIFICATION.md` for the checks actually run for this delivery.

Architecture: `stats/ingestion.py` handles parsing/validation, `stats/storage.py` SQLite/provenance, `stats/metrics.py` calculations, and `app.py` the interface. Extend platform adapters only after verifying actual access and current official API documentation; consumer Spotify access is not assumed to provide private Spotify for Artists data.
