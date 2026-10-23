# Build The Stats™️ — a Python marketing analytics dashboard

You are my software engineer and marketing analytics developer. Build a working local Python application for my band's streaming and social media data. Implement the program, install its dependencies, test its important behavior, and launch it if your environment permits. Continue beyond planning to a usable application.

## 1. Project context and sources

My name is Lewis. The project is called **The Stats™️**. Verify the actual artist name, accounts, and handles from the source files; the project name is not necessarily the band name.

The dashboard should bring together:
- Spotify for Artists.
- Facebook and Instagram analytics from Meta.
- TikTok account/content analytics, and TikTok for Artists data when available. Keep these distinct where their measurements differ.

Known project locations:
- [Analytics workbook](https://docs.google.com/spreadsheets/d/1gfPLM_kj8mT1bNn0e3sv2udEU3644PR5z_20QMfl3Yc/edit)
- [Collection queue](https://docs.google.com/spreadsheets/d/1gfPLM_kj8mT1bNn0e3sv2udEU3644PR5z_20QMfl3Yc/edit#gid=82074406)
- [Source files in Drive](https://drive.google.com/drive/folders/1sE3oczZadl04Ro2HDf0GQ51oxuNxiLdR)

A previous handoff mentioned 43 pending Spotify collection items. Treat that as historical context, not a verified current count. Meta and TikTok collection was requested separately; do not assume it has been completed.

Preserve the original **October 20, 2026 reporting baseline**. Newer captures must remain separately identifiable.

Start by inspecting the repository, any AGENTS.md instructions, and available datasets. Inventory files, sheets, accounts, metrics, reporting periods, capture dates, and gaps. Use connected access if available, but do not assume these private URLs are accessible. If blocked, build the complete file-import workflow and explain exactly which exports I should provide. Make progress without waiting for every platform.

## 2. Application and architecture

Use:
- Streamlit for the interface.
- pandas for transformations and calculations.
- Plotly for interactive charts.
- SQLite for persistent local storage.
- openpyxl for Excel support.
- pytest for meaningful calculation and import tests.

Use compatible, supported dependency versions and record the tested Python version. Reuse a suitable existing environment. Keep ingestion, storage, metric calculations, and UI in separate modules.

Build a local application that opens in my browser. The normal workflow should not require a paid service, cloud database, or AI API key. Use a clear dark theme with restrained yellow accents, readable charts, and a compact layout. Make colors configurable.

Provide sidebar navigation, contextual filters, persistent imported data, useful empty states, and clear error messages. Prioritize a finished export-based workflow; live API connections can be added later through separate adapters after their availability and permissions are verified.

## 3. Imports, storage, and provenance

Support CSV and XLSX uploads, selecting worksheets, and importing a configured local folder. Implement platform-specific parsers for observed schemas and a reusable column-mapping workflow for unfamiliar exports.

Before committing an import, show:
- Detected platform, account, entity type, and reporting period.
- Column mappings, units, and a row preview.
- Missing metadata, invalid rows, possible duplicates, and conflicts.

Preserve original files unchanged. Keep import timestamps, file hashes, source filenames, worksheet/row references where available, validation results, and snapshot membership.

Create a practical observation model that retains:
- Platform and account identity.
- Entity type and stable ID: artist, track, release, playlist, post, video, campaign, or audience segment.
- Metric name, value, unit, definition, and relevant dimensions.
- Reporting-period start/end and time grain.
- Capture/as-of timestamp separately from import timestamp.
- Source timezone when known.
- Measurement type: period count, distinct audience count, cumulative total, point-in-time count, or rate.
- Source/import references and verification or availability status.

Do not invent unknown timestamps or timezones. Preserve source daily date buckets; a date-only total cannot simply be reassigned to another timezone.

Maintain a metric dictionary covering definitions, denominators, supported aggregations, and comparison rules. Preserve stable platform IDs. Where IDs are missing, retain source-scoped identities and provide explicit mappings; never silently merge tracks or accounts because names look similar.

Repeatedly importing the same file for the same snapshot must leave totals unchanged. Different files containing overlapping observations must not double-count them. Retain revised observations as versions, with an explicit rule selecting the active version. Preserve intentionally separate snapshots even if their values are identical.

Report rejected or ambiguous rows rather than dropping them silently. Handle missing values, suppressed values, genuine zeros, date formats, percentage units, and numeric separators deliberately.

Provide a canonical CSV template for verified manual readings that cannot be exported, including the reporting window, capture date, and evidence reference.

## 4. Baseline and measurement rules

The October 20 baseline is an identified original snapshot with its original reporting windows. It is not simply every record dated before October 20.

Keep baseline membership and values immutable. Later exports covering older dates must not rewrite it. If baseline files cannot be identified reliably, mark the baseline unavailable or unverified instead of reconstructing it from newer data.

Offer baseline and newer-snapshot selection. Distinguish:
- Comparing revisions of the same historical reporting window.
- Comparing performance between different but compatible reporting periods.

Apply these rules consistently:
- Missing data stays missing; never replace it with zero by default.
- Do not sum daily unique listeners into monthly unique listeners.
- Do not sum reach or distinct audiences across overlapping segments, periods, or platforms.
- Do not add rolling-window snapshots, lifetime totals, or follower balances together.
- Do not combine account totals with their track/post breakdowns as additional activity.
- Recompute rates from compatible numerator and denominator totals when available.
- Compare equivalent metrics, populations, definitions, and period lengths.
- Show unavailable comparisons when compatible data does not exist.
- Preserve gaps and incomplete periods in charts.

Every KPI should expose its definition, period, snapshot, and source. Use the same calculation layer for cards, charts, tables, summaries, and downloads.

## 5. Dashboard views

### A. Overview

Help me answer: What changed, what is performing, and what deserves attention?

Show a small set of supported KPIs grouped by platform, their trends, and valid previous-period comparisons. Include data freshness and coverage. Offer date-range controls and convenient 7-, 28-, and 90-day selections where supported.

Use platform-native measures. Do not combine streams, views, impressions, reach, and followers into a misleading total audience or performance score.

Include concise, filter-aware observations backed by displayed numbers: growing tracks, strong content, declining metrics, or gaps that prevent a conclusion. These can be deterministic calculations and do not require an LLM.

### B. Spotify

Where supported, include:
- Streams, listeners, followers, saves, playlist additions, and their trends.
- Track and release comparisons with drill-down to source rows.
- Streams per listener and clearly defined saves-per-listener or other ratios when valid.
- Countries, cities, demographics, audience segments, and sources of streams.
- Playlist performance and contribution where the source supports it.

Label rolling monthly listeners distinctly from daily listeners or a selected period's unique listeners. Do not describe saves/listeners as a unique-person conversion rate unless the underlying data actually measures that.

Show unavailable requested sections with the specific missing export or field. Do not manufacture an “average Spotify artist” benchmark or percentile; require an appropriate documented comparison dataset.

### C. Social media

Provide Facebook, Instagram, and TikTok account filters and platform-specific views.

Use available measures such as followers, reach, impressions, video views, watch time, profile visits, link clicks, likes, comments, shares, and saves. Show post/video performance with publish date, format, title or caption excerpt, and source URL where available.

Separate paid and organic results when the source distinguishes them. Keep platform-specific definitions visible. Label each engagement rate by its denominator; reach-based and impression-based rates should not be presented as equivalent.

Respect whether content metrics describe lifetime performance, a reporting window, or performance at a particular content age. Avoid comparing a new post with an older post as if both had equal exposure time.

Include paid-campaign metrics only when relevant data exists, with currency and attribution definitions retained.

### D. Cross-platform trends and campaigns

Help me explore whether social activity and streaming movement occur together.

Show aligned time series on shared dates, with clearly labeled units. Offer an optional indexed view beginning at 100 on a valid common reference date, alongside access to absolute values. Explain the index and handle zero starting values.

Provide editable local annotations for releases, posts, shows, and campaigns. Keep user-entered annotations distinguishable from imported observations. Allow explicit links between content/campaigns and tracks.

If sufficiently complete, compatible daily series exist, add exploratory correlation and lag analysis. Use a configurable minimum observation count, defaulting to 30 matched days. Display the matched sample size, dates, lag direction, and missing-data treatment. Do not fill absent observations with zero. Explain that trends, seasonality, and other factors can influence correlations.

Do not claim that a social post caused streams, or calculate listener conversion, revenue, or campaign ROI without suitable attribution and outcome data.

### E. Data and collection

Show source inventory, import history, accounts, date coverage, snapshot membership, validation issues, metric definitions, and collection gaps.

Import the actual collection queue when accessible. Preserve its recorded status and timestamp; keep local notes or status changes separate from the source. App development or a successful file import does not automatically complete unrelated collection tasks.

Let me inspect the records behind a metric and export filtered data with its period, snapshot, units, and source references. Provide CSV downloads and a simple downloadable Markdown analysis summary.

When a platform has no data, show an informative empty state, an upload path, and the required template.

## 6. Practical behavior

The application must work after restart without re-uploading everything. Cache expensive transformations while invalidating stale results after imports or mapping changes. Make filters consistent across charts, tables, summaries, and exports.

Keep credentials, private source files, databases, and local exports out of version control. Include a suitable .gitignore. Read the source workbook without changing it. Keep external publishing and source writeback outside this initial build.

Do not assume consumer Spotify access supplies private Spotify for Artists analytics. Verify any proposed API integration against current official documentation and actual access. The core dashboard must remain usable with local exports.

Do not invent analytics to fill the interface. If demo data is helpful for development, isolate it in an explicitly selected, prominently labeled demo mode with separate storage.

## 7. Delivery and acceptance

Deliver the complete source code, reproducible dependency setup, README, import templates, metric dictionary, tests, and operating instructions. Provide exact installation and launch commands, ideally ending in:

python -m streamlit run app.py

The README should explain adding new exports, selecting snapshots, preserving the baseline, correcting mappings, backing up data, and the limits of cross-platform comparisons.

Verify:
1. The app starts with no data and provides a useful import screen.
2. An available real dataset imports and reconciles to its source values. If no real data is accessible, state that limitation and test the workflow with isolated fixtures.
3. Reimporting the same snapshot does not duplicate observations or change totals.
4. Overlapping and revised exports resolve predictably.
5. A newer snapshot cannot change the October 20 baseline.
6. Missing values remain distinct from zero.
7. Derived rates use the correct denominator and handle zero denominators.
8. Charts, tables, and downloads agree under the same filters.
9. Data and mappings survive restart.
10. The main views render without errors or broken controls.

Use tests for the consequential data rules and a focused UI smoke check. Report which checks actually ran.

Work in small steps: inspect the sources, implement ingestion and persistence, build the core views, add supported comparisons, verify, and launch. Make reasonable reversible implementation choices yourself. Ask only for missing information that materially blocks progress, while completing unaffected work.

Finish by giving me the launch command or local URL, a short feature summary, the data actually loaded, verified behavior, and specific remaining data/access gaps. Do not describe unfinished connectors or unavailable analytics as completed features.

