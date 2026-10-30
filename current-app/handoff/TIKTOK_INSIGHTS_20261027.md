# TikTok insights delivery — October 27, 2026

The reporting issue is resolved through The Stats' native dashboard. **Analysis → TikTok insights** contains the complete fixed cross-platform readout, recommendations, charts, linked post examples and downloadable evidence. **Explore → TikTok → Strongest posts** adds native reporting-window rankings and separate cumulative post snapshots. TikTok for Artists remains pending.

The prior missing report runtime is no longer required. The earlier draft, original analysis outputs and original failure receipt remain intact. The finalized report package is pinned by manifest SHA-256 `97e61defd3e6d73c88fe1dac3f20d5a8a2b0a1a7f37f46a4905d5defe79416d7`.

## Acceptance

- 63 distinct relevant checks passed across the final report, ranking, navigation, existing TikTok, cross-platform and decision-page tests. The initial UI test capture missed column-bound download controls; its final rerun passed.
- The Windows project launcher was restarted on `127.0.0.1:8501`; health returned HTTP 200 and `ok`. The six report views, charts, two-way shortcuts, ranking period changes, cumulative scope and post-ID search were inspected in the browser.
- Complete HTML, provenance JSON and ranking CSV were downloaded through the dashboard. HTML matches the sealed package byte for byte. Provenance contains the full manifest and source receipts. Ranking CSV retains all ten matching 28-day rows and exact post identifiers, with leading follower counts 14/14/11.
- Offline HTML structure and embedded assets passed package tests. Its file-URL preview was not performed because the in-app browser blocks that protocol; the native dashboard itself was visually verified.
- All 21 recorded library paths, eight original analytical outputs and seven report input paths retain their recorded hashes.

See [usage and reproduction](../docs/TIKTOK_INSIGHTS_20261027.md). Exact hashes, test logs and screenshots are retained in `outputs/dashboard_insights_20261027/VERIFICATION.json` and its adjacent files. Normal future launches continue to use `launch_windows.bat`; this task's hidden launcher runs the same project launch script with `--no-browser`.
