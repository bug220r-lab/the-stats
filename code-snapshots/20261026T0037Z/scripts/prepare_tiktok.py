"""Inspect and stage TikTok export evidence without importing live data."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stats_app.tiktok import inspect_csv, preview_export, stage_preview


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Repeated JSON key {key!r}; no mapping was applied.")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"JSON contains non-finite number {value!r}.")


def _read_json(path):
    result = json.loads(Path(path).read_text(encoding="utf-8-sig"),
                        object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    if not isinstance(result, dict):
        raise ValueError("Mapping and metadata files must each contain a JSON object.")
    return result


def _write_json(path, value):
    encoded = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)


def _read_comparison(path):
    if path is None:
        return ()
    reader = csv.reader(io.StringIO(Path(path).read_text(encoding="utf-8-sig")))
    headers = next(reader, [])
    normalized = [header.strip().casefold() for header in headers]
    if not headers or any(not header for header in normalized) or len(set(normalized)) != len(headers):
        raise ValueError("Prior staged observations require nonempty, unambiguous CSV headers.")
    rows = []
    for line, row in enumerate(reader, start=2):
        if len(row) != len(headers):
            raise ValueError(f"Prior staged observations row {line} has an inconsistent field count.")
        rows.append(dict(zip(headers, row)))
    return rows


def parser():
    command = argparse.ArgumentParser(description=__doc__,
        epilog="This preparation tool never commits to SQLite, changes the active analysis, or connects to TikTok.")
    modes = command.add_subparsers(dest="command", required=True)
    inspect = modes.add_parser("inspect", help="Inspect literal headers and bounded samples; infer no metric meanings.")
    inspect.add_argument("--input", required=True, type=Path)
    inspect.add_argument("--encoding", default="utf-8-sig")
    inspect.add_argument("--delimiter", choices=["comma", "tab", "semicolon"], default="comma")
    inspect.add_argument("--header-row", type=int, default=1)
    inspect.add_argument("--output", type=Path, help="Optional new JSON receipt file; existing files are refused.")
    for name, description in [("preview", "Validate explicit source, grain and metric mapping without saving live data."),
                              ("stage", "Preserve source bytes and accepted or rejected review evidence in a new folder.")]:
        mode = modes.add_parser(name, help=description)
        mode.add_argument("--input", required=True, type=Path)
        mode.add_argument("--mapping", required=True, type=Path)
        mode.add_argument("--metadata", required=True, type=Path)
        mode.add_argument("--compare-observations", type=Path,
                          help="Optional prior TikTok stage normalized CSV; report overlaps without merging its rows.")
        mode.add_argument("--output", required=name == "stage", type=Path,
                          help="New stage directory; optional new JSON receipt file for preview.")
    return command


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.output is not None and args.output.exists():
            raise ValueError("Output already exists; choose a new path to preserve earlier evidence.")
        raw = args.input.read_bytes()
        if args.command == "inspect":
            result = inspect_csv(raw, args.input.name, encoding=args.encoding,
                delimiter={"comma":",", "tab":"\t", "semicolon":";"}[args.delimiter], header_row=args.header_row)
        else:
            mapping, metadata = _read_json(args.mapping), _read_json(args.metadata)
            comparison = _read_comparison(args.compare_observations)
            if args.command == "stage":
                result = stage_preview(raw, args.input.name, mapping, metadata, args.output, existing_records=comparison)
            else:
                result = preview_export(raw, args.input.name, mapping, metadata, existing_records=comparison)
        if args.command != "stage" and args.output is not None:
            _write_json(args.output, result)
            display = {key:value for key,value in result.items() if key not in {"records", "sample_rows"}}
            display["receipt_file"] = str(args.output.resolve())
        else:
            display = result
        print(json.dumps(display, ensure_ascii=False, indent=2, allow_nan=False))
        return 2 if result.get("accepted") is False else 0
    except (OSError, ValueError, TypeError, LookupError) as exc:
        print(json.dumps({"accepted":False, "error":str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
