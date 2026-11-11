"""Interactive regressions over the real immutable library, without writes."""
from datetime import date
from hashlib import sha256
import io

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from stats_app.analysis_repository import load_registered_analysis
from stats_app.config import load_settings


@pytest.fixture(scope="module")
def source():
    repo = load_registered_analysis(load_settings().data_dir)
    if repo is None:
        pytest.skip("Private immutable analysis library unavailable")
    before = sha256(repo.db_path.read_bytes()).hexdigest()
    yield repo
    assert sha256(repo.db_path.read_bytes()).hexdigest() == before


@pytest.fixture
def dashboard(source, monkeypatch):
    """Use actual view functions, callbacks and CSV serialization, no writable DB."""
    downloads = {}
    original_download = st.download_button

    def capture(*args, **kwargs):
        key = kwargs.get("key")
        raw = kwargs.get("data", args[1] if len(args) > 1 else None)
        filename = kwargs.get("file_name", args[2] if len(args) > 2 else None)
        if key is not None:
            downloads[key] = (filename, raw)
        return original_download(*args, **kwargs)

    monkeypatch.setattr(st, "download_button", capture)
    script = f"""
import streamlit as st
from stats_app.analysis_repository import AnalysisRepository
from stats_app.analysis_ui import render_overview, render_spotify
from stats_app.decision_ui import render_decision_report
from stats_app.analysis_social_ui import render_social
repo = AnalysisRepository({str(source.db_path)!r})
repo.registered_key = {source.registered_key!r}
page = st.sidebar.radio('Explore', ['Overview', 'Spotify', 'Decision report', 'Social'], key='explore_page')
{{'Overview': render_overview, 'Spotify': render_spotify, 'Decision report': render_decision_report, 'Social': render_social}}[page](repo)
"""
    app = AppTest.from_string(script, default_timeout=60).run()
    healthy(app)
    return app, downloads


def healthy(app):
    assert not app.exception, [item.value for item in app.exception]
    assert not app.error, [item.value for item in app.error]


def choose(app, kind, label, value):
    next(item for item in getattr(app, kind) if item.label == label).set_value(value).run()
    healthy(app)


def click(app, label):
    next(item for item in app.button if item.label == label).click().run()
    healthy(app)


def metric(app, label):
    return next(item for item in app.metric if item.label == label)


def csv(downloads, key):
    filename, raw = downloads[key]
    assert filename.endswith(".csv") and isinstance(raw, bytes)
    return pd.read_csv(io.BytesIO(raw), dtype={"song_id": str})


def table(app, *columns):
    return next(item.value for item in app.dataframe if set(columns).issubset(item.value.columns))


def raw_artist_total(source, start, end, metric_name="streams"):
    data = pd.read_csv(io.BytesIO(source.original_bytes(
        "raw/spotify_baseline/raw/artist_timeline_2024-01-01_2026-10-20.csv")))
    return float(data.loc[data.date.between(str(start), str(end)), metric_name].sum())


def test_overview_ytd_does_not_relabel_native_prior_listener_period(dashboard, source):
    app, downloads = dashboard
    choose(app, "selectbox", "Comparison", "Year to date, matching prior year")
    listeners = metric(app, "Period-unique listeners")
    assert listeners.value == "9,419"
    audience = csv(downloads, "overview_unique_csv").iloc[0]
    assert audience.current_value == 9419
    # A later exact-period recovery is legitimate; the incompatible native
    # March–December audience must never be relabeled as January–October.
    if audience.get("previous_source_asset") == "spotify/cleaned/recovered_artist_metrics.csv":
        recovered = source.table("spotify/cleaned/recovered_artist_metrics.csv")
        exact = recovered.loc[recovered["Period start"].eq("2025-01-01") & recovered["Period end"].eq("2025-10-20")
                              & recovered["Metric"].eq("period_unique_listeners")]
        assert len(exact) == 1 and audience.previous_value == exact.iloc[0]["Value"]
        assert audience.previous_period_start == "2025-01-01" and audience.previous_period_end == "2025-10-20"
        assert audience.native_previous_period_start == "2025-03-14" and audience.native_previous_period_end == "2025-12-31"
        assert audience.percent_change == pytest.approx((9419/audience.previous_value-1)*100)
        assert listeners.delta == f"{audience.percent_change:+.1f}%"
    else:
        assert listeners.delta in ("", None)
        assert any("No compatible directly reported audience" in c.value for c in app.caption)
        assert pd.isna(audience.previous_value) and pd.isna(audience.percent_change)
    comparisons = csv(downloads, "overview_comparison_csv")
    assert comparisons.previous_start.eq("2025-01-01").all()
    assert comparisons.previous_end.eq("2025-10-20").all()


def test_custom_overview_cards_chart_records_and_csv_agree(dashboard, source):
    app, downloads = dashboard
    choose(app, "selectbox", "Comparison", "Custom")
    start, end = date(2026, 10, 1), date(2026, 10, 20)
    choose(app, "date_input", "UTC activity dates", (start, end))
    expected = raw_artist_total(source, start, end)
    assert metric(app, "Streams").value == f"{expected:,.0f}"
    assert metric(app, "Period-unique listeners").value == "Unavailable"
    comparisons = csv(downloads, "overview_comparison_csv")
    streams = comparisons.loc[comparisons.metric.eq("daily_streams")].iloc[0]
    assert streams.current == expected
    assert streams.current_start == str(start) and streams.current_end == str(end)
    assert streams.previous_start == "2026-09-11" and streams.previous_end == "2026-09-30"
    records = csv(downloads, "overview_days_csv")
    selected = records[records.interval.eq("Selected")]
    prior = records[records.interval.eq("Comparison")]
    assert len(selected) == len(prior) == 20
    assert selected.date.min() == str(start) and selected.date.max() == str(end)
    assert selected.daily_streams.sum() == expected
    assert prior.daily_streams.sum() == streams.previous
    plotted = table(app, "date", "daily_streams", "interval")
    assert len(plotted) == 40
    assert plotted[plotted.interval.eq("Selected")].daily_streams.sum() == expected


def test_song_selection_outcome_and_dates_survive_navigation_and_overview_shortcut(dashboard, source):
    app, downloads = dashboard
    click(app, "Explore songs")
    assert next(x for x in app.radio if x.label == "Spotify view").value == "Catalog comparison"
    recordings = source.table("spotify/cleaned/recordings.csv")
    song_ids = recordings[recordings.recording_label.isin(["Funny Guy", "Waste Away"])].song_id.tolist()
    assert len(song_ids) == 2
    choose(app, "multiselect", "Recordings · empty means all", song_ids)
    choose(app, "selectbox", "Catalog metric", "saves")
    choose(app, "radio", "Explore", "Overview")
    choose(app, "selectbox", "Comparison", "Custom")
    dates = (date(2026, 10, 1), date(2026, 10, 20))
    choose(app, "date_input", "UTC activity dates", dates)
    click(app, "Explore songs")
    assert next(x for x in app.date_input if x.label == "UTC activity dates").value == dates
    assert next(x for x in app.multiselect if x.label == "Recordings · empty means all").value == song_ids
    assert next(x for x in app.selectbox if x.label == "Catalog metric").value == "saves"
    visible = table(app, "song_id", "current", "previous")
    exported = csv(downloads, "catalog_csv")
    assert set(visible.song_id) == set(exported.song_id) == set(song_ids)
    source_rows = source.table("spotify/cleaned/track_daily_long.csv")
    expected = source_rows[source_rows.metric.eq("saves") & source_rows.song_id.isin(song_ids)
                           & source_rows.date.between(str(dates[0]), str(dates[1]))].groupby("song_id").value.sum()
    assert exported.set_index("song_id").current.to_dict() == expected.to_dict()
    # Hiding a page causes Streamlit widget cleanup; persisted selections must survive.
    choose(app, "radio", "Explore", "Overview")
    choose(app, "radio", "Explore", "Spotify")
    assert next(x for x in app.multiselect if x.label == "Recordings · empty means all").value == song_ids
    assert next(x for x in app.selectbox if x.label == "Catalog metric").value == "saves"
    assert next(x for x in app.date_input if x.label == "UTC activity dates").value == dates


def test_decision_custom_dates_update_songs_and_withhold_unreported_audience(dashboard, source):
    app, downloads = dashboard
    choose(app, "radio", "Explore", "Decision report")
    assert metric(app, "28-day streams").value == "4,246"
    choose(app, "selectbox", "Decision reporting period", "Custom")
    dates = (date(2026, 10, 1), date(2026, 10, 20))
    choose(app, "date_input", "UTC activity dates", dates)
    expected = raw_artist_total(source, *dates)
    assert metric(app, "20-day streams").value == f"{expected:,.0f}"
    assert metric(app, "Streams per period listener").value == "Unavailable"
    assert any("No direct period-unique listener count" in c.value for c in app.caption)
    choose(app, "radio", "Decision view", "Songs")
    visible = table(app, "song_id", "current", "previous")
    exported = csv(downloads, "decision_songs_csv")
    assert len(visible) == len(exported) == 14
    assert visible.current.sum() == exported.current.sum() == expected
    assert any("recording-level listener ratios are unavailable" in i.value for i in app.info)


def test_decision_search_export_and_recording_shortcut_use_visible_selection(dashboard, source):
    app, downloads = dashboard
    choose(app, "radio", "Explore", "Decision report")
    choose(app, "radio", "Decision view", "Songs")
    choose(app, "text_input", "Search recordings", "waste")
    visible = table(app, "song_id", "current", "previous")
    exported = csv(downloads, "decision_songs_csv")
    assert len(visible) == len(exported) == 1
    assert visible.recording_label.iloc[0] == exported.recording_label.iloc[0] == "Waste Away"
    assert exported.current.iloc[0] == 190
    assert visible.song_id.tolist() == exported.song_id.tolist()
    click(app, "Open recording history")
    assert next(x for x in app.multiselect if x.label == "Recordings · empty means all").value == exported.song_id.tolist()
    assert next(x for x in app.date_input if x.label == "UTC activity dates").value == (date(2026, 9, 23), date(2026, 10, 20))
    assert table(app, "song_id", "current", "previous").current.iloc[0] == 190
    choose(app, "radio", "Explore", "Decision report")
    assert next(x for x in app.text_input if x.label == "Search recordings").value == "waste"
    # The search is literal, so punctuation cannot become a regex or match all songs.
    choose(app, "text_input", "Search recordings", "[no match]")
    assert table(app, "song_id", "current", "previous").empty
    assert csv(downloads, "decision_songs_csv").empty
    assert any("No recordings match this search" in i.value for i in app.info)


def test_overview_content_shortcut_opens_searchable_content_view(dashboard):
    app, _ = dashboard
    click(app, "Review social content")
    assert next(x for x in app.radio if x.label == "Explore").value == "Social"
    assert next(x for x in app.radio if x.label == "Social view").value == "Collected posts & Stories"
    assert next(x for x in app.text_input if x.label == "Search collected posts · text, ID or link").value == ""


def test_current_artist_history_caption_keeps_recovered_retrieval_vintages(dashboard, source):
    if not source.metadata.get("analysis_version"):
        pytest.skip("Original retained version has no reconciled-history metadata")
    app, _ = dashboard
    choose(app, "radio", "Explore", "Spotify")
    choose(app, "radio", "Spotify view", "Artist history")
    captions = [item.value for item in app.caption]
    assert any("reconciled history" in text and "later chart-capture timestamps" in text for text in captions)
    assert not any("original_baseline package vintage" in text for text in captions)
