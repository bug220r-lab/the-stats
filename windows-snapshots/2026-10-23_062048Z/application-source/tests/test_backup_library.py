"""Portable full-library backup and read-only verification."""
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from stats_app.backup import backup_database, backup_library, verify_bundle
from stats_app.library import LibraryRepository
from stats_app.retained_store import Store
from stats_app.storage import SQLiteRepository, StorageError


@pytest.fixture
def registered_library(tmp_path):
    data = tmp_path / "live"
    local = SQLiteRepository(data / "stats.sqlite3")
    archive_root = data / "archives" / "retained"
    archive = Store(archive_root / "data" / "stats.sqlite3")
    sid = archive.create_snapshot("Preserved Spotify", status="unverified", evidence="original evidence")
    raw = b"date,streams\n2026-10-20,7\n"
    archive.commit_import(sid, "native.csv", raw, [{
        "platform": "spotify", "account_id": "artist-1", "account_name": "Artist",
        "entity_type": "artist", "entity_id": "artist-1", "entity_name": "Artist",
        "metric": "streams", "value": 7, "unit": "count", "definition": "period streams",
        "dimensions": {}, "period_start": "2026-10-20", "period_end": "2026-10-20",
        "time_grain": "daily", "measurement_type": "period_count", "status": "available",
        "source_timezone": "UTC", "source_row": 2,
    }])
    (archive_root / "spotify_coverage.json").write_text('{"gaps":["Unknown earlier dates"]}', encoding="utf-8")
    (archive_root / "evidence").mkdir()
    (archive_root / "evidence" / "capture.txt").write_bytes(b"Original capture bytes\r\n")
    registry = {"archives": [{"key": "retained", "label": "Recovered",
                "database": "archives/retained/data/stats.sqlite3",
                "source_dir": "archives/retained/data/sources", "evidence_root": "archives/retained"}]}
    (data / "archive_registry.json").write_text(json.dumps(registry), encoding="utf-8")
    (data / "unregistered-private.txt").write_text("Do not include", encoding="utf-8")
    return data, local, archive, raw


def test_bundle_restores_portable_library_and_preserves_sources(registered_library, tmp_path):
    data, local, archive, raw = registered_library
    original_bytes = archive.path.read_bytes()
    bundle = backup_library(data, tmp_path / "new-bundle")
    manifest = verify_bundle(bundle)
    assert manifest["archive_count"] == 1
    assert not (bundle / "unregistered-private.txt").exists()
    assert (bundle / "archive_registry.json").read_bytes() == (data / "archive_registry.json").read_bytes()
    assert archive.path.read_bytes() == original_bytes
    restored = LibraryRepository(SQLiteRepository(bundle / "stats.sqlite3"))
    snapshots = restored.list_snapshots()
    selected = snapshots[snapshots.backend.eq("retained")].iloc[0]
    assert restored.observations(selected.label).iloc[0].value == 7
    assert restored.original_source(hashlib.sha256(raw).hexdigest()) == raw
    assert restored.evidence_reports()["retained::spotify_coverage.json"]["gaps"] == ["Unknown earlier dates"]


def test_bundle_refuses_overwrite_and_detects_corruption(registered_library, tmp_path):
    data, _, _, _ = registered_library
    bundle = backup_library(data, tmp_path / "bundle")
    before = (bundle / "BACKUP_MANIFEST.json").read_bytes()
    with pytest.raises(FileExistsError):
        backup_library(data, bundle)
    assert (bundle / "BACKUP_MANIFEST.json").read_bytes() == before
    (bundle / "archives/retained/evidence/capture.txt").write_bytes(b"changed")
    with pytest.raises(StorageError, match="verification"):
        verify_bundle(bundle)


def test_bundle_rejects_escaping_registry_before_writing(registered_library, tmp_path):
    data, _, _, _ = registered_library
    registry = json.loads((data / "archive_registry.json").read_text())
    registry["archives"][0]["evidence_root"] = "../unrelated"
    (data / "archive_registry.json").write_text(json.dumps(registry))
    target = tmp_path / "bad-bundle"
    with pytest.raises(StorageError, match="inside"):
        backup_library(data, target)
    assert not target.exists()


def test_local_backup_includes_committed_wal_without_checkpoint(registered_library, tmp_path):
    data, _, _, _ = registered_library
    with sqlite3.connect(data / "stats.sqlite3") as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE backup_test(value TEXT)")
        writer.execute("INSERT INTO backup_test VALUES('committed in WAL')")
        writer.commit()
        database_before = (data / "stats.sqlite3").read_bytes()
        wal_before = Path(str(data / "stats.sqlite3") + "-wal").read_bytes()
        result = backup_database(data / "stats.sqlite3", tmp_path / "local.sqlite3")
        assert (data / "stats.sqlite3").read_bytes() == database_before
        assert Path(str(data / "stats.sqlite3") + "-wal").read_bytes() == wal_before
        with sqlite3.connect(result) as restored:
            assert restored.execute("SELECT value FROM backup_test").fetchone()[0] == "committed in WAL"
    with pytest.raises(FileExistsError):
        backup_database(data / "stats.sqlite3", result)


def test_active_archive_wal_is_rejected(registered_library, tmp_path):
    data, _, archive, _ = registered_library
    Path(str(archive.path) + "-wal").write_bytes(b"not a fixed archive")
    with pytest.raises(StorageError, match="journal"):
        backup_library(data, tmp_path / "bad-bundle")


def test_local_only_library_has_valid_empty_registry(tmp_path):
    data = tmp_path / "local"
    SQLiteRepository(data / "stats.sqlite3")
    bundle = backup_library(data, tmp_path / "bundle")
    assert verify_bundle(bundle)["archive_count"] == 0
    assert LibraryRepository(SQLiteRepository(bundle / "stats.sqlite3")).archives == {}
