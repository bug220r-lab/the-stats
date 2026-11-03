"""Weekly content/Spotify exploration alongside the fixed reviewed analysis."""
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from stats_app import dashboard_controls as controls
from stats_app.analysis_correlation import (
    build_weekly_activity, select_complete_weeks, correlation_pairs,
    describe_association, load_reviewed_results,
)
from stats_app.analysis_repository import AnalysisRepository
from stats_app.analysis_social_metrics import filtered_csv
from stats_app.analysis_ui_common import chart, fmt
from stats_app.analysis_spikes_ui import render_spikes

LABELS = {"facebook_posts": "Facebook posts", "instagram_stories": "Instagram Stories",
          "instagram_feed": "Instagram feed posts", "streams": "Streams", "saves": "Saves",
          "playlist_adds": "Playlist additions", "mean_daily_listeners": "Average daily listeners",
          "net_followers": "Net new followers"}
COLORS = {"facebook_posts": "#79AFFF", "instagram_stories": "#F5A866", "instagram_feed": "#CF9BFF"}
OUTCOMES = ["streams", "mean_daily_listeners", "saves", "playlist_adds", "net_followers"]
SP = "spotify/cleaned/"


@st.cache_data(show_spinner=False, max_entries=8)
def _cached_activity(path, modified_ns, size):
    # Registered sources are immutable. File identity also invalidates replacement snapshots.
    return build_weekly_activity(AnalysisRepository(path))


def _activity(repo):
    if hasattr(repo, "db_path"):
        path = Path(repo.db_path)
        stat = path.stat()
        return _cached_activity(str(path), stat.st_mtime_ns, stat.st_size)
    return build_weekly_activity(repo)


def _csv(label, frame, filename, key):
    st.download_button(label, filtered_csv(frame), filename, "text/csv", key=key)


def timeline_figure(weekly, exposures, outcome, releases):
    """Separate units, shared week axis, with no implied conversion ratio."""
    weekly = weekly.reindex(pd.date_range(weekly.index.min(), weekly.index.max(), freq="W-MON"))
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.12,
                        row_heights=[.43, .57])
    for exposure in exposures:
        fig.add_trace(go.Bar(x=weekly.index, y=weekly[exposure], name=LABELS[exposure],
                            marker_color=COLORS[exposure],
                            hovertemplate="Week of %{x|%b %d, %Y}<br>%{y:,.0f} retained items<extra>%{fullData.name}</extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=weekly.index, y=weekly[outcome], name="Spotify · " + LABELS[outcome],
                            mode="lines+markers", marker=dict(size=4), line=dict(color="#6FD6AE", width=2),
                            connectgaps=False,
                            hovertemplate="Week of %{x|%b %d, %Y}<br>%{y:,.1f}<extra>%{fullData.name}</extra>"), row=2, col=1)
    for event in releases.itertuples():
        stamp = pd.Timestamp(event.date)
        if weekly.index.min() <= stamp <= weekly.index.max() + pd.Timedelta(days=6):
            fig.add_vline(x=stamp, line_color="#8291A8", line_dash="dot", opacity=.5)
    fig.update_yaxes(title_text="Retained items", rangemode="tozero", row=1, col=1)
    fig.update_yaxes(title_text=LABELS[outcome], rangemode="tozero", row=2, col=1)
    fig.update_xaxes(title_text="Week starting Monday", row=2, col=1)
    fig.update_layout(height=530, barmode="group", hovermode="x unified")
    return fig


def _period(weekly):
    low, high = weekly.index.min().date(), (weekly.index.max() + pd.Timedelta(days=6)).date()
    preset = controls.selectbox("Comparison period", ["Reviewed 2024–2025", "2026 available", "All Spotify history", "Custom"],
                                key="correlation:period")
    if preset == "Reviewed 2024–2025":
        return date(2024, 1, 1), date(2025, 12, 28)
    if preset == "2026 available":
        return date(2026, 1, 1), high
    if preset == "Custom":
        return controls.date_range("Comparison dates", low, high, (low, high), key="correlation:dates")
    return low, high


def _timeline(repo, bundle):
    weekly = bundle["weekly"]
    if weekly.empty:
        st.info("No complete Monday–Sunday Spotify weeks are available in this source.")
        return
    a, b, c = st.columns([1.3, 1.2, 1])
    with a:
        period = _period(weekly)
    with b:
        outcome = controls.selectbox("Spotify activity", OUTCOMES, format_func=LABELS.get, key="correlation:outcome")
    with c:
        timing = controls.selectbox("Spotify timing", ["Same week", "Following week"], key="correlation:timing")
    exposures = controls.multiselect("Publishing series", list(COLORS), default=list(COLORS)[:2],
                                     format_func=LABELS.get, key="correlation:exposures")
    if period is None:
        return
    data = select_complete_weeks(weekly, *period)
    if data.empty:
        st.info("No complete Monday–Sunday weeks fall entirely inside this date range. Widen the range to compare activity.")
        return
    if not exposures:
        st.info("Choose at least one publishing series to compare with Spotify.")
        return
    st.caption(f"{data.index.min():%b %d, %Y} – {data.index.max() + pd.Timedelta(days=6):%b %d, %Y} · "
               f"{len(data)} complete calendar weeks. Boundary weeks are excluded. Social publication dates retain their source calendar; Spotify uses UTC.")
    st.caption("Counts include each strictly band-authored platform/account/post identity once. A zero means no retained publication, not verified silence. Lifetime reach, views and engagement are not assigned to publication weeks.")
    if data.index.max().year >= 2026:
        st.warning("2026 coverage is uneven: Facebook and Instagram feed exports drop sharply after May and end in August. Blank tails are unavailable; retained zero weeks within the source span do not prove no publishing.")
    if "instagram_feed" in exposures:
        st.warning("Older Instagram feed history is incomplete. This series is descriptive only and is excluded from the reviewed 20-comparison analysis.")
    if outcome == "mean_daily_listeners":
        st.caption("Average daily listeners is the mean of seven daily counts; it is not a count of unique weekly listeners.")
    elif outcome == "net_followers":
        st.caption("Net new followers sums seven consecutive daily follower-stock changes. The prior day's stock is required; unavailable changes remain blank.")
    else:
        st.caption(f"Spotify {LABELS[outcome].lower()} sum seven daily values; any missing daily value leaves that week unavailable.")
    cards = st.columns(len(exposures))
    for col, exposure in zip(cards, exposures):
        col.metric("Retained " + LABELS[exposure], fmt(data[exposure].sum(min_count=1)))
    show_releases = st.checkbox("Show release dates", value=True, key="correlation:release-markers")
    releases = repo.table(SP + "release_events.csv") if SP + "release_events.csv" in repo.tables else pd.DataFrame(columns=["date", "release_title"])
    releases = releases.loc[pd.to_datetime(releases.date).between(data.index.min(), data.index.max() + pd.Timedelta(days=6))]
    chart(timeline_figure(data, exposures, outcome, releases if show_releases else releases.iloc[:0]), "correlation-timeline")
    if show_releases and not releases.empty:
        st.caption("Dotted lines mark releases: " + "; ".join(f"{r.date}: {r.release_title}" for r in releases.itertuples()))

    lag = int(timing == "Following week")
    st.subheader("Weekly changes compared")
    st.caption(f"Publishing week t pairs with Spotify week t{' + 1' if lag else ''}. "
               "The timeline above shows activity levels on their actual dates. The comparisons below use adjacent weekly changes in log(1 + count), "
               "or inverse hyperbolic sine for follower changes, to reduce the influence of scale and long-term trends.")
    estimates, pair_exports = [], []
    fig = go.Figure()
    for exposure in exposures:
        estimate = describe_association(data, exposure, outcome, lag=lag)
        estimates.append({"Publishing series": LABELS[exposure], "Spearman correlation": estimate["rho"], "Paired weeks": estimate["n"]})
        pairs = correlation_pairs(data, exposure, outcome, lag=lag)
        if not pairs.empty:
            display = pairs.reset_index()
            display["publishing_week"] = pairs.index.strftime("%Y-%m-%d")
            fig.add_trace(go.Scatter(x=pairs.x, y=pairs.y, mode="markers", name=LABELS[exposure],
                                    marker=dict(color=COLORS[exposure], size=8, opacity=.7),
                                    customdata=list(zip(pairs.index.strftime("%Y-%m-%d"), pd.to_datetime(pairs.target_week).dt.strftime("%Y-%m-%d"))),
                                    hovertemplate="Publishing week: %{customdata[0]}<br>Spotify week: %{customdata[1]}<br>Publishing change: %{x:.3f}<br>Spotify change: %{y:.3f}<extra>%{fullData.name}</extra>"))
            display["exposure"], display["outcome"], display["lag_weeks"] = exposure, outcome, lag
            pair_exports.append(display)
    st.dataframe(pd.DataFrame(estimates), hide_index=True, width="stretch", column_config={
        "Spearman correlation": st.column_config.NumberColumn(format="%.3f")})
    st.caption("Descriptive coefficients for your selection. Undefined means too few pairs or no variation. Custom filters do not receive saved confidence intervals or adjusted p-values. See Reviewed results for the fixed analysis and uncertainty; correlation does not establish cause or post-to-stream conversion.")
    if pair_exports:
        fig.add_hline(y=0, line_dash="dot", line_color="#8291A8", opacity=.6)
        fig.add_vline(x=0, line_dash="dot", line_color="#8291A8", opacity=.6)
        fig.update_layout(height=330, xaxis_title="Change in log(1 + retained items)",
                          yaxis_title="Change in asinh(net new followers)" if outcome == "net_followers" else "Change in log(1 + Spotify activity)")
        chart(fig, "correlation-scatter")
        _csv("Download selected weekly pairs · CSV", pd.concat(pair_exports, ignore_index=True), "posts_spotify_pairs.csv", "correlation-pairs-csv")
    export_columns = [*exposures, outcome, "spotify_days", "week_end", *[e + "_status" for e in exposures]]
    _csv("Download selected weekly activity · CSV", data[[c for c in export_columns if c in data]].rename_axis("week_start").reset_index(),
         "posts_spotify_weekly.csv", "correlation-weekly-csv")
    _details(bundle["identities"], data, exposures)
    with st.expander("Coverage, definitions and sources"):
        for caption in bundle.get("captions", []):
            st.write(caption)
        st.caption("Weekly aggregation cannot fully reconcile source-calendar publication dates with UTC Spotify dates. The reviewed analysis includes a one-day boundary sensitivity. Facebook Stories are unavailable; deferred Story song mappings remain unresolved.")
        st.json({**bundle["coverage"], "selected_complete_weeks": len(data),
                 "selected_start": str(data.index.min().date()),
                 "selected_end": str((data.index.max() + pd.Timedelta(days=6)).date())})
        st.caption("Sources: Spotify artist_daily.csv and release_events.csv; social/posts_latest.csv; social/meta_collection/instagram_stories_manual.csv; social/meta_content_20261023/content_snapshots.csv and identity_bridges.csv. The selected saved version supplies all timeline data.")


def _details(identities, weekly, exposures):
    with st.expander("Posts & Stories behind these weeks"):
        st.caption("This drill-down changes the records below only. The timeline and correlations keep the comparison filters above. Conflicting publication days remain explicit when they agree on the same week.")
        chosen = controls.selectbox("Inspect publishing week", ["All selected weeks", *weekly.index.strftime("%Y-%m-%d")], key="correlation:inspect-week")
        query = controls.text_input("Search post text, ID or link", key="correlation:post-search")
        items = identities.copy()
        week = pd.to_datetime(items.week, errors="coerce")
        included = pd.Series(False, index=items.index)
        for exposure in exposures:
            included |= items.exposure.eq(exposure) & week.isin(weekly.index[weekly[exposure].notna()])
        items = items.loc[items.band_authored & included]
        st.caption("Records match the available publishing bins in the timeline. Source-edge or ambiguous weeks with unavailable counts are excluded.")
        if chosen != "All selected weeks":
            items = items.loc[pd.to_datetime(items.week).eq(pd.Timestamp(chosen))]
        if query.strip():
            fields = [c for c in ["description", "post_id", "permalink"] if c in items]
            items = items.loc[items[fields].fillna("").astype(str).apply(lambda row: " ".join(row), axis=1).str.contains(query.strip(), case=False, regex=False)]
        columns = [c for c in ["week", "platform", "post_id", "post_type", "description", "dates", "date_conflict", "permalink"] if c in items]
        st.caption(f"{len(items):,} retained identities in this drill-down.")
        st.dataframe(items[columns], hide_index=True, width="stretch", column_config={
            "week": "Publishing week", "dates": "Retained publication dates", "description": st.column_config.TextColumn("Post text", width="large"),
            "permalink": st.column_config.LinkColumn("Open post", display_text="Open")})
        _csv("Download inspected posts & Stories · CSV", items, "posts_spotify_content.csv", "correlation-content-csv")


def _reviewed(repo):
    reviewed = load_reviewed_results(repo)
    if reviewed["status"] != "available":
        st.info("Reviewed post/Spotify results are unavailable for this saved source version. " + reviewed["reason"])
        return
    st.caption("Fixed reviewed window: January 1, 2024 – December 28, 2025 · 104 complete weeks · 306 Facebook posts · 594 Instagram Stories. Timeline filters do not change these results.")
    st.info("Instagram Stories show positive same-week co-movement with streams in 2024–2025, with no consistent next-week pattern across periods. None of the 20 comparisons has a BH-adjusted p-value below 0.05.")
    outcome = controls.selectbox("Reviewed Spotify outcome", OUTCOMES, format_func=LABELS.get, key="correlation:reviewed-outcome")
    all_results = reviewed["results"]
    selected = all_results.loc[all_results.outcome.eq(outcome)].copy()
    selected["Comparison"] = selected.apply(lambda r: f"{LABELS[r.exposure]} · {'following week' if r.lag_weeks else 'same week'}", axis=1)
    fig = go.Figure(go.Scatter(x=selected.rho, y=selected.Comparison, mode="markers", marker=dict(size=10, color="#79AFFF"),
                              error_x=dict(type="data", symmetric=False, array=(selected.ci4_high-selected.rho), arrayminus=(selected.rho-selected.ci4_low)),
                              customdata=selected[["n", "q_bh_20"]].values,
                              hovertemplate="%{y}<br>Correlation: %{x:.3f}<br>Pairs: %{customdata[0]}<br>BH-adjusted p: %{customdata[1]:.3f}<extra></extra>"))
    fig.add_vline(x=0, line_dash="dash", line_color="#8291A8")
    fig.update_layout(height=300, xaxis=dict(range=[-1, 1]), xaxis_title="Spearman correlation of weekly changes", showlegend=False)
    chart(fig, "correlation-reviewed")
    st.caption("Bars show approximate pointwise 95% intervals from a four-week block bootstrap. They are not simultaneous intervals. Adjusted p-values retain all 20 planned comparisons, even when one outcome is displayed.")
    st.dataframe(selected[["Comparison", "n", "rho", "ci4_low", "ci4_high", "q_bh_20", "rho_without_release", "rho_2024", "rho_2025"]],
                 hide_index=True, width="stretch", column_config={"n": "Paired weeks", "rho": st.column_config.NumberColumn("Correlation", format="%.3f"),
                 "ci4_low": st.column_config.NumberColumn("95% lower", format="%.3f"), "ci4_high": st.column_config.NumberColumn("95% upper", format="%.3f"),
                 "q_bh_20": st.column_config.NumberColumn("BH-adjusted p · 20 tests", format="%.3f"),
                 "rho_without_release": st.column_config.NumberColumn("Release-window excluded", format="%.3f"),
                 "rho_2024": st.column_config.NumberColumn("2024", format="%.3f"), "rho_2025": st.column_config.NumberColumn("2025", format="%.3f")})
    _csv("Download all 20 reviewed comparisons · CSV", all_results, "social_spotify_reviewed.csv", "correlation-reviewed-csv")
    with st.expander("Methods, sensitivity checks and analysis provenance"):
        for caption in reviewed.get("captions", []):
            st.write(caption)
        st.write("Twenty exploratory tests: two publishing series × five Spotify outcomes × same/following week. Adjacent-week log changes reduce trend effects; follower flows use asinh. Circular-shift tests and BH correction accompany 2,000 paired circular block-bootstrap resamples. Release-window exclusions, annual subsets, influential-week removal, alternative block lengths, reverse lag and one-day date shifts remain in the full export. This is not a causal or fully seasonality-adjusted model.")
        st.caption("2026 is a separate descriptive sensitivity with uneven publishing coverage, not an extension of the reviewed testing family. Its source spans differ by publishing series.")
        st.dataframe(reviewed["sensitivity_2026"], hide_index=True, width="stretch")
        _csv("Download 2026 sensitivity · CSV", reviewed["sensitivity_2026"], "social_spotify_2026_sensitivity.csv", "correlation-2026-csv")
        st.json(reviewed["manifest"])


def render_posts_spotify(repo):
    st.subheader("Posts & Stories alongside Spotify")
    try:
        bundle = _activity(repo)
    except (ValueError, KeyError) as exc:
        st.error("Weekly activity could not be interpreted: " + str(exc))
        return
    controls.own_keys("correlation:tabs")
    tabs = st.tabs(["Spotify spikes", "Timeline & comparison", "Reviewed results"],
                   key="correlation:tabs", on_change="rerun")
    for tab, render in zip(tabs, (lambda: render_spikes(repo, bundle),
                                 lambda: _timeline(repo, bundle), lambda: _reviewed(repo))):
        if tab.open:
            with tab:
                render()
