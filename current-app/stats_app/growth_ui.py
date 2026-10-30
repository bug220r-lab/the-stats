"""Evidence-led growth views; all controls inspect existing saved observations."""
from datetime import date, timedelta
from hashlib import sha256
import io
import json

import pandas as pd
import plotly.express as px
import streamlit as st

from stats_app import dashboard_controls as controls
from stats_app.analysis_ui_common import chart, download, fmt
from stats_app.config import PROJECT_ROOT
from stats_app.growth_analysis import (
    SP, METHOD_VERSION, build_growth_report, paired_periods, panel_label, playback_panels,
)


def _source_identity(repo):
    """Cheap manifest identity plus file change token; cached reads still verify bytes."""
    catalog = repo.file_catalog()
    assets = catalog[["path", "sha256", "row_count"]].to_json(orient="records")
    stat = repo.db_path.stat()
    return (str(repo.db_path), stat.st_size, stat.st_mtime_ns,
            getattr(repo, "registered_key", repo.metadata.get("analysis_version", "unregistered")),
            repo.metadata.get("package_sha256", ""), sha256(assets.encode()).hexdigest(), METHOD_VERSION)


@st.cache_data(show_spinner=False, max_entries=32)
def _cached_report(identity, start, end, previous_start, previous_end, songs, panel, include_details, _repo):
    return build_growth_report(_repo, start, end, previous_start=previous_start, previous_end=previous_end,
                               song_ids=songs, source_panel=panel, include_details=include_details)


def report_for(repo, start, end, *, previous_start=None, previous_end=None, song_ids=None, source_panel=None, include_details=True):
    return _cached_report(_source_identity(repo), str(start), str(end), previous_start, previous_end,
                          tuple(sorted(song_ids or [])), source_panel, include_details, repo)


@st.cache_data(show_spinner=False, max_entries=48)
def _cached_table(identity, path, _repo):
    return _repo.table(path)


@st.cache_data(show_spinner=False, max_entries=48)
def _cached_original(identity, path, _repo):
    return _repo.original_bytes(path)


def _select_section(section):
    st.session_state["selection:growth:section"] = section


def render_findings(findings, *, repo=None, key="growth-findings", compact=False):
    """Each statement keeps its exact evidence scope beside its drilldown."""
    layout_columns = st.columns(2, gap="large") if not compact else None
    for finding_index, finding in enumerate(findings[:3] if compact else findings):
        with (layout_columns[finding_index % 2] if layout_columns else st).container(border=True):
            st.markdown("**"+finding["title"]+"**")
            st.write(finding["observed_statement"])
            period = finding["period"]
            if not compact:
                st.caption(f"{period['start']}–{period['end']} vs {period['previous_start']}–{period['previous_end']} · {period['timezone']} · {finding['coverage_status'].replace('_', ' ')}")
            section = "Playback routes" if finding["id"] == "playback" else "Recordings"
            if compact:
                current_dates = (date.fromisoformat(period["start"]), date.fromisoformat(period["end"]))
                prior_year = (int(period["previous_start"][:4]) == int(period["start"][:4])-1
                              and period["previous_start"][4:] == period["start"][4:]
                              and period["previous_end"][4:] == period["end"][4:])
                basis = "Matching prior-year dates" if prior_year else "Preceding equal interval"
                controls.jump("Open supporting diagnostics", "Growth diagnostics", key=key+":jump:"+finding["id"],
                              **{"growth:preset":"Custom", "growth:dates":current_dates, "growth:comparison":basis, "growth:section":section})
            else:
                st.button("Open supporting section", key=key+":jump:"+finding["id"], on_click=_select_section, args=(section,))
            details = st.expander("Evidence · "+finding["id"], key=key+":"+finding["id"], on_change="rerun")
            controls.own_keys(key+":"+finding["id"])
            if not details.open:
                continue
            with details:
                st.caption("Saved source: "+finding["source_version"])
                for path in finding["source_refs"]:
                    st.code(path, language=None)
                for receipt in finding.get("evidence", []):
                    st.caption(f"SHA-256 {receipt['sha256']} · {receipt['rows']:,} source rows")
                st.caption(finding["limitation"])
                st.caption("Interpretation: "+finding["interpretation"])
                st.caption("Input fingerprint: "+finding["input_fingerprint"])
                st.caption("Method: "+finding["method_version"])
                if repo is not None:
                    identity = _source_identity(repo)
                    for index, path in enumerate(finding["source_refs"]):
                        frame = _cached_table(identity, path, repo)
                        ids = finding.get("recording_ids", [])
                        if ids and "song_id" in frame:
                            frame = frame.loc[frame.song_id.isin(ids)]
                        if "metric" in frame:
                            frame = frame.loc[frame.metric.eq("streams")]
                        if path.endswith("source_history.csv") and finding.get("source_panel"):
                            from stats_app.growth_analysis import PANEL_KEYS
                            for field, value in zip(PANEL_KEYS, finding["source_panel"]):
                                frame = frame.loc[frame[field].eq(value)]
                        date_column = "date" if "date" in frame else "Date" if "Date" in frame else None
                        if date_column:
                            periods = [item["period"] for item in finding.get("comparison_context", [])] or [period]
                            mask = pd.Series(False, index=frame.index)
                            for scope in periods:
                                mask |= frame[date_column].between(scope["start"],scope["end"]) | frame[date_column].between(scope["previous_start"],scope["previous_end"])
                            frame = frame.loc[mask].copy()
                        table_columns = [c for c in ("date","Date","recording_label","song_id","metric","value","daily_streams","source_file","source_row") if c in frame]
                        if path.endswith("source_history.csv"):
                            table_columns = [c for c in ("Date", "All active sources", "All programmed sources", "Other", "Evidence") if c in frame]
                        st.dataframe(frame, hide_index=True, width="stretch", column_order=table_columns or None)
                        download(frame, "finding_"+finding["id"]+"_"+path.split("/")[-1], key+":rows:"+finding["id"]+str(index))
                        st.download_button("Download unchanged source · "+path.split("/")[-1], _cached_original(identity,path,repo), path.split("/")[-1], "text/csv", key=key+":source:"+finding["id"]+str(index))


def diagnostic_window(daily):
    low, high = date.fromisoformat(str(daily.date.min())), date.fromisoformat(str(daily.date.max()))
    choice = controls.selectbox("Diagnostic comparison", ["Latest 13 complete weeks", "Latest 28 days", "Latest 90 days", "Latest 7 days", "Custom"], key="growth:preset")
    if choice == "Latest 13 complete weeks":
        end = high-timedelta(days=(high.weekday()+1) % 7)
        start = end-timedelta(days=90)
    elif choice == "Custom":
        chosen = controls.date_range("Diagnostic UTC dates", low, high, (max(low, high-timedelta(days=27)), high), key="growth:dates")
        if chosen is None:
            return None
        start, end = chosen
    else:
        days = {"Latest 28 days": 28, "Latest 90 days": 90, "Latest 7 days": 7}[choice]
        start, end = high-timedelta(days=days-1), high
    basis = controls.selectbox("Comparison basis", ["Preceding equal interval", "Matching prior-year dates"], key="growth:comparison")
    if basis == "Matching prior-year dates":
        try:
            period = paired_periods(start, end, start.replace(year=start.year-1), end.replace(year=end.year-1))
        except ValueError:
            st.info("These calendar dates have no matching prior-year interval. Select another range or the preceding interval.")
            return None
    else:
        period = paired_periods(start, end)
    st.caption(f"{start:%b %d, %Y}–{end:%b %d, %Y} · UTC · compared with {period['previous_start']}–{period['previous_end']}. Loaded through {high}.")
    return period


def _historical_diagnosis(*, standalone=False):
    details = st.container() if standalone else st.expander("Historical diagnosis · October 25, 2026", key="growth:historical", on_change="rerun")
    if not standalone and not details.open:
        return
    with details:
        base = PROJECT_ROOT/"outputs/spotify_slowdown_20261025"
        try:
            manifest = json.loads((base/"DELIVERY_MANIFEST.json").read_text(encoding="utf-8"))
            entries = {row["path"]: row["sha256"] for row in manifest["files"]}
            paths = ("recordings/recording_contributions.csv", "recordings/receipt.json", "sources/artist_source_comparisons.csv",
                     "recordings/release_age_windows.csv", "apple/apple_windows.csv")
            raw = {path: (base/path).read_bytes() for path in paths}
            if any(sha256(value).hexdigest() != entries.get(path) for path, value in raw.items()):
                raise ValueError("The historical diagnosis no longer matches its delivery manifest.")
            receipt = json.loads(raw[paths[1]])
            frame = pd.read_csv(io.BytesIO(raw[paths[0]]))
            frame = frame.loc[frame.comparison.eq("primary13weeks")]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            st.info("The retained historical diagnosis is unavailable: "+str(exc))
            return
        st.caption("Fixed historical analysis; the controls above do not change this dated evidence.")
        st.write("July 20–October 18, 2026 versus April 20–July 19, 2026 · 13 complete weeks each · UTC.")
        st.caption(f"Source version: {receipt['analysis_key']} · SHA-256 {receipt['database_sha256']}")
        prior, current = frame.streams_prior.sum(), frame.streams_current.sum()
        a, b, c = st.columns(3)
        a.metric("Historical comparison streams", fmt(prior))
        b.metric("Historical selected streams", fmt(current))
        c.metric("Historical change", fmt(current-prior), f"{(current/prior-1)*100:+.1f}%" if prior else None)
        st.markdown("**Recording accounting**")
        st.dataframe(frame[["recording_label", "streams_prior", "streams_current", "streams_delta", "streams_percent_change"]], hide_index=True, width="stretch")
        download(frame, "historical_20261025_recording_contributions.csv", "growth_historical_csv")
        sources = pd.read_csv(io.BytesIO(raw[paths[2]]))
        sources = sources.loc[sources.comparison.eq("13weeks")]
        st.markdown("**Playback-source accounting**")
        st.caption("Artist / Worldwide native source panel. Parent totals are exclusive; children are details and must not be added to their parents.")
        st.dataframe(sources[["source", "hierarchy_role", "prior", "current", "change", "change_pct"]], hide_index=True, width="stretch")
        download(sources, "historical_20261025_playback_sources.csv", "growth_historical_sources_csv")
        ages = pd.read_csv(io.BytesIO(raw[paths[3]]))
        st.markdown("**Release-age evidence**")
        st.caption("Source-specific first-release ages; daily means compare unequal age bands. Incomplete launch histories stay unavailable.")
        st.dataframe(ages[["recording_label", "age_start", "age_end", "start", "end", "streams_per_day", "complete"]], hide_index=True, width="stretch")
        download(ages, "historical_20261025_release_age.csv", "growth_historical_ages_csv")
        apple = pd.read_csv(io.BytesIO(raw[paths[4]]))
        apple = apple.loc[apple.metric.eq("plays") & apple.window.eq("primary13wk")]
        st.markdown("**Apple Music cross-check**")
        st.caption("Apple daily Plays in the same UTC periods. These are separate platform volumes; title-only comparisons do not establish recording equivalence.")
        st.dataframe(apple[["entity_name", "entity_type", "prior_start", "prior_end", "current_start", "current_end", "prior", "current", "pct_change"]], hide_index=True, width="stretch")
        download(apple, "historical_20261025_apple_plays.csv", "growth_historical_apple_csv")
        st.caption("Descriptive accounting. This is retained history, not a current song recommendation or a causal effect.")


def render_saved_diagnosis(repo=None):
    """A separately routed dated receipt, never affected by live filter state."""
    st.subheader("Saved diagnosis · October 25, 2026")
    st.caption("This page preserves the original source-pinned comparison. Use Growth diagnostics to calculate a different version or reporting period.")
    _historical_diagnosis(standalone=True)


@st.cache_data(show_spinner=False, max_entries=8)
def _content_for(identity, _repo):
    from stats_app.analysis_content import load_content_observations
    return load_content_observations(_repo)


def _nearby_social(repo, period, identity):
    from stats_app.analysis_content import content_identity_inventory, conflicting_publication_identities, select_content_observations
    st.subheader("Nearby social evidence")
    st.caption("Retained publication calendar labels provide context. Meta's native calendar and Spotify UTC dates are not rebinned into a shared day; proximity does not identify a causal effect or verified played audio.")
    data = _content_for(identity, repo)
    if data.empty:
        st.info("No retained content observations are available in this analysis version.")
        return
    mode = controls.radio("Nearby publication window", ["Selected calendar labels", "Seven days around selected endpoint"], horizontal=True, key="growth:nearby-window")
    start, end = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
    if mode == "Seven days around selected endpoint":
        start, end = end-timedelta(days=7), end+timedelta(days=7)
    conflicts = conflicting_publication_identities(data)
    latest = select_content_observations(data, "latest")
    selected = latest.loc[latest.publication_date.between(str(start), str(end)) & ~latest.identity_key.isin(conflicts)].copy()
    inventory = content_identity_inventory(selected, data)
    query = controls.text_input("Find nearby content", key="growth:nearby-query", placeholder="Caption, post ID or link")
    if query.strip() and not inventory.empty:
        matches = inventory[["description","post_id","permalink"]].fillna("").astype(str).apply(lambda column:column.str.contains(query.strip(), case=False, regex=False)).any(axis=1)
        inventory = inventory.loc[matches].copy()
    st.caption(f"Publication labels {start}–{end} · {len(inventory):,} retained identities match. Unknown and conflicting publication dates are excluded from placement; they remain available in Social.")
    if inventory.empty:
        st.info("No retained content matches this context. This does not establish zero publishing.")
    else:
        st.dataframe(inventory, hide_index=True, width="stretch", column_order=["platform_selected","post_type","publication_dates","description","permalink"],
                     column_config={"permalink":st.column_config.LinkColumn("Open original post",display_text="Open")})
        download(inventory, "growth_nearby_content.csv", "growth_nearby_csv")
    controls.jump("Open collected posts and Stories", "Social", key="growth:content-library", **{"analysis-social-view":"Collected posts & Stories"})
    controls.jump("Inspect publishing around increases", "Cross-platform", key="growth:nearby-spikes", **{"cross-platform:view":"Posts & Spotify", "spikes:period":"Custom", "spikes:dates":(date.fromisoformat(period["start"]),date.fromisoformat(period["end"]))})


def render_growth_diagnostics(repo):
    st.subheader("What explains the Spotify change?")
    st.caption("Trace the selected change through recordings, playback routes and release age. Nearby publishing provides timing context; it does not establish attribution.")
    identity = _source_identity(repo)
    daily = _cached_table(identity, SP+"artist_daily.csv", repo)
    period = diagnostic_window(daily)
    if period is None:
        return
    catalog = _cached_table(identity, SP+"recordings.csv", repo)
    labels = dict(zip(catalog.song_id, catalog.recording_label))
    songs = controls.multiselect("Diagnostic recordings · empty means all", list(labels), key="growth:songs", format_func=labels.get)
    source_panel = None
    if SP+"source_history.csv" in repo.tables:
        panels = playback_panels(_cached_table(identity, SP+"source_history.csv", repo))
        if panels:
            compatible = [i for i, panel in enumerate(panels) if panel[0] == "artist" and panel[2] == "Worldwide" and panel[4] <= period["previous_start"] and panel[5] >= period["end"]]
            with st.expander("Playback-source scope", expanded=False):
                source_panel = controls.selectbox("Native playback panel", panels, index=compatible[0] if compatible else 0,
                                                  key="growth:source-panel", format_func=panel_label)
    try:
        report = report_for(repo, period["start"], period["end"], previous_start=period["previous_start"], previous_end=period["previous_end"], song_ids=songs, source_panel=source_panel)
    except (ValueError, KeyError) as exc:
        st.warning("This diagnostic selection cannot be calculated: "+str(exc))
        return
    st.caption(f"Recording filter: {len(songs) if songs else len(catalog)} selected. The artist comparison retains the full artist scope.")
    growth = report["growth"]
    a, b, c = st.columns(3)
    a.metric("Selected artist streams", fmt(growth["current"]))
    b.metric("Comparison artist streams", fmt(growth["previous"]))
    c.metric("Artist stream change", fmt(growth["change"]), f"{growth['change_pct']:+.1f}%" if growth["change_pct"] is not None else None)
    render_findings(report["findings"], repo=repo)
    rows = report["recordings"]
    section = controls.radio("Diagnostic detail", ["Recordings", "Playback routes", "Release age", "Nearby social"], horizontal=True, key="growth:section")
    if section == "Recordings":
        st.subheader("Recording contributions")
        rows = report["recordings"]
        available = rows.loc[rows.change.notna()]
        if not available.empty:
            fig = px.bar(available, x="change", y="recording_label", orientation="h", color=available.change.ge(0).map({True:"Increase", False:"Decrease"}),
                         color_discrete_map={"Increase":"#6FD6AE", "Decrease":"#EF9B9B"}, labels={"change":"Change in streams", "recording_label":"Recording", "color":"Direction"})
            fig.update_layout(height=max(320, min(650, len(available)*30+90)))
            chart(fig, "growth_recordings_chart")
        else:
            st.info("No selected recording has complete activity in both intervals.")
        st.caption("Signed gains and declines reconcile to the artist only when all recording and artist totals are complete. Shares of a net change can exceed 100% when gains offset declines.")
        st.dataframe(rows, hide_index=True, width="stretch", column_order=["recording_label", "current", "previous", "change", "change_pct", "coverage_status"], column_config={
            "recording_label":"Recording", "current":st.column_config.NumberColumn("Selected streams", format="%,d"),
            "previous":st.column_config.NumberColumn("Comparison streams", format="%,d"),
            "change":st.column_config.NumberColumn("Stream change", format="%+d"),
            "share_of_artist_net_change_pct":st.column_config.NumberColumn("Share of artist net change (%)", format="%.1f"),
        })
        download(rows, "growth_recording_contributions.csv", "growth_recordings_csv")
        selected_song = controls.selectbox("Inspect diagnostic recording", rows.song_id.tolist(), format_func=labels.get, key="growth:inspect-song")
        left, right = st.columns(2)
        with left:
            if selected_song is not None:
                controls.jump("Open recording evidence", "Spotify", key="growth:recording-jump", **{"spotify:view":"Catalog comparison", "spotify:songs":[selected_song], "spotify:preset":"Custom", "spotify:dates":(date.fromisoformat(period["start"]), date.fromisoformat(period["end"]))})
        with right:
            controls.jump("Inspect publishing around increases", "Cross-platform", key="growth:publishing-jump", **{"cross-platform:view":"Posts & Spotify", "spikes:period":"Custom", "spikes:dates":(date.fromisoformat(period["start"]), date.fromisoformat(period["end"]))})
        st.caption("Publishing inspection retains source-native calendar labels and dates. Timing alignment does not establish that a post caused streams.")
    elif section == "Playback routes":
        st.subheader("Playback routes")
        st.caption(report["source_note"])
        source_rows = report["sources"]
        if not source_rows.empty:
            parents = source_rows.loc[source_rows.hierarchy_role.eq("exclusive_parent")]
            if parents.change.notna().any():
                chart(px.bar(parents, x="source", y="change", labels={"source":"Exclusive playback parent", "change":"Change in streams"}), "growth_source_chart")
            st.dataframe(source_rows, hide_index=True, width="stretch", column_order=["source", "hierarchy_role", "previous", "current", "change", "change_pct", "coverage_status"])
            download(source_rows, "growth_playback_sources.csv", "growth_sources_csv")
        else:
            st.info(report["source_note"])
    elif section == "Release age":
        st.subheader("Release age")
        st.caption("Full retained history at each recording's first-release age. These source-specific launch windows do not follow the activity-date filter. Daily means make unequal age bands comparable; they do not remove calendar or promotion differences.")
        ages = report["release_ages"]
        age_ids = controls.multiselect("Release-age comparison recordings · empty means all", rows.song_id.tolist(),
                                      default=rows.sort_values("current", ascending=False, na_position="last").song_id.head(3).tolist(),
                                      key="growth:age-songs", format_func=labels.get)
        if age_ids:
            ages = ages.loc[ages.song_id.isin(age_ids)].copy()
        complete = ages.loc[ages.coverage_status.eq("complete")]
        if not complete.empty:
            chart(px.line(complete, x="age_band", y="streams_per_day", color="recording_label", markers=True,
                          labels={"age_band":"Days since first release", "streams_per_day":"Streams per observed day", "recording_label":"Recording"}), "growth_release_age_chart")
        st.dataframe(ages, hide_index=True, width="stretch", column_order=["recording_label", "age_band", "start", "end", "streams_per_day", "observed_days", "expected_days", "coverage_status"])
        download(ages, "growth_release_age_means.csv", "growth_release_ages_csv")
    else:
        _nearby_social(repo, period, identity)
    with st.expander("Calculation receipt and coverage", expanded=False):
        st.caption(f"Fingerprint: {report['fingerprint']} · {report['method_version']}")
        st.caption("Every finding was calculated from the selected saved version and displayed scope. Missing observations are never filled with zero. Playback routes are not measured acquisition or retention.")
        st.dataframe(pd.DataFrame(report["source_receipts"]).T, width="stretch")
        st.download_button("Download findings and source receipt · JSON", json.dumps({key:report[key] for key in ("period", "growth", "findings", "source_receipts", "fingerprint", "method_version", "selected_song_ids")}, indent=2, default=str), "growth_findings.json", "application/json", key="growth_findings_json")
    _historical_diagnosis()
