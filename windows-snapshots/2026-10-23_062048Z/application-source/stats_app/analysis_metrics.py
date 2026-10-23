"""Conservative interactive calculations over the audited package's table grains."""
from datetime import date, timedelta
import json
import math
import pandas as pd

ADDITIVE_ARTIST = {"daily_streams", "daily_saves", "daily_playlist_adds"}
ADDITIVE_TRACK = {"streams", "saves", "playlist_adds"}


def require_unique(data, keys):
    if data.duplicated(keys).any():
        raise ValueError(f"Ambiguous grain: duplicate {', '.join(keys)} keys. No aggregate produced.")


def selected_days(data, start, end, column="date"):
    return data.loc[data[column].between(str(start), str(end))].copy()


def complete_sum(data, metric, start, end, date_column="date"):
    """A complete daily series only. All-null/absent/incomplete is not zero."""
    start, end = _dates(start, end)
    require_unique(data, [date_column])
    values = selected_days(data, start, end, date_column)
    expected = (end - start).days + 1
    numeric = _observed_values(values, metric)
    observed = int(numeric.notna().sum())
    complete = observed == expected and len(values) == expected and not _partial(values).any()
    return (float(numeric.sum()) if complete else None), observed, expected


def _dates(start, end):
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if start > end:
        raise ValueError("The reporting start must not follow the end.")
    return start, end


def _observed_values(data, metric):
    numeric = pd.to_numeric(data[metric], errors="coerce").copy()
    numeric = numeric.where(numeric.map(lambda value: pd.notna(value) and math.isfinite(float(value))))
    status = metric + "_status" if metric + "_status" in data else "value_status"
    if status in data:
        numeric = numeric.where(data[status].isin({"observed", "observed_zero", "available"}))
    return numeric


def _partial(data):
    if "partial_day" not in data:
        return pd.Series(False, index=data.index)
    # An unknown partial-day flag cannot establish a complete reporting day.
    return ~data.partial_day.astype("string").str.lower().isin({"false", "0"})


def _artist_daily(data, metric):
    required = {"date", "artist_id", "snapshot_class", metric}
    if not required.issubset(data):
        raise ValueError("Artist history is missing required date, artist, retrieval or metric fields.")
    frame = data.copy()
    frame["date"] = pd.to_datetime(frame.date, errors="raise").dt.strftime("%Y-%m-%d")
    if frame.date.isna().any():
        raise ValueError("Every daily observation needs a reporting date.")
    require_unique(frame, ["date"])
    for column in ("artist_id", "snapshot_class", "reporting_timezone"):
        if column in frame and not frame.empty and frame[column].fillna("").astype(str).nunique() != 1:
            raise ValueError("Select one artist, reporting timezone and retrieval vintage.")
    return frame.sort_values("date", kind="stable")


def _source_references(data):
    columns = [column for column in ("date", "source_file", "source_row", "retrieved_at", "snapshot_class") if column in data]
    return json.dumps(json.loads(data[columns].to_json(orient="records")), separators=(",", ":"))


def follower_change(data, start, end, metric="followers_stock"):
    """Net balance change needs the preceding endpoint and selected end, never a sum."""
    start, end = _dates(start, end)
    frame = _artist_daily(data, metric)
    baseline = start - timedelta(days=1)
    baseline_rows = selected_days(frame, baseline, baseline)
    end_rows = selected_days(frame, end, end)

    def endpoint(rows):
        values = _observed_values(rows, metric)
        return float(values.iloc[0]) if len(rows) == 1 and values.notna().all() and not _partial(rows).any() else None

    first, last = endpoint(baseline_rows), endpoint(end_rows)
    complete = first is not None and last is not None
    selected = selected_days(frame, start, end)
    delta = last - first if complete else None
    return dict(start=start.isoformat(), end=end.isoformat(), baseline_date=baseline.isoformat(),
                baseline=first, current=last, net_change=delta,
                change_pct=delta / first * 100 if complete and first > 0 else None,
                status="available" if complete else "unavailable",
                observed_days=int(_observed_values(selected, metric).notna().sum()),
                expected_days=(end - start).days + 1,
                reason="Exact endpoint follower balances; difference is net growth, not gross acquisitions."
                if complete else "A complete observed follower balance is required on both the day before the interval and its final day.",
                limitations="Intermediate dates are not required for an endpoint change. This does not identify acquisitions, losses or person-level retention.",
                source_references=_source_references(pd.concat([baseline_rows, end_rows])))


def daily_periods(data, metric="daily_streams", period="week", endpoint=None):
    """Nonoverlapping calendar weeks or 28-day blocks with explicit edge coverage.

    The endpoint is a reporting date, not a collection timestamp. By default the
    latest retained reporting date anchors 28-day blocks; no platform-lag rule is
    guessed. Calendar weeks end Sunday even when the source stops midweek.
    """
    if metric not in ADDITIVE_ARTIST:
        raise ValueError("Only additive artist daily activity can be totalled.")
    if period not in {"week", "28day"}:
        raise ValueError("Period must be week or 28day.")
    frame = _artist_daily(data, metric)
    columns = ["start", "end", "observed_days", "expected_days", "partial_days", "missing_days",
               "total", "median_daily", "q25_daily", "q75_daily", "status", "previous_start", "previous_end",
               "previous_total", "absolute_change", "change_pct", "source_references"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    low = date.fromisoformat(frame.date.min())
    high = date.fromisoformat(str(endpoint)) if endpoint is not None else date.fromisoformat(frame.date.max())
    if high < low:
        return pd.DataFrame(columns=columns)
    frame = frame.loc[frame.date.le(high.isoformat())]
    length = 7 if period == "week" else 28
    first = low - timedelta(days=low.weekday()) if period == "week" else high - timedelta(days=((high-low).days // 28 + 1) * 28 - 1)
    rows, previous = [], None
    cursor = first
    while cursor <= high:
        end = cursor + timedelta(days=length-1)
        chosen = selected_days(frame, cursor, end)
        total, count, expected = complete_sum(chosen, metric, cursor, end)
        values = _observed_values(chosen, metric).dropna()
        partial = int(_partial(chosen).sum())
        row = dict(start=cursor.isoformat(), end=end.isoformat(), observed_days=count,
                   expected_days=expected, partial_days=partial, missing_days=expected-count, total=total,
                   median_daily=float(values.median()) if len(values) else None,
                   q25_daily=float(values.quantile(.25)) if len(values) else None,
                   q75_daily=float(values.quantile(.75)) if len(values) else None,
                   status="complete" if total is not None else "incomplete",
                   previous_start=previous["start"] if previous else None,
                   previous_end=previous["end"] if previous else None,
                   previous_total=previous["total"] if previous else None,
                   absolute_change=None, change_pct=None, source_references=_source_references(chosen))
        if total is not None and previous is not None and previous["total"] is not None:
            row["absolute_change"] = total - previous["total"]
            row["change_pct"] = row["absolute_change"] / previous["total"] * 100 if previous["total"] > 0 else None
        rows.append(row); previous = row; cursor += timedelta(days=length)
    result = pd.DataFrame(rows, columns=columns)
    result.attrs.update(period=period, reporting_endpoint=high.isoformat(), metric=metric,
                        limitations="Descriptive nonoverlapping periods. Calendar edge periods and missing or partial days cannot produce complete totals. Median and quartiles summarize observed days only.")
    return result


def spike_persistence(data, metric="daily_streams", baseline_days=28, response_days=7, top_n=3):
    """Screen historical highs and describe following activity; never infer impact.

    The outlier fence uses only the preceding complete history. The response
    comparison excludes the spike day and uses equal pre/post windows. A greedy
    largest-excess selection keeps selected event response windows disjoint;
    this is descriptive selection, not an independent-sample design.
    """
    if metric not in ADDITIVE_ARTIST:
        raise ValueError("Only additive artist daily activity supports this screen.")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in (baseline_days, response_days, top_n)):
        raise ValueError("Baseline days, response days and top_n must be positive integers.")
    if baseline_days < response_days:
        raise ValueError("The baseline must cover the entire pre-event comparison window.")
    frame = _artist_daily(data, metric)
    candidates, eligible = [], 0
    for row in frame.itertuples():
        event = date.fromisoformat(row.date)
        baseline_start, baseline_end = event - timedelta(days=baseline_days), event - timedelta(days=1)
        baseline = selected_days(frame, baseline_start, baseline_end)
        baseline_total, _, _ = complete_sum(baseline, metric, baseline_start, baseline_end)
        event_data = selected_days(frame, event, event)
        event_value, _, _ = complete_sum(event_data, metric, event, event)
        if baseline_total is None or event_value is None:
            continue
        eligible += 1
        values = _observed_values(baseline, metric)
        q25, q75 = float(values.quantile(.25)), float(values.quantile(.75))
        fence = q75 + 1.5 * (q75 - q25)
        if event_value <= fence:
            continue
        before_start, before_end = event-timedelta(days=response_days), event-timedelta(days=1)
        after_start, after_end = event+timedelta(days=1), event+timedelta(days=response_days)
        before, bn, _ = complete_sum(frame, metric, before_start, before_end)
        after, an, _ = complete_sum(frame, metric, after_start, after_end)
        candidates.append(dict(event_date=event.isoformat(), event_value=event_value,
            baseline_start=baseline_start.isoformat(), baseline_end=baseline_end.isoformat(),
            baseline_days=baseline_days, baseline_median=float(values.median()), threshold=fence,
            excess_above_threshold=event_value-fence,
            before_start=before_start.isoformat(), before_end=before_end.isoformat(), before_total=before,
            after_start=after_start.isoformat(), after_end=after_end.isoformat(), after_total=after,
            before_observed_days=bn, after_observed_days=an, expected_response_days=response_days,
            absolute_change=after-before if after is not None and before is not None else None,
            change_pct=(after/before-1)*100 if after is not None and before is not None and before > 0 else None,
            persistence_status="complete" if after is not None and before is not None else "unavailable",
            source_references=_source_references(selected_days(frame, baseline_start, after_end))))
    chosen = []
    for candidate in sorted(candidates, key=lambda r: (-r["excess_above_threshold"], r["event_date"])):
        event = date.fromisoformat(candidate["event_date"])
        if any(abs((event-date.fromisoformat(other["event_date"])).days) <= response_days for other in chosen):
            continue
        chosen.append(candidate)
        if len(chosen) == top_n:
            break
    return dict(events=pd.DataFrame(chosen), eligible_days=eligible, candidate_days=len(candidates),
                status="descriptive" if chosen else "no_spike_detected" if eligible else "unavailable",
                reason=f"{len(chosen)} selected high-activity days; incomplete responses remain unavailable." if chosen
                else "No daily high exceeded the historical outlier fence." if eligible else "No complete baseline and event day are available.",
                method=f"Daily value above preceding {baseline_days}-day Q3 + 1.5 × IQR; largest excesses selected with nonoverlapping {response_days}-day response windows.",
                limitations="Descriptive outlier screen, not statistical significance or causal attribution. Selection favors unusually high days and regression to the mean is expected. Releases, promotion and weekday composition may differ. No returning-person retention or durable effect is established.")


def artist_comparison(data, metric, start, end):
    if metric not in ADDITIVE_ARTIST:
        raise ValueError("Only additive artist daily activity can be totalled.")
    require_unique(data, ["artist_id", "date", "snapshot_class"])
    if data.artist_id.nunique() != 1 or data.snapshot_class.nunique() != 1:
        raise ValueError("Select one artist and one retrieval vintage.")
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    length = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=length - 1)
    current, n, expected = complete_sum(data, metric, start, end)
    previous, prior_n, _ = complete_sum(data, metric, previous_start, previous_end)
    change = 100 * (current / previous - 1) if current is not None and previous not in (None, 0) else None
    return dict(current=current, previous=previous, change_pct=change, observed=n, expected=expected,
                previous_observed=prior_n, previous_start=previous_start, previous_end=previous_end)


def catalog_comparison(track, recordings, artist, metric, start, end):
    if metric not in ADDITIVE_TRACK:
        raise ValueError("Track unique listeners and ratios must remain daily observations.")
    require_unique(recordings, ["song_id"])
    data = track.loc[track.metric.eq(metric)].copy()
    require_unique(data, ["song_id", "date", "metric"])
    # A reconciled version may fill gaps from a later capture. Its single,
    # explicit canonical set preserves each row's actual retrieval vintage.
    reconciled = ("canonical_dataset_id" in data and data.canonical_dataset_id.notna().all()
                  and data.canonical_dataset_id.nunique() == 1)
    if data.snapshot_class.nunique() != 1 and not reconciled:
        raise ValueError("Select a single recording retrieval vintage before comparing activity.")
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    prior_end = start - timedelta(days=1)
    prior_start = prior_end - (end-start)
    result = []
    for row in recordings.itertuples():
        subset = data.loc[data.song_id.eq(row.song_id)]
        current, n, expected = complete_sum(subset, "value", start, end)
        previous, pn, _ = complete_sum(subset, "value", prior_start, prior_end)
        result.append(dict(song_id=row.song_id, recording_label=row.recording_label,
                           current=current, previous=previous, observed_days=n, expected_days=expected,
                           previous_observed_days=pn, complete=current is not None,
                           change_pct=100*(current/previous-1) if current is not None and previous not in (None,0) else None))
    result = pd.DataFrame(result)
    artist_total = complete_sum(artist, "daily_"+metric, start, end)[0]
    result["share_of_artist_pct"] = result.current / artist_total * 100 if artist_total else float("nan")
    return result


def exact_period_audience(periods, start, end):
    data = periods.loc[periods.metric.eq("listeners") & periods.start_date.eq(str(start))
                       & periods.end_date.eq(str(end)) & periods.scope.eq("Worldwide")
                       & periods.snapshot_class.eq("original_baseline")]
    return data.iloc[0] if len(data) == 1 and data.iloc[0].current_status == "available" else None


def source_ratio_plot_values(ratios, listeners, keys, value_columns):
    """Only show source ratios with finite positive denominator evidence.

    The second count reports known invalid/nonpositive denominators; the third
    reports missing/nonfinite denominators. Original source readings stay intact.
    """
    require_unique(ratios, keys)
    require_unique(listeners, keys)
    numeric = ratios[keys + value_columns].copy()
    for column in value_columns:
        numeric[column] = pd.to_numeric(numeric[column], errors="coerce")
    denominators = listeners[keys + value_columns].rename(columns={c:c+"__listeners" for c in value_columns})
    joined = numeric.merge(denominators, on=keys, how="left", validate="one_to_one")
    undefined = unknown = 0
    for column in value_columns:
        denominator = pd.to_numeric(joined[column+"__listeners"], errors="coerce")
        present = joined[column].notna()
        finite = denominator.map(lambda value: pd.notna(value) and math.isfinite(float(value)))
        undefined += int((present & finite & denominator.le(0)).sum())
        unknown += int((present & ~finite).sum())
        joined.loc[~finite | denominator.le(0), column] = float("nan")
        joined.loc[~joined[column].map(lambda value: pd.notna(value) and math.isfinite(float(value))), column] = float("nan")
    return joined[keys + value_columns], undefined, unknown
