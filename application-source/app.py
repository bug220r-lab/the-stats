"""The Stats™️ — run with python -m streamlit run app.py."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from stats.ingestion import FIELDS, PLATFORMS, folder_files, preview_import, read_table, safe_csv, suggest_mapping, worksheets
from stats.metrics import (METRICS, aggregate_metric, asof_series, compare_metrics, daily_series,
                           derived_ratio, filter_observations, indexed_series,
                           lag_correlation, lifetime_content_observations, summarize_results)
from stats.storage import Store

st.set_page_config(page_title="The Stats™️", page_icon="◒", layout="wide")
DATA_DIR = Path(os.environ.get("STATS_DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / "stats.sqlite3"
store = Store(DB)
SETTINGS = DATA_DIR / "settings.json"
try:
    settings = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
except (ValueError, OSError):
    settings = {}
ACCENT = settings.get("accent", "#E5C64B")
if len(ACCENT) != 7 or not ACCENT.startswith("#") or any(c not in "0123456789abcdefABCDEF" for c in ACCENT[1:]):
    ACCENT = "#E5C64B"
st.markdown(f"""<style>
.block-container {{padding-top:4rem; max-width:1500px;}}
[data-testid="stMetric"] {{background:#191D26;padding:18px;border-radius:10px;border-top:2px solid {ACCENT};}}
[data-testid="stMetricLabel"] {{color:#A9B0BF;}}
h1 {{letter-spacing:-.04em;}} h3 {{letter-spacing:-.02em;}}
.eyebrow {{color:{ACCENT};letter-spacing:.16em;font-size:.75rem;font-weight:600;}}
</style>""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_observations(path, token, snapshot_id):
    return Store(path).read_observations(snapshot_id)


def table(data, **kwargs):
    if isinstance(data, pd.DataFrame) and data.empty:
        st.caption("No records in this selection.")
    elif isinstance(data, list) and not data:
        st.caption("No records yet.")
    else:
        st.dataframe(data, width="stretch", hide_index=True, **kwargs)


def csv_download(label, frame, filename, key=None):
    st.download_button(label, safe_csv(frame), filename, "text/csv", key=key)


def metric_label(name):
    return name.replace("_", " ").capitalize()


def account_labels(frame):
    labels = {}
    for account_id, group in frame.groupby("account_id", sort=False):
        if group.platform.nunique()>1:
            source_names=[]
            for platform, source in group.groupby("platform",sort=False):
                names=source.account_name.dropna().astype(str)
                names=names[names.str.strip().ne("")]
                source_names.append(platform.replace("_"," ").title()+": "+(names.iloc[0] if len(names) else str(account_id)))
            labels[account_id]=" / ".join(source_names)+" · "+str(account_id)
            continue
        names = group.account_name.dropna().astype(str)
        names = names[names.str.strip().ne("")]
        name = names.iloc[0] if len(names) else str(account_id)
        labels[account_id] = f"{name} · {account_id}" if name != str(account_id) else str(account_id)
    return labels


def select_account(frame, key):
    """Prefer available account totals without combining source account IDs."""
    choices = frame.account_id.dropna().unique().tolist()
    labels = account_labels(frame)
    def priority(account_id):
        group = frame[frame.account_id.eq(account_id)]
        available = group[pd.to_numeric(group.value,errors="coerce").notna() &
                          ~group.status.fillna("").str.lower().isin(["missing","suppressed","unavailable","invalid","rejected","ambiguous","conflict","unverified"])]
        totals = available[available.entity_type.isin(["account","artist"]) &
                           available.period_start.notna() & available.period_end.notna()]
        if totals.metric.eq("views").any():
            return 0
        if totals.metric.eq("streams").any():
            return 1
        if not totals.empty:
            return 2
        return 3
    default = min(range(len(choices)),key=lambda index:priority(choices[index]))
    return st.selectbox("Account",choices,index=default,format_func=lambda value:labels.get(value,str(value)),key=key)


def fmt(value):
    if value is None or pd.isna(value):
        return "Unavailable"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def reported_scope_label(dimensions):
    try:
        value = json.loads(dimensions) if isinstance(dimensions,str) else dimensions
        reported = value.get("reported_scope") if isinstance(value,dict) else None
    except (ValueError,TypeError):
        reported = None
    labels = {"instagram_and_facebook":"Instagram and Facebook combined", "instagram":"Instagram only", "facebook":"Facebook only",
              "instagram_only":"Instagram only", "facebook_only":"Facebook only"}
    return labels.get(reported,str(reported).replace("_"," ")) if reported else None


def draw_series(series, label, unit="count"):
    if series.empty or series["value"].notna().sum() == 0:
        st.info("Daily trend unavailable. Import dated daily observations; period and lifetime values are not spread across days.")
        return
    fig = px.line(series, x="date", y="value", markers=False, labels={"value": f"{label} ({unit})", "date": "Source date"})
    fig.update_traces(line_color=ACCENT, connectgaps=False)
    fig.update_layout(template="plotly_dark", height=320, margin=dict(l=10,r=10,t=20,b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch")


def provenance(result):
    st.write(result.get("definition", ""))
    st.caption(f"Period: {result.get('period_start')} → {result.get('period_end')} · Unit: {result.get('unit')} · Snapshot: {snapshot_name}")
    if result.get("reason"):
        st.info(result["reason"])
    st.json({k: result.get(k) for k in ["coverage", "sources", "scope"]}, expanded=False)


def show_kpis(scope, metrics, prefix):
    results = {metric: aggregate_metric(scope, metric, start, end) for metric in metrics}
    for offset in range(0, len(metrics), 3):
        for col, metric in zip(st.columns(3), metrics[offset:offset+3]):
            result = results[metric]
            with col:
                st.metric(metric_label(metric), fmt(result.get("value")))
                source_scope = reported_scope_label(result.get("scope",{}).get("dimensions"))
                if source_scope:
                    st.caption("Reported scope: " + source_scope)
                with st.expander("Definition & source"):
                    provenance(result)
    return results


def show_trend(scope, metric):
    measurement = scope.loc[scope.metric.eq(metric), "measurement_type"].dropna().unique()
    if len(measurement) == 1 and measurement[0] in {"rolling_window_count", "cumulative_total"}:
        series = asof_series(scope, metric, start, end)
        st.caption("As-of observations of " + metric_label(metric).lower() + ". Each point retains its own window; these values are not added or used as daily activity in correlation.")
        draw_series(series, metric_label(metric), METRICS.get(metric,{}).get("unit","count"))
    else:
        series = daily_series(scope, metric, start, end)
        label = "Follower balance" if metric == "followers" else "Daily " + metric_label(metric).lower()
        draw_series(series, label, METRICS.get(metric,{}).get("unit","source units"))
        result = aggregate_metric(scope, metric, start, end)
        if result.get("measurement_type") == "period_count" and result.get("value") is not None and not series.empty:
            if series.value.isna().any():
                st.caption("The KPI is an exact source-window total; the daily chart has incomplete coverage and retains its gaps.")
            elif abs(series.value.sum() - result["value"]) > 1e-9:
                st.warning(f"Source reconciliation: daily chart sums to {fmt(series.value.sum())}; the exact-window source reports {fmt(result['value'])}. The KPI uses the exact-window total. Both sets of source rows remain available.")


def comparison_table(frame, key):
    st.subheader("Compare tracks, releases or content")
    eligible = frame[frame.entity_type.isin(["track","release","post","video","playlist","campaign"]) & ~frame.time_grain.eq("lifetime")]
    if eligible.empty:
        st.caption("No content or release exports are available for this account.")
        return
    typ = st.selectbox("Comparison entity type", sorted(eligible.entity_type.unique()), key=key+"ranktype")
    eligible = eligible[eligible.entity_type.eq(typ)]
    metric = st.selectbox("Comparison metric", sorted(eligible.metric.unique()), key=key+"rankmetric")
    eligible = eligible[eligible.metric.eq(metric)]
    dim = st.selectbox("Comparison population", sorted(eligible.dimensions.unique()), key=key+"rankdim")
    eligible = eligible[eligible.dimensions.eq(dim)]
    rows = []
    for entity_id, group in eligible.groupby("entity_id"):
        result = aggregate_metric(group,metric,start,end)
        published = group.published_at.dropna()
        rows.append({"entity_id":entity_id,"title":group.entity_name.iloc[0],"metric":metric,"value":result["value"],"unit":result["unit"],"period_start":result["period_start"],"period_end":result["period_end"],"measurement_type":result["measurement_type"],"definition":result["definition"],"published_at":published.iloc[0] if len(published) else None,"dimensions":group.dimensions.iloc[0],"source_url":group.source_url.iloc[0],"reason":result["reason"],"snapshot":snapshot_name})
    rankings = pd.DataFrame(rows)
    if typ in {"post","video"}:
        st.caption("Content appears in source order. Publication dates and measurement types are shown; lifetime totals and unequal exposure ages are not ranked as equivalent performance.")
    else:
        # Rank only a homogeneous population of counts from this same period.
        valid = rankings.dropna(subset=["value"])
        if not valid.empty and all(valid[col].nunique() == 1 for col in ["definition","unit","measurement_type","period_start","period_end"]) and valid.measurement_type.iloc[0] == "period_count":
            rankings = rankings.sort_values("value",ascending=False,na_position="last")
    table(rankings)
    csv_download("Download comparison table",rankings,"entity_comparison.csv",key+"rankdownload")


def lifetime_content_view(frame, key):
    content = lifetime_content_observations(frame)
    if content.empty:
        return
    st.subheader("Lifetime content observations")
    st.info("These are source-reported lifetime values as captured. The source does not establish a metric cutoff or a reporting-period total. Publication dates select posts; they do not identify when these views, actions or reach occurred.")
    st.caption("Content stays in source order. Different publication dates imply different exposure ages, so these observations are not ranked or compared as equal-period performance. The sidebar reporting window does not remove lifetime content.")
    published = pd.to_datetime(content.published_at, errors="coerce")
    mode = st.radio("Content publication selection", ["All publication dates", "Custom publication dates"], horizontal=True, key=key+"publication_mode")
    if mode == "Custom publication dates":
        known = published.dropna()
        if known.empty:
            st.info("Publication dates are unknown in this export; no publication filter can be applied.")
        else:
            bounds = st.date_input("Content publication dates", (known.min().date(), known.max().date()), key=key+"publication_dates")
            include_unknown = st.checkbox("Include content with unknown publication date", value=True, key=key+"unknown_publication")
            if len(bounds) == 2:
                content = lifetime_content_observations(content, str(bounds[0]), str(bounds[1]), include_unknown)
            else:
                st.info("Choose both publication dates to apply this content filter.")
    available = sorted(content.metric.dropna().unique())
    chosen = st.multiselect("Lifetime content metrics", available, default=available, key=key+"lifetime_metrics")
    content = content[content.metric.isin(chosen)]
    visible = [column for column in ["entity_id", "entity_name", "metric", "value", "unit", "published_at", "captured_at", "period_start", "period_end", "measurement_type", "status", "source_url", "dimensions", "definition", "source_filename", "source_row", "snapshot_name"] if column in content]
    st.caption(f"{content.entity_id.nunique():,} posts/videos · {len(content):,} source metric observations. Missing reporting-window fields remain blank; capture time is not a metric cutoff.")
    table(content[visible])
    csv_download("Download lifetime content observations", content, "lifetime_content_observations.csv", key+"lifetime_download")


def evidence_rows(frame):
    """Retain explicit lifetime observations beside date-filtered period rows."""
    period_rows = filter_observations(frame, start=start, end=end)
    lifetime = lifetime_content_observations(frame)
    if lifetime.empty:
        return period_rows
    return pd.concat([period_rows, lifetime.loc[~lifetime.index.isin(period_rows.index)]]).sort_index()


def social_collection_coverage():
    manifests=sorted((DATA_DIR/"social_captures").glob("*/capture_manifest.json"),reverse=True)
    if not manifests:
        return
    st.subheader("Current social collection coverage")
    st.caption("Loaded counts come from active observations in the named capture snapshot. Collection gaps remain source acquisition gaps; successful imports do not complete them.")
    import_history=store.imports()
    for path in manifests:
        try:
            manifest=json.loads(path.read_text())
        except (ValueError,OSError) as error:
            st.warning(f"Cannot read social capture manifest {path.parent.name}: {error}")
            continue
        name=manifest.get("snapshot_name") or "Unnamed capture snapshot"
        st.markdown("**"+name+"**")
        matching=[snapshot for snapshot in snapshots if snapshot["name"]==name]
        snapshot_ids={snapshot["id"] for snapshot in matching}
        datasets=[load_observations(str(DB),store.cache_token(),snapshot["id"]) for snapshot in matching]
        active=pd.concat(datasets,ignore_index=True) if datasets else pd.DataFrame()
        files=manifest.get("files",[])
        platforms=sorted({item.get("platform","unknown") for item in files} | (set(active.platform) if not active.empty else set()))
        coverage=[]
        for platform in platforms:
            manifest_files=[item for item in files if item.get("platform")==platform]
            hashes={item.get("sha256") for item in manifest_files if item.get("sha256")}
            loaded={item["file_hash"] for item in import_history if item["snapshot_id"] in snapshot_ids and not item.get("retired") and item["file_hash"] in hashes}
            observed=active[active.platform.eq(platform)] if not active.empty else active
            coverage.append({"platform":platform,"active_observations":len(observed),"accounts":observed.account_id.nunique() if not observed.empty else 0,
                             "loaded_manifest_files":len(loaded),"manifest_files":len(manifest_files),
                             "status":"Imported observations available" if len(observed) else "No observations imported into this named snapshot"})
        table(coverage)
        gaps=manifest.get("collection_gaps",[])
        if gaps:
            st.caption("Recorded collection gaps")
            table(pd.DataFrame(gaps).assign(snapshot=name))
        st.caption("Capture manifest: " + str(path.relative_to(DATA_DIR)))


def select_scope(frame, key, types=True):
    if frame.empty:
        return frame
    scope = frame.copy()
    if types:
        entity_types = sorted(scope["entity_type"].dropna().unique())
        preferred = next((x for x in ["artist", "account", "track", "video", "post"] if x in entity_types), entity_types[0])
        typ = st.selectbox("Entity type", entity_types, index=entity_types.index(preferred), key=key+"type") if len(entity_types)>1 else entity_types[0]
        scope = scope[scope.entity_type == typ]
    ids = scope.entity_id.dropna().unique().tolist()
    names = {str(r.entity_id): f"{r.entity_name or r.entity_id} · {r.entity_id}" for r in scope[["entity_id", "entity_name"]].fillna("").drop_duplicates().itertuples()}
    identity = st.selectbox("Entity", ids, format_func=lambda x: names.get(str(x),str(x)), key=key+"id") if len(ids)>1 else ids[0]
    scope = scope[scope.entity_id == identity]
    dims = scope.dimensions.fillna("{}").astype(str).unique().tolist()
    view_dimensions=scope.loc[scope.metric.eq("views"),"dimensions"].fillna("{}").astype(str)
    preferred_dim=view_dimensions.iloc[0] if len(view_dimensions) else dims[0]
    dim = st.selectbox("Population / dimensions", dims, index=dims.index(preferred_dim), key=key+"dim") if len(dims)>1 else dims[0]
    source_scope=reported_scope_label(dim)
    if source_scope:
        st.info("Reported metric scope: " + source_scope + ". The platform tab identifies the export source; this measure retains the source's stated population.")
    st.caption("Selected population / dimensions: " + dim)
    return scope[scope.dimensions.fillna("{}").astype(str) == dim]


def downloads(scope, results, key):
    rows = filter_observations(scope, start=start, end=end)
    st.subheader("Evidence & downloads")
    st.caption("Observation rows retain original periods and values. Do not sum all rows: daily counts, window totals and distinct audiences have different aggregation rules.")
    with st.expander("Inspect source observations"):
        table(rows)
    summary_rows = [{"metric": k, **{field: v.get(field) for field in ["value", "unit", "period_start", "period_end", "reason"]}, "snapshot": snapshot_name} for k,v in results.items()]
    csv_download("Download filtered source rows", rows, "the_stats_observations.csv", key+"obs")
    csv_download("Download calculated KPIs", pd.DataFrame(summary_rows), "the_stats_kpis.csv", key+"kpi")
    text = f"# The Stats™️\n\nSnapshot: {snapshot_name}\n\nSelected reporting dates: {start} to {end}\n\n"
    text += summarize_results(results) + "\n\n## Provenance\n\n"
    for name, result in results.items():
        text += f"### {metric_label(name)}\n\nDefinition: {result.get('definition')}\n\nUnit: {result.get('unit')}; actual period: {result.get('period_start')} to {result.get('period_end')}\n\nSources: {json.dumps(result.get('sources'), default=str)}\n\n"
    text += "Missing values remain missing. Cross-platform movement does not establish causation.\n"
    st.download_button("Download analysis (.md)", text, "the_stats_summary.md", "text/markdown", key=key+"md")


def imports_page():
    st.subheader("Add source data")
    st.write("Preview, map, then commit. Original bytes are archived unchanged and imports survive restart.")
    snapshots = store.snapshots()
    with st.expander("Create a snapshot", expanded=not snapshots):
        name = st.text_input("Snapshot name", placeholder="October 22 export")
        baseline = st.checkbox("This is the identified original October 20, 2026 baseline")
        evidence = st.text_area("Evidence identifying original snapshot membership", help="A reporting end date alone does not prove baseline identity. Use original file manifest or documented snapshot reference.")
        if st.button("Create snapshot", disabled=not name or (baseline and not evidence)):
            try:
                store.create_snapshot(name, is_baseline=baseline, status="verified" if baseline else "unverified", evidence=evidence)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    editable = [s for s in snapshots if not s["locked"]]
    if not editable:
        st.info("Create a new snapshot above before importing. Sealed snapshots preserve their original observations.")
        return
    target = st.selectbox("Import into snapshot", editable, format_func=lambda s:s["name"], key="import_target")
    with st.expander("Seal this snapshot"):
        if target["is_baseline"]:
            st.warning("Baseline is staging until sealed. Add only verified original members, then seal once complete.")
        seal = st.checkbox("All intended files are imported; preserve this snapshot permanently")
        if st.button("Seal snapshot", disabled=not seal):
            try:
                store.lock_snapshot(target["id"])
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    route = st.radio("Source", ["Upload CSV / XLSX", "Local folder"], horizontal=True)
    raw, filename = None, None
    if route == "Upload CSV / XLSX":
        uploaded = st.file_uploader("Choose an export", type=["csv", "xlsx"])
        if uploaded is not None:
            raw, filename = uploaded.getvalue(), uploaded.name
    else:
        folder = st.text_input("Configured import folder", settings.get("import_folder", str(DATA_DIR / "incoming")))
        if st.button("Save folder configuration"):
            settings["import_folder"] = folder
            SETTINGS.write_text(json.dumps(settings, indent=2))
            st.success("Folder saved. Files remain unchanged.")
        try:
            files = folder_files(folder)
            if files:
                file = st.selectbox("File to preview", files, format_func=lambda p:p.name)
                raw, filename = file.read_bytes(), file.name
            else:
                st.info("Place CSV or XLSX files in this folder, then select each file to preview and import.")
        except ValueError as exc:
            st.info(str(exc))
    st.download_button("Canonical manual-reading template", Path("templates/manual_readings.csv").read_bytes(), "manual_readings.csv", "text/csv")
    st.caption("Manual readings require the actual reporting window, capture date and evidence reference. Unknown metadata should stay blank, with availability explained.")
    if raw is None:
        return
    try:
        sheet = st.selectbox("Worksheet", worksheets(raw, filename))
        header = st.number_input("Header row (1-based)", 1, 100, 1)
        frame = read_table(raw, filename, sheet, header)
        st.caption(f"{len(frame):,} source rows · {len(frame.columns)} columns")
        table(frame.head(15))
        mappings = store.mappings()
        chosen = st.selectbox("Saved mapping", ["Detect columns"] + list(mappings))
        suggested = mappings[chosen] if chosen != "Detect columns" else suggest_mapping(frame)
        form_key = filename + sheet + str(header) + chosen
        c1,c2,c3 = st.columns(3)
        platform = c1.selectbox("Default platform", [""]+PLATFORMS, key=form_key+"platform")
        account = c2.text_input("Default account ID / explicit source key", key=form_key+"account")
        entity_type = c3.selectbox("Default entity type", ["", "artist", "account", "track", "release", "playlist", "post", "video", "campaign", "audience_segment"], key=form_key+"entity")
        c1,c2,c3 = st.columns(3)
        grain = c1.selectbox("Default time grain", ["", "daily", "period", "rolling", "point", "lifetime"], key=form_key+"grain")
        capture = c2.text_input("Capture/as-of date or ISO timestamp (if known)", key=form_key+"capture")
        timezone = c3.text_input("Source timezone (if known)", key=form_key+"tz")
        with st.expander("Column mapping and metadata", expanded=True):
            st.caption("fields maps canonical field → source column. metrics maps wide source column → metric. defaults supplies metadata. Change mappings before previewing; IDs are never joined by similar names.")
            mapping_text = st.text_area("Mapping JSON", json.dumps(suggested, indent=2), height=250, key=form_key+"mapping")
            mapping_name = st.text_input("Mapping profile name", key=form_key+"name")
        mapping = json.loads(mapping_text)
        mapping.setdefault("defaults", {}).update({k:v for k,v in {"platform":platform,"account_id":account,"entity_type":entity_type,"time_grain":grain,"captured_at":capture,"source_timezone":timezone}.items() if v})
        if st.button("Save mapping profile", disabled=not mapping_name):
            store.save_mapping(mapping_name,mapping)
            st.success("Mapping saved to SQLite.")
        preview = preview_import(frame,mapping,filename,raw,sheet,header)
        st.subheader("Import preview")
        st.write({"platforms":preview["platforms"],"accounts":preview["accounts"],"period_start":preview["period_start"],"period_end":preview["period_end"],"accepted_observations":len(preview["observations"]),"SHA256":preview["file_hash"]})
        table(pd.DataFrame(preview["observations"]).head(30))
        table(preview["issues"])
        existing = store.read_observations(target["id"])
        if not existing.empty and preview["observations"]:
            keys = ["platform","account_id","entity_type","entity_id","metric","period_start","period_end","unit","definition","dimensions","time_grain","measurement_type","source_timezone"]
            incoming = pd.DataFrame(preview["observations"])
            overlap = incoming.merge(existing, on=keys, suffixes=("_incoming","_stored"))
            if not overlap.empty:
                st.warning(f"{len(overlap):,} overlapping rows. Equal values add provenance only; changed values become explicit revisions in an editable snapshot.")
                table(overlap[[*keys,"value_stored","value_incoming"]].head(50))
        errors = [x for x in preview["issues"] if x.get("severity") == "error"]
        acknowledge = st.checkbox("I reviewed metadata, units, mappings and validation issues")
        allow_partial = st.checkbox("Import valid rows and retain rejected rows in the issue log", disabled=not errors)
        conflicting = any("Conflicting rows" in x.get("message","") for x in errors)
        if st.button("Commit import", type="primary", disabled=not acknowledge or not preview["observations"] or (bool(errors) and not allow_partial) or conflicting):
            result = store.commit_import(target["id"],filename,raw,preview["observations"],worksheet=sheet,mapping=mapping,issues=preview["issues"])
            st.success(f"Import committed: {result}")
            st.cache_data.clear()
    except Exception as exc:
        st.error(f"Import needs attention: {exc}")


st.sidebar.markdown("## ◒ The Stats™️")
st.sidebar.caption("MUSIC + SOCIAL · LOCAL ANALYTICS")
snapshots = store.snapshots()
navigation = ["Overview", "Spotify", "Social media", "Cross-platform", "Data & collection", "Import data"]
if "workspace_nav" not in st.session_state:
    st.session_state["workspace_nav"] = navigation[0] if snapshots else navigation[5]
page = st.sidebar.radio("Workspace", navigation, key="workspace_nav")
sealed_baseline = any(s["is_baseline"] and s["locked"] for s in snapshots)
if not sealed_baseline:
    st.sidebar.caption("October 20 baseline: unavailable / unverified")
snapshot_id, snapshot_name = None, "No snapshot"
all_data = pd.DataFrame()
if snapshots:
    selected = st.sidebar.selectbox("Snapshot", snapshots, format_func=lambda s:s["name"]+(" · sealed" if s["locked"] else " · editable"))
    snapshot_id,snapshot_name = selected["id"],selected["name"]
    all_data = load_observations(str(DB),store.cache_token(),snapshot_id)
start=end=None
filtered=all_data
if not all_data.empty:
    platforms = st.sidebar.multiselect("Platforms",sorted(all_data.platform.unique()),default=sorted(all_data.platform.unique()))
    account_options = all_data[all_data.platform.isin(platforms)].account_id.unique().tolist()
    sidebar_account_labels = account_labels(all_data)
    accounts = st.sidebar.multiselect("Accounts",account_options,default=account_options,format_func=lambda value:sidebar_account_labels.get(value,str(value)))
    reporting_starts = pd.to_datetime(all_data.period_start, errors="coerce")
    reporting_ends = pd.to_datetime(all_data.period_end, errors="coerce")
    known_windows = reporting_starts.notna() & reporting_ends.notna()
    if known_windows.any():
        min_date = reporting_starts[known_windows].min().date()
        max_date = reporting_ends[known_windows].max().date()
        window = st.sidebar.selectbox("Reporting window",["28 days","7 days","90 days","All dates","Custom"])
        if window == "Custom":
            dates = st.sidebar.date_input("Source reporting dates",(max(min_date,max_date-pd.Timedelta(days=27)),max_date),min_value=min_date,max_value=max_date)
            if len(dates)==2:
                start,end=map(str,dates)
        else:
            days = {"7 days":7,"28 days":28,"90 days":90}.get(window)
            start,end = str(max_date-pd.Timedelta(days=days-1)) if days else str(min_date),str(max_date)
        st.sidebar.caption(f"{start} → {end}\n\nDates use source buckets; no timezone reassignment. Lifetime content has separate publication filters.")
    else:
        st.sidebar.caption("No reporting windows are supplied in this snapshot. Lifetime content remains available with publication and capture dates in Social media.")
    filtered = filter_observations(all_data,platforms=platforms,accounts=accounts)
with st.sidebar.expander("Appearance"):
    color = st.color_picker("Chart accent",ACCENT)
    if st.button("Save color"):
        settings["accent"]=color
        SETTINGS.write_text(json.dumps(settings,indent=2))
        st.rerun()
st.markdown('<div class="eyebrow">THE STATS™️ / YOUR MUSIC, IN CONTEXT</div>',unsafe_allow_html=True)
st.title(page)
st.caption(snapshot_name)

if page == "Import data":
    imports_page()
elif page == "Data & collection":
    tab1,tab2,tab3,tab4,tab5 = st.tabs(["Inventory & history","Collection queue","Definitions","Annotations","Maintenance"])
    with tab1:
        social_collection_coverage()
        st.subheader("Snapshots")
        table(snapshots)
        st.subheader("Imported files")
        table(store.imports())
        st.subheader("Source inventory")
        table(store.inventory())
        st.subheader("Validation issues")
        table(store.issues())
        if not filtered.empty:
            st.subheader("Accounts and reporting coverage")
            table(filtered.groupby(["platform","account_id","account_name","entity_type"],dropna=False).agg(first_date=("period_start","min"),last_date=("period_end","max"),observations=("metric","size")).reset_index())
            st.caption("Reporting-window filters apply to dated periods. Explicit lifetime content remains included with its original publication/capture dates and blank reporting window.")
            csv_download("Download selected snapshot rows",evidence_rows(filtered),"snapshot_rows.csv")
        inv = DATA_DIR/"connected"/"SOURCE_INVENTORY.md"
        if inv.exists():
            with st.expander("Historical original package · source inspection notes"):
                st.caption("These notes describe the original connected package. Current social captures and their remaining gaps are reported separately above.")
                st.markdown(inv.read_text())
        private_inventory = DATA_DIR/"connected"/"source_inventory.json"
        if private_inventory.exists():
            with st.expander("Historical original package · inventory and gaps"):
                st.caption("Original package inventory; it does not describe the completion status of newer social captures.")
                st.json(json.loads(private_inventory.read_text()))
    with tab2:
        st.info("Source statuses and timestamps remain as recorded. Local notes do not complete source collection tasks.")
        queue = store.queue()
        table(queue)
        if queue:
            row = st.selectbox("Collection row",queue,format_func=lambda x:str(x.get("id",x.get("row_id",x))))
            note = st.text_area("Local note",str(row.get("local_note", "")))
            if st.button("Save local collection note"):
                store.save_queue_note(row.get("id",row.get("row_id")),note)
                st.rerun()
        with st.expander("Import recorded queue CSV"):
            q = st.file_uploader("Collection queue CSV",type="csv",key="queue_upload")
            ref = st.text_input("Queue source reference")
            captured = st.text_input("Queue capture date (if known)")
            if q is not None:
                qframe = read_table(q.getvalue(),q.name)
                table(qframe)
                if st.button("Record queue",disabled=not ref):
                    store.save_queue(qframe.to_dict("records"),ref,captured or None)
                    st.rerun()
    with tab3:
        st.markdown(Path("docs/METRIC_DICTIONARY.md").read_text())
        st.subheader("Current metric catalog")
        st.caption("Built-in definitions used by the import and calculation layers. A source's explicit native definition remains attached to each observation.")
        table(pd.DataFrame.from_dict(METRICS,orient="index").rename_axis("metric").reset_index())
        st.subheader("Needed exports")
        st.markdown(Path("docs/EXPORT_GUIDE.md").read_text())
    with tab4:
        st.caption("User-entered local annotations. Explicit links describe an association; they do not establish attribution.")
        annotations = store.annotations()
        table(annotations)
        choices = [{"id":None,"title":"New annotation"}]+annotations
        a = st.selectbox("Edit annotation",choices,format_func=lambda x:x.get("title","Untitled"))
        with st.form("annotation"):
            adate=st.text_input("Date (YYYY-MM-DD)",str(a.get("date",end or "")))
            kind=st.selectbox("Kind",["release","post","show","campaign","note"])
            title=st.text_input("Title",a.get("title","") if a.get("id") else "")
            notes=st.text_area("Notes",a.get("notes", ""))
            links=st.text_area("Explicit content / campaign / track links (JSON list)",json.dumps(a.get("links",[])) if not isinstance(a.get("links",[]),str) else a["links"])
            if st.form_submit_button("Save annotation"):
                try:
                    pd.Timestamp(adate)
                    parsed=json.loads(links)
                    if not isinstance(parsed,list) or not title:
                        raise ValueError("A title and JSON list of links are required")
                    store.save_annotation({"id":a.get("id"),"date":adate,"kind":kind,"title":title,"notes":notes,"links":parsed})
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    with tab5:
        st.write("Correct a mapping by retiring its import in an editable snapshot, then reimporting with a corrected mapping. Retired observations remain in history. Sealed baselines are immutable.")
        history=store.imports()
        if history:
            imp=st.selectbox("Import to retire",history,format_func=lambda x:f"{x.get('id',x.get('import_id'))} · {x.get('filename',x.get('source_filename'))}")
            confirmed=st.checkbox("Retire this import from active calculations")
            if st.button("Retire import",disabled=not confirmed):
                try:
                    store.retire_import(imp.get("id",imp.get("import_id")))
                    st.cache_data.clear()
                    st.success("Import retired. History and original bytes preserved.")
                except ValueError as exc:
                    st.error(str(exc))
        st.caption("Back up the entire data directory while the app is stopped. See README for the SQLite online backup command.")
elif all_data.empty:
    st.info("Your dashboard is ready for data. Open Import data to upload CSV/XLSX exports or select a configured local folder.")
    st.write("Spotify, Meta and TikTok each keep their own measures. No artificial analytics or demo data are loaded.")
    st.download_button("Download manual-reading template",Path("templates/manual_readings.csv").read_bytes(),"manual_readings.csv","text/csv")
elif filtered.empty:
    st.info("No observations match the selected platforms and accounts. Adjust the sidebar filters.")
elif page == "Overview":
    st.caption("KPIs use one account and entity population at a time. Selected windows with gaps remain unavailable.")
    results={}
    selected_scopes=[]
    for platform,frame in filtered.groupby("platform"):
        st.markdown(f"### {platform.replace('_',' ').title()}")
        account=select_account(frame,"overview_"+platform)
        frame=frame[frame.account_id==account]
        frame=frame[frame.entity_type.isin(["artist","account"])]
        if frame.empty:
            st.info("Account totals unavailable. Use the platform view for track or content observations; breakdowns are not added to account totals.")
            continue
        scope=select_scope(frame,"overview"+platform)
        selected_scopes.append(scope)
        st.caption(f"{scope.account_name.iloc[0] or account} · {account}")
        available=scope.metric.unique().tolist()
        preferred=[x for x in (["streams","listeners","followers"] if platform=="spotify" else ["views","reach","followers"]) if x in available]
        platform_results=show_kpis(scope,preferred or available[:3],platform)
        for k,v in platform_results.items():
            results[platform+" / "+k]=v
        if start and end:
            prev_end=str((pd.Timestamp(start)-pd.Timedelta(days=1)).date())
            prev_start=str((pd.Timestamp(start)-(pd.Timestamp(end)-pd.Timestamp(start))-pd.Timedelta(days=1)).date())
            for metric in preferred[:2]:
                cmp=compare_metrics(scope,scope,metric,start=start,end=end,previous_start=prev_start,previous_end=prev_end)
                st.caption(f"{metric_label(metric)} vs {prev_start}–{prev_end}: " + (f"{fmt(cmp.get('percent_change'))}%" if cmp.get('percent_change') is not None else str(cmp.get('reason','Comparison unavailable'))))
        trend=st.selectbox("Trend",available,index=available.index("streams") if "streams" in available else 0,key="overview_trend"+platform)
        show_trend(scope,trend)
    st.subheader("Observations")
    st.write(summarize_results(results))
    endpoints = filtered.period_end.dropna().replace("",pd.NA).dropna()
    st.caption(f"Latest reporting bucket: {endpoints.max() if len(endpoints) else 'not supplied'}. This is separate from capture and import time.")
    known_captures=filtered.captured_at.dropna().replace("",pd.NA).dropna()
    st.caption(f"Latest recorded capture: {known_captures.max() if len(known_captures) else 'unknown'}. Exact capture missing on {len(filtered)-len(known_captures):,} observations. Last local import: {filtered.imported_at.max()}.")
    downloads(pd.concat(selected_scopes) if selected_scopes else filtered.iloc[:0],results,"overview")
elif page in {"Spotify","Social media"}:
    frame=filtered[filtered.platform.eq("spotify") if page=="Spotify" else filtered.platform.ne("spotify")]
    if frame.empty:
        st.info("No data for this platform in the selected snapshot. Open Import data and use the export checklist below.")
        st.markdown(Path("docs/EXPORT_GUIDE.md").read_text())
    else:
        if page=="Social media":
            p=st.selectbox("Social platform",sorted(frame.platform.unique()))
            frame=frame[frame.platform==p]
            st.info("TikTok account/content and TikTok for Artists are separate platforms. Rates retain their denominators; paid/organic and attribution dimensions stay distinct.")
        acc=select_account(frame,page+"_account")
        account_frame=frame[frame.account_id==acc]
        if page=="Social media":
            lifetime_content_view(account_frame,page)
            period_frame=account_frame[~account_frame.time_grain.eq("lifetime")]
        else:
            period_frame=account_frame
        if period_frame.empty:
            st.info("No period-based metrics are supplied for this account. The lifetime observations above remain available with their publication dates, capture dates and source references.")
        else:
            scope=select_scope(period_frame,page)
            default_metrics = [m for m in ["streams","listeners","followers","views","reach","impressions"] if m in scope.metric.unique()][:3]
            metrics=st.multiselect("Metrics",sorted(scope.metric.unique()),default=default_metrics or sorted(scope.metric.unique())[:3])
            results=show_kpis(scope,metrics,page)
            for metric in metrics:
                st.subheader(metric_label(metric))
                show_trend(scope,metric)
            if page=="Spotify":
                for num,den in [("streams","listeners"),("saves","listeners")]:
                    if num in scope.metric.values and den in scope.metric.values:
                        ratio=derived_ratio(scope,num,den,start,end)
                        st.metric(f"{metric_label(num)} per listener",fmt(ratio.get("value")))
                        st.caption("This is a count ratio, not a unique-person conversion rate. " + str(ratio.get("reason") or ""))
                        with st.expander(f"{metric_label(num)} per listener · definition & source"):
                            provenance(ratio)
                        results[num+"_per_listener"]=ratio
                with st.expander("Audience, geography, sources and playlists"):
                    st.write("Use Entity type and Population / dimensions above for available segments. The following sections need their own compatible exports.")
                    for typ,need in [("audience_segment","Countries/cities, demographics and stream-source tables with reporting windows and population definitions"),("playlist","Playlist ID, streams, reporting window and contribution definition"),("release","Release ID and dated release performance")]:
                        st.write(f"{typ.replace('_',' ').title()}: {'available in this snapshot' if typ in frame.entity_type.values else 'unavailable — '+need}")
                    st.caption("Rolling monthly listeners are distinct from daily or selected-period unique listeners. No artist benchmark dataset is loaded.")
            else:
                st.caption("Post/video comparisons must use equivalent reporting windows or content age. Publish date, format, paid/organic dimensions and source URL remain in the evidence table; lifetime totals are not activity for the selected period.")
                numerator_options=[x for x in ["engagements","likes","comments","shares","link_clicks"] if x in scope.metric.unique()]
                denominator_options=[x for x in ["impressions","reach","views","profile_visits"] if x in scope.metric.unique()]
                if numerator_options and denominator_options:
                    n=st.selectbox("Rate numerator",numerator_options)
                    d=st.selectbox("Rate denominator",denominator_options)
                    rate=derived_ratio(scope,n,d,start,end,multiplier=100)
                    st.metric(f"{metric_label(n)} / {metric_label(d).lower()} (%)",fmt(rate.get("value")))
                    provenance(rate)
                    results[n+"_per_"+d]=rate
            with st.expander("Track / release / content comparison",expanded=False):
                comparison_table(frame[frame.account_id==acc],page)
            st.subheader("Compare snapshots")
            other=st.selectbox("Reference snapshot",[None]+snapshots,format_func=lambda s:"Select a snapshot" if s is None else s["name"])
            if other:
                previous=load_observations(str(DB),store.cache_token(),other["id"])
                for col in ["platform","account_id","entity_type","entity_id","dimensions"]:
                    if not previous.empty:
                        previous=previous[previous[col].isin(scope[col])]
                st.caption("Revision comparison: the same historical window in different snapshots. It does not measure new-period performance.")
                for metric in metrics:
                    comparison=compare_metrics(scope,previous,metric,mode="revision",start=start,end=end,previous_start=start,previous_end=end)
                    table([{"metric":metric,"current":comparison["current"]["value"],"reference":comparison["previous"]["value"],"delta":comparison["delta"],"percent_change":comparison["percent_change"],"reason":comparison["reason"]}])
            downloads(scope,results,page)
elif page == "Cross-platform":
    st.write("Explore aligned daily movement. Absolute values keep their native units; an optional index compares relative movement.")
    daily=filtered[filtered.time_grain.eq("daily") & filtered.period_start.eq(filtered.period_end) & ~filtered.measurement_type.isin(["rolling_window_count","cumulative_total","rate"])]
    if daily.empty:
        st.info("Import compatible daily series from at least two sources to explore cross-platform movement.")
    else:
        if daily.platform.nunique() < 2:
            st.info("Only one platform has daily data in this selection. Add social exports for a cross-platform comparison; the controls below can explore two series within this platform.")
        group_cols=["platform","account_id","entity_type","entity_id","metric","dimensions","unit","definition","measurement_type"]
        groups=list(daily.groupby(group_cols,dropna=False,sort=False))
        labels=[" / ".join(str(x) for x in k[:5])+" · "+str(k[5]) for k,_ in groups]
        first_index=next((i for i,(k,_) in enumerate(groups) if k[2] in {"artist","account"} and k[4] in {"streams","views"}),0)
        second_index=next((i for i,(k,_) in enumerate(groups) if k[0]!=groups[first_index][0][0]), next((i for i in range(len(groups)) if i!=first_index),first_index))
        selected_series={}
        for side in ["A","B"]:
            i=st.selectbox(f"Daily series {side}",range(len(groups)),format_func=lambda i:labels[i],key="series"+side,index=first_index if side=="A" else second_index)
            series=daily_series(groups[i][1],groups[i][0][4],start,end)
            selected_series[side]=series
            st.subheader(f"{side} · {labels[i]}")
            draw_series(series,groups[i][0][4],groups[i][0][6])
        if st.checkbox("Show indexed view (common start = 100)"):
            indexed=indexed_series(selected_series)
            st.caption("Both series start at 100 on a common observed, nonzero date. This compares relative change, not audience size. Absolute values remain above and in the download.")
            if indexed.empty or indexed.attrs.get("reason"):
                st.info(str(indexed.attrs.get("reason","No common nonzero reference date.")))
            else:
                st.plotly_chart(px.line(indexed,x="date",y="index",color="series",template="plotly_dark"),width="stretch")
                csv_download("Download indexed and absolute values",indexed,"indexed_series.csv")
        c1,c2=st.columns(2)
        lag=c1.number_input("Lag in days (positive: A leads B)",-90,90,0)
        minimum=c2.number_input("Minimum matched daily observations",3,1000,30)
        result=lag_correlation(selected_series["A"],selected_series["B"],lag=int(lag),min_observations=int(minimum))
        st.write(result)
        st.caption("Exploratory Pearson correlation uses only matched non-missing days. No absent day is filled with zero. Trends, seasonality and other factors can influence correlation; this does not establish causation, conversion, revenue or ROI.")
        st.subheader("Local annotations")
        annotations=pd.DataFrame(store.annotations())
        if not annotations.empty and start and end:
            annotations=annotations[annotations.date.between(start,end)]
        table(annotations)
        st.caption("Edit releases, shows, posts, campaigns and explicit track links in Data & collection → Annotations.")
