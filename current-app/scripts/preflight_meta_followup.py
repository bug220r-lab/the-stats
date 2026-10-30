"""Read-only preservation gate for the next Meta evidence collection."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from stats_app.analysis_repository import analysis_registration_records
from stats_app.backup import _registered_paths
from stats_app.config import load_settings
from stats_app.storage import StorageError


def capture(data_dir, output):
    data_dir, output = Path(data_dir).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("Preserving the existing preflight; choose a new output.")
    registry_path = data_dir / "archive_registry.json"
    registry_bytes = registry_path.read_bytes()
    registry = json.loads(registry_bytes)
    _, registered = _registered_paths(data_dir, registry)
    paths = list(dict.fromkeys([data_dir / "stats.sqlite3", *registered]))
    items = []
    for path in paths:
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        sidecars = []
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(path) + suffix)
            sidecars.append({"suffix": suffix, "exists": sidecar.exists(),
                             "bytes": sidecar.stat().st_size if sidecar.exists() else None})
            if suffix != "-shm" and sidecar.exists() and sidecar.stat().st_size:
                raise StorageError("Checkpoint the live database before this immutable preservation check.")
        with sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True) as db:
            db.execute("PRAGMA query_only=ON")
            checks = [r[0] for r in db.execute("PRAGMA quick_check")]
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            counts = {"assets": db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]} if "assets" in tables else {}
        after = hashlib.sha256(path.read_bytes()).hexdigest()
        if checks != ["ok"] or before != after:
            raise StorageError("Database preservation preflight failed: " + str(path))
        items.append({"relative_path": path.relative_to(data_dir).as_posix(), "bytes": path.stat().st_size,
                      "sha256": before, "sha256_after_check": after, "quick_check": checks,
                      "unchanged_during_check": True, "connection": "mode=ro&immutable=1; query_only=ON",
                      "sidecars": sidecars, "table_counts": counts})
    if registry_path.read_bytes() != registry_bytes:
        raise StorageError("Registry changed during preservation preflight.")
    report = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "configured_data_dir": str(data_dir),
              "registry": {"relative_path": "archive_registry.json", "sha256": hashlib.sha256(registry_bytes).hexdigest()},
              "active_analysis": registry["analysis_package"], "analysis_versions": analysis_registration_records(registry),
              "databases": items, "expected_database_count": len(items), "all_quick_checks_ok": True,
              "all_database_and_registry_bytes_unchanged": True,
              "collection_scope": ["Instagram recent Story song/link evidence", "Meta Ads Manager coverage and destinations"],
              "excluded_scope": ["TikTok"], "mutations": "Only this new workspace audit JSON; no live database or registry writes"}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture(args.data_dir or load_settings().data_dir, args.output)
    print(json.dumps({"databases": result["expected_database_count"], "active_analysis": result["active_analysis"],
                      "unchanged": result["all_database_and_registry_bytes_unchanged"]}, ensure_ascii=False))
