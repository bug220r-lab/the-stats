"""Normalize retained native Meta content exports without changing the library."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stats_app.meta_content import normalize_collection


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(normalize_collection(args.collection_root, args.output_dir), ensure_ascii=True, indent=2))
