"""Portable YouTube evidence backups keep the prior analysis separate."""
import hashlib
import json
import os
from pathlib import Path
import zipfile

import pandas as pd
import pytest

from stats_app.analysis_repository import load_registered_analysis, stage_analysis_package
from stats_app.backup import backup_library, verify_bundle
from stats_app.storage import SQLiteRepository, StorageError
from stats_app.youtube_repository import (
    COLLECTION_KEY, REGISTRY_FILENAME, ZIP_FILENAME,
    import_youtube_collection, load_registered_youtube,
)


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _old_analysis(tmp_path, live):
    """Create an independently registered predecessor with baseline metadata."""
    source = b"date,streams\n2026-10-20,7\n"
    files = {
        "raw/source.csv": source,
        "spotify/cleaned/artist_daily.csv": source,
        "audit/final_validation.json": b'{"checks":{"raw_source_files_unchanged":true}}',
        "raw_sha256.json": json.dumps([
            {"path": "raw/source.csv", "bytes": len(source),
             "sha256": hashlib.sha256(source).hexdigest()}
        ]).encode(),
    }
    root, archive = tmp_path / "previous-source", tmp_path / "previous.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for name, raw in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            zipped.writestr(root.name + "/" + name, raw)
    stage_analysis_package(root, archive, live / "analysis/previous")
    registry = {"archives": [], "analysis_package": {
        "database": "analysis/previous/analysis.sqlite3",
        "evidence_root": "analysis/previous", "label": "Preserved prior analysis",
    }}
    (live / "archive_registry.json").write_text(json.dumps(registry), encoding="utf-8")


def _private_package():
    configured = os.environ.get("STATS_YOUTUBE_TEST_ZIP")
    candidates = [Path(configured)] if configured else []
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    candidates.extend([
        local / "TheStats/collections" / COLLECTION_KEY / ZIP_FILENAME,
        local / "Temp/youtube_collection_2026-10-23" / ZIP_FILENAME,
    ])
    for path in candidates:
        try:
            if path.is_file():
                with path.open("rb") as handle:
                    handle.read(1)
                return path
        except (PermissionError, FileNotFoundError):
            continue
    pytest.skip("Private YouTube source ZIP unavailable; set STATS_YOUTUBE_TEST_ZIP to run relocation acceptance.")


def test_youtube_bundle_relocation_preserves_sources_rows_and_prior_analysis(tmp_path):
    package = _private_package()
    live = tmp_path / "live"
    SQLiteRepository(live / "stats.sqlite3")
    _old_analysis(tmp_path, live)
    old_registry = (live / "archive_registry.json").read_bytes()
    old_database = _hash(live / "analysis/previous/analysis.sqlite3")
    import_youtube_collection(package, live)
    original = load_registered_youtube(live)
    youtube_registry = (live / REGISTRY_FILENAME).read_bytes()
    collection_database = _hash(original.db_path)

    bundle = backup_library(live, tmp_path / "bundle")
    manifest = verify_bundle(bundle)
    assert manifest["youtube_collections_included"] == 1
    assert manifest["analysis_versions_included"] == 1
    assert (bundle / "archive_registry.json").read_bytes() == old_registry
    assert (bundle / REGISTRY_FILENAME).read_bytes() == youtube_registry
    assert _hash(original.db_path) == collection_database
    assert _hash(live / "analysis/previous/analysis.sqlite3") == old_database

    # Relocate the complete directory, then remove reliance on the original path.
    relocated = tmp_path / "relocated"
    bundle.rename(relocated)
    restored = load_registered_youtube(relocated)
    assert restored.db_path.is_relative_to(relocated)
    assert _hash(restored.db_path) == collection_database
    assert restored.original_zip() == package.read_bytes()
    assert (restored.evidence_root / ZIP_FILENAME).read_bytes() == package.read_bytes()
    assert restored.tables == original.tables
    for path in restored.tables:
        pd.testing.assert_frame_equal(restored.table(path, raw=True), original.table(path, raw=True))
        assert restored.row_keys(path) == original.row_keys(path)
        assert restored.original_bytes(path) == original.original_bytes(path)
    for path in restored.file_catalog().path:
        assert restored.original_bytes(path) == original.original_bytes(path)
    previous = load_registered_analysis(relocated)
    assert previous.registered_key == "previous"
    assert previous.metadata["baseline_status"] == "unverified"
    assert previous.table("spotify/cleaned/artist_daily.csv").streams.tolist() == [7]
    assert _hash(previous.db_path) == old_database

    # A changed retained source must invalidate the saved bundle receipt.
    retained_zip = restored.evidence_root / ZIP_FILENAME
    with retained_zip.open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(StorageError, match="verification"):
        verify_bundle(relocated)
    with pytest.raises(StorageError):
        backup_library(relocated, tmp_path / "reject-tampered-source")
    assert not (tmp_path / "reject-tampered-source").exists()
    retained_zip.write_bytes(package.read_bytes())
    with restored.db_path.open("ab") as stream:
        stream.write(b"tampered database")
    with pytest.raises(StorageError):
        backup_library(relocated, tmp_path / "reject-tampered-database")
    assert not (tmp_path / "reject-tampered-database").exists()
    assert _hash(original.db_path) == collection_database
    assert (live / "archive_registry.json").read_bytes() == old_registry


@pytest.mark.parametrize("registry", [
    {"schema_version": 2, "collections": []},
    {"schema_version": 1, "collections": {}},
    {"schema_version": 1, "collections": [{"key": COLLECTION_KEY,
        "database": "../outside.sqlite3", "evidence_root": "../outside"}]},
    {"schema_version": 1, "collections": [{"key": COLLECTION_KEY,
        "database": "stats.sqlite3", "evidence_root": "."}]},
])
def test_invalid_youtube_registry_is_rejected_before_bundle_creation(tmp_path, registry):
    live = tmp_path / "live"
    SQLiteRepository(live / "stats.sqlite3")
    path = live / REGISTRY_FILENAME
    path.write_text(json.dumps(registry), encoding="utf-8")
    before = path.read_bytes()
    target = tmp_path / "bundle"
    with pytest.raises(StorageError):
        backup_library(live, target)
    assert not target.exists()
    assert path.read_bytes() == before


def test_malformed_youtube_registry_is_rejected_without_replacing_prior_registry(tmp_path):
    live = tmp_path / "live"
    SQLiteRepository(live / "stats.sqlite3")
    old_registry = b'{"archives":[]}\n'
    (live / "archive_registry.json").write_bytes(old_registry)
    (live / REGISTRY_FILENAME).write_bytes(b"{invalid JSON")
    with pytest.raises(StorageError, match="registry"):
        backup_library(live, tmp_path / "bundle")
    assert (live / "archive_registry.json").read_bytes() == old_registry
    assert not (tmp_path / "bundle").exists()
