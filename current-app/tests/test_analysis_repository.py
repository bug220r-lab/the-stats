"""Separate immutable analysis snapshots with safe types and exact package bytes."""
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile

import pandas as pd
import pytest

from stats_app.analysis_repository import AnalysisRepository, load_registered_analysis, stage_analysis_package
from stats_app.backup import backup_library, verify_bundle
from stats_app.storage import SQLiteRepository, StorageError


@pytest.fixture
def package(tmp_path):
    root = tmp_path / "analysis_package"
    files = {
        "raw/source.csv": b"date,streams\n2026-10-20,0\n",
        "spotify/cleaned/artist_daily.csv": b"artist_id,date,daily_streams,follower_net_change,source_file,source_row\n00123,2026-10-19,0,,raw/source.csv,2\n00123,2026-10-20,7,1,raw/source.csv,3\n",
        "social/posts_latest.csv": b"post_id,partial_day,value,value_raw,publication_date,measurement_type\n18216593050358711,False,,0,2026-10-20,lifetime_content_snapshot\n",
        "cross_platform/statistical_results.csv": b"analysis_id,inference_eligible,p_circular_shift,ci95_low_block4\ntest1,False,,\n",
        "README.md": b"Keep all distinct metric grains.\n",
        "audit/final_validation.json": b'{"checks":{"raw_source_files_unchanged":true}}',
    }
    raw_manifest = [{"path": "raw/source.csv", "bytes": len(files["raw/source.csv"]), "sha256": hashlib.sha256(files["raw/source.csv"]).hexdigest()}]
    files["raw_sha256.json"] = json.dumps(raw_manifest).encode()
    for name, data in files.items():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    archive = tmp_path / "original.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for name, data in files.items():
            zipped.writestr(root.name + "/" + name, data)
    return root, archive, files


def test_package_persists_identity_missing_flags_and_lineage(package, tmp_path):
    root, archive, files = package
    report = stage_analysis_package(root, archive, tmp_path / "staged", "https://example.test/original.zip")
    repo = AnalysisRepository(report["database"])
    before = Path(report["database"]).read_bytes()
    frame = repo.table("spotify/cleaned/artist_daily.csv")
    assert frame.artist_id.tolist() == ["00123", "00123"]
    assert str(frame.daily_streams.dtype) == "Int64"
    assert frame.daily_streams.tolist() == [0, 7]
    assert pd.isna(frame.follower_net_change.iloc[0])
    assert frame.date.iloc[0] == "2026-10-19"
    social = repo.table("social/posts_latest.csv")
    assert social.post_id.iloc[0] == "18216593050358711"
    assert not social.partial_day.iloc[0]
    assert pd.isna(social.value.iloc[0]) and social.value_raw.iloc[0] == "0"
    statistics = repo.table("cross_platform/statistical_results.csv")
    assert pd.isna(statistics.p_circular_shift.iloc[0])
    assert not statistics.inference_eligible.iloc[0]
    provenance = repo.row_provenance("spotify/cleaned/artist_daily.csv")
    assert provenance.package_csv_record.tolist() == [2, 3]
    assert provenance.source_file.tolist() == ["raw/source.csv", "raw/source.csv"]
    assert repo.original_zip() == archive.read_bytes()
    assert repo.original_bytes("raw/source.csv") == files["raw/source.csv"]
    assert repo.text("README.md").startswith("Keep")
    assert repo.metadata["baseline_status"] == "unverified"
    assert "raw/source.csv" not in repo.tables
    assert Path(report["database"]).read_bytes() == before
    with repo._connection() as connection, pytest.raises(sqlite3.OperationalError, match="readonly"):
        connection.execute("DELETE FROM metadata")


def test_same_package_replay_and_mismatch_refusal(package, tmp_path):
    root, archive, _ = package
    output = tmp_path / "stage"
    original = stage_analysis_package(root, archive, output)
    before = Path(original["database"]).read_bytes()
    assert stage_analysis_package(root, archive, output)["idempotent"]
    assert Path(original["database"]).read_bytes() == before
    (root / "README.md").write_text("changed", encoding="utf-8")
    with pytest.raises(StorageError, match="differs from original ZIP"):
        stage_analysis_package(root, archive, output)
    assert Path(original["database"]).read_bytes() == before


def test_bad_raw_hash_and_path_rejected(package, tmp_path):
    root, archive, _ = package
    (root / "raw/source.csv").write_bytes(b"changed")
    with pytest.raises(StorageError, match="Raw package audit failed"):
        stage_analysis_package(root, archive, tmp_path / "stage")
    assert not (tmp_path / "stage").exists()


def test_registered_analysis_survives_portable_backup(package, tmp_path):
    root, archive, _ = package
    data = tmp_path / "live"
    SQLiteRepository(data / "stats.sqlite3")
    stage_analysis_package(root, archive, data / "analysis/cleaned-20261022")
    registry = {"archives": [], "analysis_package": {"database": "analysis/cleaned-20261022/analysis.sqlite3", "evidence_root": "analysis/cleaned-20261022", "label": "Cleaned analysis"}}
    (data / "archive_registry.json").write_text(json.dumps(registry), encoding="utf-8")
    bundle = backup_library(data, tmp_path / "bundle")
    assert verify_bundle(bundle)["analysis_package_included"]
    restored = AnalysisRepository(bundle / registry["analysis_package"]["database"])
    assert restored.table("spotify/cleaned/artist_daily.csv").daily_streams.sum() == 7
    assert restored.original_zip() == archive.read_bytes()
    registered = load_registered_analysis(bundle)
    assert registered.registered_label == "Cleaned analysis"
    assert registered.table("spotify/cleaned/artist_daily.csv").daily_streams.sum() == 7
    registry["analysis_package"]["database"] = "../outside.sqlite3"
    (bundle / "archive_registry.json").write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(StorageError, match="Unsafe"):
        load_registered_analysis(bundle)


def test_row_tampering_is_detected(package, tmp_path):
    root, archive, _ = package
    report = stage_analysis_package(root, archive, tmp_path / "stage")
    with sqlite3.connect(report["database"]) as connection:
        connection.execute("UPDATE analysis_rows SET row_json='[]' WHERE asset_path='spotify/cleaned/artist_daily.csv' AND csv_record=2")
    with pytest.raises(StorageError, match="differ from"):
        AnalysisRepository(report["database"]).table("spotify/cleaned/artist_daily.csv")
