"""Read-only Apple Music views over existing sealed library snapshots."""
from __future__ import annotations

from datetime import date, timedelta
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stats_app import dashboard_controls as controls
from stats_app.analysis_ui_common import chart, download, fmt
from stats_app.calculations import SERIES_FIELDS, chart_data, summarize_metric
from stats_app.source_context import SourceContext, render_context


VIEWS = {"Daily history": "daily", "Source period facts": "period", "Monthly source facts": "monthly"}
METRIC_LABELS = {"plays": "Apple Music plays", "daily_unique_listeners": "Daily unique listeners",
                 "average_daily_listeners": "Average daily listeners", "shazam_count": "Shazams",
                 "radio_spins": "Radio spins", "purchases": "Purchases"}


def apple_snapshot_catalog(repo):
    """Offer identified sealed Apple captures without reading unrelated archives."""
    catalog = repo.list_snapshots().copy()
    if catalog.empty:
        return catalog
    labels = catalog.get("stored_label", catalog.label).fillna("").astype(str)
    sealed = catalog.get("sealed", pd.Series(False, index=catalog.index)).isin([True, 1, "1"])
    return catalog.loc[sealed & labels.str.contains("apple", case=False, regex=False)].copy()


def daily_statistics(data, start, end):
    """Keep complete daily scope, partial counts and non-additive audiences apart."""
    selected = data.loc[data.period_start.ge(str(start)) & data.period_end.le(str(end))].copy()
    expected = (end - start).days + 1
    one_scope = bool(not selected.empty and all(selected[field].fillna("").astype(str).nunique() == 1
                                               for field in SERIES_FIELDS))
    point_dates = not selected.empty and selected.period_start.eq(selected.period_end).all()
    numeric = selected.status.eq("observed") & pd.to_numeric(selected.value, errors="coerce").notna()
    complete = bool(one_scope and point_dates and not selected.period_end.duplicated().any()
                    and len(selected) == expected and numeric.all())
    summary = summarize_metric(selected)
    return {"data": selected, "expected": expected, "reported": selected.period_end.nunique(),
            "observed": int(numeric.sum()), "complete": complete,
            "summary": summary, "mean_daily": float(pd.to_numeric(selected.value).mean()) if complete else None}


def matched_artist_activity(apple, spotify, start, end):
    """Compare separate complete UTC artist totals over explicitly shared dates."""
    if apple.empty or not apple.entity_type.eq("artist").all() or not apple.metric.eq("plays").all():
        return None
    if not apple.source_timezone.eq("UTC").all() or spotify.empty:
        return None
    low = max(start, date.fromisoformat(str(spotify.date.min())))
    high = min(end, date.fromisoformat(str(spotify.date.max())))
    if low > high:
        return None
    result = daily_statistics(apple, low, high)
    # The selected Apple series must be an unfiltered artist scope.
    dimensions = json.loads(apple.dimensions_json.iloc[0] or "{}")
    if dimensions.get("entity_scope") != "artist" or set(dimensions) - {"entity_scope", "precision"}:
        return None
    rows = spotify.loc[spotify.date.between(str(low), str(high))].copy()
    values = pd.to_numeric(rows.daily_streams, errors="coerce")
    if (not result["complete"] or len(rows) != (high - low).days + 1
            or rows.date.duplicated().any() or values.isna().any()
            or result["summary"].value is None):
        return None
    return {"start": low, "end": high, "apple_plays": result["summary"].value,
            "spotify_streams": float(values.sum()), "days": len(rows)}


def _scope_label(scope):
    dimensions = json.loads(scope.dimensions_json or "{}")
    detail = ", ".join(f"{key.replace('_', ' ')}: {value}" for key, value in dimensions.items())
    return f"{detail or 'Source scope'} · {scope.source_timezone or 'Unknown timezone'} · {scope.unit}"


def _records(repo, data):
    download(data, "apple_music_filtered.csv", "apple:filtered-csv")
    controls.own_keys("apple:evidence")
    panel = st.expander("Records, definitions and original sources", key="apple:evidence", on_change="rerun")
    if panel.open:
        with panel:
            st.dataframe(data, hide_index=True, width="stretch")
            selected = controls.selectbox("Apple observation", data.observation_id.astype(str).tolist(),
                                          key="apple:observation")
            provenance = repo.observation_provenance(selected)
            st.dataframe(provenance, hide_index=True, width="stretch")
            if not provenance.empty and "source_hash" in provenance:
                hashes = provenance.source_hash.drop_duplicates().tolist()
                chosen = controls.selectbox("Original Apple source", hashes, key="apple:original-source")
                st.download_button("Download unchanged Apple source", repo.original_source(chosen),
                                   "apple_music_source.csv", "text/csv", key="apple:source-download")


def render_apple_music(repo, analysis=None):
    """Browse daily, exact-period and monthly facts without importing or combining them."""
    st.subheader("Apple Music")
    catalog = apple_snapshot_catalog(repo)
    if catalog.empty:
        st.info("No sealed Apple Music snapshot is saved in this library.")
        return
    displays = {row.label: getattr(row, "display_label", row.label) for row in catalog.itertuples()}
    default_snapshot = next((i for i, value in enumerate(displays) if str(value).endswith("-daily")), 0)
    snapshot = controls.selectbox("Apple Music snapshot", list(displays), index=default_snapshot, format_func=displays.get,
                                  key="apple:snapshot")
    data = repo.observations(snapshot)
    data = data.loc[data.platform.eq("Apple Music")].copy()
    if data.empty:
        st.info("This saved snapshot contains no Apple Music observations.")
        return
    captures = sorted(value for value in data.captured_at.dropna().astype(str).unique() if value.strip()) if "captured_at" in data else []
    zones = sorted(data.source_timezone.dropna().astype(str).unique())
    render_context(SourceContext(source_id=snapshot, label=displays[snapshot],
        account=", ".join(data.account.drop_duplicates().astype(str)),
        reporting_start=str(data.period_start.min()), reporting_end=str(data.period_end.max()),
        timezone=zones[0] if len(zones) == 1 and zones[0] else "Varies by selected scope",
        captured_at=" – ".join(dict.fromkeys((captures[0], captures[-1]))) if captures else "Not supplied",
        availability="Available · sealed"))
    st.caption("Daily and aggregate captures may overlap. Select one source scope; do not add their totals together.")
    available = {name: grain for name, grain in VIEWS.items() if data.time_grain.eq(grain).any()}
    if not available:
        st.info("This source has no supported daily, period or monthly observations to display.")
        return
    view = controls.radio("Apple Music view", list(available), key="apple:view", horizontal=True)
    grain = available[view]
    data = data.loc[data.time_grain.eq(grain)]
    accounts = data.account.unique().tolist()
    account = controls.selectbox("Apple artist account", accounts, key="apple:account")
    data = data.loc[data.account.eq(account)]
    entities = data[["entity_type", "entity_id", "entity_name"]].drop_duplicates(["entity_type", "entity_id"])
    labels = {(row.entity_type, row.entity_id): f"{row.entity_name or row.entity_id} · {row.entity_type}"
              for row in entities.itertuples()}
    entities_ordered = sorted(labels, key=lambda identity: (identity[0] != "artist", labels[identity]))
    entity = controls.selectbox("Apple artist or content", entities_ordered, format_func=labels.get, key="apple:entity")
    data = data.loc[data.entity_type.eq(entity[0]) & data.entity_id.eq(entity[1])]
    metrics = sorted(data.metric.unique(), key=lambda metric: (metric != "plays", metric))
    metric = controls.selectbox("Apple metric", metrics, format_func=lambda value: METRIC_LABELS.get(value, value.replace("_", " ")),
                                key="apple:metric")
    data = data.loc[data.metric.eq(metric)]
    scope_fields = ["unit", "measurement_type", "source_timezone", "dimensions_json", "definition"]
    scopes = data[scope_fields].drop_duplicates().reset_index(drop=True)
    scope = controls.selectbox("Apple measurement scope", list(scopes.index),
                              format_func=lambda index: _scope_label(scopes.loc[index]), key="apple:scope")
    for column in scope_fields:
        data = data.loc[data[column].eq(scopes.loc[scope, column])]
    if grain == "daily":
        low, high = date.fromisoformat(data.period_start.min()), date.fromisoformat(data.period_end.max())
        preset = controls.selectbox("Apple reporting period", ["Latest 28 days", "Latest 7 days", "Latest 90 days", "All available", "Custom"],
                                    key="apple:preset")
        days = {"Latest 28 days": 28, "Latest 7 days": 7, "Latest 90 days": 90}.get(preset)
        start, end = max(low, high - timedelta(days=days - 1)) if days else low, high
        if preset == "Custom":
            dates = controls.date_range("Apple reporting dates", low, high, (start, end), key="apple:dates")
            if dates is None:
                return
            start, end = dates
        result = daily_statistics(data, start, end)
        selected = result["data"]
        st.caption(f"{start} – {end} inclusive · {data.source_timezone.iloc[0] or 'Unknown timezone'} · loaded through {high}")
        a, b, c = st.columns(3)
        if metric == "daily_unique_listeners":
            a.metric("Period-unique listeners", "Unavailable")
            b.metric("Mean daily unique listeners", fmt(result["mean_daily"], 1))
            st.caption("Daily unique listeners are not added into period-unique people. The mean requires every selected day.")
        else:
            a.metric("Apple plays" if metric == "plays" else METRIC_LABELS.get(metric, metric), fmt(result["summary"].value))
            b.metric("Aggregation status", "Complete" if result["complete"] else "Partial / unavailable")
        c.metric("Observed source days", f"{result['observed']:,} / {result['expected']:,}")
        if not result["complete"]:
            st.warning("The selected source does not supply one observed value for every requested day. Any sum is partial; missing values remain unavailable.")
        plotted = chart_data(selected)
        figure = go.Figure(go.Scatter(x=plotted.period_end, y=plotted.value, mode="lines", connectgaps=False,
                                     name=METRIC_LABELS.get(metric, metric), line={"color": "#EDD264"}))
        figure.update_layout(height=350, xaxis_title="Source reporting date", yaxis_title=METRIC_LABELS.get(metric, metric))
        chart(figure, "apple:daily-chart")
        if analysis is not None and metric == "plays" and entity[0] == "artist":
            matched = matched_artist_activity(data, analysis.table("spotify/cleaned/artist_daily.csv"), start, end)
            if matched:
                st.markdown("**Same dates on Spotify and Apple Music**")
                st.caption(f"{matched['start']} – {matched['end']} · {matched['days']} complete UTC days. Each service retains its own metric.")
                left, right = st.columns(2)
                left.metric("Apple plays · matched dates", fmt(matched["apple_plays"]))
                right.metric("Spotify streams · matched dates", fmt(matched["spotify_streams"]))
                st.caption("Separate platform activity totals; no combined audience or referral conversion is inferred.")
            else:
                st.caption("A complete matching UTC artist window on Spotify is unavailable for this selection.")
    else:
        periods = sorted(set(zip(data.period_start, data.period_end)))
        period = controls.selectbox("Exact Apple source period", periods, index=len(periods) - 1,
                                    format_func=lambda value: f"{value[0]} – {value[1]}", key="apple:source-period")
        selected = data.loc[data.period_start.eq(period[0]) & data.period_end.eq(period[1])].copy()
        summary = summarize_metric(selected)
        st.metric(METRIC_LABELS.get(metric, metric.replace("_", " ")), fmt(summary.value))
        st.caption(f"{period[0]} – {period[1]} · {grain} · {data.source_timezone.iloc[0] or 'Unknown timezone'}")
        st.caption("One retained source fact. Monthly and period facts remain separate from daily sums; rounding and source discrepancies are preserved.")
        if len(selected) != 1:
            st.warning("Multiple retained facts match this scope. No combined total is calculated.")
    st.caption(str(data.definition.iloc[0]))
    _records(repo, selected)
