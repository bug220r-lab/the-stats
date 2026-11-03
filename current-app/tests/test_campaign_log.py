"""Synthetic, isolated metadata tests; no production findings or exports."""
import csv
import io
from pathlib import Path
import sqlite3

import pytest
from native_navigation_helpers import NativeAppTest as AppTest

from stats_app.access import Principal
from stats_app.campaign_log import CampaignLogRepository, COLUMNS, editable_csv, export_csv, parse_campaign_csv
from stats_app.storage import SQLiteRepository


ADMIN = Principal("Synthetic admin", "admin")
VIEWER = Principal("Synthetic viewer", "viewer")
ROOT = Path(__file__).resolve().parents[1]


def record(**changes):
    return {"platform": "Instagram", "account_id": "000001", "post_id": "0099",
            "event_type": "post", "publication_timestamp": "2026-10-20T12:00:00-07:00",
            "publication_timezone": "America/Los_Angeles", "revision_timestamp": "2026-10-23T12:00:00Z",
            "source_reference": "synthetic fixture, not production", **changes}


def csv_bytes(*rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def test_source_bytes_ids_unknowns_and_import_idempotency(tmp_path):
    path = tmp_path / "stats.sqlite3"
    repo = CampaignLogRepository(path)
    assert repo.current().empty and not path.exists()
    raw = csv_bytes(record())
    first = repo.import_csv(raw, "fixture.csv", ADMIN)
    assert first["added"] == 1 and not first["duplicate_import"]
    assert repo.import_csv(raw, "renamed.csv", ADMIN)["duplicate_import"]
    assert repo.source_bytes(first["source_hash"]) == raw
    current = repo.current()
    assert len(current) == 1 and current.iloc[0].account_id == "000001" and current.iloc[0].post_id == "0099"
    assert current.iloc[0].opening_hook == "unknown" and current.spend.isna().all()
    assert current.iloc[0].publication_timestamp_utc == "2026-10-20T19:00:00.000000+00:00"
    assert len(repo.history()) == 1


def test_revisions_are_order_independent_and_overlap_never_multiplies_posts(tmp_path):
    old = record()
    new = record(revision_timestamp="2026-10-24T10:00:00-04:00", opening_hook="Synthetic hook",
                 tag_status="inferred", tag_provenance="Synthetic coder notes")
    for name, order in [("forward", [old, new]), ("reverse", [new, old])]:
        repo = CampaignLogRepository(tmp_path / (name + ".sqlite3"))
        for row in order:
            repo.import_csv(csv_bytes(row), name + ".csv", ADMIN)
        # Different source bytes overlap an identical revision and add another ID.
        repo.import_csv(csv_bytes(old, record(post_id="0100")), "overlap.csv", ADMIN)
        current = repo.current()
        assert len(current) == 2 and not current.duplicated(["platform", "account_id", "post_id"]).any()
        assert current.loc[current.post_id.eq("0099"), "opening_hook"].iloc[0] == "Synthetic hook"
        assert len(repo.history()) == 4


def test_equal_time_conflict_rejects_entire_import_and_preserves_other_tables(tmp_path):
    local = SQLiteRepository(tmp_path / "stats.sqlite3")
    repo = CampaignLogRepository(local.db_path)
    repo.import_csv(csv_bytes(record()), "one.csv", ADMIN)
    before = repo.history().to_json()
    raw = csv_bytes(record(post_id="0100"), record(notes="Conflicting same-time edit"))
    with pytest.raises(ValueError, match="Conflicting metadata"):
        repo.import_csv(raw, "bad.csv", ADMIN)
    assert repo.history().to_json() == before
    assert len(repo.current()) == 1
    with sqlite3.connect(local.db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM campaign_sources").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0


@pytest.mark.parametrize("change,match", [
    ({"revision_timestamp": "2026-10-23"}, "explicit offset"),
    ({"publication_timestamp": "2026-10-20T12:00:00"}, "explicit offset"),
    ({"publication_timestamp": "2026-10-20T12:00:00-04:00"}, "disagrees"),
    ({"publication_timestamp": "2026-03-08T02:30:00-08:00"}, "disagrees"),
    ({"publication_timezone": "Pacific"}, "IANA"),
    ({"publication_timezone": ""}, "require publication_timezone"),
    ({"spend": "0"}, "currency"),
    ({"duration_seconds": "NaN"}, "finite"),
    ({"production_effort_minutes": "-1"}, "nonnegative"),
    ({"song_title": "Synthetic song"}, "tag_status"),
    ({"distribution": "probably paid"}, "distribution"),
    ({"post_id": "unknown"}, "identity"),
])
def test_invalid_metadata_refused_before_storage(tmp_path, change, match):
    repo = CampaignLogRepository(tmp_path / "stats.sqlite3")
    with pytest.raises(ValueError, match=match):
        repo.import_csv(csv_bytes(record(**change)), "bad.csv", ADMIN)
    assert not repo.database_path.exists()


def test_unknown_publication_preserved_and_real_zero_is_not_missing():
    data = parse_campaign_csv(csv_bytes(record(publication_timestamp="", publication_timezone="",
                                             spend="0", currency="USD")))
    assert data.iloc[0].publication_timestamp == "unknown" and data.publication_timestamp_utc.isna().all()
    assert data.iloc[0].spend == 0


def test_viewer_cannot_import_and_safe_csv_does_not_modify_source(tmp_path):
    repo = CampaignLogRepository(tmp_path / "stats.sqlite3")
    raw = csv_bytes(record(notes="=HYPERLINK(example)"))
    with pytest.raises(PermissionError, match="approved admin"):
        repo.import_csv(raw, "fixture.csv", VIEWER)
    assert not repo.database_path.exists()
    receipt = repo.import_csv(raw, "fixture.csv", ADMIN)
    assert "'=HYPERLINK" in export_csv(repo.current()).decode("utf-8-sig")
    assert repo.source_bytes(receipt["source_hash"]) == raw


def test_editable_export_roundtrips_without_new_revisions_and_detects_source_tampering(tmp_path):
    repo = CampaignLogRepository(tmp_path / "stats.sqlite3")
    original = csv_bytes(record(notes="=literal text, not a computed metric"))
    receipt = repo.import_csv(original, "synthetic.csv", ADMIN)
    output = editable_csv(repo.current())
    assert next(csv.reader(io.StringIO(output.decode("utf-8-sig")))) == COLUMNS
    replay = repo.import_csv(output, "editable.csv", ADMIN)
    assert replay["added"] == 0 and len(repo.current()) == 1
    assert repo.current().iloc[0].notes == "=literal text, not a computed metric"
    with sqlite3.connect(repo.database_path) as db:
        db.execute("UPDATE campaign_sources SET source_bytes=? WHERE source_hash=?", (b"tampered", receipt["source_hash"]))
    with pytest.raises(ValueError, match="SHA-256"):
        repo.source_bytes(receipt["source_hash"])


def test_campaign_page_renders_log_timeline_and_viewer_permissions(tmp_path):
    path = tmp_path / "stats.sqlite3"
    CampaignLogRepository(path).import_csv(csv_bytes(record()), "fixture.csv", ADMIN)
    script = f"""
from stats_app.storage import SQLiteRepository
from stats_app.access import Principal
from stats_app.campaign_ui import render_campaigns
render_campaigns(SQLiteRepository({str(path)!r}), Principal('Viewer','viewer'))
"""
    app = AppTest.from_string(script).run()
    assert not app.exception and not app.error
    assert [metric.value for metric in app.metric] == ["1", "1", "0"]
    assert len(app.get("plotly_chart")) == 1
    assert not app.get("file_uploader")
    assert any("approved admin" in item.value for item in app.info)


def test_admin_preview_save_refreshes_log_and_replay_is_idempotent(tmp_path, monkeypatch):
    import streamlit as st
    raw = csv_bytes(record())
    upload = io.BytesIO(raw)
    upload.name = "synthetic.csv"
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: upload)
    path = tmp_path / "stats.sqlite3"
    script = f"""
from stats_app.storage import SQLiteRepository
from stats_app.access import Principal
from stats_app.campaign_ui import render_campaigns
render_campaigns(SQLiteRepository({str(path)!r}), Principal('Admin','admin'))
"""
    app = AppTest.from_string(script).run()
    assert not app.exception and not app.error
    assert any("Validated 1 source records" in item.value for item in app.caption)
    assert CampaignLogRepository(path).current().empty
    next(item for item in app.button if item.label == "Save campaign preview to SQLite").click().run()
    assert not app.exception and not app.error
    assert app.metric[0].value == "1" and any("Saved 1 new metadata" in item.value for item in app.success)
    next(item for item in app.button if item.label == "Save campaign preview to SQLite").click().run()
    assert not app.exception and any("already imported" in item.value for item in app.success)
    assert len(CampaignLogRepository(path).history()) == 1


def test_optional_unreadable_youtube_does_not_block_normal_app(tmp_path, monkeypatch):
    import stats_app.youtube_repository as youtube_repository
    attempts = []
    def unreadable(*args, **kwargs):
        attempts.append(args)
        raise PermissionError("Synthetic inaccessible optional collection")
    monkeypatch.setattr(youtube_repository, "load_registered_youtube", unreadable)
    monkeypatch.setattr(youtube_repository, "list_registered_youtube", lambda *args, **kwargs: [
        {"key": "synthetic-unreadable", "label": "Synthetic unreadable collection"}])
    monkeypatch.setenv("STATS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("STATS_MODE", "local")
    app = AppTest.from_file(str(ROOT / "app.py")).run()
    assert not app.exception and not app.error
    assert not attempts, "Overview should not open an unrelated optional collection"
    from native_navigation_helpers import open_page
    open_page(app, "YouTube collection")
    assert attempts and any("Synthetic inaccessible optional collection" in item.value for item in app.error)
    assert any("Other destinations remain available" in item.value for item in app.info)
    open_page(app, "Campaigns")
    assert not app.exception and not app.error
    assert any("No content/campaign metadata" in item.value for item in app.info)
