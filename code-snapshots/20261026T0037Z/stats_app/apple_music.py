"""Explicit-mapping Apple Music CSV preparation; no library or GUI integration.

The mapping is an application contract, never a guessed native export schema.
Every retained row is review evidence. Staging does not commit observations.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from stats_app.validation import COLUMNS

SCHEMA_VERSION = 1
SCOPE_DIMENSION = "_apple_music_scope"
METRIC_BASES = {"plays": "period_count", "daily_unique_listeners": "distinct_count",
                "average_daily_listeners": "average", "period_unique_listeners": "distinct_count",
                "shazams": "period_count", "radio_spins": "period_count", "video_views": "period_count",
                "song_purchases": "period_count", "album_purchases": "period_count"}
STATUSES = {"observed", "missing", "suppressed", "unavailable"}
EXTRA_COLUMNS = ["source_kind", "report_scope", "filters_json", "service", "source_file", "source_sha256",
                 "source_record", "source_field", "source_value_raw", "source_status_raw", "value_status",
                 "value_exact", "source_url", "captured_at_raw", "native_record_json"]
OUTPUT_COLUMNS = COLUMNS + EXTRA_COLUMNS


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _text(value):
    return "" if value is None else str(value)


def _issue(issues, severity, code, message, source_row="", metric=""):
    issues.append(dict(severity=severity, code=code, message=message, source_row=source_row, metric=metric))


def _filename(filename):
    if (not isinstance(filename, str) or not filename or filename in {".", ".."}
            or any(char in filename for char in '/\\:\x00<>|?*') or any(ord(char) < 32 for char in filename) or PureWindowsPath(filename).drive
            or filename.rstrip(" .") != filename or Path(filename).suffix.lower() != ".csv"
            or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", Path(filename).stem, re.I)):
        raise ValueError("Use a safe CSV basename, without a directory, drive or stream name.")
    return filename


def _read(raw_bytes, filename, encoding, delimiter, header_row):
    _filename(filename)
    if not isinstance(raw_bytes, bytes):
        raise ValueError("CSV input must be the original bytes.")
    if not isinstance(encoding, str) or not encoding or not isinstance(delimiter, str) or len(delimiter) != 1:
        raise ValueError("Supply an explicit encoding and one-character delimiter.")
    if isinstance(header_row, bool) or not isinstance(header_row, int) or header_row < 1:
        raise ValueError("header_row must be a positive one-based CSV record number.")
    source = dict(filename=filename, sha256=_sha(raw_bytes), bytes=len(raw_bytes), encoding=encoding,
                  delimiter=delimiter, header_row=header_row)
    issues, headers, rows = [], [], []
    try:
        decoded = raw_bytes.decode(encoding)
        reader = csv.reader(io.StringIO(decoded, newline=""), delimiter=delimiter, strict=True)
        for ordinal, cells in enumerate(reader, 1):
            if ordinal < header_row:
                continue
            if ordinal == header_row:
                headers = cells
                normalized = [cell.strip().casefold() for cell in cells]
                if not normalized or any(not cell for cell in normalized) or len(normalized) != len(set(normalized)):
                    _issue(issues, "error", "ambiguous_headers", "Headers must be nonempty and unique after trimming and ignoring case.", reader.line_num)
                continue
            if not cells:
                _issue(issues, "warning", "blank_source_record", "Blank CSV record retained in original bytes, without a fabricated observation.", reader.line_num)
                continue
            if len(cells) != len(headers):
                _issue(issues, "error", "ragged_source_record", f"Expected {len(headers)} cells; found {len(cells)}. No cell alignment was guessed.", reader.line_num)
                continue
            rows.append((reader.line_num, ordinal, dict(zip(headers, cells))))
        if not headers:
            _issue(issues, "error", "missing_header", "The explicit header record is absent.")
        if not rows:
            _issue(issues, "error", "empty_source", "No rectangular data records are available.")
    except (UnicodeError, LookupError, csv.Error) as exc:
        _issue(issues, "error", "csv_read_error", str(exc))
    return source, headers, rows, issues


def inspect_csv(raw_bytes: bytes, filename: str, *, encoding="utf-8-sig", delimiter=",", header_row=1):
    source, headers, rows, issues = _read(raw_bytes, filename, encoding, delimiter, header_row)
    return dict(accepted=not any(item["severity"] == "error" for item in issues), source=source,
                headers=headers, source_row_count=len(rows), issues=issues,
                sample_rows=[dict(source_row=line, source_record=ordinal, values=native)
                             for line, ordinal, native in rows[:5]])


def _known(value):
    if not isinstance(value, str):
        return False
    text = _text(value).strip()
    return bool(text) and not ("<" in text or ">" in text or text.casefold() in {"todo", "tbd", "replace_me", "placeholder"})


def _iso(raw):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", _text(raw)):
        raise ValueError("Explicit metadata period bounds must use YYYY-MM-DD.")
    return date.fromisoformat(raw).isoformat()


def _source_date(raw, pattern):
    if not raw.strip():
        raise ValueError("Mapped date cell is blank; metadata does not replace mapped blanks.")
    if ("%Y" not in pattern or not any(part in pattern for part in ("%m", "%b", "%B")) or "%d" not in pattern
            or any(part in pattern for part in ("%H", "%I", "%M", "%S", "%p", "%z", "%Z", "%X", "%c"))):
        raise ValueError("date_format must explicitly supply four-digit year, month and day without a time or timezone.")
    return datetime.strptime(raw.strip(), pattern).date().isoformat()


def _capture(raw):
    if not _text(raw).strip():
        return ""
    if not isinstance(raw, str):
        raise ValueError("captured_at must be an explicit ISO timestamp string or blank.")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("captured_at requires an explicit UTC offset when supplied.")
    return parsed.astimezone(timezone.utc).isoformat()


def _number(raw, number_format, metric):
    token = raw.strip()
    pattern = r"[+]?(?:\d+(?:\.\d+)?)" if number_format == "plain" else r"[+]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?"
    if not re.fullmatch(pattern, token):
        raise ValueError("Use an exact nonnegative number in the configured number format; K/M suffixes, ranges and percentages are not guessed.")
    try:
        value = Decimal(token.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("Invalid numeric source value.") from exc
    if not value.is_finite() or value < 0 or (metric != "average_daily_listeners" and value != value.to_integral_value()):
        raise ValueError("Counts must be finite nonnegative integers; only average_daily_listeners may be fractional.")
    number = int(value) if value == value.to_integral_value() else float(value)
    try:
        finite = math.isfinite(float(number))
    except OverflowError:
        finite = False
    if not finite or (value != 0 and number == 0):
        raise ValueError("The exact number exceeds the finite canonical numeric representation.")
    return number, format(value, "f")


def _comparison_key(row):
    fields = ("platform", "account", "entity_type", "entity_id", "metric", "unit", "measurement_type",
              "time_grain", "source_timezone", "source_kind", "report_scope", "definition")
    if any(not _known(row.get(field)) for field in fields):
        raise ValueError("Comparison records require explicit nonempty string identity, source scope, timezone, metric basis and definition fields.")
    if "dimensions_json" not in row or "filters_json" not in row:
        raise ValueError("Comparison records require explicit staged dimensions_json and filters_json columns.")
    def canonical_json(value):
        parsed = json.loads(value or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("Comparison dimensions and filters must be JSON objects.")
        return json.dumps(parsed, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return tuple(_text(row.get(key)) for key in fields) + (
        canonical_json(row.get("dimensions_json")), canonical_json(row.get("filters_json")))


def _overlaps(records, existing_records, issues):
    def comparable_value(row):
        if row.get("status") != "observed":
            return None
        value = row.get("value_exact") or row.get("value")
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError("Comparison observed values must be finite.")
        return result
    groups = defaultdict(list)
    for old, rows in ((True, existing_records), (False, records)):
        for row in rows:
            if not isinstance(row, dict):
                _issue(issues, "error", "invalid_comparison_record", "Comparison records must be staged observation objects.")
                continue
            try:
                start, end = _iso(row.get("period_start")), _iso(row.get("period_end"))
                if start > end:
                    raise ValueError("Comparison period starts after its end.")
                key = _comparison_key(row)
                if row.get("status") not in STATUSES:
                    raise ValueError("Comparison records require a canonical observed/missing/suppressed/unavailable status.")
                if row["status"] != "observed" and any(row.get(field) is not None and _text(row.get(field)).strip()
                                                         for field in ("value", "value_exact")):
                    raise ValueError("Non-observed comparison records must have blank canonical numeric values.")
                comparable_value(row)
                groups[key].append((start, end, old, row))
            except (ValueError, TypeError, InvalidOperation) as exc:
                _issue(issues, "error", "invalid_comparison_record", str(exc), row.get("source_row", ""), row.get("metric", ""))
    pairs, duplicates = 0, set()
    for key, group in groups.items():
        ordered = sorted(group, key=lambda item: (item[0], item[1], item[2]))
        for position, left in enumerate(ordered):
            for right in ordered[position + 1:]:
                if right[0] > left[1]:
                    break
                if left[2] and right[2]:
                    continue
                pairs += 1
                current = right[3] if not right[2] else left[3]
                same_window = left[:2] == right[:2]
                same_capture = _text(left[3].get("captured_at")) == _text(right[3].get("captured_at"))
                same_values = (comparable_value(left[3]) == comparable_value(right[3]) and left[3].get("status") == right[3].get("status"))
                same_delivery = bool(left[3].get("source_sha256")) and left[3].get("source_sha256") == right[3].get("source_sha256")
                if same_window and same_capture and same_values:
                    duplicates.add((key, left[0], left[1], _text(current.get("captured_at"))))
                    code = "duplicate_observation" if current.get("captured_at") else "possible_duplicate_unknown_capture"
                    severity = "warning"
                elif same_window and same_capture and (current.get("captured_at") or same_delivery) and not same_values:
                    code, severity = "conflicting_same_capture", "error"
                else:
                    code, severity = "overlapping_snapshots_or_periods", "warning"
                _issue(issues, severity, code, "Same series has overlapping source periods; all observations remain separate and no aggregation or latest-value choice is performed.", current.get("source_row", ""), current.get("metric", ""))
    return len(duplicates), pairs


def preview_export(raw_bytes, filename, mapping, metadata, *, existing_records=()):
    if not isinstance(mapping, dict) or not isinstance(metadata, dict):
        raise ValueError("Mapping and metadata must be explicit JSON objects.")
    source, headers, rows, issues = _read(raw_bytes, filename, mapping.get("encoding", "utf-8-sig"),
                                            mapping.get("delimiter", ","), mapping.get("header_row", 1))
    records = []
    columns, dimensions, metrics = mapping.get("columns", {}), mapping.get("dimensions", {}), mapping.get("metrics", [])
    grain, pattern = mapping.get("time_grain"), mapping.get("date_format", "")
    number_format = mapping.get("number_format", "plain")
    config_errors = []
    if mapping.get("schema_version") != SCHEMA_VERSION:
        config_errors.append("Mapping schema_version must be 1.")
    if not isinstance(grain, str) or grain not in {"daily", "period"} or not isinstance(number_format, str) or number_format not in {"plain", "us_grouped"}:
        config_errors.append("Explicit daily/period time_grain and plain/us_grouped number_format are required.")
    if not isinstance(columns, dict) or not isinstance(dimensions, dict) or not isinstance(metrics, list) or not metrics:
        config_errors.append("columns/dimensions must be objects and metrics must be a nonempty list.")
        columns, dimensions, metrics = {}, {}, []
    if any(not isinstance(key, str) or not key.strip() or key.strip().casefold() == SCOPE_DIMENSION for key in dimensions):
        config_errors.append(f"Dimension names must be nonempty and may not use the reserved {SCOPE_DIMENSION} key.")
    if not isinstance(pattern, str) or not pattern:
        config_errors.append("date_format is required even when explicit metadata supplies period bounds.")
    if metadata.get("source_kind") != "artists_csv":
        config_errors.append("This preparation boundary accepts artists_csv only; provider API and Listening Now require separate source contracts.")
    for field in ("account", "entity_type", "report_scope"):
        if not _known(metadata.get(field)):
            config_errors.append(f"Explicit non-placeholder metadata.{field} is required.")
    if not columns.get("entity_id") and not _known(metadata.get("entity_id")):
        config_errors.append("Provide a literal entity_id column or explicit non-placeholder metadata.entity_id.")
    if grain == "daily" and not columns.get("date"):
        config_errors.append("Daily grain requires an explicitly mapped date column.")
    for boundary in ("period_start", "period_end"):
        if grain == "period" and not columns.get(boundary) and not metadata.get(boundary):
            config_errors.append(f"Period grain requires mapped {boundary} or explicit metadata.{boundary}.")
    if set(columns) - {"date", "period_start", "period_end", "entity_id", "entity_name"}:
        config_errors.append("Unknown canonical column mapping key.")
    if any(not isinstance(value, str) for value in columns.values()):
        config_errors.append("Column mappings must be literal header strings; omit optional fields instead of supplying other JSON types.")
    mapped = [value for value in columns.values() if value] + list(dimensions.values())
    seen_metrics = set()
    for spec in metrics:
        if not isinstance(spec, dict):
            config_errors.append("Each metric spec must be an object.")
            continue
        metric = spec.get("metric")
        if not isinstance(metric, str):
            config_errors.append("Metric IDs must be explicit canonical strings.")
            continue
        if metric not in METRIC_BASES or spec.get("measurement_basis") != METRIC_BASES.get(metric) or spec.get("unit") != "count":
            config_errors.append(f"Unsupported metric/basis/unit combination: {metric!r}.")
        if metric in seen_metrics:
            config_errors.append("Each canonical metric may be mapped only once.")
        seen_metrics.add(metric)
        if metric == "daily_unique_listeners" and grain != "daily":
            config_errors.append("daily_unique_listeners requires daily grain; period uniques and averages are different metrics.")
        if metric in {"period_unique_listeners", "average_daily_listeners"} and grain != "period":
            config_errors.append(f"{metric} requires explicit period grain.")
        if not _known(spec.get("definition")):
            config_errors.append("Every metric requires its explicitly reviewed definition.")
        mapped += [spec.get("column")]
        if spec.get("status_column"):
            mapped += [spec["status_column"]]
        for key in ("status_map", "value_tokens"):
            values = spec.get(key, {})
            if not isinstance(values, dict) or any(not isinstance(token, str) or not isinstance(status, str) or status not in STATUSES for token, status in values.items()):
                config_errors.append(f"{key} must map exact source strings to canonical statuses.")
    if any(not isinstance(column, str) or column not in headers for column in mapped):
        config_errors.append("Every mapped field must match an existing literal header exactly; no normalized lookup is used.")
    try:
        captured = _capture(metadata.get("captured_at", ""))
        zone = metadata.get("source_timezone") or "unknown"
        if zone != "unknown":
            ZoneInfo(zone)
        filters_json = json.dumps(metadata.get("filters", {}), sort_keys=True, ensure_ascii=False, allow_nan=False)
        if not isinstance(metadata.get("filters", {}), dict):
            raise ValueError("metadata.filters must be an object.")
    except (ValueError, TypeError, ZoneInfoNotFoundError) as exc:
        config_errors.append(str(exc))
        captured, zone, filters_json = "", "unknown", "{}"
    for error in config_errors:
        _issue(issues, "error", "invalid_mapping_or_metadata", error)
    if not captured:
        _issue(issues, "warning", "capture_time_unknown", "No capture time was supplied; source/file timestamps do not fill it.")
    if zone == "unknown":
        _issue(issues, "warning", "source_timezone_unknown", "The reporting timezone is unknown; UTC is not assumed.")
    if not config_errors and not any(item["severity"] == "error" for item in issues):
        for source_row, source_record, native in rows:
            for spec in metrics:
                metric = spec["metric"]
                try:
                    if grain == "daily":
                        start = end = _source_date(native[columns["date"]], pattern)
                    else:
                        start, end = [(_source_date(native[columns[key]], pattern) if columns.get(key) else _iso(metadata[key]))
                                      for key in ("period_start", "period_end")]
                    if start > end:
                        raise ValueError("Source period starts after its end.")
                    entity = native[columns["entity_id"]] if columns.get("entity_id") else metadata.get("entity_id", "")
                    if not _known(entity):
                        raise ValueError("Entity ID is blank or a placeholder; mapped blanks are not replaced.")
                    raw = native[spec["column"]]
                    status_raw = native[spec["status_column"]] if spec.get("status_column") else ""
                    if spec.get("status_column"):
                        if status_raw not in spec.get("status_map", {}):
                            raise ValueError("Source status is not explicitly mapped.")
                        status = spec["status_map"][status_raw]
                    else:
                        tokens = {"": "missing", **spec.get("value_tokens", {})}
                        status = tokens.get(raw.strip(), "observed")
                    if status == "observed":
                        value, exact = _number(raw, number_format, metric)
                        detail = "observed_zero" if value == 0 else "observed"
                    else:
                        if re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", raw.strip()):
                            raise ValueError("A numeric source value contradicts its explicitly non-observed status; the value was not silently discarded.")
                        value, exact = None, ""
                        detail = "missing_source_blank" if status == "missing" and not raw.strip() else status
                    dims = {key: native[column] for key, column in dimensions.items()}
                    # Keep source-family/report/filter ownership inside the
                    # canonical dimensions field, not only optional extras.
                    dims[SCOPE_DIMENSION] = dict(source_kind="artists_csv", report_scope=metadata["report_scope"],
                                                  filters=json.loads(filters_json))
                    row = {key: "" for key in COLUMNS}
                    row.update(platform="Apple Music", account=metadata["account"], entity_type=metadata["entity_type"],
                        entity_id=entity, entity_name=native[columns["entity_name"]] if columns.get("entity_name") else metadata.get("entity_name", ""),
                        metric=metric, value=value, unit="count", period_start=start, period_end=end, time_grain=grain,
                        measurement_type=spec["measurement_basis"], source_timezone=zone, captured_at=captured, status=status,
                        evidence_ref="raw/" + filename + "#record=" + str(source_record), dimensions_json=json.dumps(dims, sort_keys=True, ensure_ascii=False),
                        definition=spec["definition"], source_row=source_row, worksheet="", source_kind="artists_csv",
                        report_scope=metadata["report_scope"], filters_json=filters_json,
                        service="iTunes Store" if metric in {"song_purchases", "album_purchases"} else "Apple Music for Artists",
                        source_file=filename, source_sha256=source["sha256"], source_record=source_record,
                        source_field=spec["column"], source_value_raw=raw, source_status_raw=status_raw, value_status=detail,
                        value_exact=exact, source_url=metadata.get("source_url", ""), captured_at_raw=metadata.get("captured_at", ""),
                        native_record_json=json.dumps(native, ensure_ascii=False))
                    records.append(row)
                except (ValueError, TypeError, KeyError, OverflowError) as exc:
                    _issue(issues, "error", "invalid_source_observation", str(exc), source_row, metric)
    duplicates, overlaps = _overlaps(records, list(existing_records), issues)
    summary = dict(source_row_count=len(rows), record_count=len(records), error_count=sum(item["severity"] == "error" for item in issues),
        warning_count=sum(item["severity"] == "warning" for item in issues), observed_zero_count=sum(row["value_status"] == "observed_zero" for row in records),
        status_counts=dict(Counter(row["status"] for row in records)), duplicate_record_groups=duplicates, overlap_pairs=overlaps,
        metric_ids=sorted({row["metric"] for row in records}), no_aggregation=True)
    return dict(accepted=summary["error_count"] == 0 and bool(records), source=source, headers=headers, records=records,
                issues=issues, summary=summary)


def _csv(records, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    writer.writerows(records)
    return stream.getvalue().encode("utf-8")


def stage_preview(raw_bytes, filename, mapping, metadata, output_dir, *, existing_records=()):
    """Create a new review folder even for rejected data; never commit it."""
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError("Staging requires a new output directory; existing evidence is never overwritten.")
    for variable in ("LOCALAPPDATA", "APPDATA", "STATS_DATA_DIR"):
        value = os.environ.get(variable)
        if value and (destination == Path(value).expanduser().resolve() or destination.is_relative_to(Path(value).expanduser().resolve())):
            raise ValueError("Stage outside AppData and the configured live data directory.")
    preview = preview_export(raw_bytes, filename, mapping, metadata, existing_records=existing_records)
    files = dict(raw="raw/" + filename, mapping="config/mapping.json", metadata="config/metadata.json",
                 observations="normalized/observations.csv", issues="review/issues.csv", preview="preview.json")
    payloads = {files["raw"]: raw_bytes,
        files["mapping"]: (json.dumps(mapping, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"),
        files["metadata"]: (json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"),
        files["observations"]: _csv(preview["records"], OUTPUT_COLUMNS),
        files["issues"]: _csv(preview["issues"], ["severity", "code", "message", "source_row", "metric"]),
        files["preview"]: (json.dumps(preview, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")}
    destination.mkdir(parents=True, exist_ok=False)
    written = []
    for relative, raw in payloads.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
        if path.read_bytes() != raw:
            raise OSError("Staged evidence readback differs from its original payload.")
        written.append(dict(path=relative, sha256=_sha(raw), bytes=len(raw)))
    receipt = dict(accepted=preview["accepted"], output_dir=str(destination), source_sha256=preview["source"]["sha256"],
                   summary=preview["summary"], files=files, written_files=written, library_modified=False,
                   receipt_path=str(destination / "stage_receipt.json"))
    with (destination / "stage_receipt.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return receipt
