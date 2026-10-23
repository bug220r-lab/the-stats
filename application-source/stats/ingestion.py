"""CSV/XLSX parsing. Preview is pure; persistence only occurs on explicit commit."""
from __future__ import annotations

import hashlib
import io
import json
import math
from numbers import Real
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from stats.metrics import METRICS

PLATFORMS = ["spotify", "facebook", "instagram", "tiktok", "tiktok_artists"]
FIELDS = ["platform", "account_id", "account_name", "entity_type", "entity_id", "entity_name",
          "metric", "value", "unit", "definition", "dimensions", "period_start", "period_end",
          "time_grain", "captured_at", "source_timezone", "measurement_type", "status",
          "source_row", "evidence_ref", "published_at", "source_url"]
ALIASES = {
    "date": "period_start", "day": "period_start", "start date": "period_start",
    "end date": "period_end", "track uri": "entity_id", "spotify uri": "entity_id",
    "track id": "entity_id", "post id": "entity_id", "video id": "entity_id",
    "song id": "entity_id", "release id": "entity_id", "recording label": "entity_name",
    "release title": "entity_name", "collected at": "captured_at",
    "track name": "entity_name", "song": "entity_name", "title": "entity_name",
    "caption": "entity_name", "account": "account_name", "artist": "account_name",
    "publish date": "published_at", "permalink": "source_url",
}
METRIC_ALIASES = {
    "streams": "streams", "listeners": "listeners", "monthly listeners": "monthly_listeners",
    "monthly active listeners": "monthly_active_listeners", "super listeners": "super_listeners",
    "followers": "followers", "saves": "saves", "playlist adds": "playlist_adds",
    "playlist additions": "playlist_adds", "reach": "reach", "impressions": "impressions",
    "views": "views", "video views": "views", "likes": "likes", "comments": "comments",
    "shares": "shares", "profile visits": "profile_visits", "link clicks": "link_clicks",
    "engagements": "engagements", "watch time": "watch_time", "spend": "spend",
}

SPOTIFY_ARTIST_DAILY_COLUMNS = {
    "date", "listeners", "monthly listeners", "monthly active listeners", "super listeners",
    "streams", "playlist adds", "saves", "followers",
}


def _column_name(value):
    return re.sub(r"[_\s]+", " ", str(value).strip().lower())


def clean(value):
    if value is None or (not isinstance(value, (dict, list)) and pd.isna(value)):
        return ""
    return str(value).strip()


def worksheets(raw: bytes, filename: str) -> list[str]:
    if filename.lower().endswith(".xlsx"):
        return pd.ExcelFile(io.BytesIO(raw), engine="openpyxl").sheet_names
    if not filename.lower().endswith(".csv"):
        raise ValueError("Choose a CSV or XLSX file.")
    return ["CSV"]


def read_table(raw: bytes, filename: str, worksheet="CSV", header_row=1) -> pd.DataFrame:
    if not 1 <= int(header_row) <= 100:
        raise ValueError("Header row must be between 1 and 100.")
    if filename.lower().endswith(".xlsx"):
        frame = pd.read_excel(io.BytesIO(raw), sheet_name=worksheet, header=header_row - 1,
                              dtype=object, engine="openpyxl", keep_default_na=False)
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        try:
            sheet = workbook[worksheet]
            for row_position, cells in enumerate(sheet.iter_rows(min_row=header_row + 1, max_row=header_row + len(frame), max_col=len(frame.columns))):
                for column_position, cell in enumerate(cells):
                    # Excel stores 25% as 0.25 with a percent number format.
                    # Retain that unit signal so ratio and percent mappings both
                    # receive their correct numeric interpretation.
                    if isinstance(cell.value, Real) and "%" in cell.number_format:
                        frame.iat[row_position, column_position] = f"{float(cell.value) * 100:.12g}%"
        finally:
            workbook.close()
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("utf-16")
        frame = pd.read_csv(io.StringIO(text), sep=None, engine="python", header=header_row - 1,
                            dtype=str, keep_default_na=False, skip_blank_lines=False)
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


def suggest_mapping(frame: pd.DataFrame, source_metadata: dict | None = None) -> dict:
    fields, metrics = {}, {}
    for column in frame.columns:
        norm = _column_name(column)
        canonical = norm.replace(" ", "_")
        if canonical in FIELDS:
            fields[canonical] = column
        elif norm in ALIASES:
            fields[ALIASES[norm]] = column
        if norm in METRIC_ALIASES:
            metrics[column] = METRIC_ALIASES[norm]
    defaults = dict(source_metadata or {})
    mapping = {"fields": fields, "metrics": metrics, "defaults": defaults, "numeric_locale": "en_US", "date_format": "ISO"}
    if SPOTIFY_ARTIST_DAILY_COLUMNS.issubset({_column_name(c) for c in frame.columns}):
        mapping["detected_format"] = "spotify_artist_daily"
        if defaults.get("platform") == "spotify" and defaults.get("account_id") and defaults.get("entity_type") == "artist":
            defaults.setdefault("time_grain", "daily")
    return mapping


def parse_number(value, locale="en_US"):
    """Return (value, status, was_percent). Never convert absence to zero."""
    if isinstance(value, Real) and not isinstance(value, bool):
        if pd.isna(value):
            return None, "missing", False
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Number must be finite")
        return number, "available", False
    if locale not in {"en_US", "de_DE"}:
        raise ValueError("Choose numeric_locale en_US (decimal point) or de_DE (decimal comma).")
    text = clean(value)
    if text.lower() in {"", "n/a", "na", "null", "none", "nan", "—", "-", ".."}:
        return None, "missing", False
    if text.startswith(("<", ">")) or text.lower() in {"suppressed", "redacted", "privacy threshold", "*"}:
        return None, "suppressed", False
    percent = text.endswith("%")
    text = text.removesuffix("%").replace("\u00a0", "").replace(" ", "")
    if locale == "de_DE":
        if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?", text):
            raise ValueError("Invalid decimal-comma number")
        text = text.replace(".", "").replace(",", ".")
    else:
        if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", text):
            raise ValueError("Invalid decimal-point number")
        text = text.replace(",", "")
    number = float(text)
    if not math.isfinite(number):
        raise ValueError("Number must be finite")
    return number, "available", percent


def parse_date(value, date_format="ISO"):
    if not clean(value):
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    value = clean(value)
    formats = {"ISO": "%Y-%m-%d", "MDY": "%m/%d/%Y", "DMY": "%d/%m/%Y"}
    return datetime.strptime(value, formats[date_format]).date().isoformat()


def preview_import(frame, mapping, filename, raw, worksheet="CSV", header_row=1):
    observations, issues = [], []
    if not isinstance(mapping, dict) or any(not isinstance(mapping.get(key, {}), dict) for key in ("fields", "metrics", "defaults")):
        raise ValueError("Mapping must be an object with fields, metrics and defaults objects.")
    fields = mapping.get("fields", {})
    defaults = mapping.get("defaults", {})
    locale, date_format = mapping.get("numeric_locale", "en_US"), mapping.get("date_format", "ISO")
    for name in list(fields.values()) + list(mapping.get("metrics", {})):
        if name not in frame.columns:
            raise ValueError(f"Mapped column {name!r} is not present. Correct the mapping.")
    file_hash = hashlib.sha256(raw).hexdigest()
    native_artist_daily = SPOTIFY_ARTIST_DAILY_COLUMNS.issubset({_column_name(c) for c in frame.columns})
    for position, (_, row) in enumerate(frame.iterrows()):
        source_row = position + int(header_row) + 1
        if all(clean(v) == "" for v in row):
            continue
        base = {key: row[column] for key, column in fields.items() if key not in {"metric", "value"}}
        base = {**defaults, **{k: v for k, v in base.items() if clean(v)}}
        if native_artist_daily and base.get("platform") == "spotify" and base.get("account_id") and base.get("entity_type") == "artist":
            base.setdefault("time_grain", "daily")
        base.setdefault("source_row", source_row)
        base.setdefault("evidence_ref", f"{filename}#{worksheet}!row={source_row}")
        metric_values = [(metric, row[column]) for column, metric in mapping.get("metrics", {}).items()]
        if fields.get("metric") and fields.get("value"):
            metric_values = [(clean(row[fields["metric"]]), row[fields["value"]])]
        if not metric_values:
            issues.append({"source_row": source_row, "severity": "error", "message": "Map a metric/value pair or at least one metric column."})
        for metric, raw_value in metric_values:
            try:
                obs = {key: clean(value) for key, value in base.items()}
                obs["metric"] = metric
                if obs.get("platform") not in PLATFORMS:
                    raise ValueError("Platform required: spotify, facebook, instagram, tiktok or tiktok_artists")
                if not obs.get("account_id"):
                    raise ValueError("Account ID or explicit source-scoped account key required")
                if not obs.get("entity_type"):
                    raise ValueError("Entity type required")
                if not obs.get("entity_id"):
                    if obs["entity_type"] in {"artist", "account"}:
                        obs["entity_id"] = obs["account_id"]
                    elif obs.get("entity_name"):
                        scope = clean(defaults.get("identity_scope")) or file_hash
                        # Repeated names can refer to different recordings/posts.
                        # Only a supplied stable ID can join distinct source rows.
                        scoped_row = f"{scope}|{worksheet}|{source_row}|{obs['entity_type']}"
                        obs["entity_id"] = "source:" + hashlib.sha256(scoped_row.encode()).hexdigest()[:24]
                        issues.append({"source_row": source_row, "severity": "warning", "code": "source_scoped_identity",
                                       "message": "Entity ID is missing. A source-row identity was retained; supply an explicit stable ID to join this entity across rows/files."})
                    else:
                        raise ValueError("Entity ID or source-scoped name required")
                spec = METRICS.get(metric, {})
                obs.setdefault("unit", spec.get("unit", ""))
                obs.setdefault("definition", spec.get("definition", ""))
                obs.setdefault("measurement_type", spec.get("measurement_type", ""))
                for key in ("unit", "definition", "measurement_type", "time_grain"):
                    if not obs.get(key):
                        raise ValueError(f"{key} is required for {metric}")
                start = parse_date(base.get("period_start"), date_format)
                end = parse_date(base.get("period_end"), date_format)
                if not end and obs.get("time_grain") == "daily":
                    end = start
                if not start or not end or start > end:
                    raise ValueError("Valid reporting-period start and end required")
                obs.update(period_start=start, period_end=end)
                if obs.get("time_grain") == "daily" and start != end:
                    raise ValueError("Daily observations must use a single date bucket")
                number, status, percent = parse_number(raw_value, locale)
                if number is not None and number < 0 and metric not in {"net_followers", "net_likes"}:
                    raise ValueError("Negative count requires an explicitly defined net-change metric")
                if percent:
                    if obs["unit"] in {"ratio", "fraction"}:
                        number /= 100
                    elif obs["unit"] not in {"percent", "%"}:
                        raise ValueError("Percentage value needs percent or ratio unit")
                dims = base.get("dimensions", "{}") or "{}"
                if isinstance(dims, str):
                    dims = json.loads(dims)
                if not isinstance(dims, dict):
                    raise ValueError("Dimensions must be a JSON object")
                obs["dimensions"] = json.dumps(dims, sort_keys=True)
                # Source verification/availability labels are evidence, not a
                # by-product of number parsing. A missing value remains None.
                obs.update(value=number, status=obs.get("status") or status)
                if number is None and obs["status"] not in {"missing", "suppressed", "unavailable"}:
                    issues.append({"source_row": source_row, "metric": metric, "severity": "warning",
                                   "code": "missing_value", "message": f"Value is {status}; source status {obs['status']!r} was preserved."})
                for key in ("captured_at", "published_at"):
                    if obs.get(key):
                        # Validate without adding time or timezone to a date-only capture.
                        datetime.fromisoformat(obs[key].replace("Z", "+00:00"))
                observations.append({k: obs.get(k) for k in FIELDS})
            except (ValueError, TypeError, KeyError) as exc:
                issues.append({"source_row": source_row, "metric": metric, "severity": "error", "message": str(exc), "raw_value": clean(raw_value)})
    if observations and any(not x.get("captured_at") for x in observations):
        issues.append({"severity": "warning", "message": "Capture/as-of date is unknown for some rows; import time will stay separate."})
    if observations and any(not x.get("source_timezone") for x in observations):
        issues.append({"severity": "warning", "message": "Source timezone is unknown for some rows. Date buckets are preserved unchanged."})
    keys = ["platform", "account_id", "entity_type", "entity_id", "metric", "period_start", "period_end", "dimensions", "unit", "definition", "measurement_type", "time_grain", "source_timezone"]
    seen = {}
    for observation in observations:
        key = tuple(observation.get(k) for k in keys)
        if key in seen:
            conflict = seen[key] != (observation["value"], observation["status"])
            issues.append({"source_row": observation["source_row"], "severity": "error" if conflict else "warning", "message": "Conflicting rows in this import; resolve before committing." if conflict else "Duplicate observation within file; storage will retain provenance without adding totals."})
        seen[key] = (observation["value"], observation["status"])
    return {"observations": observations, "issues": issues, "file_hash": file_hash,
            "platforms": sorted({x["platform"] for x in observations}),
            "accounts": sorted({x["account_id"] for x in observations}),
            "period_start": min((x["period_start"] for x in observations), default=None),
            "period_end": max((x["period_end"] for x in observations), default=None)}


def folder_files(folder):
    path = Path(folder).expanduser().resolve()
    if not path.is_dir():
        raise ValueError("Folder does not exist")
    return sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in {".csv", ".xlsx"})


def safe_csv(frame):
    """Neutralize formula injection in spreadsheet downloads, retaining numbers."""
    out = frame.copy()
    for column in out.columns:
        out[column] = out[column].map(lambda x: "'" + x if isinstance(x, str) and x.startswith(("=", "+", "-", "@")) else x)
    return out.to_csv(index=False).encode("utf-8-sig")
