import os
import shutil
import hashlib
import json
import pytest
from stats_app.backup import backup_library, verify_bundle
from stats_app.native_paths import native_path
from stats_app.storage import SQLiteRepository, StorageError
from stats_app.tiktok_repository import TikTokRepository, import_tiktok_collection, load_registered_tiktok
from stats_app.linktree_repository import LinktreeRepository, import_linktree_collection, load_registered_linktree
from tiktok_studio_fixtures import studio_package
from linktree_fixtures import synthetic_package

@pytest.mark.skipif(os.name!='nt',reason='Windows native long-path regression')
@pytest.mark.parametrize('factory,repository',[(studio_package,TikTokRepository),(synthetic_package,LinktreeRepository)])
def test_deep_collection_evidence_remains_readable(tmp_path,factory,repository):
    source=factory(tmp_path)
    logical=tmp_path/('a'*65)/('b'*65)/('c'*65)/'package'
    assert len(str(logical))>260
    shutil.copytree(source,native_path(logical))
    repo=repository(logical)
    assert repo.package_dir==logical.absolute()
    name=repo.sources().path.iloc[0]
    assert repo.original_bytes(name)==native_path(source/name).read_bytes()

def test_native_path_is_idempotent(tmp_path):
    assert native_path(native_path(tmp_path))==native_path(tmp_path)


COLLECTIONS = [
    (studio_package, TikTokRepository, import_tiktok_collection, load_registered_tiktok, "tiktok_collections.json"),
    (synthetic_package, LinktreeRepository, import_linktree_collection, load_registered_linktree, "linktree_collections.json"),
]


def deep_asset_package(tmp_path, factory, registry_name):
    source = factory(tmp_path)
    name = "raw/" + "/".join(letter * 70 for letter in "abc") + "/original.txt"
    raw = b"Synthetic original evidence\r\n"
    physical = native_path(source / name)
    physical.parent.mkdir(parents=True)
    physical.write_bytes(raw)
    entry = {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if registry_name == "tiktok_collections.json":
        manifest_path = source / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest["assets"].append(entry)
    else:
        manifest_path = source / "collection_manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        inventory_path = source / "FILES_SHA256.json"
        inventory = json.loads(inventory_path.read_bytes())
        inventory["files"].append({**entry, "kind": "synthetic_fixture"})
        inventory_raw = json.dumps(inventory).encode("utf-8")
        inventory_path.write_bytes(inventory_raw)
        manifest.update(file_inventory=inventory["files"],
                        checksums_file_sha256=hashlib.sha256(inventory_raw).hexdigest())
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert len(str(source / name)) > 260
    return source, name, raw


@pytest.mark.skipif(os.name != "nt", reason="Windows native long-path regression")
@pytest.mark.parametrize("factory,repository,importer,loader,registry_name", COLLECTIONS)
def test_deep_collection_asset_import_and_replay(tmp_path, factory, repository, importer, loader, registry_name):
    source, name, raw = deep_asset_package(tmp_path, factory, registry_name)
    assert repository(source).original_bytes(name) == raw
    library = tmp_path / "library"
    result = importer(source, library)
    assert not result["idempotent"]
    retained = loader(library, result["key"])
    assert retained.original_bytes(name) == raw
    assert retained.package_dir == library / "collections" / result["key"] / "package"
    registry_before = (library / registry_name).read_bytes()
    assert "\\\\?\\" not in registry_before.decode("utf-8")
    assert importer(source, library)["idempotent"]
    assert (library / registry_name).read_bytes() == registry_before


@pytest.mark.skipif(os.name != "nt", reason="Windows native long-path regression")
@pytest.mark.parametrize("factory,repository,importer,loader,registry_name", COLLECTIONS)
def test_deep_registered_collection_is_included_in_verified_backup(tmp_path, factory, repository, importer, loader, registry_name):
    # Register the already retained package independently of the importer so a
    # backup regression cannot be hidden by a failure earlier in the copy path.
    source, name, raw = deep_asset_package(tmp_path, factory, registry_name)
    incoming = repository(source)
    library = tmp_path / "library"
    SQLiteRepository(library / "stats.sqlite3")
    key = incoming.metadata["collection_key"]
    relative = f"collections/{key}/package"
    shutil.copytree(native_path(source), native_path(library / relative))
    record = {"key": key, "evidence_root": f"collections/{key}", "package_dir": relative,
              "manifest_sha256": incoming.manifest_sha256, "package_sha256": incoming.package_sha256}
    if registry_name == "linktree_collections.json":
        record["inventory_sha256"] = incoming.inventory_sha256
    registry_before = json.dumps({"schema_version": 1, "collections": [record]}).encode("utf-8")
    (library / registry_name).write_bytes(registry_before)
    assert loader(library, key).original_bytes(name) == raw

    bundle = backup_library(library, tmp_path / "bundle")
    manifest = verify_bundle(bundle)
    entry = next(item for item in manifest["files"] if item["path"] == relative + "/" + name)
    assert entry["bytes"] == len(raw)
    assert entry["sha256"] == hashlib.sha256(raw).hexdigest()
    assert all("\\" not in item["path"] for item in manifest["files"])
    assert loader(bundle, key).original_bytes(name) == raw
    assert (bundle / registry_name).read_bytes() == registry_before
    assert (library / registry_name).read_bytes() == registry_before

    native_path(bundle / relative / name).write_bytes(b"changed")
    with pytest.raises(StorageError, match="verification"):
        verify_bundle(bundle)
