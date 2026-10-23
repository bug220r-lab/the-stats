"""Synthetic-only UI checks for a separate YouTube daily supplement."""
from datetime import date, timedelta
import csv
import hashlib
import io
import json

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from stats_app.config import PROJECT_ROOT
from stats_app.youtube_daily_supplement import (
    CHANNEL_ID, COLLECTION_KEY, EXPECTED_SHA256, METRICS, build_daily_supplement,
)


@pytest.fixture(scope="module")
def synthetic_supplement(tmp_path_factory):
    import zipfile

    root = tmp_path_factory.mktemp("synthetic-youtube-daily-ui")
    source = root / "synthetic-source"
    (source / "originals").mkdir(parents=True)
    (source / "evidence").mkdir()
    (source / "evidence/ui.txt").write_text("SYNTHETIC UI TEST FIXTURE. This is not collected account evidence.", encoding="utf-8")
    manifest = {
        "schema_version": 1, "collection_key": "youtube-daily-20261023-uitest",
        "label": "SYNTHETIC UI TEST FIXTURE — not collected evidence", "parent_collection_key": COLLECTION_KEY,
        "parent_zip_sha256": EXPECTED_SHA256, "retrieval_date": "2026-10-23",
        "channel": {"channel_id": CHANNEL_ID, "channel_name": "[REDACTED] TV", "channel_handle": "@redactedbandoh",
                    "channel_type": "standard_channel", "report_scope": "channel_owned", "source_timezone": "America/Los_Angeles"},
        "reports": [],
    }
    for metric, (source_field, _, _) in METRICS.items():
        content = io.StringIO(newline="")
        writer = csv.writer(content, lineterminator="\n")
        writer.writerow(["Date", source_field])
        value = "0:01:32" if metric == "average_view_duration_seconds" else "0.125" if metric == "watch_time_hours" else "2"
        unavailable = ["0:00:00" if metric == "average_view_duration_seconds" else "0", "", "—", "suppressed", "not applicable"]
        for offset in range(365):
            writer.writerow([(date(2025, 10, 22) + timedelta(days=offset)).isoformat(), unavailable[offset] if offset < 5 else value])
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("Totals.csv", content.getvalue().encode("utf-8"))
        raw = buffer.getvalue()
        original = f"originals/{metric}.zip"
        (source / original).write_bytes(raw)
        manifest["reports"].append({
            "report_id": "synthetic_" + metric, "metric": metric, "original_path": original,
            "sha256": hashlib.sha256(raw).hexdigest(), "reporting_start": "2025-10-22", "reporting_end": "2026-10-21",
            "source_timezone": "America/Los_Angeles", "report_scope": "channel_owned", "report_content_format": "all", "filters_json": "{}",
            "retrieved_at_utc": "2026-10-23T12:30:00+00:00", "retrieved_at_basis": "synthetic_test_timestamp_only",
            "source_url": f"https://studio.youtube.com/channel/{CHANNEL_ID}/analytics", "evidence_paths": ["evidence/ui.txt"],
        })
    (source / "collection_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = build_daily_supplement(source, root / "synthetic-stage")
    database = result["database"]
    # The navigation target is a test-only placeholder. No base or live library
    # is opened, registered, or changed by these synthetic tests.
    script = f'''import streamlit as st
from stats_app.youtube_daily_supplement import DailySupplementRepository
from stats_app.youtube_ui import render_youtube_collection, render_collection_entry
repo = DailySupplementRepository({database!r})
keys = [repo.metadata["collection_key"], repo.metadata["parent_collection_key"]]
selected = st.sidebar.selectbox("YouTube collection", keys, key="youtube_collection_selector")
page = st.sidebar.radio("Synthetic test view", ["YouTube", "Sources", "Coverage"])
if selected == keys[1]:
    st.info("Parent collection navigation target selected (synthetic harness).")
elif page == "YouTube":
    render_youtube_collection(repo, collection_keys=keys)
else:
    render_collection_entry(repo, "sources" if page == "Sources" else "coverage", "synthetic_entry")
'''
    return script, result


@pytest.fixture
def app(synthetic_supplement):
    at = AppTest.from_string(synthetic_supplement[0], default_timeout=30).run()
    assert not at.exception and not at.error
    return at


def choose(at, label, value, kind="selectbox"):
    next(item for item in getattr(at, kind) if item.label == label).set_value(value).run()
    assert not at.exception, [item.value for item in at.exception]
    assert not at.error, [item.value for item in at.error]


def test_supplement_dispatch_and_date_versus_numeric_coverage(app):
    assert any("SYNTHETIC UI TEST FIXTURE" in item.value for item in app.caption)
    assert any("2025-10-22 – 2026-10-21 inclusive" in item.value for item in app.caption)
    assert any("must not be added together" in item.value for item in app.info)
    assert any("youtube-20261023" in item.value for item in app.markdown)
    assert [item.value for item in app.metric] == ["365 / 365", "361 / 365", "0"]
    assert len(app.get("plotly_chart")) == 1
    assert not any(item.label == "YouTube view" for item in app.selectbox)
    values = app.dataframe[0].value
    assert values.metric.nunique() == 1 and values.metric.iloc[0] == "watch_time_hours"
    assert values.iloc[0].value == 0 and values.iloc[0].value_status == "zero"
    assert pd.isna(values.iloc[1].value) and values.iloc[1].value_status == "unavailable"
    assert values.iloc[2].source_value_raw == "—"
    assert values.iloc[3].value_status == "suppressed"
    assert values.iloc[4].value_status == "not_applicable"
    assert values.iloc[5].value == 0.125 and values.iloc[5].unit == "hours"


def test_all_four_metrics_keep_native_units_and_raw_duration(app):
    for metric in METRICS:
        choose(app, "Supplement metric", metric)
        values = app.dataframe[0].value
        assert set(values.metric) == {metric}
        assert values.activity_date.nunique() == 250  # bounded first page
        assert [item.value for item in app.metric] == ["365 / 365", "361 / 365", "0"]
        assert len(app.get("plotly_chart")) == 1
        assert set(values.snapshot_class) == {"newly_retrieved_supplement"}
        assert set(values.parent_collection_key) == {COLLECTION_KEY}
        if metric == "average_view_duration_seconds":
            assert values.iloc[5].value == 92
            assert values.iloc[5].source_value_raw == "0:01:32"
            assert values.iloc[5].unit == "seconds" and values.iloc[5].aggregation == "nonadditive"
    assert any("neither summed nor averaged" in item.value for item in app.caption)


def test_supplement_row_lineage_and_coverage_statuses(app):
    choose(app, "Show displayed rows' lineage", True, "checkbox")
    lineage = next(item.value for item in app.dataframe if "stable_row_key" in item.value.columns)
    assert len(lineage) == 250 and lineage.stable_row_key.is_unique
    assert {"source_sha256", "source_zip_sha256", "source_row_number", "retrieved_at_basis"} <= set(lineage.columns)
    choose(app, "YouTube supplement view", "Coverage & validation")
    rows = app.dataframe[0].value
    assert len(rows) == 4 and set(rows.date_coverage_status) == {"complete"}
    assert set(rows.numeric_coverage_status) == {"partial"}
    assert set(rows.observed_dates) == {365} and set(rows.numeric_dates) == {361}
    choose(app, "Supplement coverage table", "Native report index")
    assert set(app.dataframe[0].value.status) == {"complete"}
    assert set(app.dataframe[0].value.numeric_coverage_status) == {"partial"}


def test_supplement_sources_and_existing_entries(app):
    choose(app, "YouTube supplement view", "Sources & provenance")
    assert any(item.label == "Download unchanged daily supplement package" for item in app.get("download_button"))
    choose(app, "Supplement source group", "Collection and UI evidence")
    choose(app, "Supplement retained source", "evidence/ui.txt")
    assert any("not collected account evidence" in item.value for item in app.text)
    choose(app, "Synthetic test view", "Sources", "radio")
    choose(app, "Inspect YouTube supplement sources", True, "checkbox")
    assert any(item.label == "Supplement retained source" for item in app.selectbox)
    choose(app, "Synthetic test view", "Coverage", "radio")
    choose(app, "Inspect YouTube supplement coverage", True, "checkbox")
    assert len(app.dataframe[0].value) == 4


def test_parent_button_changes_navigation_only(app):
    next(item for item in app.button if item.label == "Open parent YouTube collection").click().run()
    assert not app.exception and not app.error
    assert app.session_state["youtube_collection_selector"] == COLLECTION_KEY
    assert any("Parent collection navigation target selected" in item.value for item in app.info)
    assert not app.get("plotly_chart")


def test_existing_app_dispatches_synthetic_supplement_without_base_tables(synthetic_supplement, tmp_path, monkeypatch):
    from pathlib import Path
    from stats_app.youtube_daily_supplement import DailySupplementRepository
    import stats_app.youtube_repository as registration

    result = synthetic_supplement[1]
    repository = DailySupplementRepository(result["database"])
    original = Path(result["database"]).read_bytes()
    monkeypatch.setenv("STATS_DATA_DIR", str(tmp_path / "isolated-empty-library"))
    monkeypatch.setenv("STATS_MODE", "local")
    monkeypatch.setattr(registration, "load_registered_youtube", lambda *args: repository)
    monkeypatch.setattr(registration, "list_registered_youtube", lambda *args: [{"key": result["collection_key"], "label": result["label"]}])
    at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=30).run()
    choose(at, "Explore", "YouTube collection", "radio")
    assert any(item.label == "YouTube supplement view" for item in at.selectbox)
    assert [item.value for item in at.metric] == ["365 / 365", "361 / 365", "0"]
    assert Path(result["database"]).read_bytes() == original
