"""Load the preserved connected package into local SQLite, without network access.

This intentionally creates an ordinary, unverified archived-source snapshot. It
does not identify or reconstruct an original reporting baseline and never seals
the snapshot. Re-running with unchanged canonical bytes is idempotent.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stats.ingestion import FIELDS, preview_import, read_table
from stats.storage import Store


def canonical_mapping():
    return {"fields": {field: field for field in FIELDS}, "metrics": {}, "defaults": {},
            "numeric_locale": "en_US", "date_format": "ISO"}


def load_connected(db_path=None, connected_dir=None, filenames=None, include_queue=True):
    connected = Path(connected_dir or ROOT / "data/connected")
    inventory_path = connected / "source_inventory.json"
    inventory_bytes = inventory_path.read_bytes()
    inventory = json.loads(inventory_bytes)
    evidence = json.dumps({"source_archive": inventory["source_archive"],
                           "baseline_status": inventory["baseline_status"],
                           "baseline_reason": inventory["baseline_reason"]}, sort_keys=True)
    selected = [entry for entry in inventory["canonical_files"]
                if filenames is None or Path(entry["path"]).name in filenames]
    if not selected:
        raise ValueError("No canonical source files selected.")
    # Verify bytes against the staging manifest before creating a database record.
    for entry in selected:
        raw = (connected / entry["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError(f"Canonical file checksum mismatch: {Path(entry['path']).name}")
    store = Store(db_path or ROOT / "data/stats.sqlite3")
    snapshots = [s for s in store.snapshots() if s["name"] == inventory["snapshot_label"] and s["evidence"] == evidence]
    snapshot_id = snapshots[0]["id"] if snapshots else store.create_snapshot(
        inventory["snapshot_label"], is_baseline=False, status="unverified", evidence=evidence)
    mapping = canonical_mapping()
    mapping_name = "Canonical observation CSV"
    if store.mappings().get(mapping_name) != mapping:
        store.save_mapping(mapping_name, mapping)
    results = []
    for entry in selected:
        file = connected / entry["path"]
        raw = file.read_bytes()
        frame = read_table(raw, file.name)
        preview = preview_import(frame, mapping, file.name, raw)
        errors = [issue for issue in preview["issues"] if issue.get("severity") == "error"]
        if errors:
            raise ValueError(f"Canonical validation failed for {file.name}: {errors[:5]}")
        if len(preview["observations"]) != entry["observations"]:
            raise ValueError(f"Canonical row count changed for {file.name}.")
        result = store.commit_import(snapshot_id, file.name, raw, preview["observations"],
                                     worksheet="CSV", mapping=mapping, issues=preview["issues"])
        results.append({"filename": file.name, **result})
    exclusions = [{"severity": "warning", "code": "canonical_exclusion", "source_row": row.get("row"),
                   "message": f"{row['file']}: {row.get('side', '')} {row['reason']}", "source": row}
                  for row in inventory.get("excluded_from_canonical", [])]
    exclusions.append({"severity": "warning", "code": "baseline_unverified", "message": inventory["baseline_reason"]})
    audit_result = store.commit_import(snapshot_id, "source_inventory.json", inventory_bytes, [],
                                      worksheet="source manifest", mapping={"purpose": "connected-source inventory and exclusions"}, issues=exclusions)
    queue_count = 0
    if include_queue and (connected / "collection_queue.csv").exists():
        with (connected / "collection_queue.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        acquisition = json.loads((connected / "acquisition.json").read_text())
        for row in rows:
            row["source_row"] = row["source_sheet_row"]
        source_ref = acquisition["workbook_url"] + "#" + acquisition["queue_range"]
        queue_count = store.save_queue(rows, source_ref, captured_at=None)
    return {"snapshot_id": snapshot_id, "is_baseline": False, "baseline_status": "unverified",
            "files": results, "source_inventory_import": audit_result, "queue_rows": queue_count,
            "db_path": str(store.path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "data/stats.sqlite3")
    parser.add_argument("--connected-dir", type=Path, default=ROOT / "data/connected")
    args = parser.parse_args()
    print(json.dumps(load_connected(args.database, args.connected_dir), indent=2))


if __name__ == "__main__":
    main()
