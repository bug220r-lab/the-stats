"""Conservative calculations shared by cards, charts, tables and exports.

Observations remain platform native. A result with ``value is None`` is an
unavailable KPI, not zero. ``partial_value`` is evidence for a coverage message
and must never be rendered as a complete-window KPI.
"""
from __future__ import annotations

import json
import math
from typing import Any, Mapping

import numpy as np
import pandas as pd


def _spec(definition, measurement_type="period_count", unit="count", denominator=None):
    return {
        "definition": definition,
        "measurement_type": measurement_type,
        "unit": unit,
        "aggregation": "sum_disjoint_complete_periods" if measurement_type == "period_count" else "never_sum",
        "denominator": denominator,
        "comparison": "same platform, account, entity, dimensions, definition, unit, measurement type and equivalent reporting windows",
    }


METRICS = {
    "streams": _spec("Platform-reported streams in the reporting window; use the supplied platform counting definition."),
    "listeners": _spec("Distinct listeners within the reported window; daily audiences are not additive.", "distinct_audience_count"),
    "monthly_listeners": _spec("Distinct listeners in the platform's rolling monthly window; not selected-period listeners.", "rolling_window_count"),
    "monthly_active_listeners": _spec("Source-reported active listeners in the platform's rolling window; retain the source's active-listener definition.", "rolling_window_count"),
    "super_listeners": _spec("Source-reported super listeners in the platform's rolling window; retain the source's qualifying listening threshold.", "rolling_window_count"),
    "followers": _spec("Follower balance observed as of the source date; not new followers during a period.", "point_in_time_count"),
    "new_followers": _spec("New followers reported during the specified reporting window."),
    "content_follows": _spec("Source-reported follows attributed to this content over its lifetime as captured; not account follower balance or follows acquired during a selected reporting period.", "cumulative_total"),
    "saves": _spec("Platform-reported save actions during the window; not necessarily unique people."),
    "playlist_adds": _spec("Platform-reported playlist additions during the reporting window."),
    "views": _spec("Platform-defined views during the reporting window; view thresholds vary by platform."),
    "video_views": _spec("Platform-defined video views during the reporting window; view thresholds vary by platform."),
    "video_views_3s": _spec("Source-reported Facebook 3-second video views during the reporting window under the native counting definition; repeat views may be included."),
    "video_views_1m": _spec("Source-reported Facebook 1-minute video views during the reporting window under the native counting definition; repeat views may be included."),
    "video_views_3s_boosted": _spec("Source-reported boosted Facebook 3-second video views during the reporting window; a paid breakdown, not extra activity to add to total video views."),
    "video_views_3s_organic": _spec("Source-reported organic Facebook 3-second video views during the reporting window; a breakdown, not extra activity to add to total video views."),
    "video_viewers_3s": _spec("Source-reported distinct Facebook viewers meeting the native 3-second video-view definition in the reporting window; never sum distinct viewers across dates or content.", "distinct_audience_count"),
    "video_viewers_1m": _spec("Source-reported distinct Facebook viewers meeting the native 1-minute video-view definition in the reporting window; never sum distinct viewers across dates or content.", "distinct_audience_count"),
    "viewers": _spec("Source-reported distinct Meta viewers within the reporting window under the native audience definition; never sum viewers across dates, content or platforms.", "distinct_audience_count"),
    "reach": _spec("Distinct accounts or people reached in the source reporting window and population.", "distinct_audience_count"),
    "impressions": _spec("Platform-reported content displays during the reporting window, including repeat displays."),
    "likes": _spec("Platform-reported like actions during the reporting window."),
    "comments": _spec("Platform-reported comments during the reporting window."),
    "shares": _spec("Platform-reported share actions during the reporting window."),
    "watch_time": _spec("Total watch duration in the source reporting window; use an explicitly supplied duration unit.", unit="seconds"),
    "profile_visits": _spec("Platform-reported profile visits during the reporting window; not necessarily distinct visitors."),
    "link_clicks": _spec("Platform-reported link clicks in the reporting window under the source click definition."),
    "engagements": _spec("Source-defined engagement actions in the reporting window; retain the included action types in the definition."),
    "content_interactions": _spec("Source-reported Meta content interactions during the reporting window; retain the source's included action types and do not add their breakdown to the interaction total."),
    "unique_user_engagements": _spec("Source-reported distinct Facebook users who engaged during the daily reporting window; not engagement actions, and never sum users across dates or categories.", "distinct_audience_count"),
    "unique_negative_feedback_users": _spec("Source-reported distinct Facebook users who gave negative feedback during the daily reporting window; not feedback actions, and never sum users across dates or feedback categories.", "distinct_audience_count"),
    "negative_feedback_total": _spec("Source-reported total Facebook negative-feedback actions during the daily reporting window; includes the reported feedback breakdown, so never add the total to its categories."),
    "negative_feedback_hide_all": _spec("Source-reported Facebook hide-all negative-feedback actions during the daily reporting window; a breakdown of total negative feedback, not additional activity to add to that total."),
    "negative_feedback_hide": _spec("Source-reported Facebook hide negative-feedback actions during the daily reporting window; a breakdown of total negative feedback, not additional activity to add to that total."),
    "negative_feedback_report_spam": _spec("Source-reported Facebook report-spam negative-feedback actions during the daily reporting window; a breakdown of total negative feedback, not additional activity to add to that total."),
    "negative_feedback_unlike_page": _spec("Source-reported Facebook unlike-page negative-feedback actions during the daily reporting window; a breakdown of total negative feedback, not additional activity to add to that total."),
    "negative_feedback_click_x": _spec("Source-reported Facebook click-X negative-feedback actions during the daily reporting window; a breakdown of total negative feedback, not additional activity to add to that total."),
    "spend": _spec("Advertising spend in the source reporting window; retain currency and attribution dimensions.", unit="currency"),
    "engagement_rate": _spec("Source-reported engagement rate; an explicit numerator, denominator and unit are required.", "rate", "percent", "source_defined"),
    "streams_per_listener": _spec("Stream events divided by distinct listeners in the identical reporting window; not a conversion rate.", "rate", "ratio", "listeners"),
    "saves_per_listener": _spec("Save actions divided by distinct listeners in the identical reporting window; not unique-person conversion.", "rate", "ratio", "listeners"),
}

TYPE_ALIASES = {
    "period count": "period_count", "distinct audience count": "distinct_audience_count",
    "distinct_count": "distinct_audience_count", "cumulative total": "cumulative_total",
    "point-in-time count": "point_in_time_count", "point_in_time": "point_in_time_count",
    "rolling_window": "rolling_window_count", "rolling": "rolling_window_count",
}
SCOPE_COLUMNS = ("platform", "account_id", "entity_type", "entity_id", "dimensions")
SOURCE_COLUMNS = ("source_filename", "source_file", "filename", "source_sheet", "worksheet", "sheet_name",
                  "source_row", "source_ref", "evidence_ref", "evidence_reference", "source_references", "import_id", "file_hash", "file_sha256",
                  "source_url", "captured_at", "imported_at", "source_timezone", "snapshot_id", "snapshot_name")
UNAVAILABLE_STATUSES = {"missing", "suppressed", "unavailable", "invalid", "rejected", "ambiguous", "conflict", "unverified"}


def _clean(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value.item() if hasattr(value, "item") else value


def _dimensions(value):
    if _clean(value) in (None, ""):
        return "{}"
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    try:
        decoded = json.loads(str(value))
        if not isinstance(decoded, dict):
            return "INVALID_DIMENSIONS:" + str(value)
        return json.dumps(decoded, sort_keys=True, separators=(",", ":"))
    except (ValueError, TypeError):
        return "INVALID_DIMENSIONS:" + str(value)


def _date(value):
    value = _clean(value)
    if value is None or value == "":
        return None
    try:
        # Preserve a source's date bucket; do not convert it between timezones.
        parsed = pd.Timestamp(value)
        if pd.isna(parsed):
            return None
        return pd.Timestamp(parsed.date())
    except (ValueError, TypeError):
        return None


def _iso(value):
    parsed = _date(value)
    return parsed.date().isoformat() if parsed is not None else None


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    for col in ("metric", "platform", "account_id", "account_name", "entity_type", "entity_id", "entity_name", "snapshot_id", "snapshot_name"):
        if col not in data:
            data[col] = None
    if "dimensions" not in data:
        data["dimensions"] = "{}"
    data["dimensions"] = data["dimensions"].map(_dimensions)
    for col in ("period_start", "period_end"):
        if col not in data:
            data[col] = None
        data[col] = pd.to_datetime(data[col].map(_date))
    for col in ("definition", "unit", "measurement_type"):
        if col not in data:
            data[col] = data["metric"].map(lambda metric: METRICS.get(metric, {}).get(col))
    data["measurement_type"] = data["measurement_type"].map(lambda v: TYPE_ALIASES.get(str(v).strip().lower(), str(v).strip().lower()) if _clean(v) else None)
    if "value" not in data:
        data["value"] = np.nan
    data["value"] = pd.to_numeric(data["value"], errors="coerce").replace([np.inf, -np.inf], np.nan)
    if "status" in data:
        bad = data["status"].fillna("").astype(str).str.lower().isin(UNAVAILABLE_STATUSES)
        data.loc[bad, "value"] = np.nan
    return data


def filter_observations(df, start=None, end=None, platforms=None, accounts=None, entity_type=None):
    """Filter by intersecting reporting windows without changing source dates.

    Aggregation later requires fully contained windows. ``accounts`` matches
    stable account IDs, not display names. Snapshot/entity selection is explicit
    at the caller; calculations reject mixed selections.
    """
    data = df.copy()
    if data.empty:
        return data
    if platforms is not None:
        values = [platforms] if isinstance(platforms, str) else platforms
        data = data[data["platform"].isin(values)]
    if accounts is not None:
        values = [accounts] if isinstance(accounts, str) else accounts
        data = data[data["account_id"].isin(values)]
    if entity_type is not None:
        values = [entity_type] if isinstance(entity_type, str) else entity_type
        data = data[data["entity_type"].isin(values)]
    starts = data.get("period_start", pd.Series(None, index=data.index)).map(_date)
    ends = data.get("period_end", pd.Series(None, index=data.index)).map(_date)
    if start is not None:
        data = data[ends >= _date(start)]
        starts = starts.loc[data.index]
    if end is not None:
        data = data[starts <= _date(end)]
    return data.copy()


def lifetime_content_observations(df, published_start=None, published_end=None, include_unknown_publication=True):
    """Select source-reported lifetime content without inventing a metric window.

    Publication-date filters select content, never the dates on which activity
    occurred. Raw values, capture dates, missing cutoffs and provenance remain
    intact. This function does not aggregate or rank content performance.
    """
    if df.empty or not {"entity_type", "time_grain"}.issubset(df.columns):
        return df.iloc[:0].copy()
    data = df[df["entity_type"].isin({"post", "video"}) & df["time_grain"].fillna("").str.lower().eq("lifetime")].copy()
    if published_start is None and published_end is None:
        return data
    dates = pd.to_datetime(data.get("published_at", pd.Series(None, index=data.index)).map(_date))
    selected = pd.Series(True, index=data.index)
    if published_start is not None:
        bound = _date(published_start)
        if bound is None:
            raise ValueError("A valid content publication start date is required.")
        selected &= dates.ge(bound)
    if published_end is not None:
        bound = _date(published_end)
        if bound is None:
            raise ValueError("A valid content publication end date is required.")
        selected &= dates.le(bound)
    if include_unknown_publication:
        selected |= dates.isna()
    return data[selected].copy()


def _source_records(data):
    records = []
    seen = set()
    for _, row in data.iterrows():
        record = {col: _clean(row[col]) for col in SOURCE_COLUMNS if col in row and _clean(row[col]) is not None}
        if record:
            key = json.dumps(record, sort_keys=True, default=str)
            if key not in seen:
                records.append(record)
                seen.add(key)
    return records


def _one(data, col):
    values = data[col].map(lambda v: "" if _clean(v) is None else str(v)).unique()
    return values[0] if len(values) == 1 else None


def _scope_problem(data, *, include_snapshot=True):
    columns = list(SCOPE_COLUMNS) + ["definition", "unit", "measurement_type"]
    if include_snapshot:
        columns.append("snapshot_id")
    for column in columns:
        if _one(data, column) is None:
            return f"Select one {column.replace('_', ' ')}; mixed populations or definitions cannot be combined."
    for col in ("platform", "account_id", "entity_type", "entity_id", "definition", "unit", "measurement_type"):
        if not _one(data, col):
            return f"Missing {col.replace('_', ' ')} prevents a verified calculation."
    if data["dimensions"].str.startswith("INVALID_DIMENSIONS:").any():
        return "Invalid dimensions JSON prevents a verified population comparison."
    if _one(data, "measurement_type") not in {"period_count", "distinct_audience_count", "point_in_time_count", "rolling_window_count", "cumulative_total", "rate"}:
        return "Unknown measurement type prevents a verified aggregation."
    # Date-only buckets in different source zones are different populations of time.
    if "source_timezone" in data and _one(data, "source_timezone") is None:
        return "Source timezones differ or are partly unknown; daily buckets cannot be realigned."
    return None


def _base(data, metric, start, end):
    return {
        "metric": metric, "value": None, "partial_value": None, "reason": None,
        "unit": _one(data, "unit") if not data.empty else METRICS.get(metric, {}).get("unit"),
        "definition": _one(data, "definition") if not data.empty else METRICS.get(metric, {}).get("definition"),
        "measurement_type": _one(data, "measurement_type") if not data.empty else METRICS.get(metric, {}).get("measurement_type"),
        "period_start": _iso(start), "period_end": _iso(end), "sources": _source_records(data),
        "snapshot": _one(data, "snapshot_id") if not data.empty else None,
        "snapshot_name": _one(data, "snapshot_name") if not data.empty else None,
        "scope": {col: _one(data, col) for col in SCOPE_COLUMNS} if not data.empty else {},
        "source_timezone": _one(data, "source_timezone") if "source_timezone" in data and not data.empty else None,
        "coverage": {"complete": False, "expected_days": None, "observed_days": 0, "missing_days": [], "used_rows": 0},
    }


def _unique_periods(data):
    """Return equivalent duplicate periods once, or refuse conflicting versions."""
    for _, group in data.groupby(["period_start", "period_end"], dropna=False):
        values = group["value"].drop_duplicates()
        if len(values) > 1:
            return None, "Conflicting observations for the same reporting window; select an active version in Data."
    return data.drop_duplicates(["period_start", "period_end", "value"]), None


def aggregate_metric(df, metric, start=None, end=None):
    """Calculate one native KPI for exactly one population and snapshot.

    An exact-window observation takes precedence over constituent rows. Without
    one, only nonoverlapping period counts covering every requested day can be
    summed. Distinct audiences, rolling windows, lifetime totals and reported
    rates require their own exact observation. Follower balances use the latest
    reported point and expose its actual date.
    """
    data = _prepare(df[df["metric"] == metric] if "metric" in df else df)
    first = _date(start) if start is not None else (data["period_start"].min() if not data.empty else None)
    last = _date(end) if end is not None else (data["period_end"].max() if not data.empty else None)
    if data.empty:
        result = _base(data, metric, first, last)
        result["reason"] = "No observations for this metric and selection."
        return result
    if first is None or last is None or pd.isna(first) or pd.isna(last) or first > last:
        result = _base(data, metric, first, last)
        result["reason"] = "A valid reporting window is required."
        return result
    # Intersect before checking scope, so unrelated periods do not invalidate a selection.
    data = data[(data["period_end"] >= first) & (data["period_start"] <= last)]
    result = _base(data, metric, first, last)
    problem = _scope_problem(data) if not data.empty else "No observations intersect this reporting window."
    if problem:
        result["reason"] = problem
        return result
    if (data["period_start"] > data["period_end"]).any():
        result["reason"] = "An observation has an inverted reporting window."
        return result
    expected = pd.date_range(first, last, freq="D")
    result["coverage"]["expected_days"] = len(expected)
    measurement = result["measurement_type"]
    if metric == "spend" and result["unit"] == "currency" and not json.loads(_one(data, "dimensions")).get("currency"):
        result["reason"] = "Advertising spend requires an explicit currency unit or a currency dimension."
        return result
    if measurement == "rate" and result["definition"] == METRICS.get("engagement_rate", {}).get("definition") and not json.loads(_one(data, "dimensions")).get("denominator"):
        result["reason"] = "A reported engagement rate requires its explicit denominator in the source definition or dimensions."
        return result
    exact = data[(data["period_start"] == first) & (data["period_end"] == last)]
    chosen = exact
    if measurement == "point_in_time_count" and exact.empty:
        points = data[(data["period_start"] == data["period_end"]) & (data["period_end"] <= last)]
        if not points.empty:
            latest = points["period_end"].max()
            chosen = points[points["period_end"] == latest]
            result["period_start"] = result["period_end"] = _iso(latest)
            result["coverage"]["expected_days"] = 1
    if not chosen.empty:
        unique, problem = _unique_periods(chosen)
        if problem:
            result["reason"] = problem
            return result
        value = unique.iloc[0]["value"]
        result["sources"] = _source_records(chosen)
        if pd.isna(value):
            result["reason"] = "The exact reporting-window observation is missing, suppressed, or unverified."
            return result
        result["value"] = float(value)
        result["coverage"].update(complete=True, observed_days=result["coverage"]["expected_days"], used_rows=1,
                                  method="latest_reported_balance" if measurement == "point_in_time_count" else "exact_reported_window")
        return result
    if measurement != "period_count":
        result["reason"] = f"{measurement.replace('_', ' ').capitalize()} values cannot be summed; an exact reporting-window observation is required."
        return result
    contained = data[(data["period_start"] >= first) & (data["period_end"] <= last)]
    # A complete daily export is also an unambiguous partition. Coarser source
    # summaries are alternate observations, never extra activity. Keep the
    # exact-window rule above authoritative when both representations exist.
    daily = contained[contained["period_start"] == contained["period_end"]]
    daily_unique, daily_problem = _unique_periods(daily)
    if not daily_problem and len(daily_unique) == len(expected) and daily_unique["value"].notna().all():
        result["value"] = float(daily_unique["value"].sum())
        result["sources"] = _source_records(daily)
        result["coverage"].update(complete=True, observed_days=len(expected), used_rows=len(daily_unique),
                                  method="sum_complete_daily_counts", ignored_coarser_rows=len(contained) - len(daily))
        return result
    unique, problem = _unique_periods(contained)
    if problem:
        result["reason"] = problem
        return result
    unique = unique.sort_values(["period_start", "period_end"])
    previous_end = None
    covered = set()
    total = 0.0
    for _, row in unique.iterrows():
        if previous_end is not None and row["period_start"] <= previous_end:
            result["reason"] = "Overlapping reporting windows cannot be added; select one complete authoritative window or disjoint counts."
            return result
        previous_end = row["period_end"]
        if pd.notna(row["value"]):
            covered.update(pd.date_range(row["period_start"], row["period_end"], freq="D"))
            total += float(row["value"])
    missing = [day.date().isoformat() for day in expected if day not in covered]
    result["sources"] = _source_records(contained)
    result["coverage"].update(observed_days=len(covered), missing_days=missing, used_rows=len(unique), method="sum_disjoint_period_counts")
    if missing:
        result["partial_value"] = total if covered else None
        result["reason"] = f"Incomplete reporting window: {len(covered)} of {len(expected)} days available; partial counts are not a complete-period total."
        return result
    result["value"] = total
    result["coverage"]["complete"] = True
    return result


def derived_ratio(df, numerator, denominator, start=None, end=None, multiplier=1.0):
    """Recompute an explicitly labelled ratio from compatible native totals."""
    top = aggregate_metric(df, numerator, start, end)
    bottom = aggregate_metric(df, denominator, start, end)
    result = dict(top)
    result.update(metric=f"{numerator}_per_{denominator}", value=None, partial_value=None, measurement_type="rate",
                  numerator=top, denominator=bottom, unit="percent" if multiplier == 100 else "ratio",
                  definition=f"{numerator} divided by {denominator} for the same reporting window and population" + (" × 100." if multiplier == 100 else ".") + " Actions per audience member are not unique-person conversion rates.")
    if top["value"] is None or bottom["value"] is None:
        result["reason"] = "Compatible numerator and denominator totals are required. " + (top["reason"] or bottom["reason"] or "")
        return result
    for key in ("scope", "snapshot", "source_timezone", "period_start", "period_end"):
        if top[key] != bottom[key]:
            result["reason"] = f"Numerator and denominator have different {key.replace('_', ' ')}."
            return result
    if not top["snapshot"]:
        result["reason"] = "Snapshot identity is required for a derived ratio."
        return result
    if top["measurement_type"] not in {"period_count", "distinct_audience_count"} or bottom["measurement_type"] not in {"period_count", "distinct_audience_count"}:
        result["reason"] = "Derived ratios require compatible period counts or exact-window distinct audiences."
        return result
    if bottom["value"] <= 0:
        result["reason"] = "The denominator is zero or negative; the ratio is unavailable."
        return result
    if not math.isfinite(float(multiplier)):
        result["reason"] = "A finite ratio multiplier is required."
        return result
    result["value"] = top["value"] / bottom["value"] * multiplier
    result["reason"] = None
    result["sources"] = top["sources"] + [s for s in bottom["sources"] if s not in top["sources"]]
    return result


def daily_series(df, metric, start=None, end=None):
    """Return observed daily buckets only; never spread a period total over days."""
    data = _prepare(df[df["metric"] == metric] if "metric" in df else df)
    first = _date(start) if start is not None else (data["period_start"].min() if not data.empty else None)
    last = _date(end) if end is not None else (data["period_end"].max() if not data.empty else None)
    if first is None or last is None or pd.isna(first) or pd.isna(last) or first > last:
        result = pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"), "value": pd.Series(dtype=float)})
        result.attrs["reason"] = "No valid daily reporting window."
        return result
    result = pd.DataFrame({"date": pd.date_range(first, last), "value": np.nan})
    data = data[(data["period_start"] >= first) & (data["period_end"] <= last)]
    problem = _scope_problem(data) if not data.empty else "No daily observations for this selection."
    result.attrs.update(metric=metric, unit=_one(data, "unit") if not data.empty else None,
                        source_timezone=_one(data, "source_timezone") if "source_timezone" in data and not data.empty else None,
                        daily=True, reason=problem)
    if problem:
        return result
    daily = data[data["period_start"] == data["period_end"]]
    if "time_grain" in daily:
        daily = daily[daily["time_grain"].fillna("").str.lower().isin({"day", "daily", "date"})]
    # A point balance may be plotted on its reported date, but a rolling window
    # whose extraction only supplied an as-of date is not a daily audience count.
    if _one(data, "measurement_type") in {"rolling_window_count", "cumulative_total", "rate"}:
        result.attrs["reason"] = "This measurement is not a daily activity series; use its reported windows or as-of observations."
        return result
    unique, problem = _unique_periods(daily)
    if problem:
        result.attrs["reason"] = problem
        return result
    mapping = unique.set_index("period_start")["value"]
    result["value"] = result["date"].map(mapping)
    result.attrs["reason"] = None if result["value"].notna().any() else "No observed daily buckets; period totals are not interpolated."
    return result


def asof_series(df, metric, start=None, end=None):
    """Plot native balances/rolling/lifetime observations at reported end dates.

    The original reporting windows remain in the output. These observations are
    explicitly not a daily activity series and are ineligible for daily lag
    correlation. No rolling-window dates are reconstructed from an as-of point.
    """
    data = _prepare(df[df["metric"] == metric] if "metric" in df else df)
    first = _date(start) if start is not None else (data["period_end"].min() if not data.empty else None)
    last = _date(end) if end is not None else (data["period_end"].max() if not data.empty else None)
    output = pd.DataFrame(columns=["date", "value", "period_start", "period_end", "measurement_type"])
    output.attrs.update(daily=False, series_kind="as_of_observation", metric=metric,
                        reason=None, note="Reported as-of observations; rolling/lifetime/balance values are not daily activity and are never added.")
    if first is None or last is None or pd.isna(first) or pd.isna(last) or first > last:
        output.attrs["reason"] = "No valid as-of observation window."
        return output
    data = data[data["period_end"].between(first, last)]
    problem = _scope_problem(data) if not data.empty else "No as-of observations for this selection."
    if problem:
        output.attrs["reason"] = problem
        return output
    measurement = _one(data, "measurement_type")
    if measurement not in {"point_in_time_count", "rolling_window_count", "cumulative_total"}:
        output.attrs["reason"] = "As-of trends require reported balances, rolling windows or lifetime observations."
        return output
    for _, group in data.groupby("period_end"):
        if group[["period_start", "value"]].drop_duplicates().shape[0] > 1:
            output.attrs["reason"] = "Multiple conflicting windows or values share an as-of date; select one source window."
            return output
    data = data.drop_duplicates(["period_start", "period_end", "value"]).set_index("period_end", drop=False)
    grid = pd.date_range(first, last)
    output = data.reindex(grid)[["value", "period_start", "period_end", "measurement_type"]].rename_axis("date").reset_index()
    output.attrs.update(daily=False, series_kind="as_of_observation", metric=metric, measurement_type=measurement,
                        unit=_one(data, "unit"), definition=_one(data, "definition"),
                        source_timezone=_one(data, "source_timezone") if "source_timezone" in data else None,
                        reason=None if output["value"].notna().any() else "No numeric, available as-of observations.",
                        note="Reported as-of observations; rolling/lifetime/balance values are not daily activity and are never added.")
    return output


def compare_metrics(current, previous, metric, mode="performance", start=None, end=None, previous_start=None, previous_end=None):
    """Compare revisions of one window or performance in disjoint equal windows."""
    now = aggregate_metric(current, metric, start, end)
    before = aggregate_metric(previous, metric, previous_start, previous_end)
    result = {"metric": metric, "mode": mode, "current": now, "previous": before,
              "delta": None, "percent_change": None, "reason": None}
    if mode not in {"performance", "revision"}:
        result["reason"] = "Comparison mode must be performance or revision."
        return result
    if now["value"] is None or before["value"] is None:
        result["reason"] = now["reason"] or before["reason"]
        return result
    for key in ("scope", "unit", "definition", "measurement_type", "source_timezone"):
        if now[key] != before[key]:
            result["reason"] = f"Comparison requires the same {key.replace('_', ' ')}."
            return result
    a, b = _date(now["period_start"]), _date(now["period_end"])
    c, d = _date(before["period_start"]), _date(before["period_end"])
    if mode == "revision":
        if (a, b) != (c, d):
            result["reason"] = "Revision comparisons require the identical historical reporting window."
            return result
        if not now["snapshot"] or not before["snapshot"] or now["snapshot"] == before["snapshot"]:
            result["reason"] = "Revision comparisons require two explicitly identified, different snapshots."
            return result
    else:
        if now["measurement_type"] == "cumulative_total":
            result["reason"] = "Lifetime totals are not comparable period performance; equal content exposure and attribution are required."
            return result
        if b - a != d - c:
            result["reason"] = "Performance comparisons require equal reporting-period lengths."
            return result
        if not (b < c or d < a):
            result["reason"] = "Performance comparisons require nonoverlapping reporting periods; use revision mode for the same window."
            return result
    result["delta"] = now["value"] - before["value"]
    if before["value"] != 0:
        result["percent_change"] = result["delta"] / abs(before["value"]) * 100
    else:
        result["percent_change_reason"] = "Percentage change is unavailable because the earlier value is zero."
    return result


def _clean_series(frame):
    if not {"date", "value"}.issubset(frame.columns):
        raise ValueError("Series must contain date and value columns.")
    series = frame[["date", "value"]].copy()
    series["date"] = pd.to_datetime(series["date"].map(_date))
    series["value"] = pd.to_numeric(series["value"], errors="coerce").replace([np.inf, -np.inf], np.nan)
    if series["date"].isna().any() or series["date"].duplicated().any():
        raise ValueError("Series must have one row per valid source date.")
    return series.sort_values("date")


def indexed_series(series: Mapping[str, pd.DataFrame]):
    """Index all series to 100 on their first common nonzero observed date.

    Absolute values remain in ``value``. Earlier dates have no index. Missing
    days stay missing and zero baselines are never divided through.
    """
    output = pd.DataFrame(columns=["date", "series", "value", "index"])
    if not series:
        output.attrs["reason"] = "Select at least one series."
        return output
    try:
        cleaned = {name: _clean_series(frame) for name, frame in series.items()}
    except ValueError as exc:
        output.attrs["reason"] = str(exc)
        return output
    common = None
    for frame in cleaned.values():
        dates = set(frame.loc[frame["value"].notna() & frame["value"].ne(0), "date"])
        common = dates if common is None else common & dates
    reference = min(common) if common else None
    frames = []
    for name, frame in cleaned.items():
        current = frame.copy()
        current["series"] = name
        current["index"] = np.nan
        if reference is not None:
            base = current.loc[current["date"] == reference, "value"].iloc[0]
            selected = current["date"] >= reference
            current.loc[selected, "index"] = current.loc[selected, "value"] / base * 100
        frames.append(current)
    output = pd.concat(frames, ignore_index=True)[["date", "series", "value", "index"]]
    output.attrs.update(reference_date=_iso(reference), reason=None if reference is not None else "No common date with a nonzero observed value in every series.")
    return output


def lag_correlation(left, right, lag=0, min_observations=30):
    """Pearson association of left(t) with right(t + lag) on matched dates.

    Positive lag means left leads right. No missing-value filling occurs.
    Caller supplies native daily series, preferably from ``daily_series``.
    """
    result = {"correlation": None, "n": 0, "start": None, "end": None, "lag": lag,
              "lag_direction": "positive lag: left leads right by the stated number of days",
              "missing_data": "Pairwise matched observed dates only; missing values are not filled.",
              "reason": None,
              "caveat": "Exploratory association, not causation. Trends, seasonality and other factors can influence correlation."}
    if not isinstance(lag, (int, np.integer)) or not isinstance(min_observations, (int, np.integer)) or min_observations < 3:
        result["reason"] = "Lag must be whole days and minimum observations must be at least 3."
        return result
    if left.attrs.get("reason") or right.attrs.get("reason"):
        result["reason"] = left.attrs.get("reason") or right.attrs.get("reason")
        return result
    left_zone, right_zone = left.attrs.get("source_timezone"), right.attrs.get("source_timezone")
    if left_zone != right_zone:
        result["reason"] = "Source daily bucket timezones differ or are partly unknown; correlation cannot realign date-only totals."
        return result
    if left.attrs.get("daily") is False or right.attrs.get("daily") is False:
        result["reason"] = "Correlation requires daily observations."
        return result
    try:
        a, b = _clean_series(left), _clean_series(right)
    except ValueError as exc:
        result["reason"] = str(exc)
        return result
    # A daily grid is necessary: weekly/monthly values must not masquerade as
    # daily points. Explicit NaN rows preserve a real daily grid with gaps.
    for frame in (a, b):
        if len(frame) > 1 and not frame["date"].diff().dropna().eq(pd.Timedelta(days=1)).all():
            result["reason"] = "Correlation requires a daily date grid with missing days retained as gaps."
            return result
    b["right_date"] = b["date"]
    b["date"] -= pd.Timedelta(days=int(lag))
    aligned = a.merge(b, on="date", suffixes=("_left", "_right"))
    matched = aligned.dropna(subset=["value_left", "value_right"])
    result["n"] = len(matched)
    result["aligned_days"] = len(aligned)
    result["excluded_missing_pairs"] = len(aligned) - len(matched)
    result["matched_fraction"] = len(matched) / len(aligned) if len(aligned) else None
    if not matched.empty:
        result.update(start=_iso(matched["date"].min()), end=_iso(matched["date"].max()),
                      right_start=_iso(matched["right_date"].min()), right_end=_iso(matched["right_date"].max()))
    if len(matched) < min_observations:
        result["reason"] = f"Only {len(matched)} matched days; at least {min_observations} are required."
        return result
    if matched["value_left"].nunique() < 2 or matched["value_right"].nunique() < 2:
        result["reason"] = "Correlation is unavailable for a constant series."
        return result
    result["correlation"] = float(matched["value_left"].corr(matched["value_right"]))
    return result


def summarize_results(results: Mapping[str, dict]) -> str:
    """Produce concise Markdown from displayed KPIs without raw provenance dumps.

    Complete source references stay in the calculation result and evidence
    downloads. The narrative names supporting files and counts source records.
    """
    def period(calculated):
        return f"{calculated.get('period_start') or 'unknown'}–{calculated.get('period_end') or 'unknown'}"

    def snapshot(calculated):
        return calculated.get("snapshot_name") or calculated.get("snapshot") or "not supplied"

    def source_note(calculated):
        sources = calculated.get("sources", [])
        if not sources:
            return "Source reference not supplied."
        names = set()

        def add_name(source):
            if not isinstance(source, dict):
                return
            for field in ("source_filename", "source_file", "filename"):
                name = source.get(field)
                if name:
                    # Keep prose compact and avoid exposing a local directory.
                    names.add(str(name).replace("\\", "/").rsplit("/", 1)[-1])
                    break

        for source in sources:
            add_name(source)
            references = source.get("source_references") if isinstance(source, dict) else None
            if isinstance(references, str):
                try:
                    references = json.loads(references)
                except (ValueError, TypeError):
                    references = None
            if isinstance(references, list):
                for reference in references:
                    add_name(reference)
        filenames = sorted(names)
        shown = [name if len(name) <= 120 else name[:117] + "…" for name in filenames[:3]]
        label = ", ".join(shown) if shown else "referenced source records"
        if len(filenames) > 3:
            label += f" and {len(filenames) - 3:,} other filenames"
        count = len(sources)
        return f"{label} ({count:,} source record{'s' if count != 1 else ''})."

    lines = []
    for label, result in results.items():
        if lines:
            lines.append("")
        if "current" in result:
            current, previous = result["current"], result["previous"]
            context = f"Current {period(current)}, snapshot {snapshot(current)}; previous {period(previous)}, snapshot {snapshot(previous)}."
            if result["delta"] is None:
                lines.append(f"- **{label}:** comparison unavailable — {result['reason']} {context}")
            else:
                percent = f" ({result['percent_change']:+.1f}%)" if result["percent_change"] is not None else " (percentage change unavailable)"
                lines.append(f"- **{label}:** {current['value']:,.4g} versus {previous['value']:,.4g} {current.get('unit') or ''}; {result['mode']} change {result['delta']:+,.4g}{percent}. {context}")
            if current.get("definition"):
                lines.append(f"  Definition: {current['definition']}")
            lines.append(f"  Current sources: {source_note(current)} Previous sources: {source_note(previous)}")
            continue
        context = f"{period(result)}; snapshot {snapshot(result)}."
        if result.get("value") is None:
            partial = f" Partial observed count: {result['partial_value']:,.4g} {result.get('unit') or ''}." if result.get("partial_value") is not None else ""
            reason = str(result.get("reason") or "missing data").rstrip(".")
            lines.append(f"- **{label}:** unavailable — {reason}.{partial} {context}")
        else:
            lines.append(f"- **{label}:** {result['value']:,.4g} {result.get('unit') or ''}; {context}")
        if result.get("definition"):
            lines.append(f"  Definition: {result['definition']}")
        lines.append(f"  Sources: {source_note(result)}")
    return "\n".join(lines) + ("\n" if lines else "")
