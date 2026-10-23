"""Validate native social exports, then optionally load a distinct local snapshot.

The default is a read-only preview. --commit performs the explicit import after
every listed file and its checksum have passed validation. Raw files remain
unchanged. Existing snapshots, including the October baseline, are not modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stats.social import parse_social_export
from stats.storage import Store


def load_social(manifest_path, db_path=None, *, commit=False):
    manifest_path = Path(manifest_path).expanduser().resolve()
    capture_dir = manifest_path.parent
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported social manifest schema_version.")
    if not manifest.get("snapshot_key") or not manifest.get("snapshot_name"):
        raise ValueError("A social manifest needs a distinct snapshot_key and snapshot_name.")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("A social manifest must identify at least one source export.")
    prepared, seen = [], set()
    for entry in entries:
        path = (capture_dir / entry["path"]).resolve()
        if not path.is_relative_to(capture_dir):
            raise ValueError("Source exports must be inside the manifest directory.")
        if path in seen:
            raise ValueError("The manifest repeats a source file.")
        seen.add(path)
        raw = path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        if checksum != entry.get("sha256"):
            raise ValueError(f"Source checksum mismatch: {path.name}")
        if not entry.get("captured_at") and entry["parser"] != "meta_ui_readings_v1":
            raise ValueError(f"Acquisition capture time is required before loading {path.name}; it cannot be reconstructed from a filesystem timestamp.")
        metadata = {key: value for key, value in entry.items() if key not in {"path", "sha256", "parser"}}
        parsed = parse_social_export(raw, path.name, entry["parser"], metadata)
        errors = [issue for issue in parsed["issues"] if issue["severity"] == "error"]
        if errors:
            raise ValueError(f"Source validation failed for {path.name}: {errors[:5]}")
        if not parsed["observations"]:
            raise ValueError(f"No valid observations in {path.name}.")
        prepared.append({"path": path, "raw": raw, "metadata": metadata, "parsed": parsed, "entry": entry})
    report = {"committed": False, "is_baseline": False, "snapshot_name": manifest["snapshot_name"], "files": []}
    for file in prepared:
        parsed = file["parsed"]
        report["files"].append({"filename": file["path"].name, "sha256": parsed["file_hash"],
                                "source_rows": parsed["source_rows"], "observations": len(parsed["observations"]),
                                "accounts": parsed["accounts"], "period_start": parsed["period_start"],
                                "period_end": parsed["period_end"], "issues": parsed["issues"],
                                "coverage": parsed["coverage"], "reconciliation": parsed["reconciliation"]})
    if not commit:
        return report
    store = Store(db_path or ROOT / "data/stats.sqlite3")
    evidence = json.dumps({"kind": "native_meta_exports", "snapshot_key": manifest["snapshot_key"], "schema_version": 1}, sort_keys=True)
    snapshots = [snapshot for snapshot in store.snapshots() if snapshot["evidence"] == evidence and not snapshot["is_baseline"]]
    if len(snapshots) > 1:
        raise ValueError("Multiple snapshots share this acquisition key; resolve the local snapshot identity before importing.")
    snapshot_id = snapshots[0]["id"] if snapshots else store.create_snapshot(manifest["snapshot_name"], status="available", evidence=evidence)
    for item, file in zip(report["files"], prepared):
        mapping = {"parser": file["entry"]["parser"], "metadata": file["metadata"]}
        item["import_result"] = store.commit_import(snapshot_id, file["path"].name, file["raw"],
                                                     file["parsed"]["observations"], worksheet="CSV",
                                                     mapping=mapping, issues=file["parsed"]["issues"])
    report["manifest_import"] = store.commit_import(snapshot_id, manifest_path.name, manifest_bytes, [],
                                                     worksheet="capture manifest", mapping={"purpose": "native social acquisition evidence"})
    report.update(committed=True, snapshot_id=snapshot_id, db_path=str(store.path))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--database", type=Path, default=ROOT / "data/stats.sqlite3")
    parser.add_argument("--commit", action="store_true", help="Commit a separately identified social snapshot after all files pass preflight.")
    args = parser.parse_args()
    print(json.dumps(load_social(args.manifest, args.database, commit=args.commit), indent=2))


if __name__ == "__main__":
    main()
