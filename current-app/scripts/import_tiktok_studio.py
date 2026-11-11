"""Validate a Studio collection; copy/register only with explicit --execute."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stats_app.tiktok_repository import TikTokRepository, import_tiktok_collection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, help="Explicit durable library destination; required with --execute")
    parser.add_argument("--execute", action="store_true", help="Copy verified bytes and register the separate Studio collection")
    args = parser.parse_args()
    if args.execute and args.data_dir is None:
        parser.error("--execute requires --data-dir")
    if args.execute:
        receipt = import_tiktok_collection(args.package_dir, args.data_dir)
    else:
        repo = TikTokRepository(args.package_dir)
        receipt = {"mode": "validation_only", "key": repo.metadata["collection_key"], "tables": len(repo.tables),
                   "assets": len(repo.sources()), "package_sha256": repo.package_sha256,
                   "manifest_sha256": repo.manifest_sha256}
    print(json.dumps(receipt, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
