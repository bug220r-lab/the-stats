"""Pure social calculations following the delivered social_pipeline contract.

Only complete, compatible additive daily intervals receive totals. Lifetime,
unique audience, stock and distribution measurements stay separate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import math

import pandas as pd


ADDITIVE = frozenset({"follows", "interactions", "link_clicks", "views", "visits"})
OBSERVED = frozenset({"observed", "observed_zero"})
DAILY_SCOPE = ("platform_selected", "selected_account_id", "metric_platform_scope", "metric",
               "measurement_type", "reporting_timezone", "snapshot_class")


def _one_scope(data):
    # The delivered canonical account_daily contract explicitly defines a
    # Pacific calendar. A few source rows omit their own timezone metadata;
    # leave those raw fields blank, but use the documented table calendar.
    # An explicit different timezone is incompatible and is never rebinned.
    fields = [field for field in DAILY_SCOPE if field != "reporting_timezone"]
    if any(data[field].fillna("").astype(str).nunique() != 1 for field in fields):
        return False
    zones = set(data.reporting_timezone.dropna().astype(str)) - {""}
    return zones.issubset({"Pacific Time", "America/Los_Angeles"}) and not data.date.duplicated().any()


def truth(series):
    return series.fillna(False).astype(str).str.lower().isin({"true", "1"})


def prepare_daily(frame):
    """Mask nonobservations without changing retained status or raw values."""
    data = frame.copy()
    if data.empty:
        return data
    required = set(DAILY_SCOPE) | {"date", "value", "value_status", "partial_day"}
    if not required.issubset(data):
        raise ValueError("The account daily table is missing required scope or status columns.")
    data["date"] = pd.to_datetime(data["date"], errors="raise").dt.strftime("%Y-%m-%d")
    if data.date.isna().any():
        raise ValueError("Every social daily observation needs a reporting date.")
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    valid = data.value.map(lambda value: pd.notna(value) and math.isfinite(float(value)) and float(value) >= 0)
    data.loc[~valid, "value"] = float("nan")
    data.loc[~data.value_status.isin(OBSERVED), "value"] = float("nan")
    # Unknown completeness cannot establish a complete period. Preserve native
    # flags in the source table; this view treats unknowns as incomplete.
    data["partial_day"] = ~data.partial_day.astype("string").str.lower().isin({"false", "0"})
    if data.duplicated([*DAILY_SCOPE, "date"]).any():
        raise ValueError("Duplicate account-day keys would inflate activity; select the canonical daily table.")
    return data


def canonical_social_series(repo):
    """Select the reviewed follows replacement once, retaining each source path.

    This selection changes descriptive views only. Historical package tables
    and their statistical input versions remain untouched.
    """
    original = prepare_daily(repo.table("social/account_daily.csv"))
    original["source_reporting_timezone"] = original.reporting_timezone
    zones = set(original.reporting_timezone.dropna()) - {""}
    if not zones.issubset({"Pacific Time", "America/Los_Angeles"}):
        raise ValueError("Canonical social calendar contains an incompatible timezone.")
    original["reporting_timezone"] = "America/Los_Angeles"
    repair_path = "social/meta_collection/follows_daily_resolved.csv"
    result = [("social/account_daily.csv", original)]
    if repair_path not in repo.tables:
        return result
    repair = prepare_daily(repo.table(repair_path))
    if repair.empty:
        return result
    identity_keys = ["platform_selected", "selected_account_id", "metric", "metric_platform_scope"]
    identities = repair[identity_keys].drop_duplicates()
    if (len(identities) != 1 or identities.iloc[0].platform_selected != "Instagram"
            or identities.iloc[0].metric != "follows" or identities.isna().any().any()):
        raise ValueError("The approved follows repair must have one Instagram account and scope.")
    match = pd.Series(True, index=original.index)
    for key, value in identities.iloc[0].items():
        match &= original[key].eq(value)
    if not match.any():
        raise ValueError("The reviewed follows repair has no matching inherited account and metric scope.")
    if repair.date.duplicated().any():
        raise ValueError("Duplicate reviewed follows dates cannot replace inherited activity.")
    if not set(repair.reporting_timezone.dropna()).issubset({"Pacific Time", "America/Los_Angeles"}):
        raise ValueError("Reviewed follows repair has an incompatible native calendar.")
    repair["source_snapshot_class"] = repair.snapshot_class
    repair["source_reporting_timezone"] = repair.reporting_timezone
    repair["snapshot_class"] = "reviewed_follows_repair_canonical_selection"
    repair["reporting_timezone"] = "America/Los_Angeles"
    return [("social/account_daily.csv", original.loc[~match]), (repair_path, repair)]


@dataclass(frozen=True)
class DailyWindow:
    start: str
    end: str
    calendar_days: int
    observed_days: int
    missing_days: int
    partial_days: int
    total: float | None
    observed_sum: float | None
    median_daily: float | None
    reason: str


def summarize_daily(frame, start, end):
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if start > end:
        raise ValueError("The reporting start must not follow the end.")
    data = prepare_daily(frame)
    if not data.empty and not _one_scope(data):
        raise ValueError("Select one account, metric, scope, timezone and snapshot class before aggregation.")
    selected = data[data.date.between(start.isoformat(), end.isoformat())] if not data.empty else data
    expected = (end - start).days + 1
    observed = selected.value.dropna() if not selected.empty else pd.Series(dtype=float)
    count = len(observed)
    missing = expected - count
    partial = int(selected.partial_day.sum()) if not selected.empty else 0
    metric = data.metric.iloc[0] if not data.empty else None
    kind = data.measurement_type.iloc[0] if not data.empty else None
    additive = metric in ADDITIVE and kind == "daily_interval_count"
    complete = count == expected and partial == 0
    observed_sum = float(observed.sum()) if count and additive else None
    total = observed_sum if complete and additive else None
    if not additive:
        reason = "Daily unique audiences, stocks and other nonadditive measurements have no calculated period total."
    elif partial:
        reason = f"{partial} source day(s) are partial; a complete-window total and comparison are unavailable."
    elif missing:
        reason = f"{missing} date(s) are missing or unavailable; omitted values are not zero."
    else:
        reason = "Complete nonoverlapping daily activity in one account, metric and platform scope."
    return DailyWindow(start.isoformat(), end.isoformat(), expected, count, missing, partial, total,
                       observed_sum, float(observed.median()) if count else None, reason)


def compare_daily(frame, start, end):
    current = summarize_daily(frame, start, end)
    prior_end = date.fromisoformat(current.start) - timedelta(days=1)
    prior_start = prior_end - timedelta(days=current.calendar_days - 1)
    previous = summarize_daily(frame, prior_start.isoformat(), prior_end.isoformat())
    comparable = current.total is not None and previous.total is not None
    delta = current.total - previous.total if comparable else None
    percent = delta / previous.total * 100 if comparable and previous.total > 0 else None
    return {"current": current, "previous": previous, "delta": delta, "percent_change": percent,
            "reason": "Equal, nonoverlapping complete periods; descriptive comparison, not a causal effect."
            if comparable else "Comparison unavailable: both periods need complete observed additive activity."}


def daily_grid(frame, start, end):
    data = prepare_daily(frame)
    if not data.empty and not _one_scope(data):
        raise ValueError("Choose one daily scope before plotting.")
    grid = pd.DataFrame({"date": pd.date_range(start, end).strftime("%Y-%m-%d")})
    result = grid.merge(data, on="date", how="left", validate="one_to_one")
    result["value_status"] = result.value_status.fillna("missing_date_in_loaded_table")
    return result


def prepare_posts(frame):
    data = frame.copy()
    if data.empty:
        return data
    if data.duplicated(["platform_selected", "post_id"]).any():
        raise ValueError("The latest-post table contains duplicate platform/post IDs; snapshots cannot be added.")
    if not data.measurement_type.eq("lifetime_content_snapshot").all():
        raise ValueError("Content browsing requires explicitly identified lifetime snapshots.")
    for column in ("post_age_days", "views", "reach", "likes", "comments", "shares", "saves",
                   "reactions", "engagement_actions", "engagement_per_reach"):
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce")
            if column + "_status" in data:
                data.loc[~data[column + "_status"].isin(OBSERVED), column] = float("nan")
    return data


def publication_series(posts):
    """Count retained publication events only; never allocate lifetime outcomes."""
    data = prepare_posts(posts)
    if data.empty:
        return pd.DataFrame(columns=["publication_date", "post_type", "retained_posts"])
    return data.groupby(["publication_date", "post_type"], dropna=False).size().rename("retained_posts").reset_index()


def filtered_csv(frame):
    """Export filtered evidence with IDs as text and formula-safe string cells."""
    output = frame.copy()
    for column in output:
        output[column] = output[column].map(lambda value: "'" + value if isinstance(value, str)
                                            and value.startswith(("=", "+", "-", "@")) else value)
    return output.to_csv(index=False).encode("utf-8-sig")
