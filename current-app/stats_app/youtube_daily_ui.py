"""Read-only views for a separately retrieved native YouTube daily supplement."""
from __future__ import annotations

import json

import streamlit as st
from stats_app import dashboard_controls as controls

from stats_app.youtube_daily_supplement import DAILY_PATH, METRICS
from stats_app.youtube_repository import SOURCE_URL as PARENT_SOURCE_URL
from stats_app.youtube_ui import _daily_chart, _daily_range, _records, _scope, _select, daily_coverage, _own_youtube_keys


METRIC_LABELS = {
    "watch_time_hours": "Watch time (hours)",
    "average_view_duration_seconds": "Average view duration (seconds)",
    "subscribers_gained": "Subscribers gained",
    "subscribers_lost": "Subscribers lost",
}


def _open_parent(key):
    # Navigation only: the parent collection's records are never loaded here.
    # The application selector restores this persistent value on each render.
    st.session_state["selection:youtube_collection_selector"] = key
    # Retain compatibility with direct renderers using a plain Streamlit widget.
    st.session_state["youtube_collection_selector"] = key
    controls.navigate("YouTube collection")


def heading(repo, collection_keys=()):
    metadata = repo.metadata
    st.subheader("YouTube annual daily supplement")
    st.caption(f"Collection: {metadata['label']} · {metadata['collection_key']}")
    st.caption(f"{metadata['channel_name']} · {metadata['channel_handle']} · {metadata['channel_id']}")
    period = metadata["reporting_periods"][0]
    st.caption(f"{period['reporting_start']} – {period['reporting_end']} inclusive · America/Los_Angeles calendar dates · "
               "standard channel · channel_owned · all content formats · no additional filters")
    st.caption(f"Retrieved {metadata['retrieval_date']} · newly_retrieved_supplement. "
               "Each report retains its own UTC retrieval timestamp and explicit timestamp basis.")
    st.info("This separate supplement preserves four native daily total series. Its reporting period overlaps the parent "
            "collection; the two collections must not be added together. The parent collection, Spotify baseline metadata "
            "and saved analysis versions remain unchanged.")
    parent_key = metadata["parent_collection_key"]
    st.markdown(f"Parent collection: **{parent_key}** · [original collected package]({PARENT_SOURCE_URL})")
    if parent_key in collection_keys:
        st.button("Open parent YouTube collection", on_click=_open_parent, args=(parent_key,), key="yt_daily_open_parent")
    with st.expander("Collection lineage and package hashes"):
        st.json({field: metadata[field] for field in ("collection_key", "collection_kind", "parent_collection_key",
                                                     "parent_zip_sha256", "zip_sha256", "retrieval_date", "baseline_status")}, expanded=True)
        st.caption("The parent package hash pins the original collection. This supplement has its own package and stable row keys.")


def render_daily_metrics(repo):
    data = _scope(repo.table(DAILY_PATH), "yt_supplement_daily")
    data = _select(data, "metric", "Supplement metric", "yt_supplement_metric", "watch_time_hours", METRIC_LABELS)
    if data.empty:
        st.info("No source rows are available for this selection.")
        return
    metric = str(data.iloc[0].metric)
    report_id = data.iloc[0].report_id
    data, selected_dates = _daily_range(data, "yt_supplement_daily")
    if selected_dates:
        coverage = daily_coverage(data, *selected_dates)
        left, middle, right = st.columns(3)
        left.metric("Native reported dates", f"{coverage['reported']:,} / {coverage['expected']:,}")
        middle.metric("Dates with numeric values", f"{coverage['numeric']:,} / {coverage['expected']:,}")
        right.metric("Omitted calendar dates", f"{coverage['missing']:,}")
        st.caption("Coverage above applies to the selected activity dates. Full-report coverage remains in Coverage & validation. "
                   "An exported calendar row can still contain an unavailable, suppressed or not-applicable value.")
    if data.empty:
        st.info("No source observations fall within this daily selection.")
        return
    st.caption(f"{data.iloc[0].report_id} · source unit: {data.iloc[0].unit} · source member: {data.iloc[0].source_file}")
    st.caption("Watch time stays in hours. Average view duration is parsed from native h:mm:ss into seconds with its raw text retained. "
               "Average durations are neither summed nor averaged across days. No period total is calculated here.")
    _daily_chart(data, title=METRIC_LABELS.get(metric, metric), key="yt_supplement_daily_chart")
    _records(repo, DAILY_PATH, data, "yt_supplement_daily_records")
    panel = st.expander("Selected report and retrieval evidence", key="yt_supplement_report_evidence", on_change="rerun")
    if panel.open:
        with panel:
            index = repo.table("normalized/collection_index.csv")
            st.dataframe(index.loc[index.report_id.eq(report_id)], hide_index=True, width="stretch")


def render_daily_coverage(repo, key="yt_supplement_coverage"):
    st.subheader("YouTube supplement coverage")
    st.info("Complete date coverage means the native export supplied all 365 calendar rows. Numeric availability is checked "
            "separately. Missing, suppressed, unavailable, not applicable and explicit zero remain distinct.")
    paths = {"Daily coverage": "normalized/daily_coverage.csv", "Native report index": "normalized/collection_index.csv",
             "Validation checks": "normalized/validation_checks.csv", "Native member inventory": "normalized/source_files.csv",
             "Metric dictionary": "normalized/metric_dictionary.csv"}
    choice = st.selectbox("Supplement coverage table", list(paths), key=key + "_table")
    path = paths[choice]
    data = repo.table(path)
    if "metric" in data:
        metrics = st.multiselect("Supplement coverage metrics · empty means all", list(METRICS),
                                format_func=METRIC_LABELS.get, key=key + "_metrics")
        if metrics:
            data = data.loc[data.metric.isin(metrics)]
    _records(repo, path, data, key + "_records")


def render_daily_sources(repo, key="yt_supplement_sources"):
    st.subheader("YouTube supplement sources and provenance")
    metadata = repo.metadata
    st.caption(f"Supplement {metadata['collection_key']} · parent {metadata['parent_collection_key']}. "
               "Source rows retain native ZIP/member hashes, CSV record numbers, retrieval timestamps and UI evidence paths.")
    st.markdown(f"[Parent collection original package]({PARENT_SOURCE_URL}) · parent SHA-256: `{metadata['parent_zip_sha256']}`")
    catalog = repo.file_catalog()
    groups = ["Native exports and members", "Collection and UI evidence", "Normalized tables", "All retained files"]
    group = st.selectbox("Supplement source group", groups, key=key + "_group")
    paths = catalog.path.astype(str)
    if group == groups[0]:
        catalog = catalog.loc[paths.str.startswith(("originals/", "extracted/"))]
    elif group == groups[1]:
        catalog = catalog.loc[~paths.str.startswith(("originals/", "extracted/", "normalized/"))]
    elif group == groups[2]:
        catalog = catalog.loc[paths.str.startswith("normalized/")]
    path = st.selectbox("Supplement retained source", catalog.path.tolist(), key=key + "_file")
    st.dataframe(catalog.loc[catalog.path.eq(path)], hide_index=True, width="stretch")
    panel = st.expander("Open original supplement and package downloads", key=key + "_downloads", on_change="rerun")
    if panel.open:
        with panel:
            raw = repo.original_bytes(path)
            st.download_button("Download unchanged supplement source", raw, path.rsplit("/", 1)[-1], key=key + "_file_download")
            if path.endswith(".json"):
                st.json(json.loads(raw), expanded=False)
            elif path.endswith((".txt", ".md")):
                st.text(raw.decode("utf-8-sig"))
            elif path in repo.tables and st.checkbox("Inspect supplement CSV records", key=key + "_inspect"):
                _records(repo, path, repo.table(path), key + "_table_records")
            st.download_button("Download unchanged daily supplement package", repo.original_zip(), metadata["zip_filename"],
                               "application/zip", key=key + "_package_download")


def render_daily_supplement(repo, collection_keys=()):
    heading(repo, collection_keys)
    views = {"Daily metrics": render_daily_metrics, "Coverage & validation": render_daily_coverage,
             "Sources & provenance": render_daily_sources}
    selected = st.selectbox("YouTube supplement view", list(views), key="yt_supplement_view")
    views[selected](repo)
    _own_youtube_keys()


def render_daily_entry(repo, kind, key):
    with st.expander(f"YouTube daily supplement · {repo.metadata['retrieval_date']}"):
        st.caption(f"Separate supplement {repo.metadata['collection_key']} · parent {repo.metadata['parent_collection_key']} · "
                   "365 native dates per metric; numeric availability is separate. Open YouTube collection in Explore to inspect daily values.")
        if st.checkbox("Inspect YouTube supplement " + kind, key=key + "_open"):
            (render_daily_sources if kind == "sources" else render_daily_coverage)(repo, key=key)
