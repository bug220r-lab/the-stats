import pandas as pd
import pytest

from stats_app.calculations import available_metrics, chart_data, filter_observations, summarize_metric


def row(**updates):
    result = {"metric": "streams", "platform": "spotify", "value": 10,
              "status": "observed", "period_start": "2026-10-01", "period_end": "2026-10-20"}
    result.update(updates)
    return result


def test_empty_selection_is_unavailable_not_zero():
    summary = summarize_metric(pd.DataFrame())
    assert summary.value is None
    assert summary.status == "unavailable"
    assert available_metrics(pd.DataFrame()) == []
    assert chart_data(pd.DataFrame()).empty


def test_genuine_zero_remains_observed():
    summary = summarize_metric(pd.DataFrame([row(value=0)]))
    assert summary.value == 0
    assert summary.status == "observed"
    assert summary.missing_rows == 0


@pytest.mark.parametrize("status", ["missing", "suppressed", "unavailable"])
def test_missing_values_and_status_are_preserved(status):
    summary = summarize_metric(pd.DataFrame([row(value=None, status=status)]))
    assert summary.value is None
    assert summary.status == status
    assert summary.missing_rows == 1


def test_overlapping_periods_cumulative_values_and_missing_rows_are_not_summed():
    observations = pd.DataFrame([
        row(value=100), row(value=150, period_start="2026-10-10"), row(value=None, status="missing"),
    ])
    summary = summarize_metric(observations)
    assert summary.value is None
    assert summary.status == "multiple_records"
    assert summary.observed_rows == 2
    assert summary.missing_rows == 1


def test_chart_keeps_missing_gap_and_observed_zero():
    observations = pd.DataFrame([
        row(value=0, period_start="2026-10-01", period_end="2026-10-01"),
        row(value=None, status="missing", period_start="2026-10-02", period_end="2026-10-02"),
        row(value=7, period_start="2026-10-03", period_end="2026-10-03"),
    ])
    result = chart_data(observations)
    assert result.iloc[0]["value"] == 0
    assert pd.isna(result.iloc[1]["value"])
    assert result.iloc[2]["value"] == 7
    assert observations.iloc[0]["period_start"] == "2026-10-01"


def test_filters_return_copy_and_metrics_are_sorted():
    observations = pd.DataFrame([row(), row(platform="meta", metric="followers")])
    selected = filter_observations(observations, platform="spotify")
    assert len(selected) == 1
    selected.loc[:, "value"] = 900
    assert observations.iloc[0]["value"] == 10
    assert available_metrics(observations) == ["followers", "streams"]


def daily(day, **updates):
    result = row(period_start=day, period_end=day)
    result.update(account="The Stats", entity_type="track", entity_id="track-1", unit="count",
                  time_grain="daily", measurement_type="period_count", source_timezone="",
                  dimensions_json="{}", definition="Reported daily streams")
    result.update(updates)
    return result


def test_complete_daily_count_series_can_be_added():
    summary = summarize_metric(pd.DataFrame([
        daily("2026-10-01", value=10), daily("2026-10-02", value=0), daily("2026-10-03", value=20),
    ]))
    assert summary.value == 30
    assert summary.status == "observed"
    assert summary.observed_rows == 3
    assert summary.missing_rows == 0


def test_daily_gaps_and_explicit_missing_rows_make_total_partial():
    data = pd.DataFrame([
        daily("2026-10-01", value=10),
        daily("2026-10-02", value=None, status="missing"),
        daily("2026-10-04", value=20),
    ])
    summary = summarize_metric(data)
    assert summary.value == 30
    assert summary.status == "partial"
    assert summary.observed_rows == 2
    assert summary.missing_rows == 2
    chart = chart_data(data)
    assert len(chart) == 4
    gap = chart.loc[chart["is_gap"]].iloc[0]
    assert gap["period_start"] == pd.Timestamp("2026-10-03")
    assert pd.isna(gap["value"])
    assert gap["status"] == "missing"


@pytest.mark.parametrize("updates", [
    {"metric": "listeners"}, {"metric": "reach"}, {"metric": "followers"},
    {"measurement_type": "cumulative"}, {"measurement_type": "rate"},
    {"measurement_type": "rolling_unique"},
    {"unit": "percent"},
])
def test_non_additive_metrics_never_sum(updates):
    summary = summarize_metric(pd.DataFrame([daily("2026-10-01", **updates), daily("2026-10-02", **updates)]))
    assert summary.value is None
    assert summary.status == "multiple_records"


@pytest.mark.parametrize("updates", [
    {"account": "Another account"}, {"entity_id": "track-2"},
    {"entity_type": "account", "entity_id": "account"},
    {"definition": "Different counting definition"}, {"source_timezone": "UTC"},
    {"dimensions_json": '{"country":"US"}'}, {"unit": "percentage"},
])
def test_mixed_reporting_scopes_never_sum(updates):
    summary = summarize_metric(pd.DataFrame([daily("2026-10-01"), daily("2026-10-02", **updates)]))
    assert summary.value is None


def test_daily_duplicate_and_overlapping_periods_never_sum():
    duplicate = pd.DataFrame([daily("2026-10-01"), daily("2026-10-01")])
    overlapping = pd.DataFrame([daily("2026-10-01", period_end="2026-10-02"), daily("2026-10-02")])
    assert summarize_metric(duplicate).value is None
    assert summarize_metric(overlapping).value is None


def test_all_missing_daily_values_never_become_zero():
    summary = summarize_metric(pd.DataFrame([
        daily("2026-10-01", value=None, status="missing"),
        daily("2026-10-02", value=None, status="unavailable"),
    ]))
    assert summary.value is None
    assert summary.status == "unavailable"


def test_rolling_daily_series_shows_missing_endpoint_gap_without_summing():
    data = pd.DataFrame([
        daily("2026-10-01", period_start="2026-09-04", metric="monthly_listeners", measurement_type="rolling_count"),
        daily("2026-10-03", period_start="2026-09-06", metric="monthly_listeners", measurement_type="rolling_count"),
    ])
    assert summarize_metric(data).value is None
    chart = chart_data(data)
    gap = chart.loc[chart.is_gap].iloc[0]
    assert gap.period_end == pd.Timestamp("2026-10-02")
    assert gap.period_start == pd.Timestamp("2026-09-05")
    assert pd.isna(gap.value)


def test_spotify_playlist_adds_is_an_additive_daily_count():
    data = pd.DataFrame([
        daily("2026-10-01", metric="playlist_adds", value=2),
        daily("2026-10-02", metric="playlist_adds", value=3),
    ])
    assert summarize_metric(data).value == 5
