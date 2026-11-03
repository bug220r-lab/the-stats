"""Portable relocation and refusal of damaged Linktree source packages."""
import json

import pandas as pd
import pytest

from linktree_fixtures import synthetic_package
from stats_app.backup import backup_library, verify_bundle
from stats_app.linktree_repository import import_linktree_collection, load_registered_linktree, REGISTRY_FILENAME
from stats_app.storage import SQLiteRepository, StorageError


def test_linktree_full_backup_relocates_exact_bytes_and_provenance(tmp_path):
    source = synthetic_package(tmp_path)
    live = tmp_path / "live"
    SQLiteRepository(live / "stats.sqlite3")
    (live / "archive_registry.json").write_bytes(b'{"archives":[]}\n')
    (live / "unregistered-private.txt").write_bytes(b"not included")
    import_linktree_collection(source, live)
    original = load_registered_linktree(live)
    registry = (live / REGISTRY_FILENAME).read_bytes()
    before = {p.relative_to(live): p.read_bytes() for p in live.rglob("*") if p.is_file()}
    bundle = backup_library(live, tmp_path / "bundle")
    assert verify_bundle(bundle)["linktree_collections_included"] == 1
    assert (bundle / REGISTRY_FILENAME).read_bytes() == registry
    assert not (bundle / "unregistered-private.txt").exists()
    assert all((live / name).read_bytes() == raw for name, raw in before.items())
    restored_dir = tmp_path / "relocated"
    bundle.rename(restored_dir)
    restored = load_registered_linktree(restored_dir)
    assert restored.package_sha256 == original.package_sha256
    for path in original.sources().path:
        assert restored.original_bytes(path) == original.original_bytes(path)
    for dataset in original.tables:
        pd.testing.assert_frame_equal(original.table(dataset), restored.table(dataset))
        pd.testing.assert_frame_equal(original.row_provenance(dataset), restored.row_provenance(dataset))
    assert verify_bundle(restored_dir)["linktree_collections_included"] == 1


@pytest.mark.parametrize("kind", ["changed", "extra", "escape"])
def test_linktree_backup_refuses_corruption_before_creating_output(tmp_path, kind):
    live = tmp_path / "live"
    SQLiteRepository(live / "stats.sqlite3")
    import_linktree_collection(synthetic_package(tmp_path), live)
    package = live / "collections/linktree-20261025/package"
    if kind == "changed":
        (package / "captures/native.txt").write_bytes(b"changed")
    elif kind == "extra":
        (package.parent / "unexpected.txt").write_bytes(b"unregistered")
    else:
        registry = json.loads((live / REGISTRY_FILENAME).read_text())
        registry["collections"][0]["package_dir"] = "../outside"
        (live / REGISTRY_FILENAME).write_text(json.dumps(registry))
    with pytest.raises(StorageError):
        backup_library(live, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()
