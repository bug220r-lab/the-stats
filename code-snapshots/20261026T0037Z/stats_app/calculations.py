"""Conservative reporting helpers; missing measurements never become zero.

Do not total arbitrary exports: daily values, period totals, cumulative counters,
and rates describe different things. These helpers summarize only an explicitly
selected compatible series and refuse ambiguous aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


SERIES_FIELDS = ("platform", "account", "entity_type", "entity_id", "metric", "unit",
                 "time_grain", "measurement_type", "source_timezone", "dimensions_json", "definition")
# Unique audiences, reach, ratios, balances, and cumulative counters are excluded.
ADDITIVE_COUNT_METRICS = {"streams", "plays", "views", "video_views", "impressions", "likes",
                         "comments", "shares", "saves", "profile_views", "clicks", "link_clicks",
                         "engagements", "playlist_adds", "new_followers", "followers_gained", "followers_lost"}


@dataclass(frozen=True)
class MetricSummary:
    value: float | None
    observed_rows: int
    missing_rows: int
    status: str
    explanation: str


def _one_daily_series(observations: pd.DataFrame, *, point_periods: bool = True) -> bool:
    if observations.empty or any(field not in observations for field in SERIES_FIELDS):
        return False
    if any(observations[field].fillna("").astype(str).nunique() != 1 for field in SERIES_FIELDS):
        return False
    if str(observations.iloc[0]["time_grain"]).lower() not in {"day", "daily"}:
        return False
    starts = pd.to_datetime(observations["period_start"], errors="coerce")
    ends = pd.to_datetime(observations["period_end"], errors="coerce")
    if starts.isna().any() or ends.isna().any() or ends.duplicated().any():
        return False
    if point_periods:
        return bool(starts.eq(ends).all())
    # Daily endpoint series can represent rolling windows. Their lengths must
    # agree before synthesizing a missing endpoint for the chart.
    return bool((ends - starts).nunique() == 1)


def available_metrics(observations: pd.DataFrame) -> list[str]:
    if observations.empty or "metric" not in observations:
        return []
    return sorted(observations["metric"].dropna().astype(str).unique().tolist())


def filter_observations(observations: pd.DataFrame, **filters: Any) -> pd.DataFrame:
    """Return a copy; blank/None filters mean all values for that dimension."""
    result = observations.copy()
    for field, value in filters.items():
        if value is not None and value != "" and field in result:
            result = result.loc[result[field] == value]
    return result.copy()


def summarize_metric(observations: pd.DataFrame) -> MetricSummary:
    """Describe a selected series without inventing totals or filling gaps.

    One observed row is displayed as recorded. Only explicitly additive daily
    period_count measurements from one scope can be summed. Missing rows or
    unreported dates make that sum explicitly partial.
    """
    if observations.empty:
        return MetricSummary(None, 0, 0, "unavailable", "No records have been imported for this selection.")
    observed = observations["status"].eq("observed") & observations["value"].notna()
    observed_count = int(observed.sum())
    missing_count = len(observations) - observed_count
    if len(observations) == 1:
        row = observations.iloc[0]
        if observed_count:
            return MetricSummary(float(row["value"]), 1, 0, "observed", "Value as reported for the selected period.")
        return MetricSummary(None, 0, 1, str(row["status"]), "The source does not provide a numeric value for this record.")
    if observed_count == 0:
        return MetricSummary(None, 0, missing_count, "unavailable", "All selected records have a missing-data status.")
    if (_one_daily_series(observations)
            and observations.iloc[0]["measurement_type"] == "period_count"
            and str(observations.iloc[0]["unit"]).lower() == "count"
            and observations.iloc[0]["metric"].lower() in ADDITIVE_COUNT_METRICS):
        dates = pd.to_datetime(observations["period_start"])
        expected_count = int((dates.max() - dates.min()).days) + 1
        absent_dates = expected_count - len(observations)
        value = float(pd.to_numeric(observations.loc[observed, "value"]).sum(min_count=1))
        missing_count += absent_dates
        if missing_count:
            return MetricSummary(value, observed_count, missing_count, "partial",
                                 f"Partial sum of {observed_count} reported daily values; {missing_count} dates are missing or unavailable within the selected date range. Missing dates are not zero.")
        return MetricSummary(value, observed_count, 0, "observed",
                             f"Sum of {observed_count} non-overlapping daily counts for one metric and reporting scope.")
    return MetricSummary(None, observed_count, missing_count, "multiple_records",
                         "Multiple records are shown separately; period totals, cumulative values, rates, and gaps must not be summed indiscriminately.")


def chart_data(observations: pd.DataFrame) -> pd.DataFrame:
    """Retain unknown values as NaN so Plotly can render gaps (connectgaps=False)."""
    result = observations.copy()
    if result.empty:
        return result
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    result.loc[result["status"] != "observed", "value"] = float("nan")
    result["period_end"] = pd.to_datetime(result["period_end"], errors="coerce")
    result["period_start"] = pd.to_datetime(result["period_start"], errors="coerce")
    result["is_gap"] = False
    if _one_daily_series(observations, point_periods=False):
        start, end = result["period_end"].min(), result["period_end"].max()
        # Bound expansion for malformed or exceptionally broad source periods.
        if (end - start).days <= 36600:
            dates = pd.date_range(start, end, freq="D")
            existing = set(result["period_end"])
            window_length = result.iloc[0]["period_end"] - result.iloc[0]["period_start"]
            missing = dates[~dates.isin(existing)]
            gaps = []
            for day in missing:
                gap = {column: "" for column in result.columns}
                gap.update({field: result.iloc[0][field] for field in SERIES_FIELDS})
                gap.update(value=float("nan"), status="missing", period_start=day - window_length, period_end=day,
                           is_gap=True, source_row=None, source_count=0,
                           source_names="No imported record for this date")
                if "entity_name" in result:
                    gap["entity_name"] = result.iloc[0]["entity_name"]
                gaps.append(gap)
            if gaps:
                result = pd.concat([result, pd.DataFrame(gaps)], ignore_index=True)
    return result.sort_values(["period_start", "period_end", "metric"], kind="stable")
