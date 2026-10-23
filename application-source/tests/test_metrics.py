"""Acceptance checks for consequential measurement and population rules."""
import json

import numpy as np
import pandas as pd
import pytest

from stats.metrics import (
    METRICS, aggregate_metric, asof_series, compare_metrics, daily_series, derived_ratio,
    filter_observations, indexed_series, lag_correlation, summarize_results,
)


def observation(metric="streams", value=10, start="2026-10-01", end=None, **kwargs):
    spec = METRICS[metric]
    row = dict(platform="spotify", account_id="artist:123", account_name="Test artist",
               entity_type="artist", entity_id="artist:123", entity_name="Test artist",
               metric=metric, value=value, unit=spec["unit"], definition=spec["definition"],
               dimensions="{}", period_start=start, period_end=end or start,
               time_grain="day" if end is None or end == start else "period",
               measurement_type=spec["measurement_type"], status="verified",
               source_timezone=None, captured_at="2026-10-20T12:00:00Z",
               snapshot_id="baseline", snapshot_name="October 20 baseline",
               source_filename="isolated-test-fixture.csv", source_row=2)
    row.update(kwargs)
    return row


def frame(*rows):
    return pd.DataFrame(rows)


def days(values=(10, 20, 30), **kwargs):
    return frame(*(observation(value=value, start=f"2026-10-{day:02d}", **kwargs)
                   for day, value in enumerate(values, start=1)))


def test_complete_daily_counts_sum_and_keep_sources():
    result = aggregate_metric(days(), "streams", "2026-10-01", "2026-10-03")
    assert result["value"] == 60
    assert result["coverage"]["complete"] is True
    assert result["coverage"]["observed_days"] == 3
    assert result["sources"][0]["source_filename"] == "isolated-test-fixture.csv"


def test_missing_is_not_zero_and_partial_is_explicit():
    result = aggregate_metric(days((10, np.nan, 0)), "streams")
    assert result["value"] is None
    assert result["partial_value"] == 10
    assert result["coverage"]["missing_days"] == ["2026-10-02"]
    assert aggregate_metric(days((0, 0, 0)), "streams")["value"] == 0


def test_requested_window_edges_are_not_silently_trimmed():
    result = aggregate_metric(days(), "streams", "2026-09-30", "2026-10-04")
    assert result["value"] is None
    assert result["coverage"]["observed_days"] == 3
    assert result["coverage"]["expected_days"] == 5


def test_authoritative_exact_period_not_added_to_daily_breakdown():
    data = pd.concat([days(), frame(observation(value=65, end="2026-10-03"))])
    result = aggregate_metric(data, "streams")
    assert result["value"] == 65
    assert result["coverage"]["method"] == "exact_reported_window"


def test_disjoint_multiday_periods_can_sum():
    data = frame(observation(value=40, end="2026-10-02"),
                 observation(value=60, start="2026-10-03", end="2026-10-04"))
    assert aggregate_metric(data, "streams")["value"] == 100


def test_overlapping_partial_periods_never_sum():
    data = frame(observation(value=40, end="2026-10-02"),
                 observation(value=60, start="2026-10-02", end="2026-10-03"))
    result = aggregate_metric(data, "streams")
    assert result["value"] is None
    assert "Overlapping" in result["reason"]


def test_complete_daily_partition_excludes_coarser_partial_summaries():
    data = pd.concat([days(), frame(observation(value=31, end="2026-10-02"))], ignore_index=True)
    result = aggregate_metric(data, "streams")
    assert result["value"] == 60
    assert result["coverage"]["method"] == "sum_complete_daily_counts"
    assert result["coverage"]["ignored_coarser_rows"] == 1


def test_period_extending_outside_requested_window_is_not_prorated():
    data = frame(observation(value=40, end="2026-10-10"))
    result = aggregate_metric(data, "streams", "2026-10-02", "2026-10-04")
    assert result["value"] is None
    assert result["partial_value"] is None


@pytest.mark.parametrize("metric", ["listeners", "reach", "monthly_listeners"])
def test_distinct_and_rolling_audiences_never_sum(metric):
    result = aggregate_metric(days(metric=metric), metric)
    assert result["value"] is None
    assert "cannot be summed" in result["reason"]


def test_exact_period_unique_listeners_are_available():
    data = frame(observation("listeners", 50, end="2026-10-31"))
    assert aggregate_metric(data, "listeners", "2026-10-01", "2026-10-31")["value"] == 50


def test_followers_latest_balance_is_not_total_and_retains_as_of_date():
    result = aggregate_metric(days(metric="followers"), "followers", "2026-10-01", "2026-10-07")
    assert result["value"] == 30
    assert result["period_start"] == result["period_end"] == "2026-10-03"
    assert result["coverage"]["method"] == "latest_reported_balance"


def test_cumulative_and_rates_are_not_summed():
    for measurement_type in ("cumulative_total", "rate"):
        result = aggregate_metric(days(measurement_type=measurement_type), "streams")
        assert result["value"] is None


@pytest.mark.parametrize("column,new_value", [
    ("account_id", "artist:other"), ("platform", "instagram"),
    ("entity_type", "track"), ("entity_id", "track:123"),
    ("definition", "Different counting policy"), ("unit", "thousands"),
    ("dimensions", json.dumps({"country": "US"})),
    ("snapshot_id", "later"), ("measurement_type", "cumulative_total"),
    ("source_timezone", "America/New_York"),
])
def test_mixed_scopes_definitions_units_and_snapshots_fail_closed(column, new_value):
    data = days()
    data.loc[1, column] = new_value
    result = aggregate_metric(data, "streams")
    assert result["value"] is None
    assert result["reason"]


def test_account_total_and_track_breakdown_never_add():
    data = frame(observation(value=100), observation(value=20, entity_type="track", entity_id="track:123"))
    assert aggregate_metric(data, "streams")["value"] is None


def test_same_period_duplicates_collapse_and_conflicts_are_unavailable():
    data = frame(observation(value=10), observation(value=10, source_filename="another.csv"))
    assert aggregate_metric(data, "streams")["value"] == 10
    assert len(aggregate_metric(data, "streams")["sources"]) == 2
    data.loc[1, "value"] = 11
    assert "Conflicting" in aggregate_metric(data, "streams")["reason"]


def test_equivalent_dimension_json_order_does_not_change_population():
    data = days()
    data["dimensions"] = ['{"country":"US","segment":"organic"}', '{"segment":"organic","country":"US"}', '{"country": "US", "segment": "organic"}']
    assert aggregate_metric(data, "streams")["value"] == 60


def test_invalid_dimensions_do_not_become_empty_population():
    assert aggregate_metric(days(dimensions="country=US"), "streams")["value"] is None


@pytest.mark.parametrize("status", ["suppressed", "missing", "unverified", "rejected"])
def test_unavailable_status_does_not_turn_numeric_placeholder_into_data(status):
    assert aggregate_metric(frame(observation(value=0, status=status)), "streams")["value"] is None


def test_ratios_recompute_compatible_period_counts_and_unique_denominator():
    data = frame(observation(value=120, end="2026-10-07"),
                 observation("listeners", 30, end="2026-10-07"))
    result = derived_ratio(data, "streams", "listeners")
    assert result["value"] == 4
    assert result["unit"] == "ratio"
    assert "not unique-person conversion" in result["definition"]


def test_engagement_rate_denominator_is_explicit():
    data = frame(observation("engagements", 20), observation("impressions", 200), observation("reach", 100))
    assert derived_ratio(data, "engagements", "impressions", multiplier=100)["value"] == 10
    assert derived_ratio(data, "engagements", "reach", multiplier=100)["value"] == 20


def test_ratio_zero_denominator_unavailable():
    result = derived_ratio(frame(observation(value=20), observation("listeners", 0)), "streams", "listeners")
    assert result["value"] is None
    assert "zero" in result["reason"]


@pytest.mark.parametrize("difference", [dict(snapshot_id="other"), dict(entity_id="other"), dict(dimensions='{"country":"US"}'), dict(start="2026-10-02")])
def test_ratio_rejects_different_population_snapshot_and_window(difference):
    data = frame(observation(value=20), observation("listeners", 4, **difference))
    result = derived_ratio(data, "streams", "listeners")
    assert result["value"] is None


def test_daily_chart_keeps_gaps_and_does_not_interpolate_periods():
    data = frame(observation(value=10), observation(value=0, start="2026-10-03"), observation(value=100, end="2026-10-04"))
    series = daily_series(data, "streams")
    assert series["value"].iloc[0] == 10
    assert pd.isna(series["value"].iloc[1])
    assert series["value"].iloc[2] == 0
    assert pd.isna(series["value"].iloc[3])
    assert series["date"].iloc[0] == pd.Timestamp("2026-10-01")


def test_chart_and_kpi_agree_on_complete_daily_selection():
    data = days()
    series = daily_series(data, "streams")
    assert series["value"].sum() == aggregate_metric(data, "streams")["value"]


def test_filter_uses_account_id_and_intersecting_window():
    data = frame(observation(value=10, end="2026-10-07"), observation(value=20, start="2026-10-08"), observation(value=30, account_id="other"))
    selected = filter_observations(data, start="2026-10-02", end="2026-10-03", accounts=["artist:123"], platforms=["spotify"], entity_type="artist")
    assert len(selected) == 1
    assert selected.iloc[0]["period_start"] == "2026-10-01"
    assert aggregate_metric(selected, "streams", "2026-10-02", "2026-10-03")["value"] is None


def test_performance_and_revision_have_distinct_rules():
    earlier = frame(observation(value=100, end="2026-10-07"))
    current = frame(observation(value=120, start="2026-10-08", end="2026-10-14", snapshot_id="new"))
    result = compare_metrics(current, earlier, "streams")
    assert result["delta"] == 20
    assert result["percent_change"] == 20
    assert compare_metrics(current, earlier, "streams", mode="revision")["delta"] is None
    revision = frame(observation(value=125, end="2026-10-07", snapshot_id="new"))
    assert compare_metrics(revision, earlier, "streams", mode="revision")["delta"] == 25
    assert compare_metrics(revision, earlier, "streams")["delta"] is None


def test_different_period_lengths_cannot_compare():
    earlier = frame(observation(value=100, end="2026-10-07"))
    current = frame(observation(value=120, start="2026-10-08", end="2026-10-15"))
    assert "equal" in compare_metrics(current, earlier, "streams")["reason"]


def test_lifetime_content_does_not_compare_as_equal_exposure():
    earlier = frame(observation(value=100, measurement_type="cumulative_total"))
    current = frame(observation(value=120, start="2026-10-02", measurement_type="cumulative_total"))
    assert "Lifetime" in compare_metrics(current, earlier, "streams")["reason"]


def test_comparison_zero_start_preserves_absolute_delta():
    result = compare_metrics(frame(observation(value=10, start="2026-10-02")), frame(observation(value=0)), "streams")
    assert result["delta"] == 10
    assert result["percent_change"] is None


def test_index_uses_common_nonzero_date_and_retains_absolute_values():
    a = pd.DataFrame({"date": pd.date_range("2026-10-01", periods=3), "value": [0, 10, 20]})
    b = pd.DataFrame({"date": pd.date_range("2026-10-01", periods=3), "value": [5, 20, np.nan]})
    result = indexed_series({"streams": a, "views": b})
    assert result.attrs["reference_date"] == "2026-10-02"
    assert result["value"].iloc[0] == 0
    assert pd.isna(result["index"].iloc[0])
    assert result["index"].iloc[1] == 100
    assert result["index"].iloc[2] == 200
    assert pd.isna(result["index"].iloc[5])


def test_index_all_zero_has_explicit_unavailability():
    data = pd.DataFrame({"date": pd.date_range("2026-10-01", periods=3), "value": [0, 0, 0]})
    result = indexed_series({"zero": data})
    assert result["index"].isna().all()
    assert result.attrs["reason"]


def test_correlation_uses_matched_days_without_zero_fill():
    a = pd.DataFrame({"date": pd.date_range("2026-08-01", periods=40), "value": np.arange(40, dtype=float)})
    b = a.copy()
    b.loc[:4, "value"] = np.nan
    result = lag_correlation(a, b)
    assert result["n"] == 35
    assert result["correlation"] == pytest.approx(1)
    assert result["start"] == "2026-08-06"


def test_positive_lag_means_left_leads_right():
    rng = np.random.default_rng(123)
    values = rng.normal(size=40)
    a = pd.DataFrame({"date": pd.date_range("2026-08-01", periods=40), "value": values})
    b = a.copy()
    b["value"] = np.r_[np.nan, np.nan, values[:-2]]
    result = lag_correlation(a, b, lag=2)
    assert result["n"] == 38
    assert result["correlation"] == pytest.approx(1)
    assert result["right_start"] == "2026-08-03"


def test_correlation_refuses_small_sample_constant_weekly_and_zone_mismatch():
    a = pd.DataFrame({"date": pd.date_range("2026-08-01", periods=40), "value": np.arange(40, dtype=float)})
    assert lag_correlation(a.iloc[:20], a.iloc[:20])["correlation"] is None
    constant = a.assign(value=5)
    assert "constant" in lag_correlation(a, constant)["reason"]
    assert "daily" in lag_correlation(a.iloc[::7], a.iloc[::7])["reason"]
    b = a.copy()
    b.attrs["source_timezone"] = "UTC"
    assert "timezones" in lag_correlation(a, b)["reason"]


def test_summary_uses_results_and_reports_missing_not_zero():
    complete = aggregate_metric(days(), "streams")
    missing = aggregate_metric(days((1, np.nan, 2)), "streams")
    text = summarize_results({"Spotify streams": complete, "Incomplete streams": missing})
    assert "60 count" in text
    assert "unavailable" in text
    assert "Partial observed count: 3" in text
    assert "isolated-test-fixture.csv" in text
    assert "October 20 baseline" in text
    assert not text.startswith("#")


def test_summary_stays_compact_with_repeated_nested_provenance():
    result = aggregate_metric(days(), "streams")
    result["sources"] = [
        {"source_filename": "artist_daily.csv", "source_row": row,
         "source_references": json.dumps([{"source_filename": "artist_daily.csv", "source_row": row,
                                            "file_hash": "a" * 64, "evidence_ref": "raw/source.csv#row=" + str(row)},
                                           {"source_filename": "overlapping_export.csv", "source_row": row}])}
        for row in range(1000)
    ]
    text = summarize_results({"Spotify streams": result})
    assert len(text) < 600
    assert text.count("artist_daily.csv") == 1
    assert "overlapping_export.csv" in text
    assert "1,000 source records" in text
    assert "source_references" not in text
    assert "file_hash" not in text
    assert "{" not in text
    assert len(result["sources"]) == 1000
    assert "source_references" in result["sources"][0]


def test_inputs_not_mutated():
    data = days()
    original = data.copy(deep=True)
    aggregate_metric(data, "streams")
    daily_series(data, "streams")
    pd.testing.assert_frame_equal(data, original)


def test_missing_metric_has_explanatory_result():
    result = aggregate_metric(pd.DataFrame(), "streams")
    assert result["value"] is None
    assert "No observations" in result["reason"]


def test_asof_rolling_audience_trend_retains_gaps_without_daily_activity():
    data = frame(observation("monthly_listeners", 100), observation("monthly_listeners", 110, start="2026-10-03"))
    series = asof_series(data, "monthly_listeners")
    assert series["value"].iloc[0] == 100
    assert pd.isna(series["value"].iloc[1])
    assert series["value"].iloc[2] == 110
    assert series.attrs["daily"] is False
    assert lag_correlation(series, series, min_observations=3)["correlation"] is None
    assert "daily observations" in lag_correlation(series, series, min_observations=3)["reason"]
    assert daily_series(data, "monthly_listeners")["value"].isna().all()


def test_asof_retains_reported_rolling_window_without_reconstructing_it():
    data = frame(observation("monthly_listeners", 100, start="2026-09-04", end="2026-10-01"))
    series = asof_series(data, "monthly_listeners", "2026-10-01", "2026-10-03")
    assert series["period_start"].iloc[0] == pd.Timestamp("2026-09-04")
    assert series["value"].iloc[0] == 100
    assert series["value"].iloc[1:].isna().all()


def test_unknown_currency_and_engagement_denominator_are_unavailable():
    assert "currency" in aggregate_metric(frame(observation("spend", 100)), "spend")["reason"]
    assert aggregate_metric(frame(observation("spend", 100, dimensions='{"currency":"USD"}')), "spend")["value"] == 100
    assert "denominator" in aggregate_metric(frame(observation("engagement_rate", 5)), "engagement_rate")["reason"]
    assert aggregate_metric(frame(observation("engagement_rate", 5, dimensions='{"denominator":"reach"}')), "engagement_rate")["value"] == 5


def test_null_date_is_unavailable_not_an_exception():
    data = frame(observation(start=pd.NA))
    assert aggregate_metric(data, "streams")["value"] is None


def test_evidence_and_import_timestamps_remain_in_kpi_sources():
    data = frame(observation(evidence_ref="manual screenshot row 2", imported_at="2026-10-22T12:00:00Z", source_references='[{"filename":"source.csv"}]'))
    source = aggregate_metric(data, "streams")["sources"][0]
    assert source["evidence_ref"] == "manual screenshot row 2"
    assert source["imported_at"] == "2026-10-22T12:00:00Z"
    assert source["source_references"]
