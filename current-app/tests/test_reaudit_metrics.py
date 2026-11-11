"""Regressions for confirmed re-audit defects; no production writes."""
import hashlib
from pathlib import Path

import pandas as pd
import pytest

from stats_app.analysis_metrics import complete_sum, exact_period_audience, artist_comparison
from stats_app.analysis_social_metrics import canonical_social_series, summarize_daily
from stats_app.analysis_repository import load_registered_analysis
from stats_app.config import load_settings
from stats_app.decision_report import build_report


@pytest.fixture(scope="module")
def repo():
    loaded = load_registered_analysis(load_settings().data_dir)
    if loaded is None:
        pytest.skip("Private immutable source package unavailable")
    return loaded


def test_ytd_audience_comparison_requires_matching_prior_bounds(repo):
    periods = repo.table("spotify/cleaned/artist_period_dashboard.csv")
    row = exact_period_audience(periods, "2026-01-01", "2026-10-20",
                                previous_start="2025-01-01", previous_end="2025-10-20")
    assert row.current_value == 9419
    assert row.previous_value is None and row.percent_change is None
    assert not row.comparison_available
    compatible = exact_period_audience(periods, "2026-01-01", "2026-10-20",
                                       previous_start="2025-03-14", previous_end="2025-12-31")
    assert compatible.previous_value == 3558 and compatible.comparison_available
    # A custom range cannot acquire a fabricated audience from daily uniques.
    assert exact_period_audience(periods, "2026-10-01", "2026-10-20") is None


@pytest.mark.parametrize("invalid", [-1, float("inf"), float("nan")])
def test_invalid_activity_cannot_create_complete_spotify_period(repo, invalid):
    daily = repo.table("spotify/cleaned/artist_daily.csv").iloc[:1].copy()
    daily["daily_streams"] = invalid
    assert complete_sum(daily, "daily_streams", daily.date.iloc[0], daily.date.iloc[0])[0] is None


@pytest.mark.parametrize("invalid", [-1, float("inf"), float("nan")])
def test_invalid_social_activity_cannot_create_complete_period(repo, invalid):
    daily = repo.table("social/account_daily.csv")
    row = daily[daily.metric.eq("views")].iloc[:1].copy()
    row["value"] = invalid
    assert summarize_daily(row, row.date.iloc[0], row.date.iloc[0]).total is None


def test_unknown_partial_flag_and_missing_date_are_not_complete(repo):
    daily = repo.table("social/account_daily.csv")
    row = daily[daily.metric.eq("views")].iloc[:1].copy()
    row["partial_day"] = pd.NA
    result = summarize_daily(row, row.date.iloc[0], row.date.iloc[0])
    assert result.total is None and result.partial_days == 1
    row["date"] = pd.NA
    with pytest.raises(ValueError, match="reporting date"):
        summarize_daily(row, "2026-01-01", "2026-01-01")


def test_repair_selection_replaces_once_and_keeps_original_bytes(repo):
    repair = "social/meta_collection/follows_daily_resolved.csv"
    if repair not in repo.tables:
        pytest.skip("Version predates reviewed repair")
    original = repo.original_bytes("social/account_daily.csv")
    sources = canonical_social_series(repo)
    inherited, repaired = sources[0][1], sources[1][1]
    assert not (inherited.platform_selected.eq("Instagram") & inherited.metric.eq("follows")).any()
    assert len(repaired) == 293 and not repaired.date.duplicated().any()
    assert summarize_daily(repaired, "2026-09-23", "2026-10-20").total == 15
    assert repo.original_bytes("social/account_daily.csv") == original


def test_selected_report_dates_change_totals_and_withhold_unavailable_audience(repo):
    before = hashlib.sha256(repo.db_path.read_bytes()).hexdigest()
    report = build_report(repo, "2026-10-01", "2026-10-20")
    daily = repo.table("spotify/cleaned/artist_daily.csv")
    expected = artist_comparison(daily, "daily_streams", "2026-10-01", "2026-10-20")
    assert report["period"]["days"] == 20
    assert report["growth"]["current"] == expected["current"]
    assert report["period_unique_listeners"] is None
    assert report["listening_intensity"]["value"] is None
    assert report["song_ratios"] == []
    assert sum(row["current"] for row in report["songs"]) == expected["current"]
    assert all(row["current"]["start"] == "2026-10-01" and row["current"]["end"] == "2026-10-20" for row in report["social_comparisons"])
    assert all("2026-10-01" <= row["event_date"] <= "2026-10-20" for row in report["spikes"]["events"])
    assert hashlib.sha256(repo.db_path.read_bytes()).hexdigest() == before


def test_social_repair_cards_filtered_download_and_navigation_agree(repo, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from stats_app import analysis_social_ui
    if "social/meta_collection/follows_daily_resolved.csv" not in repo.tables:
        pytest.skip("Version predates reviewed repair")
    downloads = []
    monkeypatch.setattr(analysis_social_ui, "_download", lambda data, name, key: downloads.append((data.copy(), name)))
    code = ("from stats_app.analysis_repository import AnalysisRepository\n"
            "from stats_app.analysis_social_ui import render_social\n"
            f"render_social(AnalysisRepository({str(repo.db_path)!r}))")
    app = AppTest.from_string(code, default_timeout=30).run()
    next(w for w in app.radio if w.label == "Social view").set_value("Account activity").run()
    next(w for w in app.selectbox if w.label == "Social activity metric").set_value("follows").run()
    assert not app.exception and not app.error
    assert app.metric[0].value == "15"
    rows, filename = downloads[-1]
    assert filename == "follows_daily_resolved.csv"
    assert len(rows) == 28 and rows.date.nunique() == 28 and rows.value.sum() == 15
    assert rows.date.min() == "2026-09-23" and rows.date.max() == "2026-10-20"
    next(w for w in app.radio if w.label == "Social view").set_value("Audience distribution").run()
    next(w for w in app.radio if w.label == "Social view").set_value("Account activity").run()
    assert not app.exception and not app.error
    assert next(w for w in app.selectbox if w.label == "Social activity metric").value == "follows"
    assert app.metric[0].value == "15"
