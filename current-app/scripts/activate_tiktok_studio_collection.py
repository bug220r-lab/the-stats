"""Back up and register a validated Studio collection in an explicit library.

No existing database, registry, analysis or source file is replaced. The before
inventory is checked after import and replay. Run only for authorized activation.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stats_app.tiktok_repository import TikTokRepository, import_tiktok_collection, load_registered_tiktok


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(library):
    return {p.relative_to(library).as_posix(): {"sha256": sha(p), "bytes": p.stat().st_size}
            for p in library.rglob("*") if p.is_file() and not p.name.endswith(("-wal", "-shm"))}


def activate(package, library, output):
    if output.exists():
        raise FileExistsError("Choose a new activation receipt directory")
    repo = TikTokRepository(package)
    database = library / "stats.sqlite3"
    if not database.is_file():
        raise ValueError("The explicit target must be the existing library")
    before = inventory(library)
    output.mkdir(parents=True)
    (output / "library-before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    with closing(sqlite3.connect(database.as_uri()+"?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(output / "local-database-before.sqlite3")) as backup:
            source.backup(backup)
            assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        table_counts = {name: source.execute('SELECT COUNT(*) FROM "'+name.replace('"','""')+'"').fetchone()[0]
                        for (name,) in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    first = import_tiktok_collection(package, library)
    replay = import_tiktok_collection(package, library)
    loaded = load_registered_tiktok(library, repo.metadata["collection_key"])
    assert loaded.package_sha256 == repo.package_sha256
    table_rows = {d["dataset_id"]: len(loaded.table(d["dataset_id"])) for d in loaded.metadata["datasets"] if d.get("path")}
    after = inventory(library)
    changed = [name for name, value in before.items() if after.get(name) != value]
    if changed:
        raise RuntimeError("Existing library contents changed: " + repr(changed))
    added = sorted(set(after)-set(before))
    allowed = "collections/" + repo.metadata["collection_key"] + "/"
    if any(name != "tiktok_collections.json" and not name.startswith(allowed) for name in added):
        raise RuntimeError("Unexpected library addition")
    receipt = {"completed_at": datetime.now(timezone.utc).isoformat(), "library": str(library),
               "import": first, "replay": replay, "protected_files_unchanged": len(before),
               "existing_table_counts": table_counts, "new_files": len(added), "tables": table_rows,
               "manifest_sha256": repo.manifest_sha256, "package_sha256": repo.package_sha256,
               "sqlite_backup": "local-database-before.sqlite3", "artists_status": "pending",
               "previous_analyses_and_baselines_changed": False}
    (output / "activation.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(activate(args.package_dir.absolute(), args.data_dir.absolute(), args.output.absolute()), indent=2))
