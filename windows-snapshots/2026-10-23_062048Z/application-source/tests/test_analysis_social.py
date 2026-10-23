"""Meaningful social aggregation and live Streamlit rendering contracts."""
from dataclasses import asdict
from hashlib import sha256
import io
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from stats_app.analysis_social_metrics import (
    compare_daily, daily_grid, filtered_csv, prepare_daily, prepare_posts, publication_series, summarize_daily,
)
from stats_app.analysis_repository import AnalysisRepository
from stats_app.config import PROJECT_ROOT


DB = PROJECT_ROOT / "data" / "reconciliation" / "staged_analysis" / "analysis.sqlite3"
REAL = pytest.mark.skipif(not DB.exists(), reason="Private cleaned analysis snapshot is not included in Git.")


def series(metric="views", kind="daily_interval_count"):
    return pd.DataFrame([dict(platform_selected="Instagram", selected_account_id="17841454335424545",
        metric_platform_scope="Facebook and Instagram combined", metric=metric, measurement_type=kind,
        reporting_timezone="Pacific Time", snapshot_class="supplement", date=day, value=value,
        value_status=status, partial_day=partial) for day, value, status, partial in [
            ("2026-10-17", 1, "observed", False), ("2026-10-18", 2, "observed", False),
            ("2026-10-19", 3, "observed", False), ("2026-10-20", 4, "observed", False),
            ("2026-10-21", 9, "observed", True)]])


def test_complete_equal_windows_and_partial_day_are_distinct():
    data = series()
    result = compare_daily(data, "2026-10-19", "2026-10-20")
    assert result["current"].total == 7 and result["previous"].total == 3
    assert result["delta"] == 4
    assert result["percent_change"] == pytest.approx(400 / 3)
    partial = compare_daily(data, "2026-10-20", "2026-10-21")
    assert partial["current"].partial_days == 1
    assert partial["current"].total is None and partial["delta"] is None


@pytest.mark.parametrize("metric,kind", [("reach", "daily_unique_count"), ("viewers", "daily_unique_count"),
                                         ("followers", "stock"), ("views", "lifetime_content_snapshot")])
def test_nonadditive_data_never_get_period_total(metric, kind):
    value = summarize_daily(series(metric, kind), "2026-10-19", "2026-10-20")
    assert value.total is None and value.observed_sum is None
    assert value.median_daily == 3.5


def test_missing_raw_zero_is_masked_and_missing_calendar_dates_block_comparison():
    data = series()
    data.loc[2, ["value", "value_status"]] = [0, "missing_date_in_native_export"]
    prepared = prepare_daily(data)
    assert pd.isna(prepared.loc[2, "value"])
    assert data.loc[2, "value"] == 0
    value = summarize_daily(data, "2026-10-19", "2026-10-20")
    assert value.total is None and value.missing_days == 1 and value.observed_sum == 4
    value = summarize_daily(data.loc[data.date.ne("2026-10-20")], "2026-10-19", "2026-10-20")
    assert value.observed_days == 0 and value.missing_days == 2
    grid = daily_grid(data.loc[data.date.ne("2026-10-20")], "2026-10-19", "2026-10-20")
    assert len(grid) == 2 and grid.value.isna().all()


def test_duplicate_and_mixed_scope_records_are_refused():
    data = series()
    with pytest.raises(ValueError, match="Duplicate"):
        summarize_daily(pd.concat([data, data.iloc[[0]]]), "2026-10-17", "2026-10-20")
    data.loc[0, "metric_platform_scope"] = "Facebook"
    with pytest.raises(ValueError, match="Select one"):
        summarize_daily(data, "2026-10-17", "2026-10-20")


def test_canonical_pacific_contract_retains_missing_source_timezone_and_refuses_other_zones():
    data = series()
    data.loc[0, "reporting_timezone"] = None
    assert summarize_daily(data, "2026-10-17", "2026-10-20").total == 10
    assert data.loc[0, "reporting_timezone"] is None
    data.loc[0, "reporting_timezone"] = "UTC"
    with pytest.raises(ValueError, match="Select one"):
        summarize_daily(data, "2026-10-17", "2026-10-20")


def test_publication_counts_do_not_include_lifetime_values_or_colliding_platform_ids():
    posts = pd.DataFrame([dict(platform_selected=platform, post_id="18430983631182631", publication_date="2026-10-01",
        post_type="photo", measurement_type="lifetime_content_snapshot", views=views, views_status="observed")
        for platform, views in [("Facebook", 100), ("Instagram", 500)]])
    counts = publication_series(posts)
    assert counts.retained_posts.sum() == 2
    assert "views" not in counts
    with pytest.raises(ValueError, match="duplicate"):
        prepare_posts(pd.concat([posts, posts.iloc[[0]]]))
    raw = filtered_csv(posts.assign(description="=formula"))
    readback = pd.read_csv(io.BytesIO(raw), dtype=str)
    assert readback.post_id.eq("18430983631182631").all()
    assert readback.description.eq("'=formula").all()


@REAL
def test_every_delivered_social_comparison_reconciles_and_128_nulls_survive():
    repo = AnalysisRepository(DB)
    daily = repo.table("social/account_daily.csv")
    before = daily.copy(deep=True)
    assert len(daily) == 3528
    assert daily.value.isna().sum() == 128
    assert prepare_daily(daily).partial_day.sum() == 12
    audited = repo.table("social/account_period_comparisons.csv")
    for row in audited.itertuples():
        chosen = daily[daily.platform_selected.eq(row.platform_selected) & daily.metric.eq(row.metric)
                       & daily.metric_platform_scope.eq(row.metric_platform_scope)]
        result = compare_daily(chosen, row.current_start, row.current_end)
        for label in ("current", "previous"):
            expected = getattr(row, label + "_total")
            assert result[label].total is None if pd.isna(expected) else result[label].total == pytest.approx(expected)
            assert result[label].observed_days == getattr(row, label + "_observed_days")
    pd.testing.assert_frame_equal(before, daily)
    posts = repo.table("social/posts_latest.csv")
    assert posts.post_id.map(type).eq(str).all()
    assert len(prepare_posts(posts)) == 377
    assert publication_series(posts).retained_posts.sum() == 377


def social_app():
    script = f"""
from stats_app.analysis_repository import AnalysisRepository
from stats_app.analysis_social_ui import render_social
render_social(AnalysisRepository({str(DB)!r}))
"""
    return AppTest.from_string(script, default_timeout=30).run()


def choose(at, label, value, kind="selectbox"):
    next(item for item in getattr(at, kind) if item.label == label).set_value(value).run()
    assert not at.exception, [item.value for item in at.exception]
    assert not at.error, [item.value for item in at.error]
    return at


@REAL
def test_social_activity_scope_partial_gaps_unique_and_downloads_render():
    before = sha256(DB.read_bytes()).hexdigest()
    at = social_app()
    assert not at.exception and not at.error
    assert any("Facebook and Instagram combined" in item.value for item in at.info)
    assert any("2026" in item.value and "Oct 20" in item.value for item in at.caption)
    assert len(at.get("plotly_chart")) == 1
    choose(at, "Activity window", "Latest 90 days", "radio")
    assert at.metric[0].value == "23,270"
    choose(at, "Social activity metric", "reach")
    assert at.metric[0].value == "Unavailable"
    choose(at, "Social activity metric", "follows")
    assert at.metric[0].value == "Unavailable"
    assert any("Coverage gap" in item.value for item in at.warning)
    choose(at, "Social activity metric", "views")
    choose(at, "Include partial source days", True, "checkbox")
    assert at.metric[0].value == "Unavailable"
    assert any("Partial-period view" in item.value for item in at.warning)
    assert any(item.label == "Download filtered records · CSV" for item in at.get("download_button"))
    choose(at, "Social platform", "TikTok")
    assert any("TikTok data unavailable" in item.value for item in at.info)
    assert not at.metric and not at.get("plotly_chart")
    assert sha256(DB.read_bytes()).hexdigest() == before


@REAL
def test_content_publication_age_author_scope_and_audience_render():
    at = social_app()
    choose(at, "Social view", "Content & publishing", "radio")
    assert at.metric[0].value == "125"
    assert len(at.get("plotly_chart")) == 2
    assert any("Lifetime as captured October 22 UTC" in item.value for item in at.info)
    choose(at, "Content author scope", ["verified_collaboration"], "multiselect")
    assert at.metric[0].value == "3"
    choose(at, "Content author scope", ["band_authored"], "multiselect")
    choose(at, "Post formats", ["IG story"], "multiselect")
    assert at.metric[0].value == "126"
    assert any("183 malformed records" in item.value for item in at.warning)
    choose(at, "Social view", "Audience distribution", "radio")
    assert len(at.get("plotly_chart")) == 1
    assert any("no follower counts are reconstructed" in item.value for item in at.info)
    choose(at, "Social view", "Native period & stock evidence", "radio")
    assert any("stock is not new-follower activity" in item.value for item in at.info)
    assert not at.metric and not at.get("plotly_chart")
