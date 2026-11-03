"""Stage explicitly mapped TikTok CSV evidence without a live import or GUI.

Source families, report scopes and ownership remain distinct. Content metadata
never supplies metric dates, and cumulative captures never become daily counts.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import json
import math
import os
from pathlib import Path
import re

from stats_app.apple_music import (
    _capture, _csv, _iso, _issue, _known, _read, _sha, _source_date, _text,
    inspect_csv as _inspect_csv,
)
from stats_app.validation import COLUMNS

SCHEMA_VERSION = 1
SCOPE_DIMENSION = "_tiktok_scope"
SOURCE_FAMILIES = {"studio_csv", "artists_csv", "business_suite_csv"}
COUNT_METRICS = {"video_views", "profile_views", "likes", "comments", "shares", "saves"}
SONG_METRICS = {"song_video_views", "song_video_posts"}
RATE_METRICS = {"completion_rate", "engagement_rate"}
CONTENT_FIELDS = ["caption", "caption_status", "publication_date", "published_local", "permalink", "sound_id",
                  "sound_title", "song_id", "song_title", "author_id"]
EXTRA_COLUMNS = ["source_family", "source_kind", "content_scope", "report_scope", "filters_json", "source_file",
    "source_sha256", "source_record", "source_field", "source_value_raw", "source_status_raw", "value_status",
    "value_exact", "source_url", "captured_at_raw", "canonical_import_eligible", "native_record_json",
    "caption", "caption_status_raw", "caption_availability", "publication_date", "publication_date_raw",
    "publication_date_status", "published_local", "permalink", "sound_id", "sound_title", "song_id", "song_title", "author_id"]
OUTPUT_COLUMNS = COLUMNS + EXTRA_COLUMNS
STATUSES = {"observed", "missing", "suppressed", "unavailable"}


def inspect_csv(raw_bytes, filename, *, encoding="utf-8-sig", delimiter=",", header_row=1):
    return _inspect_csv(raw_bytes, filename, encoding=encoding, delimiter=delimiter, header_row=header_row)


def _rule(metric, entity, grain, basis, unit):
    cumulative = grain == "snapshot"
    if metric in COUNT_METRICS | SONG_METRICS:
        expected = "cumulative_count" if cumulative else "period_count"
        return unit == "count" and basis == expected and (metric != "profile_views" or entity == "account")
    if metric == "net_followers":
        return entity == "account" and not cumulative and basis == "period_count" and unit == "count"
    if metric == "followers":
        return entity == "account" and basis == "point_in_time" and unit == "count"
    if metric == "unique_viewers":
        return basis == "distinct_count" and unit == "count"
    if metric == "total_watch_time":
        return basis == ("cumulative_sum" if cumulative else "period_sum") and unit in {"seconds", "minutes", "hours"}
    if metric == "average_watch_time":
        return basis == "average" and unit == "seconds"
    if metric in RATE_METRICS:
        return basis == "rate" and unit in {"percent", "ratio"}
    return False


def _number(raw, spec, number_format):
    token, unit, metric = raw.strip(), spec["unit"], spec["metric"]
    if token.endswith("%"):
        if unit != "percent" or spec.get("allow_percent_suffix") is not True:
            raise ValueError("A percent suffix requires explicit unit percent and allow_percent_suffix=true; no rescaling is inferred.")
        token = token[:-1].strip()
    sign = r"[+-]?" if metric == "net_followers" else r"[+]?"
    body = r"\d+(?:\.\d+)?" if number_format == "plain" else r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?"
    if not re.fullmatch(sign + body, token):
        raise ValueError("Use an exact number in the declared format; suffixes, durations, ranges and scientific notation are not inferred.")
    value = Decimal(token.replace(",", ""))
    if not value.is_finite() or (value < 0 and metric != "net_followers"):
        raise ValueError("Only net_followers may be negative; values must be finite.")
    if unit == "count" and value != value.to_integral_value():
        raise ValueError("Count metrics, including signed net followers, require integers.")
    if unit == "percent" and not Decimal(0) <= value <= Decimal(100):
        raise ValueError("Percent values must be within 0..100.")
    if unit == "ratio" and not Decimal(0) <= value <= Decimal(1):
        raise ValueError("Ratio values must be within 0..1.")
    result = int(value) if value == value.to_integral_value() else float(value)
    try:
        finite = math.isfinite(float(result))
    except OverflowError:
        finite = False
    if not finite or (value != 0 and result == 0):
        raise ValueError("The source number exceeds the finite canonical representation or underflows to zero.")
    return result, format(value, "f")


def _series(row):
    fields = ("platform", "account", "entity_type", "entity_id", "metric", "unit", "measurement_type", "time_grain",
              "source_timezone", "source_family", "content_scope", "report_scope", "definition")
    if any(not _known(row.get(field)) for field in fields):
        raise ValueError("Comparison rows require explicit staged identity, metric, source family, ownership, scope, timezone and definition.")
    parts = []
    for field in ("dimensions_json", "filters_json"):
        if field not in row:
            raise ValueError("Comparison rows require staged dimensions_json and filters_json fields.")
        value = json.loads(row[field])
        if not isinstance(value, dict):
            raise ValueError("Comparison dimensions/filters must be objects.")
        parts.append(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return tuple(row[field] for field in fields) + tuple(parts)


def _overlaps(records, existing, issues):
    groups, duplicate_keys, pairs = defaultdict(list), set(), 0
    for old, entries in ((True, existing), (False, records)):
        for row in entries:
            try:
                if not isinstance(row, dict):
                    raise ValueError("Comparison rows must be objects.")
                key = _series(row)
                start, end = _text(row.get("period_start")), _text(row.get("period_end"))
                if start:
                    _iso(start)
                if end:
                    _iso(end)
                if (not start or not end) and row["time_grain"] != "snapshot":
                    raise ValueError("Only explicit snapshots may have unknown comparison bounds.")
                if start and end and start > end:
                    raise ValueError("Comparison period starts after its end.")
                if row.get("status") not in STATUSES:
                    raise ValueError("Comparison rows require a canonical observed/missing/suppressed/unavailable status.")
                if row["status"] != "observed" and any(row.get(field) is not None and _text(row.get(field)).strip()
                                                          for field in ("value", "value_exact")):
                    raise ValueError("Non-observed comparison rows must have blank canonical numeric values.")
                value = Decimal(str(row.get("value_exact") or row.get("value"))) if row.get("status") == "observed" else None
                if value is not None and not value.is_finite():
                    raise ValueError("Comparison observed values must be finite.")
                groups[key].append((old, row, start, end, value))
            except (ValueError, TypeError, KeyError, InvalidOperation) as exc:
                _issue(issues, "error", "invalid_comparison_record", str(exc), row.get("source_row", "") if isinstance(row, dict) else "")
    for key, group in groups.items():
        for index, left in enumerate(group):
            for right in group[index + 1:]:
                if left[0] and right[0]:
                    continue
                if all((left[2], left[3], right[2], right[3])) and (left[3] < right[2] or right[3] < left[2]):
                    continue
                pairs += 1
                a, b = left[1], right[1]
                current = b if not right[0] else a
                same_window = left[2:4] == right[2:4]
                same_capture = a.get("captured_at", "") == b.get("captured_at", "")
                same_delivery = bool(a.get("source_sha256")) and a.get("source_sha256") == b.get("source_sha256")
                same_value = left[4] == right[4] and a.get("status") == b.get("status")
                if same_window and same_capture and same_value:
                    duplicate_keys.add((key, left[2], left[3], a.get("captured_at", "")))
                    code = "duplicate_observation" if current.get("captured_at") else "possible_duplicate_unknown_capture"
                    severity = "warning"
                elif same_window and same_capture and (current.get("captured_at") or same_delivery) and not same_value:
                    code, severity = "conflicting_same_capture", "error"
                else:
                    code, severity = "overlapping_snapshots_or_periods", "warning"
                _issue(issues, severity, code, "Same scoped series has overlapping or unknown metric coverage. All captures remain separate; no aggregation or latest-capture choice occurs.", current.get("source_row", ""), current["metric"])
    return len(duplicate_keys), pairs


def preview_export(raw_bytes, filename, mapping, metadata, *, existing_records=()):
    if not isinstance(mapping, dict) or not isinstance(metadata, dict):
        raise ValueError("Mapping and metadata must be JSON objects.")
    source, headers, rows, issues = _read(raw_bytes, filename, mapping.get("encoding", "utf-8-sig"), mapping.get("delimiter", ","), mapping.get("header_row", 1))
    columns, dimensions, metrics = mapping.get("columns", {}), mapping.get("dimensions", {}), mapping.get("metrics", [])
    grain, number_format = mapping.get("time_grain"), mapping.get("number_format", "plain")
    family, entity, ownership = metadata.get("source_family"), metadata.get("entity_type"), metadata.get("content_scope")
    errors, records = [], []
    if mapping.get("schema_version") != 1:
        errors.append("schema_version must be 1.")
    if not isinstance(grain, str) or grain not in {"daily", "period", "snapshot"}:
        errors.append("Explicit daily, period or snapshot time_grain is required.")
    if not isinstance(number_format, str) or number_format not in {"plain", "us_grouped"}:
        errors.append("number_format must be plain or us_grouped.")
    if not isinstance(columns, dict) or not isinstance(dimensions, dict) or not isinstance(metrics, list) or not metrics:
        errors.append("columns/dimensions must be objects and metrics a nonempty list; caption-only imports are not prepared as stats.")
        columns, dimensions, metrics = {}, {}, []
    allowed_columns = {"date", "period_start", "period_end", "entity_id", "entity_name", *CONTENT_FIELDS}
    if set(columns) - allowed_columns or any(not isinstance(value, str) for value in columns.values()):
        errors.append("Column keys must be supported canonical fields mapped to literal header strings.")
    if any(not isinstance(key, str) or not key.strip() or key.strip().casefold() == SCOPE_DIMENSION for key in dimensions):
        errors.append("Dimension names must be nonempty and may not shadow _tiktok_scope.")
    if not isinstance(family, str) or family not in SOURCE_FAMILIES or entity not in ("account", "video", "song"):
        errors.append("Explicit source_family and account/video/song entity_type are required.")
    if entity == "song":
        if family != "artists_csv" or ownership != "all_creators":
            errors.append("Song performance requires artists_csv and all_creators scope; it is not band-owned post performance.")
    elif ownership != "band_owned":
        errors.append("Account/video stats require explicit band_owned content_scope.")
    for key in ("account", "report_scope"):
        if not _known(metadata.get(key)):
            errors.append(f"Explicit non-placeholder string metadata.{key} is required.")
    if not columns.get("entity_id") and not _known(metadata.get("entity_id")):
        errors.append("An explicit entity_id column or non-placeholder fallback ID is required.")
    if grain == "daily" and not columns.get("date"):
        errors.append("Daily activity requires a mapped metric date; publication dates cannot substitute.")
    if grain == "period":
        for key in ("period_start", "period_end"):
            if not columns.get(key) and not metadata.get(key):
                errors.append(f"Period stats require explicit {key} from a mapped column or metadata.")
    pattern = mapping.get("date_format", "")
    if any(columns.get(key) for key in ("date", "period_start", "period_end")) and (not isinstance(pattern, str) or not pattern):
        errors.append("Mapped metric dates require explicit date_format.")
    mapped = [value for value in columns.values() if value] + list(dimensions.values())
    seen = set()
    for spec in metrics:
        if not isinstance(spec, dict) or not isinstance(spec.get("metric"), str):
            errors.append("Each metric spec requires an explicit canonical string metric ID.")
            continue
        metric, unit, basis = spec["metric"], spec.get("unit"), spec.get("measurement_basis")
        if metric in seen or not isinstance(unit, str) or not isinstance(basis, str) or not _rule(metric, entity, grain, basis, unit):
            errors.append(f"Unsupported or duplicate metric/basis/unit/grain combination: {metric}.")
        seen.add(metric)
        if (entity == "song") != (metric in SONG_METRICS):
            errors.append("Song/all-creator metrics must use song_video_views or song_video_posts and stay separate from account/video stats.")
        if not _known(spec.get("definition")):
            errors.append("Every metric requires its explicitly reviewed native definition.")
        if not isinstance(spec.get("allow_percent_suffix", False), bool):
            errors.append("allow_percent_suffix must be an explicit boolean.")
        mapped.append(spec.get("column"))
        if spec.get("status_column"):
            mapped.append(spec["status_column"])
        for key in ("status_map", "value_tokens"):
            values = spec.get(key, {})
            if not isinstance(values, dict) or any(not isinstance(token, str) or not isinstance(status, str) or status not in STATUSES for token, status in values.items()):
                errors.append(f"{key} must map exact source strings to canonical statuses.")
    if any(not isinstance(value, str) or value not in headers for value in mapped):
        errors.append("Every mapped column must match a literal native header; no header or profile is guessed.")
    try:
        captured = _capture(metadata.get("captured_at", ""))
        zone = metadata.get("source_timezone") or "unknown"
        if not isinstance(zone, str):
            raise ValueError("source_timezone must be a string or unknown.")
        if zone != "unknown":
            from zoneinfo import ZoneInfo
            ZoneInfo(zone)
        if not isinstance(metadata.get("filters", {}), dict):
            raise ValueError("metadata.filters must be an object.")
        filters_json = json.dumps(metadata.get("filters", {}), sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, KeyError) as exc:
        errors.append(str(exc))
        captured, zone, filters_json = "", "unknown", "{}"
    for error in errors:
        _issue(issues, "error", "invalid_mapping_or_metadata", error)
    if not captured:
        _issue(issues, "warning", "capture_time_unknown", "No capture time supplied; no timestamp or chronology is inferred.")
    if zone == "unknown":
        _issue(issues, "warning", "source_timezone_unknown", "Reporting timezone remains unknown; UTC is not assumed.")
    if not any(item["severity"] == "error" for item in issues):
        for source_row, source_record, native in rows:
            for spec in metrics:
                metric = spec["metric"]
                try:
                    if grain == "daily":
                        start = end = _source_date(native[columns["date"]], pattern)
                    else:
                        bounds = []
                        for key in ("period_start", "period_end"):
                            raw_bound = native[columns[key]] if columns.get(key) else metadata.get(key, "")
                            if not raw_bound and grain == "snapshot":
                                bounds.append("")
                            else:
                                bounds.append(_source_date(raw_bound, pattern) if columns.get(key) else _iso(raw_bound))
                        start, end = bounds
                    if start and end and start > end:
                        raise ValueError("Metric coverage starts after it ends.")
                    if metric == "followers" and start and end and start != end:
                        raise ValueError("Follower stock is point-in-time, not a multi-day activity total.")
                    identifier = native[columns["entity_id"]] if columns.get("entity_id") else metadata.get("entity_id", "")
                    if not _known(identifier):
                        raise ValueError("Entity ID is blank/placeholder; mapped blanks are not replaced.")
                    raw = native[spec["column"]]
                    status_raw = native[spec["status_column"]] if spec.get("status_column") else ""
                    if spec.get("status_column"):
                        if status_raw not in spec.get("status_map", {}):
                            raise ValueError("Native status is not explicitly mapped.")
                        status = spec["status_map"][status_raw]
                    else:
                        status = {"": "missing", **spec.get("value_tokens", {})}.get(raw.strip(), "observed")
                    if status == "observed":
                        value, exact = _number(raw, spec, number_format)
                        detail = "observed_zero" if value == 0 else "observed"
                    else:
                        if re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?%?", raw.strip()):
                            raise ValueError("A numeric native value contradicts its non-observed status; it was not silently discarded.")
                        value, exact = None, ""
                        detail = "missing_source_blank" if status == "missing" and not raw.strip() else status
                    dims = {key: native[column] for key, column in dimensions.items()}
                    dims[SCOPE_DIMENSION] = dict(source_family=family, content_scope=ownership, report_scope=metadata["report_scope"], filters=json.loads(filters_json))
                    content = {key: native[columns[key]] if columns.get(key) else "" for key in CONTENT_FIELDS}
                    pub_raw, pub_date = content["publication_date"], ""
                    pub_status = "not_supplied" if not columns.get("publication_date") else "missing_source_blank" if not pub_raw else "unparsed_source_label"
                    if pub_raw and mapping.get("publication_date_format"):
                        try:
                            pub_date = _source_date(pub_raw, mapping["publication_date_format"])
                            pub_status = "observed_source_date"
                        except (ValueError, TypeError) as exc:
                            _issue(issues, "warning", "publication_label_unparsed", str(exc), source_row, metric)
                    row = {key: "" for key in COLUMNS}
                    row.update(platform="TikTok for Artists" if family == "artists_csv" else "TikTok", account=metadata["account"], entity_type=entity,
                        entity_id=identifier, entity_name=native[columns["entity_name"]] if columns.get("entity_name") else metadata.get("entity_name", ""),
                        metric=metric, value=value, unit=spec["unit"], period_start=start, period_end=end, time_grain=grain,
                        measurement_type=spec["measurement_basis"], source_timezone=zone, captured_at=captured, status=status,
                        evidence_ref=f"raw/{filename}#record={source_record}", dimensions_json=json.dumps(dims, sort_keys=True, ensure_ascii=False),
                        definition=spec["definition"], source_row=source_row, worksheet="", source_family=family, source_kind=family,
                        content_scope=ownership, report_scope=metadata["report_scope"], filters_json=filters_json,
                        source_file=filename, source_sha256=source["sha256"], source_record=source_record, source_field=spec["column"],
                        source_value_raw=raw, source_status_raw=status_raw, value_status=detail, value_exact=exact,
                        source_url=metadata.get("source_url", ""), captured_at_raw=metadata.get("captured_at", ""),
                        canonical_import_eligible=bool(start and end), native_record_json=json.dumps(native, ensure_ascii=False),
                        caption=content["caption"], caption_status_raw=content["caption_status"],
                        caption_availability="not_supplied" if not columns.get("caption") else "missing_source_blank" if not content["caption"].strip() else "source_text_available",
                        publication_date=pub_date, publication_date_raw=pub_raw, publication_date_status=pub_status,
                        **{key: content[key] for key in ("published_local", "permalink", "sound_id", "sound_title", "song_id", "song_title", "author_id")})
                    records.append(row)
                except (ValueError, TypeError, KeyError, InvalidOperation, OverflowError) as exc:
                    _issue(issues, "error", "invalid_source_observation", str(exc), source_row, metric)
    duplicates, overlaps = _overlaps(records, list(existing_records), issues)
    error_count = sum(item["severity"] == "error" for item in issues)
    accepted = bool(records) and not error_count
    canonical = accepted and all(row["canonical_import_eligible"] for row in records)
    if records and not all(row["canonical_import_eligible"] for row in records):
        _issue(issues, "warning", "snapshot_bounds_unknown_review_only", "Unknown snapshot metric bounds are retained honestly; these rows are not eligible for generic canonical import.")
    summary = dict(source_row_count=len(rows), record_count=len(records), error_count=error_count,
        warning_count=sum(item["severity"] == "warning" for item in issues), observed_zero_count=sum(row["value_status"] == "observed_zero" for row in records),
        status_counts=dict(Counter(row["status"] for row in records)), metric_ids=sorted({row["metric"] for row in records}),
        duplicate_record_groups=duplicates, overlap_pairs=overlaps, no_aggregation=True, canonical_import_eligible=canonical)
    return dict(accepted=accepted, canonical_import_eligible=canonical, source=source, headers=headers, records=records, issues=issues, summary=summary)


def stage_preview(raw_bytes, filename, mapping, metadata, output_dir, *, existing_records=()):
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError("Staging requires a new output directory; prior evidence is never overwritten.")
    for variable in ("LOCALAPPDATA", "APPDATA", "STATS_DATA_DIR"):
        value = os.environ.get(variable)
        if value and destination.is_relative_to(Path(value).expanduser().resolve()):
            raise ValueError("Stage outside AppData and the configured live library.")
    preview = preview_export(raw_bytes, filename, mapping, metadata, existing_records=existing_records)
    files = dict(raw="raw/" + filename, mapping="config/mapping.json", metadata="config/metadata.json",
                 observations="normalized/observations.csv", issues="review/issues.csv", preview="preview.json")
    def encoded(value):
        return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    payloads = {files["raw"]: raw_bytes, files["mapping"]: encoded(mapping), files["metadata"]: encoded(metadata),
        files["observations"]: _csv(preview["records"], OUTPUT_COLUMNS),
        files["issues"]: _csv(preview["issues"], ["severity", "code", "message", "source_row", "metric"]), files["preview"]: encoded(preview)}
    destination.mkdir(parents=True, exist_ok=False)
    written = []
    for relative, raw in payloads.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
        if path.read_bytes() != raw:
            raise OSError("Staged evidence readback differs from its source payload.")
        written.append(dict(path=relative, sha256=_sha(raw), bytes=len(raw)))
    receipt = dict(accepted=preview["accepted"], canonical_import_eligible=preview["canonical_import_eligible"], output_dir=str(destination),
        source_sha256=preview["source"]["sha256"], summary=preview["summary"], files=files, written_files=written,
        library_modified=False, receipt_path=str(destination / "stage_receipt.json"))
    with (destination / "stage_receipt.json").open("xb") as stream:
        stream.write(encoded(receipt))
    return receipt
