"""Register a verified, staged library without replacing the writable database."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

from stats_app.archive_repository import ImportedArchiveRepository
from stats_app.config import load_settings


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def promote(stage, recovery_zip, cross_reference, data_dir):
    stage, recovery_zip, cross_reference, data_dir = map(Path, (stage, recovery_zip, cross_reference, data_dir))
    key = "handoff-20261022"
    target = data_dir / "archives" / key
    registry_path = data_dir / "archive_registry.json"
    if target.exists():
        raise FileExistsError(f"Preserving existing archive: {target}")
    report = json.loads((stage / "spotify_import_report.json").read_text(encoding="utf-8"))
    if not (report.get("original_unchanged") and report.get("earlier_snapshot_rows_unchanged") and report.get("integrity") == "ok"):
        raise ValueError("Staging preservation checks did not pass")
    # Validate the actual staged source, including every imported raw file.
    repo = ImportedArchiveRepository(stage / "data/stats.sqlite3", stage / "data/sources", stage)
    for source_hash in repo.import_history().source_hash.unique():
        repo.original_source(source_hash)
    with sqlite3.connect(repo.db_path.as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Staged database integrity failed")
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {"archives": []}
    if any(item["key"] == key for item in registry["archives"]):
        raise ValueError("Archive is already registered; no replacement attempted")
    original_db = data_dir / "stats.sqlite3"
    original_hash = digest(original_db) if original_db.exists() else None
    temporary = target.with_name(key + ".staging")
    if temporary.exists():
        raise FileExistsError(f"Preserving an earlier partial copy: {temporary}")
    shutil.copytree(stage, temporary)
    evidence = temporary / "evidence"
    evidence.mkdir()
    shutil.copy2(recovery_zip, evidence / recovery_zip.name)
    (temporary / "reconciliation").mkdir(exist_ok=True)
    shutil.copy2(cross_reference, temporary / "reconciliation/cross_reference.json")
    files = {p.relative_to(temporary).as_posix(): digest(p) for p in temporary.rglob("*") if p.is_file()}
    for path in stage.rglob("*"):
        if path.is_file() and files[path.relative_to(stage).as_posix()] != digest(path):
            raise ValueError("Copy verification failed; original data untouched")
    if files["evidence/" + recovery_zip.name] != digest(recovery_zip):
        raise ValueError("Recovery ZIP copy verification failed")
    receipt = {"created_at": datetime.now(timezone.utc).isoformat(), "archive_key": key,
               "local_database_sha256_before": original_hash, "files_sha256": files,
               "snapshots": repo.list_snapshots().to_dict("records"),
               "note": "Archive registered separately. Original baseline remains unverified."}
    (temporary / "promotion_receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.rename(target)
    registry["archives"].append({"key": key, "database": f"archives/{key}/data/stats.sqlite3",
                                "source_dir": f"archives/{key}/data/sources", "evidence_root": f"archives/{key}",
                                "label": "Recovered handoff + Spotify extensions"})
    pending = registry_path.with_suffix(".json.new")
    if pending.exists():
        raise FileExistsError("Preserving an earlier pending registry")
    pending.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    pending.replace(registry_path)
    if original_hash and digest(original_db) != original_hash:
        raise ValueError("The writable database changed during registration; investigate concurrent imports")
    print(json.dumps({"registered": str(target), "local_database_unchanged": True,
                      "snapshots": receipt["snapshots"], "verified_files": len(files)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--recovery-zip", type=Path, required=True)
    parser.add_argument("--cross-reference", type=Path, required=True)
    args = parser.parse_args()
    promote(args.stage, args.recovery_zip, args.cross_reference, load_settings().data_dir)
