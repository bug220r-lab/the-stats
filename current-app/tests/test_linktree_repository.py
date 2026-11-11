"""Exact-byte file collection, immutable replay and path-safety regressions."""
import csv
import io
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from linktree_fixtures import synthetic_package, reseal, write_csv
from stats_app.linktree_repository import (LinktreeRepository, REGISTRY_FILENAME, _safe_path,
                                         import_linktree_collection, list_registered_linktree, load_registered_linktree)
from stats_app.storage import StorageError


def test_import_replay_preserves_independent_registries_and_source_bytes(tmp_path):
    source = synthetic_package(tmp_path)
    source_before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    live = tmp_path / "live"
    live.mkdir()
    preserved = {"archive_registry.json": b'{"archives":[],"active_analysis":"unchanged"}', "stats.sqlite3": b"existing-test-bytes",
                 "youtube_collections.json": b"existing-youtube", "shopify_collections.json": b"existing-shopify"}
    for name, raw in preserved.items():
        (live / name).write_bytes(raw)
    first = import_linktree_collection(source, live)
    assert not first["idempotent"] and first["integrity"] == "ok"
    repo = load_registered_linktree(live)
    assert repo.metadata["account"] == "fixture-account"
    assert repo.metadata["reporting_timezone"] == "unknown"
    assert repo.metadata["coverage"]["current_day_incomplete"] == "2026-10-25"
    assert repo.metadata["baseline_status"].endswith("not_original_baseline")
    before = {p.relative_to(live): p.read_bytes() for p in live.rglob("*") if p.is_file()}
    second = import_linktree_collection(source, live)
    assert second["idempotent"] and second["package_sha256"] == first["package_sha256"]
    assert before == {p.relative_to(live): p.read_bytes() for p in live.rglob("*") if p.is_file()}
    assert source_before == {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    assert all((live / name).read_bytes() == raw for name, raw in preserved.items())
    assert all(repo.original_bytes(path.as_posix()) == raw for path, raw in source_before.items())
    rows = repo.table("activity_daily")
    assert rows.value.tolist() == ["0", "13"] and rows.link_id.tolist() == ["00001", "00001"]
    assert repo.table("music_service_metrics").value.tolist() == [""]
    assert repo.table("period_summaries").iloc[2].value == "162.5"
    provenance = repo.row_provenance("activity_daily")
    assert provenance.csv_record.tolist() == [2, 3]
    assert provenance.stable_row_key.is_unique
    assert provenance.source_reference.eq("captures/native.txt").all()
    assert len(list_registered_linktree(live)) == 1


def test_absent_and_unknown_collection_are_scoped(tmp_path):
    assert list_registered_linktree(tmp_path) == []
    assert load_registered_linktree(tmp_path) is None
    import_linktree_collection(synthetic_package(tmp_path), tmp_path / "live")
    with pytest.raises(StorageError, match="Unknown Linktree collection"):
        load_registered_linktree(tmp_path / "live", "linktree-20261024")


@pytest.mark.parametrize("path", ["../outside", "/outside", "C:/outside", "C:outside", "x\\y", "x//y", "x/./y", "CON.txt", "x/aux", "x.", "x ", "a:stream", "a\nfile", ""])
def test_unsafe_paths_rejected(path):
    with pytest.raises(StorageError):
        _safe_path(path)


@pytest.mark.parametrize("kind", ["modified", "missing", "extra", "inventory", "manifest"])
def test_registered_hash_or_namespace_corruption_is_rejected(tmp_path, kind):
    import_linktree_collection(synthetic_package(tmp_path), tmp_path / "live")
    package = tmp_path / "live/collections/linktree-20261025/package"
    if kind == "modified":
        (package / "captures/native.txt").write_bytes(b"altered")
    elif kind == "missing":
        (package / "captures/native.txt").unlink()
    elif kind == "extra":
        (package / "unexpected.txt").write_bytes(b"extra")
    elif kind == "inventory":
        (package / "FILES_SHA256.json").write_bytes(b"{}")
    else:
        (package / "collection_manifest.json").write_bytes(b"{}")
    with pytest.raises(StorageError):
        load_registered_linktree(tmp_path / "live")


def test_source_changes_after_repository_load_fail_download(tmp_path):
    source = synthetic_package(tmp_path)
    repo = LinktreeRepository(source)
    (source / "captures/native.txt").write_bytes(b"altered")
    with pytest.raises(StorageError, match="verification"):
        repo.original_bytes("captures/native.txt")
    with pytest.raises(StorageError, match="Unknown"):
        repo.original_bytes("not-in-inventory.txt")


def test_changed_same_key_replay_cannot_replace_collection(tmp_path):
    source = synthetic_package(tmp_path)
    import_linktree_collection(source, tmp_path / "live")
    registry = (tmp_path / "live" / REGISTRY_FILENAME).read_bytes()
    (source / "captures/native.txt").write_bytes(b"valid newer bytes; same key")
    reseal(source)
    with pytest.raises(StorageError, match="different source bytes"):
        import_linktree_collection(source, tmp_path / "live")
    assert (tmp_path / "live" / REGISTRY_FILENAME).read_bytes() == registry


@pytest.mark.parametrize("fault", ["duplicate_inventory", "unsafe_inventory", "wrong_rows", "account", "identity", "duplicate_header", "ragged"])
def test_malformed_packages_fail_before_registration(tmp_path, fault):
    source = synthetic_package(tmp_path)
    manifest_path = source / "collection_manifest.json"
    if fault == "account":
        raw = (source / "normalized/activity_daily.csv").read_bytes().replace(b"fixture-account", b"other-account")
        (source / "normalized/activity_daily.csv").write_bytes(raw)
        reseal(source)
    elif fault == "identity":
        (source / "collection_identity.json").write_text('{}', encoding="utf-8")
        reseal(source)
    elif fault in {"duplicate_header", "ragged"}:
        raw = b"account,value,Value\nfixture-account,1,1\n" if fault == "duplicate_header" else b"account,value\nfixture-account,1,extra\n"
        (source / "normalized/activity_daily.csv").write_bytes(raw)
        reseal(source)
    elif fault == "wrong_rows":
        manifest = json.loads(manifest_path.read_text())
        manifest["dataset_tables"][0]["row_count"] = 99
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    else:
        inventory_path = source / "FILES_SHA256.json"
        inventory = json.loads(inventory_path.read_text())
        if fault == "duplicate_inventory":
            inventory["files"].append(inventory["files"][0])
        else:
            inventory["files"][0]["path"] = "../outside"
        raw = json.dumps(inventory).encode()
        inventory_path.write_bytes(raw)
        import hashlib
        manifest = json.loads(manifest_path.read_text())
        manifest.update(file_inventory=inventory["files"], checksums_file_sha256=hashlib.sha256(raw).hexdigest())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(StorageError):
        import_linktree_collection(source, tmp_path / "live")
    assert not (tmp_path / "live" / REGISTRY_FILENAME).exists()


def test_registry_path_escape_and_import_lock_are_rejected(tmp_path):
    source = synthetic_package(tmp_path)
    live = tmp_path / "live"
    live.mkdir()
    (live / ".linktree_import.lock").write_bytes(b"another operation")
    with pytest.raises(StorageError, match="Another"):
        import_linktree_collection(source, live)
    assert (live / ".linktree_import.lock").read_bytes() == b"another operation"
    (live / ".linktree_import.lock").unlink()
    (live / REGISTRY_FILENAME).write_text(json.dumps({"schema_version": 1, "collections": [
        {"key": "linktree-20261025", "package_dir": "../outside", "evidence_root": ".."}]}))
    with pytest.raises(StorageError, match="registration"):
        list_registered_linktree(live)


def test_import_cli_validation_is_default_and_runs_outside_project(tmp_path):
    source = synthetic_package(tmp_path)
    script = Path(__file__).resolve().parents[1] / "scripts/import_linktree_collection.py"
    live = tmp_path / "live"
    run = subprocess.run([sys.executable, str(script), "--package-dir", str(source), "--data-dir", str(live)],
                         cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["mode"] == "validation_only"
    assert not live.exists()


def test_actual_package_tables_retain_all_tokens_and_known_gaps():
    source = Path(__file__).resolve().parents[1] / "data/collection/linktree-20261025"
    if not source.exists():
        pytest.skip("Private Linktree package is absent")
    repo = LinktreeRepository(source)
    assert len(repo.tables) == 19
    for path in repo.tables:
        expected = pd.DataFrame(list(csv.DictReader(io.StringIO(repo.original_bytes(path).decode("utf-8-sig")))), dtype=object)
        pd.testing.assert_frame_equal(repo.table(path), expected)
    services = repo.table("music_service_metrics")
    assert services.value.eq("").all(), "Missing outbound service clicks must remain absent"
    rates = repo.table("period_summaries")
    assert "162.5" in rates.value.tolist() and "105.3" in rates.value.tolist()
    daily_sources = repo.table("traffic_sources_daily")
    assert daily_sources.value.eq("").sum() == 10
    assert repo.metadata["identity"]["reporting_timezone"] is None
    assert repo.metadata["coverage"]["current_day_incomplete"] == "2026-10-25"
