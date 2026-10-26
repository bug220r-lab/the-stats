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


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_database(database, output):
    """Include committed WAL contents using SQLite backup without changing source."""
    database, output = Path(database).resolve(), Path(output).expanduser().resolve()
    if not database.is_file():
        raise StorageError("No configured local database exists. Nothing to back up.")
    if database == output:
        raise StorageError("Backup destination must differ from the live database.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb"):
        pass
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source, closing(sqlite3.connect(output)) as destination:
        source.backup(destination)
        if destination.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise StorageError("Backup SQLite verification failed; preserve the incomplete output for inspection.")
    return output


def _not_link(path):
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise StorageError("Registered backup inputs must not contain symbolic links or directory junctions.")


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
        if not database.is_file() or not sources.is_dir() or not evidence.is_dir():
            raise StorageError("A registered archive database, sources folder or evidence folder is missing.")
        if evidence == data_dir or sources == data_dir or (data_dir / "stats.sqlite3").is_relative_to(evidence) or (data_dir / "stats.sqlite3").is_relative_to(sources):
            raise StorageError("Register a dedicated archive evidence folder; the full live data directory cannot be copied as archive evidence.")
        for suffix in ("-wal", "-journal"):
            sidecar = Path(str(database) + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                raise StorageError("A registered archive has pending SQLite journal data; supply a fixed consistent archive before backup.")
        databases.append(database); roots.extend([sources, evidence]); files.add(database)
    for analysis in [*analysis_registration_records(registry), *collection_records]:
        database = resolve(analysis.get("database")); evidence = resolve(analysis.get("evidence_root"))
        if not database.is_file() or not evidence.is_dir():
            raise StorageError("The registered analysis database or evidence directory is missing.")
        if database == data_dir / "stats.sqlite3" or evidence == data_dir or (data_dir / "stats.sqlite3").is_relative_to(evidence):
            raise StorageError("The analysis package requires a dedicated directory separate from the live database.")
        for suffix in ("-wal", "-journal"):
            sidecar = Path(str(database) + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                raise StorageError("The analysis snapshot has pending SQLite journal data.")
        databases.append(database); roots.append(evidence); files.add(database)
    for root in sorted(set(roots)):
        for directory, child_dirs, child_files in os.walk(root, followlinks=False):
            directory = Path(directory); _not_link(directory)
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
    if bundle.exists():
        raise FileExistsError("Backup bundle directory already exists; choose a new directory.")
    if bundle.is_relative_to(data_dir) or data_dir.is_relative_to(bundle):
        raise StorageError("Put the new bundle outside the live data directory.")
    database = data_dir / "stats.sqlite3"
    if not database.is_file():
        raise StorageError("No configured local database exists. Nothing to back up.")
    registry_path = data_dir / "archive_registry.json"
    _not_link(registry_path)
    registry_bytes = registry_path.read_bytes() if registry_path.exists() else None
    try:
        registry = json.loads(registry_bytes) if registry_bytes is not None else {"archives": []}
    except ValueError as exc:
        raise StorageError("The archive registry is invalid JSON.") from exc
    # Source collections have their own registry; analysis version pointers and
    # historical archive registrations remain independent and unchanged.
    from stats_app.youtube_repository import list_registered_youtube
    collection_registry_path = data_dir / "youtube_collections.json"
    _not_link(collection_registry_path)
    collection_registry_bytes = collection_registry_path.read_bytes() if collection_registry_path.exists() else None
    collections = list_registered_youtube(data_dir)
    from stats_app.shopify_repository import list_registered_shopify, load_registered_shopify, REGISTRY_FILENAME as SHOPIFY_REGISTRY
    shopify_registry_path = data_dir / SHOPIFY_REGISTRY
    _not_link(shopify_registry_path)
    shopify_registry_bytes = shopify_registry_path.read_bytes() if shopify_registry_path.exists() else None
    shopify_collections = list_registered_shopify(data_dir)
    # Verify every registered Shopify database and its retained evidence before
    # opening a destination. Its registry never changes analysis selection.
    for collection in shopify_collections:
        shopify = load_registered_shopify(data_dir, collection["key"])
        for table in shopify.tables:
            shopify.table(table)
    all_collections = [*collections, *shopify_collections]
    inputs, archive_databases = _registered_paths(data_dir, registry, all_collections)
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
    bundle.mkdir(parents=True, exist_ok=False)
    try:
        backup_database(database, bundle / "stats.sqlite3")
        for source in inputs:
            target = bundle / source.relative_to(data_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as src, target.open("xb") as dst:
                while chunk := src.read(1024 * 1024):
                    dst.write(chunk)
            relative = source.relative_to(data_dir).as_posix()
            if _hash(target) != before[relative] or _hash(source) != before[relative]:
                raise StorageError("An archive changed during backup or failed copy verification.")
        copied_registry = registry_bytes if registry_bytes is not None else b'{"archives":[]}\n'
        with (bundle / "archive_registry.json").open("xb") as handle:
            handle.write(copied_registry)
        if collection_registry_bytes is not None:
            with (bundle / "youtube_collections.json").open("xb") as handle:
                handle.write(collection_registry_bytes)
        if shopify_registry_bytes is not None:
            with (bundle / SHOPIFY_REGISTRY).open("xb") as handle:
                handle.write(shopify_registry_bytes)
        after_inputs, _ = _registered_paths(data_dir, registry, all_collections)
        if (inputs != after_inputs
                or (registry_path.read_bytes() if registry_path.exists() else None) != registry_bytes
                or (collection_registry_path.read_bytes() if collection_registry_path.exists() else None) != collection_registry_bytes
                or (shopify_registry_path.read_bytes() if shopify_registry_path.exists() else None) != shopify_registry_bytes
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
                    "files": [{"path": p.relative_to(bundle).as_posix(), "bytes": p.stat().st_size, "sha256": _hash(p)}
                              for p in sorted(bundle.rglob("*")) if p.is_file()]}
        with (bundle / "BACKUP_MANIFEST.json").open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2); handle.write("\n")
        verify_bundle(bundle)
    except Exception as exc:
        (bundle / "BACKUP_INCOMPLETE.txt").write_text("Backup did not complete successfully. Do not restore as a verified bundle.\n" + str(exc) + "\n", encoding="utf-8")
        raise
    return bundle


def verify_bundle(bundle_dir):
    """Verify a saved bundle before restore without modifying any file."""
    bundle = Path(bundle_dir).expanduser().resolve()
    if (bundle / "BACKUP_INCOMPLETE.txt").exists():
        raise StorageError("This backup was not completed successfully.")
    manifest = json.loads((bundle / "BACKUP_MANIFEST.json").read_text(encoding="utf-8"))
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
        if not target.is_file() or target.stat().st_size != entry["bytes"] or _hash(target) != entry["sha256"]:
            raise StorageError("Backup file failed size/SHA-256 verification: " + entry["path"])
    actual = {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()} - {"BACKUP_MANIFEST.json"}
    if listed != actual or not {"stats.sqlite3", "archive_registry.json"}.issubset(listed):
        raise StorageError("Backup contains missing or unexpected files.")
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
