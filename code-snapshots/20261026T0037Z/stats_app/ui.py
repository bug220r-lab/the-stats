"""Streamlit presentation only; parsing, rules and persistence are separate."""
from datetime import date, timedelta
import hashlib
import json
import sqlite3

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stats_app.access import enforce_access
from stats_app.branding import render_brand_header
from stats_app.calculations import chart_data, summarize_metric
from stats_app.config import PROJECT_ROOT, load_settings
from stats_app.ingestion import PROFILES, detect_profile, parse_export, read_table, sheet_names
from stats_app.library import LibraryRepository
from stats_app.navigation import navigation_regions, render_navigation
from stats_app.service import BASELINE_MANIFEST, commit_import, load_collected_baseline
from stats_app.storage import SQLiteRepository, StorageError
from stats_app.validation import COLUMNS, validate_records
from stats_app import dashboard_controls as controls


def label(value):
    return str(value).replace("_", " ").capitalize()


def source_download(data, name="observations.csv"):
    # Escape spreadsheet formulas in text exports. Original archived bytes are untouched.
    output = data.copy()
    for column in output.select_dtypes(include="object"):
        output[column] = output[column].map(lambda v: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v)
    st.download_button("Download these records · CSV", output.to_csv(index=False).encode("utf-8-sig"), name, "text/csv")


def empty_state():
    st.info("No observations imported yet. Open Import data to preview and save a CSV or Excel export.")
    st.write("Spotify needs an artist or track timeline export. Facebook and Instagram need Meta exports with account, metric and reporting scope. TikTok account analytics and TikTok for Artists are separate sources.")
    st.caption("Missing data is unavailable, never zero. No live platform credentials are required.")


def snapshot_label(row):
    return row.get("display_label", row["label"])


def render_records(repo, data):
    st.dataframe(data, hide_index=True, width="stretch")
    source_download(data)
    if not data.empty:
        observation = st.selectbox("Inspect provenance for observation", data.observation_id.tolist())
        st.dataframe(repo.observation_provenance(observation), hide_index=True, width="stretch")


def render_undated(repo, data):
    st.subheader("Lifetime and unknown reporting windows")
    st.info("These readings have no established reporting bounds. Publication dates and capture dates are retained separately and are not used as reporting windows. Lifetime results are not period activity.")
    if "published_at" in data and data.published_at.fillna("").ne("").any():
        st.caption("The published_at column is the source publication timestamp; no common content age or measurement cutoff is assumed.")
    selected_metrics = st.multiselect("Metrics in evidence table", sorted(data.metric.unique()))
    if selected_metrics:
        data = data.loc[data.metric.isin(selected_metrics)]
    st.caption(f"{len(data):,} source observations. No sum or date-axis placement is applied.")
    render_records(repo, data)


def overview(repo):
    snapshots = repo.list_snapshots()
    if snapshots.empty:
        empty_state()
        return
    displays = {row["label"]: snapshot_label(row) for row in snapshots.to_dict("records")}
    snapshot = st.sidebar.selectbox("Snapshot", snapshots["label"].tolist(), format_func=displays.get)
    snapshot_info = snapshots.loc[snapshots.label.eq(snapshot)].iloc[0]
    data = repo.observations(snapshot)
    st.caption(f"{displays[snapshot]} | {len(data):,} stored observations")
    st.warning("Original October 20 baseline: unavailable / unverified. A reporting endpoint or sealed archive does not establish original baseline membership. Earlier stored labels and records remain unchanged for audit.")
    st.caption("Snapshots may overlap. Select one source snapshot; do not add their totals together.")
    if data.empty:
        empty_state()
        return
    platforms = ["Spotify", "Apple Music", "Facebook", "Instagram", "TikTok", "TikTok for Artists"]
    available_platforms = [p for p in platforms if p in set(data.platform)]
    platform = st.sidebar.selectbox("Platform", platforms, index=platforms.index(available_platforms[0]) if available_platforms else 0)
    data = data.loc[data.platform.eq(platform)]
    if data.empty:
        st.subheader(f"{platform} · awaiting exports")
        st.info(f"No {platform} observations are stored in this snapshot. Use Import data with the appropriate account, period, units and source reference. Data in another project or archive is not automatically loaded.")
        return
    account_names = {}
    if "account_name" in data:
        account_names = {r.account: f"{r.account_name or r.account} · {r.account}" for r in data[["account", "account_name"]].drop_duplicates("account").itertuples()}
    account = st.sidebar.selectbox("Account", data.account.unique().tolist(), format_func=lambda value: account_names.get(value, value))
    data = data.loc[data.account.eq(account)]
    bounded = data.period_start.fillna("").ne("") & data.period_end.fillna("").ne("") & ~data.time_grain.eq("lifetime")
    modes = (["Dated activity"] if bounded.any() else []) + (["Lifetime / unknown window"] if (~bounded).any() else [])
    mode = st.sidebar.radio("Evidence view", modes) if len(modes) > 1 else modes[0]
    if mode == "Lifetime / unknown window":
        render_undated(repo, data.loc[~bounded].copy())
        return
    if (~bounded).any():
        st.caption(f"{int((~bounded).sum()):,} lifetime or undated readings are available separately under Evidence view.")
    data = data.loc[bounded].copy()
    entities = data[["entity_id", "entity_name", "entity_type"]].drop_duplicates(["entity_type", "entity_id"])
    labels = {(r.entity_type, r.entity_id): f"{r.entity_name or r.entity_id} · {r.entity_type}" for r in entities.itertuples()}
    entity = st.sidebar.selectbox("Artist, account or content", list(labels),
                                 format_func=lambda value: labels.get(value, str(value)),
                                 key=f"entity:{snapshot}:{platform}:{account}")
    data = data.loc[data.entity_type.eq(entity[0]) & data.entity_id.eq(entity[1])]
    metrics = data.metric.unique().tolist()
    metric = st.sidebar.selectbox("Metric", metrics, index=metrics.index("streams") if "streams" in metrics else 0,
                                 format_func=label, key=f"metric:{snapshot}:{platform}:{account}:{entity}")
    data = data.loc[data.metric.eq(metric)]
    # An export can carry several units, populations or definitions. Never combine these.
    scope_fields = ["unit", "measurement_type", "time_grain", "source_timezone", "dimensions_json", "definition"]
    scopes = data[scope_fields].drop_duplicates()
    def scope_text(row):
        dims = json.loads(row.dimensions_json or "{}")
        scope = dims.get("reported_scope", "").replace("_", " ")
        other = ", ".join(f"{label(k)}: {v}" for k, v in dims.items() if k not in {"reported_scope", "source_report"})
        return f"{label(row.time_grain)} · {label(row.measurement_type)} · {scope or other or 'All reported population'} · {row.unit}"
    if len(scopes) > 1:
        scopes = scopes.reset_index(drop=True)
        index = st.sidebar.selectbox("Measurement scope", list(scopes.index), format_func=lambda i: scope_text(scopes.loc[i]))
        for field in scope_fields:
            data = data.loc[data[field].eq(scopes.loc[index, field])]
    dimensions = json.loads(data.dimensions_json.iloc[0] or "{}")
    if dimensions.get("reported_scope"):
        st.info("Reported views scope: " + dimensions["reported_scope"].replace("_", " ") + ". Combined and component results are separate populations.")
    all_min = date.fromisoformat(data.period_end.min())
    all_max = date.fromisoformat(data.period_end.max())
    daily = data.time_grain.isin(["daily", "day"]).all()
    window = st.sidebar.selectbox("Window", ["Latest 28 days", "Latest 7 days", "Latest 90 days", "All available", "Custom"]) if daily else "Exact source period"
    days = {"Latest 28 days": 28, "Latest 7 days": 7, "Latest 90 days": 90}.get(window)
    start = max(all_min, all_max - timedelta(days=days - 1)) if days else all_min
    end = all_max
    if not daily:
        periods = sorted(set(zip(data.period_start, data.period_end)))
        selected_period = st.sidebar.selectbox("Exact source period", periods, index=len(periods)-1, format_func=lambda p: f"{p[0]} to {p[1]}")
        start, end = (date.fromisoformat(value) for value in selected_period)
        data = data.loc[data.period_start.eq(selected_period[0]) & data.period_end.eq(selected_period[1])]
    if window == "Custom":
        selected = st.sidebar.date_input("Reporting endpoints", (start, end), min_value=all_min, max_value=all_max)
        if len(selected) != 2:
            st.info("Choose a start and an end date.")
            return
        start, end = selected
    data = data.loc[data.period_end.between(start.isoformat(), end.isoformat())].copy()
    st.subheader(f"{label(metric)} · {labels[entity]}")
    st.caption(f"{start:%b %d, %Y} – {end:%b %d, %Y} · reporting endpoints · {platform}")
    if data.empty:
        st.info("No records cover this selection.")
        return
    definition = data.definition.iloc[0] or "Definition not supplied by source. Interpret cautiously."
    st.write(definition)
    summary = summarize_metric(data)
    last = data.sort_values("period_end").iloc[-1]
    fmt = lambda value: "Unavailable" if value is None or pd.isna(value) else f"{value:,.2f}".rstrip("0").rstrip(".")
    cards = st.columns(3)
    expected_days = (end - start).days + 1
    reported_days = data.period_end.nunique()
    coverage_gap = data.time_grain.eq("daily").all() and reported_days < expected_days
    total_label = "Partial observed sum" if summary.status == "partial" or coverage_gap else "Selected period total"
    cards[0].metric(total_label if data.measurement_type.iloc[0] == "period_count" else "Selected period aggregation", fmt(summary.value))
    cards[1].metric("Latest reported endpoint", fmt(last.value) if last.status == "observed" else "Unavailable")
    cards[2].metric("Observed source records", f"{summary.observed_rows:,}")
    st.caption(summary.explanation)
    if coverage_gap:
        st.warning(f"Coverage gap: {reported_days} of {expected_days} selected endpoints have records. Any displayed sum covers observed values only.")
    st.caption(f"Unit: {last.unit} · measurement: {label(last.measurement_type)} · source timezone: {last.source_timezone or 'Unknown'}")
    chart = chart_data(data)
    fig = go.Figure(go.Scatter(x=chart.period_end, y=chart.value, mode="lines" if daily and len(chart)>1 else "markers", connectgaps=False, line=dict(color="#EDD264", width=2), name=label(metric), hovertemplate="%{x|%b %d, %Y}<br>%{y:,.2f}<extra></extra>"))
    fig.update_layout(height=360, margin=dict(l=12, r=12, t=10, b=12), xaxis_title="Reporting endpoint", yaxis_title=f"{label(metric)} ({last.unit})", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
    with st.expander("Records, definitions and source references"):
        render_records(repo, data)
    coverage_note = f" Coverage is partial: {reported_days} of {expected_days} selected endpoints have records." if coverage_gap else ""
    summary_text = f"# The Stats — selection\n\nSnapshot: {snapshot}\n\n{platform} / {labels[entity]} / {metric}\n\nReporting endpoints: {start} to {end}\n\nUnit: {last.unit}; measurement: {last.measurement_type}; timezone: {last.source_timezone or 'unknown'}\n\n{definition}\n\nSelected aggregation: {fmt(summary.value)} ({summary.status}). {summary.explanation}{coverage_note}\n\nLatest endpoint {last.period_end}: {fmt(last.value)} ({last.status}).\n\nOriginal sources: {', '.join(sorted(data.source_names.unique()))}\n\nNo causal or cross-platform audience claims are made. Missing values remain missing.\n"
    st.download_button("Download selection summary · Markdown", summary_text, "the_stats_summary.md", "text/markdown")


def import_view(repo, principal, settings):
    st.subheader("Import data")
    if principal.role != "admin":
        st.info("Your viewer permission allows browsing and downloading records. An admin must import data.")
        return
    st.write("Preview an export, verify its identity and reporting scope, then save it to a named snapshot.")
    with st.expander("Preserved native Spotify archive — baseline unverified"):
        if BASELINE_MANIFEST.exists():
            st.write("The native source package is available locally. Loading verifies source hashes and protects five native CSVs. This does not establish original baseline membership. Repeating this action leaves values unchanged.")
            if st.button("Load preserved native Spotify archive"):
                try:
                    results = load_collected_baseline(repo, principal)
                    st.success(f"Archive preserved. Original baseline remains unverified. Added {sum(r.imported_rows for r in results):,} records; skipped {sum(r.duplicate_import for r in results)} previously imported files.")
                except (OSError, ValueError) as exc:
                    st.error(str(exc))
        else:
            st.info("Native source package is unavailable. Do not label later files as the baseline; import them under a new snapshot.")
    template = PROJECT_ROOT / "templates" / "observations.csv"
    if template.exists():
        st.download_button("Download canonical CSV template", template.read_bytes(), "observations.csv", "text/csv")
    source_mode = st.radio("Source", ["Upload a file", "Configured import folder"], horizontal=True)
    raw = None
    name = ""
    if source_mode == "Upload a file":
        upload = st.file_uploader("CSV, TSV or XLSX export", type=["csv", "tsv", "xlsx"])
        if upload is not None:
            raw, name = upload.getvalue(), upload.name
    elif not settings.import_dir or not settings.import_dir.is_dir():
        st.info("Set STATS_IMPORT_DIR to your export folder, then restart the app. Files are read without modification.")
    else:
        files = sorted(p for p in settings.import_dir.iterdir() if p.is_file() and p.suffix.lower() in {".csv", ".tsv", ".xlsx"})
        if files:
            path = st.selectbox("Export file", files, format_func=lambda p: p.name)
            if path.stat().st_size <= 25 * 1024 * 1024:
                raw, name = path.read_bytes(), path.name
            else:
                st.error("This export exceeds the 25 MiB import limit.")
        else:
            st.info("No CSV, TSV or XLSX files found in the configured folder.")
    if raw is None:
        return
    digest = hashlib.sha256(raw).hexdigest()
    try:
        sheet = st.selectbox("Worksheet", sheet_names(raw)) if name.lower().endswith(".xlsx") else None
        table = read_table(raw, name, sheet)
    except Exception as exc:
        st.error(f"Cannot read export: {exc}")
        return
    if st.session_state.get("draft", {}).get("file_key") != (digest, sheet):
        st.session_state.pop("draft", None)
    profile = st.selectbox("Import format", list(PROFILES), index=list(PROFILES).index(detect_profile(table)), format_func=PROFILES.get)
    st.caption(f"{name} · {len(table):,} source rows · SHA-256 {digest[:16]}…")
    st.dataframe(table.head(20), hide_index=True, width="stretch")
    with st.form("prepare_import"):
        snapshot = st.text_input("Snapshot label", value=f"New capture · {date.today().isoformat()}", help="Use a distinct label for changed values or later captures. Existing sealed snapshots are protected.")
        a, b = st.columns(2)
        platform = a.selectbox("Platform (fallback for mapped records)", ["Spotify", "Facebook", "Instagram", "TikTok", "TikTok for Artists"])
        account = b.text_input("Account identity", help="Stable artist or account ID from the export or source account.")
        entity_type = a.selectbox("Entity type", ["artist", "account", "track", "post", "video", "release", "playlist", "audience_segment"])
        entity_id = b.text_input("Entity ID", help="Use an explicit source-scoped ID if a platform ID is unavailable.")
        entity_name = a.text_input("Display name (optional)")
        timezone = b.text_input("Source timezone (blank if unknown)", value="UTC" if profile == "spotify_daily" else "")
        captured = a.text_input("Captured/as-of date or timestamp (optional)", help="ISO YYYY-MM-DD or timestamp. Leave unknown; import time is recorded separately.")
        evidence = b.text_input("Evidence/source reference (optional)")
        metadata = dict(platform=platform, account=account, entity_type=entity_type, entity_id=entity_id, entity_name=entity_name, source_timezone=timezone, captured_at=captured, evidence_ref=evidence)
        mapping = {}
        if profile != "spotify_daily":
            metadata["metric"] = a.text_input("Metric name (fallback)")
            metadata["unit"] = b.selectbox("Unit (fallback)", ["count", "percent", "seconds", "currency", "ratio"])
            metadata["measurement_type"] = a.selectbox("Measurement type (fallback)", ["period_count", "distinct_count", "point_in_time", "rolling_count", "cumulative", "rate"])
            metadata["time_grain"] = b.selectbox("Time grain (fallback)", ["daily", "period", "snapshot"])
            metadata["definition"] = st.text_input("Metric definition and scope (optional)")
            metadata["dimensions_json"] = st.text_input("Dimensions JSON (optional)", value="{}", help='For example paid/organic scope. Keep platform definitions distinct.')
            if profile == "meta_daily":
                mapping["value"] = st.selectbox("Value column", list(table.columns))
            else:
                metadata["period_start"] = a.text_input("Reporting start (fallback YYYY-MM-DD)")
                metadata["period_end"] = b.text_input("Reporting end (fallback YYYY-MM-DD)")
                with st.expander("Column mapping — canonical names map automatically"):
                    options = [""] + list(table.columns)
                    for field in COLUMNS:
                        if field in {"worksheet", "source_row"}:
                            continue
                        default = next((str(c) for c in table.columns if str(c).lower() == field), "")
                        choice = st.selectbox(label(field), options, index=options.index(default), key="map_" + field)
                        if choice:
                            mapping[field] = choice
        prepare = st.form_submit_button("Validate and preview", type="primary")
    if prepare:
        st.session_state.pop("draft", None)
        try:
            if not snapshot.strip():
                raise ValueError("A snapshot label is required.")
            records = parse_export(table, profile, metadata, mapping)
            issues = validate_records(records)
            if issues:
                for issue in issues[:20]:
                    st.error(issue)
                st.caption(f"{len(issues)} validation issue(s); nothing imported.")
            else:
                prepared = dict(file_key=(digest, sheet), raw_bytes=raw, source_name=name, records=records, snapshot_label=snapshot.strip(), provenance={"profile": profile, "mapping": mapping, "metadata": metadata, "worksheet": sheet or ""})
                preview = repo.preview_dataset(**{k:v for k,v in prepared.items() if k != "file_key"})
                st.session_state.draft = prepared
                st.session_state["import_preview_counts"] = (preview.imported_rows, preview.duplicate_rows, preview.duplicate_import)
        except (ValueError, TypeError) as exc:
            st.error(str(exc))
    draft = st.session_state.get("draft")
    if draft:
        st.subheader("Validated preview")
        st.caption(f"{len(draft['records']):,} observations → {draft['snapshot_label']}. This preview contains the last validated settings. Validate again after changing the form.")
        added, duplicates, repeated = st.session_state["import_preview_counts"]
        a,b = st.columns(2)
        a.metric("New observations", f"{added:,}")
        b.metric("Unchanged / duplicate rows", f"{duplicates:,}")
        st.caption("Validation runs the actual importer on an isolated in-memory copy. No production record has been saved; saving checks the current database again.")
        if repeated:
            st.info("This exact file and interpretation already exist in this snapshot. Saving it again will leave observations unchanged.")
        st.dataframe(draft["records"].head(50), hide_index=True, width="stretch")
        st.caption("Exact duplicates will be skipped. Conflicting values cancel the entire file import; use a new snapshot label to preserve a revision.")
        if st.button("Save this preview to SQLite", type="primary"):
            try:
                args = {k: v for k, v in draft.items() if k != "file_key"}
                result = commit_import(repo, principal, **args)
                st.success(f"Saved. {result.imported_rows:,} new records; {result.duplicate_rows:,} duplicates skipped. Data will remain after restart.")
                st.session_state.pop("draft", None)
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))


def sources_view(repo, settings, analysis=None):
    st.subheader("Sources & provenance")
    if settings.mode == "local":
        st.caption(f"Persistent database: {settings.database_path}")
    if analysis is not None:
        from stats_app.analysis_ui_common import download
        catalog = analysis.file_catalog()
        version = getattr(analysis, "registered_key", analysis.metadata.get("analysis_version", "selected saved version"))
        st.caption(f"Active analysis: {version} · {len(catalog):,} retained assets · {int(catalog.is_table.sum()):,} parsed tables. The local/handoff import history below is a separate source store.")
        with st.expander("Active analysis assets and source lineage"):
            st.dataframe(catalog, hide_index=True, width="stretch")
            download(catalog, "active_analysis_assets.csv", "sources-active-catalog")
            st.json(analysis.metadata.get("input_lineage", {}))
    snapshots = repo.list_snapshots()
    if snapshots.empty:
        if analysis is not None:
            st.info("No local or handoff imports are registered. The selected analysis assets remain available above.")
        else:
            empty_state()
        return
    st.dataframe(snapshots, hide_index=True, width="stretch")
    history = repo.import_history()
    st.subheader("Import history")
    st.dataframe(history, hide_index=True, width="stretch")
    if not history.empty:
        index = st.selectbox("Archived original source", history.index.tolist(), format_func=lambda i: f"{history.loc[i, 'source_name']} · {history.loc[i, 'snapshot_label']}")
        row = history.loc[index]
        st.download_button("Download unchanged original file", repo.original_source(row.source_hash), row.source_name, "application/octet-stream")
        st.json(json.loads(row.provenance_json))
    st.subheader("Collection gaps")
    st.write("This history lists local and registered handoff imports. The selected analysis and YouTube collections retain their own source inventories. Snapshots may overlap and must not be summed. Open Coverage & cross-reference for current saved coverage and historical snapshot issues.")


def coverage_view(repo, analysis=None, youtube_keys=()):
    st.subheader("Coverage & cross-reference")
    if analysis is not None:
        from stats_app.analysis_coverage import render_current_coverage
        render_current_coverage(analysis, youtube_keys, "cross-reference-current")
        st.subheader("Historical snapshot receipts")
    st.warning("The original October 20 baseline is unavailable / unverified. Legacy labels and source records are preserved; archive dates do not prove baseline membership.")
    st.info("The snapshot issues and queue below preserve their acquisition-time state. Earlier disabled Story exports do not describe the expanded content library. TikTok analytics remain uncollected in the retained evidence; access has not been rechecked.")
    snapshots = repo.list_snapshots()
    if snapshots.empty:
        if analysis is not None:
            st.info("No local or handoff snapshot issues are registered. Current saved coverage is shown above.")
        else:
            empty_state()
        return
    displays = {row["label"]: snapshot_label(row) for row in snapshots.to_dict("records")}
    chosen = st.selectbox("Coverage for snapshot", snapshots.label.tolist(), format_func=displays.get)
    issues = repo.coverage_issues(chosen)
    st.caption("Recorded validation issues and exclusions for this snapshot; warnings remain source-qualified.")
    if issues.empty:
        st.write("No recorded import issues. This is not proof of complete source coverage.")
    else:
        st.dataframe(issues, hide_index=True, width="stretch")
        source_download(issues, "snapshot_coverage_issues.csv")
    reports = repo.evidence_reports()
    for name, report in reports.items():
        with st.expander(name):
            if name.endswith("spotify_coverage.json"):
                if isinstance(report, list):
                    st.dataframe(pd.DataFrame(report), hide_index=True, width="stretch")
                else:
                    for key in ("coverage", "gaps"):
                        if isinstance(report.get(key), list):
                            st.write(label(key))
                            st.dataframe(pd.DataFrame(report[key]), hide_index=True, width="stretch")
                    st.json(report, expanded=False)
            else:
                st.json(report, expanded=False)
    with st.expander("Historical collection queue — preserved source state"):
        queue = repo.collection_queue()
        if queue.empty:
            st.write("No collection queue is registered.")
        else:
            st.dataframe(queue, hide_index=True, width="stretch")
            st.caption("Queue state belongs to its acquisition. Newer collection records do not silently change this historical queue.")


def main():
    st.set_page_config(page_title="[REDACTED] · The Stats™️", page_icon="📊", layout="wide")
    try:
        settings = load_settings()
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    principal = enforce_access(settings)
    render_brand_header()
    try:
        local_repo = SQLiteRepository(settings.database_path)
        repo = LibraryRepository(local_repo, settings.data_dir / "archive_registry.json")
        from stats_app.analysis_repository import load_registered_analysis, list_registered_analyses
        analysis = load_registered_analysis(settings.data_dir)
        versions = list_registered_analyses(settings.data_dir)
        from stats_app.youtube_repository import load_registered_youtube, list_registered_youtube
        try:
            youtube = load_registered_youtube(settings.data_dir)
            youtube_versions = list_registered_youtube(settings.data_dir)
        except (OSError, sqlite3.Error, ValueError) as exc:
            youtube, youtube_versions = None, []
            st.warning(f"The optional YouTube collection could not be read ({type(exc).__name__}). Other views remain available. Check its retained path and access permissions; this does not mean the channel has no activity.")
        from stats_app.shopify_repository import load_registered_shopify, list_registered_shopify
        try:
            shopify = load_registered_shopify(settings.data_dir)
            shopify_versions = list_registered_shopify(settings.data_dir)
        except (OSError, sqlite3.Error, ValueError, StorageError) as exc:
            shopify, shopify_versions = None, []
            st.warning(f"The optional Shopify collection could not be read ({type(exc).__name__}). Other views remain available; this does not mean the store has no activity.")
        primary_navigation, more_navigation, more = navigation_regions()
        more.divider()
        with more.expander("Saved sources & versions"):
            if len(versions) > 1:
                active = next((i for i, item in enumerate(versions) if item["active"]), 0)
                names = {item["key"]: item["label"] for item in versions}
                selected_version = controls.selectbox("Analysis version", list(names), index=active,
                                                       format_func=names.get,key="analysis_version")
                analysis = load_registered_analysis(settings.data_dir, selected_version)
            if len(youtube_versions) > 1:
                youtube_names = {item["key"]: item["label"] for item in youtube_versions}
                youtube_key = controls.selectbox("YouTube collection", list(youtube_names), format_func=youtube_names.get,
                                                  key="youtube_collection_selector")
                try:
                    youtube = load_registered_youtube(settings.data_dir, youtube_key)
                except (OSError, sqlite3.Error, ValueError) as exc:
                    youtube = None
                    st.warning(f"The selected YouTube collection could not be read ({type(exc).__name__}). Other views remain available.")
            if len(shopify_versions) > 1:
                shopify_names = {item["key"]: item["label"] for item in shopify_versions}
                shopify_key = controls.selectbox("Shopify collection", list(shopify_names), format_func=shopify_names.get,
                                                  key="shopify_collection_selector")
                try:
                    shopify = load_registered_shopify(settings.data_dir, shopify_key)
                except (OSError, sqlite3.Error, ValueError, StorageError) as exc:
                    shopify = None
                    st.warning(f"The selected Shopify collection could not be read ({type(exc).__name__}). Other views remain available.")
            st.caption("Saved versions retain their original inputs. YouTube and Shopify collections are independent of the analysis selection.")
            if st.button("Reload saved data", help="Clear report caches and reread saved sources. This does not collect fresh platform data."):
                st.cache_data.clear()
                st.rerun()
            st.caption("For fresh observations, import a new platform export. Reloading does not contact Spotify, Meta, YouTube or Shopify.")
        more.caption("Local · loopback only" if settings.mode == "local" else "Private hosted workspace")
        pages = (["Overview", "Spotify", "Social", "Cross-platform", "Data quality", "Snapshot explorer"]
                 if analysis is not None else ["Overview"])
        if analysis is not None:
            pages.insert(1, "Decision report")
        pages.append("Campaigns")
        if analysis is not None and "social/meta_collection/collection_status.csv" in analysis.tables:
            pages.insert(3, "Meta collection")
        if youtube is not None:
            pages.insert(min(3, len(pages)), "YouTube collection")
        if shopify is not None:
            pages.append("Shopify")
        navigation = pages + ["Import data", "Sources & provenance", "Coverage & cross-reference"]
        page = render_navigation(navigation, primary_navigation, more_navigation)
        if page == "Campaigns":
            from stats_app.campaign_ui import render_campaigns
            render_campaigns(local_repo, principal, analysis)
        elif analysis is not None and page == "Decision report":
            from stats_app.decision_ui import render_decision_report
            render_decision_report(analysis, youtube=youtube)
        elif youtube is not None and page == "YouTube collection":
            from stats_app.youtube_ui import render_youtube_collection
            render_youtube_collection(youtube, collection_keys=tuple(item["key"] for item in youtube_versions))
        elif shopify is not None and page == "Shopify":
            from stats_app.shopify_ui import render_shopify_collection
            render_shopify_collection(shopify)
        elif analysis is not None and page == "Meta collection":
            from stats_app.analysis_meta_ui import render_meta_collection
            render_meta_collection(analysis)
        elif analysis is not None and page in {"Overview", "Spotify", "Social", "Cross-platform", "Data quality"}:
            from stats_app.analysis_ui import render_overview, render_spotify, render_cross_platform, render_quality
            from stats_app.analysis_social_ui import render_social
            if page == "Data quality":
                render_quality(analysis, tuple(item["key"] for item in youtube_versions))
            else:
                {"Overview":render_overview, "Spotify":render_spotify, "Social":render_social,
                 "Cross-platform":render_cross_platform}[page](analysis)
            if page == "Data quality":
                inventory = PROJECT_ROOT / "data/reconciliation/reaudit_20261023/source_inventory.csv"
                with st.expander("Historical October 23 re-audit · before expanded content"):
                    if "social/meta_collection/follows_daily_resolved.csv" in analysis.tables:
                        st.write("This version uses the reviewed Instagram follows repair.")
                    else:
                        st.write("This saved version predates the Instagram follows repair; choose a newer analysis version to use that evidence.")
                    st.write("YTD listener changes require matching prior dates.")
                    if any(item['key'] == 'youtube-daily-20261023' for item in youtube_versions):
                        st.write("The YouTube daily supplement is installed separately; overlapping values are not added to its parent collection.")
                    st.caption("This receipt predates the expanded Meta content inventory. TikTok analytics, six unverified October Story soundtracks and original October 20 Spotify baseline membership remain unresolved. Historical statistical results keep their original inputs.")
                    if inventory.is_file():
                        st.download_button("Download historical re-audit source inventory", inventory.read_bytes(), "source_inventory.csv", "text/csv")
            if page == "Data quality" and youtube is not None:
                from stats_app.youtube_ui import render_collection_entry
                render_collection_entry(youtube, "coverage", "yt_quality_entry")
            if page == "Data quality" and shopify is not None:
                from stats_app.shopify_ui import render_shopify_entry
                render_shopify_entry(shopify, "coverage", "shopify_quality_entry")
        elif page in {"Overview", "Snapshot explorer"}:
            overview(repo)
        elif page == "Import data":
            st.caption("New uploads are saved as local workspace snapshots. Registered handoff snapshots remain read-only.")
            import_view(local_repo, principal, settings)
        elif page == "Sources & provenance":
            sources_view(repo, settings, analysis)
            if youtube is not None:
                from stats_app.youtube_ui import render_collection_entry
                render_collection_entry(youtube, "sources", "yt_sources_entry")
            if shopify is not None:
                from stats_app.shopify_ui import render_shopify_entry
                render_shopify_entry(shopify, "sources", "shopify_sources_entry")
        else:
            coverage_view(repo, analysis, tuple(item["key"] for item in youtube_versions))
            if youtube is not None:
                from stats_app.youtube_ui import render_collection_entry
                render_collection_entry(youtube, "coverage", "yt_coverage_entry")
            if shopify is not None:
                from stats_app.shopify_ui import render_shopify_entry
                render_shopify_entry(shopify, "coverage", "shopify_coverage_entry")
    except (OSError, StorageError, sqlite3.Error, ValueError) as exc:
        st.error(f"Cannot access persistent data: {exc}")
        st.info("Check STATS_DATA_DIR permissions and available disk space. Preserve the database; do not delete it to troubleshoot.")
