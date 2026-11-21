"""Validation rules shared by ingestion and persistence. Missing is never zero."""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd

COLUMNS = ["platform", "account", "entity_type", "entity_id", "entity_name", "metric", "value", "unit", "period_start", "period_end", "time_grain", "measurement_type", "source_timezone", "captured_at", "status", "evidence_ref", "dimensions_json", "definition", "source_row", "worksheet"]
REQUIRED = ["platform", "account", "entity_type", "entity_id", "metric", "unit", "period_start", "period_end", "time_grain", "measurement_type", "status"]
STATUSES = {"observed", "missing", "suppressed", "unavailable"}


def text_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def finite_number(value: Any) -> float:
    """Convert only when a source number survives the REAL storage boundary.

    Integers must remain exact. Decimal inputs may use the usual shortest
    round-trip float representation (for example 0.1), but extra source digits
    cannot silently disappear, and a nonzero input cannot become zero.
    Already-rounded caller inputs cannot be recovered here.
    """
    # A supplied binary64 value is already rounded evidence. Widening its
    # shortest decimal repr into a new exact integer claim can falsely refuse
    # unchanged floats such as 1e23; no further conversion is needed here.
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("A metric must be finite.")
        return value
    try:
        exact = Decimal(str(value))
        number = float(value)
    except (InvalidOperation, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("A metric must be a finite number.") from exc
    if not exact.is_finite() or not math.isfinite(number):
        raise ValueError("A metric must be finite.")
    if exact != 0 and number == 0:
        raise ValueError("A nonzero metric would underflow to zero; retain it in an exact source format.")
    if exact == exact.to_integral_value():
        if Decimal.from_float(number) != exact:
            raise ValueError("An integer metric would lose precision; retain it in an exact source format.")
    elif Decimal(str(number)) != exact:
        raise ValueError("A decimal metric would lose source precision; retain it in an exact source format.")
    return number


def numeric_value(value: Any) -> tuple[float | None, str]:
    """Accept explicit numbers and US thousands groups; reject rounded/ambiguous text."""
    raw = text_value(value)
    lowered = raw.casefold()
    if lowered in {"", "-", "—", "–", "na", "n/a", "null", "none", "nan", "missing"}:
        return None, "missing"
    if lowered in {"suppressed", "*", "**"} or lowered.startswith(("<", ">")):
        return None, "suppressed"
    if lowered in {"unavailable", "not available", "not reported"}:
        return None, "unavailable"
    if lowered == "not_applicable":
        raise ValueError("Use a blank value with status unavailable and retain not_applicable as availability_reason in dimensions_json.")
    percentage = raw.endswith("%")
    if percentage:
        raw = raw[:-1].strip()
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?)", raw):
        raise ValueError(f"Invalid or ambiguous number {value!r}; use an exact number (no K/M suffix).")
    number = finite_number(raw.replace(",", ""))
    return number, "observed"


def iso_date(value: Any) -> str:
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    raw = text_value(value)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ValueError(f"Date {raw!r} must use YYYY-MM-DD; ambiguous dates are not guessed.")
    return date.fromisoformat(raw).isoformat()


def validate_records(records: pd.DataFrame | list[dict]) -> list[str]:
    """Return all consequential validation errors; callers must reject the batch."""
    # Preserve Python integers/Decimals in list inputs before validating them.
    df = records if isinstance(records, pd.DataFrame) else pd.DataFrame(records, dtype=object)
    if df.empty:
        return ["No observations to import."]
    missing_columns = [key for key in REQUIRED + ["value"] if key not in df.columns]
    if missing_columns:
        return ["Missing required columns: " + ", ".join(missing_columns)]
    errors = []
    for index, row in df.iterrows():
        label = f"Source row {text_value(row.get('source_row')) or index + 2}"
        for key in REQUIRED:
            if not text_value(row.get(key)):
                errors.append(f"{label}: {key} is required.")
        try:
            start, end = iso_date(row.period_start), iso_date(row.period_end)
            if start > end:
                errors.append(f"{label}: period_start is after period_end.")
        except (ValueError, TypeError) as exc:
            errors.append(f"{label}: {exc}")
        status = text_value(row.status)
        if status not in STATUSES:
            errors.append(f"{label}: unknown status {status!r}.")
        val = row.value
        absent = val is None or pd.isna(val)
        if status == "observed":
            if absent:
                errors.append(f"{label}: observed requires a numeric value.")
            else:
                try:
                    number = finite_number(val)
                    if number < 0 and text_value(row.metric) not in {"net_followers", "net_follows", "follower_change"}:
                        errors.append(f"{label}: negative value requires an explicitly signed net-change metric.")
                except (ValueError, TypeError) as exc:
                    errors.append(f"{label}: {exc}")
        elif not absent:
            errors.append(f"{label}: {status} must have a blank value.")
        captured = text_value(row.get("captured_at"))
        if captured:
            try:
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", captured):
                    date.fromisoformat(captured)
                else:
                    parsed = datetime.fromisoformat(captured.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        errors.append(f"{label}: captured_at timestamp needs an explicit UTC offset; a known date alone is also valid.")
            except ValueError:
                errors.append(f"{label}: captured_at is not an ISO timestamp.")
        dimensions = text_value(row.get("dimensions_json")) or "{}"
        try:
            if not isinstance(json.loads(dimensions), dict):
                errors.append(f"{label}: dimensions_json must be a JSON object.")
        except (ValueError, TypeError):
            errors.append(f"{label}: invalid dimensions_json.")
    return errors
