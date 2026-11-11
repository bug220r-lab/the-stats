"""Read retained Spotify audience evidence without altering immutable packages.

Audience stocks and rolling listener windows are endpoints, never additive
daily activity. Raw CSV/text assets retain their hashes and row/line references
when interpreted here; no parsed asset or stored analysis is rewritten.
"""
from datetime import datetime, timedelta
import hashlib
import io
import json
import math
import re

import pandas as pd

from stats_app.analysis_metrics import exact_period_audience, require_unique, selected_days

SP = "spotify/cleaned/"
SEGMENT_DAILY = "raw/spotify_baseline/normalized/audience_segment_daily.csv"
SEGMENT_CAPTURE = "raw/spotify_baseline/captured/audience_segments.txt"
CAPTURE_MANIFEST = "raw/spotify_baseline/captured/manifest.json"
RECOVERED_AUDIENCE = SP + "recovered_artist_metrics.csv"
PERIOD_AUDIENCE = SP + "artist_period_dashboard.csv"
ARTIST_DAILY = SP + "artist_daily.csv"
DEFINITIONS_URL = "https://support.spotify.com/us/artists/article/audience-segments-on-spotify/"

SEGMENT_METRICS = ["total_audience", "monthly_active_listeners", "previously_active", "programmed",
                   "super_listeners", "moderate_listeners", "light_listeners"]
MOVEMENT = {
    "reactivated_listeners": ("Reactivated listeners", "Previously active listeners who returned to monthly active listening."),
    "new_active_listeners": ("New active listeners", "Listeners newly active after at least two years outside the monthly active segment."),
    "new_listeners": ("New listeners", "Listeners with no streams of this artist in the preceding two years."),
}


def _has_asset(repo, path):
    return path in set(repo.file_catalog().path)


def _raw_asset(repo, path):
    """Repository verifies source bytes before this helper interprets them."""
    raw = repo.original_bytes(path)
    return raw, hashlib.sha256(raw).hexdigest()


def audience_segment_daily(repo):
    """Return dated audience stocks, retaining the unmodified CSV lineage."""
    if not _has_asset(repo, SEGMENT_DAILY):
        return pd.DataFrame(columns=["date", *SEGMENT_METRICS])
    raw, digest = _raw_asset(repo, SEGMENT_DAILY)
    frame = pd.read_csv(io.BytesIO(raw), dtype="string")
    required = {"date", "measurement_type", "source", *SEGMENT_METRICS}
    if not required.issubset(frame):
        raise ValueError("Retained Spotify segment history lacks its required fields.")
    frame["date"] = pd.to_datetime(frame.date, errors="raise").dt.strftime("%Y-%m-%d")
    if frame.date.isna().any() or not frame.measurement_type.eq("rolling_audience_stock").all():
        raise ValueError("Segment history requires dated rolling audience stocks.")
    require_unique(frame, ["date"])
    for column in SEGMENT_METRICS:
        numeric = pd.to_numeric(frame[column], errors="raise")
        if numeric.dropna().map(lambda value: not math.isfinite(float(value)) or value < 0 or value % 1 != 0).any():
            raise ValueError("Audience stocks must be nonnegative whole counts or unavailable.")
        frame[column] = numeric.astype("Int64")
    frame.insert(0, "source_csv_record", range(2, len(frame) + 2))
    frame["source_asset"] = SEGMENT_DAILY
    frame["source_sha256"] = digest
    frame.attrs.update(package_path=SEGMENT_DAILY, source_sha256=digest,
                       measurement="Source-defined rolling audience stocks; do not sum across dates.")
    return frame.sort_values("date", kind="stable")


def audience_movement(repo):
    """Normalize only explicitly scoped counts from the saved rendered capture.

    A missing value or ambiguous context remains unavailable. These categories
    can overlap and never reconcile additively to growth in the audience stock.
    """
    if not _has_asset(repo, SEGMENT_CAPTURE):
        return pd.DataFrame()
    raw, digest = _raw_asset(repo, SEGMENT_CAPTURE)
    text = raw.decode("utf-8-sig")
    dates = re.findall(r"paragraph: ([A-Z][a-z]{2} \d{1,2}, \d{4}) • Worldwide", text)
    artists = set(re.findall(r"/c/artist/([A-Za-z0-9]+)/", text))
    scoped = len(dates) == 1 and len(artists) == 1 and text.count("paragraph: Last 28 days • Worldwide") == 1
    end = datetime.strptime(dates[0], "%b %d, %Y").date() if scoped else None
    collected_at = None
    if _has_asset(repo, CAPTURE_MANIFEST):
        manifest = json.loads(repo.text(CAPTURE_MANIFEST))
        captures = [entry for entry in manifest if entry.get("file") == "audience_segments.txt"]
        if len(captures) == 1:
            collected_at = captures[0].get("collected_at")
    lines, rows = text.splitlines(), []
    for metric, (label, definition) in MOVEMENT.items():
        positions = [index for index, line in enumerate(lines) if line.strip() == "- generic: " + label]
        value, line_number = None, None
        if scoped and len(positions) == 1:
            # Saved accessibility text places an optional Help button before
            # the value. Bound the scan so another metric cannot supply it.
            values = [(i, re.fullmatch(r'\s*- generic: "?([\d,]+)"?\s*', lines[i]))
                      for i in range(positions[0] + 1, min(positions[0] + 4, len(lines)))]
            values = [(i, match) for i, match in values if match]
            if len(values) == 1:
                line_number, match = values[0]
                value, line_number = int(match.group(1).replace(",", "")), line_number + 1
        rows.append(dict(metric=metric, label=label, value=value,
                         value_status="observed" if value is not None else "unavailable",
                         period_start=(end - timedelta(days=27)).isoformat() if end else None,
                         period_end=end.isoformat() if end else None,
                         scope="Worldwide" if scoped else None, artist_id=next(iter(artists)) if scoped else None,
                         reporting_timezone="UTC" if scoped else None, retrieved_at=collected_at,
                         definition=definition, definitions_url=DEFINITIONS_URL,
                         source_asset=SEGMENT_CAPTURE, source_line=line_number, source_sha256=digest,
                         extraction="Interpreted saved rendered capture; not a native CSV export"))
    result = pd.DataFrame(rows)
    result["value"] = result.value.astype("Int64")
    result["source_line"] = result.source_line.astype("Int64")
    result.attrs.update(package_path=SEGMENT_CAPTURE, source_sha256=digest)
    return result


def super_listener_history(repo, start=None, end=None):
    """Endpoint history of overlapping 28-day super-listener populations."""
    data = repo.table(ARTIST_DAILY)
    required = {"date", "rolling28_super_listeners", "artist_id", "snapshot_class", "reporting_timezone"}
    if not required.issubset(data):
        raise ValueError("Spotify super-listener history lacks its required scope fields.")
    for column in ("artist_id", "snapshot_class", "reporting_timezone"):
        if not data.empty and data[column].fillna("").astype(str).nunique() != 1:
            raise ValueError("Select one artist, timezone and retrieval vintage for super listeners.")
    frame = data.copy()
    frame["date"] = pd.to_datetime(frame.date, errors="raise").dt.strftime("%Y-%m-%d")
    if frame.date.isna().any():
        raise ValueError("Super-listener history requires a reporting date.")
    require_unique(frame, ["date"])
    counts = pd.to_numeric(frame.rolling28_super_listeners, errors="coerce")
    valid = counts.map(lambda value: pd.notna(value) and math.isfinite(float(value)) and value >= 0 and value % 1 == 0)
    if "value_status" in frame:
        valid &= frame.value_status.isin({"observed", "observed_zero", "available"})
    frame["rolling28_super_listeners"] = counts.where(valid).astype("Int64")
    if start is not None or end is not None:
        frame = selected_days(frame, start or frame.date.min(), end or frame.date.max())
    frame.attrs.update(data.attrs)
    return frame.sort_values("date", kind="stable")


def exact_retained_period_audience(repo, start, end, *, previous_start=None, previous_end=None,
                                   artist_id=None, reporting_timezone="UTC"):
    """Supplement an exact current total with an exact recovered prior total.

    Native prior comparisons still win when compatible. An unrelated date,
    artist, timezone, population, ambiguous row or unsupported method is never
    used. This does not sum daily listener counts or overwrite a source row.
    """
    row = exact_period_audience(repo.table(PERIOD_AUDIENCE), start, end,
                               previous_start=previous_start, previous_end=previous_end,
                               artist_id=artist_id, reporting_timezone=reporting_timezone)
    if row is None:
        return None
    row["current_source_asset"] = PERIOD_AUDIENCE
    row["previous_source_asset"] = PERIOD_AUDIENCE if row.comparison_available else None
    if row.comparison_available or previous_start is None or RECOVERED_AUDIENCE not in repo.tables:
        return row
    recovered = repo.table(RECOVERED_AUDIENCE)
    required = {"Scope", "Spotify ID", "Period start", "Period end", "Metric", "Population", "Value",
                "reporting_timezone", "snapshot_class", "Method", "source_file", "source_row", "Collected UTC"}
    if not required.issubset(recovered):
        return row
    matches = recovered.loc[
        recovered["Scope"].eq("artist") & recovered["Spotify ID"].eq(row.artist_id)
        & recovered["Period start"].eq(str(previous_start)) & recovered["Period end"].eq(str(previous_end))
        & recovered["Metric"].eq("period_unique_listeners") & recovered["Population"].eq(row.scope)
        & recovered.reporting_timezone.eq(reporting_timezone)
        & recovered.snapshot_class.eq("baseline_supplement")
        & recovered["Method"].fillna("").str.startswith("Direct dashboard period total;")]
    if len(matches) != 1:
        return row
    prior = matches.iloc[0]
    value = pd.to_numeric(prior["Value"], errors="coerce")
    if pd.isna(value) or not math.isfinite(float(value)) or value < 0 or value % 1:
        return row
    native = repo.table(PERIOD_AUDIENCE)
    native = native.loc[native.metric.eq("listeners") & native.start_date.eq(str(start))
                        & native.end_date.eq(str(end)) & native.artist_id.eq(row.artist_id)
                        & native.scope.eq(row.scope) & native.snapshot_class.eq(row.snapshot_class)]
    if len(native) == 1:
        original = native.iloc[0]
        row["native_previous_value"] = original.previous_value
        row["native_previous_period_start"] = original.previous_period_start
        row["native_previous_period_end"] = original.previous_period_end
    row["previous_value"] = float(value)
    row["previous_status"] = "available_direct_recovered_period"
    row["previous_period_start"], row["previous_period_end"] = str(previous_start), str(previous_end)
    row["comparison_available"] = True
    row["comparison_reason"] = "Directly reported audience for the exact comparison interval; separately retained later recovery."
    row["comparison_type"] = "exact requested prior interval; directly recovered total"
    row["previous_source_asset"] = RECOVERED_AUDIENCE
    row["previous_source_file"], row["previous_source_row"] = prior.source_file, prior.source_row
    row["previous_retrieved_at"] = prior["Collected UTC"]
    row["previous_snapshot_class"] = prior.snapshot_class
    row["absolute_change"] = float(row.current_value) - float(value)
    row["percent_change"] = row.absolute_change / float(value) * 100 if value > 0 else None
    return row
