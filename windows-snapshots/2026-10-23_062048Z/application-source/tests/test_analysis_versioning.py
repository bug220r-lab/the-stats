"""Immutable analysis history, atomic activation and portable version backups."""
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from scripts.promote_analysis import promote
from stats_app.analysis_repository import (
    AnalysisRepository, list_registered_analyses, load_registered_analysis, stage_analysis_package,
)
from stats_app.backup import backup_library, verify_bundle
from stats_app.storage import SQLiteRepository, StorageError


def make_package(tmp_path, name, streams):
    root = tmp_path / name
    raw = f"date,streams\n2026-10-20,{streams}\n".encode()
    files = {
        "raw/source.csv": raw,
        "spotify/cleaned/artist_daily.csv": raw,
        "audit/final_validation.json": b'{"checks":{"raw_source_files_unchanged":true}}',
        "raw_sha256.json": json.dumps([{"path": "raw/source.csv", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}]).encode(),
    }
    archive = tmp_path / (name + ".zip")
    with zipfile.ZipFile(archive, "w") as zipped:
        for name, contents in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
            zipped.writestr(root.name + "/" + name, contents)
    return root, archive


@pytest.fixture
def versions(tmp_path):
    live = tmp_path / "live"
    SQLiteRepository(live / "stats.sqlite3")
    old_root, old_zip = make_package(tmp_path, "original", 7)
    old_dir = live / "analysis/cleaned-20261022"
    stage_analysis_package(old_root, old_zip, old_dir)
    registry = {"archives": [], "analysis_package": {
        "database": "analysis/cleaned-20261022/analysis.sqlite3", "evidence_root": "analysis/cleaned-20261022", "label": "Original cleaned analysis",
    }}
    (live / "archive_registry.json").write_text(json.dumps(registry), encoding="utf-8")
    new_root, new_zip = make_package(tmp_path, "combined", 9)
    stage = tmp_path / "stage"
    stage_analysis_package(new_root, new_zip, stage, "https://example.test/collection",
                           label="Expanded Spotify collection", metadata={"activity_endpoint": "2026-10-21", "retrieval_vintage": "2026-10-23",
                           "version_lineage": [{"key": "cleaned-20261022", "purpose": "preserved predecessor"}]})
    audit = tmp_path / "independent_audit.json"
    audit.write_text('{"verified":true}', encoding="utf-8")
    return live, stage, audit, old_zip, new_zip


def test_legacy_key_is_inferred_without_rewriting_registry(versions):
    live, _, _, _, _ = versions
    before = (live / "archive_registry.json").read_bytes()
    records = list_registered_analyses(live)
    assert len(records) == 1 and records[0]["key"] == "cleaned-20261022"
    assert records[0]["active"]
    assert load_registered_analysis(live).registered_key == "cleaned-20261022"
    assert load_registered_analysis(live, "cleaned-20261022").table("spotify/cleaned/artist_daily.csv").streams.tolist() == [7]
    assert (live / "archive_registry.json").read_bytes() == before
    with pytest.raises(StorageError, match="No registered"):
        load_registered_analysis(live, "not-imported")


def test_activation_keeps_prior_versions_exact_and_replay_is_read_only(versions, tmp_path):
    live, stage, audit, old_zip, new_zip = versions
    old = {p: p.read_bytes() for p in live.rglob("*.sqlite3")}
    report = promote(stage, audit, live, key="expanded-20261023")
    assert report["active"] and not report["idempotent"]
    assert all(path.read_bytes() == contents for path, contents in old.items())
    assert [r["active"] for r in list_registered_analyses(live)] == [False, True]
    assert load_registered_analysis(live).registered_key == "expanded-20261023"
    assert load_registered_analysis(live).original_zip() == new_zip.read_bytes()
    assert load_registered_analysis(live, "cleaned-20261022").original_zip() == old_zip.read_bytes()
    assert load_registered_analysis(live).metadata["baseline_status"] == "unverified"
    receipt = json.loads((live / "analysis/expanded-20261023/activation_receipt.json").read_text())
    assert set(receipt["earlier_database_hashes"]) == {"stats.sqlite3", "analysis/cleaned-20261022/analysis.sqlite3"}
    registry_before = (live / "archive_registry.json").read_bytes()
    assert promote(stage, audit, live, key="expanded-20261023")["idempotent"]
    assert (live / "archive_registry.json").read_bytes() == registry_before
    assert not (live / "archive_registry.lock").exists()

    next_root, next_zip = make_package(tmp_path, "later", 12)
    next_stage = tmp_path / "next-stage"
    stage_analysis_package(next_root, next_zip, next_stage, label="Later collection")
    promote(next_stage, audit, live, key="later-20261024")
    prior_registry = (live / "archive_registry.json").read_bytes()
    replay = promote(stage, audit, live, key="expanded-20261023")
    assert replay["idempotent"] and not replay["active"]
    assert (live / "archive_registry.json").read_bytes() == prior_registry
    assert load_registered_analysis(live).registered_key == "later-20261024"


def test_different_data_same_key_refused_without_registry_or_store_changes(versions, tmp_path):
    live, stage, audit, _, _ = versions
    promote(stage, audit, live, key="expanded")
    root, archive = make_package(tmp_path, "different", 10)
    changed = tmp_path / "different-stage"
    stage_analysis_package(root, archive, changed)
    before = {p: p.read_bytes() for p in live.rglob("*") if p.is_file()}
    with pytest.raises(StorageError, match="already identifies different"):
        promote(changed, audit, live, key="expanded")
    assert all(p.read_bytes() == contents for p, contents in before.items())
    with pytest.raises(StorageError, match="keys must"):
        promote(stage, audit, live, key="../escape")


def test_every_version_survives_backup_and_relocation(versions, tmp_path):
    live, stage, audit, old_zip, new_zip = versions
    promote(stage, audit, live, key="expanded")
    bundle = backup_library(live, tmp_path / "backup")
    manifest = verify_bundle(bundle)
    assert manifest["analysis_versions_included"] == 2
    paths = [item["path"] for item in manifest["files"]]
    assert len(paths) == len(set(paths))
    for name in ("cleaned-20261022", "expanded"):
        relative = f"analysis/{name}/analysis.sqlite3"
        assert paths.count(relative) == 1
        assert (bundle / relative).read_bytes() == (live / relative).read_bytes()
    assert (bundle / "archive_registry.json").read_bytes() == (live / "archive_registry.json").read_bytes()
    assert load_registered_analysis(bundle, "cleaned-20261022").original_zip() == old_zip.read_bytes()
    assert load_registered_analysis(bundle).original_zip() == new_zip.read_bytes()
    assert load_registered_analysis(bundle).table("spotify/cleaned/artist_daily.csv").streams.tolist() == [9]
    with sqlite3.connect((bundle / "stats.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_pointer_conflicts_duplicate_versions_and_unsafe_prior_paths_fail_closed(versions):
    live, stage, audit, _, _ = versions
    promote(stage, audit, live, key="expanded")
    path = live / "archive_registry.json"
    original = json.loads(path.read_text())
    modified = json.loads(json.dumps(original))
    modified["analysis_package"]["label"] = "Incorrect pointer"
    path.write_text(json.dumps(modified))
    with pytest.raises(StorageError, match="conflicts"):
        load_registered_analysis(live)
    modified = json.loads(json.dumps(original))
    modified["analysis_versions"].append(modified["analysis_versions"][0])
    path.write_text(json.dumps(modified))
    with pytest.raises(StorageError, match="must be unique"):
        list_registered_analyses(live)
    modified = json.loads(json.dumps(original))
    modified["analysis_versions"][0]["database"] = "../private.sqlite3"
    path.write_text(json.dumps(modified))
    with pytest.raises(StorageError, match="Unsafe"):
        load_registered_analysis(live)


def test_failed_registry_replace_never_switches_active_version(versions, monkeypatch):
    live, stage, audit, _, _ = versions
    registry = live / "archive_registry.json"
    before = registry.read_bytes()
    old_replace = Path.replace

    def fail_registry_replace(self, target):
        if self.name == "archive_registry.json.new":
            raise OSError("simulated registry write failure")
        return old_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_registry_replace)
    with pytest.raises(OSError, match="simulated"):
        promote(stage, audit, live, key="expanded")
    assert registry.read_bytes() == before
    assert load_registered_analysis(live).registered_key == "cleaned-20261022"
    assert (live / "analysis/expanded/analysis.sqlite3").is_file()
    assert not (live / "archive_registry.lock").exists()


def test_staging_custom_metadata_preserves_integrity_fields_and_source_bytes(versions, tmp_path):
    _, stage, _, _, new_zip = versions
    repo = AnalysisRepository(stage / "analysis.sqlite3")
    assert repo.metadata["label"] == "Expanded Spotify collection"
    assert repo.metadata["activity_endpoint"] == "2026-10-21"
    assert repo.metadata["version_lineage"][0]["key"] == "cleaned-20261022"
    assert repo.original_zip() == new_zip.read_bytes()
    root = tmp_path / "combined"
    with pytest.raises(StorageError, match="integrity fields"):
        stage_analysis_package(root, new_zip, tmp_path / "unsafe", metadata={"baseline_status": "verified"})
    with pytest.raises(StorageError, match="different metadata"):
        stage_analysis_package(root, new_zip, stage, label="Relabeled old package")
    assert repo.metadata["label"] == "Expanded Spotify collection"
