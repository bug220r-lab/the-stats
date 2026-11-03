"""Behavioral checks for source-qualified publication/Spotify exploration."""
from pathlib import Path
import json
import shutil

import numpy as np
import pandas as pd
import pytest

from stats_app.analysis_correlation import (
    DEFAULT_ANALYSIS_DIR, SOURCE_PATHS, OUTCOMES, REVIEWED_EXPOSURES,
    build_weekly_activity, correlation_pairs, describe_association, load_reviewed_results,
    publication_identities, select_complete_weeks, weekly_publications, weekly_spotify,
)
from stats_app.analysis_repository import AnalysisRepository

ROOT = Path(__file__).resolve().parents[1]


def observation(key="story", day="2024-01-10", **changes):
    row = dict(identity_key=key, identity_complete=True, post_id="001234567890123456", platform_selected="Instagram",
               post_type="IG story", author_scope="band_authored", publication_date=day,
               description="A retained publication", permalink="https://example.test/post")
    row.update(changes)
    return row


def daily_frame(days=28):
    return pd.DataFrame(dict(date=pd.date_range("2024-01-01", periods=days).strftime("%Y-%m-%d"),
        artist_id="artist", snapshot_class="one", reporting_timezone="UTC", value_status="observed",
        daily_streams=np.arange(days)+1, daily_listeners=2, daily_saves=1, daily_playlist_adds=3,
        followers_stock=np.arange(days)+100))


def test_dedup_and_positive_native_author_evidence_survives_unknown_manual_evidence():
    observations = pd.DataFrame([
        observation(), observation(author_scope="selected_account_detail_authorship_unverified"),
        observation(author_scope="selected_account_grid_authorship_unverified"),
        observation("other-platform", platform_selected="Facebook", post_type="Photo"),
        observation("associated"), observation("associated", author_scope="associated_account_authorship_unverified"),
        observation("collaboration", author_scope="verified_collaboration"),
        observation("unknown", author_scope="unknown"),
        observation("unresolved", identity_complete=False),
    ])
    identities = publication_identities(observations).set_index("identity_key")
    assert identities.loc["story", "strict_band"]
    assert identities.loc["story", "observation_count"] == 3
    assert identities.loc["story", "post_id"] == "001234567890123456"
    assert identities.loc["story", "description"] == identities.loc["story", "text"]
    assert identities.loc["other-platform", "strict_band"]
    assert not identities.loc[["associated", "collaboration", "unknown", "unresolved"], "strict_band"].any()
    assert len(identities) == 6  # Same bare ID on another platform is a distinct publication.


def test_week_certain_conflicts_count_once_but_cross_week_disputes_are_missing():
    identities = publication_identities(pd.DataFrame([
        observation("first", "2024-01-01"), observation("last", "2024-02-04"),
        observation("same", "2024-01-10"), observation("same", "2024-01-12"),
        observation("cross", "2024-01-21"), observation("cross", "2024-01-22"),
    ]))
    same = identities.set_index("identity_key").loc["same"]
    assert same.date_conflict and same.week == "2024-01-08"
    counts = weekly_publications(identities, pd.date_range("2024-01-01", periods=5, freq="W-MON"))
    assert counts.loc["2024-01-08", "instagram_stories"] == 1
    assert counts.loc[["2024-01-15", "2024-01-22"], "instagram_stories"].isna().all()
    assert counts.loc["2024-01-22", "instagram_stories_status"] == "ambiguous_publication_week"
    assert counts.facebook_posts.isna().all()  # No Facebook evidence is not a zero series.


def test_publication_edges_and_missing_dates_remain_unknown():
    identities = publication_identities(pd.DataFrame([
        observation("first", "2024-01-03"), observation("last", "2024-01-25"), observation("undated", "")
    ]))
    counts = weekly_publications(identities, pd.date_range("2024-01-01", periods=5, freq="W-MON"))
    assert counts.loc[["2024-01-01", "2024-01-22", "2024-01-29"], "instagram_stories"].isna().all()
    assert counts.loc["2024-01-08", "instagram_stories"] == 0
    assert counts.loc["2024-01-08", "instagram_stories_status"] == "retained_count_only"
    assert counts.attrs["series"]["instagram_stories"]["unknown_date_identities"] == 1
    assert counts.attrs["series"]["instagram_stories"]["last_complete_publication_week"] == "2024-01-15"


def test_spotify_aggregation_keeps_daily_audience_mean_and_signed_balance_changes():
    daily = daily_frame(21)
    daily.loc[14:, "followers_stock"] = 90  # A real net loss at the start of the third week.
    weekly = weekly_spotify(daily)
    assert weekly.loc["2024-01-01", "streams"] == 28
    assert weekly.loc["2024-01-01", "mean_daily_listeners"] == 2  # Not the weekly sum 14.
    assert weekly.loc["2024-01-08", "saves"] == 7
    assert weekly.loc["2024-01-08", "playlist_adds"] == 21
    assert np.isnan(weekly.loc["2024-01-01", "net_followers"])
    assert weekly.loc["2024-01-08", "net_followers"] == 7
    assert weekly.loc["2024-01-15", "net_followers"] == -23


def test_absent_day_prevents_complete_total_and_does_not_bridge_follower_stock_gap():
    daily = daily_frame(21).drop(index=6)
    weekly = weekly_spotify(daily)
    assert weekly.loc["2024-01-01", "spotify_days"] == 6
    assert weekly.loc["2024-01-01", list(OUTCOMES)].isna().all()
    assert np.isnan(weekly.loc["2024-01-08", "net_followers"])
    assert weekly.loc["2024-01-15", "net_followers"] == 7
    chosen = select_complete_weeks(weekly, "2024-01-01", "2024-01-21")
    assert chosen.index.strftime("%Y-%m-%d").tolist() == ["2024-01-08", "2024-01-15"]
    assert weekly.attrs["coverage"]["missing_calendar_days"] == 1


def test_numeric_missing_and_partial_status_do_not_become_zero():
    daily = daily_frame(14)
    daily.loc[2, "daily_saves"] = np.nan
    daily["daily_streams_status"] = "observed"
    daily.loc[9, "daily_streams_status"] = "unavailable"
    weekly = weekly_spotify(daily)
    assert np.isnan(weekly.loc["2024-01-01", "saves"])
    assert weekly.loc["2024-01-01", "streams"] == 28
    assert np.isnan(weekly.loc["2024-01-08", "streams"])
    daily["partial_day"] = "false"
    daily.loc[0, "partial_day"] = "true"
    assert weekly_spotify(daily).iloc[0][list(OUTCOMES)].isna().all()


@pytest.mark.parametrize("mutation", ["duplicate", "mixed_artist", "mixed_vintage", "timezone"])
def test_spotify_mixed_grains_fail_closed(mutation):
    daily = daily_frame(14)
    if mutation == "duplicate":
        daily = pd.concat([daily, daily.iloc[[0]]])
    else:
        column, value = {"mixed_artist": ("artist_id", "other"), "mixed_vintage": ("snapshot_class", "other"), "timezone": ("reporting_timezone", "Pacific Time")}[mutation]
        daily.loc[0, column] = value
    with pytest.raises(ValueError):
        weekly_spotify(daily)


def test_date_selection_excludes_partial_calendar_boundaries():
    weekly = weekly_spotify(daily_frame(28))
    assert select_complete_weeks(weekly, "2024-01-02", "2024-01-21").index.strftime("%Y-%m-%d").tolist() == ["2024-01-08", "2024-01-15"]
    assert select_complete_weeks(weekly, "2024-01-09", "2024-01-20").empty
    with pytest.raises(ValueError):
        select_complete_weeks(weekly, "2024-02-01", "2024-01-01")


def test_changes_and_lag_are_calendar_preserving_across_missing_weeks():
    weekly = pd.DataFrame({"facebook_posts": [1, 2, 8, 16, 32], "streams": [10, 20, 80, 160, 320]},
                          index=pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-22", "2024-01-29", "2024-02-05"]))
    same = correlation_pairs(weekly, "facebook_posts", "streams")
    assert same.index.strftime("%Y-%m-%d").tolist() == ["2024-01-08", "2024-01-29", "2024-02-05"]
    later = correlation_pairs(weekly, "facebook_posts", "streams", lag=1)
    assert later.index.strftime("%Y-%m-%d").tolist() == ["2024-01-29"]
    assert later.iloc[0].target_week == pd.Timestamp("2024-02-05")
    assert later.iloc[0].x == pytest.approx(np.log1p(16)-np.log1p(8))
    assert later.iloc[0].y == pytest.approx(np.log1p(320)-np.log1p(160))


def test_signed_follower_transform_and_constant_or_short_series():
    index = pd.date_range("2024-01-01", periods=6, freq="W-MON")
    weekly = pd.DataFrame({"facebook_posts": [1, 2, 1, 4, 3, 2], "net_followers": [-5, 0, 2, -1, 4, 0], "streams": 20}, index=index)
    pairs = correlation_pairs(weekly, "facebook_posts", "net_followers")
    assert pairs.iloc[0].y == pytest.approx(np.arcsinh(0)-np.arcsinh(-5))
    description = describe_association(weekly, "facebook_posts", "streams")
    assert description["status"] == "constant_series" and np.isnan(description["rho"])
    assert describe_association(weekly.iloc[:3], "facebook_posts", "net_followers")["status"] == "insufficient_pairs"
    with pytest.raises(ValueError):
        correlation_pairs(weekly, "facebook_posts", "net_followers", lag=2)


@pytest.fixture(scope="module")
def actual_repo():
    path = ROOT / "data/reconciliation/meta_content_20261023/staged/analysis.sqlite3"
    if not path.exists():
        pytest.skip("Retained reviewed integration source is unavailable in this checkout.")
    return AnalysisRepository(path)


def test_reviewed_104_week_golden_reproduces_all_descriptive_estimates(actual_repo):
    data = build_weekly_activity(actual_repo, "2024-01-01", "2025-12-28")
    weekly = data["weekly"]
    assert len(weekly) == 104
    assert weekly.streams.sum() == 42948
    assert weekly.facebook_posts.sum() == 306
    assert weekly.instagram_stories.sum() == 594
    assert weekly.facebook_posts.notna().all() and weekly.instagram_stories.notna().all()
    assert weekly.instagram_feed.isna().any()  # Historical feed availability cannot become zero activity.
    reviewed = pd.read_csv(DEFAULT_ANALYSIS_DIR / "correlations.csv")
    for row in reviewed.itertuples():
        estimate = describe_association(weekly, row.exposure, row.outcome, int(row.lag_weeks))
        assert estimate["n"] == row.n
        assert estimate["rho"] == pytest.approx(row.rho, abs=1e-12)
        assert estimate["rho_levels"] == pytest.approx(row.rho_levels, abs=1e-12)
    assert data["coverage"]["week_certain_date_conflicts"] == 4
    json.dumps(data["coverage"])  # UI details must be plain serializable metadata.
    full = build_weekly_activity(actual_repo)["weekly"]
    assert full.loc["2026-08-24":, "facebook_posts"].isna().all()
    assert full.loc["2026-10-12":, "instagram_stories"].isna().all()


class CatalogRepo:
    def __init__(self, manifest, replace=None, missing=None):
        self.rows = [dict(row) for row in manifest["sources"] if row["path"] != missing]
        for row in self.rows:
            if row["path"] == replace:
                row["sha256"] = "0" * 64

    def file_catalog(self):
        return pd.DataFrame(self.rows)


@pytest.fixture
def reviewed_directory(tmp_path):
    filenames = ["run_manifest.json", "analysis.py", "analysis_plan.md", "correlations.csv", "correlations_2026_sensitivity.csv", "source_audit/verification.json"]
    for filename in filenames:
        destination = tmp_path / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DEFAULT_ANALYSIS_DIR / filename, destination)
    return tmp_path


def test_reviewed_loader_requires_matching_sources_and_verified_result_bytes(reviewed_directory):
    manifest = json.loads((reviewed_directory / "run_manifest.json").read_text(encoding="utf-8"))
    repo = CatalogRepo(manifest)
    loaded = load_reviewed_results(repo, reviewed_directory)
    assert loaded["status"] == "available" and len(loaded["results"]) == 20
    assert loaded["results"].q_bh_20.min() == pytest.approx(0.0970873786407766)
    with (reviewed_directory / "correlations.csv").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    changed = load_reviewed_results(repo, reviewed_directory)
    assert changed["status"] == "unavailable" and changed["results"].empty
    assert "changed" in changed["reason"]


@pytest.mark.parametrize("source", SOURCE_PATHS)
def test_each_of_six_source_hashes_gates_reviewed_inference(source, reviewed_directory):
    manifest = json.loads((reviewed_directory / "run_manifest.json").read_text(encoding="utf-8"))
    for repo in (CatalogRepo(manifest, replace=source), CatalogRepo(manifest, missing=source)):
        result = load_reviewed_results(repo, reviewed_directory)
        assert result["status"] == "unavailable"
        assert result["source_mismatches"] == [source]
        assert result["results"].empty and result["sensitivity_2026"].empty


def test_reviewed_manifest_cannot_weaken_its_six_source_gate(reviewed_directory):
    path = reviewed_directory / "run_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    repo = CatalogRepo(manifest)
    manifest["sources"].pop()
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = load_reviewed_results(repo, reviewed_directory)
    assert result["status"] == "unavailable" and "six required" in result["reason"]
