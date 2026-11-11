"""Scoped exploration of retained Linktree evidence; no listening attribution."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import mimetypes
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stats_app import dashboard_controls as controls
from stats_app.analysis_ui_common import chart


LABELS = {"total_views": "Views", "total_clicks": "Clicks", "new_contacts": "New contacts",
          "contacts": "Contacts", "reported_click_rate_percent": "Reported click rate",
          "unique_views": "Daily unique views", "unique_clicks": "Daily unique clicks"}
NUMERIC_STATUSES = {"observed", "observed_zero", "derived"}
SECTIONS = ("Overview", "Daily activity", "Links & destinations", "Source details")


def numeric_values(data):
    """Finite literal values only; an unavailable number remains unavailable."""
    if "value" not in data:
        return pd.Series(float("nan"), index=data.index, dtype=float)
    result = pd.to_numeric(data["value"], errors="coerce").astype(float)
    result = result.where(result.abs().lt(float("inf")))
    if "availability_status" in data:
        result = result.where(data["availability_status"].isin(NUMERIC_STATUSES))
    return result


def inspection_csv(data):
    """Spreadsheet-safe inspection export; originals are separately downloadable."""
    def safe(value):
        if not isinstance(value, str) or not value.lstrip().startswith(("=", "+", "-", "@")):
            return value
        if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value):
            try:
                if Decimal(value).is_finite():
                    return value
            except InvalidOperation:
                pass
        return "'" + value
    return data.map(safe).to_csv(index=False).encode("utf-8-sig")


def _table(repo, dataset, *, key, columns=None):
    data = repo.table(dataset)
    query = controls.text_input("Search these records", key="linktree:" + key + ":search")
    shown = data
    if query.strip():
        mask = data.fillna("").astype(str).apply(lambda column: column.str.contains(query, case=False, regex=False)).any(axis=1)
        shown = data.loc[mask]
    st.caption(f"{len(shown):,} of {len(data):,} retained records · {dataset.replace('_', ' ')} · one source table")
    if shown.empty:
        st.info("No records match this search. Clear the search to restore this table.")
        return
    preferred = columns or ["title", "period_start", "period_end", "metric", "original_value_label", "value",
                            "availability_status", "dimension_value", "service_label", "destination_url"]
    visible = [column for column in preferred if column in shown]
    st.dataframe(shown[visible] if visible else shown, hide_index=True, width="stretch")
    st.download_button("Download these records · inspection CSV", inspection_csv(shown),
                       f"linktree_{dataset}_filtered.csv", "text/csv", key="linktree:csv:" + key)
    if st.toggle("Inspect a retained row", key="linktree:inspect:" + key):
        def label(index):
            row = shown.loc[index]
            parts = [str(row.get(field, "")) for field in ("title", "service_label", "metric", "period_start", "dimension_value")]
            return f"Record {index + 2} · " + " · ".join(value for value in parts if value)
        selected = controls.selectbox("Retained row", shown.index.tolist(), format_func=label, key="linktree:row:" + key)
        st.json(shown.loc[selected].to_dict(), expanded=False)
        st.dataframe(repo.row_provenance(dataset).iloc[[selected]], hide_index=True, width="stretch")


def _overview(repo):
    data = repo.table("period_summaries")
    choices = data.dimension_value.drop_duplicates().tolist()
    default = choices.index("last_28_days") if "last_28_days" in choices else 0
    selected = controls.selectbox("Source-reported summary window", choices, index=default,
                                  format_func=lambda value: value.replace("_", " "), key="linktree:summary")
    selected_rows = data.loc[data.dimension_value.eq(selected)]
    if selected_rows.empty:
        st.info("No retained summary is available for this selection.")
        return
    first = selected_rows.iloc[0]
    bounds = f"{first.period_start} – {first.period_end}" if first.period_start else "Lifetime boundaries unavailable"
    st.caption(bounds + " · source calendar · reporting timezone unknown · no timezone alignment to Spotify")
    incomplete = repo.metadata.get("coverage", {}).get("current_day_incomplete")
    if incomplete and any(selected_rows.period_start.le(incomplete) & selected_rows.period_end.ge(incomplete)):
        st.warning(f"This source window includes the incomplete collection day, {incomplete}. Reporting delay is unknown.")
    order = ["total_views", "total_clicks", "reported_click_rate_percent", "new_contacts", "contacts"]
    wanted = [metric for metric in order if metric in set(selected_rows.metric)][:4]
    if wanted:
        cards = st.columns(len(wanted))
        for card, metric in zip(cards, wanted):
            rows = selected_rows.loc[selected_rows.metric.eq(metric)]
            value = "Unavailable"
            if len(rows) == 1:
                row = rows.iloc[0]
                number = numeric_values(rows).iloc[0]
                if pd.notna(number):
                    value = row.get("original_value_label") or f"{number:g}"
                    if row.get("unit") == "percent" and "%" not in value:
                        value += "%"
                elif row.get("original_value_label"):
                    value = row.original_value_label + " · source display"
            card.metric(LABELS.get(metric, metric.replace("_", " ")), value)
    st.caption("Clicks and views are separate Linktree activity. Reported rates above 100% remain as displayed. Parent music-preview clicks, outbound service referrals and confirmed streams are separate stages.")
    if st.toggle("Inspect source summary rows", key="linktree:summary:rows"):
        st.dataframe(selected_rows[[field for field in ("metric", "value", "original_value_label", "availability_status", "precision", "aggregation_caution")
                                   if field in selected_rows]], hide_index=True, width="stretch")
    if st.toggle("Read source limitations and discrepancies", key="linktree:limitations"):
        st.write(repo.original_bytes("VALIDATION_AND_GAPS.md").decode("utf-8-sig"))


def _daily(repo):
    dataset = controls.selectbox("Daily evidence", ["activity_daily", "activity_daily_reported_rates", "traffic_sources_daily"],
                                 format_func=lambda value: value.replace("_", " "), key="linktree:daily:dataset")
    data = repo.table(dataset)
    metrics = data.metric.drop_duplicates().tolist()
    metric = controls.selectbox("Metric", metrics, format_func=lambda value: LABELS.get(value, value.replace("_", " ")),
                                key="linktree:daily:metric:" + dataset)
    data = data.loc[data.metric.eq(metric)].copy()
    if "dimension_value" in data and data.dimension_value.ne("").any():
        values = data.loc[data.dimension_value.ne(""), "dimension_value"].drop_duplicates().tolist()
        chosen = controls.selectbox("Incoming referrer · partial source list", values, key="linktree:daily:source")
        data = data.loc[data.dimension_value.eq(chosen)]
    dates = pd.to_datetime(data.period_start, errors="coerce")
    if dates.notna().any():
        low, high = dates.min().date(), dates.max().date()
        bounds = controls.date_range("Linktree source-calendar dates · timezone unknown", low, high, (low, high),
                                     key="linktree:daily:dates:" + dataset)
        if bounds is None:
            return
        start, end = bounds
        data = data.loc[data.period_start.between(start.isoformat(), end.isoformat())].copy()
        incomplete = repo.metadata.get("coverage", {}).get("current_day_incomplete")
        if incomplete and start.isoformat() <= incomplete <= end.isoformat():
            st.warning(f"{incomplete} is incomplete; it remains visible as a partial source day.")
    data["display_value"] = numeric_values(data)
    st.caption("Each point is one retained source observation. Missing values stay gaps; daily unique counts are not added into a period audience. Source rates are not averaged.")
    if not data.empty:
        fig = go.Figure(go.Scatter(x=data.period_start, y=data.display_value, mode="lines+markers", connectgaps=False,
                                  name=LABELS.get(metric, metric.replace("_", " ")),
                                  customdata=data[["availability_status"]],
                                  hovertemplate="%{x}<br>%{y}<br>%{customdata[0]}<extra></extra>"))
        fig.update_layout(xaxis_title="Source calendar date · unknown timezone", yaxis_title=metric.replace("_", " "))
        chart(fig, key="linktree:daily:chart")
        st.dataframe(data[["period_start", "metric", "value", "availability_status", "date_completeness"]], hide_index=True, width="stretch")
        st.download_button("Download displayed daily records", inspection_csv(data.drop(columns="display_value")),
                           "linktree_daily_filtered.csv", "text/csv", key="linktree:daily:csv")


def render_linktree(repo):
    if repo is None:
        st.info("No verified Linktree collection is installed. Add a reviewed collection through the documented local importer.")
        return
    metadata = repo.metadata
    controls.own_keys("linktree:summary:rows", "linktree:limitations", "linktree:originals")
    identity = metadata["identity"]
    st.subheader("Link activity")
    st.caption(f"{identity.get('profile_display_name', identity['account'])} · {identity.get('public_url', '')} · collected {metadata.get('collected_at', 'unknown')}")
    st.info("Linktree source timezone is unknown. Its views and clicks do not establish Spotify listeners, confirmed streams or campaign conversion.")
    section = controls.radio("Explore Linktree", SECTIONS, key="linktree:section", horizontal=True, label_visibility="collapsed")
    if section == "Overview":
        _overview(repo)
    elif section == "Daily activity":
        _daily(repo)
    elif section == "Links & destinations":
        dataset = controls.selectbox("Evidence table", ["link_inventory", "individual_link_metrics", "music_service_destinations", "music_service_metrics", "link_traffic_sources"],
                                     key="linktree:links:dataset", format_func=lambda value: value.replace("_", " "))
        st.caption("Configuration describes the collection-time destination and status. Inventory badges have unknown reporting bounds. Unavailable service-click values stay unavailable; parent interactions do not supply them.")
        _table(repo, dataset, key=dataset)
    else:
        dataset_ids = [item["dataset_id"] for item in repo.datasets.to_dict("records")]
        dataset = controls.selectbox("Retained table", dataset_ids, key="linktree:evidence:table", format_func=lambda value: value.replace("_", " "))
        _table(repo, dataset, key="evidence:" + dataset)
        if st.toggle("Show collection metadata and original downloads", key="linktree:originals"):
            st.json(metadata, expanded=False)
            paths = repo.sources().path.tolist()
            path = controls.selectbox("Original retained asset", paths, key="linktree:original:path")
            raw = repo.original_bytes(path)
            st.caption("Exact source bytes, verified against the sealed inventory before download.")
            st.download_button("Download unchanged source", raw, path.rsplit("/", 1)[-1],
                               mimetypes.guess_type(path)[0] or "application/octet-stream", key="linktree:original:download")
