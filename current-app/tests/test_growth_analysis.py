"""Coverage and accounting contracts for the live growth diagnostic model."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

from stats_app.growth_analysis import (
    PANEL_KEYS, SP, build_growth_report, paired_periods, playback_source_comparison,
    recording_contributions, release_age_means, direction_context,
)


@pytest.fixture
def frames():
    dates = pd.date_range("2026-01-01", periods=8).strftime("%Y-%m-%d")
    recordings = pd.DataFrame([dict(song_id="a", recording_label="Same title · A", first_released="2026-01-01"),
                               dict(song_id="b", recording_label="Same title · B", first_released="2026-01-01")])
    track = pd.DataFrame([dict(song_id=song, recording_label=label, date=day, metric="streams", value=value,
                               value_status="observed", reporting_timezone="UTC", snapshot_class="test")
                          for song, label, values in [("a","Same title · A",[1]*4+[3]*4), ("b","Same title · B",[2]*4+[1]*4)]
                          for day, value in zip(dates, values)])
    artist = track.groupby("date", as_index=False).value.sum().rename(columns={"value":"daily_streams"})
    artist["value_status"] = "observed"
    return artist, track, recordings


def test_signed_contributions_are_identity_based_and_reconcile(frames):
    artist, track, recordings = frames
    report = recording_contributions(track, recordings, artist, paired_periods("2026-01-05", "2026-01-08"))
    rows = report.set_index("song_id")
    assert rows.loc["a", "change"] == 8 and rows.loc["b", "change"] == -4
    assert rows.loc["a", "share_of_artist_net_change_pct"] == 200
    assert rows.loc["b", "share_of_artist_net_change_pct"] == -100
    assert report.accounting_status.eq("reconciled").all()
    subset = recording_contributions(track, recordings, artist, paired_periods("2026-01-05", "2026-01-08"), song_ids=["a"])
    assert len(subset) == 1 and subset.iloc[0].share_of_artist_net_change_pct == 200


def test_missing_invalid_status_and_partial_values_never_zero_fill(frames):
    artist, track, recordings = frames
    track.loc[(track.song_id == "a") & (track.date == "2026-01-05"), "value_status"] = "unavailable"
    report = recording_contributions(track, recordings, artist, paired_periods("2026-01-05", "2026-01-08"))
    row = report.set_index("song_id").loc["a"]
    assert pd.isna(row.current) and pd.isna(row.change)
    assert row.current_observed_days == 3
    assert report.share_of_artist_net_change_pct.isna().all()
    track.loc[:, "partial_day"] = False
    track.loc[0, "partial_day"] = True
    assert pd.isna(recording_contributions(track, recordings, artist, paired_periods("2026-01-05", "2026-01-08")).set_index("song_id").loc["a", "previous"])


def test_zero_denominator_and_zero_net_change_withhold_shares(frames):
    artist, track, recordings = frames
    track.loc[track.date < "2026-01-05", "value"] = 0
    artist = track.groupby("date", as_index=False).value.sum().rename(columns={"value":"daily_streams"})
    report = recording_contributions(track, recordings, artist, paired_periods("2026-01-05", "2026-01-08"))
    assert report.change_pct.isna().all()
    track.loc[track.date >= "2026-01-05", "value"] = 0
    artist["daily_streams"] = 0
    report = recording_contributions(track, recordings, artist, paired_periods("2026-01-05", "2026-01-08"))
    assert report.current.eq(0).all() and report.share_of_artist_net_change_pct.isna().all()


def test_duplicate_or_incompatible_grain_refused(frames):
    artist, track, recordings = frames
    period = paired_periods("2026-01-05", "2026-01-08")
    with pytest.raises(ValueError, match="duplicate"):
        recording_contributions(pd.concat([track, track.iloc[:1]]), recordings, artist, period)
    track.loc[0, "reporting_timezone"] = "America/Los_Angeles"
    with pytest.raises(ValueError, match="UTC"):
        recording_contributions(track, recordings, artist, period)


def source_fixture():
    panel = ("artist", "artist-id", "Worldwide", "retained", "2026-01-01", "2026-01-08", "streams")
    rows = []
    for day in pd.date_range("2026-01-01", periods=8).strftime("%Y-%m-%d"):
        rows.append(dict(zip(PANEL_KEYS, panel), Date=day, **{"All active sources":3,"Active child":3,"All programmed sources":2,"Programmed child":2,"Other":1}))
    return pd.DataFrame(rows, columns=[*PANEL_KEYS, "Date", "All active sources", "Active child", "All programmed sources", "Programmed child", "Other"]), panel


def test_source_parents_and_children_stay_separate_and_incomplete_explicit():
    source, panel = source_fixture()
    period = paired_periods("2026-01-05", "2026-01-08")
    result, note = playback_source_comparison(source, period, panel)
    assert len(result) == 5
    assert result.loc[result.hierarchy_role.eq("exclusive_parent"), "current"].sum() == 24
    assert "must not be added" in note
    assert result.share_of_net_change_pct.isna().all()
    broken = source.copy()
    broken.loc[0, "Active child"] = 2
    result, note = playback_source_comparison(broken, period, panel)
    assert result.empty and "do not reconcile" in note
    result, note = playback_source_comparison(source.iloc[1:], period, panel)
    assert result.previous.isna().all() and "completely cover" in note


def test_release_age_daily_means_and_incomplete_bands(frames):
    _, track, recordings = frames
    ages = release_age_means(track, recordings, bands=((0,3),(4,7),(8,12)))
    song = ages.loc[ages.song_id.eq("a")].set_index("age_start")
    assert song.loc[0, "streams_per_day"] == 1
    assert song.loc[4, "streams_per_day"] == 3
    assert pd.isna(song.loc[8, "streams"]) and song.loc[8,"observed_days"] == 0


def test_recent_and_longer_direction_keep_separate_windows_and_incomplete_status():
    days = pd.date_range("2026-01-01", periods=180).strftime("%Y-%m-%d")
    artist = pd.DataFrame(dict(date=days, daily_streams=[10]*90+[1]*62+[2]*28))
    recent, longer = direction_context(artist,days[-1])
    assert recent["change"] > 0 and longer["change"] < 0
    assert recent["period"]["days"]==28 and longer["period"]["days"]==90
    assert recent["period"]["start"]!=longer["period"]["start"]
    recent, longer = direction_context(artist.iloc[1:],days[-1])
    assert recent["coverage_status"]=="complete"
    assert longer["coverage_status"]=="unavailable_incomplete_coverage" and longer["change"] is None
    class Repo:
        registered_key="context-test"
        metadata={}
        tables={SP+"artist_daily.csv":artist,
                SP+"track_daily_long.csv":pd.DataFrame(dict(song_id="one",recording_label="Example",date=days,metric="streams",value=artist.daily_streams)),
                SP+"recordings.csv":pd.DataFrame([dict(song_id="one",recording_label="Example",first_released=days[0])])}
        def table(self,path):
            return self.tables[path].copy()
    repo=Repo()
    report=build_growth_report(repo,days[-7],days[-1],include_details=False)
    finding=next(item for item in report["findings"] if item["id"]=="context")
    assert [item["days"] for item in finding["comparison_context"]]==[28,90]
    assert finding["period"]["start"]!=report["period"]["start"]
    repo.tables[SP+"artist_daily.csv"]=artist.iloc[1:].copy()
    missing=build_growth_report(repo,days[-7],days[-1],include_details=False)
    assert not any(item["id"]=="context" for item in missing["findings"])


def test_fingerprint_and_findings_follow_sources_version_period_and_selection(frames):
    artist, track, recordings = frames
    class Repo:
        registered_key = "test-version"
        metadata = {}
        tables = {SP+"artist_daily.csv":artist, SP+"track_daily_long.csv":track, SP+"recordings.csv":recordings}
        def table(self, name):
            return self.tables[name].copy()
    repo = Repo()
    first = build_growth_report(repo,"2026-01-05","2026-01-08")
    second = build_growth_report(repo,"2026-01-05","2026-01-08",song_ids=["b"])
    assert first["fingerprint"] != second["fingerprint"]
    assert "Same title · B" in second["findings"][1]["observed_statement"]
    assert all(f["source_version"] == "test-version" and f["period"]["start"] == "2026-01-05" for f in first["findings"])
    assert all(f["interpretation"] and f["input_fingerprint"]==first["fingerprint"] and f["evidence"] for f in first["findings"])
    repo.registered_key = "new-version"
    assert build_growth_report(repo,"2026-01-05","2026-01-08")["fingerprint"] != first["fingerprint"]
    with pytest.raises(ValueError, match="nonoverlapping"):
        paired_periods("2026-01-05","2026-01-08","2026-01-04","2026-01-05")


def test_saved_slowdown_regression_without_importing_writer_scripts():
    from stats_app.analysis_repository import load_registered_analysis
    from stats_app.config import load_settings, PROJECT_ROOT
    repo = load_registered_analysis(load_settings().data_dir)
    if repo is None:
        pytest.skip("Private immutable source unavailable")
    before = sha256(repo.db_path.read_bytes()).hexdigest()
    expected_path = PROJECT_ROOT/"outputs/spotify_slowdown_20261025/recordings/recording_contributions.csv"
    if not expected_path.is_file():
        pytest.skip("Historical independent regression evidence unavailable")
    expected = pd.read_csv(expected_path).loc[lambda d:d.comparison.eq("primary13weeks")].set_index("song_id")
    report = build_growth_report(repo,"2026-07-20","2026-10-18")
    actual = report["recordings"].set_index("song_id")
    pd.testing.assert_series_equal(actual.current.sort_index(),expected.streams_current.sort_index(),check_names=False,check_dtype=False)
    pd.testing.assert_series_equal(actual.change.sort_index(),expected.streams_delta.sort_index(),check_names=False,check_dtype=False)
    assert report["growth"]["current"] == 13838 and report["growth"]["previous"] == 20153
    assert sha256(repo.db_path.read_bytes()).hexdigest() == before
