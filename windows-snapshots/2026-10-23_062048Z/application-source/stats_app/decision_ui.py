"""Decision report presentation; analytical logic lives in decision_report."""
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from stats_app.analysis_repository import AnalysisRepository
from stats_app.analysis_ui_common import chart, fmt, download
from stats_app.decision_report import build_report, markdown_report


@st.cache_data(show_spinner="Refreshing source-backed decisions…")
def _report(path, modified_ns, size, key):
    repo=AnalysisRepository(path)
    repo.registered_key=key
    return build_report(repo)


def report_for(repo):
    stat=repo.db_path.stat()
    return _report(str(repo.db_path),stat.st_mtime_ns,stat.st_size,getattr(repo,"registered_key",repo.metadata.get("analysis_version","unregistered")))


def render_decision_report(repo, youtube=None):
    report=report_for(repo)
    p=report["period"]
    st.subheader("Decisions from the available evidence")
    st.caption(f"{report['band_name']} · Spotify {report['artist_id']} · {p['start']}–{p['end']} {p['timezone']}")
    st.caption(f"Source version: {report['analysis_key']} · {p['basis']}")
    st.info(report["baseline_status"])
    section=st.radio("Decision view",["Growth & persistence","Songs","Content","Audience","Quality & methods","Experiments"],horizontal=True)
    if section=="Growth & persistence":
        a,b,c=st.columns(3)
        a.metric("28-day streams",fmt(report['growth28']['current']),fmt(report['growth28']['change_pct'],1)+"%" if report['growth28']['change_pct'] is not None else None)
        b.metric("Streams per period listener",fmt(report['listening_intensity']['value'],2))
        b.caption("Streams ÷ directly reported period-unique listeners; listening intensity.")
        f=report["follower_change"]
        c.metric("Net Spotify follower change",fmt(f['net_change']))
        c.caption(f"{f['baseline_date']} stock {fmt(f['baseline'])} → {f['end']} stock {fmt(f['current'])}.")
        for item in report["findings"][:2]:
            st.write(item["observed"])
            st.caption(item["possible_explanation"])
        weeks=pd.DataFrame(report['weekly'])
        st.caption("Nonoverlapping Monday–Sunday UTC weeks. Partial or missing weeks have no total; the trailing calendar week is incomplete.")
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
        st.caption(f"Same {p['start']}–{p['end']} calendar period versus preceding 28 days; stable recording IDs.")
        chart(px.bar(songs,x="current",y="recording_label",orientation="h",labels={"current":"Streams","recording_label":"Recording"}),"decision_songs")
        st.dataframe(songs,hide_index=True,width="stretch")
        ratios=pd.DataFrame(report['song_ratios'])
        st.caption("Direct period-unique listeners and save actions remain separate from daily distinct counts. Save actions per 100 listeners are not a conversion probability.")
        if not ratios.empty:
            st.dataframe(ratios[["recording_label","streams","listeners","streams_per_period_listener_exact","saves","save_actions_per_100_period_listeners","rate_caveat"]],hide_index=True,width="stretch")
        st.caption("Release-age windows below have equal lengths; release era, exposure and promotion differ.")
        launches=pd.DataFrame(report['launch_windows'])
        age=st.selectbox("Launch comparison days",sorted(launches.days_since_release.dropna().unique().tolist()))
        st.dataframe(launches[launches.days_since_release.eq(age)],hide_index=True,width="stretch")
    elif section=="Content":
        st.warning("Lifetime content snapshots have unequal ages and exposure. These distributions describe comparable platform/format groups; they cannot establish first-week results or a winning hook.")
        content=pd.DataFrame(report['content_distributions'])
        platform=st.selectbox("Content platform",content.platform_selected.unique().tolist())
        metric=st.selectbox("Content outcome",content.metric.unique().tolist())
        author=st.selectbox("Content authorship",content.loc[content.platform_selected.eq(platform),'author_scope'].dropna().unique().tolist())
        data=content[content.platform_selected.eq(platform)&content.metric.eq(metric)&content.author_scope.eq(author)]
        chart(px.bar(data,x="post_type",y="median",hover_data=["observed","missing","p25","p75","maximum"],labels={"post_type":"Format","median":f"Median lifetime {metric}"}),"decision_content")
        st.dataframe(data,hide_index=True,width="stretch")
        st.caption("Use Campaigns to record hooks, excerpts, distribution and measured links. The existing Social view retains individual source posts and counts.")
    elif section=="Audience":
        countries=pd.DataFrame(report['countries'])
        st.caption("Spotify source period shown per row. Top locations are partial breakdowns; countries and cities must not be added together.")
        chart(px.bar(countries.head(10),x="country",y="listeners",hover_data=["period_start","period_end","active_listeners","coverage"]),"decision_countries")
        st.dataframe(countries,hide_index=True,width="stretch")
        st.dataframe(pd.DataFrame(report['cities']),hide_index=True,width="stretch")
        st.info("Investigate local engagement and actual event response before committing spend. Separate age, gender and location summaries do not define a joint audience segment.")
    elif section=="Quality & methods":
        st.write("Current descriptive social coverage includes the separately reviewed Instagram follows repair. Earlier cross-platform results keep their original inputs.")
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
        st.download_button("Download decision report",markdown_report(report),"decision_report.md","text/markdown")
        st.download_button("Download structured analysis",json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),"decision_report.json","application/json")
        st.dataframe(pd.DataFrame(report['sources']).T, width="stretch")
