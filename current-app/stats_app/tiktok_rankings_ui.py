"""Native, source-qualified strongest-post rankings for the TikTok page."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stats_app import dashboard_controls as controls
from stats_app.analysis_ui_common import chart
from stats_app.linktree_ui import inspection_csv
from stats_app.tiktok_rankings import (METRIC_LABELS, SNAPSHOT_METRICS, prepare_native_rankings,
                                      prepare_snapshot_rankings, ranking_period, select_native_rankings)


def _table(repo, name):
    datasets = repo.datasets
    if datasets.empty or "dataset_id" not in datasets or name not in set(datasets.dataset_id):
        return pd.DataFrame()
    return repo.table(name)


def _plot(rows, metric_label, key):
    plotted = rows.loc[rows.plot_value.notna()].copy()
    if plotted.empty:
        st.caption("No numeric values are available for a chart. Missing values remain unavailable.")
        return
    labels = [f"{row.get('rank', i + 1)}. {(str(row.caption) or 'Caption unavailable')[:65]}" for i, row in plotted.reset_index(drop=True).iterrows()]
    fig = go.Figure(go.Bar(x=plotted.plot_value, y=labels, orientation="h", text=plotted.ranking_value_raw,
                          textposition="outside", cliponaxis=False,
                          customdata=plotted[["ranking_value_raw", "value_precision", "caption"]].to_numpy(),
                          hovertemplate="%{customdata[2]}<br>%{customdata[0]} · %{customdata[1]}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_xaxes(title=metric_label, rangemode="tozero")
    chart(fig, key=key, height=max(280, len(plotted) * 44 + 90))
    if plotted.value_precision.eq("rounded").any():
        st.caption("Bar lengths use approximate positions for native K/M labels. Labels and downloads retain the reported precision; equal rounded labels do not establish exact ties.")


def _display(rows, *, metric_label, native):
    columns = {"rank": "Native rank", "caption": "Post caption", "ranking_value_raw": metric_label,
               "all_views_raw": "All views · cumulative", "value_precision": "Value precision",
               "posted_on_raw": "Published · native label", "public_url": "Open post"}
    if not native:
        columns = {"caption": "Post caption", "ranking_value_raw": metric_label + " · cumulative",
                   "value_precision": "Value precision", "views_raw": "Views · cumulative",
                   "saves_raw": "Saves · cumulative", "posted_date_raw": "Published · native label",
                   "captured_at": "Captured at (UTC)", "public_url": "Open post"}
    display = rows[[c for c in columns if c in rows]].rename(columns=columns)
    st.dataframe(display, hide_index=True, width="stretch", height=min(500, 40 * (len(display) + 1)),
                 column_config={"Open post": st.column_config.LinkColumn("Open post", display_text="Open TikTok")})


def render_tiktok_rankings(repo):
    st.subheader("Strongest posts")
    st.caption("Rank by the outcome you want: followers, views, new viewers or likes. TikTok for Artists remains pending.")
    mode = controls.radio("Ranking scope", ["Reporting-window rankings", "Cumulative post snapshots"],
                          key="tiktok:strongest:mode", horizontal=True)
    inventory = _table(repo, "post_inventory")
    native = mode == "Reporting-window rankings"
    if native:
        all_rows = prepare_native_rankings(_table(repo, "content_rankings"), inventory)
        if all_rows.empty:
            st.info(all_rows.attrs.get("unavailable_reason", "No native ranking rows are retained."))
            return
        windows = sorted({int(v) for v in all_rows.window_days_numeric.dropna() if v in (7, 28, 60, 365)})
        if not windows:
            st.info("No supported native reporting windows are available.")
            return
        window = controls.selectbox("Native reporting window", windows, index=windows.index(28) if 28 in windows else 0,
                                    format_func=lambda n: f"{n} days", key="tiktok:strongest:window")
        available = set(all_rows.loc[all_rows.window_days_numeric.eq(window), "ranking_metric"])
        metrics = [key for key in METRIC_LABELS if key in available]
        if not metrics:
            st.info("No supported ranking metric is retained for this window.")
            return
        metric = controls.selectbox("Rank posts by", metrics, format_func=METRIC_LABELS.get, key="tiktok:strongest:metric")
        scope = all_rows.loc[all_rows.window_days_numeric.eq(window) & all_rows.ranking_metric.eq(metric)]
        sources = scope.source_file.drop_duplicates().tolist()
        source = controls.selectbox("Ranking capture", sources, format_func=lambda p: p.rsplit("/", 1)[-1],
                                    key="tiktok:strongest:capture") if len(sources) > 1 else sources[0]
        period = ranking_period(_table(repo, "account_panel_metrics"), window)
        if period:
            st.caption(f"Reporting labels: {period[0]} – {period[1]} · {window} days · timezone unknown.")
        else:
            st.caption(f"Native {window}-day ranking. Exact reporting bounds are unavailable in this collection.")
        st.caption("The ranked metric measures the selected reporting window. All views is a separate cumulative display. Native top lists are retained subsets, not all posts published in the window.")
        search = controls.text_input("Search ranked captions or verified post ID", key="tiktok:strongest:search")
        try:
            rows = select_native_rankings(all_rows, window, metric, source, search)
        except ValueError as exc:
            st.warning(str(exc))
            return
        metric_label = METRIC_LABELS[metric]
    else:
        metric = controls.selectbox("Rank snapshots by", list(SNAPSHOT_METRICS), format_func=SNAPSHOT_METRICS.get,
                                    key="tiktok:strongest:snapshot-metric")
        st.caption("Cumulative snapshots have unequal post ages and capture times. Ordering uses native exact or rounded display values; it does not measure activity within a selected period or a controlled creative comparison.")
        search = controls.text_input("Search ranked captions or verified post ID", key="tiktok:strongest:search")
        try:
            rows = prepare_snapshot_rankings(_table(repo, "post_summary"), inventory, metric, search)
        except ValueError as exc:
            st.warning(str(exc))
            return
        metric_label = SNAPSHOT_METRICS[metric]
    if rows.empty:
        st.info("No posts match these filters, or the selected source has no usable ranking metadata. Clear the search or choose another source.")
        return
    limit = controls.selectbox("Show ranked posts", [5, 10, 20, 50], index=1, key="tiktok:strongest:limit")
    shown = rows.head(limit)
    st.caption(f"Showing {len(shown):,} of {len(rows):,} matching rows. CSV includes all matching rows in this scope.")
    _plot(shown, metric_label + (" · reporting window" if native else " · cumulative snapshot"), "tiktok:strongest:chart")
    _display(shown, metric_label=metric_label, native=native)
    if native:
        unresolved = rows.public_url.eq("").sum()
        if unresolved:
            st.caption(f"{unresolved} matching rows have no unambiguous retained public link. Duplicate or unmatched captions stay unlinked.")
        st.caption("Source capture: " + source.rsplit("/", 1)[-1])
    st.download_button("Download filtered strongest-post rankings · CSV", inspection_csv(rows.drop(columns=["plot_value"], errors="ignore")),
                       "tiktok_strongest_posts.csv", "text/csv", key="tiktok:strongest:download")
