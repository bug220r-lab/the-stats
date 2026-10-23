"""Scoped exploration of reconciled Spotify recovery evidence."""
import pandas as pd
import plotly.express as px
import streamlit as st

from stats_app.analysis_ui_common import chart, evidence, fmt
from stats_app.analysis_metrics import require_unique, source_ratio_plot_values

SP = "spotify/cleaned/"


def _select(data, column, title, key):
    choices = sorted(data[column].dropna().unique().tolist())
    if not choices:
        st.info(f"No retained {title.lower()} is available for this selection.")
        return data.iloc[:0]
    value = st.selectbox(title, choices, key=key)
    return data.loc[data[column].eq(value)].copy()


def recovery_summary(repo):
    coverage = repo.table(SP+"recovery_coverage.csv")
    tracks = repo.table(SP+"track_daily_long.csv")
    a, b, c = st.columns(3)
    a.metric("Recording × metric histories", len(coverage))
    b.metric("Canonical song-day-metric values", fmt(len(tracks)))
    c.metric("Historical reporting endpoint", "October 20, 2026")
    st.caption("Recovered chart observations fill historical gaps in a new analysis version. They are not new native exports. Earlier analysis and source files remain available unchanged.")
    if SP+"remaining_limits.csv" in repo.tables:
        st.subheader("Remaining collection limits")
        remaining = repo.table(SP+"remaining_limits.csv")
        columns = [c for c in ["Data", "Recording", "Status", "Next action"] if c in remaining]
        st.dataframe(remaining[columns] if columns else remaining, hide_index=True, width="stretch")
    if "audit/recovery_changes.json" in repo.file_catalog().path.tolist():
        with st.expander("Before and after reconciliation"):
            import json
            st.json(json.loads(repo.text("audit/recovery_changes.json")))


def render_sources(repo):
    st.subheader("Recovered source comparisons")
    st.caption("Cumulative source masters are reconciled once. Select one entity, population, window, metric and hierarchy; earlier supplements are not appended again.")
    path = SP+"source_recovery.csv"
    master = repo.table(path)
    data = master.copy()
    data = _select(data, "Scope", "Source scope", "recovery_scope")
    identities = data[["Spotify ID", "Recording"]].drop_duplicates()
    labels = dict(zip(identities["Spotify ID"], identities["Recording"]))
    entity = st.selectbox("Source entity", list(labels), format_func=labels.get)
    data = data.loc[data["Spotify ID"].eq(entity)]
    data = _select(data, "Population", "Source population", "recovery_population")
    windows = data[["Period start", "Period end", "Previous start", "Previous end"]].drop_duplicates()
    values = [tuple(row) for row in windows.itertuples(index=False, name=None)]
    chosen = st.selectbox("Source reporting window", values,
                          format_func=lambda row: f"{row[0]} – {row[1]} (prior {row[2]} – {row[3]})")
    for column, value in zip(windows.columns, chosen):
        data = data.loc[data[column].eq(value)]
    period_listeners = data.loc[data["Metric"].eq("listeners")].copy()
    data = _select(data, "Metric", "Recovered source metric", "recovery_metric")
    if data.empty: return
    metric = data["Metric"].iloc[0]
    data = _select(data, "Hierarchy level", "Recovered source hierarchy", "recovery_level")
    if data.empty: return
    require_unique(data, ["Source"])
    st.warning("Source parents overlap their children. Listeners overlap source categories and dates. Ratios and unique audiences are never summed. Missing table values remain unavailable, even when a daily chart explicitly shows zero.")
    st.caption(f"Reporting: {chosen[0]} – {chosen[1]} · prior {chosen[2]} – {chosen[3]}. Basis: {', '.join(data['Reporting basis'].dropna().unique())}. Capture timestamps and evidence labels are retained with each row.")
    if chosen[1] > "2026-10-20":
        st.info("Newer reporting snapshot: this selected window extends beyond the October 20 historical endpoint.")
    plotted = data.copy()
    for column in ["Current value", "Previous value"]:
        plotted[column] = pd.to_numeric(plotted[column], errors="coerce")
    if metric == "streams_per_listener":
        plotted, undefined, unknown = source_ratio_plot_values(plotted, period_listeners, ["Source"], ["Current value", "Previous value"])
        st.caption(f"Period ratios: {undefined} readings with invalid or nonpositive listener denominators and {unknown} without finite denominator evidence are omitted from the chart. Source readings remain unchanged below.")
    bars = plotted.melt(id_vars=["Source"], value_vars=["Current value", "Previous value"],
                        var_name="Interval", value_name="Value").dropna(subset=["Value"])
    if bars.empty:
        st.info("No numeric period reading is available for this scope.")
    else:
        chart(px.bar(bars, x="Value", y="Source", color="Interval", barmode="group", orientation="h",
                     labels={"Value":metric.replace('_',' ').capitalize()}), "recovery_source_period")
    st.dataframe(data[["Source", "Hierarchy level", "Current value", "Previous value", "Reporting basis", "Collected UTC", "Evidence"]],
                 hide_index=True, width="stretch")
    evidence(repo, path, data, "recovery_source_records")
    source = st.selectbox("Daily source series", data["Source"].tolist())
    daily_path = SP+"source_history.csv"
    daily = repo.table(daily_path)
    for column in ["Scope", "Spotify ID", "Population"]:
        daily = daily.loc[daily[column].eq(data[column].iloc[0])]
    daily = daily.loc[daily["Window start"].eq(chosen[0]) & daily["Window end"].eq(chosen[1])]
    daily_listeners = daily.loc[daily["Metric"].eq("listeners")].copy()
    daily = daily.loc[daily["Metric"].eq(metric)]
    require_unique(daily, ["Date"])
    if source not in daily or daily.empty:
        st.info("No matching daily source chart was retained.")
    else:
        plot = daily[["Date", source]].copy()
        plot[source] = pd.to_numeric(plot[source], errors="coerce")
        if metric == "streams_per_listener":
            plot, undefined, unknown = source_ratio_plot_values(plot, daily_listeners, ["Date"], [source])
            st.caption(f"Daily ratios: {undefined} invalid or nonpositive denominator points and {unknown} without finite denominator evidence are unavailable and omitted. Reported values are retained in source records.")
        st.caption("Daily chart observations only. No sum of daily listeners or ratios is produced.")
        chart(px.line(plot, x="Date", y=source, labels={"Date":"UTC date", source:metric.replace('_',' ').capitalize()}),
              "recovery_source_daily")
        evidence(repo, daily_path, daily, "recovery_daily_records")


def render_recovery_evidence(repo):
    st.subheader("Recovery evidence and coverage")
    recovery_summary(repo)
    names = {
        "recovery_coverage.csv", "current_queue.csv", "remaining_limits.csv", "newer_snapshots.csv",
        "geography_comparison_daily.csv", "content_event_reporting.csv", "recovered_song_periods.csv",
        "source_stream_reconciliation.csv", "song_periods_complete_baseline.csv",
    }
    candidates = [path for path in repo.tables if path.startswith(SP) and path.split('/')[-1] in names]
    selected = st.selectbox("Recovery evidence table", candidates,
                            format_func=lambda path:path.split('/')[-1].replace('_',' ').removesuffix('.csv').capitalize())
    data = repo.table(selected)
    st.info("October 21 geography/catalog data and current content/event observations retain their own reporting basis. Unknown playlist bounds stay blank. Event dates are not reporting windows; asset or inventory observations are not sales.")
    for column in ["Reporting basis", "Dataset"]:
        if column in data:
            data = _select(data, column, column, "recovery_evidence_"+column)
    evidence(repo, selected, data, "recovery_evidence")
