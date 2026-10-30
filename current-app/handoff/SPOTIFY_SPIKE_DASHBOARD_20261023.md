# Spotify spike drill-down

Implemented in Cross-platform → Posts & Spotify → Spotify spikes. The view ranks positive absolute changes between consecutive complete Monday–Sunday Spotify weeks using the selected saved repository. Listener comparisons use the average of daily unique counts, not weekly unique people. Prior comparisons are calculated before filtering target weeks; missing weeks cannot become adjacent baselines.

Clicking a ranking bar or choosing a rising week selects its stream/listener KPIs and daily context. Content windows include the selected week, the preceding week by default, and optionally the following week. Type and literal caption/ID/link filters affect only the publication list and its CSV. Expanders show full retained captions and separate original links. Dates disputed within one week remain explicit; unknown or cross-week dates are excluded. Strict band-authored platform/account/post identities are deduplicated. Missing captions remain unavailable. Saved Story links may have expired; external links were inspected, not opened or verified remotely.

Files: stats_app/analysis_spikes.py, stats_app/analysis_spikes_ui.py; integration in analysis_correlation_ui.py; usage in README.md. The existing timeline and reviewed inference remain available. No saved analysis CSV is hardcoded as the live data source.

Verification on October 23, 2026:

- 20 spike-helper tests passed, including independent known-source rankings, calendar gaps, zero baselines, missing metrics, full captions and identity/date rules.
- 7 new spike UI tests passed, including filters, pagination, exports, callback state, empty sources and missing daily observations.
- 22 existing correlation helper tests, 7 existing correlation UI tests and 4 analysis app tests passed. Existing NumPy timedelta deprecation warnings remain in the older timeline code.
- Live in-app browser: clicked the +500 stream bar and confirmed February 23, 2026, 2,201 streams and 200.1 average daily listeners; switched to listener ranking; inspected full caption and original Instagram link; searched by post ID and restored the full list. Chart and caption views inspected at normal width; ranking inspected at 520px with navigation collapsed. No browser console errors observed in the final session.
- Screenshots: test-results/spike-dashboard-20261023/spike-selection.jpg, spike-caption-detail.jpg and spike-narrow.jpg.
- Active immutable source meta-content-20261023 retained SHA-256 a055587589c82f49cd9b6554a978588964824ef3fc77696ed1cc9732dead60e3.

The local Streamlit service is running at http://127.0.0.1:8501/ with the existing library. Associations remain descriptive; no causal attribution or fresh Meta collection was added.
