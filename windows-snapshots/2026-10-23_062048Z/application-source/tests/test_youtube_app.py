"""YouTube source-grain and read-only UI checks; private-source smoke is optional."""
import json
import os
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from stats_app.config import PROJECT_ROOT
from stats_app.youtube_ui import retention_figure, source_series


def test_numeric_statuses_keep_unknown_and_explicit_zero_distinct():
    data = pd.DataFrame({"activity_date": ["2026-10-19", "2026-10-20", "2026-10-21"],
                         "value": [0, 0, 129.2], "value_status": ["unavailable", "zero", "observed"]})
    shown = source_series(data, "activity_date")
    assert pd.isna(shown.iloc[0].value)
    assert shown.iloc[1].value == 0
    assert shown.iloc[2].value == 129.2
    assert data.iloc[0].value == 0, "Presentation must not mutate retained raw values."


def test_retention_axis_and_values_are_not_clamped_or_extended():
    data = pd.DataFrame({"video_position_percent": list(range(100)), "value": [135.5, -17.5] + [20.0] * 98,
                         "value_status": ["reported"] * 99 + ["unavailable"], "unit": ["percent"] * 100,
                         "metric": ["compared_to_other_videos"] * 100})
    fig = retention_figure(data)
    assert list(fig.data[0].x) == list(range(100))
    assert fig.data[0].y[0] == 135.5 and fig.data[0].y[1] == -17.5
    assert pd.isna(fig.data[0].y[-1])
    assert fig.layout.xaxis.range == (0, 99)
    assert fig.layout.yaxis.range is None
    assert "Elapsed video" in fig.layout.xaxis.title.text


@pytest.fixture(scope="module")
def youtube_copy(tmp_path_factory):
    from stats_app.youtube_repository import import_youtube_collection
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    durable = local / "TheStats/collections/youtube-20261023"
    configured = os.environ.get("STATS_YOUTUBE_TEST_ZIP")
    candidates = [Path(configured)] if configured else []
    candidates.extend([durable / "The_Stats_YouTube_Collection_2026-10-23.zip",
                  local / "Temp/youtube_collection_2026-10-23/The_Stats_YouTube_Collection_2026-10-23.zip",
                  Path(os.environ.get("TEMP", Path.home() / "AppData/Local/Temp")) /
                  "youtube_collection_2026-10-23/The_Stats_YouTube_Collection_2026-10-23.zip"])
    try:
        if durable.is_dir():
            candidates.extend(durable.glob("*.zip"))
    except PermissionError:
        pass
    source = None
    for candidate in candidates:
        try:
            if candidate.is_file():
                with candidate.open("rb") as handle:
                    handle.read(1)
                source = candidate
                break
        except (PermissionError, FileNotFoundError):
            continue
    if source is None:
        pytest.skip("Readable private YouTube package unavailable; set STATS_YOUTUBE_TEST_ZIP.")
    root = tmp_path_factory.mktemp("youtube-ui")
    import_youtube_collection(source, root)
    return root


@pytest.fixture
def app(youtube_copy, monkeypatch):
    monkeypatch.setenv("STATS_DATA_DIR", str(youtube_copy))
    monkeypatch.setenv("STATS_MODE", "local")
    at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=60).run()
    assert not at.exception and not at.error
    choose(at, "Explore", "YouTube collection", "radio")
    return at


def choose(at, label, value, kind="selectbox"):
    next(item for item in getattr(at, kind) if item.label == label).set_value(value).run()
    assert not at.exception, [item.value for item in at.exception]
    assert not at.error, [item.value for item in at.error]


def test_inventory_and_separate_formats(app):
    assert len(app.dataframe[0].value) == 27
    assert app.dataframe[0].value.video_id.nunique() == 27
    assert any("newly retrieved historical" in item.value for item in app.info)
    assert any("America/Los_Angeles" in item.value for item in app.caption)
    choose(app, "Inventory formats · empty means all", ["videos"], "multiselect")
    assert len(app.dataframe[0].value) == 19
    choose(app, "Inventory formats · empty means all", ["shorts"], "multiselect")
    assert len(app.dataframe[0].value) == 8


def test_video_daily_metrics_and_scope_are_separate(app):
    choose(app, "YouTube view", "Video daily data")
    assert len(app.get("plotly_chart")) == 1
    assert any("365 retained records" in item.value for item in app.caption)
    records = app.dataframe[0].value
    assert records.video_id.nunique() == 1
    assert {"views", "views_status", "engaged_views", "engaged_views_status"} <= set(records.columns)
    choose(app, "YouTube daily video metric", "engaged_views")
    assert len(app.get("plotly_chart")) == 1
    spec = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert spec["data"][0]["name"] == "engaged_views (count)"
    choose(app, "YouTube canonical content format", "videos")
    assert set(app.dataframe[0].value.canonical_content_format) == {"videos"}


def test_channel_period_history_and_partial_daily_data(app):
    choose(app, "YouTube view", "Channel data")
    choose(app, "YouTube metric", "watch_time_hours")
    assert len(app.dataframe[0].value) == 243
    assert any("partial data" in item.value for item in app.warning)
    assert set(app.dataframe[0].value.filters_json) == {"{}"}
    choose(app, "YouTube channel data", "Source period summaries", "radio")
    period = next(item for item in app.selectbox if item.label == "YouTube reporting period")
    period.set_value(("baseline365_historical", "2025-10-21", "2026-10-20")).run()
    assert not app.exception and not app.error
    assert set(app.dataframe[0].value.snapshot_class) == {"newly_retrieved_historical"}
    assert set(app.dataframe[0].value.reporting_end) == {"2026-10-20"}
    assert not app.get("plotly_chart")


def test_native_retention_and_header_only_member_are_distinct(app):
    choose(app, "YouTube view", "Retention")
    assert len(app.get("plotly_chart")) == 1
    rows = app.dataframe[0].value
    assert len(rows) == 100 and set(rows.video_position_percent) == set(range(100))
    assert rows.video_id.nunique() == rows.member_name.nunique() == rows.metric.nunique() == 1
    choose(app, "YouTube retention member", "Skippable video ad.csv")
    assert not app.get("plotly_chart")
    assert any("header-only" in item.value for item in app.info)
    choose(app, "YouTube retention source", "Manual UI summaries", "radio")
    assert not app.get("plotly_chart")
    assert any("Manual UI transcription" in item.value for item in app.warning)
    assert len(app.dataframe[0].value) == 1
    assert "average_view_duration_display" in app.dataframe[0].value


def test_dimension_mapping_and_existing_provenance_entries(app):
    choose(app, "YouTube view", "Discovery & audience")
    assert app.dataframe and not app.get("plotly_chart")
    choose(app, "YouTube dimension data", "Daily observations", "radio")
    assert len(app.get("plotly_chart")) == 1
    assert app.dataframe[0].value.dimension_json.nunique() == 1
    choose(app, "YouTube view", "Song mappings")
    assert len(app.dataframe[0].value) == 27
    assert app.dataframe[0].value.spotify_recording_id.isna().all()
    choose(app, "Explore", "Sources & provenance", "radio")
    assert any(item.label == "YouTube collection · October 23, 2026" for item in app.expander)
    choose(app, "Inspect YouTube sources", True, "checkbox")
    assert any(item.label == "YouTube retained source" for item in app.selectbox)
    choose(app, "Explore", "Coverage & cross-reference", "radio")
    choose(app, "Inspect YouTube coverage", True, "checkbox")
    assert any("collection_item" in item.value.columns for item in app.dataframe)


def test_coverage_references_partial_metrics_and_statuses(app):
    choose(app, "YouTube view", "Coverage & limitations")
    statuses = app.dataframe[0].value
    assert {"blocked", "partial", "not_applicable", "not_yet_collected", "complete"} <= set(statuses.status)
    choose(app, "YouTube coverage table", "Daily coverage")
    row = app.dataframe[0].value.iloc[0]
    assert row.observed_dates == 243 and row.expected_dates == 365
    assert row.missing_dates_count == 122
    assert row.metric == "watch_time_hours"
