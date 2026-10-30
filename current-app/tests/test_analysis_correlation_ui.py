"""Exercise the actual Cross-platform controls and exports without library writes."""
from datetime import date
from hashlib import file_digest
import io
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from stats_app.analysis_content import CONTENT_PATH
from stats_app.analysis_repository import AnalysisRepository, load_registered_analysis
from stats_app.config import load_settings

ROOT = Path(__file__).resolve().parents[1]
REVIEWED = ROOT / "data/analysis/social_spotify_20261023"


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


@pytest.fixture(scope="module")
def source():
    repo = load_registered_analysis(load_settings().data_dir)
    if repo is None or CONTENT_PATH not in repo.tables:
        pytest.skip("Private collected-content analysis unavailable")
    before = digest(repo.db_path)
    yield repo
    assert digest(repo.db_path) == before


@pytest.fixture
def render(monkeypatch):
    downloads = {}
    original = st.download_button

    def capture(*args, **kwargs):
        key = kwargs.get("key")
        if key is not None:
            downloads[key] = (
                kwargs.get("file_name", args[2] if len(args) > 2 else None),
                kwargs.get("data", args[1] if len(args) > 1 else None),
            )
        return original(*args, **kwargs)

    monkeypatch.setattr(st, "download_button", capture)

    def start(repo):
        script = f"""
import streamlit as st
from stats_app.analysis_repository import AnalysisRepository
from stats_app.analysis_ui import render_cross_platform
repo = AnalysisRepository({str(repo.db_path)!r})
repo.registered_key = {getattr(repo, 'registered_key', '')!r}
page = st.sidebar.radio('Explore', ['Cross-platform', 'Away'], key='explore_page')
if page == 'Cross-platform':
    st.session_state['correlation:tabs'] = st.session_state.get('_test_active_tab', 'Timeline & comparison')
    render_cross_platform(repo)
else:
    st.write('Another page; the comparison widgets are not rendered.')
"""
        app = AppTest.from_string(script, default_timeout=30).run()
        healthy(app)
        return app, downloads

    return start


@pytest.fixture
def dashboard(source, render):
    return render(source)


def healthy(app):
    assert not app.exception, [item.value for item in app.exception]
    assert not app.error, [item.value for item in app.error]


def choose(app, kind, label, value):
    next(node for node in getattr(app, kind) if node.label == label).set_value(value).run()
    healthy(app)


def switch_tab(app, label):
    # Native tab events are not exposed by AppTest; exercise their saved state.
    app.session_state["_test_active_tab"] = label
    app.run()
    healthy(app)


def value(app, kind, label):
    return next(node for node in getattr(app, kind) if node.label == label).value


def csv(downloads, key):
    filename, raw = downloads[key]
    assert filename.endswith(".csv") and isinstance(raw, bytes)
    return pd.read_csv(io.BytesIO(raw), dtype={"post_id": str, "identity_key": str})


def table(app, *columns):
    return next(node.value for node in app.dataframe if set(columns).issubset(node.value.columns))


def test_default_reviewed_totals_pairs_and_downloads_match_independent_receipt(dashboard):
    app, downloads = dashboard
    assert value(app, "radio", "Cross-platform view") == "Posts & Spotify"
    assert value(app, "selectbox", "Comparison period") == "Reviewed 2024–2025"
    assert value(app, "metric", "Retained Facebook posts") == "306"
    assert value(app, "metric", "Retained Instagram Stories") == "594"
    weekly = csv(downloads, "correlation-weekly-csv")
    golden = pd.read_csv(REVIEWED / "weekly_primary.csv")
    assert len(weekly) == 104
    assert weekly.week_start.min() == "2024-01-01"
    assert weekly.week_start.max() == "2025-12-22"
    golden_columns = ["week_start", "facebook_posts", "instagram_stories", "streams", "spotify_days"]
    pd.testing.assert_frame_equal(weekly[golden_columns], golden[golden_columns], check_dtype=False, rtol=1e-12)
    assert weekly.spotify_days.eq(7).all()
    assert (pd.to_datetime(weekly.week_end) - pd.to_datetime(weekly.week_start)).eq(pd.Timedelta(days=6)).all()
    assert {"facebook_posts_status", "instagram_stories_status"}.issubset(weekly)
    assert weekly.streams.sum() == 42948
    detail = csv(downloads, "correlation-content-csv")
    assert len(detail) == detail.identity_key.nunique() == 900
    assert set(detail.exposure) == {"facebook_posts", "instagram_stories"}
    pairs = csv(downloads, "correlation-pairs-csv")
    assert pairs.groupby("exposure").size().to_dict() == {"facebook_posts": 103, "instagram_stories": 103}
    assert pairs.publishing_week.eq(pairs.target_week).all()
    estimates = table(app, "Publishing series", "Spearman correlation", "Paired weeks")
    assert estimates["Paired weeks"].tolist() == [103, 103]
    assert any("zero means no retained publication" in node.value for node in app.caption)
    switch_tab(app, "Reviewed results")
    all_reviewed = csv(downloads, "correlation-reviewed-csv")
    assert len(all_reviewed) == 20 and all_reviewed.q_bh_20.ge(.05).all()


def test_custom_dates_mean_daily_listeners_and_following_week_keep_calendar_alignment(dashboard, source):
    app, downloads = dashboard
    choose(app, "selectbox", "Comparison period", "Custom")
    choose(app, "date_input", "Comparison dates", (date(2026, 1, 1), date(2026, 1, 25)))
    choose(app, "selectbox", "Spotify activity", "mean_daily_listeners")
    weekly = csv(downloads, "correlation-weekly-csv")
    assert weekly.week_start.tolist() == ["2026-01-05", "2026-01-12", "2026-01-19"]
    # Reconstruct from retained raw artist days, independently of the weekly API.
    raw = pd.read_csv(io.BytesIO(source.original_bytes(
        "raw/spotify_baseline/raw/artist_timeline_2024-01-01_2026-10-20.csv")))
    raw["date"] = pd.to_datetime(raw.date)
    selected = raw[raw.date.between("2026-01-05", "2026-01-25")].copy()
    selected["week"] = selected.date - pd.to_timedelta(selected.date.dt.weekday, unit="D")
    expected = selected.groupby("week").listeners.mean()
    assert weekly.mean_daily_listeners.tolist() == pytest.approx(expected.tolist())
    assert any("not a count of unique weekly listeners" in node.value for node in app.caption)
    choose(app, "selectbox", "Spotify timing", "Following week")
    pairs = csv(downloads, "correlation-pairs-csv")
    assert len(pairs) == 2  # One pair per publishing series, after differencing and lag.
    assert set(pairs.publishing_week) == {"2026-01-12"}
    assert set(pairs.target_week) == {"2026-01-19"}
    assert set(pairs.outcome) == {"mean_daily_listeners"}
    assert pairs.lag_weeks.eq(1).all()
    assert table(app, "Publishing series", "Spearman correlation")["Spearman correlation"].isna().all()
    assert any("Custom filters do not receive saved confidence intervals" in node.value for node in app.caption)


def test_details_search_exports_only_selected_id_without_changing_timeline(dashboard):
    app, downloads = dashboard
    weekly_before = csv(downloads, "correlation-weekly-csv")
    pairs_before = csv(downloads, "correlation-pairs-csv")
    details = csv(downloads, "correlation-content-csv")
    row = details.iloc[0]
    choose(app, "selectbox", "Inspect publishing week", row.week)
    choose(app, "text_input", "Search post text, ID or link", row.post_id)
    filtered = csv(downloads, "correlation-content-csv")
    visible = table(app, "post_id", "dates", "date_conflict")
    assert filtered.post_id.tolist() == visible.post_id.tolist() == [row.post_id]
    assert filtered.week.tolist() == [row.week]
    pd.testing.assert_frame_equal(csv(downloads, "correlation-weekly-csv"), weekly_before)
    pd.testing.assert_frame_equal(csv(downloads, "correlation-pairs-csv"), pairs_before)
    choose(app, "text_input", "Search post text, ID or link", "[not-a-post]")
    assert csv(downloads, "correlation-content-csv").empty
    assert table(app, "post_id", "dates", "date_conflict").empty


def test_filters_survive_navigation_and_legacy_switch_keeps_original_test_family(dashboard):
    app, downloads = dashboard
    choose(app, "selectbox", "Comparison period", "2026 available")
    choose(app, "selectbox", "Spotify activity", "saves")
    choose(app, "selectbox", "Spotify timing", "Following week")
    choose(app, "multiselect", "Publishing series", ["instagram_feed"])
    before = csv(downloads, "correlation-weekly-csv")
    assert {"week_start", "instagram_feed", "saves", "spotify_days", "week_end", "instagram_feed_status"}.issubset(before)
    assert not {"facebook_posts", "instagram_stories", "streams"}.intersection(before)
    assert any("excluded from the reviewed 20-comparison" in node.value for node in app.warning)
    # Date coverage must leave the feed tail unavailable, not create artificial zero weeks.
    assert before.loc[before.week_start.gt("2026-08-16"), "instagram_feed"].isna().all()
    choose(app, "radio", "Explore", "Away")
    choose(app, "radio", "Explore", "Cross-platform")
    assert value(app, "selectbox", "Comparison period") == "2026 available"
    assert value(app, "selectbox", "Spotify activity") == "saves"
    assert value(app, "selectbox", "Spotify timing") == "Following week"
    assert value(app, "multiselect", "Publishing series") == ["instagram_feed"]
    choose(app, "radio", "Cross-platform view", "Account activity · saved analysis")
    assert value(app, "metric", "Planned comparisons") == "12"
    assert value(app, "metric", "Eligible for exploratory uncertainty") == "6"
    assert value(app, "metric", "Smallest BH-adjusted p") == "0.385"
    assert len(table(app, "analysis_id", "q_bh_12_tests")) == 12
    choose(app, "radio", "Cross-platform view", "Posts & Spotify")
    pd.testing.assert_frame_equal(csv(downloads, "correlation-weekly-csv"), before)


def test_empty_date_range_and_series_are_explicit_without_stale_weekly_exports(dashboard):
    app, downloads = dashboard
    choose(app, "selectbox", "Comparison period", "Custom")
    downloads.clear()
    choose(app, "date_input", "Comparison dates", (date(2026, 1, 6), date(2026, 1, 8)))
    assert any("No complete Monday–Sunday weeks" in node.value for node in app.info)
    assert "correlation-weekly-csv" not in downloads
    assert "correlation-pairs-csv" not in downloads
    choose(app, "selectbox", "Comparison period", "Reviewed 2024–2025")
    downloads.clear()
    choose(app, "multiselect", "Publishing series", [])
    assert any("Choose at least one publishing series" in node.value for node in app.info)
    assert "correlation-weekly-csv" not in downloads
    switch_tab(app, "Reviewed results")
    assert len(csv(downloads, "correlation-reviewed-csv")) == 20


def test_reviewed_selection_retains_full_family_and_hash_mismatch_is_unavailable(dashboard, monkeypatch):
    from stats_app import analysis_correlation_ui

    app, downloads = dashboard
    switch_tab(app, "Reviewed results")
    golden = csv(downloads, "correlation-reviewed-csv")
    choose(app, "selectbox", "Reviewed Spotify outcome", "net_followers")
    selected = table(app, "Comparison", "n", "rho", "q_bh_20")
    assert len(selected) == 4
    assert sorted(selected.q_bh_20) == pytest.approx(sorted(golden[golden.outcome.eq("net_followers")].q_bh_20))
    pd.testing.assert_frame_equal(csv(downloads, "correlation-reviewed-csv"), golden)
    monkeypatch.setattr(analysis_correlation_ui, "load_reviewed_results", lambda repo: {
        "status": "unavailable", "reason": "The retained source hashes do not match the reviewed analysis."})
    downloads.clear()
    app.run()
    healthy(app)
    assert any("unavailable for this saved source version" in node.value and "hashes" in node.value for node in app.info)
    assert "correlation-reviewed-csv" not in downloads
    assert "correlation-2026-csv" not in downloads
    switch_tab(app, "Timeline & comparison")
    assert len(csv(downloads, "correlation-weekly-csv")) == 104


def test_legacy_source_without_content_table_still_defaults_to_original_analysis(render):
    path = ROOT / "data/reconciliation/staged_analysis/analysis.sqlite3"
    if not path.exists():
        pytest.skip("Private legacy analysis snapshot unavailable")
    source = AnalysisRepository(path)
    assert CONTENT_PATH not in source.tables
    before = digest(path)
    app, _ = render(source)
    assert not any(node.label == "Cross-platform view" for node in app.radio)
    assert value(app, "metric", "Planned comparisons") == "12"
    assert len(table(app, "analysis_id", "q_bh_12_tests")) == 12
    assert digest(path) == before
