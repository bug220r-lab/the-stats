"""Regression checks for native-calendar filters, coverage and video drilldown."""
from datetime import date
import json

import pandas as pd
import pytest
from native_navigation_helpers import NativeAppTest as AppTest

from stats_app.youtube_ui import daily_coverage, filter_daily_dates
from test_youtube_daily_app import synthetic_supplement
from test_youtube_app import youtube_copy, choose


def test_native_date_filter_preserves_missing_values_and_original_indices():
    source = pd.DataFrame({"activity_date": ["2026-10-19", "2026-10-20", "2026-10-22"],
                           "value": [0, None, 9], "value_status": ["zero", "unavailable", "observed"]}, index=[2, 5, 8])
    result = filter_daily_dates(source, date(2026, 10, 19), date(2026, 10, 21))
    assert list(result.index) == [2, 5]
    assert list(result.activity_date) == ["2026-10-19", "2026-10-20"]
    assert pd.isna(result.iloc[1].value)
    assert daily_coverage(result, date(2026, 10, 19), date(2026, 10, 21)) == {
        "expected": 3, "reported": 2, "numeric": 1, "missing": 1}
    assert len(source) == 3


def test_supplement_filter_controls_cards_chart_table_and_download(synthetic_supplement, monkeypatch):
    import stats_app.youtube_ui as ui
    exports = []
    monkeypatch.setattr(ui, "download", lambda frame, *_: exports.append(frame.copy()))
    at = AppTest.from_string(synthetic_supplement[0], default_timeout=30).run()
    at.date_input[0].set_value((date(2025, 10, 22), date(2025, 10, 24))).run()
    assert not at.exception and not at.error
    assert [item.value for item in at.metric] == ["3 / 3", "1 / 3", "0"]
    assert len(at.dataframe[0].value) == len(exports[-1]) == 3
    spec = json.loads(at.get("plotly_chart")[0].proto.spec)
    assert spec["data"][0]["x"] == ["2025-10-22", "2025-10-23", "2025-10-24"]
    assert list(exports[-1].value_status) == ["zero", "unavailable", "unavailable"]
    choose(at, "Supplement metric", "average_view_duration_seconds")
    assert len(at.dataframe[0].value) == 3
    choose(at, "YouTube supplement view", "Coverage & validation")
    choose(at, "YouTube supplement view", "Daily metrics")
    assert at.date_input[0].value == (date(2025, 10, 22), date(2025, 10, 24))
    assert [item.value for item in at.metric] == ["3 / 3", "1 / 3", "0"]
    at.date_input[0].set_value((date(2025, 10, 23),)).run()
    assert not at.exception and not at.error and not at.get("plotly_chart")


def test_inventory_search_drills_into_selected_video_and_preserves_date_filter(youtube_copy, monkeypatch):
    import stats_app.youtube_ui as ui
    exports = []
    monkeypatch.setattr(ui, "download", lambda frame, *_: exports.append(frame.copy()))
    script = f'''from stats_app.youtube_repository import load_registered_youtube
from stats_app.youtube_ui import render_youtube_collection
render_youtube_collection(load_registered_youtube({str(youtube_copy)!r}))
'''
    at = AppTest.from_string(script, default_timeout=60).run()
    inventory = at.dataframe[0].value
    # Pick a regular video to exercise a drilldown across the format default.
    video_id = str(inventory.loc[inventory.content_format.eq("videos")].iloc[0].video_id)
    at.text_input[0].set_value(video_id).run()
    assert len(at.dataframe[0].value) == len(exports[-1]) == 1
    next(item for item in at.button if item.label == "Open video daily data").click().run()
    assert not at.exception and not at.error
    assert set(at.dataframe[0].value.video_id) == {video_id}
    at.date_input[0].set_value((date(2026, 10, 15), date(2026, 10, 21))).run()
    assert len(at.dataframe[0].value) == len(exports[-1]) == 7
    choose(at, "Show canonical daily detail", True, "checkbox")
    detail = next(item.value for item in at.dataframe if "metric" in item.value)
    assert len(detail) == 7
    assert set(detail.activity_date) == set(exports[-1].activity_date)
    choose(at, "YouTube view", "Video inventory")
    choose(at, "YouTube view", "Video daily data")
    assert at.date_input[0].value == (date(2026, 10, 15), date(2026, 10, 21))
    assert set(at.dataframe[0].value.video_id) == {video_id}
    assert not at.exception and not at.error


def test_parent_button_updates_integrated_persistent_collection_selector(synthetic_supplement, youtube_copy, tmp_path, monkeypatch):
    from stats_app.config import PROJECT_ROOT
    from stats_app.youtube_daily_supplement import DailySupplementRepository
    import stats_app.youtube_repository as registration

    parent = registration.load_registered_youtube(youtube_copy)
    supplement = DailySupplementRepository(synthetic_supplement[1]["database"])
    parent_key = parent.metadata["collection_key"]
    supplement_key = supplement.metadata["collection_key"]
    repositories = {parent_key: parent, supplement_key: supplement}
    monkeypatch.setenv("STATS_DATA_DIR", str(tmp_path / "isolated-navigation-library"))
    monkeypatch.setenv("STATS_MODE", "local")
    monkeypatch.setattr(registration, "list_registered_youtube", lambda *_: [
        {"key": key, "label": repo.metadata["label"]} for key, repo in repositories.items()])
    monkeypatch.setattr(registration, "load_registered_youtube", lambda _, key=None: repositories[key or parent_key])
    at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=60).run()
    at.session_state["_requested_page"] = "YouTube collection"
    at.run()
    assert not at.exception and not at.error
    choose(at, "YouTube collection", supplement_key)
    assert any(item.label == "YouTube supplement view" for item in at.selectbox)
    next(item for item in at.button if item.label == "Open parent YouTube collection").click().run()
    assert not at.exception and not at.error
    assert at.session_state["selection:youtube_collection_selector"] == parent_key
    assert next(item for item in at.selectbox if item.label == "YouTube collection").value == parent_key
    assert any(item.label == "YouTube view" for item in at.selectbox)
    assert not any(item.label == "YouTube supplement view" for item in at.selectbox)
    assert len(at.dataframe[0].value) == 27
