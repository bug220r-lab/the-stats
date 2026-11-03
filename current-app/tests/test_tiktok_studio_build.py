"""Synthetic source controls for the Studio package builder, without private data."""
from copy import deepcopy
from datetime import date, timedelta
import json

import pytest

from scripts import build_tiktok_studio_collection as builder


def label(day):
    return day.strftime("%B ") + str(day.day)


def test_calendar_assigns_year_from_bounds_without_timezone_conversion():
    start = date(2025, 10, 26)
    rows = [{"Date": label(start + timedelta(days=i))} for i in range(365)]
    result = builder.label_calendar(rows)
    assert result[0] == "2025-10-26"
    assert result[-1] == "2026-10-25"
    assert result[67] == "2026-01-01"
    assert len(set(result)) == 365


@pytest.mark.parametrize("mutation", ["repeated_fall_label", "missing_spring_label", "one_day_shift"])
def test_conflicting_calendar_labels_are_rejected_instead_of_repaired(mutation):
    start = date(2025, 10, 26)
    days = [start + timedelta(days=i) for i in range(365)]
    rows = [{"Date": label(day)} for day in days]
    if mutation == "repeated_fall_label":
        rows[8]["Date"] = "November 2"
    elif mutation == "missing_spring_label":
        index = days.index(date(2026, 3, 8))
        rows[index]["Date"] = "March 9"
    else:
        rows = [{"Date": label(day + timedelta(days=1))} for day in days]
    with pytest.raises(ValueError, match="Native calendar mismatch"):
        builder.label_calendar(rows)


def test_hourly_calendar_requires_complete_native_day_groups():
    rows = [{"Date": "October 25", "Hour": str(hour)} for hour in range(24)]
    assert builder.label_calendar(rows, repeats=24) == ["2026-10-25"] * 24
    with pytest.raises(ValueError, match="Incomplete reporting-day groups"):
        builder.label_calendar(rows[:-1], repeats=24)


@pytest.fixture
def source_rows(monkeypatch):
    # Two compact synthetic days, retaining the builder's frozen-source control
    # total so checks exercise normalization without reading private exports.
    rows = {
        "Overview.csv": [
            {"Date": "October 24", "Video Views": "514995", "Profile Views": "3", "Likes": "4", "Comments": "-3", "Shares": "1"},
            {"Date": "October 25", "Video Views": "0", "Profile Views": "0", "Likes": "0", "Comments": "0", "Shares": "0"},
        ],
        "Viewers.csv": [
            {"Date": "October 24", "Total Viewers": "10", "New Viewers": "6", "Returning Viewers": "4"},
            {"Date": "October 25", "Total Viewers": "undefined", "New Viewers": "0", "Returning Viewers": "0"},
        ],
        "FollowerHistory.csv": [
            {"Date": "October 24", "Followers": "100", "Difference in followers from previous day": "1"},
            {"Date": "October 25", "Followers": "98", "Difference in followers from previous day": "-2"},
        ],
        "FollowerActivity.csv": [{"Date": "October 25", "Hour": str(hour), "Active followers": "0"} for hour in range(24)],
    }
    monkeypatch.setattr(builder, "native", lambda _path, member: deepcopy(rows[member]))
    return rows


def test_daily_normalization_preserves_signed_comments_unknown_total_and_zeros(source_rows):
    tables = builder.daily_tables()
    activity = tables["account_daily"][0]
    assert [r["comments_signed_native"] for r in activity] == [-3, 0]
    assert [r["comments_raw"] for r in activity] == ["-3", "0"]
    assert all(r["comments_status"] == "source_signed_net_semantics_unverified" for r in activity)
    assert sum(r["video_views"] for r in activity) == 514995
    assert activity[1]["video_views"] == 0
    viewer = tables["viewer_daily"][0][1]
    assert viewer["total_viewers"] == ""
    assert viewer["total_viewers_raw"] == "undefined"
    assert viewer["total_viewers_status"] == "unavailable_native_undefined"
    assert viewer["new_viewers"] == viewer["returning_viewers"] == 0
    followers = tables["follower_daily"][0]
    assert [r["net_followers"] for r in followers] == [1, -2]
    # First delta references an earlier unobserved stock, so it is not the same
    # calculation as last stock minus first stock.
    assert sum(r["net_followers"] for r in followers) == -1
    assert followers[-1]["followers"] - followers[0]["followers"] == -2
    for name, (rows, source) in tables.items():
        assert all(r["reporting_timezone"] == "unknown" for r in rows)
        assert all(r["source_zip"] == source.as_posix() for r in rows)
        assert [r["source_record"] for r in rows] == list(range(2, len(rows) + 2))
        assert all(r["source_member"] in source_rows for r in rows)
        assert rows[-1]["date"] == "2026-10-25"


def test_daily_normalization_rejects_shifted_follower_difference(source_rows):
    source_rows["FollowerHistory.csv"][1]["Difference in followers from previous day"] = "0"
    with pytest.raises((AssertionError, ValueError)):
        builder.daily_tables()


def test_daily_normalization_rejects_changed_control_total(source_rows):
    source_rows["Overview.csv"][0]["Video Views"] = "514996"
    with pytest.raises((AssertionError, ValueError)):
        builder.daily_tables()


@pytest.mark.parametrize("raw,exact", [("16,423", 16423), ("0", 0), ("-2", -2), ("341.8K", ""), ("<1", ""), ("--", "")])
def test_display_precision_does_not_promote_abbreviations_or_drop_signed_counts(raw, exact):
    assert builder.exact_display(raw) == exact


PANEL_STEMS = [
    "004-overview-365", "017-overview-7", "007-viewers-365", "008-viewers-60",
    "009-viewers-28", "010-viewers-7", "012b-followers-365-loaded",
    "013-followers-60", "014-followers-28", "015-followers-7",
    "030-monetization-7", "031-monetization-30", "032-monetization-60",
]


@pytest.fixture
def panel_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    evidence = tmp_path / builder.EVIDENCE
    evidence.mkdir(parents=True)
    for stem in PANEL_STEMS:
        (evidence / f"{stem}.txt").write_text("", encoding="utf-8")
        (evidence / f"{stem}.json").write_text(json.dumps({
            "captured_at": "2026-10-27T00:35:00Z",
            "source_url": "https://www.tiktok.com/tiktokstudio/analytics",
        }), encoding="utf-8")

    def write(stem, text):
        (evidence / f"{stem}.txt").write_text(text, encoding="utf-8")

    return write


def test_account_panel_metrics_keep_exactness_comparison_and_source_context(panel_sources):
    panel_sources("017-overview-7", '- button "Video views 4.9K -1.4K (-21.8%)":\n- button "Shares 0 0 (0.0%)":\n')
    panel_sources("015-followers-7", '- button "Total followers 16K All time":\n- button "Net followers -2 -13 (-118.2%)":\n')
    metrics, _, _ = builder.account_panels()
    by_key = {(r["panel_id"], r["metric"]): r for r in metrics}
    views = by_key[("017-overview-7", "Video views")]
    assert views["value_raw"] == "4.9K" and views["value_exact"] == ""
    assert views["comparison_raw"] == "-1.4K (-21.8%)"
    assert "4.9K -1.4K (-21.8%)" in views["button_display_raw"]
    assert by_key[("017-overview-7", "Shares")]["value_exact"] == 0
    net = by_key[("015-followers-7", "Net followers")]
    assert net["value_exact"] == -2 and net["value_status"] == "exact_displayed"
    assert net["comparison_raw"] == "-13 (-118.2%)"
    stock = by_key[("015-followers-7", "Total followers")]
    assert stock["value_exact"] == "" and stock["scope"] == "all-time follower stock"
    for row in metrics:
        assert row["source_file"].endswith(row["panel_id"] + ".txt")
        assert row["captured_at"] == "2026-10-27T00:35:00Z"
        assert row["source_url"].endswith("/analytics")
        assert row["reporting_timezone"] == "unknown"


def test_account_breakdowns_preserve_percentage_bounds_and_native_population(panel_sources):
    body = '- generic: Locations\n- generic: Netherlands\n- generic: <1%\n- generic: Others\n- generic: 26.9%\n'
    panel_sources("015-followers-7", body)
    panel_sources("010-viewers-7", body)
    _, breakdowns, _ = builder.account_panels()
    assert len(breakdowns) == 4
    assert {r["family"] for r in breakdowns} == {"viewers", "followers"}
    for row in breakdowns:
        if row["label"] == "Netherlands":
            assert row["value_raw"] == "<1%" and row["value_status"] == "bounded_percentage"
        else:
            assert row["value_raw"] == "26.9%" and row["value_status"] == "displayed_rounded_percentage"
        assert row["source_file"].endswith(row["panel_id"] + ".txt")


@pytest.mark.parametrize("stem,message", [
    ("007-viewers-365", "In the last 7 days, your viewers were most active on Oct 23, between 1pm to 2pm"),
    ("012b-followers-365-loaded", "Over the past 7 days, most of your followers were active on October 25 at 5pm."),
])
def test_activity_notice_does_not_inherit_annual_reporting_scope(panel_sources, stem, message):
    panel_sources(stem, '- generic: Most active times\n- generic: ' + message + '\n')
    _, _, notes = builder.account_panels()
    assert len(notes) == 1
    note = notes[0]
    assert note["reporting_start"] == "2026-10-19"
    assert note["reporting_end"] == "2026-10-25"
    assert "7 days" in note["note_raw"]
    assert note["source_file"].endswith(stem + ".txt")


def test_monetization_observed_zero_keeps_currency_and_unknown_dates(panel_sources):
    panel_sources("030-monetization-7", '  - button "Total $0.00 0% (Last 7 days)":\n  - button "LIVE rewards $0.00 0% (Last 7 days)":\n')
    metrics, _, _ = builder.account_panels()
    assert len(metrics) == 2
    for row in metrics:
        assert row["value_raw"] == "$0.00" and row["value_exact"] == "0.00"
        assert row["value_status"] == "displayed_currency"
        assert row["reporting_start"] == row["reporting_end"] == ""
        assert "USD" in row["scope"]


def test_viewer_affinity_keeps_third_party_links_separate_from_owned_posts(panel_sources):
    panel_sources("007-viewers-365", '''- link "Back to TikTok":
  - /url: https://www.tiktok.com
- generic: Posts your viewers also viewed
- 'link "1 An unrelated creator''s post 1.8B views Example Creator"':
  - /url: /@examplecreator/video/012345
  - generic: "1"
- generic: Creators your viewers also watched
- link "Example Creator 2.6M followers":
  - /url: /@examplecreator
- generic: Gender
- link "Help":
  - /url: /help
''')
    rows = builder.account_affinity()
    assert len(rows) == 2
    assert [r["observed_url"] for r in rows] == ["/@examplecreator/video/012345", "/@examplecreator"]
    assert [r["section"] for r in rows] == ["Posts your viewers also viewed", "Creators your viewers also watched"]
    assert "1.8B views" in rows[0]["link_display_raw"]
    assert "2.6M followers" in rows[1]["link_display_raw"]
    for row in rows:
        assert row["window_days"] == 365
        assert row["source_file"].endswith("007-viewers-365.txt")
        assert row["captured_at"] == "2026-10-27T00:35:00Z"
        assert "third-party" in row["scope"] and "not owned-post activity" in row["scope"]
        assert "post_id" not in row and "account" not in row
