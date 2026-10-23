"""Audited analysis views inside the existing Streamlit application."""
from datetime import date, timedelta
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from stats_app.analysis_metrics import artist_comparison, catalog_comparison, exact_period_audience, selected_days
from stats_app.analysis_ui_common import chart, evidence, fmt, download

SP = "spotify/cleaned/"


def heading(repo):
    st.caption("[REDACTED] · historical Spotify reporting through October 20, 2026 · newer evidence has its own reporting window")
    st.caption("Retrieval vintages remain separate. Spotify dates are UTC; Business Suite dates are Pacific. Ads Manager retains its own source timezone. Daily totals cannot be precisely rebinned.")
    st.caption("The retained original_baseline source label does not verify membership in the original October 20 archive; that membership remains unverified.")
    if repo.metadata.get("analysis_version"):
        st.caption(f"Analysis version: {repo.metadata['analysis_version']} · {repo.metadata['label']}")


def render_overview(repo):
    heading(repo)
    choices = {"Latest 28 days":"28day", "Latest 90 days":"90day", "Latest 7 days":"7day", "Year to date, matching prior year":"YTD2026_vs_2025"}
    choice = st.selectbox("Comparison", list(choices))
    comparisons = repo.table(SP+"artist_comparisons.csv")
    current = comparisons.loc[comparisons.comparison.eq(choices[choice])]
    # Preserve audited naming rather than substituting another comparison.
    if current.empty:
        st.info("This matching comparison is unavailable in the audited package.")
        evidence(repo, SP+"artist_comparisons.csv", comparisons, "overview_unavailable")
        return
    first = current.iloc[0]
    st.subheader("Spotify activity")
    st.caption(f"{first.current_start} – {first.current_end}, compared with {first.previous_start} – {first.previous_end} · original_baseline retrieval class")
    cards = st.columns(4)
    for card, metric, title in zip(cards[:3],["daily_streams","daily_saves","daily_playlist_adds"],["Streams","Saves","Playlist additions"]):
        row = current.loc[current.metric.eq(metric)].iloc[0]
        card.metric(title,fmt(row.current), f"{float(row.percent_change):+.1f}%" if pd.notna(row.percent_change) else None)
        card.caption(f"Prior: {fmt(row.previous)} · {fmt(row.n_current)} / {fmt(row.n_previous)} observed days")
    periods = repo.table(SP+"artist_period_dashboard.csv")
    unique = exact_period_audience(periods, first.current_start, first.current_end)
    if unique is not None:
        cards[3].metric("Period-unique listeners", fmt(unique.current_value),
                  f"{float(unique.percent_change):+.1f}%" if pd.notna(unique.percent_change) else None)
        cards[3].caption(f"Prior: {fmt(unique.previous_value)} · directly reported")
    else:
        st.info("No matching exact period-unique listener reading. Daily listeners are not added to create one.")
    daily = repo.table(SP+"artist_daily.csv")
    shown = selected_days(daily, first.previous_start, first.current_end)
    fig = px.line(shown,x="date",y="daily_streams",labels={"daily_streams":"Streams","date":"UTC date"})
    fig.update_traces(line_color="#EDD264",connectgaps=False)
    fig.update_layout(height=330)
    chart(fig,"overview_streams")
    if unique is not None:
        evidence(repo,SP+"artist_period_dashboard.csv",unique.to_frame().T,"overview_unique","Exact period audience, never a sum of daily listeners.")
    evidence(repo,SP+"artist_daily.csv",shown,"overview_days","Artist-day streams; daily history covers both displayed comparison intervals.")
    evidence(repo,SP+"artist_comparisons.csv",current,"overview_comparison","Audited descriptive comparisons, no causal or statistical-significance claim.")
    st.subheader("What to inspect next")
    st.write("Spotify compares recordings and release ages; Social separates complete daily activity from lifetime content. Cross-platform retains every planned comparison and its uncertainty. Data quality exposes missing and quarantined records.")
    st.info("The saved exploratory analysis found no comparison surviving correction across the 12 planned tests. This is not proof that marketing has no effect.")


def artist_window(data):
    low, high = date.fromisoformat(data.date.min()), date.fromisoformat(data.date.max())
    preset = st.selectbox("Spotify date window", ["Latest 28 days","Latest 90 days","All available","Custom"])
    start = max(low, high-timedelta(days=27 if preset=="Latest 28 days" else 89)) if preset.startswith("Latest") else low
    end = high
    if preset == "Custom":
        chosen = st.date_input("UTC activity dates", (start,end),min_value=low,max_value=high)
        if len(chosen)!=2:
            st.info("Select both dates."); return None
        start,end = chosen
    return start,end


def render_spotify(repo):
    heading(repo)
    options = ["Artist history","Catalog comparison","Release age","Audience & sources"]
    if SP+"source_recovery.csv" in repo.tables:
        options += ["Recovered sources", "Recovery evidence"]
    options += ["Other retained tables"]
    view = st.radio("Spotify view", options,horizontal=True)
    if view in {"Recovered sources", "Recovery evidence"}:
        from stats_app.analysis_recovery_ui import render_sources, render_recovery_evidence
        (render_sources if view == "Recovered sources" else render_recovery_evidence)(repo)
        return
    if view in ("Artist history","Catalog comparison"):
        daily = repo.table(SP+"artist_daily.csv")
        window = artist_window(daily)
        if window is None: return
        start,end=window
        if view == "Catalog comparison" and repo.metadata.get("analysis_version"):
            st.caption(f"{start} – {end} inclusive · UTC · reconciled history. Original observations retain their vintage; recovered values retain later chart-capture timestamps.")
        else:
            st.caption(f"{start} – {end} inclusive · UTC · original_baseline package vintage · retrieved October 22 (date precision)")
        if view == "Artist history":
            metrics = {"Streams":"daily_streams","Saves":"daily_saves","Playlist additions":"daily_playlist_adds",
                       "Daily unique listeners":"daily_listeners","Followers · stock":"followers_stock",
                       "Rolling 28-day listeners":"rolling28_listeners","Rolling active listeners":"rolling28_active_listeners"}
            title=st.selectbox("Artist metric",list(metrics)); metric=metrics[title]
            shown=selected_days(daily,start,end)
            if metric in {"daily_streams","daily_saves","daily_playlist_adds"}:
                stats=artist_comparison(daily,metric,start,end)
                a,b,c=st.columns(3)
                a.metric(title,fmt(stats["current"]))
                b.metric("Previous equal interval",fmt(stats["previous"]))
                c.metric("Change",fmt(stats["change_pct"],1)+"%" if stats["change_pct"] is not None else "Unavailable")
                st.caption(f"Coverage: {stats['observed']} / {stats['expected']} days. Prior: {stats['previous_start']} – {stats['previous_end']} ({stats['previous_observed']} observed days).")
            else:
                st.metric("Latest endpoint",fmt(shown.iloc[-1][metric]) if not shown.empty else "Unavailable")
                st.info("These are daily unique audiences, overlapping windows or follower balances. No period sum is valid.")
            unique=exact_period_audience(repo.table(SP+"artist_period_dashboard.csv"),start,end)
            if metric=="daily_listeners":
                st.metric("Exact selected-period unique listeners",fmt(unique.current_value) if unique is not None else "Unavailable")
            chart(px.line(shown,x="date",y=metric,labels={metric:title,"date":"UTC date"}),"artist_history")
            evidence(repo,SP+"artist_daily.csv",shown,"artist_records")
            monthly=repo.table(SP+"artist_monthly_additive.csv")
            with st.expander("Complete calendar months · full retained history"):
                include=st.checkbox("Include incomplete months",value=False)
                month=monthly if include else monthly.loc[monthly.complete_month.fillna(False)]
                if include: st.warning("October is partial; its total is not a complete-month comparison.")
                chart(px.bar(month,x="month",y="streams",labels={"streams":"Streams","month":"Calendar month"}),"complete_months")
                evidence(repo,SP+"artist_monthly_additive.csv",month,"months")
        else:
            tracks=repo.table(SP+"track_daily_long.csv"); recordings=repo.table(SP+"recordings.csv")
            labels=dict(zip(recordings.song_id,recordings.recording_label))
            chosen=st.multiselect("Recordings · empty means all", list(labels),format_func=labels.get)
            metric=st.selectbox("Catalog metric",["streams","saves","playlist_adds"])
            comparisons=catalog_comparison(tracks,recordings,daily,metric,start,end)
            if chosen: comparisons=comparisons.loc[comparisons.song_id.isin(chosen)]
            complete=comparisons.loc[comparisons.complete.fillna(False)]
            st.caption("Totals require every selected date for each recording. Percent share uses the artist total, not the selected subset. Stable recording IDs prevent duplicate release membership.")
            if len(complete)!=len(comparisons): st.warning(f"{len(comparisons)-len(complete)} selected recording(s) lack complete coverage; their totals remain unavailable.")
            bar=comparisons.melt(id_vars=["song_id","recording_label"],value_vars=["current","previous"],var_name="Interval",value_name="count").dropna(subset=["count"])
            fig=px.bar(bar,y="recording_label",x="count",color="Interval",barmode="group",orientation="h",labels={"count":metric.capitalize(),"recording_label":"Recording"})
            fig.update_layout(height=max(380,len(comparisons)*38),yaxis=dict(autorange="reversed"))
            chart(fig,"catalog")
            st.dataframe(comparisons,hide_index=True,width="stretch",column_config={
                "recording_label":"Recording", "current":"Current", "previous":"Previous",
                "change_pct":st.column_config.NumberColumn("Change (%)",format="%.1f"),
                "share_of_artist_pct":st.column_config.NumberColumn("Artist share (%)",format="%.1f")})
            download(comparisons,"catalog_comparison.csv","catalog_csv")
            filtered=selected_days(tracks,start,end)
            filtered=filtered.loc[filtered.metric.eq(metric)]
            if chosen: filtered=filtered.loc[filtered.song_id.isin(chosen)]
            evidence(repo,SP+"track_daily_long.csv",filtered,"catalog_source")
            with st.expander("Audited latest 28-day comparison"):
                evidence(repo,SP+"track_28day_comparison.csv",repo.table(SP+"track_28day_comparison.csv"),"catalog_audited")
    elif view=="Release age":
        data=repo.table(SP+"recording_launch_windows.csv")
        age=st.selectbox("Days from release",sorted(data.days_since_release.dropna().unique().tolist()))
        data=data.loc[data.days_since_release.eq(age)]
        st.info("Calendar release ages are comparable lengths, not controlled experiments. Exact release time, audience size, release era and promotion differ. Incomplete launches remain unavailable.")
        complete=data.loc[data.complete.fillna(False)]
        chart(px.bar(complete.sort_values("streams"),x="streams",y="recording_label",orientation="h",labels={"streams":f"Streams in first {age} calendar days","recording_label":"Recording"}),"release_age")
        evidence(repo,SP+"recording_launch_windows.csv",data,"launch")
    elif view=="Audience & sources":
        group=st.selectbox("Audience/source view",["Stream sources","Audience segments","Age distribution"])
        if group=="Stream sources":
            path=SP+"artist_sources_28day.csv"; data=repo.table(path)
            metric=st.selectbox("Source metric",data.metric.unique().tolist())
            data=data.loc[data.metric.eq(metric)]
            level=st.selectbox("Source hierarchy",data.level.unique().tolist())
            data=data.loc[data.level.eq(level)]
            st.caption("September 23–October 20 versus August 26–September 22 · UTC · original_baseline retrieval class")
            st.warning("Source parents overlap detailed children. Listener populations overlap categories. Missing editorial readings remain missing; no total across these rows is applied.")
            bars=data.melt(id_vars=["source_category"],value_vars=["current_value","previous_value"],var_name="Interval",value_name="value")
            chart(px.bar(bars,x="value",y="source_category",color="Interval",barmode="group",orientation="h"),"sources")
        elif group=="Audience segments":
            path=SP+"audience_segment_snapshot.csv";data=repo.table(path)
            st.caption("As of October 20 · source-defined past-two-year audience; monthly-active qualification uses the last 28 days. Displayed percentages are rounded.")
            chart(px.bar(data,x="listeners",y="segment",orientation="h"),"segments")
        else:
            path=SP+"audience_demographics_age.csv";data=repo.table(path)
            st.warning("Age counts total 1,063 and gender counts 1,064 versus 1,062 period listeners. Source values remain unbalanced. Displayed percentages are rounded.")
            chart(px.bar(data,x="age_range",y="share_pct_displayed",labels={"share_pct_displayed":"Reported share (%)","age_range":"Age"}),"ages")
        evidence(repo,path,data,"audience")
    else:
        candidates=[p for p in repo.tables if p.startswith(SP)]
        path=st.selectbox("Spotify evidence table",candidates)
        data=repo.table(path)
        if "snapshot_class" in data:
            vintage=st.selectbox("Retrieval vintage",data.snapshot_class.dropna().unique().tolist())
            data=data.loc[data.snapshot_class.eq(vintage)]
        st.info("Source evidence at its native grain. Unknown windows, lifetime totals, rounded values and overlapping source categories are retained; this table view applies no aggregate.")
        evidence(repo,path,data,"retained")


def render_cross_platform(repo):
    heading(repo)
    path="cross_platform/statistical_results.csv";data=repo.table(path)
    st.subheader("Exploratory weekly associations")
    st.warning("None of the 12 planned comparisons survives multiple-testing correction. This does not establish that marketing has no effect. The analysis cannot estimate social-to-streaming conversion or causal lift.")
    st.caption("Saved analysis: January 5–October 18, 2026 complete nominal weeks. Meta uses Pacific dates and Spotify UTC; date boundaries remain different. Filters below inspect one saved analysis; they do not rerun inference.")
    if repo.metadata.get("analysis_version"):
        st.info("These statistical results retain the original cleaned analysis inputs and testing family. The added song/source evidence does not create new independent samples or a new significance test.")
    a,b,c=st.columns(3)
    a.metric("Planned comparisons",len(data));b.metric("Eligible for exploratory uncertainty",int(data.inference_eligible.fillna(False).sum()))
    c.metric("Smallest BH-adjusted p",fmt(pd.to_numeric(data.q_bh_12_tests,errors="coerce").min(),3))
    defined=data.loc[data.rho_change.notna()].copy()
    defined["comparison_label"] = defined.apply(lambda row: f"{row.predictor_platform} {str(row.predictor_metric).replace('_',' ')} · {'next week' if row.lag_weeks else 'same week'}", axis=1)
    fig=go.Figure()
    for eligible,title,symbol in [(True,"With marginal 95% interval","circle"),(False,"No justified interval","diamond-open")]:
        part=defined.loc[defined.inference_eligible.eq(eligible)]
        error=dict(type="data",symmetric=False,array=(part.ci95_high_block4-part.rho_change).tolist(),arrayminus=(part.rho_change-part.ci95_low_block4).tolist()) if eligible else None
        fig.add_trace(go.Scatter(x=part.rho_change,y=part.comparison_label,mode="markers",name=title,marker=dict(symbol=symbol,size=10),error_x=error))
    fig.add_vline(x=0,line_dash="dash");fig.update_layout(height=490,xaxis_title="Spearman correlation of weekly log changes",xaxis=dict(range=[-1,1]))
    chart(fig,"associations")
    st.caption("Intervals are marginal four-week block-bootstrap 95% intervals, not simultaneous and not the inverse of the circular-shift test. An interval excluding zero does not override adjusted p-values. Two undefined coefficients have no chart mark; all 12 remain in the table.")
    columns=["analysis_id","status","inference_eligible","rho_change","ci95_low_block4","ci95_high_block4","q_bh_12_tests","n_weekly_change_pairs","inference_exclusion_reason"]
    st.dataframe(data[columns],hide_index=True,width="stretch",column_config={
        "analysis_id":"Planned comparison", "inference_eligible":"Uncertainty eligible",
        "rho_change":st.column_config.NumberColumn("Correlation",format="%.3f"),
        "ci95_low_block4":st.column_config.NumberColumn("95% lower",format="%.3f"),
        "ci95_high_block4":st.column_config.NumberColumn("95% upper",format="%.3f"),
        "q_bh_12_tests":st.column_config.NumberColumn("BH-adjusted p",format="%.3f")})
    selected=st.selectbox("Inspect planned comparison",data.analysis_id.tolist(),format_func=lambda value:data.loc[data.analysis_id.eq(value),"question"].iloc[0])
    row=data.loc[data.analysis_id.eq(selected)].iloc[0]
    if not row.inference_eligible: st.info(str(row.inference_exclusion_reason))
    pairs=repo.table("cross_platform/joined_week_pairs.csv")
    pairs=pairs.loc[pairs.analysis_id.eq(selected)]
    plot=pairs.dropna(subset=["social_log_change","spotify_log_change"])
    chart(px.scatter(plot,x="social_log_change",y="spotify_log_change",hover_data=["social_week","spotify_week"],labels={"social_log_change":"Social weekly change in log(1 + activity)","spotify_log_change":"Spotify weekly change in log(1 + streams)"}),"weekly_pairs")
    st.caption(f"Lag {row.lag_weeks}: social week t pairs with Spotify week t+{row.lag_weeks}. Reused weeks across tests are not additional independent samples.")
    evidence(repo,"cross_platform/joined_week_pairs.csv",pairs,"pairs")
    evidence(repo,path,data,"statistical_results","All planned cases, sensitivity estimates and limitations remain available.")
    with st.expander("Methods and limitations"):
        st.markdown(repo.text("cross_platform/README.md"))
        st.write(row.uncertainty_caveat);st.write(row.limitations)


def render_quality(repo):
    heading(repo)
    st.subheader("Coverage and source lineage")
    st.info("TikTok data unavailable; access and collection are deferred. This newer package includes valid Stories plus quarantined malformed rows. The earlier archive's disabled-export record remains historical evidence.")
    if SP+"recovery_coverage.csv" in repo.tables:
        from stats_app.analysis_recovery_ui import recovery_summary
        recovery_summary(repo)
    st.markdown(repo.text("DATA_QUALITY_ASSESSMENT.md"))
    readiness=repo.table("analysis_readiness.csv")
    evidence(repo,"analysis_readiness.csv",readiness,"readiness")
    candidates=[p for p in repo.tables if any(k in p.lower() for k in ["quality","exclud","quarant","coverage","inventory","cleaning","validation","queue"])]
    path=st.selectbox("Inspect quality or source table",candidates)
    evidence(repo,path,repo.table(path),"quality_table")
    result_count = len(repo.table('statistical_results.csv'))
    result_title = (f"Retained {result_count} results · original cleaned analysis inputs" if repo.metadata.get("analysis_version")
                    else f"All {result_count} retained analytical results")
    with st.expander(result_title):
        evidence(repo,"statistical_results.csv",repo.table("statistical_results.csv"),"all_results",
                 "Earlier result version; current recovery coverage and descriptive updates are reported above." if repo.metadata.get("analysis_version") else "")
    with st.expander("Collection priorities and measurement plan"):
        st.markdown(repo.text("MEASUREMENT_PLAN.md"))
    with st.expander("Validation and package identity"):
        st.json(repo.metadata)
        st.json(json.loads(repo.text("audit/final_validation.json")))
        st.dataframe(repo.file_catalog(),hide_index=True,width="stretch")
