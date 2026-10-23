"""Activate a new immutable analysis version while retaining every older store."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from stats_app.analysis_repository import AnalysisRepository, list_registered_analyses
from stats_app.backup import _registered_paths
from stats_app.config import load_settings
from stats_app.storage import StorageError


def _digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def promote(stage, audit, data_dir, *, key, label=None):
    """Add a new key; identical replays are read-only and never reactivate.

    The legacy pointer is migrated in the same atomic registry replacement that
    selects the new version. Conflicting copies remain unregistered and intact.
    """
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        raise StorageError("Analysis version keys must contain only letters, numbers, underscores or hyphens.")
    stage, audit, data_dir = (Path(path).expanduser().resolve() for path in (stage, audit, data_dir))
    source = AnalysisRepository(stage / "analysis.sqlite3")
    for table in source.tables:
        source.table(table)
    source.original_zip()
    if not audit.is_file():
        raise StorageError("An independent analysis audit file is required.")
    version_label = label or source.metadata["label"]
    if not isinstance(version_label, str) or not version_label.strip():
        raise StorageError("The analysis version label must be nonempty text.")
    target = data_dir / "analysis" / key
    for path in (target, *target.parents):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise StorageError("The analysis destination must not contain links or junctions.")
        if path == data_dir:
            break
    if stage == target or stage.is_relative_to(target) or target.is_relative_to(stage):
        raise StorageError("The analysis stage and destination must be separate directories.")
    for path in stage.rglob("*"):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise StorageError("The analysis stage must not contain links or junctions.")
    data_dir.mkdir(parents=True, exist_ok=True)
    lock = data_dir / "archive_registry.lock"
    with lock.open("x", encoding="utf-8") as handle:
        handle.write("Analysis version promotion in progress.\n")
    try:
        registry_path = data_dir / "archive_registry.json"
        if registry_path.is_symlink():
            raise StorageError("The registry must not be a symbolic link.")
        before_registry = registry_path.read_bytes() if registry_path.exists() else None
        registry = json.loads(before_registry) if before_registry is not None else {"archives": []}
        records = list_registered_analyses(data_dir)
        _, old_archives = _registered_paths(data_dir, registry)
        old_paths = list(dict.fromkeys([data_dir / "stats.sqlite3", *old_archives]))
        before = {path.relative_to(data_dir).as_posix(): _digest(path) for path in old_paths if path.exists()}
        item = {"key": key, "database": f"analysis/{key}/analysis.sqlite3", "evidence_root": f"analysis/{key}", "label": version_label}
        registered = next((entry for entry in records if entry["key"] == key), None)
        if registered is not None:
            same_registration = {field: value for field, value in registered.items() if field != "active"} == item
            same_database = target.is_dir() and _digest(target / "analysis.sqlite3") == _digest(source.db_path)
            same_audit = (target / "independent_analysis_audit.json").is_file() and _digest(target / "independent_analysis_audit.json") == _digest(audit)
            if not (same_registration and same_database and same_audit):
                raise StorageError("This analysis key already identifies different data or evidence; choose a new key.")
            return {"activated": str(target), "key": key, "idempotent": True, "active": registered["active"],
                    "earlier_databases_unchanged": True, "tables": len(source.tables)}
        if target.exists():
            raise FileExistsError("Preserving existing unregistered analysis directory; choose a new key.")
        stage_hashes = {path.relative_to(stage).as_posix(): _digest(path) for path in stage.rglob("*") if path.is_file()}
        audit_hash = _digest(audit)
        if "independent_analysis_audit.json" in stage_hashes and stage_hashes["independent_analysis_audit.json"] != audit_hash:
            raise StorageError("The stage contains different independent audit evidence.")
        if "activation_receipt.json" in stage_hashes:
            raise StorageError("Stage a new analysis package without an older activation receipt.")
        shutil.copytree(stage, target)
        if not (target / "independent_analysis_audit.json").exists():
            shutil.copy2(audit, target / "independent_analysis_audit.json")
        for relative, digest in stage_hashes.items():
            if _digest(stage / relative) != digest or _digest(target / relative) != digest:
                raise StorageError("Analysis stage changed during promotion or its copy failed verification.")
        if _digest(audit) != audit_hash or _digest(target / "independent_analysis_audit.json") != audit_hash:
            raise StorageError("Independent audit changed during promotion.")
        report = {"key": key, "activated_at": datetime.now(timezone.utc).isoformat(),
                  "database_sha256": _digest(target / "analysis.sqlite3"), "earlier_database_hashes": before,
                  "earlier_databases_unchanged": True, "metadata": source.metadata}
        with (target / "activation_receipt.json").open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        registry["analysis_versions"] = [{field: value for field, value in entry.items() if field != "active"} for entry in records] + [item]
        registry["analysis_package"] = item
        _registered_paths(data_dir, registry)
        pending = registry_path.with_suffix(".json.new")
        with pending.open("x", encoding="utf-8") as handle:
            json.dump(registry, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        if (registry_path.read_bytes() if registry_path.exists() else None) != before_registry:
            raise StorageError("The registry changed concurrently; the new analysis remains unregistered.")
        if any(_digest(data_dir / path) != value for path, value in before.items()):
            raise StorageError("Earlier data changed concurrently; the registry is unchanged.")
        pending.replace(registry_path)
        return {"activated": str(target), "key": key, "tables": len(source.tables), "idempotent": False,
                "active": True, "earlier_databases_unchanged": True}
    finally:
        lock.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--key", required=True, help="New stable version key; existing data is never replaced")
    parser.add_argument("--label")
    parser.add_argument("--data-dir", type=Path, help="Defaults to the configured local data directory")
    args = parser.parse_args()
    print(json.dumps(promote(args.stage, args.audit, args.data_dir or load_settings().data_dir, key=args.key, label=args.label)))
