"""Consequential regressions for audit F03/F04 using isolated libraries only."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

import scripts.promote_analysis as promotion
from stats_app.analysis_repository import load_registered_analysis, stage_analysis_package
from stats_app.archive_repository import ImportedArchiveRepository
from stats_app.retained_store import Store
from stats_app.storage import SQLiteRepository, StorageError


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _package(parent, name, streams):
    root = parent / name
    raw = f"date,streams\n2026-10-24,{streams}\n".encode()
    files = {
        "raw/source.csv": raw,
        "spotify/cleaned/artist_daily.csv": raw,
        "audit/final_validation.json": b'{"checks":{"raw_source_files_unchanged":true}}',
        "raw_sha256.json": json.dumps([{
            "path": "raw/source.csv", "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }]).encode(),
    }
    archive = parent / (name + ".zip")
    with zipfile.ZipFile(archive, "x") as zipped:
        for relative, contents in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
            zipped.writestr(root.name + "/" + relative, contents)
    return root, archive


@pytest.fixture
def promotion_library(tmp_path):
    live = tmp_path / "isolated-library"
    SQLiteRepository(live / "stats.sqlite3")
    original, original_zip = _package(tmp_path, "original", 7)
    old_dir = live / "analysis/original"
    stage_analysis_package(original, original_zip, old_dir, label="Synthetic original",
                           metadata={"activity_endpoint": "2026-10-24", "retrieval_vintage": "2026-10-25"})
    entry = {"key": "original", "database": "analysis/original/analysis.sqlite3",
             "evidence_root": "analysis/original", "label": "Synthetic original"}
    registry = live / "archive_registry.json"
    registry.write_text(json.dumps({"archives": [], "analysis_versions": [entry],
                                    "analysis_package": entry}), encoding="utf-8")
    candidate, candidate_zip = _package(tmp_path, "candidate", 9)
    stage = tmp_path / "stage"
    stage_analysis_package(candidate, candidate_zip, stage, label="Synthetic candidate",
                           metadata={"activity_endpoint": "2026-10-24", "retrieval_vintage": "2026-10-25"})
    # A legacy failed-operation artifact and another attempt's diagnostic must
    # neither block this attempt nor be removed by its cleanup.
    diagnostics = {
        live / "archive_registry.json.new": b"preserved legacy diagnostic\n",
        live / "archive_registry.json.other-attempt.new": b"preserved other attempt\n",
    }
    for path, raw in diagnostics.items():
        path.write_bytes(raw)
    return live, stage, registry, old_dir / "analysis.sqlite3", diagnostics


def _acceptance(live, stage, key, path):
    # Synthetic acceptance for only the explicit registered fixture databases.
    raw = {
        "passed": True, "audited_at_utc": "2026-10-25T06:00:00+00:00",
        "candidate_database_sha256": _digest(stage / "analysis.sqlite3"),
        "all_prior_database_hashes": {
            relative: _digest(live / relative)
            for relative in ("stats.sqlite3", "analysis/original/analysis.sqlite3")
        },
        "audit_scope": "independent_semantic_evidence_and_storage_acceptance",
        "analysis_version": key,
        "semantic_checks": {"synthetic_sources_reviewed": True},
        "storage_checks": {"all_candidate_table_rows_match_csv": True, "all_zip_assets_match_database": True},
        "registry_unchanged_before_activation": True,
        "supporting_receipts": {"semantic_acceptance_audit.json": "1" * 64,
                                "independent_storage_audit.json": "2" * 64},
    }
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _assert_only_retained_diagnostics(live, diagnostics):
    assert set(live.glob("archive_registry.json*.new")) == set(diagnostics)
    assert all(path.read_bytes() == raw for path, raw in diagnostics.items())
    assert not (live / "archive_registry.lock").exists()
    assert not (live / ".youtube_import.lock").exists()


def test_rejected_concurrent_change_cleans_only_owned_pending_and_fresh_key_succeeds(promotion_library, tmp_path, monkeypatch):
    live, stage, registry, original_db, diagnostics = promotion_library
    before_registry, before_original, candidate_hash = registry.read_bytes(), original_db.read_bytes(), _digest(stage / "analysis.sqlite3")
    audit = _acceptance(live, stage, "rejected", tmp_path / "rejected-audit.json")
    verify_copy = promotion._verify_copy
    attempts = 0
    owned_paths = []

    def change_after_pending_write(*args, **kwargs):
        nonlocal attempts
        verify_copy(*args, **kwargs)
        attempts += 1
        if attempts == 2:
            owned_paths.extend(set(live.glob("archive_registry.json.*.new")) - set(diagnostics))
            assert len(owned_paths) == 1
            with closing(sqlite3.connect(live / "stats.sqlite3")) as writer:
                writer.execute("CREATE TABLE concurrent_import(value TEXT)")
                writer.execute("INSERT INTO concurrent_import VALUES('committed')")
                writer.commit()

    with monkeypatch.context() as patch:
        patch.setattr(promotion, "_verify_copy", change_after_pending_write)
        with pytest.raises(StorageError, match="changed"):
            promotion.promote(stage, audit, live, key="rejected")
    assert registry.read_bytes() == before_registry
    assert original_db.read_bytes() == before_original
    assert (live / "analysis/rejected/analysis.sqlite3").is_file()
    assert all(not path.exists() for path in owned_paths)
    _assert_only_retained_diagnostics(live, diagnostics)

    # Retry has a fresh key and acceptance for the changed writable fixture.
    retry = _acceptance(live, stage, "retry", tmp_path / "retry-audit.json")
    result = promotion.promote(stage, retry, live, key="retry")
    assert result["active"] and not result["idempotent"]
    assert load_registered_analysis(live).registered_key == "retry"
    assert original_db.read_bytes() == before_original
    assert _digest(stage / "analysis.sqlite3") == candidate_hash
    _assert_only_retained_diagnostics(live, diagnostics)


def test_registry_replace_failure_preserves_diagnostics_and_allows_new_key(promotion_library, tmp_path, monkeypatch):
    live, stage, registry, original_db, diagnostics = promotion_library
    before_registry, before_original = registry.read_bytes(), original_db.read_bytes()
    audit = _acceptance(live, stage, "replace-failure", tmp_path / "replace-audit.json")
    replace = Path.replace

    def reject_registry_replace(path, target):
        if Path(target) == registry:
            assert path.name.startswith("archive_registry.json.") and path.suffix == ".new"
            assert path not in diagnostics
            raise OSError("synthetic registry replace failure")
        return replace(path, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", reject_registry_replace)
        with pytest.raises(OSError, match="synthetic registry replace failure"):
            promotion.promote(stage, audit, live, key="replace-failure")
    assert registry.read_bytes() == before_registry
    assert original_db.read_bytes() == before_original
    _assert_only_retained_diagnostics(live, diagnostics)
    retry = _acceptance(live, stage, "replace-retry", tmp_path / "replace-retry-audit.json")
    assert promotion.promote(stage, retry, live, key="replace-retry")["active"]
    assert load_registered_analysis(live).registered_key == "replace-retry"
    _assert_only_retained_diagnostics(live, diagnostics)


def _archive(tmp_path, records=1):
    store = Store(tmp_path / "retained/fixture.sqlite3")
    snapshot_id = store.create_snapshot("Synthetic retained archive")
    rows = [{"platform": "spotify", "account_id": "synthetic-account", "entity_type": "artist",
             "entity_id": f"synthetic-{index}", "metric": "streams", "value": 7, "unit": "count",
             "definition": "Synthetic daily streams", "dimensions": {}, "period_start": "2026-10-24",
             "period_end": "2026-10-24", "time_grain": "daily", "measurement_type": "period_count",
             "status": "available", "source_timezone": "UTC", "source_row": index + 2}
            for index in range(records)]
    store.commit_import(snapshot_id, "synthetic.csv", b"Synthetic fixture; no real source data\n", rows)
    store.lock_snapshot(snapshot_id)
    return store, ImportedArchiveRepository(store.path, store.source_dir)


@pytest.mark.parametrize("suffix", ["-wal", "-journal"])
def test_pending_archive_sidecars_refused_by_constructor_and_existing_reader(tmp_path, suffix):
    store, reader = _archive(tmp_path)
    before = store.path.read_bytes()
    sidecar = Path(str(store.path) + suffix)
    raw = b"pending synthetic journal evidence"
    sidecar.write_bytes(raw)
    with pytest.raises(StorageError, match="nonempty WAL or rollback journal"):
        ImportedArchiveRepository(store.path, store.source_dir)
    with pytest.raises(StorageError, match="nonempty WAL or rollback journal"):
        reader.list_snapshots()
    assert store.path.read_bytes() == before and sidecar.read_bytes() == raw


@pytest.mark.parametrize("suffix", ["-wal", "-journal"])
def test_empty_archive_sidecars_allow_byte_preserving_reads(tmp_path, suffix):
    store, _ = _archive(tmp_path)
    before = store.path.read_bytes()
    sidecar = Path(str(store.path) + suffix)
    sidecar.write_bytes(b"")
    reader = ImportedArchiveRepository(store.path, store.source_dir)
    assert reader.observations("Synthetic retained archive").value.tolist() == [7]
    assert store.path.read_bytes() == before and sidecar.read_bytes() == b""


def test_real_uncommitted_cache_spill_is_refused_without_recovering_or_changing_source(tmp_path):
    store, reader = _archive(tmp_path, records=1500)
    before = store.path.read_bytes()
    with closing(sqlite3.connect(store.path)) as writer:
        writer.execute("PRAGMA journal_mode=DELETE")
        writer.execute("PRAGMA cache_size=1")
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE observations SET value=8")
        journal = Path(str(store.path) + "-journal")
        assert journal.stat().st_size > 0
        pending_database, pending_journal = store.path.read_bytes(), journal.read_bytes()
        assert pending_database != before  # Dirty pages really reached the main file.
        with pytest.raises(StorageError, match="nonempty WAL or rollback journal"):
            reader.observations("Synthetic retained archive")
        with pytest.raises(StorageError, match="nonempty WAL or rollback journal"):
            ImportedArchiveRepository(store.path, store.source_dir)
        assert store.path.read_bytes() == pending_database
        assert journal.read_bytes() == pending_journal
        writer.rollback()
    assert store.path.read_bytes() == before
    restored = reader.observations("Synthetic retained archive")
    assert len(restored) == 1500 and restored.value.eq(7).all()


def test_archive_sidecar_appearing_during_connection_open_is_refused(tmp_path, monkeypatch):
    store, reader = _archive(tmp_path)
    before = store.path.read_bytes()
    connect = sqlite3.connect
    journal = Path(str(store.path) + "-journal")

    def connect_then_mark_pending(*args, **kwargs):
        connection = connect(*args, **kwargs)
        journal.write_bytes(b"synthetic sidecar created during connection open")
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect_then_mark_pending)
    with pytest.raises(StorageError, match="nonempty WAL or rollback journal"):
        reader.list_snapshots()
    assert store.path.read_bytes() == before
    # The failed read closed its connection (important on Windows).
    renamed = store.path.with_suffix(".closed.sqlite3")
    store.path.rename(renamed)
    assert renamed.read_bytes() == before
