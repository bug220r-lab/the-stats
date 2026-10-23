"""Refreshable descriptive decisions over a single immutable analysis version.

No source writes, cross-platform attribution, or implicit snapshot unions. The
same functions supply the dashboard and the dated JSON/Markdown report.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
import json
import math

import pandas as pd

from stats_app.analysis_metrics import (
    artist_comparison, catalog_comparison, exact_period_audience, require_unique,
    follower_change, daily_periods, spike_persistence,
)
from stats_app.analysis_social_metrics import prepare_daily, prepare_posts, compare_daily, DAILY_SCOPE

SP = "spotify/cleaned/"
VERSION = "1.0.0"


def records(frame):
    """JSON records with nulls (never NaN/Infinity) and preserved identifier text."""
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def json_safe(value):
    if isinstance(value, pd.DataFrame):
        return records(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if hasattr(value, "item"):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def safe_ratio(numerator, denominator):
    if pd.isna(numerator) or pd.isna(denominator):
        return {"value": None, "status": "unavailable", "reason": "Missing numerator or denominator."}
    a, b = float(numerator), float(denominator)
    if not math.isfinite(a) or not math.isfinite(b) or a < 0 or b <= 0:
        return {"value": None, "status": "unavailable", "reason": "Ratio requires finite nonnegative activity and a positive denominator."}
    return {"value": a / b, "status": "descriptive", "reason": "Compatible observed counts; listening intensity, not returning-person retention."}


def social_series(repo):
    """Keep the explicitly repaired follows series separate from inherited inputs."""
    original = prepare_daily(repo.table("social/account_daily.csv"))
    original["source_reporting_timezone"] = original.reporting_timezone
    # The canonical account_daily contract supplies Pacific dates for source
    # records whose own timezone field is blank. This is not date conversion.
    zones=set(original.reporting_timezone.dropna())
    if not zones.issubset({"Pacific Time", "America/Los_Angeles"}):
        raise ValueError("Canonical social calendar contains an incompatible timezone.")
    original["reporting_timezone"] = "America/Los_Angeles"
    result = [("social/account_daily.csv", original)]
    repair_path = "social/meta_collection/follows_daily_resolved.csv"
    if repair_path in repo.tables:
        repair = prepare_daily(repo.table(repair_path))
        if not repair.empty:
            identities = repair[["platform_selected", "selected_account_id", "metric", "metric_platform_scope"]].drop_duplicates()
            if len(identities) != 1 or identities.iloc[0].platform_selected != "Instagram" or identities.iloc[0].metric != "follows":
                raise ValueError("The approved follows repair must have one Instagram account and scope.")
            # Exclude precisely this identity from the decision view. All original
            # rows and the old statistical testing family remain unchanged.
            match = pd.Series(True, index=original.index)
            for key, value in identities.iloc[0].items():
                match &= original[key].eq(value)
            require_unique(repair,["date"])
            if not set(repair.reporting_timezone.dropna()).issubset({"Pacific Time","America/Los_Angeles"}):
                raise ValueError("Reviewed follows repair has an incompatible native calendar.")
            repair["source_snapshot_class"] = repair.snapshot_class
            repair["source_reporting_timezone"] = repair.reporting_timezone
            repair["snapshot_class"] = "reviewed_follows_repair_canonical_selection"
            repair["reporting_timezone"] = "America/Los_Angeles"
            result = [("social/account_daily.csv", original.loc[~match]) , (repair_path, repair)]
    return result


def coverage_and_social(repo):
    coverage, comparisons = [], []
    for path, data in social_series(repo):
        for key, group in data.groupby(list(DAILY_SCOPE), dropna=False):
            scope = dict(zip(DAILY_SCOPE, key))
            require_unique(group, ["date"])
            start, end = group.date.min(), group.date.max()
            expected = len(pd.date_range(start, end))
            usable = group.loc[~group.partial_day & group.value.notna()]
            latest = usable.date.max() if not usable.empty else None
            coverage.append(dict(**scope, source_table=path, start=start, end=end,
                                 latest_complete_observed_date=latest, calendar_days=expected,
                                 present_dates=len(group), observed_values=int(group.value.notna().sum()),
                                 missing_dates=expected-len(group), unavailable_values=int(group.value.isna().sum()),
                                 partial_dates=int(group.partial_day.sum()), duplicate_keys=0,
                                 source_vintages=group.get("source_snapshot_class",group.snapshot_class).value_counts(dropna=False).to_dict(),
                                 statuses=group.value_status.value_counts(dropna=False).to_dict()))
            if latest:
                window_start = date.fromisoformat(latest)-timedelta(days=27)
                comparison = compare_daily(group, window_start, latest)
                comparisons.append(dict(**scope, source_table=path, current=asdict(comparison["current"]),
                                        previous=asdict(comparison["previous"]), delta=comparison["delta"],
                                        percent_change=comparison["percent_change"], reason=comparison["reason"]))
    return coverage, comparisons


def content_distributions(repo):
    """Same format/scope lifetime descriptions; no equal-age performance claim."""
    path = "social/posts_latest.csv"
    data = prepare_posts(repo.table(path))
    keys = ["platform_selected", "selected_account_id", "metric_platform_scope", "post_type", "author_scope"]
    rows = []
    for key, group in data.groupby(keys, dropna=False):
        for metric in ["views", "reach", "shares", "saves", "comments", "profile_visits"]:
            if metric not in group:
                continue
            values = pd.to_numeric(group[metric], errors="coerce")
            if metric+"_status" in group:
                values = values.where(group[metric+"_status"].isin(["observed", "observed_zero"]))
            observed = values.dropna()
            rows.append(dict(zip(keys, key), metric=metric, posts=len(group), observed=len(observed),
                             missing=int(values.isna().sum()), median=observed.median(), p25=observed.quantile(.25),
                             p75=observed.quantile(.75), maximum=observed.max(),
                             youngest_days=group.post_age_days.min(), oldest_days=group.post_age_days.max(),
                             source_table=path, measurement="lifetime_snapshot",
                             limitation="Unequal post ages/exposure; description within format and scope, not a format effectiveness ranking."))
    return rows


def experiments():
    return [
        dict(decision="Which opening hook merits repeat production?", change="Two hooks for the same Funny Guy excerpt.",
             comparable="Same platform, format, duration band, destination and paid/organic status; record publishing slot.",
             primary_outcome="Unique measured outbound clicks per post in its first 7 days; retain click and reach counts separately.",
             window="7 days per post; 4 weeks of collection.", repetition="At least four matched pairs; randomize hook order within pairs and rotate time slots.",
             worthwhile="Proposed decision threshold: at least 2 additional clicks per post without more production effort; agree before launch.",
             limitations="A proposed practical threshold, not an observed lift or power guarantee. Organic reach is uncontrolled; clicks are not streams."),
        dict(decision="Can post outcomes be compared at equal ages?", change="Capture each new post at 24 hours and 7 days with exact IDs, native scope, metric definitions and timestamps.",
             comparable="Same reporting age, platform and format; keep missing snapshots explicit.",
             primary_outcome="Share of new posts with both validated snapshots.", window="Next 4 weeks.",
             repetition="Capture every post, including low performers; review missing captures weekly.",
             worthwhile="At least 90% complete paired snapshots, a proposed measurement-quality target.",
             limitations="Enables fairer descriptive comparisons; does not itself establish causal content effects."),
        dict(decision="Does a promising excerpt deserve further promotion?", change="Rotate Funny Guy (current demand) and Waste Away (recent momentum) excerpts after the hook test; one tagged destination per post.",
             comparable="Same hook/format, duration band, spend and 7-day observation age; record releases, shows and playlist events.",
             primary_outcome="Measured outbound clicks per post; song streams tracked as a separate exploratory outcome.",
             window="7 days per post plus a separately specified next-7-day song-listening response.",
             repetition="Randomize order within at least four matched pairs across weeks; reserve later pairs to check the pattern.",
             worthwhile="Proposed threshold: 2 additional clicks per post at comparable effort, set before collection.",
             limitations="Song and algorithm exposure differ; artist-day streams cannot be allocated to posts. Low counts may remain inconclusive."),
    ]


def build_report(repo):
    sources = {}
    def read(path):
        frame = repo.table(path)
        sources[path] = {"sha256": frame.attrs["source_sha256"], "rows": len(frame), "csv_record_offset": 2}
        return frame
    daily = read(SP+"artist_daily.csv")
    require_unique(daily, ["artist_id", "date", "snapshot_class"])
    if daily.artist_id.nunique()!=1 or daily.snapshot_class.nunique()!=1 or daily.reporting_timezone.nunique()!=1:
        raise ValueError("Decision report requires one artist, retrieval class and native timezone.")
    observed = daily.loc[daily.value_status.isin(["observed", "observed_zero"]) & daily.daily_streams.notna()]
    observed = observed.loc[observed.daily_streams.map(lambda x: math.isfinite(float(x)) and x>=0)]
    if "partial_day" in observed:
        observed = observed.loc[observed.partial_day.astype(str).str.lower().isin(["false","0"])]
    if observed.empty:
        raise ValueError("No observed artist daily streams; no baseline report can be calculated.")
    end = observed.date.max()
    start = (date.fromisoformat(end)-timedelta(days=27)).isoformat()
    growth = artist_comparison(daily, "daily_streams", start, end)
    growth90 = artist_comparison(daily, "daily_streams", date.fromisoformat(end)-timedelta(days=89), end)
    periods = read(SP+"artist_period_dashboard.csv")
    audience = exact_period_audience(periods, start, end)
    unique = None if audience is None else audience.to_dict()
    ratio = safe_ratio(growth["current"], None if unique is None else unique["current_value"])
    tracks, catalog = read(SP+"track_daily_long.csv"), read(SP+"recordings.csv")
    songs = catalog_comparison(tracks, catalog, daily, "streams", start, end)
    songs = songs.sort_values(["current", "song_id"], ascending=[False, True], na_position="last")
    track_ratios = read(SP+"track_28day_activity_ratios.csv")
    # Periods must match the current decision window; source ratios stay as
    # separate period evidence and cannot silently attach to another interval.
    track_ratios = track_ratios.loc[track_ratios.chart_start_date.eq(start) & track_ratios.chart_end_date.eq(end)]
    track_ratios = track_ratios.copy()
    for index,row in track_ratios.iterrows():
        valid=str(row.capture_valid).lower() in {"true","1"}
        if not valid:
            for column in ["streams","listeners","saves","playlist_adds","streams_per_listener"]:
                track_ratios.loc[index,column]=None
        for numerator,column,multiplier in [("streams","streams_per_period_listener_exact",1),("saves","save_actions_per_100_period_listeners",100),("playlist_adds","playlist_add_actions_per_100_period_listeners",100)]:
            ratio_value=safe_ratio(row[numerator],row.listeners)["value"] if valid else None
            track_ratios.loc[index,column]=ratio_value*multiplier if ratio_value is not None else None
    coverage, social = coverage_and_social(repo)
    content = content_distributions(repo)
    for path in {row["source_table"] for row in coverage+content}:
        read(path)
    countries, cities = read(SP+"audience_top_countries.csv"), read(SP+"audience_top_cities.csv")
    statistical = read("cross_platform/statistical_results.csv")
    q = pd.to_numeric(statistical.q_bh_12_tests, errors="coerce")
    readiness = read("analysis_readiness.csv")
    queue = read(SP+"current_queue.csv") if SP+"current_queue.csv" in repo.tables else pd.DataFrame()
    queue_counts = queue.Status.str.extract(r"^(Complete|Partial|Blocked)")[0].value_counts().to_dict() if not queue.empty else {}
    catalog_sum = songs.current.sum(min_count=len(songs))
    reconciled = pd.notna(catalog_sum) and growth["current"] is not None and abs(float(catalog_sum)-growth["current"])<1e-9
    if not reconciled:
        reconciliation = {"status": "unavailable", "reason": "Incomplete catalog coverage or catalog/artist difference; no exhaustive share claim."}
    else:
        reconciliation = {"status": "passed", "artist_streams": growth["current"], "catalog_streams": float(catalog_sum), "difference": 0}
    findings = []
    def finding(identifier, observed_text, interpretation, next_action, paths):
        findings.append(dict(id=identifier, evidence_basis="descriptive", observed=observed_text,
                             possible_explanation=interpretation, next_action=next_action,
                             source_tables=paths, period=f"{start} through {end}",
                             limitations="Observed counts; no causal effect or independent-observation confidence interval estimated."))
    finding("growth", f"28-day streams {growth['current']} versus {growth['previous']}; change {growth['change_pct']:.2f}%." if growth['change_pct'] is not None else "28-day stream comparison unavailable: incomplete coverage or zero prior denominator.",
            "A short-term change can coexist with a different longer-term trend; inspect both 28-day and 90-day comparisons.",
            "Plan repeatable content tests and monitor complete subsequent weeks.", [SP+"artist_daily.csv"])
    if unique:
        finding("intensity", f"Direct period listeners: {unique['current_value']} versus {unique['previous_value']}. Streams per period listener: {ratio['value']:.3f}." if ratio['value'] is not None else "Listening intensity unavailable.",
                "More streams per listener can reflect concentrated listening; it does not identify returning people.",
                "Track listening intensity alongside distinct audience size.", [SP+"artist_daily.csv", SP+"artist_period_dashboard.csv"])
    if not songs.empty and pd.notna(songs.iloc[0].current):
        top = songs.iloc[0]
        finding("song", f"{top.recording_label}: {top.current:.0f} streams; {top.share_of_artist_pct:.2f}% of artist streams in the matched window.",
                "Current demand supports testing this recording; unequal promotion and release age prevent causal ranking.",
                "Use the leading recording as a test candidate, with a matched alternative and tagged links.", [SP+"track_daily_long.csv",SP+"recordings.csv"])
    hypotheses = [
        {"question":"Do song posts precede unusual song listening?", "outcome":"Song streams per UTC day", "predictor":"Verified song-specific posts", "unit":"Song-day/event", "response":"Next 7 days", "baseline":"Prior matched weekdays", "status":"insufficient evidence", "missing":"Complete verified audio-to-song map, promotion/event calendar and enough separated repeated events; current captions do not prove played audio.", "controls":"Release age, weekday, trend, playlist events and spend needed; currently incomplete."},
        {"question":"Which format produces stronger link activity?", "outcome":"Measured outbound clicks", "predictor":"Format/hook", "unit":"Post at 7 days", "response":"First 7 days", "baseline":"Same-platform matched posts", "status":"insufficient evidence", "missing":"Per-post tagged-link counts and equal-age histories with paid/organic scope.", "controls":"Song, duration, publishing slot, distribution and spend."},
        {"question":"Does social activity coincide with later listening?", "outcome":"Weekly change in Spotify streams", "predictor":"Weekly Meta activity changes", "unit":"Complete nominal week pair", "response":"Same/next week", "baseline":"Prior complete week", "status":"retained exploratory association", "missing":"Broader controls and later held-out observations for confirmation.", "controls":"Differenced weekly log activity; block-bootstrap/circular shift and 12-test BH correction; timezones differ and confounding remains."},
    ]
    for hypothesis in hypotheses:
        hypothesis["reporting_period"] = "2026-01-05 through 2026-10-18 complete nominal weeks" if hypothesis["status"]=="retained exploratory association" else f"Prospective; available daily history overlaps through {end}, but required event/age measurements are missing."
    return json_safe(dict(schema_version=VERSION, analysis_key=getattr(repo,"registered_key",repo.metadata.get("analysis_version","unregistered")),
        label=repo.metadata["label"], artist_id=daily.artist_id.iloc[0], band_name="[REDACTED]",
        baseline_status="Original October 20, 2026 snapshot membership remains unverified; later retrievals preserved separately.",
        period=dict(start=start,end=end,timezone=daily.reporting_timezone.iloc[0],basis="Latest source-observed complete Spotify date; not today's date or a guarantee of later reporting availability."),
        growth28=growth,growth90=growth90,period_unique_listeners=unique,listening_intensity=ratio,
        follower_change=follower_change(daily,start,end),weekly=daily_periods(daily,period="week",endpoint=end),
        nonoverlapping28=daily_periods(daily,period="28day",endpoint=end),spikes=spike_persistence(daily),
        songs=songs,song_ratios=track_ratios,launch_windows=read(SP+"recording_launch_windows.csv"),
        spotify_coverage=dict(start=daily.date.min(),end=daily.date.max(),present_dates=len(daily),
                              missing_dates=len(pd.date_range(daily.date.min(),daily.date.max()))-daily.date.nunique(),
                              streams_unavailable=int(daily.daily_streams.isna().sum()),track_metric_rows=len(tracks)),
        social_coverage=coverage,social_comparisons=social,content_distributions=content,
        countries=countries,cities=cities,readiness=readiness,collection_queue=queue_counts,
        cross_platform=dict(planned=len(statistical),eligible=int(statistical.inference_eligible.fillna(False).sum()),
                            minimum_adjusted_p=q.min(),adjusted_significant=int(q.lt(.05).sum()),
                            input_status="Original retained testing family; new descriptive follows repair does not rerun or alter inference."),
        hypotheses=hypotheses,findings=findings,experiments=experiments(),reconciliation=reconciliation,sources=sources,
        limitations=["Daily Spotify dates are UTC; Meta dates are Pacific. Daily totals cannot be accurately reassigned across zones.",
                     "Rolling listener counts and daily unique listeners are not additive. Platform audiences are never summed into unique fans.",
                     "Lifetime content and top-N geography are snapshots, not exhaustive or equal-age performance comparisons.",
                     "TikTok has no accessible analytical dataset. Original baseline membership, post-to-stream attribution and repeat-person retention remain unavailable.",
                     "Instagram follows repair is explicit daily evidence; these are follow actions, not a net follower-stock series.",
                     "Saved readiness rows describe their original input versions; current social coverage above includes the separately reviewed follows repair."]))


def markdown_report(report):
    p=report["period"]
    lines=["# The Stats™️ — decision report", "",f"Band: {report['band_name']} · Spotify artist `{report['artist_id']}`.",
           f"Analysis: `{report['analysis_key']}`. Reporting window: {p['start']}–{p['end']} ({p['timezone']}).", "",report["baseline_status"],"", "## Findings"]
    for f in report["findings"]:
        lines += ["",f"### {f['id'].capitalize()}",f"**Observed ({f['evidence_basis']}):** {f['observed']}",
                  f"**Interpretation:** {f['possible_explanation']}",f"**Next action:** {f['next_action']}",
                  f"**Limits:** {f['limitations']}","Evidence: "+", ".join(f"`{s}`" for s in f["source_tables"])+"."]
    f=report['follower_change'];g90=report['growth90']
    lines += ["",f"Follower stocks: {f['baseline']} on {f['baseline_date']} → {f['current']} on {f['end']}; net change {f['net_change']}.",
              f"Latest 90-day streams: {g90['current']} versus {g90['previous']} ({g90['change_pct']:.2f}%)." if g90['change_pct'] is not None else "90-day change unavailable.",
              "", "### Current song demand", "", "| Recording | Current streams | Prior streams | Artist share (%) |", "|---|---:|---:|---:|"]
    for row in report['songs']:
        lines.append(f"| {row['recording_label']} | {row['current']} | {row['previous']} | {row['share_of_artist_pct']} |")
    lines += ["", "### Activity after selected high days", "",report['spikes']['method'],report['spikes']['limitations'],
              "", "| High day | Daily streams | Prior 7-day streams | Following 7-day streams | Coverage |", "|---|---:|---:|---:|---|"]
    for row in report['spikes']['events']:
        lines.append(f"| {row['event_date']} | {row['event_value']} | {row['before_total']} | {row['after_total']} | {row['persistence_status']} |")
    lines += ["", "## Coverage and quality", "", f"Spotify: {report['spotify_coverage']}",
              f"Collection queue: {report['collection_queue']}. These are collection tasks, not samples.",
              f"Catalog/artist reconciliation: {report['reconciliation']}", "", "| Platform / metric / scope | Coverage | Missing values / partial dates |", "|---|---|---|"]
    for row in report["social_coverage"]:
        lines.append(f"| {row['platform_selected']} / {row['metric']} / {row['metric_platform_scope']} | {row['start']}–{row['end']} | {row['unavailable_values']} / {row['partial_dates']} |")
    lines += ["", "Full values, source hashes, distributions, geography, launch-age comparisons, weekly coverage and spike windows are in the companion JSON and dashboard.",
              "", "## Statistical limits", "", str(report["cross_platform"])]
    for h in report["hypotheses"]:
        lines += ["", f"- **{h['question']}** {h['status']}. Needed: {h['missing']}"]
    lines += ["", "## Next experiments"]
    for e in report["experiments"]:
        lines += ["", f"### {e['decision']}"]+[f"- **{k.replace('_',' ').capitalize()}:** {v}" for k,v in e.items() if k!="decision"]
    lines += ["", "## Assumptions and unavailable inputs"]+[f"- {x}" for x in report["limitations"]]
    lines += ["", "## Source receipt", "", "CSV record numbers start at 2 (header is record 1); source tables retain their native source row/file fields."]
    lines += [f"- `{p}`: {s['rows']} rows; SHA-256 `{s['sha256']}`." for p,s in report["sources"].items()]
    return "\n".join(lines)+"\n"
