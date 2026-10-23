"""Analytical guards; fixtures are synthetic and never become production data."""
import json

import pandas as pd
import pytest

from stats_app.analysis_metrics import (
    complete_sum, daily_periods, follower_change, source_ratio_plot_values, spike_persistence,
)


def history(days=70):
    dates = pd.date_range("2026-01-05", periods=days).strftime("%Y-%m-%d")
    return pd.DataFrame(dict(date=dates, daily_streams=[10] * days,
                             followers_stock=list(range(100, 100+days)),
                             artist_id="fixture-only", snapshot_class="fixture-only",
                             reporting_timezone="UTC", value_status="observed",
                             source_file="synthetic.csv", source_row=range(2, days+2)))


def test_follower_growth_uses_day_before_interval_and_preserves_missing_endpoints():
    frame = history(10)
    result = follower_change(frame, "2026-01-08", "2026-01-12")
    assert result["baseline_date"] == "2026-01-07"
    assert result["baseline"] == 102 and result["current"] == 107
    assert result["net_change"] == 5
    assert result["change_pct"] == pytest.approx(5/102*100)
    assert len(json.loads(result["source_references"])) == 2
    # Intermediate gaps do not invalidate an exact endpoint stock change.
    gapped = frame.loc[frame.date.ne("2026-01-10")]
    assert follower_change(gapped, "2026-01-08", "2026-01-12")["net_change"] == 5
    missing = follower_change(frame, "2026-01-05", "2026-01-12")
    assert missing["net_change"] is None and missing["status"] == "unavailable"
    frame.loc[frame.date.eq("2026-01-07"), "followers_stock"] = 0
    zero = follower_change(frame, "2026-01-08", "2026-01-12")
    assert zero["net_change"] == 107 and zero["change_pct"] is None
    frame.loc[frame.date.eq("2026-01-12"), "value_status"] = "suppressed"
    assert follower_change(frame, "2026-01-08", "2026-01-12")["current"] is None


def test_complete_weeks_match_weekdays_and_incomplete_edges_remain_unavailable():
    frame = history(10)
    periods = daily_periods(frame)
    assert periods.start.tolist() == ["2026-01-05", "2026-01-12"]
    assert periods.end.tolist() == ["2026-01-11", "2026-01-18"]
    assert periods.total.iloc[0] == 70
    assert pd.isna(periods.total.iloc[1]) and periods.missing_days.iloc[1] == 4
    assert periods.status.tolist() == ["complete", "incomplete"]
    assert periods.change_pct.isna().all()
    assert periods.median_daily.tolist() == [10, 10]


def test_28day_blocks_are_disjoint_and_only_full_previous_periods_compare():
    frame = history()
    frame.loc[frame.index >= 42, "daily_streams"] = 20
    periods = daily_periods(frame, period="28day")
    assert periods.status.tolist() == ["incomplete", "complete", "complete"]
    assert periods.total.iloc[1:].tolist() == [280, 560]
    assert periods.absolute_change.iloc[-1] == 280 and periods.change_pct.iloc[-1] == 100
    assert pd.isna(periods.change_pct.iloc[1])
    for previous, current in zip(periods.itertuples(), list(periods.itertuples())[1:]):
        assert (pd.Timestamp(current.start)-pd.Timestamp(previous.end)).days == 1
    assert periods.end.iloc[-1] == frame.date.max()
    assert sum(len(json.loads(v)) for v in periods.source_references) == len(frame)


def test_status_partial_and_nonfinite_values_cannot_establish_complete_totals():
    frame = history(7)
    frame.loc[2, "value_status"] = "unavailable"
    total, observed, expected = complete_sum(frame, "daily_streams", frame.date.min(), frame.date.max())
    assert total is None and observed == 6 and expected == 7
    frame.loc[2, "value_status"] = "observed"
    frame["partial_day"] = False
    frame.loc[6, "partial_day"] = True
    assert daily_periods(frame).partial_days.iloc[0] == 1
    assert pd.isna(daily_periods(frame).total.iloc[0])
    frame["partial_day"] = False
    frame["daily_streams"] = frame.daily_streams.astype(float)
    frame.loc[6, "daily_streams"] = float("inf")
    assert complete_sum(frame, "daily_streams", frame.date.min(), frame.date.max())[0] is None
    with pytest.raises(ValueError, match="start"):
        complete_sum(frame, "daily_streams", "2026-02-01", "2026-01-01")


def test_scopes_duplicates_and_nonadditive_period_sums_are_refused():
    frame = history()
    with pytest.raises(ValueError, match="Ambiguous"):
        daily_periods(pd.concat([frame, frame.iloc[[0]]]))
    frame.loc[0, "reporting_timezone"] = "America/Los_Angeles"
    with pytest.raises(ValueError, match="timezone"):
        follower_change(frame, "2026-01-08", "2026-01-12")
    with pytest.raises(ValueError, match="additive"):
        daily_periods(history(), metric="followers_stock")


def test_spike_response_excludes_spike_and_requires_complete_equal_windows():
    frame = history(70)
    frame.loc[35, "daily_streams"] = 100
    frame.loc[36:42, "daily_streams"] = 20
    result = spike_persistence(frame, top_n=1)
    event = result["events"].iloc[0]
    assert result["status"] == "descriptive" and result["eligible_days"] == 42
    assert event.event_date == frame.date.iloc[35]
    assert event.before_total == 70 and event.after_total == 140
    assert event.absolute_change == 70 and event.change_pct == 100
    assert event.baseline_median == 10 and event.threshold == 10
    assert event.persistence_status == "complete"
    assert "not statistical significance" in result["limitations"]
    # The final day is retained as a spike; no invented post-event history.
    frame.loc[69, "daily_streams"] = 200
    latest = spike_persistence(frame, top_n=1)["events"].iloc[0]
    assert latest.event_date == frame.date.iloc[69]
    assert latest.after_total is None and latest.change_pct is None
    assert latest.persistence_status == "unavailable" and latest.after_observed_days == 0


def test_spike_screen_reports_insufficient_history_and_does_not_reuse_response_windows():
    insufficient = spike_persistence(history(28))
    assert insufficient["status"] == "unavailable" and insufficient["events"].empty
    flat = spike_persistence(history())
    assert flat["status"] == "no_spike_detected"
    frame = history(80)
    frame.loc[[35, 36, 60], "daily_streams"] = [100, 200, 300]
    selected = spike_persistence(frame)["events"]
    assert len(selected) == 2
    assert set(selected.event_date) == {frame.date.iloc[36], frame.date.iloc[60]}


def test_source_ratios_with_unknown_invalid_denominators_remain_unavailable():
    ratios = pd.DataFrame({"date": list("abcde"), "value": [1., 2., 3., 4., 5.]})
    denominators = pd.DataFrame({"date": list("abcd"), "value": [0., -1., float("inf"), 2.]})
    shown, invalid, unknown = source_ratio_plot_values(ratios, denominators, ["date"], ["value"])
    assert invalid == 2 and unknown == 2
    assert shown.value.isna().tolist() == [True, True, True, False, True]
    assert ratios.value.tolist() == [1., 2., 3., 4., 5.]

