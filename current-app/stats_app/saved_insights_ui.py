"""Native, versioned TikTok/music readout; no external report runtime required."""
from pathlib import Path
import json

import pandas as pd
import plotly.express as px
import streamlit as st

from stats_app import dashboard_controls as controls
from stats_app.analysis_ui_common import chart
from stats_app.linktree_ui import inspection_csv
from stats_app.saved_insights import load_saved_insights
from stats_app.source_context import SourceContext, render_context
from stats_app.storage import StorageError


REPORT_VIEWS = {
    "Findings & actions": ("summary", "actions"),
    "Trends": ("momentum",),
    "Song priorities": ("song-choice",),
    "Post examples": ("recent-posts", "historical-posts"),
    "Other platforms": ("other-platforms",),
    "Sources & downloads": ("scope",),
}


def _chart(report, item):
    """Render the report's reviewed chart fields at their original grain."""
    rows = report.table(item["queryId"])
    spec = item["spec"]
    x, y = spec["x"], spec["y"]
    if rows.empty or not {x, y}.issubset(rows.columns):
        st.info("This chart has no compatible retained rows; unavailable values are not zero.")
        return
    rows = rows.copy()
    rows[y] = pd.to_numeric(rows[y], errors="coerce")
    st.subheader(item["title"])
    if spec["type"] == "line":
        rows[x] = pd.to_datetime(rows[x], errors="coerce")
        rows = rows.sort_values(x)
        fig = px.line(rows, x=x, y=y, markers=True, labels={x: "Complete month", y: spec.get("yLabel", y)})
        fig.update_traces(connectgaps=False)
        fig.update_yaxes(rangemode="tozero")
    elif spec["type"] == "horizontalBar":
        fig = px.bar(rows, x=y, y=x, orientation="h", labels={x: "Recording", y: "Streams"})
        fig.update_yaxes(autorange="reversed")
        fig.update_xaxes(rangemode="tozero")
    else:
        st.info("The retained chart type is not supported in this view. Its source rows remain available below.")
        return
    fig.update_layout(height=int(item.get("height", 330)))
    chart(fig, "insights:chart:" + item["id"])
    st.caption(report.queries[item["queryId"]].get("source", {}).get("reportingPeriod", "See source-specific reporting dates."))


def _source_inspector(report):
    labels = {key: value.get("source", {}).get("label", key) for key, value in report.queries.items()}
    selected = controls.selectbox("Inspect report evidence", list(labels), format_func=labels.get, key="insights:evidence")
    source = report.queries[selected].get("source", {})
    st.caption(source.get("reportingPeriod", "Source-specific reporting period"))
    for caveat in source.get("caveats", []):
        st.caption(caveat)
    rows = report.table(selected)
    query = controls.text_input("Search evidence rows", key="insights:search")
    if query.strip() and not rows.empty:
        mask = rows.fillna("").astype(str).apply(lambda column: column.str.contains(query.strip(), case=False, regex=False)).any(axis=1)
        rows = rows.loc[mask]
    st.caption(f"{len(rows):,} of {len(report.table(selected)):,} retained rows. Search applies to this table and its CSV only; the saved findings keep their original scope.")
    if rows.empty:
        st.info("No evidence rows match this selection. Missing evidence is not zero activity.")
    else:
        links = {name: st.column_config.LinkColumn(name.replace("_", " ").capitalize())
                 for name in ("canonical_url", "spotify_url", "permalink") if name in rows}
        st.dataframe(rows, hide_index=True, width="stretch", height=420, column_config=links)
    st.download_button("Download selected evidence · CSV", inspection_csv(rows), f"tiktok_insights_{selected}.csv",
                       "text/csv", key="insights:evidence-download")
    with st.expander("Source identity and methods"):
        st.json(source, expanded=False)
    with st.expander("Report manifest and source fingerprints"):
        st.json(report.metadata, expanded=False)
        st.json(json.loads(report.asset_bytes("sources.json")), expanded=False)


def render_saved_insights(root: Path | None = None):
    """A dated report independent of live source selections and external plugins."""
    try:
        report = load_saved_insights(root)
    except (StorageError, OSError, ValueError) as exc:
        st.error(f"The saved TikTok insights report could not be verified ({type(exc).__name__}).")
        st.info("Preserve the report package and restore its verified files. Other dashboard pages remain available; an unavailable report is not zero activity.")
        return
    if report is None:
        st.info("No saved TikTok and music report is installed. TikTok Studio and other collected sources remain available; missing report evidence is not zero activity.")
        return
    render_context(SourceContext(
        report.key, "October 27, 2026 · fixed TikTok and music analysis", account="[REDACTED] · TikTok @funnyguycrawl",
        reporting_start="Common comparison: 2026-09-23", reporting_end="2026-10-20; other sections have separate dates",
        timezone="Source-specific · TikTok timezone unknown", captured_at="October 2026 source snapshots; see receipts",
        availability="Available · verified saved report"))
    st.caption("This dated report uses meta-story-backfill-20261024 and TikTok tiktok-20261027-studio. Analysis-version selections on other pages do not change it. TikTok for Artists remains pending.")
    st.subheader(report.title)
    controls.jump("Open the 14-day Funny Guy / The Cut plan", "Content plan", key="insights:open-content-plan")
    controls.jump("Explore TikTok strongest posts", "TikTok", key="insights:open-rankings", **{"tiktok:section": "Strongest posts"})
    section = controls.radio("Report view", list(REPORT_VIEWS), horizontal=True, key="insights:section")
    indexed = {item["id"]: item for item in report.sections}
    for section_id in REPORT_VIEWS[section]:
        item = indexed.get(section_id)
        if item is None:
            st.info("This section is unavailable in the saved report.")
            continue
        st.markdown(item["markdown"])
        for chart_item in item.get("charts", []):
            _chart(report, chart_item)
    if section == "Sources & downloads":
        st.subheader("Complete report")
        st.caption("Exports contain every saved section, not just the visible view. The HTML includes its figures and opens offline.")
        a, b = st.columns(2)
        a.download_button("Download complete report · HTML", report.html(), "the_stats_tiktok_insights_20261027.html",
                          "text/html", key="insights:html-download")
        b.download_button("Download complete report · Markdown", report.markdown(), "the_stats_tiktok_insights_20261027.md",
                          "text/markdown", key="insights:markdown-download")
        provenance = {"manifest": report.metadata, "source_receipts": json.loads(report.asset_bytes("sources.json"))}
        st.download_button("Download report provenance · JSON", json.dumps(provenance, indent=2),
                           "the_stats_tiktok_insights_provenance.json", "application/json", key="insights:provenance-download")
        _source_inspector(report)
