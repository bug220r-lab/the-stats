"""Source-only decision suggestions follow selected, complete recording evidence."""
import hashlib
import json

import pandas as pd
import pytest

from stats_app.analysis_social_metrics import DAILY_SCOPE
from stats_app.decision_report import SP, build_report, experiments, markdown_report


class MemoryRepo:
    metadata = {"label": "Synthetic separate source", "analysis_version": "synthetic-other-songs"}

    def __init__(self):
        dates = pd.date_range("2026-01-05", periods=70).strftime("%Y-%m-%d")
        artist = pd.DataFrame(dict(
            date=dates, daily_streams=10, followers_stock=range(100, 170),
            artist_id="fixture-only", snapshot_class="fixture-only", reporting_timezone="UTC",
            value_status="observed", source_file="synthetic.csv", source_row=range(2, 72),
        ))
        tracks = pd.DataFrame([
            dict(song_id=song, recording_label=label, date=day, metric="streams", value=value,
                 snapshot_class="fixture-only", reporting_timezone="UTC", value_status="observed")
            for day in dates
            for song, label, value in [
                ("a", "Synthetic Alpha", 8 if day < "2026-02-16" else 7 if day < "2026-03-02" else 1),
                ("b", "Synthetic Beta", 2 if day < "2026-02-16" else 3 if day < "2026-03-02" else 9),
            ]
        ])
        self.assets = {
            SP + "artist_daily.csv": artist,
            SP + "track_daily_long.csv": tracks,
            SP + "recordings.csv": pd.DataFrame([
                dict(song_id="a", recording_label="Synthetic Alpha"),
                dict(song_id="b", recording_label="Synthetic Beta"),
            ]),
            SP + "artist_period_dashboard.csv": pd.DataFrame(columns=[
                "artist_id", "metric", "start_date", "end_date", "scope", "snapshot_class",
            ]),
            SP + "track_28day_activity_ratios.csv": pd.DataFrame(columns=["chart_start_date", "chart_end_date"]),
            "social/account_daily.csv": pd.DataFrame(columns=[
                *DAILY_SCOPE, "date", "value", "value_status", "partial_day",
            ]),
            SP + "audience_top_countries.csv": pd.DataFrame(),
            SP + "audience_top_cities.csv": pd.DataFrame(),
            "cross_platform/statistical_results.csv": pd.DataFrame({"q_bh_12_tests": [], "inference_eligible": []}),
            "analysis_readiness.csv": pd.DataFrame(),
            SP + "recording_launch_windows.csv": pd.DataFrame(),
        }
        self.tables = list(self.assets)

    def table(self, path):
        frame = self.assets[path].copy()
        frame.attrs["source_sha256"] = hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()
        return frame


def test_report_candidates_follow_selected_source_period_and_changed_rankings():
    repo = MemoryRepo()
    early = build_report(repo, "2026-02-16", "2026-03-01")
    hook, _, excerpts = early["experiments"]
    assert "Synthetic Alpha" in hook["change"]
    assert "98 streams" in hook["candidate_basis"]
    assert "Synthetic Alpha" in excerpts["change"] and "Synthetic Beta" in excerpts["change"]
    assert "Synthetic Beta: +14 streams" in excerpts["candidate_basis"]
    assert excerpts["source_period"] == "2026-02-16 through 2026-03-01 UTC"
    assert excerpts["comparison_period"] == "2026-02-02 through 2026-02-15 UTC"
    early_song = next(finding for finding in early["findings"] if finding["id"] == "song")
    assert "Synthetic Alpha: 98 streams" in early_song["observed"]
    assert "70.00% of artist streams" in early_song["observed"]

    later = build_report(repo, "2026-03-02", "2026-03-15")
    hook, _, excerpts = later["experiments"]
    assert "Synthetic Beta" in hook["change"] and "Synthetic Alpha" not in hook["change"]
    assert "Synthetic Beta: +84 streams" in excerpts["candidate_basis"]
    assert "prospectively chosen matched alternative" in excerpts["change"]
    assert excerpts["source_period"] == "2026-03-02 through 2026-03-15 UTC"
    assert excerpts["comparison_period"] == "2026-02-16 through 2026-03-01 UTC"
    assert "Synthetic Beta" in next(finding["observed"] for finding in later["findings"] if finding["id"] == "song")
    for report in (early, later):
        encoded = json.dumps(report, allow_nan=False)
        text = markdown_report(report)
        for experiment in (report["experiments"][0], report["experiments"][2]):
            assert experiment["change"] in text
            assert experiment["source_period"] in text and experiment["source_period"] in encoded
        assert "Funny Guy" not in encoded and "Waste Away" not in encoded
        assert report["analysis_key"] == "synthetic-other-songs"
        assert "This report does not use TikTok Studio data" in text
        assert "Explore → TikTok" in text


@pytest.mark.parametrize("unavailable", ["missing", "partial"])
def test_incomplete_current_recording_cannot_be_ranked_below_a_complete_recording(unavailable):
    repo = MemoryRepo()
    tracks = repo.assets[SP + "track_daily_long.csv"]
    row = tracks.song_id.eq("a") & tracks.date.eq("2026-02-20")
    if unavailable == "missing":
        tracks.loc[row, "value_status"] = "unavailable"
    else:
        tracks["partial_day"] = False
        tracks.loc[row, "partial_day"] = True
    report = build_report(repo, "2026-02-16", "2026-03-01")
    assert all(finding["id"] != "song" for finding in report["findings"])
    result = report["experiments"]
    for experiment in (result[0], result[2]):
        assert "Synthetic" not in experiment["change"]
        assert "incomplete selected-period coverage" in experiment["candidate_basis"]


def test_incomplete_previous_period_allows_current_demand_but_no_momentum_claim():
    repo = MemoryRepo()
    tracks = repo.assets[SP + "track_daily_long.csv"]
    tracks.loc[tracks.song_id.eq("b") & tracks.date.eq("2026-02-10"), "value_status"] = "missing"
    result = build_report(repo, "2026-02-16", "2026-03-01")["experiments"]
    assert "Synthetic Alpha" in result[0]["change"]
    assert "Synthetic Beta" not in result[2]["change"]
    assert "No momentum candidate selected. The loaded catalog has incomplete preceding-period coverage." in result[2]["candidate_basis"]


@pytest.mark.parametrize("current,previous", [(2, 2), (1, 2), (0, 2)])
def test_flat_declining_and_zero_activity_supply_no_positive_momentum(current, previous):
    repo = MemoryRepo()
    tracks = repo.assets[SP + "track_daily_long.csv"]
    tracks["value"] = previous
    tracks.loc[tracks.date.ge("2026-02-16"), "value"] = current
    report = build_report(repo, "2026-02-16", "2026-03-01")
    excerpts = report["experiments"][2]
    assert "No momentum candidate selected. No positive recording increase is observed." in excerpts["candidate_basis"]
    assert "+" not in excerpts["candidate_basis"]
    if current == 0:
        assert all(finding["id"] != "song" for finding in report["findings"])
        assert "Synthetic" not in report["experiments"][0]["change"]
        assert "Synthetic" not in excerpts["change"]


def test_complete_recording_demand_can_be_reported_without_artist_share():
    repo = MemoryRepo()
    artist = repo.assets[SP + "artist_daily.csv"]
    artist.loc[artist.date.eq("2026-02-20"), "value_status"] = "unavailable"
    report = build_report(repo, "2026-02-16", "2026-03-01")
    finding = next(finding for finding in report["findings"] if finding["id"] == "song")
    assert "Synthetic Alpha: 98 streams" in finding["observed"]
    assert "Artist share is unavailable" in finding["observed"]
    assert "nan%" not in markdown_report(report)


def test_momentum_uses_absolute_change_even_when_previous_total_is_zero():
    repo = MemoryRepo()
    tracks = repo.assets[SP + "track_daily_long.csv"]
    tracks.loc[tracks.song_id.eq("b") & tracks.date.lt("2026-02-16"), "value"] = 0
    report = build_report(repo, "2026-02-16", "2026-03-01")
    assert "Synthetic Beta: +42 streams" in report["experiments"][2]["candidate_basis"]
    assert next(row for row in report["songs"] if row["song_id"] == "b")["change_pct"] is None


@pytest.mark.parametrize("songs", [None, pd.DataFrame(), pd.DataFrame({"current": [12]})])
def test_absent_or_unqualified_recording_evidence_keeps_neutral_templates(songs):
    result = experiments(songs, "2026-03-01", "2026-03-15", "UTC")
    assert "Choose one excerpt prospectively" in result[0]["change"]
    assert "Choose two matched excerpts prospectively" in result[2]["change"]
    assert "No song selected." in result[0]["candidate_basis"]
    assert "No momentum candidate selected." in result[2]["candidate_basis"]
    assert len(result) == 3


def test_unscoped_recordings_do_not_supply_a_song_recommendation():
    result = experiments(pd.DataFrame([dict(
        song_id="a", recording_label="Synthetic Alpha", current=10, previous=5, complete=True,
    )]))
    assert "Synthetic Alpha" not in json.dumps(result)
    assert "Unavailable: no selected reporting interval." == result[2]["source_period"]
