"""Consistent local SQLite backup or portable backup of the registered library."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sqlite3

from stats_app.config import load_settings
from stats_app.storage import StorageError
from stats_app.analysis_repository import analysis_registration_records
from stats_app.native_paths import native_path


def _hash(path):
    digest = hashlib.sha256()
    with native_path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_database(database, output):
    """Include committed WAL contents using SQLite backup without changing source."""
    database, output = Path(database).resolve(), Path(output).expanduser().resolve()
    if not native_path(database).is_file():
        raise StorageError("No configured local database exists. Nothing to back up.")
    if database == output:
        raise StorageError("Backup destination must differ from the live database.")
    native_path(output.parent).mkdir(parents=True, exist_ok=True)
    with native_path(output).open("xb"):
        pass
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source, closing(sqlite3.connect(output)) as destination:
        source.backup(destination)
        if destination.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise StorageError("Backup SQLite verification failed; preserve the incomplete output for inspection.")
    return output


def _not_link(path):
    physical = native_path(path)
    if physical.is_symlink() or (hasattr(physical, "is_junction") and physical.is_junction()):
        raise StorageError("Registered backup inputs must not contain symbolic links or directory junctions.")


def _tree_files(root):
    """Walk physical Windows paths while retaining portable logical identities."""
    physical_root = native_path(root)
    for physical in physical_root.rglob("*"):
        path = root / physical.relative_to(physical_root)
        _not_link(path)
        if physical.is_file():
            yield path


def _optional_bytes(path):
    physical = native_path(path)
    return physical.read_bytes() if physical.exists() else None


def _registered_paths(data_dir, registry, collection_records=()):
    """Validate the portable registry and enumerate only its explicitly named roots."""
    if not isinstance(registry, dict) or not isinstance(registry.get("archives"), list):
        raise StorageError("The archive registry must contain an archives list.")
    keys, databases, roots, files = set(), [], [], set()

    def resolve(raw):
        if not isinstance(raw, str) or not raw or "\\" in raw:
            raise StorageError("Portable archive paths must be nonempty relative paths using forward slashes.")
        rel = Path(raw)
        path = data_dir / rel
        if rel.is_absolute() or PureWindowsPath(raw).drive or ".." in rel.parts or not path.resolve().is_relative_to(data_dir):
            raise StorageError("Archive backup paths must stay inside the registered data directory.")
        for ancestor in [path, *path.parents]:
            _not_link(ancestor)
            if ancestor == data_dir:
                break
        return path.resolve()

    for item in registry["archives"]:
        if not isinstance(item, dict):
            raise StorageError("Every registered archive must be an object.")
        key = item.get("key", "")
        if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", key) or key == "local" or key in keys:
            raise StorageError("Archive keys must be unique and must not be local.")
        keys.add(key)
        database = resolve(item.get("database")); sources = resolve(item.get("source_dir"))
        if database == data_dir / "stats.sqlite3":
            raise StorageError("The writable local database cannot also be registered as a fixed archive.")
        evidence = resolve(item["evidence_root"]) if item.get("evidence_root") else database.parent
        if not native_path(database).is_file() or not native_path(sources).is_dir() or not native_path(evidence).is_dir():
            raise StorageError("A registered archive database, sources folder or evidence folder is missing.")
        if evidence == data_dir or sources == data_dir or (data_dir / "stats.sqlite3").is_relative_to(evidence) or (data_dir / "stats.sqlite3").is_relative_to(sources):
            raise StorageError("Register a dedicated archive evidence folder; the full live data directory cannot be copied as archive evidence.")
        for suffix in ("-wal", "-journal"):
            sidecar = Path(str(database) + suffix)
            if native_path(sidecar).exists() and native_path(sidecar).stat().st_size:
                raise StorageError("A registered archive has pending SQLite journal data; supply a fixed consistent archive before backup.")
        databases.append(database); roots.extend([sources, evidence]); files.add(database)
    for analysis in [*analysis_registration_records(registry), *collection_records]:
        database = resolve(analysis.get("database")); evidence = resolve(analysis.get("evidence_root"))
        if not native_path(database).is_file() or not native_path(evidence).is_dir():
            raise StorageError("The registered analysis database or evidence directory is missing.")
        if database == data_dir / "stats.sqlite3" or evidence == data_dir or (data_dir / "stats.sqlite3").is_relative_to(evidence):
            raise StorageError("The analysis package requires a dedicated directory separate from the live database.")
        for suffix in ("-wal", "-journal"):
            sidecar = Path(str(database) + suffix)
            if native_path(sidecar).exists() and native_path(sidecar).stat().st_size:
                raise StorageError("The analysis snapshot has pending SQLite journal data.")
        databases.append(database); roots.append(evidence); files.add(database)
    for root in sorted(set(roots)):
        physical_root = native_path(root)
        for physical_directory, child_dirs, child_files in os.walk(physical_root, followlinks=False):
            directory = root / Path(physical_directory).relative_to(physical_root)
            _not_link(directory)
            for child in child_dirs + child_files:
                path = directory / child; _not_link(path)
                if not path.resolve().is_relative_to(root):
                    raise StorageError("An archive file resolves outside its registered folder.")
            files.update(directory / child for child in child_files)
    return sorted(files), list(dict.fromkeys(databases))


def backup_library(data_dir, bundle_dir):
    """Create a new portable directory containing only the configured library.

    The local writable database uses SQLite backup; registered fixed archives,
    original source bytes and evidence are copied unchanged. A complete manifest
    is written only after hashes, source stability and SQLite integrity pass.
    """
    data_dir = Path(data_dir).expanduser().resolve()
    bundle = Path(bundle_dir).expanduser().resolve()
    if native_path(bundle).exists():
        raise FileExistsError("Backup bundle directory already exists; choose a new directory.")
    if bundle.is_relative_to(data_dir) or data_dir.is_relative_to(bundle):
        raise StorageError("Put the new bundle outside the live data directory.")
    database = data_dir / "stats.sqlite3"
    if not native_path(database).is_file():
        raise StorageError("No configured local database exists. Nothing to back up.")
    registry_path = data_dir / "archive_registry.json"
    _not_link(registry_path)
    registry_bytes = _optional_bytes(registry_path)
    try:
        registry = json.loads(registry_bytes) if registry_bytes is not None else {"archives": []}
    except ValueError as exc:
        raise StorageError("The archive registry is invalid JSON.") from exc
    # Source collections have their own registry; analysis version pointers and
    # historical archive registrations remain independent and unchanged.
    from stats_app.youtube_repository import list_registered_youtube
    collection_registry_path = data_dir / "youtube_collections.json"
    _not_link(collection_registry_path)
    collection_registry_bytes = _optional_bytes(collection_registry_path)
    collections = list_registered_youtube(data_dir)
    from stats_app.shopify_repository import list_registered_shopify, load_registered_shopify, REGISTRY_FILENAME as SHOPIFY_REGISTRY
    shopify_registry_path = data_dir / SHOPIFY_REGISTRY
    _not_link(shopify_registry_path)
    shopify_registry_bytes = _optional_bytes(shopify_registry_path)
    shopify_collections = list_registered_shopify(data_dir)
    # Verify every registered Shopify database and its retained evidence before
    # opening a destination. Its registry never changes analysis selection.
    for collection in shopify_collections:
        shopify = load_registered_shopify(data_dir, collection["key"])
        for table in shopify.tables:
            shopify.table(table)
    from stats_app.linktree_repository import list_registered_linktree, load_registered_linktree, REGISTRY_FILENAME as LINKTREE_REGISTRY
    linktree_registry_path = data_dir / LINKTREE_REGISTRY
    _not_link(linktree_registry_path)
    linktree_registry_bytes = _optional_bytes(linktree_registry_path)
    linktree_collections = list_registered_linktree(data_dir)
    def linktree_inputs():
        result = []
        for collection in linktree_collections:
            linktree = load_registered_linktree(data_dir, collection["key"])
            # File-package collections have no synthetic SQLite database. Their
            # entire retained namespace is enumerated and verified by the adapter.
            evidence = data_dir / collection["evidence_root"]
            expected = {linktree.package_dir / name for name in linktree.sources().path}
            actual = set(_tree_files(evidence))
            if actual != expected:
                raise StorageError("Registered Linktree evidence contains unexpected files.")
            result.extend(sorted(expected))
        return result
    linktree_files = linktree_inputs()
    from stats_app.tiktok_repository import list_registered_tiktok, load_registered_tiktok, REGISTRY_FILENAME as TIKTOK_REGISTRY
    tiktok_registry_path = data_dir / TIKTOK_REGISTRY
    _not_link(tiktok_registry_path)
    tiktok_registry_bytes = _optional_bytes(tiktok_registry_path)
    tiktok_collections = list_registered_tiktok(data_dir)
    def tiktok_inputs():
        result = []
        for collection in tiktok_collections:
            tiktok = load_registered_tiktok(data_dir, collection["key"], verify_all=True)
            evidence = data_dir / collection["evidence_root"]
            expected = {tiktok.package_dir / name for name in tiktok.sources().path}
            actual = set(_tree_files(evidence))
            if actual != expected:
                raise StorageError("Registered TikTok evidence contains unexpected files.")
            result.extend(sorted(expected))
        return result
    tiktok_files = tiktok_inputs()
    all_collections = [*collections, *shopify_collections]
    inputs, archive_databases = _registered_paths(data_dir, registry, all_collections)
    inputs = sorted(set(inputs) | set(linktree_files) | set(tiktok_files))
    before = {str(p.relative_to(data_dir).as_posix()): _hash(p) for p in inputs}
    for collection in collections:
        from stats_app.youtube_repository import ZIP_FILENAME
        source_zip = collection["evidence_root"] + "/" + collection.get("zip_filename", ZIP_FILENAME)
        if (before.get(collection["database"]) != collection.get("database_sha256")
                or before.get(source_zip) != collection.get("zip_sha256")):
            raise StorageError("Registered YouTube database or ZIP failed SHA-256 verification.")
    for path in archive_databases:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise StorageError("Registered archive SQLite verification failed.")
    native_path(bundle).mkdir(parents=True, exist_ok=False)
    try:
        backup_database(database, bundle / "stats.sqlite3")
        for source in inputs:
            target = bundle / source.relative_to(data_dir)
            native_path(target.parent).mkdir(parents=True, exist_ok=True)
            with native_path(source).open("rb") as src, native_path(target).open("xb") as dst:
                while chunk := src.read(1024 * 1024):
                    dst.write(chunk)
            relative = source.relative_to(data_dir).as_posix()
            if _hash(target) != before[relative] or _hash(source) != before[relative]:
                raise StorageError("An archive changed during backup or failed copy verification.")
        copied_registry = registry_bytes if registry_bytes is not None else b'{"archives":[]}\n'
        with native_path(bundle / "archive_registry.json").open("xb") as handle:
            handle.write(copied_registry)
        if collection_registry_bytes is not None:
            with native_path(bundle / "youtube_collections.json").open("xb") as handle:
                handle.write(collection_registry_bytes)
        if shopify_registry_bytes is not None:
            with native_path(bundle / SHOPIFY_REGISTRY).open("xb") as handle:
                handle.write(shopify_registry_bytes)
        if linktree_registry_bytes is not None:
            with native_path(bundle / LINKTREE_REGISTRY).open("xb") as handle:
                handle.write(linktree_registry_bytes)
        if tiktok_registry_bytes is not None:
            with native_path(bundle / TIKTOK_REGISTRY).open("xb") as handle:
                handle.write(tiktok_registry_bytes)
        after_inputs, _ = _registered_paths(data_dir, registry, all_collections)
        after_inputs = sorted(set(after_inputs) | set(linktree_inputs()) | set(tiktok_inputs()))
        if (inputs != after_inputs
                or _optional_bytes(registry_path) != registry_bytes
                or _optional_bytes(collection_registry_path) != collection_registry_bytes
                or _optional_bytes(shopify_registry_path) != shopify_registry_bytes
                or _optional_bytes(linktree_registry_path) != linktree_registry_bytes
                or _optional_bytes(tiktok_registry_path) != tiktok_registry_bytes
                or any(_hash(p) != before[p.relative_to(data_dir).as_posix()] for p in inputs)):
            raise StorageError("Registered library contents changed during backup; this bundle is incomplete.")
        manifest = {"schema_version": 1, "status": "verified", "created_at": datetime.now(timezone.utc).isoformat(),
                    "local_database_method": "SQLite online backup; includes committed WAL data",
                    "archives_method": "Exact copies of registered fixed archive databases, source folders and evidence roots",
                    "registry_relative_paths_preserved": True, "archive_count": len(registry["archives"]),
                    "analysis_package_included": registry.get("analysis_package") is not None,
                    "analysis_versions_included": len(analysis_registration_records(registry)),
                    "youtube_collections_included": len(collections),
                    "shopify_collections_included": len(shopify_collections),
                    "linktree_collections_included": len(linktree_collections),
                    "tiktok_collections_included": len(tiktok_collections),
                    "files": [{"path": p.relative_to(bundle).as_posix(), "bytes": native_path(p).stat().st_size, "sha256": _hash(p)}
                              for p in sorted(_tree_files(bundle))]}
        with native_path(bundle / "BACKUP_MANIFEST.json").open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2); handle.write("\n")
        verify_bundle(bundle)
    except Exception as exc:
        native_path(bundle / "BACKUP_INCOMPLETE.txt").write_text("Backup did not complete successfully. Do not restore as a verified bundle.\n" + str(exc) + "\n", encoding="utf-8")
        raise
    return bundle


def verify_bundle(bundle_dir):
    """Verify a saved bundle before restore without modifying any file."""
    bundle = Path(bundle_dir).expanduser().resolve()
    if native_path(bundle / "BACKUP_INCOMPLETE.txt").exists():
        raise StorageError("This backup was not completed successfully.")
    manifest = json.loads(native_path(bundle / "BACKUP_MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "verified" or manifest.get("schema_version") != 1:
        raise StorageError("This is not a completed supported backup manifest.")
    listed = set()
    for entry in manifest["files"]:
        relative = Path(entry["path"]); target = bundle / relative
        if relative.is_absolute() or PureWindowsPath(entry["path"]).is_absolute() or ".." in relative.parts or not target.resolve().is_relative_to(bundle):
            raise StorageError("Backup manifest contains an unsafe file path.")
        if entry["path"] in listed:
            raise StorageError("Backup manifest contains duplicate file paths.")
        listed.add(entry["path"])
        _not_link(target)
        if not native_path(target).is_file() or native_path(target).stat().st_size != entry["bytes"] or _hash(target) != entry["sha256"]:
            raise StorageError("Backup file failed size/SHA-256 verification: " + entry["path"])
    actual = {p.relative_to(bundle).as_posix() for p in _tree_files(bundle)} - {"BACKUP_MANIFEST.json"}
    if listed != actual or not {"stats.sqlite3", "archive_registry.json"}.issubset(listed):
        raise StorageError("Backup contains missing or unexpected files.")
    from stats_app.linktree_repository import list_registered_linktree, load_registered_linktree, REGISTRY_FILENAME as LINKTREE_REGISTRY
    if native_path(bundle / LINKTREE_REGISTRY).exists():
        records = list_registered_linktree(bundle)
        if manifest.get("linktree_collections_included") != len(records):
            raise StorageError("Backup Linktree collection count differs from its registry.")
        for record in records:
            load_registered_linktree(bundle, record["key"])
    elif manifest.get("linktree_collections_included", 0):
        raise StorageError("Backup Linktree collection registry is missing.")
    from stats_app.tiktok_repository import list_registered_tiktok, load_registered_tiktok, REGISTRY_FILENAME as TIKTOK_REGISTRY
    if native_path(bundle / TIKTOK_REGISTRY).exists():
        records = list_registered_tiktok(bundle)
        if manifest.get("tiktok_collections_included") != len(records):
            raise StorageError("Backup TikTok collection count differs from its registry.")
        for record in records:
            load_registered_tiktok(bundle, record["key"], verify_all=True)
    elif manifest.get("tiktok_collections_included", 0):
        raise StorageError("Backup TikTok collection registry is missing.")
    return manifest

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--output", help="Local database only: new destination .sqlite3 file (must not exist)")
    choice.add_argument("--bundle-dir", help="Complete registered library: new private directory (must not exist)")
    choice.add_argument("--verify-bundle", help="Read-only verification of a previously created bundle")
    args = parser.parse_args()
    if args.verify_bundle:
        result = verify_bundle(args.verify_bundle)
        print(f"Verified {len(result['files'])} backup files.")
    else:
        settings = load_settings()
        result = backup_library(settings.data_dir, args.bundle_dir) if args.bundle_dir else backup_database(settings.database_path, args.output)
        print(str(result).encode("ascii", "backslashreplace").decode("ascii"))
