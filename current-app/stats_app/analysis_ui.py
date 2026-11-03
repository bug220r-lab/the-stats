"""Audited analysis views inside the existing Streamlit application."""
from datetime import date, timedelta
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from stats_app.analysis_metrics import artist_comparison, catalog_comparison, complete_sum, selected_days, follower_change
from stats_app.analysis_ui_common import chart, evidence, fmt, download
from stats_app.spotify_audience import RECOVERED_AUDIENCE, exact_retained_period_audience
from stats_app import dashboard_controls as controls

SP = "spotify/cleaned/"


def heading(repo):
    with st.expander("About these saved results"):
        st.caption("Spotify dates are UTC; Meta and YouTube retain Pacific dates. Daily totals cannot be precisely reassigned to a different calendar.")
        st.caption("Original October 20 baseline membership remains unverified. A reporting endpoint does not establish when the source was collected.")
        st.caption(f"Analysis version: {getattr(repo, 'registered_key', repo.metadata.get('analysis_version', 'unregistered'))} · {repo.metadata['label']}")


def render_overview(repo):
    st.subheader("How is the band doing?")
    daily = repo.table(SP+"artist_daily.csv")
    selection = controls.reporting_window(daily, label="Comparison", key="overview", allow_ytd=True)
    if selection is None:
        return
    start, end, choice = selection
    comparisons = repo.table(SP+"artist_comparisons.csv")
    rows = []
    for metric in ["daily_streams", "daily_saves", "daily_playlist_adds"]:
        if choice == "Year to date, matching prior year":
            # The native YTD comparison establishes the prior dates. Its saved
            # totals are not substituted for the selected version's daily facts.
            native = comparisons.loc[comparisons.metric.eq(metric) & comparisons.current_start.eq(str(start))
                                     & comparisons.current_end.eq(str(end))
                                     & comparisons.comparison.astype(str).str.startswith("YTD")]
            if len(native) != 1:
                continue
            prior_start, prior_end = str(native.iloc[0].previous_start), str(native.iloc[0].previous_end)
            value, n, _ = complete_sum(daily, metric, start, end)
            prior, pn, _ = complete_sum(daily, metric, prior_start, prior_end)
            result = dict(current=value, previous=prior, change_pct=(value/prior-1)*100 if value is not None and prior not in (None,0) else None,
                          observed=n, previous_observed=pn, previous_start=prior_start, previous_end=prior_end)
        else:
            result = artist_comparison(daily, metric, start, end)
        rows.append(dict(metric=metric, current_start=str(start), current_end=str(end),
                         previous_start=str(result["previous_start"]), previous_end=str(result["previous_end"]),
                         current=result["current"], previous=result["previous"], percent_change=result["change_pct"],
                         n_current=result["observed"], n_previous=result["previous_observed"]))
    current = pd.DataFrame(rows)
    # Preserve audited naming rather than substituting another comparison.
    if current.empty:
        st.info("This matching comparison is unavailable in the audited package.")
        evidence(repo, SP+"artist_comparisons.csv", comparisons, "overview_unavailable")
        return
    first = current.iloc[0]
    st.subheader("Spotify activity")
    st.caption(f"Compared with {first.previous_start} – {first.previous_end}. Streams, saves and playlist additions are separate actions.")
    growth = current.loc[current.metric.eq("daily_streams")].iloc[0]
    cards = st.columns(3, gap="large")
    cards[0].metric("Streams",fmt(growth.current), f"{float(growth.percent_change):+.1f}%" if pd.notna(growth.percent_change) else None)
    cards[0].caption(f"Prior: {fmt(growth.previous)} · {fmt(growth.n_current)} / {fmt(growth.n_previous)} observed days")
    unique = exact_retained_period_audience(repo, first.current_start, first.current_end,
                                           previous_start=first.previous_start, previous_end=first.previous_end)
    if unique is not None:
        cards[1].metric("Period-unique listeners", fmt(unique.current_value),
                  f"{float(unique.percent_change):+.1f}%" if pd.notna(unique.percent_change) else None)
        prior_basis = "separately recovered exact-period total" if unique.get("previous_source_asset") == RECOVERED_AUDIENCE else "directly reported"
        cards[1].caption(f"Prior: {fmt(unique.previous_value)} · {prior_basis}")
        if not unique.comparison_available:
            cards[1].caption(unique.comparison_reason)
    else:
        cards[1].metric("Period-unique listeners", "Unavailable")
        cards[1].caption("No directly reported audience matches this range. Daily unique listeners cannot be summed.")
    followers = follower_change(daily, first.current_start, first.current_end)
    cards[2].metric("Net Spotify followers", fmt(followers['net_change']))
    cards[2].caption(f"{followers['baseline_date']}: {fmt(followers['baseline'])} → {followers['end']}: {fmt(followers['current'])}")
    secondary = []
    for metric, title in [("daily_saves", "Saves"), ("daily_playlist_adds", "Playlist additions")]:
        row = current.loc[current.metric.eq(metric)].iloc[0]
        delta = f" ({float(row.percent_change):+.1f}%)" if pd.notna(row.percent_change) else ""
        secondary.append(f"**{title}: {fmt(row.current)}**{delta}")
    st.markdown(" · ".join(secondary))
    st.caption(f"Loaded through {daily.date.max()} · saved Spotify reporting coverage, not a live platform update.")
    current_days = selected_days(daily, first.current_start, first.current_end)
    previous_days = selected_days(daily, first.previous_start, first.previous_end)
    shown = pd.concat([previous_days.assign(interval="Comparison"), current_days.assign(interval="Selected")], ignore_index=True)
    fig = px.line(shown,x="date",y="daily_streams",color="interval", color_discrete_map={"Selected":"#EDD264","Comparison":"#979797"},labels={"daily_streams":"Streams","date":"UTC activity date","interval":"Period"})
    fig.update_traces(line_color="#EDD264",connectgaps=False)
    for trace in fig.data:
        trace.line.color = "#EDD264" if trace.name == "Selected" else "#979797"
    fig.update_layout(height=440)
    trend, findings = st.columns([1.8, 1.1], gap="large")
    with trend:
        st.markdown("**Streams through the selected periods**")
        chart(fig,"overview_streams")
    with findings:
        st.markdown("**What the saved evidence shows**")
        from stats_app.growth_ui import render_findings, report_for
        try:
            report = report_for(repo, first.current_start, first.current_end,
                                         previous_start=first.previous_start, previous_end=first.previous_end,
                                         include_details=False)
            render_findings(report["findings"], repo=repo, key="overview-findings", compact=True)
        except (ValueError, KeyError) as exc:
            st.info("Recording diagnostics are unavailable for this source selection: "+str(exc))
    st.subheader("What to inspect next")
    a,b,c = st.columns(3)
    with a:
        controls.jump("Explore songs", "Spotify", key="overview_songs", **{"spotify:view":"Catalog comparison", "spotify:preset":choice if choice != "Year to date, matching prior year" else "Custom", "spotify:dates":(start,end)})
    with b:
        controls.jump("Review social content", "Social", key="overview_social", **{"analysis-social-view":"Collected posts & Stories"})
    with c:
        controls.jump("Explain the Spotify change", "Growth diagnostics", key="overview_diagnostics", **{"growth:preset":"Custom", "growth:dates":(start,end)})
    if choice == "Year to date, matching prior year":
        st.caption("These shortcuts carry the current activity dates. Song and diagnostic views compare them with the preceding equal-length interval, rather than matching prior-year YTD.")
    st.caption("Social and YouTube have their own account scopes and Pacific reporting calendars. No combined audience or causal attribution is calculated.")
    with st.expander("Coverage limitations and supporting records"):
        st.info("TikTok analytics remain unavailable. Six October Story song assignments are deferred. Original October 20 Spotify baseline membership is unverified. These gaps do not prevent compatible Spotify activity comparisons.")
        if unique is not None:
            evidence(repo,SP+"artist_period_dashboard.csv",unique.to_frame().T,"overview_unique","Exact period audience; any incompatible prior audience is withheld.")
            if unique.get("previous_source_asset") == RECOVERED_AUDIENCE:
                recovered = repo.table(RECOVERED_AUDIENCE)
                recovered = recovered.loc[recovered["Period start"].eq(str(first.previous_start)) & recovered["Period end"].eq(str(first.previous_end)) & recovered["Spotify ID"].eq(unique.artist_id)]
                evidence(repo, RECOVERED_AUDIENCE, recovered, "overview_recovered_unique", "Direct prior-period audience recovered separately; original period dashboard values remain preserved.")
        evidence(repo,SP+"artist_daily.csv",shown,"overview_days","Only the two displayed intervals are included; the interval column is added for inspection.")
        st.dataframe(current, hide_index=True, width="stretch")
        download(current,"overview_comparison.csv","overview_comparison_csv")
        st.caption("The saved 12-test exploratory family keeps its original inputs; none survives its multiple-comparison correction. This is not proof that marketing has no effect.")
    heading(repo)


def artist_window(data):
    selected = controls.reporting_window(data, label="Spotify date window", key="spotify")
    return selected[:2] if selected else None


def render_spotify(repo):
    heading(repo)
    options = ["Artist history","Catalog comparison","Release age","Audience & sources"]
    if SP+"source_recovery.csv" in repo.tables:
        options += ["Recovered sources", "Recovery evidence"]
    options += ["Other retained tables"]
    view = controls.radio("Spotify view", options,horizontal=True,key="spotify:view")
    if view in {"Recovered sources", "Recovery evidence"}:
        from stats_app.analysis_recovery_ui import render_sources, render_recovery_evidence
        (render_sources if view == "Recovered sources" else render_recovery_evidence)(repo)
        return
    if view in ("Artist history","Catalog comparison"):
        daily = repo.table(SP+"artist_daily.csv")
        window = artist_window(daily)
        if window is None: return
        start,end=window
        if repo.metadata.get("analysis_version"):
            st.caption(f"{start} – {end} inclusive · UTC · reconciled history. Original observations retain their vintage; recovered values retain later chart-capture timestamps.")
        else:
            st.caption(f"{start} – {end} inclusive · UTC · original_baseline package vintage · retrieved October 22 (date precision)")
        if view == "Artist history":
            metrics = {"Streams":"daily_streams","Saves":"daily_saves","Playlist additions":"daily_playlist_adds",
                       "Daily unique listeners":"daily_listeners","Followers · stock":"followers_stock",
                       "Rolling 28-day listeners":"rolling28_listeners","Rolling active listeners":"rolling28_active_listeners"}
            if "rolling28_super_listeners" in daily:
                metrics["Rolling super listeners"] = "rolling28_super_listeners"
            title=controls.selectbox("Artist metric",list(metrics),key="spotify:metric"); metric=metrics[title]
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
            unique=exact_retained_period_audience(repo,start,end)
            if metric=="daily_listeners":
                st.metric("Exact selected-period unique listeners",fmt(unique.current_value) if unique is not None else "Unavailable")
            chart(px.line(shown,x="date",y=metric,labels={metric:title,"date":"UTC date"}),"artist_history")
            evidence(repo,SP+"artist_daily.csv",shown,"artist_records")
            months_panel = st.expander("Complete calendar months · full retained history", key="spotify:months", on_change="rerun")
            controls.own_keys("spotify:months", "spotify:include-months")
            if months_panel.open:
                with months_panel:
                    monthly=repo.table(SP+"artist_monthly_additive.csv")
                    include=st.checkbox("Include incomplete months",value=False,key="spotify:include-months")
                    month=monthly if include else monthly.loc[monthly.complete_month.fillna(False)]
                    if include: st.warning("October is partial; its total is not a complete-month comparison.")
                    chart(px.bar(month,x="month",y="streams",labels={"streams":"Streams","month":"Calendar month"}),"complete_months")
                    evidence(repo,SP+"artist_monthly_additive.csv",month,"months")
        else:
            tracks=repo.table(SP+"track_daily_long.csv"); recordings=repo.table(SP+"recordings.csv")
            labels=dict(zip(recordings.song_id,recordings.recording_label))
            chosen=controls.multiselect("Recordings · empty means all", list(labels),format_func=labels.get,key="spotify:songs")
            metric=controls.selectbox("Catalog metric",["streams","saves","playlist_adds"],key="spotify:catalog_metric")
            comparisons=catalog_comparison(tracks,recordings,daily,metric,start,end)
            comparisons = comparisons.sort_values(["current", "song_id"], ascending=[False, True], na_position="last")
            previous_end = start - timedelta(days=1)
            previous_start = previous_end - (end-start)
            st.caption(f"Catalog comparison: {start} – {end} versus {previous_start} – {previous_end}, the preceding equal-length interval. This differs from matching prior-year YTD.")
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
            audited_panel = st.expander("Audited latest 28-day comparison", key="spotify:audited-catalog", on_change="rerun")
            controls.own_keys("spotify:audited-catalog")
            if audited_panel.open:
                with audited_panel:
                    evidence(repo,SP+"track_28day_comparison.csv",repo.table(SP+"track_28day_comparison.csv"),"catalog_audited")
    elif view=="Release age":
        data=repo.table(SP+"recording_launch_windows.csv")
        age=controls.selectbox("Days from release",sorted(data.days_since_release.dropna().unique().tolist()),key="spotify:release-age")
        data=data.loc[data.days_since_release.eq(age)]
        st.info("Calendar release ages are comparable lengths, not controlled experiments. Exact release time, audience size, release era and promotion differ. Incomplete launches remain unavailable.")
        complete=data.loc[data.complete.fillna(False)]
        chart(px.bar(complete.sort_values("streams"),x="streams",y="recording_label",orientation="h",labels={"streams":f"Streams in first {age} calendar days","recording_label":"Recording"}),"release_age")
        evidence(repo,SP+"recording_launch_windows.csv",data,"launch")
    elif view=="Audience & sources":
        group=controls.selectbox("Audience/source view",["Stream sources","Audience segments","Age distribution"],key="spotify:audience-view")
        if group=="Stream sources":
            path=SP+"artist_sources_28day.csv"; data=repo.table(path)
            metric=controls.selectbox("Source metric",data.metric.unique().tolist(),key="spotify:source-metric")
            data=data.loc[data.metric.eq(metric)]
            level=controls.selectbox("Source hierarchy",data.level.unique().tolist(),key="spotify:source-hierarchy")
            data=data.loc[data.level.eq(level)]
            st.caption("September 23–October 20 versus August 26–September 22 · UTC · original_baseline retrieval class")
            st.warning("Source parents overlap detailed children. Listener populations overlap categories. Missing editorial readings remain missing; no total across these rows is applied.")
            bars=data.melt(id_vars=["source_category"],value_vars=["current_value","previous_value"],var_name="Interval",value_name="value")
            chart(px.bar(bars,x="value",y="source_category",color="Interval",barmode="group",orientation="h"),"sources")
        elif group=="Audience segments":
            from stats_app.analysis_spotify_audience_ui import render_audience_segments
            render_audience_segments(repo)
            return
        else:
            path=SP+"audience_demographics_age.csv";data=repo.table(path)
            st.warning("Age counts total 1,063 and gender counts 1,064 versus 1,062 period listeners. Source values remain unbalanced. Displayed percentages are rounded.")
            chart(px.bar(data,x="age_range",y="share_pct_displayed",labels={"share_pct_displayed":"Reported share (%)","age_range":"Age"}),"ages")
        evidence(repo,path,data,"audience")
    else:
        candidates=[p for p in repo.tables if p.startswith(SP)]
        path=controls.selectbox("Spotify evidence table",candidates,key="spotify:evidence-table")
        data=repo.table(path)
        if "snapshot_class" in data:
            vintage=controls.selectbox("Retrieval vintage",data.snapshot_class.dropna().unique().tolist(),key="spotify:evidence-vintage")
            data=data.loc[data.snapshot_class.eq(vintage)]
        st.info("Source evidence at its native grain. Unknown windows, lifetime totals, rounded values and overlapping source categories are retained; this table view applies no aggregate.")
        evidence(repo,path,data,"retained")


def render_cross_platform(repo):
    heading(repo)
    controls.jump("Read TikTok and music findings · October 27", "TikTok insights", key="cross-platform:tiktok-insights")
    from stats_app.analysis_content import CONTENT_PATH
    if CONTENT_PATH in repo.tables:
        view = controls.radio("Cross-platform view", ["Posts & Spotify", "Account activity · saved analysis"],
                              key="cross-platform:view", horizontal=True)
        if view == "Posts & Spotify":
            from stats_app.analysis_correlation_ui import render_posts_spotify
            render_posts_spotify(repo)
            return
    render_account_activity(repo)


def render_account_activity(repo):
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
    selected=controls.selectbox("Inspect planned comparison",data.analysis_id.tolist(),format_func=lambda value:data.loc[data.analysis_id.eq(value),"question"].iloc[0],key="associations:comparison")
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


def render_quality(repo, youtube_keys=()):
    heading(repo)
    st.subheader("Coverage and source lineage")
    from stats_app.analysis_coverage import render_current_coverage
    render_current_coverage(repo, youtube_keys, "quality-current")
    if SP+"recovery_coverage.csv" in repo.tables:
        from stats_app.analysis_recovery_ui import recovery_summary
        with st.expander("Spotify recovery and remaining source requests"):
            recovery_summary(repo)
    with st.expander("Historical assessment and readiness · original source state"):
        st.caption("This preserved assessment describes its original inputs. Later repairs and content collections are reflected in Current saved coverage above; historical missing-date and disabled-export notices are not current library totals.")
        st.markdown(repo.text("DATA_QUALITY_ASSESSMENT.md"))
        readiness=repo.table("analysis_readiness.csv")
        evidence(repo,"analysis_readiness.csv",readiness,"readiness")
    candidates=[p for p in repo.tables if any(k in p.lower() for k in ["quality","exclud","quarant","coverage","inventory","cleaning","validation","queue"])]
    path=controls.selectbox("Inspect quality or source table",candidates,key="quality:source-table")
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
