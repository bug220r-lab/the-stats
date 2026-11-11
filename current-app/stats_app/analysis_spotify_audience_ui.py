"""Compact dedicated views for Spotify audience evidence already retained."""
from datetime import date, timedelta

import plotly.express as px
import streamlit as st

from stats_app.analysis_ui_common import chart, download, evidence, fmt
from stats_app.spotify_audience import (
    ARTIST_DAILY, DEFINITIONS_URL, SEGMENT_CAPTURE, SEGMENT_DAILY,
    audience_movement, audience_segment_daily, super_listener_history,
)


def render_audience_segments(repo):
    """Existing Audience & sources → Audience segments view."""
    segments = audience_segment_daily(repo)
    if segments.empty:
        path = "spotify/cleaned/audience_segment_snapshot.csv"
        snapshot = repo.table(path)
        st.caption("Retained audience segment snapshot; dated segment history is unavailable in this analysis version.")
        chart(px.bar(snapshot, x="listeners", y="segment", orientation="h"), "segments")
        evidence(repo, path, snapshot, "audience_segments_snapshot")
        return
    last = segments.iloc[-1]
    st.caption(f"Segment history · Worldwide · {segments.date.min()} – {segments.date.max()} UTC · "
               f"{fmt(last.total_audience)} total audience at the final endpoint. "
               "Audience balances and rolling windows are not daily additions.")
    left, right = st.columns(2)
    with left:
        st.markdown("**Audience segments**")
        fields = {"monthly_active_listeners": "Monthly active", "previously_active": "Previously active", "programmed": "Programmed"}
        plot = segments.melt(id_vars=["date"], value_vars=list(fields), var_name="Segment", value_name="Listeners")
        plot["Segment"] = plot.Segment.map(fields)
        figure = px.line(plot, x="date", y="Listeners", color="Segment", labels={"date": "UTC endpoint"})
        figure.update_traces(connectgaps=False)
        figure.update_layout(height=300, xaxis_title=None, legend_title_text=None)
        chart(figure, "spotify_segment_history", legend=dict(orientation="h", y=1.02, yanchor="bottom"),
              margin=dict(t=60, l=10, r=10, b=20))
    with right:
        st.markdown("**Super listeners**")
        history = super_listener_history(repo)
        span = st.selectbox("Super-listener history", ["Latest 90 days", "All retained dates"],
                            key="spotify:super-listener-span", label_visibility="collapsed")
        shown = history
        if span == "Latest 90 days" and not history.empty:
            start = date.fromisoformat(history.date.max()) - timedelta(days=89)
            shown = history.loc[history.date.ge(str(start))].copy()
        figure = px.line(shown, x="date", y="rolling28_super_listeners",
                         labels={"date": "UTC endpoint", "rolling28_super_listeners": "Rolling 28-day listeners"})
        figure.update_traces(connectgaps=False)
        figure.update_layout(height=265)
        chart(figure, "spotify_super_listener_history")
        st.caption(f"{shown.date.min()} – {shown.date.max()} · latest {fmt(shown.iloc[-1].rolling28_super_listeners) if not shown.empty else 'Unavailable'}")
    movement = audience_movement(repo)
    if not movement.empty:
        scope = movement.iloc[0]
        st.markdown("**Audience movement**")
        if scope.period_start is not None and scope.period_end is not None:
            st.caption(f"{scope.period_start} – {scope.period_end} · Worldwide · source-defined groups may overlap.")
        else:
            st.caption("The retained movement capture lacks an unambiguous reporting scope; values remain unavailable.")
        for column, row in zip(st.columns(3), movement.itertuples()):
            column.metric(row.label, fmt(row.value), help=row.definition)
    with st.expander("Definitions and retained audience records"):
        st.caption("Monthly active listeners intentionally streamed in the last 28 days. Previously active listeners have left that active window; programmed listeners have no active-source listening in the past two years. Total audience spans two years.")
        st.caption("Super listeners intentionally streamed at least 15 times in the last 28 days. They are a subset of monthly active listeners. Stocks must not be summed across dates; movement groups are not an additive growth total.")
        st.markdown(f"[Spotify audience definitions]({DEFINITIONS_URL})")
        st.caption(f"Segment history source: {SEGMENT_DAILY} · SHA-256 {segments.attrs.get('source_sha256')}")
        st.dataframe(segments, hide_index=True, width="stretch")
        download(segments, "retained_audience_segment_daily.csv", "spotify_segments_interpreted_csv")
        st.download_button("Download unchanged segment source", repo.original_bytes(SEGMENT_DAILY),
                           "audience_segment_daily.csv", "text/csv", key="spotify_segments_raw_csv")
        if not movement.empty:
            st.caption("Movement counts were read from the saved rendered capture, retaining exact source lines and scope. No native export was inferred.")
            st.dataframe(movement, hide_index=True, width="stretch")
            download(movement, "retained_audience_movement.csv", "spotify_movement_csv")
            st.download_button("Download unchanged movement capture", repo.original_bytes(SEGMENT_CAPTURE),
                               "audience_segments.txt", "text/plain", key="spotify_movement_raw")
        st.caption(f"Super-listener source: {ARTIST_DAILY}. Export includes only the displayed history interval.")
        st.dataframe(shown, hide_index=True, width="stretch")
        download(shown, "super_listener_history.csv", "spotify_super_history_csv")
        st.download_button("Download unchanged artist history", repo.original_bytes(ARTIST_DAILY),
                           "artist_daily.csv", "text/csv", key="spotify_super_history_raw")
