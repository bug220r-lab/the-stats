"""Decision report presentation; analytical logic lives in decision_report."""
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from stats_app.analysis_repository import AnalysisRepository
from stats_app.analysis_ui_common import chart, fmt, download
from stats_app.decision_report import build_report, markdown_report
from stats_app import dashboard_controls as controls


@st.cache_data(show_spinner="Refreshing source-backed decisions…")
def _report(path, modified_ns, size, key, start=None, end=None):
    repo=AnalysisRepository(path)
    repo.registered_key=key
    return build_report(repo, start, end)


def report_for(repo, start=None, end=None):
    stat=repo.db_path.stat()
    return _report(str(repo.db_path),stat.st_mtime_ns,stat.st_size,getattr(repo,"registered_key",repo.metadata.get("analysis_version","unregistered")),str(start) if start else None,str(end) if end else None)


def render_decision_report(repo, youtube=None):
    selection = controls.reporting_window(repo.table("spotify/cleaned/artist_daily.csv"), label="Decision reporting period", key="decision")
    if selection is None:
        return
    start, end, _ = selection
    report=report_for(repo, start, end)
    p=report["period"]
    st.subheader("Decisions from the available evidence")
    st.caption(f"{report['band_name']} · Spotify {report['artist_id']} · {p['start']}–{p['end']} {p['timezone']}")
    growth = report['growth28']
    st.caption(f"Activity comparison: {growth['previous_start']} – {growth['previous_end']}, the preceding {p['days']} days. Content, release-age and audience breakdowns keep their separately labelled source windows.")
    section=controls.radio("Decision view",["Growth & persistence","Songs","Content","Audience","Quality & methods","Experiments"],horizontal=True,key="decision:view")
    if section=="Growth & persistence":
        a,b,c=st.columns(3)
        a.metric(f"{p['days']}-day streams",fmt(report['growth28']['current']),fmt(report['growth28']['change_pct'],1)+"%" if report['growth28']['change_pct'] is not None else None)
        a.caption(f"Previous equal interval: {fmt(growth['previous'])} streams.")
        b.metric("Streams per period listener",fmt(report['listening_intensity']['value'],2))
        b.caption("Streams ÷ directly reported period-unique listeners; listening intensity.")
        if report['period_unique_listeners'] is None:
            b.caption("No direct period-unique listener count matches this date range; daily unique listeners are not summed.")
        f=report["follower_change"]
        c.metric("Net Spotify follower change",fmt(f['net_change']))
        c.caption(f"{f['baseline_date']} stock {fmt(f['baseline'])} → {f['end']} stock {fmt(f['current'])}.")
        for item in report["findings"][:2]:
            st.write(item["observed"])
            st.caption(item["possible_explanation"])
        weeks=pd.DataFrame(report['weekly'])
        st.caption("Nonoverlapping Monday–Sunday UTC weeks inside the selection. Incomplete edge weeks and missing dates have no complete-week total.")
        chart(px.line(weeks.tail(26),x="start",y="total",labels={"start":"Week starting (UTC)","total":"Complete-week streams"}),"decision_weeks")
        st.subheader("After unusually high days")
        st.caption(report['spikes']['method'])
        events=pd.DataFrame(report['spikes']['events'])
        if not events.empty:
            cols=["event_date","event_value","before_start","before_end","before_total","after_start","after_end","after_total","change_pct","persistence_status"]
            st.dataframe(events[cols],hide_index=True,width="stretch")
        else:
            st.info(report['spikes']['reason'])
        st.warning(report['spikes']['limitations'])
        with st.expander("Complete periods and source records"):
            st.dataframe(weeks,hide_index=True,width="stretch")
            download(weeks,"decision_weeks.csv","decision_weeks_download")
            st.dataframe(pd.DataFrame(report['nonoverlapping28']),hide_index=True,width="stretch")
    elif section=="Songs":
        songs=pd.DataFrame(report['songs'])
        st.caption(f"Same {p['start']}–{p['end']} calendar period versus preceding {p['days']} days; stable recording IDs.")
        search = controls.text_input("Search recordings", key="decision_song_search", placeholder="Song title or recording ID")
        if search.strip():
            songs = songs.loc[songs.recording_label.str.contains(search.strip(),case=False,regex=False,na=False) | songs.song_id.str.contains(search.strip(),case=False,regex=False,na=False)]
        songs = songs.sort_values(["current", "song_id"], ascending=[False, True], na_position="last")
        chart(px.bar(songs,x="current",y="recording_label",orientation="h",labels={"current":"Streams","recording_label":"Recording"}),"decision_songs")
        st.dataframe(songs,hide_index=True,width="stretch")
        download(songs,"decision_selected_songs.csv","decision_songs_csv")
        if songs.empty:
            st.info("No recordings match this search. Clear the search to show the catalog.")
        else:
            song_labels = dict(zip(songs.song_id, songs.recording_label))
            selected_song = controls.selectbox("Inspect recording", list(song_labels), format_func=song_labels.get, key="decision:recording")
            controls.jump("Open recording history", "Spotify", key="decision_song_history", **{"spotify:view":"Catalog comparison", "spotify:songs":[selected_song], "spotify:preset":"Custom", "spotify:dates":(start,end)})
        ratios=pd.DataFrame(report['song_ratios'])
        st.caption("Direct period-unique listeners and save actions remain separate from daily distinct counts. Save actions per 100 listeners are not a conversion probability.")
        if not ratios.empty:
            ratios = ratios.loc[ratios.song_id.isin(songs.song_id)]
            st.dataframe(ratios[["recording_label","streams","listeners","streams_per_period_listener_exact","saves","save_actions_per_100_period_listeners","rate_caveat"]],hide_index=True,width="stretch")
        else:
            st.info("Direct recording-level listener ratios are unavailable for the selected period.")
        st.caption("Release-age windows below have equal lengths; release era, exposure and promotion differ.")
        launches=pd.DataFrame(report['launch_windows'])
        age=controls.selectbox("Launch comparison days",sorted(launches.days_since_release.dropna().unique().tolist()),key="decision:launch_age")
        st.dataframe(launches[launches.days_since_release.eq(age) & launches.song_id.isin(songs.song_id)],hide_index=True,width="stretch")
    elif section=="Content":
        content=pd.DataFrame(report['content_distributions'])
        inventory=report.get('content_inventory', {})
        st.caption(f"Retained library: {inventory.get('identities', 0):,} distinct posts & Stories, including {inventory.get('stories', 0):,} Stories. The activity-date filter does not apply to these captures.")
        if inventory.get('conflicting_date_identities') or inventory.get('unknown_date_identities'):
            st.caption(f"Publication dates: {inventory.get('conflicting_date_identities', 0):,} conflicting identities; {inventory.get('unknown_date_identities', 0):,} undated identities. These are retained in the library, with no publication day inferred.")
        st.caption("Each outcome describes one capture-day cohort, measurement scope and author group. Ages and exposure differ; distributions do not establish first-week performance or a winning hook.")
        if content.empty:
            st.info("No retained content identities are available in this analysis version.")
            return
        top=st.columns([1, 1.5, 2])
        with top[0]:
            platform=controls.selectbox("Content platform",content.platform_selected.unique().tolist(),key="decision:content_platform")
        content = content.loc[content.platform_selected.eq(platform)]
        accounts=content.apply(lambda row: f"{row.identity_account_id_type} · {row.identity_account_id}", axis=1)
        with top[1]:
            account=controls.selectbox("Content account",accounts.unique().tolist(),key="decision:content_account")
        content = content.loc[accounts.eq(account)]
        with top[2]:
            scope=controls.selectbox("Content measurement scope",content.metric_platform_scope.unique().tolist(),key="decision:content_scope")
        content = content.loc[content.metric_platform_scope.eq(scope)]
        columns=st.columns(4)
        with columns[0]:
            measurements=content.measurement_type.unique().tolist()
            measurement=controls.selectbox("Content measurement type",measurements,index=measurements.index("lifetime_content_snapshot") if "lifetime_content_snapshot" in measurements else 0,key="decision:content_measurement")
        content = content.loc[content.measurement_type.eq(measurement)]
        with columns[1]:
            cohorts=sorted((value for value in content.capture_cohort.unique() if value != "Unknown capture time"), reverse=True)
            if content.capture_cohort.eq("Unknown capture time").any():
                cohorts.append("Unknown capture time")
            cohort=controls.selectbox("Content capture cohort",cohorts,key="decision:content_cohort")
        content = content.loc[content.capture_cohort.eq(cohort)]
        with columns[2]:
            metric=controls.selectbox("Content outcome",content.metric.unique().tolist(),key="decision:content_metric")
        with columns[3]:
            author=controls.selectbox("Content authorship",content.author_scope.dropna().unique().tolist(),key="decision:content_author")
        data=content[content.metric.eq(metric)&content.author_scope.eq(author)]
        if data.observed.gt(0).any():
            chart(px.bar(data,x="post_type",y="median",hover_data=["observed","missing","p25","p75","maximum"],labels={"post_type":"Format","median":f"Median captured {metric}"}),"decision_content")
        else:
            st.info("This outcome is unavailable for the selected capture group. Missing values remain unavailable.")
        st.dataframe(data,hide_index=True,width="stretch")
        download(data,"decision_content_groups.csv","decision_content_csv")
        st.caption("Use Campaigns to record hooks, excerpts, distribution and measured links. The existing Social view retains individual source posts and counts.")
    elif section=="Audience":
        countries=pd.DataFrame(report['countries'])
        st.caption("Spotify source period shown per row. Top locations are partial breakdowns; countries and cities must not be added together.")
        chart(px.bar(countries.head(10),x="country",y="listeners",hover_data=["period_start","period_end","active_listeners","coverage"]),"decision_countries")
        st.dataframe(countries,hide_index=True,width="stretch")
        st.dataframe(pd.DataFrame(report['cities']),hide_index=True,width="stretch")
        st.info("Investigate local engagement and actual event response before committing spend. Separate age, gender and location summaries do not define a joint audience segment.")
    elif section=="Quality & methods":
        st.info(report["baseline_status"])
        st.caption(f"Source version: {report['analysis_key']} · {p['basis']}")
        if "social/meta_collection/follows_daily_resolved.csv" in repo.tables:
            st.write("This version's descriptive social coverage includes the reviewed Instagram follows repair. Earlier cross-platform results keep their original inputs.")
        else:
            st.write("This saved version predates the Instagram follows repair. Its original missing values and statistical inputs remain intact; select a newer version for repaired follows.")
        st.dataframe(pd.DataFrame(report['social_coverage']),hide_index=True,width="stretch")
        flat=[]
        for row in report['social_comparisons']:
            flat.append({k:v for k,v in row.items() if k not in {'current','previous'}}|{f"{p}_{k}":v for p in ['current','previous'] for k,v in row[p].items()})
        st.dataframe(pd.DataFrame(flat),hide_index=True,width="stretch")
        st.json(report['cross_platform'])
        st.dataframe(pd.DataFrame(report['hypotheses']),hide_index=True,width="stretch")
        for limitation in report['limitations']: st.write("• "+limitation)
        st.caption("YouTube keeps its own account, dates, scope and source checks in YouTube collection; it is never pooled with Spotify or Meta.")
        if youtube is None: st.warning("YouTube is not available to this report session. Check the collection's registered file/access; source audit documents any separately verified ZIP evidence.")
    else:
        for e in report['experiments']:
            st.subheader(e['decision'])
            for k,v in e.items():
                if k!='decision': st.write(f"**{k.replace('_',' ').capitalize()}:** {v}")
    with st.expander("Download report and source receipt"):
        st.caption("The full report uses the activity dates above and includes all recordings. Song-search exports are provided beside the filtered song table. Lifetime content, geography and historical inference keep their own source periods.")
        st.download_button("Download decision report",markdown_report(report),"decision_report.md","text/markdown")
        st.download_button("Download structured analysis",json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),"decision_report.json","application/json")
        st.dataframe(pd.DataFrame(report['sources']).T, width="stretch")
