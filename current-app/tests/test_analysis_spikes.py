from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stats_app.analysis_correlation import build_weekly_activity
from stats_app.analysis_repository import AnalysisRepository
from stats_app.analysis_spikes import publications_around_week, rank_spotify_increases


def weekly(values, listeners=None, start="2024-01-01"):
    return pd.DataFrame({"streams": values, "mean_daily_listeners": listeners if listeners is not None else values,
                         "spotify_days": 7, "complete_week": True},
                        index=pd.date_range(start, periods=len(values), freq="W-MON", name="week_start"))


def identity(key="one", dates="2024-01-09", **changes):
    row = dict(identity_key=key, post_id="001234567890123456", platform="Instagram", exposure="instagram_stories",
               strict_band=True, band_authored=True, identity_complete=True, dates=dates, week="2024-01-08",
               date_conflict=False, text="Full source caption", description="Full source caption", permalink="https://example.test/one",
               post_type="IG story", author_evidence="band_authored")
    row.update(changes)
    return row


def test_comparison_precedes_period_filter_and_ties_are_deterministic():
    frame = weekly([10, 30, 50, 40], [1, 4, 5, 6])
    original = frame.copy(deep=True)
    ranked = rank_spotify_increases(frame, start="2024-01-08", end="2024-01-21")
    assert ranked.week_start.tolist() == [pd.Timestamp("2024-01-08"), pd.Timestamp("2024-01-15")]
    assert ranked.iloc[0].prior == 10 and ranked.iloc[0].current == 30
    assert ranked.iloc[0].increase == 20 and ranked.iloc[0]["pct_change"] == 200
    assert ranked.iloc[0].previous_week_start == pd.Timestamp("2024-01-01")
    assert ranked.iloc[0].mean_daily_listeners_increase == 3
    pd.testing.assert_frame_equal(frame, original)


def test_zero_baseline_keeps_absolute_rise_without_infinite_percentage():
    ranked = rank_spotify_increases(weekly([0, 12, 0, 0]))
    assert len(ranked) == 1 and ranked.iloc[0].increase == 12
    assert pd.isna(ranked.iloc[0]["pct_change"])


def test_calendar_gap_and_partial_week_do_not_become_previous_comparators():
    frame = weekly([10, 20, 100, 140, 180, 220])
    frame = frame.drop(pd.Timestamp("2024-01-15"))
    frame.loc["2024-01-29", "spotify_days"] = 6
    ranked = rank_spotify_increases(frame)
    assert ranked.week_start.tolist() == [pd.Timestamp("2024-01-08")]
    assert ranked.attrs["source_calendar_weeks"] == 6


def test_metric_missingness_is_separate_and_invalid_values_cannot_rank():
    frame = weekly([10, 30, np.inf, 100, 130], [1, np.nan, 5, 6, 7])
    result = rank_spotify_increases(frame)
    assert set(result.week_start) == {pd.Timestamp("2024-01-08"), pd.Timestamp("2024-01-29")}
    assert result.loc[result.week_start.eq("2024-01-08"), "mean_daily_listeners_increase"].isna().all()
    listeners = rank_spotify_increases(frame, "mean_daily_listeners")
    assert listeners.week_start.tolist() == [pd.Timestamp("2024-01-22"), pd.Timestamp("2024-01-29")]


def test_partial_requested_boundaries_are_excluded_but_prior_outside_range_is_used():
    frame = weekly([10, 20, 30])
    assert rank_spotify_increases(frame, start="2024-01-09", end="2024-01-21").week_start.tolist() == [pd.Timestamp("2024-01-15")]
    assert rank_spotify_increases(frame, start="2024-01-09", end="2024-01-20").empty
    with pytest.raises(ValueError):
        rank_spotify_increases(frame, start="2024-02-01", end="2024-01-01")


@pytest.mark.parametrize("bad", ["duplicate", "non_monday", "no_completeness", "mixed_artist", "wrong_end"])
def test_invalid_weekly_grain_fails_closed(bad):
    frame = weekly([1, 2, 3])
    if bad == "duplicate":
        frame = pd.concat([frame, frame.iloc[[0]]])
    elif bad == "non_monday":
        frame.index += np.timedelta64(1, "D")
    elif bad == "no_completeness":
        frame = frame.drop(columns="spotify_days")
    elif bad == "mixed_artist":
        frame["artist_id"] = ["one", "two", "one"]
    else:
        frame["week_end"] = frame.index
    with pytest.raises(ValueError):
        rank_spotify_increases(frame)


def test_explicit_week_column_and_empty_valid_result_have_stable_schema():
    frame = weekly([5, 4, 3]).reset_index()
    result = rank_spotify_increases(frame)
    assert result.empty and {"week_start", "prior", "current", "increase", "pct_change"}.issubset(result)
    empty = rank_spotify_increases(pd.DataFrame())
    assert list(empty) == list(result)


def test_identity_dedup_preserves_conflicting_dates_full_text_and_all_links():
    caption = "Complete caption " + "with detail " * 120
    rows = pd.DataFrame([
        identity(dates="2024-01-09", text=caption, description=caption),
        identity(dates="2024-01-10", text="Second retained caption", description="Second retained caption", permalink="https://example.test/two"),
        identity("other-platform", dates="2024-01-10", platform="Facebook", exposure="facebook_posts"),
    ])
    before = rows.copy(deep=True)
    selected = publications_around_week(rows, "2024-01-08", before_weeks=0)
    assert len(selected) == 2  # Bare ID is the same; platform identities remain separate.
    row = selected.set_index("identity_key").loc["one"]
    assert row.dates == "2024-01-09;2024-01-10" and row.date_conflict
    assert caption in row.description and "Second retained caption" in row.description
    assert "https://example.test/one" in row.permalink and "https://example.test/two" in row.permalink
    assert row.timing_status == "week_certain_date_conflict" and row.caption_available
    assert row.relation == "same_week"
    pd.testing.assert_frame_equal(rows, before)


def test_authorship_cross_week_and_unknown_dates_are_excluded():
    rows = pd.DataFrame([
        identity("eligible"), identity("unknown", dates=""), identity("disputed", dates="2024-01-07;2024-01-08"),
        identity("associated", author_evidence="band_authored;associated_account_authorship_unverified"),
        identity("not-band", strict_band=False), identity("incomplete", identity_complete=False),
    ])
    result = publications_around_week(rows, "2024-01-08")
    assert result.identity_key.tolist() == ["eligible"]
    assert result.attrs["excluded_identities"]["conflicting_week"] == 1
    assert result.attrs["excluded_identities"]["unknown_or_invalid_date"] == 1
    assert result.attrs["excluded_identities"]["authorship_or_identity"] == 3


def test_relative_window_search_and_exposure_filters_intersect():
    rows = pd.DataFrame([
        identity("two-before", "2023-12-27", text="Waste Away", description="Waste Away"),
        identity("before", "2024-01-03", text="Funny Guy", description="Funny Guy"),
        identity("same", "2024-01-09", text="Funny Guy", description="Funny Guy"),
        identity("after", "2024-01-16", text="Funny Guy", description="Funny Guy", platform="Facebook", exposure="facebook_posts"),
        identity("too-late", "2024-01-23"),
    ])
    all_rows = publications_around_week(rows, "2024-01-08", before_weeks=2, after_weeks=1)
    assert all_rows.week_offset.tolist() == [-2, -1, 0, 1]
    assert all_rows.relation.tolist() == ["preceding_week", "preceding_week", "same_week", "following_week"]
    narrowed = publications_around_week(rows, "2024-01-08", before_weeks=2, after_weeks=1, exposures=["instagram_stories"], query="FUNNY guy")
    assert narrowed.identity_key.tolist() == ["before", "same"]
    assert publications_around_week(rows, "2024-01-08", exposures=[]).empty
    assert publications_around_week(rows, "2024-01-08", query="[literal]").empty


@pytest.mark.parametrize("text", ["", "  ", "--", "Loading preview…"])
def test_blank_or_ui_placeholder_is_not_a_retained_caption(text):
    result = publications_around_week(pd.DataFrame([identity(text=text, description=text)]), "2024-01-08")
    assert not result.iloc[0].caption_available
    assert result.iloc[0].caption_availability == "not_available_in_retained_source"


def test_invalid_selection_and_identity_collision_raise():
    rows = pd.DataFrame([identity()])
    with pytest.raises(ValueError):
        publications_around_week(rows, "2024-01-09")
    with pytest.raises(ValueError):
        publications_around_week(rows, "2024-01-08", before_weeks=3)
    with pytest.raises(ValueError):
        publications_around_week(rows, "2024-01-08", exposures=["facebook_stories"])
    with pytest.raises(ValueError):
        publications_around_week(pd.DataFrame([identity(), identity(platform="Facebook")]), "2024-01-08")


def test_current_source_spike_rankings_and_timing_drilldown():
    path = Path(__file__).resolve().parents[1] / "data/reconciliation/meta_content_20261023/staged/analysis.sqlite3"
    if not path.exists():
        pytest.skip("Immutable reviewed source not present in this checkout.")
    bundle = build_weekly_activity(AnalysisRepository(path))
    streams = rank_spotify_increases(bundle["weekly"])
    assert streams.week_start.head(8).dt.strftime("%Y-%m-%d").tolist() == [
        "2025-08-04", "2026-03-09", "2025-10-13", "2025-07-14", "2026-02-16", "2024-05-27", "2024-06-03", "2026-02-23"]
    assert streams.increase.head(8).tolist() == [1703, 711, 689, 653, 639, 606, 547, 500]
    assert streams.iloc[0].current == 3030 and streams.iloc[0].prior == 1327
    listeners = rank_spotify_increases(bundle["weekly"], "mean_daily_listeners")
    assert listeners.week_start.head(3).dt.strftime("%Y-%m-%d").tolist() == ["2025-08-04", "2026-02-23", "2024-06-03"]
    assert listeners.iloc[0].increase == pytest.approx(95.42857142857143)
    february = publications_around_week(bundle["identities"], "2026-02-23", before_weeks=0)
    announced = february.loc[february.dates.str.contains("2026-02-25", regex=False)]
    assert not announced.empty and announced.relation.eq("same_week").all()
    assert any("video" in text.casefold() for text in announced.description)
    assert february.identity_key.is_unique
