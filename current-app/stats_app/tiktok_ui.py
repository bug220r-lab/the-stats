"""TikTok Studio collection views and the preparation fallback.

Reporting dates, lifetime post snapshots and overlapping audience reports retain
their separate source scopes. This module never changes a saved collection.
"""
from pathlib import Path
import mimetypes
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stats_app.config import PROJECT_ROOT
from stats_app import dashboard_controls as controls
from stats_app.analysis_ui_common import chart
from stats_app.linktree_ui import inspection_csv
from stats_app.tiktok_collection import list_collections


STUDIO_SECTIONS = ("Account activity", "Strongest posts", "Owned posts", "Audience reports", "Rankings & comments", "Coverage & sources")
DATASET_ALIASES = {
    "daily": ("account_daily", "account_daily_resolved", "overview_daily"),
    "inventory": ("post_inventory", "posts_inventory"),
    "summary": ("post_summary", "post_summary_snapshots"),
    "viewers": ("post_viewers", "post_viewer_summary"),
    "breakdowns": ("post_breakdowns", "post_displayed_breakdowns"),
    "panels": ("post_panels", "post_panel_captures"),
    "rankings": ("content_rankings", "content_ranking_observations"),
    "comments": ("recent_comments", "comment_observations"),
    "dates": ("source_dispositions", "date_decisions", "date_resolution", "export_dispositions"),
}
METRIC_LABELS = {"video_views": "Video views", "profile_views": "Profile views", "likes": "Likes",
                 "comments": "Comments · signed source values", "shares": "Shares", "total_viewers": "Daily unique viewers",
                 "new_viewers": "New viewers", "returning_viewers": "Returning viewers", "followers": "Followers",
                 "net_followers": "Net follower change"}


def _datasets(repo):
    return repo.datasets.fillna("").to_dict("records")


def _dataset(repo, alias):
    items = {item["dataset_id"]: item for item in _datasets(repo)}
    for candidate in DATASET_ALIASES.get(alias, (alias,)):
        if candidate in items and items[candidate].get("path"):
            return items[candidate]
    return None


def _table(repo, alias):
    item = _dataset(repo, alias)
    return repo.table(item["dataset_id"]) if item else pd.DataFrame()


def exact_values(data, value_column="value", status_column="value_status"):
    """Only finite exact observations may enter a trend or numeric sort."""
    if value_column not in data:
        return pd.Series(float("nan"), index=data.index, dtype=float)
    raw = data[value_column].fillna("").astype(str)
    literal = raw.str.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")
    result = pd.to_numeric(raw.where(literal), errors="coerce").astype(float)
    result = result.where(result.abs().lt(float("inf")))
    if status_column in data:
        allowed = {"observed", "observed_exact", "observed_zero", "exact", "exact_displayed", "exact_integer", "reported", "zero", "derived"}
        result = result.where(data[status_column].fillna("").astype(str).isin(allowed))
    return result


def post_records(inventory, summary):
    """One owned-post row; captured overview counters keep their own provenance."""
    if inventory.empty:
        return summary.copy().fillna("")
    if summary.empty:
        return inventory.copy().fillna("")
    return summary.merge(inventory, on="post_id", how="outer", validate="one_to_one", suffixes=("", "_inventory")).fillna("")


def _search(data, query):
    if not query.strip() or data.empty:
        return data
    return data.loc[data.fillna("").astype(str).apply(lambda column: column.str.contains(query.strip(), case=False, regex=False)).any(axis=1)]


def _records(data, *, key, columns=(), label="retained records"):
    if data.empty:
        st.info("No retained records are available for this selection. Missing evidence is not zero activity.")
        return
    query = controls.text_input("Search these records", key=key + ":search")
    shown = _search(data, query)
    st.caption(f"{len(shown):,} of {len(data):,} {label}. Downloads include every filtered row.")
    if shown.empty:
        st.info("No records match this search.")
        return
    visible = [column for column in columns if column in shown] or shown.columns.tolist()
    st.dataframe(shown[visible], hide_index=True, width="stretch", height=360)
    st.download_button("Download filtered records · inspection CSV", inspection_csv(shown),
                       key.replace(":", "_") + ".csv", "text/csv", key=key + ":download")


def _daily(repo):
    data = _table(repo, "daily")
    st.subheader("Account activity")
    st.caption("Native source calendar · reporting timezone unknown. These daily account measures are separate from post lifetime counters and period-unique audiences.")
    resolution = repo.metadata.get("date_resolution_summary")
    if resolution:
        st.info(str(resolution))
    if data.empty:
        st.info("No reviewed daily account series is available. Inspect Coverage & sources for the date-resolution decision.")
        return
    date_column = next((field for field in ("date", "reporting_date", "period_start") if field in data), None)
    if not date_column:
        _records(data, key="tiktok:daily:unmapped")
        return
    if "metric" in data and "value" in data:
        metrics = data.metric.drop_duplicates().tolist()
        metric = controls.selectbox("Daily metric", metrics, format_func=lambda value: METRIC_LABELS.get(value, str(value).replace("_", " ").capitalize()), key="tiktok:daily:metric")
        selected = data.loc[data.metric.eq(metric)].copy()
        status = next((column for column in ("value_status", "availability_status", "status") if column in selected), "value_status")
        selected["_display_value"] = exact_values(selected, "value", status)
    else:
        metrics = [column for column in METRIC_LABELS if column in data]
        if not metrics:
            _records(data, key="tiktok:daily:unmapped")
            return
        metric = controls.selectbox("Daily metric", metrics, format_func=METRIC_LABELS.get, key="tiktok:daily:metric")
        selected = data.copy()
        selected["_display_value"] = exact_values(selected, metric, metric + "_status")
    dates = pd.to_datetime(selected[date_column], format="%Y-%m-%d", errors="coerce")
    if dates.isna().any() or selected[date_column].duplicated().any():
        st.warning("This selection contains invalid or repeated reporting dates. A daily chart is withheld; source rows remain available.")
        _records(selected.drop(columns="_display_value"), key="tiktok:daily:conflict")
        return
    low, high = dates.min().date(), dates.max().date()
    bounds = controls.date_range("TikTok reporting dates", low, high, (low, high), key="tiktok:daily:dates")
    if bounds is None:
        return
    start, end = bounds
    selected = selected.loc[selected[date_column].between(start.isoformat(), end.isoformat())].sort_values(date_column)
    if selected.empty:
        st.info("No source rows fall in this range.")
        return
    observed = int(selected._display_value.notna().sum())
    expected = (end - start).days + 1
    st.caption(f"{observed:,} exact values across {len(selected):,} retained reporting days in a {expected:,}-day selection. Missing or withheld values remain gaps.")
    if metric in {"video_views", "profile_views", "likes", "shares"} and observed == expected:
        st.metric(METRIC_LABELS.get(metric, metric) + " · selected days", f"{selected._display_value.sum():,.0f}")
    elif "viewer" in metric:
        st.caption("Daily unique viewers are not added into a period-unique audience.")
    elif metric == "comments":
        st.warning("Signed comment values retain the source export's semantics. Negative values are not replaced with zero or treated as newly posted comments.")
    timeline = selected.set_index(date_column)._display_value.reindex(pd.date_range(start, end).strftime("%Y-%m-%d"))
    fig = go.Figure(go.Scatter(x=timeline.index, y=timeline, mode="lines", connectgaps=False,
                              name=METRIC_LABELS.get(metric, metric), hovertemplate="%{x}<br>%{y}<extra></extra>"))
    fig.update_layout(xaxis_title="TikTok source calendar · timezone unknown", yaxis_title=METRIC_LABELS.get(metric, metric))
    chart(fig, key="tiktok:daily:chart")
    if "comments_signed_native" in selected:
        st.caption("The retained rows also preserve signed comment values. Their net-count semantics are unverified, so they are excluded from activity totals and charts.")
    _records(selected.drop(columns="_display_value"), key="tiktok:daily:rows", label="source-day observations")


def _post_detail(repo, row):
    post_id = str(row["post_id"])
    caption = row.get("caption_raw") or "Caption unavailable"
    st.write(caption)
    st.caption(f"Post {post_id} · {row.get('posted_date_raw') or row.get('publication_raw') or 'Publication date unavailable'} · publication timezone unknown")
    st.caption(f"Analytics captured {row.get('captured_at') or 'see panel evidence'} · lifetime/stated post scope")
    link = row.get("canonical_url") or row.get("observed_url")
    if isinstance(link, str) and link.startswith("https://www.tiktok.com/"):
        st.link_button("Open original post", link)
    cards = st.columns(5)
    for card, metric in zip(cards, ("views", "likes", "comments", "shares", "saves")):
        value = row.get(metric + "_raw") or row.get(metric + "_display") or "Unavailable"
        card.metric(metric.capitalize(), str(value))
    st.caption("Counters preserve TikTok's displayed precision. K/M values are rounded displays; they are not converted to exact counts or added into daily account totals.")
    fields = [("Average watch time", "average_watch_time_raw"), ("Completion", "completion_rate_raw"),
              ("Total play time", "total_play_time_raw"), ("New followers", "new_followers_raw")]
    st.dataframe(pd.DataFrame([{"Measure": label, "Native display": row.get(field) or "Unavailable"} for label, field in fields]), hide_index=True, width="stretch")
    viewers = _table(repo, "viewers")
    if not viewers.empty and "post_id" in viewers:
        viewers = viewers.loc[viewers.post_id.eq(post_id)]
        if not viewers.empty:
            st.caption("Post viewers are source snapshot populations and are not additive across posts.")
            st.dataframe(viewers[[column for column in ("total_viewers_raw", "precision", "captured_at", "scope") if column in viewers]], hide_index=True, width="stretch")
    breakdowns = _table(repo, "breakdowns")
    if not breakdowns.empty and "post_id" in breakdowns:
        breakdowns = breakdowns.loc[breakdowns.post_id.eq(post_id)]
        if not breakdowns.empty:
            dimension = controls.selectbox("Post audience or discovery breakdown", breakdowns.dimension.drop_duplicates().tolist(), key="tiktok:post:dimension")
            chosen = breakdowns.loc[breakdowns.dimension.eq(dimension)]
            st.dataframe(chosen[[column for column in ("label", "value_raw", "value_status", "scope", "captured_at") if column in chosen]], hide_index=True, width="stretch")
            st.caption("Percentages retain displayed rounding and less-than bounds. Suppressed or unavailable categories are not zero.")
    controls.own_keys("tiktok:post:evidence")
    if st.toggle("Inspect this post's source records", key="tiktok:post:evidence"):
        st.json(row.to_dict(), expanded=False)
        panels = _table(repo, "panels")
        if not panels.empty and "post_id" in panels:
            panels = panels.loc[panels.post_id.eq(post_id)]
            st.dataframe(panels, hide_index=True, width="stretch")
        st.caption("Saved panels preserve visible text and viewport images. They do not contain every interactive chart point or unavailable history.")


def _posts(repo):
    st.subheader("Owned posts")
    data = post_records(_table(repo, "inventory"), _table(repo, "summary"))
    if data.empty or "post_id" not in data:
        st.info("No owned-post inventory is retained.")
        return
    query = controls.text_input("Search caption or post ID", key="tiktok:posts:search")
    searchable = [column for column in ("post_id", "caption_raw", "selector_caption", "selector_label") if column in data]
    shown = data.loc[_search(data[searchable], query).index].copy()
    sort = controls.selectbox("Order posts", ["Inventory order", "Exact views · highest first", "Exact likes · highest first", "Exact comments · highest first"], key="tiktok:posts:order")
    if sort.startswith("Exact"):
        metric = sort.split()[1]
        shown["_sort"] = exact_values(shown, metric + "_exact", metric + "_status")
        shown = shown.sort_values("_sort", ascending=False, na_position="last", kind="stable").drop(columns="_sort")
        st.caption("Only exact displayed counts are ranked. Rounded or unavailable counts appear afterward; this is not a ranking of every post's true total.")
    elif "canonical_index" in shown:
        shown = shown.assign(_sort=pd.to_numeric(shown.canonical_index, errors="coerce")).sort_values("_sort", kind="stable").drop(columns="_sort")
    st.caption(f"{len(shown):,} of {len(data):,} owned posts · snapshots captured at different times and post ages")
    if shown.empty:
        st.info("No posts match this search.")
        return
    visible = [column for column in ("post_id", "caption_raw", "posted_date_raw", "views_raw", "likes_raw", "comments_raw", "shares_raw", "saves_raw") if column in shown]
    st.dataframe(shown[visible], hide_index=True, width="stretch", height=310)
    st.download_button("Download filtered post snapshots", inspection_csv(shown), "tiktok_post_snapshots.csv", "text/csv", key="tiktok:posts:download")
    rows = shown.set_index("post_id", drop=False)
    def post_label(post_id):
        row = rows.loc[post_id]
        text = str(row.get("caption_raw") or "Caption unavailable").replace("\n", " ")
        return f"{post_id} · {text[:90]}"
    selected = controls.selectbox("Inspect a post", rows.index.tolist(), format_func=post_label, key="tiktok:posts:selected")
    _post_detail(repo, rows.loc[selected])


def _audience(repo):
    st.subheader("Audience reports")
    choices = [item for item in _datasets(repo) if item.get("path") and
               (item.get("family") in {"audience", "viewers", "followers", "native_audience"}
                or any(token in item["dataset_id"] for token in ("viewer_daily", "viewer_history", "follower", "audience", "native_viewer", "account_panel_metrics", "account_breakdowns"))
                or any(token in str(item.get("label", "")).lower() for token in ("viewer", "follower")))]
    choices = [item for item in choices if not item["dataset_id"].startswith("post_")]
    if not choices:
        st.info("No account-audience table is available. Coverage & sources retains the collected evidence and its limits.")
        return
    items = {item["dataset_id"]: item for item in choices}
    selected = controls.selectbox("Audience source snapshot", list(items), format_func=lambda key: items[key].get("label") or key.replace("_", " "), key="tiktok:audience:dataset")
    item = items[selected]
    st.caption(str(item.get("definition") or item.get("scope") or "One retained native report."))
    disposition = item.get("date_disposition") or item.get("disposition")
    if disposition:
        message = "Date decision: " + str(disposition).replace("_", " ")
        (st.warning if "excluded" in str(disposition) or "conflict" in str(disposition) else st.info)(message)
    if item.get("reason"):
        st.warning(str(item["reason"]))
    st.caption("Overlapping reports remain separate. Daily unique viewers, period-unique viewers and follower stocks are not added together. Activity-hour exports retain their own seven-day coverage.")
    data = repo.table(selected)
    if selected in {"viewer_daily", "follower_daily"}:
        data = _audience_timeline(data, selected)
    elif "panel_id" in data:
        panel = controls.selectbox("Captured audience or summary panel", data.panel_id.drop_duplicates().tolist(), key="tiktok:audience:" + selected + ":panel")
        data = data.loc[data.panel_id.eq(panel)]
    _records(data, key="tiktok:audience:" + selected)


def _audience_timeline(data, dataset):
    """Chart only reviewed audience dates; raw alternative exports stay tables."""
    candidates = ("total_viewers", "new_viewers", "returning_viewers") if dataset == "viewer_daily" else ("followers", "net_followers")
    metrics = [metric for metric in candidates if metric in data]
    if data.empty or "date" not in data or not metrics:
        return data
    dates = pd.to_datetime(data.date, format="%Y-%m-%d", errors="coerce")
    if dates.isna().any() or data.date.duplicated().any():
        st.warning("Audience dates contain invalid or repeated labels. The timeline is withheld; native rows remain available.")
        return data
    metric = controls.selectbox("Audience timeline metric", metrics, format_func=METRIC_LABELS.get, key="tiktok:audience:" + dataset + ":metric")
    low, high = dates.min().date(), dates.max().date()
    bounds = controls.date_range("Audience reporting dates", low, high, (low, high), key="tiktok:audience:" + dataset + ":dates")
    if bounds is None:
        return data.iloc[0:0]
    start, end = bounds
    selected = data.loc[data.date.between(start.isoformat(), end.isoformat())].sort_values("date").copy()
    values = exact_values(selected, metric, metric + "_status")
    timeline = pd.Series(values.to_numpy(), index=selected.date).reindex(pd.date_range(start, end).strftime("%Y-%m-%d"))
    fig = go.Figure(go.Scatter(x=timeline.index, y=timeline, mode="lines+markers", connectgaps=False,
                              name=METRIC_LABELS[metric], hovertemplate="%{x}<br>%{y}<extra></extra>"))
    fig.update_layout(xaxis_title="TikTok source calendar · timezone unknown", yaxis_title=METRIC_LABELS[metric])
    chart(fig, key="tiktok:audience:" + dataset + ":chart")
    st.caption("Preferred native calendar only. Missing values, including a native undefined viewer total, remain gaps. No audience or follower-stock sum is calculated.")
    return selected


def _rankings_comments(repo):
    kind = controls.selectbox("Explore retained interactions", ["Content rankings", "Recent comments"], key="tiktok:interactions:kind")
    data = _table(repo, "rankings" if kind == "Content rankings" else "comments")
    st.subheader(kind)
    if data.empty:
        st.info("No records are retained for this selection.")
        return
    if kind == "Content rankings":
        st.caption("Rankings use their displayed window and metric. Native content exports contain a top-post subset, not the full owned-post inventory; ranking values and All views remain separate.")
        if "source_file" in data:
            selected = controls.selectbox("Ranking report", data.source_file.drop_duplicates().tolist(), key="tiktok:ranking:source")
            data = data.loc[data.source_file.eq(selected)]
        _records(data, key="tiktok:rankings", columns=("rank", "row_text", "semantic_scope", "captured_at"), label="ranking row observations")
    else:
        distinct = data.observation_fingerprint.nunique() if "observation_fingerprint" in data else None
        detail = f" · {distinct:,} distinct row fingerprints" if distinct is not None else ""
        st.caption(f"{len(data):,} repeated row observations{detail}. Fingerprints are not asserted unique comment IDs. This is a partial recent-comments capture, not all-time comment history.")
        _records(data, key="tiktok:comments", columns=("author", "row_text", "captured_at", "source_file", "identity_status"), label="recent comment observations")


def render_tiktok_coverage(repo, key="tiktok:coverage"):
    st.subheader("TikTok Studio coverage")
    st.info("TikTok for Artists remains pending by user instruction. Song and sound identity mappings are unresolved; Studio account activity does not establish community-wide use of a recording.")
    data = repo.datasets.copy()
    columns = [column for column in ("dataset_id", "label", "status", "row_count", "reason", "reporting_start", "reporting_end", "grain", "definition") if column in data]
    st.dataframe(data[columns], hide_index=True, width="stretch", height=360)
    st.download_button("Download TikTok coverage", inspection_csv(data), "tiktok_coverage.csv", "text/csv", key=key + ":download")
    dates = _table(repo, "dates")
    if not dates.empty:
        st.subheader("Export date decisions")
        st.dataframe(dates, hide_index=True, width="stretch")
    for note in repo.metadata.get("limitations", []):
        st.caption(str(note))


def render_tiktok_sources(repo, key="tiktok:sources"):
    st.subheader("TikTok retained sources")
    controls.own_keys(key + ":table_inspection")
    if st.toggle("Inspect a retained data table", key=key + ":table_inspection"):
        datasets = {item["dataset_id"]: item for item in _datasets(repo) if item.get("path")}
        if datasets:
            dataset = controls.selectbox("Retained table", list(datasets), format_func=lambda value: datasets[value].get("label") or value.replace("_", " "), key=key + ":table")
            item = datasets[dataset]
            st.caption(str(item.get("definition") or "Retained table; inspect source scope and reporting dates before comparing."))
            if item.get("date_disposition"):
                st.info("Date decision: " + str(item["date_disposition"]).replace("_", " "))
            if item.get("reason"):
                st.warning(str(item["reason"]))
            _records(repo.table(dataset), key=key + ":records:" + dataset)
    sources = repo.sources()
    query = controls.text_input("Find a source file", key=key + ":search")
    sources = _search(sources, query)
    st.caption(f"{len(sources):,} matching source assets. Source downloads preserve original bytes and verify their hashes; inspection CSVs make spreadsheet formulas inert.")
    if sources.empty:
        st.info("No source files match this search.")
        return
    st.dataframe(sources.head(100), hide_index=True, width="stretch", height=300)
    if len(sources) > 100:
        st.caption("Showing the first 100 file records. Search narrows both the table and the source selector.")
    selected = controls.selectbox("Retained source file", sources.path.tolist(), key=key + ":file")
    raw = repo.source_bytes(selected)
    st.download_button("Download unchanged retained source", raw, selected.rsplit("/", 1)[-1],
                       mimetypes.guess_type(selected)[0] or "application/octet-stream", key=key + ":original")
    controls.own_keys(key + ":manifest")
    if st.toggle("Show collection metadata", key=key + ":manifest"):
        st.json(repo.metadata, expanded=False)


def render_tiktok_studio(repo):
    if repo is None:
        st.info("No reviewed TikTok Studio collection is installed.")
        return
    st.caption("Authenticated Studio collection for " + str(repo.metadata.get("account", "account recorded in source evidence")) + ". TikTok for Artists remains pending.")
    controls.jump("Read TikTok and music findings", "TikTok insights", key="tiktok:open-insights")
    section = controls.radio("Explore TikTok Studio", STUDIO_SECTIONS, key="tiktok:section", horizontal=True, label_visibility="collapsed")
    if section == "Account activity":
        _daily(repo)
    elif section == "Strongest posts":
        from stats_app.tiktok_rankings_ui import render_tiktok_rankings
        render_tiktok_rankings(repo)
    elif section == "Owned posts":
        _posts(repo)
    elif section == "Audience reports":
        _audience(repo)
    elif section == "Rankings & comments":
        _rankings_comments(repo)
    else:
        render_tiktok_coverage(repo)
        render_tiktok_sources(repo)


def render_tiktok_entry(repo, kind, key):
    with st.expander("TikTok Studio collection · " + str(repo.metadata.get("collected_at", "dated collection"))[:10]):
        st.caption("Independent Studio collection. Open TikTok for account activity, owned posts, audience reports and date decisions. Artists remains pending.")
        controls.own_keys(key + ":open")
        if st.checkbox("Inspect TikTok " + kind, key=key + ":open"):
            (render_tiktok_sources if kind == "sources" else render_tiktok_coverage)(repo, key=key)


def render_tiktok_preparation(collection_root: Path | None = None):
    root = collection_root if collection_root is not None else PROJECT_ROOT / "data" / "collection"
    st.subheader("Collection workspace")
    st.info("Preparation only. TikTok performance is not integrated into The Stats. Missing evidence does not mean zero activity.")
    collections = list_collections(root)
    selected = None
    if collections:
        choices = {item["collection_id"]: item for item in collections}
        key = controls.selectbox("Preparation workspace", list(choices), key="tiktok:workspace")
        selected = choices[key]
        st.write(f"Profile: {selected.get('profile_url', 'Not supplied')}")
        status_label = str(selected.get("status", "unknown")).replace("_", " ").capitalize()
        st.caption(f"Identity: User supplied; ownership not verified · Prepared: {selected.get('prepared_on', 'unknown')} · Status: {status_label}")
        st.caption("The supplied profile identifies the intended collection. Native account ownership, reporting access, timezone and history still need verification.")
        st.write(f"Retained raw files: {selected.get('raw_file_count', 0)} · Evidence files: {selected.get('evidence_file_count', 0)}")
        for issue in selected.get("issues", []):
            st.warning(issue["message"])
    else:
        st.info("No TikTok preparation workspace found. Create a dated collection with the local preparation command.")

    collect, review, questions = st.tabs(["Collect", "Review & stage", "Analysis plan"])
    with collect:
        st.write("Start with account identity and a small native export to verify its layout. Then collect the widest useful history the account actually offers.")
        st.markdown("1. **Account trends:** real daily activity or explicitly bounded period reports.\n2. **Owned posts:** post IDs, captions, publication time, sound IDs and available performance/watch metrics.\n3. **Song activity:** TikTok for Artists track/sound evidence, if accessible, kept separate from the account's own posts.")
        if selected:
            queue = pd.DataFrame(selected.get("queue", []))
            if not queue.empty:
                queue = queue.drop(columns=["item_id"], errors="ignore")
                queue["status"] = queue["status"].str.replace("_", " ").str.capitalize()
                queue["required"] = queue["required"].map({"true": "Yes", "false": "Optional"})
                queue = queue.rename(columns={"label": "Collection step", "required": "Required", "status": "Status", "evidence_ref": "Evidence", "notes": "Notes"})
            st.dataframe(queue, hide_index=True, width="stretch")
            st.caption("Queue outcomes require source evidence. Collected, partial, verified empty, unavailable and blocked have different meanings; none implies library activation.")
            folder = Path(selected["path"])
            for name, label in [("post_log.csv", "Download post and campaign log"),
                                ("snapshot_schedule.csv", "Download post snapshot schedule")]:
                path = folder / name
                if path.is_file():
                    st.download_button(label, path.read_bytes(), name, "text/csv", key="tiktok:" + name)
        st.caption("For future posts, aim for captures around 24 hours, 72 hours, 7 days and 28 days. Record the actual capture time and age; missed earlier snapshots cannot be reconstructed from today's totals. No automatic collection is scheduled.")
        st.markdown("[TikTok Studio guidance](https://support.tiktok.com/en/using-tiktok/creating-videos/tiktok-studio) · [TikTok for Artists](https://artists.tiktok.com/)")
    with review:
        st.write("Preserve original downloads in raw/ and account/date/filter evidence in evidence/. Use explicit source mappings; templates describe The Stats fields, not guaranteed TikTok export headers.")
        st.code('.\\.venv\\Scripts\\python.exe scripts\\prepare_tiktok.py inspect --input "C:\\path\\to\\native-export.csv"', language="powershell")
        st.write("Before integration: verify ownership, native metric definitions and units, reporting dates and timezone; reconcile a matching source total; inspect missingness and overlapping captures; review sound-to-recording matches.")
        st.caption("Accepted staging is review evidence. It does not import, register or activate a collection. Lifetime snapshots never become daily activity or activity on the publication date.")
        if selected:
            st.code('.\\.venv\\Scripts\\python.exe scripts\\manage_tiktok_collection.py status --collection "' + str(folder) + '"', language="powershell")
            inventory = selected.get("inventory", [])
            if inventory:
                st.dataframe(pd.DataFrame(inventory), hide_index=True, width="stretch")
            else:
                st.info("No raw or supporting evidence files retained in this workspace yet.")
        guide = PROJECT_ROOT / "docs" / "TIKTOK_COLLECTION_20261026.md"
        if guide.is_file():
            st.download_button("Download collection guide", guide.read_bytes(), guide.name, "text/markdown", key="tiktok:guide")
    with questions:
        st.dataframe(pd.DataFrame([
            {"Decision": "Which clips hold attention?", "Evidence needed": "Owned-post watch/completion and engagement at comparable ages", "Boundary": "Keep source denominators, paid support and missing metrics explicit"},
            {"Decision": "Which recordings spread beyond our posts?", "Evidence needed": "Artists song/sound activity plus reviewed recording identities", "Boundary": "Community use is separate from owned-post publishing"},
            {"Decision": "Does discovery coincide with listening or purchases?", "Evidence needed": "Compatible TikTok, Linktree, Spotify, Apple Music and Shopify reporting windows", "Boundary": "Clicks, streams, listeners and sales remain separate; co-movement does not establish attribution"},
        ]), hide_index=True, width="stretch")
        st.caption("Performance charts and comparisons wait for reviewed native data. Historical analysis versions retain their original inputs.")
