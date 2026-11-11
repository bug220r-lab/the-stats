"""Promotion preserves separately registered Shopify stores and native evidence."""
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

import scripts.promote_analysis as promotion
from stats_app.analysis_repository import load_registered_analysis, stage_analysis_package
from stats_app.shopify_repository import REGISTRY_FILENAME, _lock, import_shopify_collection
from stats_app.storage import SQLiteRepository, StorageError
from stats_app.youtube_repository import COLLECTION_KEY, ZIP_FILENAME


SHOPIFY_DB = "collections/shopify-20261025/shopify.sqlite3"
YOUTUBE_DB = f"collections/{COLLECTION_KEY}/youtube.sqlite3"


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def _stage(parent, name, streams, output):
    root = parent / name
    raw = f"date,streams\n2026-10-24,{streams}\n".encode()
    assets = {
        "raw/source.csv": raw,
        "spotify/cleaned/artist_daily.csv": raw,
        "audit/final_validation.json": b'{"checks":{"raw_source_files_unchanged":true}}',
        "raw_sha256.json": json.dumps([{"path": "raw/source.csv", "bytes": len(raw),
                                         "sha256": hashlib.sha256(raw).hexdigest()}]).encode(),
    }
    archive = parent / (name + ".zip")
    with zipfile.ZipFile(archive, "x") as zipped:
        for relative, contents in assets.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
            zipped.writestr(root.name + "/" + relative, contents)
    stage_analysis_package(root, archive, output, label="Synthetic " + name,
                           metadata={"activity_endpoint": "2026-10-24", "retrieval_vintage": "2026-10-25"})


@pytest.fixture
def library(tmp_path):
    live = tmp_path / "isolated-library"
    SQLiteRepository(live / "stats.sqlite3")
    _stage(tmp_path, "original", 7, live / "analysis/original")
    entry = {"key": "original", "database": "analysis/original/analysis.sqlite3",
             "evidence_root": "analysis/original", "label": "Synthetic original"}
    (live / "archive_registry.json").write_text(json.dumps({"archives": [], "analysis_versions": [entry],
                                                           "analysis_package": entry}), encoding="utf-8")
    stage = tmp_path / "stage"
    _stage(tmp_path, "candidate", 9, stage)

    source = tmp_path / "shopify-source"
    (source / "raw").mkdir(parents=True)
    (source / "normalized").mkdir()
    (source / "raw/orders.json").write_bytes(b'{"orderCount":2,"complete":true}\r\n')
    (source / "normalized/orders.csv").write_bytes(b"order_id,net_sales,currency\r\n001,-2.25,USD\r\n002,0,USD\r\n")
    manifest = {
        "schema_version": 1, "collection_key": "shopify-20261025", "collected_at": "2026-10-25T12:00:00Z",
        "store": {"domain": "band.myshopify.com", "name": "Band shop", "timezone": "America/New_York", "currency": "USD"},
        "privacy": {"customer_pii_included": False},
        "datasets": [{"dataset_id": "orders", "status": "collected", "path": "normalized/orders.csv",
                      "source_paths": ["raw/orders.json"], "primary_key": ["order_id"]}],
    }
    (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    import_shopify_collection(source, live)

    # A distinct YouTube registry proves adding Shopify cannot replace the
    # collection inventory already protected by promotion.
    youtube = live / "collections" / COLLECTION_KEY
    SQLiteRepository(youtube / "youtube.sqlite3")
    with zipfile.ZipFile(youtube / ZIP_FILENAME, "x") as zipped:
        zipped.writestr("fixture.txt", "Synthetic YouTube source")
    registration = {"key": COLLECTION_KEY, "database": YOUTUBE_DB,
                    "evidence_root": f"collections/{COLLECTION_KEY}", "zip_filename": ZIP_FILENAME,
                    "database_sha256": _digest(youtube / "youtube.sqlite3"),
                    "zip_sha256": _digest(youtube / ZIP_FILENAME)}
    (live / "youtube_collections.json").write_text(json.dumps({"schema_version": 1, "collections": [registration]}), encoding="utf-8")
    (live / "archive_registry.json.new").write_bytes(b"Preserved earlier failed-operation diagnostic\n")
    return live, stage


def _acceptance(live, stage, path, key="expanded"):
    # Independent synthetic inventory names only the four fixture databases.
    # It deliberately does not trust the production discovery under test.
    receipt = {
        "passed": True, "audited_at_utc": "2026-10-25T06:00:00+00:00",
        "candidate_database_sha256": _digest(stage / "analysis.sqlite3"),
        "all_prior_database_hashes": {name: _digest(live / name) for name in (
            "stats.sqlite3", "analysis/original/analysis.sqlite3", YOUTUBE_DB, SHOPIFY_DB)},
        "audit_scope": "independent_semantic_evidence_and_storage_acceptance", "analysis_version": key,
        "semantic_checks": {"synthetic_sources_reviewed": True},
        "storage_checks": {"all_candidate_table_rows_match_csv": True, "all_zip_assets_match_database": True},
        "registry_unchanged_before_activation": True,
        "supporting_receipts": {"semantic_acceptance_audit.json": "1" * 64, "independent_storage_audit.json": "2" * 64},
    }
    path.write_text(json.dumps(receipt), encoding="utf-8")
    return path


def _assert_clean(live):
    assert not (live / "archive_registry.lock").exists()
    assert not (live / ".youtube_import.lock").exists()
    assert not (live / ".shopify_import.lock").exists()
    assert {p.name for p in live.glob("archive_registry.json*.new")} == {"archive_registry.json.new"}
    assert (live / "archive_registry.json.new").read_bytes() == b"Preserved earlier failed-operation diagnostic\n"


def test_complete_inventory_preserves_both_collection_families_and_replay_is_read_only(library, tmp_path, monkeypatch):
    live, stage = library
    audit = _acceptance(live, stage, tmp_path / "audit.json")
    collections_before = _files(live / "collections")
    registries_before = {name: (live / name).read_bytes() for name in (REGISTRY_FILENAME, "youtube_collections.json")}
    result = promotion.promote(stage, audit, live, key="expanded")
    assert result["active"] and not result["idempotent"]
    assert load_registered_analysis(live).registered_key == "expanded"
    receipt = json.loads((live / "analysis/expanded/activation_receipt.json").read_text())
    assert receipt["earlier_database_hashes"] == json.loads(audit.read_text())["all_prior_database_hashes"]
    assert receipt["shopify_collections_verified"] == receipt["youtube_collections_verified"] == 1
    assert receipt["shopify_registry_sha256"] == hashlib.sha256(registries_before[REGISTRY_FILENAME]).hexdigest()
    assert _files(live / "collections") == collections_before
    assert all((live / name).read_bytes() == raw for name, raw in registries_before.items())
    _assert_clean(live)

    # Existing import locks are not touched by a replay, which never reactivates.
    existing_locks = (live / ".shopify_import.lock", live / ".youtube_import.lock")
    for lock in existing_locks:
        lock.write_bytes(b"another importer owns this lock")
    before = _files(live)
    original_open = Path.open

    def read_only_open(path, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in "wax+"), "Replay attempted a write"
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", read_only_open)
    assert promotion.promote(stage, audit, live, key="expanded")["idempotent"]
    assert _files(live) == before


@pytest.mark.parametrize("omitted", [SHOPIFY_DB, YOUTUBE_DB])
def test_acceptance_cannot_omit_any_registered_collection(library, tmp_path, omitted):
    live, stage = library
    audit = _acceptance(live, stage, tmp_path / "audit.json")
    receipt = json.loads(audit.read_text())
    del receipt["all_prior_database_hashes"][omitted]
    audit.write_text(json.dumps(receipt))
    before = _files(live)
    with pytest.raises(StorageError, match="prior database inventory"):
        promotion.promote(stage, audit, live, key="expanded")
    assert _files(live) == before
    assert not (live / "analysis/expanded").exists()
    _assert_clean(live)


@pytest.mark.parametrize("altered", ["registered-database-hash", "retained-raw", "retained-csv"])
def test_existing_shopify_integrity_failure_refused_before_copy(library, tmp_path, altered):
    live, stage = library
    audit = _acceptance(live, stage, tmp_path / "audit.json")
    if altered == "registered-database-hash":
        path = live / REGISTRY_FILENAME
        registry = json.loads(path.read_text())
        registry["collections"][0]["database_sha256"] = "0" * 64
        path.write_text(json.dumps(registry))
    else:
        name = "raw/orders.json" if altered == "retained-raw" else "normalized/orders.csv"
        (live / "collections/shopify-20261025/package" / name).write_bytes(b"altered retained source")
    before = _files(live)
    with pytest.raises(StorageError, match="Shopify.*(hash differs|evidence is missing or changed)"):
        promotion.promote(stage, audit, live, key="expanded")
    assert _files(live) == before
    assert not (live / "analysis/expanded").exists()
    _assert_clean(live)


@pytest.mark.parametrize("change", ["registry", "raw", "database"])
@pytest.mark.parametrize("moment", ["after-acceptance", "during-copy", "before-registry-replace", "during-replay"])
def test_concurrent_shopify_changes_cannot_switch_analysis(library, tmp_path, monkeypatch, change, moment):
    live, stage = library
    audit = _acceptance(live, stage, tmp_path / "audit.json")
    if moment == "during-replay":
        promotion.promote(stage, audit, live, key="expanded")
    registry = live / "archive_registry.json"
    before_registry = registry.read_bytes()
    before_original = (live / "analysis/original/analysis.sqlite3").read_bytes()
    source = live / (REGISTRY_FILENAME if change == "registry" else
                     "collections/shopify-20261025/package/raw/orders.json" if change == "raw" else SHOPIFY_DB)

    def mutate():
        source.write_bytes(source.read_bytes() + b"\n")

    if moment == "after-acceptance":
        original = promotion._acceptance

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            mutate()
            return result

        monkeypatch.setattr(promotion, "_acceptance", changed)
    elif moment == "during-copy":
        original = promotion.shutil.copytree

        def changed(source_path, target, *args, **kwargs):
            result = original(source_path, target, *args, **kwargs)
            if Path(source_path) == stage:
                mutate()
            return result

        monkeypatch.setattr(promotion.shutil, "copytree", changed)
    else:
        original = promotion._verify_copy
        calls = 0

        def changed(*args, **kwargs):
            nonlocal calls
            result = original(*args, **kwargs)
            calls += 1
            if calls == (1 if moment == "during-replay" else 2):
                mutate()
            return result

        monkeypatch.setattr(promotion, "_verify_copy", changed)
    with pytest.raises(StorageError, match="Shopify|database inventory changed"):
        promotion.promote(stage, audit, live, key="expanded")
    assert registry.read_bytes() == before_registry
    assert (live / "analysis/original/analysis.sqlite3").read_bytes() == before_original
    assert load_registered_analysis(live).registered_key == ("expanded" if moment == "during-replay" else "original")
    if moment == "after-acceptance":
        assert not (live / "analysis/expanded").exists()
    _assert_clean(live)


def test_concurrent_registry_refusal_preserves_copy_and_diagnostics_then_fresh_key_retry_succeeds(library, tmp_path, monkeypatch):
    live, stage = library
    audit = _acceptance(live, stage, tmp_path / "rejected-audit.json", key="rejected")
    copytree = promotion.shutil.copytree

    def mutate_registry_after_copy(source, target, *args, **kwargs):
        result = copytree(source, target, *args, **kwargs)
        if Path(source) == stage:
            registry = live / REGISTRY_FILENAME
            registry.write_bytes(registry.read_bytes() + b"\n")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(promotion.shutil, "copytree", mutate_registry_after_copy)
        with pytest.raises(StorageError, match="Shopify collection registry changed"):
            promotion.promote(stage, audit, live, key="rejected")
    rejected = _files(live / "analysis/rejected")
    assert rejected and load_registered_analysis(live).registered_key == "original"
    _assert_clean(live)
    retry = _acceptance(live, stage, tmp_path / "retry-audit.json", key="retry")
    assert promotion.promote(stage, retry, live, key="retry")["active"]
    assert load_registered_analysis(live).registered_key == "retry"
    assert _files(live / "analysis/rejected") == rejected
    _assert_clean(live)


def test_shopify_import_lock_rejects_before_copy_and_preserves_owner_lock(library, tmp_path):
    live, stage = library
    audit = _acceptance(live, stage, tmp_path / "audit.json")
    registry_before = (live / "archive_registry.json").read_bytes()
    with _lock(live):
        lock = live / ".shopify_import.lock"
        before = lock.read_bytes()
        with pytest.raises(StorageError, match="Another Shopify import is active"):
            promotion.promote(stage, audit, live, key="expanded")
        assert lock.read_bytes() == before
        assert (live / "archive_registry.json").read_bytes() == registry_before
        assert not (live / "analysis/expanded").exists()
        assert not (live / "archive_registry.lock").exists()
        assert not (live / ".youtube_import.lock").exists()
    _assert_clean(live)


@pytest.mark.parametrize("suffix", ["-wal", "-journal"])
@pytest.mark.parametrize("replay", [False, True])
def test_pending_shopify_sidecars_refuse_promotion_and_replay_without_source_changes(library, tmp_path, suffix, replay):
    live, stage = library
    audit = _acceptance(live, stage, tmp_path / "audit.json")
    if replay:
        promotion.promote(stage, audit, live, key="expanded")
    Path(str(live / SHOPIFY_DB) + suffix).write_bytes(b"pending synthetic SQLite journal")
    before = _files(live)
    with pytest.raises(StorageError, match="Shopify database has pending SQLite journal"):
        promotion.promote(stage, audit, live, key="expanded")
    assert _files(live) == before
    _assert_clean(live)
