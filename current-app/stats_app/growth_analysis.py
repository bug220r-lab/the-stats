"""Read-only, coverage-aware growth diagnostics over a selected saved analysis.

These calculations have no filesystem writes or import-time execution. They
generalize the dated October 25 diagnosis; its fixed dates and recommendations
are deliberately not inputs to live findings.
"""
from datetime import date, timedelta
from hashlib import sha256
import json
import math
from typing import NotRequired, TypedDict

import pandas as pd

from stats_app.analysis_metrics import complete_sum, require_unique

SP = "spotify/cleaned/"
METHOD_VERSION = "growth-diagnostics-3"
PARENTS = ("All active sources", "All programmed sources", "Other")
PANEL_KEYS = ("Scope", "Spotify ID", "Population", "Reporting basis", "Window start", "Window end", "Metric")


class FindingResult(TypedDict):
    """Reusable evidence contract shared by Overview and diagnostic views."""
    id: str
    title: str
    observed_statement: str
    interpretation: str
    evidence_basis: str
    source_version: str
    period: dict
    coverage_status: str
    source_refs: list[str]
    recording_ids: list[str]
    limitation: str
    method_version: str
    evidence: list[dict]
    input_fingerprint: str
    source_panel: tuple | None
    comparison_context: NotRequired[list[dict]]


def paired_periods(start, end, previous_start=None, previous_end=None):
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if start > end:
        raise ValueError("The reporting start must not follow the end.")
    if (previous_start is None) != (previous_end is None):
        raise ValueError("Both comparison dates are required.")
    length = (end - start).days + 1
    prior_end = date.fromisoformat(str(previous_end)) if previous_end is not None else start - timedelta(days=1)
    prior_start = date.fromisoformat(str(previous_start)) if previous_start is not None else prior_end - timedelta(days=length - 1)
    if prior_start > prior_end or prior_end >= start:
        raise ValueError("The comparison must be an earlier, nonoverlapping interval.")
    return dict(start=str(start), end=str(end), previous_start=str(prior_start), previous_end=str(prior_end),
                days=length, previous_days=(prior_end-prior_start).days+1, timezone="UTC")


def _change(current, previous):
    return (current-previous)/previous*100 if current is not None and previous is not None and previous > 0 else None


def direction_context(artist, endpoint):
    """Two separately labelled complete comparisons anchored to an endpoint."""
    end = date.fromisoformat(str(endpoint))
    results = []
    for days in (28, 90):
        period = paired_periods(end-timedelta(days=days-1), end)
        current, n, expected = complete_sum(artist,"daily_streams",period["start"],period["end"])
        previous, pn, pe = complete_sum(artist,"daily_streams",period["previous_start"],period["previous_end"])
        change = current-previous if current is not None and previous is not None else None
        results.append(dict(days=days,period=period,current=current,previous=previous,change=change,
                            change_pct=_change(current,previous),observed=n,expected=expected,
                            previous_observed=pn,previous_expected=pe,
                            coverage_status="complete" if change is not None else "unavailable_incomplete_coverage"))
    return results


def recording_contributions(track, recordings, artist, period, metric="streams", song_ids=None):
    """Signed recording accounting; a subset never becomes the artist total."""
    if metric not in {"streams", "saves", "playlist_adds"}:
        raise ValueError("Only additive recording actions can be compared.")
    require_unique(recordings, ["song_id"])
    data = track.loc[track.metric.eq(metric)].copy()
    require_unique(data, ["song_id", "date"])
    if "canonical_dataset_id" in data and data.canonical_dataset_id.notna().all():
        if data.canonical_dataset_id.nunique() != 1:
            raise ValueError("Select one canonical recording dataset.")
    elif "snapshot_class" in data and data.snapshot_class.nunique() > 1:
        raise ValueError("Select one recording retrieval vintage.")
    if "reporting_timezone" in data and not data.reporting_timezone.eq("UTC").all():
        raise ValueError("Recording diagnostics require a single UTC calendar.")
    rows = []
    for recording in recordings.itertuples():
        selected = data.loc[data.song_id.eq(recording.song_id)]
        current, observed, expected = complete_sum(selected, "value", period["start"], period["end"])
        previous, prior_observed, prior_expected = complete_sum(selected, "value", period["previous_start"], period["previous_end"])
        delta = current-previous if current is not None and previous is not None else None
        rows.append(dict(song_id=recording.song_id, recording_label=recording.recording_label,
                         current=current, previous=previous, change=delta, change_pct=_change(current, previous),
                         current_observed_days=observed, current_expected_days=expected,
                         previous_observed_days=prior_observed, previous_expected_days=prior_expected,
                         coverage_status="complete" if delta is not None else "unavailable_incomplete_coverage"))
    result = pd.DataFrame(rows, columns=["song_id", "recording_label", "current", "previous", "change", "change_pct",
                                       "current_observed_days", "current_expected_days", "previous_observed_days", "previous_expected_days", "coverage_status"])
    artist_current, _, _ = complete_sum(artist, "daily_"+metric, period["start"], period["end"])
    artist_previous, _, _ = complete_sum(artist, "daily_"+metric, period["previous_start"], period["previous_end"])
    all_complete = bool(len(result)) and result.coverage_status.eq("complete").all()
    reconciled = all_complete and artist_current is not None and artist_previous is not None and math.isclose(result.current.sum(), artist_current) and math.isclose(result.previous.sum(), artist_previous)
    artist_delta = artist_current-artist_previous if artist_current is not None and artist_previous is not None else None
    result["share_of_artist_net_change_pct"] = result.change/artist_delta*100 if reconciled and artist_delta else None
    result["artist_current_share_pct"] = result.current/artist_current*100 if reconciled and artist_current else None
    result["accounting_status"] = "reconciled" if reconciled else "unavailable_catalog_or_artist_not_reconciled"
    for key in ("start", "end", "previous_start", "previous_end", "timezone"):
        result[key] = period[key]
    if song_ids:
        result = result.loc[result.song_id.isin(song_ids)].copy()
    return result.sort_values(["change", "song_id"], na_position="last", kind="stable").reset_index(drop=True)


def playback_panels(source):
    if not set(PANEL_KEYS).issubset(source):
        return []
    data = source.loc[source.Metric.eq("streams")]
    return [tuple(row[key] for key in PANEL_KEYS) for row in data[list(PANEL_KEYS)].drop_duplicates().sort_values(list(PANEL_KEYS)).to_dict("records")]


def panel_label(panel):
    row = dict(zip(PANEL_KEYS, panel))
    return f"{row['Scope']} · {row['Spotify ID']} · {row['Population']} · {row['Window start']}–{row['Window end']} · {row['Reporting basis']}"


def playback_source_comparison(source, period, panel):
    """One explicit native panel. Exclusive parents are the accounting total."""
    if panel is None:
        return pd.DataFrame(), "No playback-source panel is selected."
    if len(panel) != len(PANEL_KEYS) or not set(PANEL_KEYS+PARENTS).issubset(source):
        return pd.DataFrame(), "Playback-source definitions are unavailable."
    data = source.copy()
    for field, value in zip(PANEL_KEYS, panel):
        data = data.loc[data[field].eq(value)]
    if data.empty:
        return pd.DataFrame(), "This saved analysis does not contain the selected playback-source panel."
    if panel[-1] != "streams":
        return pd.DataFrame(), "Only additive playback-source streams are supported."
    require_unique(data, ["Date"])
    # Column names are retained from the native export, including its text encoding.
    first = list(source.columns).index(PARENTS[0])
    last = list(source.columns).index(PARENTS[-1])
    columns = list(source.columns)[first:last+1]
    parents = list(PARENTS)
    active = columns[1:columns.index(PARENTS[1])]
    programmed = columns[columns.index(PARENTS[1])+1:-1]
    selected = data.loc[data.Date.between(period["previous_start"], period["end"])].copy()
    for column in columns:
        selected[column] = pd.to_numeric(selected[column], errors="coerce")
    values = selected[columns]
    valid = values.notna().all().all() and values.map(lambda value: math.isfinite(float(value)) and value >= 0).all().all()
    reconciled = valid and (not active or selected[active].sum(axis=1, min_count=len(active)).eq(selected[PARENTS[0]]).all()) and (not programmed or selected[programmed].sum(axis=1, min_count=len(programmed)).eq(selected[PARENTS[1]]).all())
    if not reconciled:
        return pd.DataFrame(), "Playback parents and children do not reconcile, or a selected value is missing/invalid; source totals are withheld."
    rows = []
    for column in columns:
        current, n, expected = complete_sum(selected, column, period["start"], period["end"], "Date")
        previous, pn, pe = complete_sum(selected, column, period["previous_start"], period["previous_end"], "Date")
        delta = current-previous if current is not None and previous is not None else None
        rows.append(dict(source=column, hierarchy_role="exclusive_parent" if column in parents else "child_detail",
                         current=current, previous=previous, change=delta, change_pct=_change(current, previous),
                         current_observed_days=n, current_expected_days=expected, previous_observed_days=pn, previous_expected_days=pe,
                         coverage_status="complete" if delta is not None else "unavailable_incomplete_coverage"))
    result = pd.DataFrame(rows)
    totals = result.loc[result.hierarchy_role.eq("exclusive_parent")]
    total_delta = totals.change.sum(min_count=len(parents))
    result["share_of_net_change_pct"] = result.change/total_delta*100 if pd.notna(total_delta) and total_delta else None
    for key, value in zip(PANEL_KEYS, panel):
        result[key] = value
    for key in ("start", "end", "previous_start", "previous_end", "timezone"):
        result[key] = period[key]
    reason = "Exclusive parent totals; child rows explain their parent and must not be added to it."
    if not result.coverage_status.eq("complete").all():
        reason = "The source panel does not completely cover both selected intervals; incomplete totals are unavailable."
    return result, reason


def release_age_means(track, recordings, song_ids=None, bands=((0, 6), (7, 27), (28, 89), (90, 179))):
    """Compare daily means at source-grounded ages; incomplete bands stay absent."""
    require_unique(recordings, ["song_id"])
    data = track.loc[track.metric.eq("streams")].copy()
    require_unique(data, ["song_id", "date"])
    if "reporting_timezone" in data and not data.reporting_timezone.eq("UTC").all():
        raise ValueError("Release ages require UTC recording activity.")
    selected = recordings.loc[recordings.song_id.isin(song_ids)] if song_ids else recordings
    rows = []
    for recording in selected.itertuples():
        try:
            released = date.fromisoformat(str(recording.first_released))
        except (ValueError, AttributeError):
            rows.append(dict(song_id=recording.song_id, recording_label=recording.recording_label,
                             coverage_status="unavailable_release_date", streams=None, streams_per_day=None))
            continue
        for low, high in bands:
            start, end = released+timedelta(days=low), released+timedelta(days=high)
            total, observed, expected = complete_sum(data.loc[data.song_id.eq(recording.song_id)], "value", start, end)
            rows.append(dict(song_id=recording.song_id, recording_label=recording.recording_label,
                             first_released=str(released), age_start=low, age_end=high, age_band=f"{low}–{high}",
                             start=str(start), end=str(end), observed_days=observed, expected_days=expected,
                             streams=total, streams_per_day=total/expected if total is not None else None,
                             coverage_status="complete" if total is not None else "unavailable_incomplete_coverage"))
    return pd.DataFrame(rows)


def build_growth_report(repo, start, end, *, previous_start=None, previous_end=None, song_ids=None, source_panel=None, include_details=True):
    """Fresh source-backed model; fingerprint binds inputs, method and filters."""
    period = paired_periods(start, end, previous_start, previous_end)
    receipts = {}
    def read(name):
        path = SP+name+".csv"
        frame = repo.table(path)
        digest = frame.attrs.get("source_sha256") or sha256(frame.to_csv(index=False).encode()).hexdigest()
        receipts[path] = dict(sha256=digest, rows=len(frame))
        return frame
    artist, track, recordings = read("artist_daily"), read("track_daily_long"), read("recordings")
    for column in ("artist_id", "snapshot_class", "reporting_timezone"):
        if column in artist and artist[column].fillna("").nunique() != 1:
            raise ValueError("Select one artist, reporting timezone and retrieval vintage.")
    if "reporting_timezone" in artist and not artist.reporting_timezone.eq("UTC").all():
        raise ValueError("Artist growth diagnostics require UTC daily observations.")
    current, observed, expected = complete_sum(artist, "daily_streams", period["start"], period["end"])
    previous, pn, pe = complete_sum(artist, "daily_streams", period["previous_start"], period["previous_end"])
    change = current-previous if current is not None and previous is not None else None
    growth = dict(current=current, previous=previous, change=change, change_pct=_change(current, previous), observed=observed, expected=expected, previous_observed=pn, previous_expected=pe)
    contributions = recording_contributions(track, recordings, artist, period, song_ids=song_ids)
    ages = release_age_means(track, recordings, song_ids) if include_details else pd.DataFrame()
    source_data, source_note = pd.DataFrame(), "Playback-source history is unavailable in this saved analysis."
    panels = []
    if include_details and SP+"source_history.csv" in repo.tables:
        source = read("source_history")
        panels = playback_panels(source)
        source_data, source_note = playback_source_comparison(source, period, source_panel)
    version = getattr(repo, "registered_key", repo.metadata.get("analysis_version", "unregistered"))
    for frame, path in ((contributions, SP+"track_daily_long.csv"), (ages, SP+"track_daily_long.csv"), (source_data, SP+"source_history.csv")):
        if not frame.empty:
            frame["analysis_key"] = version
            frame["method_version"] = METHOD_VERSION
            frame["source_table"] = path
            frame["source_sha256"] = receipts[path]["sha256"]
    findings: list[FindingResult] = []
    def add(identifier, title, statement, paths, coverage="complete", limitation="Descriptive accounting; this does not estimate causal marketing effects.", ids=None, finding_period=None):
        findings.append(dict(id=identifier, title=title, observed_statement=statement, evidence_basis="descriptive",
                             interpretation={
                                 "activity":"This is saved activity in the displayed periods; it does not estimate promotion impact.",
                                 "context":"Recent direction can differ from longer history. Overlapping windows are not independent samples.",
                                 "demand":"These complete recording counts describe current demand. Release age and exposure differ.",
                                 "contribution":"This is arithmetic accounting of recording movement, not an explanation of its cause.",
                                 "playback":"Playback routes describe where streams played, not new or returning people or causal playlist effects.",
                             }.get(identifier,"This describes retained observations without a causal interpretation."),
                             source_version=getattr(repo, "registered_key", repo.metadata.get("analysis_version", "unregistered")),
                             period=(finding_period or period).copy(), coverage_status=coverage, source_refs=paths, recording_ids=ids or [],
                             limitation=limitation, method_version=METHOD_VERSION,
                             source_panel=source_panel if identifier == "playback" else None,
                             evidence=[dict(path=path, **receipts[path]) for path in paths if path in receipts]))
    if change is not None:
        direction = "increased" if change > 0 else "decreased" if change < 0 else "were unchanged"
        percentage = f" ({growth['change_pct']:+.1f}%)" if growth["change_pct"] is not None else " (percentage unavailable: zero comparison denominator)"
        add("activity", "The selected activity comparison", f"Streams {direction}: {previous:,.0f} → {current:,.0f}{percentage}.", [SP+"artist_daily.csv"])
    else:
        add("activity", "The comparison needs complete coverage", f"Current: {observed}/{expected} observed days; comparison: {pn}/{pe}. An incomplete period is unavailable, never zero.", [SP+"artist_daily.csv"], "unavailable_incomplete_coverage")
    context = direction_context(artist, period["end"])
    recent, longer = context
    sign = lambda value: (value > 0)-(value < 0)
    if all(item["coverage_status"] == "complete" for item in context) and sign(recent["change"]) != sign(longer["change"]):
        statements = []
        for item in context:
            p = item["period"]
            percent = f" ({item['change_pct']:+.1f}%)" if item["change_pct"] is not None else " (percentage unavailable)"
            statements.append(f"{item['days']} days: {item['previous']:,.0f} → {item['current']:,.0f}{percent}; {p['start']}–{p['end']} versus {p['previous_start']}–{p['previous_end']}")
        add("context", "Recent and longer direction differ", ". ".join(statements)+". These are separate endpoint-anchored comparisons, not the main selection's totals.",
            [SP+"artist_daily.csv"], finding_period=recent["period"])
        findings[-1]["comparison_context"] = context
    complete = contributions.loc[contributions.coverage_status.eq("complete")]
    if not complete.empty:
        top = complete.sort_values(["current", "song_id"], ascending=[False, True]).iloc[0]
        add("demand", "Current recording demand", f"{top.recording_label} has the most streams among the selected complete recordings ({top.current:,.0f}).", [SP+"track_daily_long.csv", SP+"recordings.csv"], ids=[top.song_id])
        movers = complete.loc[complete.change.ne(0)]
        if not movers.empty:
            largest = movers.loc[movers.change.abs().idxmax()]
            add("contribution", "Largest recording movement", f"{largest.recording_label}: {largest.change:+,.0f} streams against the displayed comparison. Gains and declines remain signed.", [SP+"track_daily_long.csv"], ids=[largest.song_id])
    if not source_data.empty:
        parents = source_data.loc[source_data.hierarchy_role.eq("exclusive_parent") & source_data.change.notna()]
        if len(parents) == len(PARENTS):
            largest = parents.loc[parents.change.abs().idxmax()]
            add("playback", "Largest playback-route movement", f"{largest.source}: {largest.change:+,.0f} streams in the selected native {source_panel[0]} / {source_panel[2]} panel.",
                [SP+"source_history.csv"], limitation="Playback routes describe where streams played. They do not measure new-fan acquisition, retention or the effect of publishing.")
    selected_ids = sorted(song_ids) if song_ids else []
    identity = dict(method=METHOD_VERSION, version=getattr(repo, "registered_key", repo.metadata.get("analysis_version", "unregistered")),
                    sources=receipts, period=period, song_ids=selected_ids, source_panel=source_panel, include_details=include_details)
    fingerprint = sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
    for finding in findings:
        finding["input_fingerprint"] = fingerprint
    return dict(period=period, growth=growth, recordings=contributions, release_ages=ages, sources=source_data,
                source_panels=panels, source_note=source_note, findings=findings, source_receipts=receipts,
                fingerprint=fingerprint, method_version=METHOD_VERSION, selected_song_ids=selected_ids, context_comparisons=context)
