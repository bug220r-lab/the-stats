"""Create or inspect a TikTok collection workspace without activating data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stats_app.tiktok_collection import create_collection, assess_collection, _new_destination


def parser():
    command = argparse.ArgumentParser(description=__doc__)
    modes = command.add_subparsers(dest="command", required=True)
    init = modes.add_parser("init", help="Create a fresh collection folder with empty acquisition worksheets.")
    init.add_argument("--output", required=True, type=Path)
    init.add_argument("--profile-url", required=True)
    init.add_argument("--prepared-on", default="2026-10-26")
    status = modes.add_parser("status", help="Inspect collection status and source hashes without modifying the package.")
    status.add_argument("--collection", required=True, type=Path)
    status.add_argument("--output", type=Path, help="Optional new JSON receipt file; existing files are refused.")
    return command


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.output is not None and args.output.exists():
            raise FileExistsError("Output already exists; choose a fresh path.")
        if args.command == "init":
            result = create_collection(args.output, profile_url=args.profile_url, prepared_on=args.prepared_on)
        else:
            if args.output is not None:
                _new_destination(args.output)
            result = assess_collection(args.collection)
            if args.output is not None:
                with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        # Console code pages on Windows may not encode the project name or source
        # text. JSON escapes keep stdout portable; saved receipts remain UTF-8.
        print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
        return 2 if any(item["severity"] == "error" for item in result["issues"]) else 0
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        print(json.dumps({"accepted": False, "error": str(exc), "library_modified": False}, ensure_ascii=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
