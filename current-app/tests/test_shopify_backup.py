"""Portable Shopify backup relocation and rejection of altered evidence."""
import hashlib
import json

import pandas as pd
import pytest

from stats_app.backup import backup_library, verify_bundle
from stats_app.shopify_repository import import_shopify_collection, load_registered_shopify, REGISTRY_FILENAME
from stats_app.storage import SQLiteRepository, StorageError


def package_with_collection(tmp_path):
    source = tmp_path / "source"
    (source / "raw").mkdir(parents=True)
    (source / "normalized").mkdir()
    (source / "raw/orders.json").write_bytes(b'{"orderCount":2,"complete":true}\r\n')
    (source / "normalized/orders.csv").write_bytes(b"order_id,net_sales,currency\r\n001,-2.25,USD\r\n002,0,USD\r\n")
    (source / "normalized/inventory.csv").write_bytes(b"variant_id,quantity\n")
    manifest = {"schema_version": 1, "collection_key": "shopify-20261025", "collected_at": "2026-10-25T12:00:00Z",
                "store": {"domain": "band.myshopify.com", "name": "Band shop", "timezone": "America/New_York", "currency": "USD"},
                "privacy": {"customer_pii_included": False},
                "datasets": [{"dataset_id": "orders", "status": "collected", "path": "normalized/orders.csv",
                              "source_paths": ["raw/orders.json"], "primary_key": ["order_id"]},
                             {"dataset_id": "inventory", "status": "verified_empty", "path": "normalized/inventory.csv"}]}
    (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return source


def test_shopify_bundle_relocation_keeps_originals_and_other_registrations(tmp_path):
    source = package_with_collection(tmp_path)
    live = tmp_path / "live"
    SQLiteRepository(live / "stats.sqlite3")
    old_registry = b'{"archives":[]}\n'
    (live / "archive_registry.json").write_bytes(old_registry)
    (live / "unregistered-private.txt").write_bytes(b"exclude")
    import_shopify_collection(source, live)
    original = load_registered_shopify(live)
    registry = (live / REGISTRY_FILENAME).read_bytes()
    database_hash = hashlib.sha256(original.db_path.read_bytes()).hexdigest()
    before = {p.relative_to(live).as_posix(): p.read_bytes() for p in live.rglob("*") if p.is_file()}

    bundle = backup_library(live, tmp_path / "bundle")
    receipt = verify_bundle(bundle)
    assert receipt["shopify_collections_included"] == 1
    assert receipt["youtube_collections_included"] == 0
    assert (bundle / "archive_registry.json").read_bytes() == old_registry
    assert (bundle / REGISTRY_FILENAME).read_bytes() == registry
    assert not (bundle / "unregistered-private.txt").exists()
    # The online backup may open SQLite's transient WAL/shared-memory sidecars;
    # every pre-existing persistent file and registered source stays unchanged.
    assert all((live / name).read_bytes() == raw for name, raw in before.items())

    relocated = tmp_path / "restored"
    bundle.rename(relocated)
    restored = load_registered_shopify(relocated)
    assert restored.db_path.is_relative_to(relocated)
    assert hashlib.sha256(restored.db_path.read_bytes()).hexdigest() == database_hash
    for asset in original.sources().path:
        assert restored.source_bytes(asset) == original.source_bytes(asset)
    for path in original.tables:
        pd.testing.assert_frame_equal(original.table(path), restored.table(path))
        pd.testing.assert_frame_equal(original.row_provenance(path), restored.row_provenance(path))
    assert restored.metadata["store"]["currency"] == "USD"
    assert verify_bundle(relocated)["shopify_collections_included"] == 1


def test_shopify_backup_rejects_changed_sources_before_output(tmp_path):
    source = package_with_collection(tmp_path)
    live = tmp_path / "live"
    SQLiteRepository(live / "stats.sqlite3")
    import_shopify_collection(source, live)
    retained = live / "collections/shopify-20261025/package/raw/orders.json"
    retained.write_bytes(b"altered evidence")
    with pytest.raises(StorageError, match="evidence is missing or changed"):
        backup_library(live, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_shopify_backup_rejects_escaping_registration(tmp_path):
    live = tmp_path / "live"
    SQLiteRepository(live / "stats.sqlite3")
    (live / REGISTRY_FILENAME).write_text(json.dumps({"schema_version": 1, "collections": [
        {"key": "shopify-20261025", "database": "../outside.sqlite3", "evidence_root": ".."}]}), encoding="utf-8")
    with pytest.raises(StorageError, match="registration"):
        backup_library(live, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()
