"""Read-only YouTube collection views, preserving source grains and scope."""
from __future__ import annotations

import json
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stats_app.analysis_ui_common import chart, download

NORMALIZED = "normalized/"
RETENTION = "retention/"
NUMERIC_STATUSES = {"observed", "zero", "reported"}


def heading(repo):
    metadata = repo.metadata
    st.subheader("YouTube collection")
    st.caption(f"{metadata.get('channel_name', '[REDACTED] TV')} · "
               f"{metadata.get('channel_handle', '@redactedbandoh')} · "
               f"{metadata.get('channel_id', 'UCkSoRiC9Pz9hEbJOOTYaq_w')}")
    st.caption("Standard channel · channel_owned; retention uses channel_owned_selected_video. "
               "Artist-wide Official Artist Channel, Total Reach and Other Channels reporting was not exposed.")
    st.caption("Reporting dates are inclusive America/Los_Angeles calendar dates. Retrieval: October 23, 2026; "
               "download-file modification timestamps are proxies, separate from reporting dates.")
    st.info("Reports ending October 20 are newly retrieved historical data, not an original October 20 snapshot. "
            "Existing Spotify baseline classifications and saved analysis versions remain unchanged.")
    with st.expander("Reporting windows and stored coverage"):
        periods = metadata.get("reporting_periods", [])
        names = {"annual_current": "Current annual", "baseline365_historical": "Newly retrieved historical window",
                 "last28_current": "Audience, 28 days", "last90_current": "Audience, 90 days", "lifetime": "Lifetime channel"}
        if periods:
            st.markdown("| Report | Inclusive Pacific dates | Snapshot class |\n| --- | --- | --- |\n" + "\n".join(
                f"| {names.get(item['period_kind'], item['period_kind'])} | {item['reporting_start']} – {item['reporting_end']} | {item['snapshot_class']} |"
                for item in periods))
        counts = metadata.get("validation", {})
        if counts:
            st.caption(f"{counts['video_count']:,} video IDs · {counts['regular_video_count']:,} regular videos · "
                       f"{counts['shorts_count']:,} Shorts · {counts['annual_video_days']:,} annual video-days with separate views/engaged views · "
                       f"{counts['main_retention_points']:,} main retention points. These are collection counts, not statistical sample sizes.")


def _select(data, column, title, key, preferred=None, labels=None):
    """Select an exact source key, including a real blank when supplied."""
    if column not in data or data.empty:
        return data
    values = data[column].fillna("").astype(str)
    options = sorted(values.unique())
    index = options.index(preferred) if preferred in options else 0
    selected = st.selectbox(title, options, index=index, key=key,
                            format_func=lambda value: (labels or {}).get(value, value or "(not supplied)"))
    return data.loc[values.eq(selected)]


def _scope(data, key):
    """Keep overlapping windows, population, formats and filters distinct."""
    data = _select(data, "channel_id", "YouTube channel ID", key + "_channel")
    period_columns = [c for c in ("period_kind", "period", "reporting_start", "reporting_end") if c in data]
    if period_columns and not data.empty:
        values = data[period_columns].fillna("").astype(str).agg(tuple, axis=1)
        periods = sorted(values.unique())
        preferred = next((i for i, item in enumerate(periods) if "annual_current" in item), 0)
        chosen = st.selectbox("YouTube reporting period", periods, index=preferred,
                              format_func=lambda item: " · ".join(item), key=key + "_period")
        data = data.loc[values.map(lambda item: item == chosen)]
    for column, title, preferred in (
        ("snapshot_class", "YouTube snapshot class", "current_retrieval"),
        ("report_scope", "YouTube account scope", "channel_owned"),
        ("canonical_content_format", "YouTube canonical content format", "all"),
        ("report_content_format", "YouTube report content filter", "all"),
        ("filters_json", "YouTube additional filters", "{}"),
    ):
        data = _select(data, column, title, key + "_" + column, preferred)
    return data


def _records(repo, path, data, key):
    """Bound display size while retaining full filtered downloads and lineage."""
    st.caption(f"{len(data):,} retained records · {path}. Blank and unavailable values are not zero.")
    pages = max(1, math.ceil(len(data) / 250))
    page = int(st.number_input("Record page (250 rows)", min_value=1, max_value=pages,
                               value=1, step=1, key=key + "_page")) if pages > 1 else 1
    shown = data.iloc[(page - 1) * 250:page * 250]
    st.dataframe(shown, hide_index=True, width="stretch")
    download(data, path.rsplit("/", 1)[-1], key + "_filtered")
    with st.expander("Unchanged source and row provenance"):
        st.download_button("Download unchanged source table", repo.original_bytes(path),
                           path.rsplit("/", 1)[-1], "text/csv", key=key + "_original")
        st.caption("Filtered downloads retain source references, statuses and raw cells where supplied. "
                   "The unchanged table preserves the complete original CSV bytes.")
        if not shown.empty and st.checkbox("Show displayed rows' lineage", key=key + "_lineage"):
            st.dataframe(repo.row_provenance(path).loc[shown.index], hide_index=True, width="stretch")


def _video(data, repo, key):
    inventory = repo.table(NORMALIZED + "video_inventory.csv")
    labels = {str(row.video_id): f"{row.title} · {row.video_id}" for row in inventory.itertuples()}
    return _select(data, "video_id", "YouTube video", key + "_video", labels=labels)


def source_series(data, x, metric="value", status="value_status"):
    """Only source numeric statuses can appear as numbers; keep missing gaps."""
    result = data.sort_values(x).copy()
    values = pd.to_numeric(result[metric], errors="coerce")
    result[metric] = values.where(result[status].isin(NUMERIC_STATUSES))
    return result


def _daily_chart(data, metric="value", status="value_status", title="Source value", key="daily"):
    if data.empty:
        return
    if data.activity_date.duplicated().any():
        st.info("Several source observations remain for a date. Inspect their scopes below; no combined curve is drawn.")
        return
    shown = source_series(data, "activity_date", metric, status)
    fig = go.Figure(go.Scatter(x=shown.activity_date.tolist(), y=shown[metric].to_numpy(dtype=float, na_value=float("nan")),
                              mode="markers", name=title, connectgaps=False))
    fig.update_layout(xaxis_title="Pacific calendar date (America/Los_Angeles)", yaxis_title=title, height=340)
    chart(fig, key)
    st.caption("Each marker is a source observation. Omitted dates and unavailable values remain gaps; no daily sum or interpolation is applied.")


def _definitions(repo):
    with st.expander("Metric definitions and view-definition changes"):
        st.dataframe(repo.table(NORMALIZED + "metric_dictionary.csv"), hide_index=True, width="stretch")
        st.caption("Shorts view-definition change: March 31, 2025. All-format first-frame rollout announcement: "
                   "August 24, 2026; this channel's observed UI marks August 27, 2026. Both source dates are retained.")


def render_inventory(repo):
    path = NORMALIZED + "video_inventory.csv"
    data = repo.table(path)
    st.caption(f"{data.video_id.nunique()} stable video IDs in the collection. Classification follows native format filters; "
               "a live-performance upload is not automatically a livestream.")
    formats = st.multiselect("Inventory formats · empty means all", sorted(data.content_format.dropna().unique()), key="yt_inventory_formats")
    if formats:
        data = data.loc[data.content_format.isin(formats)]
    _records(repo, path, data, "yt_inventory")


def render_channel(repo):
    view = st.radio("YouTube channel data", ["Daily observations", "Source period summaries", "Wide daily records"], horizontal=True)
    filename = {"Daily observations": "channel_daily.csv", "Source period summaries": "channel_period.csv",
                "Wide daily records": "channel_daily_wide.csv"}[view]
    path = NORMALIZED + filename
    data = _scope(repo.table(path), "yt_channel_" + filename)
    if "metric" in data:
        data = _select(data, "metric", "YouTube metric", "yt_channel_metric_" + filename, "views")
        if not data.empty:
            unit = data.iloc[0].unit
            st.caption(f"Source unit: {unit}. Source channel aggregates may differ from attributed video or dimension totals.")
        if view == "Daily observations":
            _daily_chart(data, title=f"{data.iloc[0].metric} ({data.iloc[0].unit})" if not data.empty else "Source value", key="yt_channel_daily")
    st.warning("This original collection's annual multi-metric table has 243 reported dates. Watch time, average view duration, "
               "subscribers gained and subscribers lost have partial data in this frozen package. Its passkey blocker describes "
               "the original collection attempt. Select a dated daily supplement in the sidebar when available; missing dates here remain missing.")
    _records(repo, path, data, "yt_channel_" + filename)
    _definitions(repo)


def render_video_daily(repo):
    path = NORMALIZED + "video_daily_wide_365.csv"
    data = _video(_scope(repo.table(path), "yt_video_daily"), repo, "yt_video_daily")
    metric = st.selectbox("YouTube daily video metric", ["views", "engaged_views"])
    st.caption("Views and engaged views are separate source metrics. Native prepublication chart zero padding is retained; "
               "it does not establish publication or activity before release.")
    _daily_chart(data, metric, metric + "_status", metric + " (count)", "yt_video_daily_chart")
    _records(repo, path, data, "yt_video_daily")
    with st.expander("Canonical daily metric detail and quality notes"):
        if st.checkbox("Show canonical daily detail", key="yt_daily_detail") and not data.empty:
            detail_path = NORMALIZED + "video_daily.csv"
            detail = repo.table(detail_path)
            for field in ("channel_id", "video_id", "snapshot_class", "period_kind", "reporting_start", "reporting_end",
                          "report_scope", "canonical_content_format", "filters_json"):
                detail = detail.loc[detail[field].eq(data.iloc[0][field])]
            detail = detail.loc[detail.metric.eq(metric)]
            _records(repo, detail_path, detail, "yt_video_daily_detail")
    _definitions(repo)


def render_periods(repo):
    path = NORMALIZED + "video_period.csv"
    data = _video(_scope(repo.table(path), "yt_video_period"), repo, "yt_video_period")
    data = _select(data, "metric", "YouTube metric", "yt_video_period_metric", "views")
    st.caption("Exact source period summaries. Unique/returning viewers, durations, average percentage viewed and CTR "
               "are nonadditive. Average percentage viewed can exceed 100%.")
    _records(repo, path, data, "yt_video_period")
    _definitions(repo)


def render_dimensions(repo):
    view = st.radio("YouTube dimension data", ["Period summaries", "Daily observations"], horizontal=True)
    path = NORMALIZED + ("dimension_period.csv" if view == "Period summaries" else "dimension_daily.csv")
    data = _scope(repo.table(path), "yt_dimensions_" + view)
    data = _select(data, "report_breakdown", "YouTube breakdown", "yt_breakdown_" + view)
    data = _select(data, "metric", "YouTube metric", "yt_dimension_metric_" + view, "views")
    if view == "Daily observations":
        data = _select(data, "dimension_json", "YouTube dimension member", "yt_dimension_member")
        _daily_chart(data, title=f"{data.iloc[0].metric} ({data.iloc[0].unit})" if not data.empty else "Source value", key="yt_dimension_daily")
    st.info("Dimensions and filtered scopes can overlap or omit withheld detail. Preserve source channel totals. "
            "Short-window demographics are suppressed; raw New viewers zeros documented as unavailable remain unavailable.")
    _records(repo, path, data, "yt_dimensions_" + view)


def retention_figure(data):
    """One exact video/member/segment/metric curve, with no invented endpoint."""
    shown = source_series(data, "video_position_percent")
    unit = str(shown.iloc[0].unit) if not shown.empty else "source unit"
    figure = go.Figure(go.Scatter(x=pd.to_numeric(shown.video_position_percent).tolist(),
                                 y=shown.value.to_numpy(dtype=float, na_value=float("nan")), mode="lines+markers",
                                 name=str(shown.iloc[0].metric) if not shown.empty else "Retention", connectgaps=False))
    figure.update_layout(xaxis_title="Elapsed video (%) · exported bins 0–99", xaxis=dict(range=[0, 99]),
                         yaxis_title=f"Source value ({unit})", height=350)
    return figure


def render_retention(repo):
    mode = st.radio("YouTube retention source", ["Native retention curves", "Manual UI summaries"], horizontal=True)
    st.caption("Since-uploaded lifetime periods belong to each video. Upload and public publication dates can differ. "
               "Retention positions, videos and overlapping segments must not be summed.")
    if mode == "Manual UI summaries":
        path = RETENTION + "retention_ui_summary.csv"
        data = _video(repo.table(path), repo, "yt_manual_retention")
        st.warning("Manual UI transcription: rounded average duration, average percentage viewed and Shorts Stayed-to-watch "
                   "summaries are separate from native CSV curves and annual export summaries. Exact UI reading times were not retained.")
        _records(repo, path, data, "yt_manual_retention")
        return
    path = RETENTION + "retention_observations.csv"
    data = _video(repo.table(path), repo, "yt_retention")
    data = _scope(data, "yt_retention")
    data = _select(data, "report_id", "YouTube retention report", "yt_retention_report")
    source_path = RETENTION + "retention_source_files.csv"
    sources = repo.table(source_path)
    if data.empty:
        st.info("No native retention rows are available for this selection.")
        return
    sources = sources.loc[sources.report_id.eq(data.iloc[0].report_id)]
    selected_sources = _select(sources, "member_name", "YouTube retention member", "yt_retention_member", "All.csv")
    member = selected_sources.iloc[0].member_name
    data = data.loc[data.member_name.eq(member)]
    if data.empty:
        st.info("This native member is header-only: unavailable, not zero. No curve or suppression cause is inferred.")
        _records(repo, source_path, selected_sources, "yt_retention_empty_member")
        return
    for column, title in (("segment_dimension", "YouTube segment dimension"), ("segment_value", "YouTube segment value"), ("metric", "YouTube retention metric")):
        data = _select(data, column, title, "yt_retention_" + column, "absolute_audience_retention" if column == "metric" else None)
    st.caption("Elapsed-video percentages are not calendar dates. The export has no 100% endpoint. "
               "Absolute retention may exceed 100%; relative comparisons may be negative. Values are not clamped.")
    if data.video_position_percent.duplicated().any():
        st.info("Multiple observations remain at a position. Inspect the source keys; no combined curve is drawn.")
    else:
        chart(retention_figure(data), "yt_retention_chart")
    _records(repo, path, data, "yt_retention_curve")


def render_mapping(repo):
    path = NORMALIZED + "video_song_mapping.csv"
    data = repo.table(path)
    st.info("Multiple videos may relate to one song. Title evidence does not prove identical recordings. "
            "Uncertain song relationships and unverified Spotify recording IDs remain unresolved; no conversion or causal claim is made.")
    status = st.multiselect("Song mapping status · empty means all", sorted(data.song_mapping_status.unique()))
    if status:
        data = data.loc[data.song_mapping_status.isin(status)]
    _records(repo, path, data, "yt_mapping")


def render_coverage(repo, key="yt_coverage"):
    st.subheader("YouTube coverage and limitations")
    st.warning("At the time this original package was collected, four full daily exports were blocked by Google passkey verification. "
               "This frozen annual multi-metric table retains 243 reported dates and partial metric coverage. A separately dated "
               "daily supplement, when registered, is available in the sidebar. No omitted day in this package is zero-filled.")
    paths = {"Collection statuses": NORMALIZED + "collection_status.csv", "Daily coverage": NORMALIZED + "daily_coverage.csv",
             "Core report index": NORMALIZED + "collection_index.csv", "Retention report index": RETENTION + "retention_collection_index.csv",
             "Retention member availability": RETENTION + "retention_source_files.csv",
             "Core validation": NORMALIZED + "validation_checks.csv", "Retention validation": RETENTION + "retention_validation_checks.csv"}
    name = st.selectbox("YouTube coverage table", list(paths), key=key + "_table")
    path = paths[name]
    data = repo.table(path)
    if name == "Daily coverage":
        data = _scope(data, key + "_daily")
        data = _select(data, "grain", "YouTube coverage grain", key + "_grain", "channel_daily")
        data = _select(data, "metric", "YouTube metric", key + "_metric", "watch_time_hours")
    elif "status" in data:
        selected = st.multiselect("YouTube availability statuses · empty means all", sorted(data.status.dropna().unique()), key=key + "_statuses")
        if selected:
            data = data.loc[data.status.isin(selected)]
    _records(repo, path, data, key + "_records")


def render_sources(repo, key="yt_sources"):
    st.subheader("YouTube sources and provenance")
    catalog = repo.file_catalog()
    st.caption("Original native ZIPs, exact CSV members, manifests, dictionaries and validation evidence are retained. "
               "The raw observations table is provenance evidence; use canonical domain views for inspection, never concatenate it into totals.")
    kind = st.selectbox("YouTube source group", ["Dictionaries and collection evidence", "Normalized tables", "Original native exports", "All retained files"], key=key + "_group")
    paths = catalog.path.astype(str)
    if kind == "Dictionaries and collection evidence":
        shown = catalog.loc[paths.str.contains("dictionary|manifest|validation|collection_index|collection_status|source_files|README|delivery_links|daily_coverage", regex=True)]
    elif kind == "Normalized tables":
        shown = catalog.loc[paths.str.startswith("normalized/") | paths.isin([RETENTION + "retention_observations.csv", RETENTION + "retention_ui_summary.csv"])]
    elif kind == "Original native exports":
        shown = catalog.loc[paths.str.startswith(("originals/", "retention/originals/"))]
    else:
        shown = catalog
    path = st.selectbox("YouTube retained source", shown.path.tolist(), key=key + "_file")
    st.dataframe(shown.loc[shown.path.eq(path)], hide_index=True, width="stretch")
    content = repo.original_bytes(path)
    st.download_button("Download unchanged retained file", content, path.rsplit("/", 1)[-1], key=key + "_download")
    if path.endswith((".txt", ".md")):
        st.text(content.decode("utf-8-sig"))
    elif path.endswith(".json"):
        st.json(json.loads(content), expanded=False)
    elif path in repo.tables and st.checkbox("Inspect retained CSV records", key=key + "_inspect"):
        _records(repo, path, repo.table(path), key + "_csv")
    st.download_button("Download unchanged complete YouTube package", repo.original_zip(),
                       "The_Stats_YouTube_Collection_2026-10-23.zip", "application/zip", key=key + "_package")


def render_youtube_collection(repo, *, collection_keys=()):
    if repo.metadata.get("collection_kind") == "daily_supplement":
        from stats_app.youtube_daily_ui import render_daily_supplement
        render_daily_supplement(repo, collection_keys)
        return
    heading(repo)
    views = {"Video inventory": render_inventory, "Channel data": render_channel, "Video daily data": render_video_daily,
             "Video period summaries": render_periods, "Discovery & audience": render_dimensions, "Retention": render_retention,
             "Song mappings": render_mapping, "Coverage & limitations": render_coverage, "Sources & provenance": render_sources}
    selected = st.selectbox("YouTube view", list(views))
    views[selected](repo)


def render_collection_entry(repo, kind, key):
    """Expose the separate collection in existing provenance and quality pages."""
    if repo.metadata.get("collection_kind") == "daily_supplement":
        from stats_app.youtube_daily_ui import render_daily_entry
        render_daily_entry(repo, kind, key)
        return
    with st.expander("YouTube collection · October 23, 2026"):
        st.caption("Separate YouTube collection · Pacific reporting dates · historical October 20 endpoint newly retrieved. "
                   "Open YouTube collection in Explore for scoped channel/video data and native retention.")
        if st.checkbox("Inspect YouTube " + kind, key=key + "_open"):
            (render_sources if kind == "sources" else render_coverage)(repo, key=key)
