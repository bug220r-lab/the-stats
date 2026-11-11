"""Actual Import data bindings for the audit's row-loss and scope regressions."""
from contextlib import closing
import csv
from pathlib import Path
import sqlite3

from native_navigation_helpers import NativeAppTest as AppTest

from native_navigation_helpers import open_page

from stats_app.storage import SQLiteRepository
from stats_app.validation import COLUMNS


ROOT = Path(__file__).resolve().parents[1]


def record(identity, definition="Organic video views"):
    return dict(platform="Instagram", account="synthetic-account", entity_type="video",
                entity_id=identity, metric="views", value=25, unit="count", period_start="2026-10-01",
                period_end="2026-10-01", time_grain="daily", measurement_type="period_count",
                source_timezone="UTC", status="observed", dimensions_json="{}", definition=definition)


def source_file(tmp_path, records):
    folder = tmp_path / "synthetic-exports"
    folder.mkdir()
    path = folder / "synthetic.csv"
    fields = ["entity_id"] + [key for key in COLUMNS if key not in {"entity_id", "source_row", "worksheet"}]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    return path


def import_page(monkeypatch, data_dir, path):
    monkeypatch.setenv("STATS_MODE", "local")
    monkeypatch.setenv("STATS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("STATS_IMPORT_DIR", str(path.parent))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    open_page(app, "Import data")
    next(item for item in app.radio if item.label == "Source").set_value("Configured import folder").run()
    next(item for item in app.text_input if item.label == "Snapshot label").set_value("Synthetic capture")
    assert not app.exception and not app.error
    return app


def button(app, label):
    return next(item for item in app.button if item.label == label)


def counts(data_dir):
    with closing(sqlite3.connect(data_dir / "stats.sqlite3")) as connection:
        return {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in ("snapshots", "observations", "imports", "source_files")}


def test_day_date_rows_survive_actual_preview_save_and_replay(tmp_path, monkeypatch):
    path = source_file(tmp_path, [record(identity) for identity in ("first", "Day", "Date", "last")])
    original = path.read_bytes()
    data_dir = tmp_path / "isolated-library"
    app = import_page(monkeypatch, data_dir, path)
    button(app, "Validate and preview").click().run()
    assert not app.exception and not app.error
    assert [metric.value for metric in app.metric] == ["4", "0"]
    assert app.dataframe[-1].value.entity_id.tolist() == ["first", "Day", "Date", "last"]
    assert counts(data_dir) == dict(snapshots=0, observations=0, imports=0, source_files=0)
    button(app, "Save this preview to SQLite").click().run()
    assert not app.exception and not app.error
    assert counts(data_dir) == dict(snapshots=1, observations=4, imports=1, source_files=1)
    button(app, "Validate and preview").click().run()
    assert not app.exception and not app.error
    assert [metric.value for metric in app.metric] == ["0", "4"]
    button(app, "Save this preview to SQLite").click().run()
    assert not app.exception and not app.error
    assert counts(data_dir) == dict(snapshots=1, observations=4, imports=1, source_files=1)
    assert path.read_bytes() == original


def test_definition_conflict_is_a_visible_refusal_before_any_save(tmp_path, monkeypatch):
    path = source_file(tmp_path, [record("same-video", "Paid video views")])
    data_dir = tmp_path / "isolated-library"
    repo = SQLiteRepository(data_dir / "stats.sqlite3")
    repo.import_dataset(b"original organic evidence", "organic.csv", [record("same-video")], "Synthetic capture")
    before = counts(data_dir)
    app = import_page(monkeypatch, data_dir, path)
    button(app, "Validate and preview").click().run()
    assert not app.exception
    assert any("definition or scope" in error.value for error in app.error)
    assert not any(item.label == "Save this preview to SQLite" for item in app.button)
    assert counts(data_dir) == before
    assert repo.observations("Synthetic capture").definition.tolist() == ["Organic video views"]
