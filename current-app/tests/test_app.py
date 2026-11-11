from pathlib import Path
import time

import pytest
from native_navigation_helpers import NativeAppTest as AppTest

from native_navigation_helpers import open_page

from stats_app.access import Principal, authorize_claims, require_admin
from stats_app.config import PROJECT_ROOT
from stats_app.storage import SQLiteRepository


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DATA_DIR", str(tmp_path / "db"))
    monkeypatch.setenv("STATS_MODE", "local")
    monkeypatch.delenv("STATS_IMPORT_DIR", raising=False)
    return tmp_path


def app():
    return AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=30).run()


def button(at, text):
    return next(item for item in at.button if item.label == text)


def test_empty_dashboard_and_import_screen(isolated_app):
    at = app()
    assert not at.exception
    assert any("No observations" in item.value for item in at.info)
    open_page(at, "Import data")
    assert not at.exception
    assert any(item.label == "CSV, TSV or XLSX export" for item in at.get("file_uploader"))


def test_folder_import_preview_commit_duplicate_and_restart(isolated_app, monkeypatch):
    imports = isolated_app / "imports"
    imports.mkdir()
    (imports / "fixture.csv").write_text(
        "platform,account,entity_type,entity_id,metric,value,unit,period_start,period_end,time_grain,measurement_type,status\n"
        "Spotify,test-account,artist,test-id,streams,17,count,2026-10-19,2026-10-19,daily,period_count,observed\n"
        "Spotify,test-account,artist,test-id,streams,,count,2026-10-20,2026-10-20,daily,period_count,missing\n", encoding="utf-8")
    monkeypatch.setenv("STATS_IMPORT_DIR", str(imports))
    at = app()
    open_page(at, "Import data")
    next(r for r in at.radio if r.label == "Source").set_value("Configured import folder").run()
    assert not at.exception
    button(at, "Validate and preview").click().run()
    assert not at.exception
    assert not at.error
    button(at, "Save this preview to SQLite").click().run()
    assert not at.exception
    assert any("2 new records" in item.value for item in at.success)
    button(at, "Validate and preview").click().run()
    button(at, "Save this preview to SQLite").click().run()
    assert any("0 new records" in item.value for item in at.success)
    restart = app()
    assert not restart.exception
    assert len(restart.get("plotly_chart")) == 1
    assert any(m.value == "Unavailable" for m in restart.metric)
    repo = SQLiteRepository(isolated_app / "db" / "stats.sqlite3")
    label = repo.list_snapshots().iloc[0].label
    data = repo.observations(label)
    assert len(data) == 2
    assert data.value.sum() == 17
    assert data.loc[data.status.eq("missing"), "value"].isna().all()
    open_page(restart, "Sources & provenance")
    assert not restart.exception
    assert len(restart.dataframe) == 2


def test_hosted_missing_auth_fails_before_database_read(isolated_app, monkeypatch):
    monkeypatch.setenv("STATS_MODE", "hosted")
    monkeypatch.delenv("STATS_APPROVED_USERS_FILE", raising=False)
    at = app()
    assert not at.exception
    assert any("access denied" in item.value.lower() for item in at.error)
    assert not (isolated_app / "db" / "stats.sqlite3").exists()


def test_local_public_binding_denied(isolated_app, monkeypatch):
    import streamlit as st
    original = st.get_option
    monkeypatch.setattr(st, "get_option", lambda key: "0.0.0.0" if key == "server.address" else original(key))
    at = app()
    assert any("Local access refused" in item.value for item in at.error)
    assert not (isolated_app / "db" / "stats.sqlite3").exists()


def test_viewer_cannot_import(isolated_app, monkeypatch):
    import stats_app.ui as ui
    monkeypatch.setattr(ui, "enforce_access", lambda settings: Principal("Test viewer", "viewer"))
    at = app()
    open_page(at, "Import data")
    assert any("viewer permission" in item.value for item in at.info)
    assert not at.get("file_uploader")
    with pytest.raises(PermissionError):
        require_admin(Principal("Test viewer", "viewer"))


def test_claims_require_approved_issuer_subject_and_expiry():
    issuer = "https://identity.example.invalid"
    users = [dict(name="Test viewer", issuer=issuer, subject="test-subject", role="viewer")]
    claims = dict(iss=issuer, sub="test-subject", exp=time.time() + 60)
    assert authorize_claims(claims, users, issuer).role == "viewer"
    for changes in ({"sub": "unapproved"}, {"iss": "https://wrong.example.invalid"}, {"exp": 0}, {"exp": None}):
        with pytest.raises(PermissionError):
            authorize_claims(claims | changes, users, issuer)


def test_apple_music_daily_and_period_scopes_stay_separate(isolated_app):
    repo = SQLiteRepository(isolated_app / "db" / "stats.sqlite3")
    base = dict(platform="Apple Music", account="Synthetic Apple artist", entity_type="artist",
                entity_id="apple-artist", entity_name="Synthetic Apple artist", metric="plays", unit="count",
                time_grain="daily", measurement_type="period_count", source_timezone="UTC", status="observed",
                dimensions_json='{"entity_scope":"artist"}', definition="Synthetic Apple Plays fixture.")
    rows = [base | dict(period_start=day, period_end=day, value=value)
            for day, value in [("2026-10-22", 7), ("2026-10-23", 10)]]
    rows.append(base | dict(period_start="2026-10-22", period_end="2026-10-23", time_grain="period", value=17))
    rows.extend(base | dict(metric="daily_unique_listeners", measurement_type="distinct_count",
                           period_start=day, period_end=day, value=value,
                           definition="Synthetic daily unique listeners; never total across dates.")
                for day, value in [("2026-10-22", 5), ("2026-10-23", 6)])
    repo.import_dataset(b"synthetic-apple-export", "apple.csv", rows, "Apple Music synthetic capture")

    at = app()
    assert not at.exception and not at.error
    platform = next(item for item in at.selectbox if item.label == "Platform")
    assert platform.value == "Apple Music"
    assert len(at.get("plotly_chart")) == 1

    scope = next(item for item in at.selectbox if item.label == "Measurement scope")
    daily_index = next(i for i, option in enumerate(scope.options) if option.startswith("Daily"))
    scope.set_value(daily_index).run()
    assert {item.label: item.value for item in at.metric} == {
        "Selected period total": "17", "Latest reported endpoint": "10", "Observed source records": "2"}

    scope = next(item for item in at.selectbox if item.label == "Measurement scope")
    period_index = next(i for i, option in enumerate(scope.options) if option.startswith("Period"))
    scope.set_value(period_index).run()
    assert not at.exception and not at.error
    assert next(item for item in at.selectbox if item.label == "Exact source period").value == ("2026-10-22", "2026-10-23")
    assert {item.label: item.value for item in at.metric} == {
        "Selected period total": "17", "Latest reported endpoint": "17", "Observed source records": "1"}

    next(item for item in at.selectbox if item.label == "Metric").set_value("daily_unique_listeners").run()
    assert not at.exception and not at.error
    assert {item.label: item.value for item in at.metric} == {
        "Selected period aggregation": "Unavailable", "Latest reported endpoint": "6", "Observed source records": "2"}
    assert any("shown separately" in item.value for item in at.caption)
