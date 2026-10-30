"""Portable Studio collections retain exact files alongside the existing library."""
import json

import pandas as pd
import pytest

from tiktok_studio_fixtures import studio_package
from stats_app.backup import backup_library, verify_bundle
from stats_app.storage import SQLiteRepository, StorageError
from stats_app.tiktok_repository import import_tiktok_collection, load_registered_tiktok, REGISTRY_FILENAME


def test_tiktok_full_backup_relocates_originals_and_provenance(tmp_path):
    live = tmp_path / "live"
    SQLiteRepository(live / "stats.sqlite3")
    (live / "archive_registry.json").write_bytes(b'{"archives":[]}\n')
    (live / "unregistered-private.txt").write_bytes(b"excluded")
    import_tiktok_collection(studio_package(tmp_path), live)
    original = load_registered_tiktok(live)
    registry = (live / REGISTRY_FILENAME).read_bytes()
    before = {p.relative_to(live): p.read_bytes() for p in live.rglob("*") if p.is_file()}
    bundle = backup_library(live, tmp_path / "bundle")
    assert verify_bundle(bundle)["tiktok_collections_included"] == 1
    assert (bundle / REGISTRY_FILENAME).read_bytes() == registry
    assert not (bundle / "unregistered-private.txt").exists()
    assert all((live / name).read_bytes() == raw for name, raw in before.items())
    bundle.rename(tmp_path / "relocated")
    restored = load_registered_tiktok(tmp_path / "relocated")
    assert restored.package_sha256 == original.package_sha256
    for path in original.sources().path:
        assert restored.source_bytes(path) == original.source_bytes(path)
    for dataset in original.tables:
        pd.testing.assert_frame_equal(original.table(dataset), restored.table(dataset))
        pd.testing.assert_frame_equal(original.row_provenance(dataset), restored.row_provenance(dataset))
    assert verify_bundle(tmp_path / "relocated")["tiktok_collections_included"] == 1


@pytest.mark.parametrize("kind", ["changed", "extra", "escape"])
def test_tiktok_backup_rejects_damage_before_creating_bundle(tmp_path, kind):
    live = tmp_path / "live"
    SQLiteRepository(live / "stats.sqlite3")
    import_tiktok_collection(studio_package(tmp_path), live)
    package = live / "collections/tiktok-20261027-studio/package"
    if kind == "changed":
        (package / "raw/native.txt").write_bytes(b"changed")
    elif kind == "extra":
        (package.parent / "unexpected.txt").write_bytes(b"extra")
    else:
        registry = json.loads((live / REGISTRY_FILENAME).read_text())
        registry["collections"][0]["package_dir"] = "../outside"
        (live / REGISTRY_FILENAME).write_text(json.dumps(registry))
    with pytest.raises(StorageError):
        backup_library(live, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()
