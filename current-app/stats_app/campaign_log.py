"""Immutable, source-backed content metadata revisions in the writable library.

This log never merges or sums performance observations. One latest revision per
platform/account/post is selected by explicit revision time, independent of
import order. Source bytes and all superseded revisions remain retrievable.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import math
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from stats_app.access import Principal, require_admin


COLUMNS = [
    "platform", "account_id", "post_id", "event_type", "publication_timestamp",
    "publication_timezone", "revision_timestamp", "song_id", "song_title", "excerpt",
    "opening_hook", "content_format", "duration_seconds", "call_to_action", "distribution",
    "spend", "currency", "campaign_id", "release_id", "destination_link", "utm_source",
    "utm_medium", "utm_campaign", "utm_content", "production_effort_minutes", "related_events",
    "tag_status", "tag_provenance", "source_reference", "notes",
]
KEY = ["platform", "account_id", "post_id"]
REQUIRED = KEY + ["revision_timestamp", "source_reference"]
NUMERIC = {"duration_seconds", "spend", "production_effort_minutes"}
TAGS = {"song_id", "song_title", "excerpt", "opening_hook", "content_format", "call_to_action"}
PLATFORMS = {"Spotify", "Instagram", "Facebook", "TikTok", "YouTube", "Offline"}
EVENT_TYPES = {"post", "release", "show", "playlist", "campaign", "other", "unknown"}
MAX_BYTES = 5 * 1024 * 1024


def _timestamp(value: str, field: str) -> datetime:
    try:
        if "T" not in value:
            raise ValueError
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError
        return stamp
    except ValueError as exc:
        raise ValueError(f"{field} requires an ISO timestamp with an explicit offset, for example 2026-10-23T12:00:00-04:00.") from exc


def _utc(stamp: datetime) -> str:
    return stamp.astimezone(timezone.utc).isoformat(timespec="microseconds")


def parse_campaign_csv(raw: bytes) -> pd.DataFrame:
    """Validate a complete CSV before any database mutation; preserve string IDs."""
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("Choose a nonempty campaign CSV no larger than 5 MiB.")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)):
            raise ValueError("Duplicate CSV column names are not allowed.")
        missing = set(REQUIRED) - set(headers)
        if missing:
            raise ValueError("Required CSV columns missing: " + ", ".join(sorted(missing)))
        extras = set(headers) - set(COLUMNS)
        if extras:
            raise ValueError("Unrecognized CSV columns: " + ", ".join(sorted(extras)))
        records = []
        seen = {}
        for source_row, raw_row in enumerate(reader, 2):
            if None in raw_row or any(value is None for value in raw_row.values()):
                raise ValueError(f"CSV record {source_row}: field count differs from header.")
            row = {field: (raw_row.get(field, "") or "").strip() for field in COLUMNS}
            if any(not row[field] or row[field].lower() in {"unknown", "unclassified"} for field in REQUIRED):
                raise ValueError(f"CSV record {source_row}: verified identity, revision_timestamp and source_reference are required.")
            if row["platform"] not in PLATFORMS:
                raise ValueError(f"CSV record {source_row}: unsupported platform.")
            for field in COLUMNS:
                if not row[field] or row[field].lower() in {"unknown", "unclassified"}:
                    row[field] = "unknown"
            row["event_type"] = row["event_type"].lower()
            if row["event_type"] not in EVENT_TYPES:
                raise ValueError(f"CSV record {source_row}: invalid event_type.")
            row["revision_timestamp"] = _utc(_timestamp(row["revision_timestamp"], "revision_timestamp"))
            zone_name = row["publication_timezone"]
            if zone_name != "unknown":
                try:
                    zone = ZoneInfo(zone_name)
                except (ZoneInfoNotFoundError, OSError, ValueError) as exc:
                    raise ValueError(f"CSV record {source_row}: publication_timezone must be an IANA zone such as America/Los_Angeles or UTC.") from exc
            row["publication_timestamp_utc"] = None
            if row["publication_timestamp"] != "unknown":
                if zone_name == "unknown":
                    raise ValueError(f"CSV record {source_row}: known publication timestamps require publication_timezone.")
                stamp = _timestamp(row["publication_timestamp"], "publication_timestamp")
                local = stamp.astimezone(zone)
                if stamp.utcoffset() != local.utcoffset() or stamp.replace(tzinfo=None) != local.replace(tzinfo=None):
                    raise ValueError(f"CSV record {source_row}: publication timestamp offset disagrees with its native timezone.")
                row["publication_timestamp_utc"] = _utc(stamp)
            for field in NUMERIC:
                value = row[field]
                if value == "unknown":
                    row[field] = None
                    continue
                try:
                    value = float(value)
                except ValueError as exc:
                    raise ValueError(f"CSV record {source_row}: {field} must be nonnegative or unknown.") from exc
                if not math.isfinite(value) or value < 0:
                    raise ValueError(f"CSV record {source_row}: {field} must be finite and nonnegative.")
                row[field] = value
            row["distribution"] = row["distribution"].lower()
            if row["distribution"] not in {"organic", "paid", "mixed", "unknown"}:
                raise ValueError(f"CSV record {source_row}: distribution must be organic, paid, mixed or unknown.")
            if row["spend"] is not None and (len(row["currency"]) != 3 or not row["currency"].isascii() or not row["currency"].isalpha()):
                raise ValueError(f"CSV record {source_row}: known spend requires a three-letter currency code.")
            if row["currency"] != "unknown":
                row["currency"] = row["currency"].upper()
            row["tag_status"] = row["tag_status"].lower()
            if row["tag_status"] not in {"verified", "inferred", "unknown"}:
                raise ValueError(f"CSV record {source_row}: tag_status must be verified, inferred or unknown.")
            if any(row[field] != "unknown" for field in TAGS) and (row["tag_status"] == "unknown" or row["tag_provenance"] == "unknown"):
                raise ValueError(f"CSV record {source_row}: assigned creative tags require tag_status and tag_provenance.")
            row["source_row"] = source_row
            key = tuple(row[field] for field in KEY + ["revision_timestamp"])
            canonical = {key: value for key, value in row.items() if key != "source_row"}
            if key in seen and seen[key] != canonical:
                raise ValueError(f"CSV record {source_row}: conflicting values for the same identity and revision time.")
            seen[key] = canonical
            records.append(row)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Campaign log must be a valid UTF-8 CSV.") from exc
    if not records:
        raise ValueError("The template has no records. Fill a row with real source-backed metadata first.")
    return pd.DataFrame(records)


def template_bytes() -> bytes:
    return (",".join(COLUMNS) + "\n").encode("utf-8-sig")


def export_csv(data: pd.DataFrame) -> bytes:
    """Spreadsheet-safe export; original source bytes are available separately."""
    output = data.copy()
    for field in output.select_dtypes(include=["object", "string"]):
        output[field] = output[field].map(lambda value: "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value)
    return output.to_csv(index=False).encode("utf-8-sig")


def editable_csv(data: pd.DataFrame) -> bytes:
    """Round-trip template fields; retain exact text, including literal prefixes.

    This interchange export is distinct from spreadsheet-safe inspection output.
    Formula escaping would otherwise alter saved hooks, IDs and source references.
    """
    return data.loc[:, COLUMNS].to_csv(index=False).encode("utf-8-sig")


class CampaignLogRepository:
    """Owns only campaign_* tables in the existing writable stats.sqlite3."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).resolve()

    def _read(self, sql, params=()):
        if not self.database_path.exists():
            return []
        connection = sqlite3.connect(self.database_path.as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='campaign_revisions'").fetchone():
                return []
            return [dict(row) for row in connection.execute(sql, params)]
        finally:
            connection.close()

    def current(self) -> pd.DataFrame:
        rows = self._read("""SELECT * FROM (SELECT *, ROW_NUMBER() OVER
            (PARTITION BY entity_key ORDER BY revised_at DESC) AS rank FROM campaign_revisions)
            WHERE rank=1 ORDER BY entity_key""")
        return pd.DataFrame([{**json.loads(row["data_json"]), "revision_id": row["revision_id"]} for row in rows],
                            columns=COLUMNS + ["publication_timestamp_utc", "revision_id"])

    def history(self) -> pd.DataFrame:
        rows = self._read("""SELECT r.*, s.source_hash, s.source_name, s.imported_at, x.source_row
            FROM campaign_revisions r JOIN campaign_record_sources x ON r.revision_id=x.revision_id
            JOIN campaign_sources s ON s.source_hash=x.source_hash ORDER BY r.entity_key,r.revised_at,x.source_row""")
        return pd.DataFrame([{**json.loads(row["data_json"]), **{key: row[key] for key in
            ("revision_id", "source_hash", "source_name", "imported_at", "source_row")}} for row in rows])

    def source_bytes(self, source_hash: str) -> bytes:
        rows = self._read("SELECT source_bytes FROM campaign_sources WHERE source_hash=?", (source_hash,))
        if not rows:
            raise ValueError("Source not found.")
        raw = rows[0]["source_bytes"]
        if sha256(raw).hexdigest() != source_hash:
            raise ValueError("Retained campaign source failed its SHA-256 check; unchanged-source download refused.")
        return raw

    def import_csv(self, raw: bytes, source_name: str, principal: Principal) -> dict:
        require_admin(principal)
        data = parse_campaign_csv(raw)
        source_hash = sha256(raw).hexdigest()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=15)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            for sql in (
                "CREATE TABLE IF NOT EXISTS campaign_sources (source_hash TEXT PRIMARY KEY,source_name TEXT NOT NULL,source_bytes BLOB NOT NULL,imported_at TEXT NOT NULL,imported_by TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS campaign_revisions (revision_id TEXT PRIMARY KEY,entity_key TEXT NOT NULL,revised_at TEXT NOT NULL,data_json TEXT NOT NULL,UNIQUE(entity_key,revised_at))",
                "CREATE TABLE IF NOT EXISTS campaign_record_sources (revision_id TEXT NOT NULL REFERENCES campaign_revisions(revision_id),source_hash TEXT NOT NULL REFERENCES campaign_sources(source_hash),source_row INTEGER NOT NULL,PRIMARY KEY(revision_id,source_hash,source_row))",
            ):
                connection.execute(sql)
            if connection.execute("SELECT 1 FROM campaign_sources WHERE source_hash=?", (source_hash,)).fetchone():
                connection.rollback()
                return dict(source_hash=source_hash, added=0, duplicate_import=True, retained_rows=len(data))
            connection.execute("INSERT INTO campaign_sources VALUES (?,?,?,?,?)", (source_hash, Path(source_name).name, raw,
                               _utc(datetime.now(timezone.utc)), principal.name))
            added = 0
            for row in data.to_dict("records"):
                source_row = int(row.pop("source_row"))
                row = {key: None if not isinstance(value, str) and pd.isna(value) else value for key, value in row.items()}
                payload = json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False)
                entity_key = json.dumps([row[field] for field in KEY], ensure_ascii=False)
                revision_id = sha256(payload.encode("utf-8")).hexdigest()
                previous = connection.execute("SELECT revision_id FROM campaign_revisions WHERE entity_key=? AND revised_at=?",
                                              (entity_key, row["revision_timestamp"])).fetchone()
                if previous and previous[0] != revision_id:
                    raise ValueError("Conflicting metadata at an existing revision time. Use a later explicit revision_timestamp to preserve the correction.")
                if not previous:
                    connection.execute("INSERT INTO campaign_revisions VALUES (?,?,?,?)", (revision_id, entity_key, row["revision_timestamp"], payload))
                    added += 1
                connection.execute("INSERT INTO campaign_record_sources VALUES (?,?,?)", (revision_id, source_hash, source_row))
            connection.commit()
            return dict(source_hash=source_hash, added=added, duplicate_import=False, retained_rows=len(data))
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
