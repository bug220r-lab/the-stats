"""Export-first readers. Raw bytes are read only; persistence belongs to storage."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from .validation import COLUMNS, iso_date, numeric_value, text_value

PROFILES = {"canonical": "Canonical / mapped CSV or Excel", "spotify_daily": "Spotify daily timeline", "meta_daily": "Meta daily export"}
SPOTIFY_METRICS = {
    "streams": ("period_count", "Number of Spotify streams in this UTC day."),
    "saves": ("period_count", "Spotify save activity in this UTC day; not distinct people."),
    "playlist adds": ("period_count", "Spotify playlist additions in this UTC day."),
    "listeners": ("distinct_count", "Unique Spotify listeners in this UTC day; do not sum into period listeners."),
    "followers": ("point_in_time", "Follower balance at the daily endpoint; not gross new followers."),
    "monthly listeners": ("rolling_count", "Rolling 28-day unique listeners at this endpoint; not additive."),
    "monthly active listeners": ("rolling_count", "Rolling 28-day active listeners at this endpoint; not additive."),
    "super listeners": ("rolling_count", "Rolling 28-day super listener segment at this endpoint; not additive."),
}


def _normalized_columns(headers) -> dict:
    """Reject ambiguous labels before building a normalized column lookup."""
    columns = {}
    for header in headers:
        key = "" if header is None else str(header).strip().casefold()
        if not key:
            raise ValueError("Headers must be nonempty and unique.")
        if key in columns:
            raise ValueError(
                "Duplicate headers after trimming whitespace and ignoring case: "
                f"{columns[key]!r} and {header!r}; correct them in a separate working copy."
            )
        columns[key] = header
    return columns


def sheet_names(raw_bytes: bytes) -> list[str]:
    return pd.ExcelFile(io.BytesIO(raw_bytes), engine="openpyxl").sheet_names


def read_table(raw_bytes: bytes, filename: str, worksheet: str | None = None) -> pd.DataFrame:
    """Read a rectangular CSV/TSV/XLSX, preserving IDs and source row references.

    Meta UTF-16 exports can have a title/preamble before their Date header.
    Multisection and ragged exports are rejected instead of dropping their rows.
    """
    suffix = Path(filename).suffix.lower()
    if suffix == ".xlsx":
        names = sheet_names(raw_bytes)
        selected = worksheet or names[0]
        if selected not in names:
            raise ValueError(f"Worksheet {selected!r} does not exist.")
        # Inspect actual headers before pandas can silently mangle duplicates.
        import openpyxl
        workbook = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
        headers = next(workbook[selected].iter_rows(values_only=True), ())
        workbook.close()
        _normalized_columns(headers)
        df = pd.read_excel(io.BytesIO(raw_bytes), sheet_name=selected, dtype=object, keep_default_na=False, engine="openpyxl")
        for column in df.columns:
            df[column] = df[column].map(lambda value: value.date().isoformat() if isinstance(value, datetime) and value.time().isoformat() == "00:00:00" else str(value) if value is not None else "")
        df.attrs.update(source_rows=list(range(2, len(df) + 2)), worksheet=selected, header_row=1)
        return df
    if suffix not in {".csv", ".tsv"}:
        raise ValueError("Select a CSV, TSV, or XLSX file; ZIP packages must be extracted first.")
    try:
        text = raw_bytes.decode("utf-16" if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("File encoding is not UTF-8 or BOM-marked UTF-16; save a separate UTF-8 CSV copy.") from exc
    delimiter = "\t" if suffix == ".tsv" else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = []
    for row in reader:
        rows.append((reader.line_num, row))
    nonempty = [(line, row) for line, row in rows if any(cell.strip() for cell in row)]
    if not nonempty:
        raise ValueError("The file is empty.")
    header_index = 0
    # A rectangular first header is authoritative: Day/Date can be ordinary
    # IDs or titles in its body. The retained Meta layout has one title cell
    # immediately followed by a named daily header, not an arbitrary prefix.
    if len(nonempty[0][1]) == 1 and any(len(row) > 1 for _, row in nonempty[1:]):
        candidate = nonempty[1][1]
        daily_header = (len(candidate) > 1 and candidate[0].strip().casefold() in {"date", "day"}
                        and all(cell.strip() and pd.isna(pd.to_numeric(cell, errors="coerce"))
                                for cell in candidate[1:]))
        if not daily_header:
            raise ValueError("Ambiguous CSV preamble; use a separate rectangular working copy without changing the original.")
        header_index = 1
    header_line, header = nonempty[header_index]
    header = [cell.strip() for cell in header]
    _normalized_columns(header)
    body, source_rows = [], []
    for line, row in nonempty[header_index + 1:]:
        if len(row) != len(header):
            raise ValueError(f"Source row {line}: expected {len(header)} fields, found {len(row)}; no rows imported.")
        if row == header:
            raise ValueError(f"Source row {line}: repeated header or multiple sections require separate imports.")
        body.append(row)
        source_rows.append(line)
    df = pd.DataFrame(body, columns=header)
    df.attrs.update(source_rows=source_rows, worksheet="", header_row=header_line)
    return df


def detect_profile(df: pd.DataFrame) -> str:
    columns = set(_normalized_columns(df.columns))
    if {"metric", "value"} <= columns:
        return "canonical"
    if "date" in columns and columns.intersection(SPOTIFY_METRICS):
        return "spotify_daily"
    return "canonical"


def _base(metadata: dict, row_number: int, worksheet: str) -> dict:
    result = {column: metadata.get(column, "") for column in COLUMNS}
    result.update(value=None, source_row=row_number, worksheet=worksheet, dimensions_json=metadata.get("dimensions_json") or "{}")
    return result


def parse_export(df: pd.DataFrame, profile: str, metadata: dict, mapping: dict | None = None) -> pd.DataFrame:
    """Normalize a preview. Mapping is canonical-field -> source-column.

    Required source identity is supplied as explicit metadata, never guessed from
    filenames. Canonical rows override metadata. Raises before commit on malformed
    data. validate_records provides the required-field/status check.
    """
    if profile not in PROFILES:
        raise ValueError(f"Unknown import profile: {profile}")
    mapping = mapping or {}
    source_rows = df.attrs.get("source_rows", list(range(2, len(df) + 2)))
    worksheet = df.attrs.get("worksheet", "")
    columns = _normalized_columns(df.columns)
    result = []
    for position, (_, source) in enumerate(df.iterrows()):
        row_number = source_rows[position]
        try:
            if profile == "canonical":
                record = _base(metadata, row_number, worksheet)
                for field in COLUMNS:
                    column = mapping.get(field, columns.get(field))
                    if column is not None and column != "":
                        if column not in df.columns:
                            raise ValueError(f"Mapped column {column!r} does not exist.")
                        record[field] = source[column]
                raw = record["value"]
                record["value"], inferred_status = numeric_value(raw)
                record["status"] = text_value(record["status"]) or inferred_status
                if text_value(raw).endswith("%") and text_value(record["unit"]) not in {"percent", "percentage_points"}:
                    raise ValueError("Percent-marked values require unit percent; fractions are not inferred.")
                record["period_start"] = iso_date(record["period_start"])
                record["period_end"] = iso_date(record["period_end"])
                record["dimensions_json"] = text_value(record["dimensions_json"]) or "{}"
                # Source provenance cannot be reassigned by a mapped data cell.
                record["source_row"], record["worksheet"] = row_number, worksheet
                result.append(record)
                continue
            date_column = mapping.get("date") or columns.get("date") or columns.get("day")
            if date_column not in df.columns:
                raise ValueError("A Date/Day column is required.")
            day = iso_date(source[date_column])
            if profile == "spotify_daily":
                metric_columns = [(key, column) for key, column in columns.items() if key in SPOTIFY_METRICS]
                unknown = set(columns) - set(SPOTIFY_METRICS) - {"date", "day"}
                if unknown:
                    raise ValueError("Unrecognized Spotify columns: " + ", ".join(sorted(unknown)) + "; use canonical mapping.")
            else:
                # A single observed Meta metric per import avoids treating report
                # titles such as Instagram Views as a platform-scope guarantee.
                value_column = mapping.get("value") or metadata.get("value_column")
                if not value_column:
                    candidates = [c for c in df.columns if c != date_column]
                    if len(candidates) != 1:
                        raise ValueError("Choose one Meta value column explicitly.")
                    value_column = candidates[0]
                metric_columns = [(text_value(metadata.get("metric")), value_column)]
                if not metric_columns[0][0]:
                    raise ValueError("Provide the actual Meta metric name and measurement scope.")
            if not metric_columns:
                raise ValueError("No supported metric columns were found.")
            for metric, column in metric_columns:
                record = _base(metadata, row_number, worksheet)
                record.update(period_start=day, period_end=day, time_grain="daily", metric=metric.replace(" ", "_"))
                if profile == "spotify_daily":
                    measure, definition = SPOTIFY_METRICS[metric]
                    record.update(platform="Spotify", unit="count", measurement_type=measure, definition=definition)
                    if measure == "rolling_count":
                        record["period_start"] = (date.fromisoformat(day) - timedelta(days=27)).isoformat()
                record["value"], record["status"] = numeric_value(source[column])
                if text_value(source[column]).endswith("%") and text_value(record["unit"]) not in {"percent", "percentage_points"}:
                    raise ValueError("Percent-marked values require unit percent; fractions are not inferred.")
                result.append(record)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"Source row {row_number}: {exc}") from exc
    return pd.DataFrame(result, columns=COLUMNS)
