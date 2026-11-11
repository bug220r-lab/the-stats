"""Shopify source preservation, isolation and malformed-package boundaries."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from stats_app.shopify_repository import (
    REGISTRY_FILENAME, import_shopify_collection, list_registered_shopify,
    load_registered_shopify,
)
from stats_app.storage import StorageError


def make_package(tmp_path, *, key="shopify-20261025", rows="order_id,date,net_sales,discounts\n001,2026-10-24,-1.25,\n002,2026-10-24,0,0\n"):
    package = tmp_path / (key + "-source")
    (package / "raw").mkdir(parents=True)
    (package / "normalized").mkdir()
    (package / "raw/orders.json").write_bytes(b'{"orders":[{"id":"001"},{"id":"002"}],"hasNextPage":false}\n')
    (package / "normalized/orders.csv").write_text(rows, encoding="utf-8", newline="")
    (package / "normalized/customers.csv").write_bytes(b"country,customer_count\n")
    manifest = {
        "schema_version": 1, "collection_key": key,
        "collected_at": "2026-10-25T05:10:00+00:00",
        "store": {"name": "Band shop", "domain": "band.myshopify.com", "timezone": "America/New_York", "currency": "USD"},
        "privacy": {"customer_pii_included": False},
        "datasets": [
            {"dataset_id": "orders", "status": "collected", "path": "normalized/orders.csv",
             "source_paths": ["raw/orders.json"], "primary_key": ["order_id"], "reporting_start": "2026-10-24", "reporting_end": "2026-10-24",
             "definition": "Native daily order records in store calendar dates."},
            {"dataset_id": "customers", "status": "verified_empty", "path": "normalized/customers.csv"},
            {"dataset_id": "traffic", "status": "blocked", "reason": "Report permission unavailable."},
        ],
    }
    write_manifest(package, manifest)
    return package, manifest


def write_manifest(package, manifest):
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_exact_bytes_negative_currency_blanks_empty_and_isolation(tmp_path):
    package, _ = make_package(tmp_path)
    library = tmp_path / "library"
    library.mkdir()
    existing = {"stats.sqlite3": b"unrelated live upload bytes", "archive_registry.json": b"original October20 registry",
                "youtube_collections.json": b"unrelated YouTube registry"}
    for name, raw in existing.items():
        (library / name).write_bytes(raw)
    original = {path.relative_to(package).as_posix(): path.read_bytes() for path in package.rglob("*") if path.is_file()}
    report = import_shopify_collection(package, library)
    assert report["idempotent"] is False and report["integrity"] == "ok"
    repo = load_registered_shopify(library)
    assert repo.metadata["store"]["name"] == "Band shop"
    assert repo.metadata["baseline_status"] == "newly_collected_separate_source"
    assert repo.table("orders").to_dict("records") == [
        {"order_id": "001", "date": "2026-10-24", "net_sales": "-1.25", "discounts": ""},
        {"order_id": "002", "date": "2026-10-24", "net_sales": "0", "discounts": "0"},
    ]
    assert repo.table("customers").empty
    assert repo.table("customers").columns.tolist() == ["country", "customer_count"]
    assert len(repo.datasets) == 3
    with pytest.raises(StorageError, match="no collected table"):
        repo.table("traffic")
    for name, raw in original.items():
        assert repo.source_bytes(name) == raw == (package / name).read_bytes()
        assert (library / "collections/shopify-20261025/package" / name).read_bytes() == raw
    for name, raw in existing.items():
        assert (library / name).read_bytes() == raw
    assert len(repo.sources()) == len(original)
    provenance = repo.row_provenance("orders")
    assert provenance.csv_record.tolist() == [2, 3]
    assert provenance.stable_row_key.nunique() == 2
    assert json.loads(provenance.identity_json.iloc[0]) == {"order_id": "001"}
    with repo._connect() as db, pytest.raises(sqlite3.OperationalError, match="readonly"):
        db.execute("DELETE FROM metadata")


def test_replay_is_read_only_and_changed_bytes_conflict(tmp_path):
    package, _ = make_package(tmp_path)
    library = tmp_path / "library"
    import_shopify_collection(package, library)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in library.rglob("*") if p.is_file()}
    assert import_shopify_collection(package, library)["idempotent"] is True
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in library.rglob("*") if p.is_file()}
    (package / "raw/orders.json").write_bytes(b"changed source")
    with pytest.raises(StorageError, match="different source bytes"):
        import_shopify_collection(package, library)
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in library.rglob("*") if p.is_file()}


@pytest.mark.parametrize("mutation,match", [
    (lambda m: m.update(collected_at="2026-10-25T12:00:00"), "UTC offset"),
    (lambda m: m["datasets"][0].update(status="mystery"), "status"),
    (lambda m: m["datasets"][0].update(path="../orders.csv"), "Unsafe"),
    (lambda m: m["datasets"][0].update(source_paths=["raw/missing.json"]), "missing"),
    (lambda m: m["datasets"][0].update(status="verified_empty"), "contains rows"),
    (lambda m: m["datasets"][2].update(reason=""), "explicit reason"),
    (lambda m: m["privacy"].update(customer_pii_included=True), "personal information"),
    (lambda m: m.pop("privacy"), "Explicitly confirm"),
    (lambda m: m["datasets"].append(dict(m["datasets"][0])), "unique"),
    (lambda m: m["datasets"][0].update(reporting_start="2026-10-26"), "reversed"),
    (lambda m: m["datasets"][0].update(row_count=100), "row_count differs"),
])
def test_rejected_manifest_never_creates_library(tmp_path, mutation, match):
    package, manifest = make_package(tmp_path)
    mutation(manifest)
    write_manifest(package, manifest)
    library = tmp_path / "library"
    with pytest.raises(StorageError, match=match):
        import_shopify_collection(package, library)
    assert not library.exists()


@pytest.mark.parametrize("rows,match", [
    ("id, ID\n1,2\n", "Duplicate"),
    ("id,amount\n1\n", "field count"),
    ("id,amount\n", "verified_empty"),
])
def test_malformed_csv_rejected_before_mutation(tmp_path, rows, match):
    package, _ = make_package(tmp_path, rows=rows)
    with pytest.raises(StorageError, match=match):
        import_shopify_collection(package, tmp_path / "library")
    assert not (tmp_path / "library").exists()


def test_duplicate_native_ids_rejected(tmp_path):
    package, _ = make_package(tmp_path, rows="order_id,net_sales\n001,-1.00\n001,2.00\n")
    with pytest.raises(StorageError, match="duplicated"):
        import_shopify_collection(package, tmp_path / "library")


def test_blank_trailing_csv_lines_keep_source_bytes_without_inventing_rows(tmp_path):
    package, _ = make_package(tmp_path, rows="order_id,net_sales\n001,-1.00\n\n")
    library = tmp_path / "library"
    import_shopify_collection(package, library)
    repo = load_registered_shopify(library)
    assert len(repo.table("orders")) == 1
    assert repo.source_bytes("normalized/orders.csv").endswith(b"\n\n")


def test_missing_retained_evidence_detected(tmp_path):
    package, _ = make_package(tmp_path)
    library = tmp_path / "library"
    import_shopify_collection(package, library)
    (library / "collections/shopify-20261025/package/raw/orders.json").write_bytes(b"tamper")
    with pytest.raises(StorageError, match="evidence is missing or changed"):
        load_registered_shopify(library)


def test_declared_source_hashes_verified_before_import(tmp_path):
    package, manifest = make_package(tmp_path)
    manifest["assets"] = [{"path": path.relative_to(package).as_posix(), "bytes": path.stat().st_size,
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                          for path in sorted(package.rglob("*")) if path.is_file() and path.name != "manifest.json"]
    write_manifest(package, manifest)
    import_shopify_collection(package, tmp_path / "good")
    (package / "raw/orders.json").write_bytes(b"changed after declared receipt")
    with pytest.raises(StorageError, match="hash/size differs"):
        import_shopify_collection(package, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_registered_database_tamper_detected(tmp_path):
    package, _ = make_package(tmp_path)
    library = tmp_path / "library"
    report = import_shopify_collection(package, library)
    database = Path(report["database"])
    with database.open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(StorageError, match="hash differs"):
        load_registered_shopify(library)


def test_separate_retrievals_select_latest_without_merging(tmp_path):
    first, _ = make_package(tmp_path)
    later, _ = make_package(tmp_path, key="shopify-20261025-followup", rows="order_id,net_sales\n003,2.50\n")
    library = tmp_path / "library"
    import_shopify_collection(first, library)
    import_shopify_collection(later, library)
    assert len(list_registered_shopify(library)) == 2
    assert load_registered_shopify(library).metadata["collection_key"] == "shopify-20261025-followup"
    assert load_registered_shopify(library, "shopify-20261025").table("orders").order_id.tolist() == ["001", "002"]
    assert load_registered_shopify(library).table("orders").order_id.tolist() == ["003"]


def test_missing_or_conflicting_registry_and_destination(tmp_path):
    package, _ = make_package(tmp_path)
    library = tmp_path / "library"
    assert load_registered_shopify(library) is None
    (library / "collections/shopify-20261025").mkdir(parents=True)
    with pytest.raises(StorageError, match="Unregistered"):
        import_shopify_collection(package, library)
    assert not (library / REGISTRY_FILENAME).exists()


def test_reject_library_inside_incoming_package(tmp_path):
    package, _ = make_package(tmp_path)
    with pytest.raises(StorageError, match="outside"):
        import_shopify_collection(package, package / "library")
    assert not (package / "library").exists()


def test_cli_success_receipt_survives_legacy_windows_encoding(tmp_path):
    package, _ = make_package(tmp_path)
    library = tmp_path / "library-\u2122\ufe0f"
    environment = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
    result = subprocess.run([sys.executable, "-m", "stats_app.shopify_repository", "--package-dir", str(package),
                             "--data-dir", str(library)], capture_output=True, env=environment,
                            cwd=Path(__file__).resolve().parents[1], timeout=30)
    assert result.returncode == 0, result.stderr.decode("cp1252")
    receipt = json.loads(result.stdout.decode("ascii"))
    assert receipt["integrity"] == "ok" and str(library) in receipt["database"]
