"""Replaceable SQLite repository for immutable, source-backed reporting snapshots.

Every operation opens its own connection. A snapshot is an explicit comparison
boundary: imports may add observations, but cannot silently replace a value.
Source bytes, observations, and per-source provenance commit together.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import sqlite3
import time
from typing import Any, Iterable, Mapping

import pandas as pd

from .validation import finite_number

KEY_FIELDS = (
    "platform", "account", "entity_type", "entity_id", "metric", "unit",
    "period_start", "period_end", "time_grain", "measurement_type",
    "source_timezone", "dimensions_json",
)
REQUIRED_FIELDS = set(KEY_FIELDS) - {"source_timezone", "dimensions_json"}
TEXT_FIELDS = tuple(dict.fromkeys((*KEY_FIELDS, "entity_name", "captured_at",
                                 "status", "evidence_ref", "definition", "worksheet")))
RECORD_FIELDS = (*TEXT_FIELDS, "value", "source_row")
ALLOWED_STATUSES = {"observed", "missing", "suppressed", "unavailable"}


class StorageError(ValueError):
    """An import could not be accepted without changing trusted data."""


class ImportConflictError(StorageError):
    """A source disagrees with an existing observation in this snapshot."""


class SnapshotSealedError(StorageError):
    """New source files cannot be added to a sealed snapshot."""


@dataclass(frozen=True)
class ImportResult:
    import_id: int
    source_hash: str
    snapshot_label: str
    imported_rows: int
    duplicate_rows: int
    duplicate_import: bool


def _text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, (str, dict, list)) and pd.isna(value):
        return ""
    return str(value).strip()


def _captured(value: Any) -> str:
    value = _text(value)
    if value:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise StorageError("captured_at must be an ISO date/time or left blank when unknown.") from exc
    return value


def _normalize_record(row: Mapping[str, Any], captured_at: str) -> dict[str, Any]:
    result = {field: _text(row.get(field)) for field in TEXT_FIELDS}
    absent = sorted(field for field in REQUIRED_FIELDS if not result[field])
    if absent:
        raise StorageError("Missing required fields: " + ", ".join(absent))
    for field in ("period_start", "period_end"):
        try:
            result[field] = date.fromisoformat(result[field]).isoformat()
        except ValueError as exc:
            raise StorageError(f"{field} must be a real ISO date (YYYY-MM-DD).") from exc
    if result["period_start"] > result["period_end"]:
        raise StorageError("period_start must not be later than period_end.")
    result["status"] = result["status"].lower()
    if result["status"] not in ALLOWED_STATUSES:
        raise StorageError("status must be observed, missing, suppressed, or unavailable.")
    raw_value = row.get("value")
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()) or pd.isna(raw_value):
        value = None
    else:
        try:
            value = finite_number(raw_value)
        except (TypeError, ValueError) as exc:
            raise StorageError(str(exc)) from exc
    if result["status"] == "observed" and value is None:
        raise StorageError("An observed metric requires a number; use a missing status for unknown data.")
    if result["status"] != "observed" and value is not None:
        raise StorageError("Missing, suppressed, and unavailable metrics must have a blank value.")
    result["value"] = value
    result["captured_at"] = _captured(result["captured_at"] or captured_at)
    raw_dimensions = row.get("dimensions_json")
    if isinstance(raw_dimensions, dict):
        dimensions = raw_dimensions
    else:
        try:
            dimensions = json.loads(result["dimensions_json"] or "{}")
        except (TypeError, ValueError) as exc:
            raise StorageError("dimensions_json must contain a JSON object.") from exc
    if not isinstance(dimensions, dict):
        raise StorageError("dimensions_json must contain a JSON object.")
    try:
        result["dimensions_json"] = json.dumps(dimensions, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise StorageError("dimensions_json must contain finite JSON values.") from exc
    source_row = _text(row.get("source_row"))
    try:
        # pandas often represents optional integer columns as floats.
        numeric_row = float(source_row) if source_row else None
        if numeric_row is not None and (not numeric_row.is_integer() or numeric_row < 1):
            raise ValueError
        result["source_row"] = int(numeric_row) if numeric_row is not None else None
    except (ValueError, OverflowError) as exc:
        raise StorageError("source_row must be a positive whole number or blank.") from exc
    return result


class SQLiteRepository:
    """Single-host storage, suitable for local use and replaceable for hosting.

    Public reads return pandas DataFrames. ``import_dataset`` returns ImportResult.
    Baseline creation requires ``provenance={'baseline_evidence': '...verified source...'}``.
    After loading all verified original files, call ``seal_snapshot(label)``.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        connection.execute("PRAGMA synchronous=FULL")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self):
        with self._connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise StorageError(f"Unsupported database schema version {version}; preserve this database and upgrade the app.")
            # SQLite's initial WAL transition can report BUSY without applying
            # busy_timeout when another process opens the new database at once.
            deadline = time.monotonic() + 15
            while True:
                try:
                    mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
                    if mode.lower() != "wal":
                        connection.execute("PRAGMA journal_mode=WAL")
                    break
                except sqlite3.OperationalError as exc:
                    code = getattr(exc, "sqlite_errorcode", 0) & 255
                    if code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            if version == 1:
                return
            connection.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY, label TEXT NOT NULL UNIQUE,
                    is_baseline INTEGER NOT NULL DEFAULT 0 CHECK(is_baseline IN (0,1)),
                    sealed INTEGER NOT NULL DEFAULT 0 CHECK(sealed IN (0,1)),
                    captured_at TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_baseline
                    ON snapshots(is_baseline) WHERE is_baseline=1;
                CREATE TABLE IF NOT EXISTS source_files (
                    hash TEXT PRIMARY KEY, original_bytes BLOB NOT NULL,
                    byte_count INTEGER NOT NULL, archived_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS imports (
                    id INTEGER PRIMARY KEY, snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
                    source_hash TEXT NOT NULL REFERENCES source_files(hash), source_name TEXT NOT NULL,
                    imported_at TEXT NOT NULL, captured_at TEXT NOT NULL DEFAULT '',
                    source_context TEXT NOT NULL, interpretation_hash TEXT NOT NULL,
                    provenance_json TEXT NOT NULL, imported_rows INTEGER NOT NULL DEFAULT 0,
                    duplicate_rows INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(snapshot_id, source_hash, source_context)
                );
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY, snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
                    observation_key TEXT NOT NULL, record_json TEXT NOT NULL,
                    value REAL, status TEXT NOT NULL,
                    UNIQUE(snapshot_id, observation_key),
                    CHECK((status='observed' AND value IS NOT NULL) OR
                          (status IN ('missing','suppressed','unavailable') AND value IS NULL))
                );
                CREATE TABLE IF NOT EXISTS observation_sources (
                    id INTEGER PRIMARY KEY, observation_id INTEGER NOT NULL REFERENCES observations(id),
                    import_id INTEGER NOT NULL REFERENCES imports(id), source_row INTEGER,
                    worksheet TEXT NOT NULL DEFAULT '', evidence_ref TEXT NOT NULL DEFAULT '',
                    captured_at TEXT NOT NULL DEFAULT '', definition TEXT NOT NULL DEFAULT '',
                    entity_name TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS observation_sources_observation
                    ON observation_sources(observation_id);
                PRAGMA user_version=1;
                COMMIT;
            """)

    def import_dataset(
        self, raw_bytes: bytes, source_name: str,
        records: pd.DataFrame | Iterable[Mapping[str, Any]], snapshot_label: str,
        captured_at: str | None = None, baseline: bool = False,
        provenance: Mapping[str, Any] | None = None,
    ) -> ImportResult:
        if not isinstance(raw_bytes, bytes) or not raw_bytes:
            raise StorageError("A nonempty original source file is required.")
        source_name = _text(source_name)
        snapshot_label = _text(snapshot_label)
        if not source_name or not snapshot_label:
            raise StorageError("source_name and snapshot_label are required.")
        captured = _captured(captured_at)
        provenance = dict(provenance or {})
        if baseline and not _text(provenance.get("baseline_evidence")):
            raise StorageError("Creating or adding to the original baseline requires verified baseline_evidence provenance.")
        try:
            provenance_json = json.dumps(provenance, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise StorageError("provenance must contain JSON-compatible values.") from exc
        if isinstance(records, pd.DataFrame):
            records = records.to_dict(orient="records")
        normalized = [_normalize_record(row, captured) for row in records]
        if not normalized:
            raise StorageError("No reporting records were supplied; nothing was imported.")
        digest = sha256(raw_bytes).hexdigest()
        source_context = json.dumps(sorted({row["worksheet"] for row in normalized}), separators=(",", ":"))
        interpretation = json.dumps(sorted(
            json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False)
            for row in normalized
        ), separators=(",", ":"))
        interpretation_hash = sha256(interpretation.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                snapshot = connection.execute("SELECT * FROM snapshots WHERE label=?", (snapshot_label,)).fetchone()
                if snapshot is None:
                    if baseline and connection.execute("SELECT 1 FROM snapshots WHERE is_baseline=1").fetchone():
                        raise StorageError("The original baseline already exists. Import newer data as a separate non-baseline snapshot.")
                    cursor = connection.execute(
                        "INSERT INTO snapshots(label,is_baseline,captured_at,created_at) VALUES(?,?,?,?)",
                        (snapshot_label, int(baseline), captured, now),
                    )
                    snapshot_id = cursor.lastrowid
                else:
                    snapshot_id = snapshot["id"]
                    if bool(snapshot["is_baseline"]) != bool(baseline):
                        raise StorageError("Snapshot baseline designation cannot be changed; choose a distinct snapshot label.")
                    existing_import = connection.execute(
                        "SELECT * FROM imports WHERE snapshot_id=? AND source_hash=? AND source_context=?",
                        (snapshot_id, digest, source_context),
                    ).fetchone()
                    if existing_import:
                        if existing_import["interpretation_hash"] != interpretation_hash:
                            raise ImportConflictError(
                                "This source and worksheet were already imported with different mappings or metadata. "
                                "Use a new snapshot to review a changed interpretation."
                            )
                        connection.rollback()
                        return ImportResult(existing_import["id"], digest, snapshot_label, 0, len(normalized), True)
                    if snapshot["sealed"]:
                        raise SnapshotSealedError("This snapshot is sealed. Import the new source into a separately labeled snapshot.")
                connection.execute(
                    "INSERT OR IGNORE INTO source_files(hash,original_bytes,byte_count,archived_at) VALUES(?,?,?,?)",
                    (digest, raw_bytes, len(raw_bytes), now),
                )
                cursor = connection.execute(
                    "INSERT INTO imports(snapshot_id,source_hash,source_name,imported_at,captured_at,source_context,interpretation_hash,provenance_json) VALUES(?,?,?,?,?,?,?,?)",
                    (snapshot_id, digest, source_name, now, captured, source_context, interpretation_hash, provenance_json),
                )
                import_id = cursor.lastrowid
                imported_rows = duplicate_rows = 0
                for record in normalized:
                    key = json.dumps([record[field] for field in KEY_FIELDS], separators=(",", ":"))
                    existing = connection.execute(
                        "SELECT id,value,status,record_json FROM observations WHERE snapshot_id=? AND observation_key=?", (snapshot_id, key)
                    ).fetchone()
                    if existing:
                        definition = _text(json.loads(existing["record_json"]).get("definition"))
                        if definition != record["definition"]:
                            raise ImportConflictError(
                                f"Conflicting definition or scope for {record['metric']} on {record['entity_id']}. "
                                "The entire import was cancelled. Keep distinct measurement scopes explicit in "
                                "dimensions_json, or review the definition in a new snapshot."
                            )
                        if existing["value"] != record["value"] or existing["status"] != record["status"]:
                            raise ImportConflictError(
                                f"Conflicting {record['metric']} for {record['entity_id']} "
                                f"({record['period_start']} to {record['period_end']}). "
                                "The entire import was cancelled. Keep changed measurements in a new snapshot."
                            )
                        observation_id = existing["id"]
                        duplicate_rows += 1
                    else:
                        cursor = connection.execute(
                            "INSERT INTO observations(snapshot_id,observation_key,record_json,value,status) VALUES(?,?,?,?,?)",
                            (snapshot_id, key, json.dumps(record, sort_keys=True, allow_nan=False), record["value"], record["status"]),
                        )
                        observation_id = cursor.lastrowid
                        imported_rows += 1
                    connection.execute(
                        "INSERT INTO observation_sources(observation_id,import_id,source_row,worksheet,evidence_ref,captured_at,definition,entity_name) VALUES(?,?,?,?,?,?,?,?)",
                        (observation_id, import_id, record["source_row"], record["worksheet"], record["evidence_ref"], record["captured_at"], record["definition"], record["entity_name"]),
                    )
                connection.execute("UPDATE imports SET imported_rows=?,duplicate_rows=? WHERE id=?", (imported_rows, duplicate_rows, import_id))
                connection.commit()
                return ImportResult(import_id, digest, snapshot_label, imported_rows, duplicate_rows, False)
            except Exception:
                connection.rollback()
                raise

    def preview_dataset(
        self, raw_bytes: bytes, source_name: str,
        records: pd.DataFrame | Iterable[Mapping[str, Any]], snapshot_label: str,
        captured_at: str | None = None, baseline: bool = False,
        provenance: Mapping[str, Any] | None = None,
    ) -> ImportResult:
        """Predict this import against a consistent, disposable memory copy.

        The real importer supplies duplicate, conflict, interpretation and sealed
        snapshot checks. Opening the source read-only and using SQLite's backup
        API includes committed WAL data without modifying production tables.
        The returned import ID is provisional; saving always rechecks current
        storage because another import may occur after this preview.
        """
        class PreviewRepository(SQLiteRepository):
            def __init__(self, connection):
                self.connection = connection

            @contextmanager
            def _connection(self):
                yield self.connection

        preview = sqlite3.connect(":memory:")
        preview.row_factory = sqlite3.Row
        try:
            source = sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True, timeout=15)
            try:
                source.execute("PRAGMA query_only=ON")
                source.backup(preview)
            finally:
                source.close()
            preview.execute("PRAGMA foreign_keys=ON")
            return PreviewRepository(preview).import_dataset(
                raw_bytes, source_name, records, snapshot_label,
                captured_at=captured_at, baseline=baseline, provenance=provenance,
            )
        finally:
            preview.close()

    def list_snapshots(self) -> pd.DataFrame:
        with self._connection() as connection:
            return pd.read_sql_query("""
                SELECT s.label, s.is_baseline, s.sealed, s.captured_at, s.created_at,
                       (SELECT COUNT(*) FROM observations o WHERE o.snapshot_id=s.id) AS observation_count,
                       (SELECT COUNT(*) FROM imports i WHERE i.snapshot_id=s.id) AS import_count
                FROM snapshots s ORDER BY s.is_baseline DESC, s.created_at DESC, s.label
            """, connection)

    def observations(self, snapshot_label: str) -> pd.DataFrame:
        with self._connection() as connection:
            rows = connection.execute("""
                SELECT o.id,o.record_json FROM observations o JOIN snapshots s ON s.id=o.snapshot_id
                WHERE s.label=? ORDER BY o.id
            """, (snapshot_label,)).fetchall()
            all_sources = connection.execute("""
                SELECT DISTINCT os.observation_id,i.id,i.source_name,i.source_hash,i.imported_at
                FROM observation_sources os JOIN imports i ON i.id=os.import_id
                JOIN snapshots s ON s.id=i.snapshot_id WHERE s.label=?
                ORDER BY i.imported_at,i.id
            """, (snapshot_label,)).fetchall()
            sources_by_observation: dict[int, list[sqlite3.Row]] = {}
            for source in all_sources:
                sources_by_observation.setdefault(source["observation_id"], []).append(source)
            result = []
            for row in rows:
                record = json.loads(row["record_json"])
                sources = sources_by_observation.get(row["id"], [])
                record.update(observation_id=row["id"], snapshot_label=snapshot_label,
                              source_names="; ".join(source["source_name"] for source in sources),
                              source_count=len(sources), imported_at=sources[0]["imported_at"] if sources else "")
                result.append(record)
            columns = [*RECORD_FIELDS, "observation_id", "snapshot_label", "source_names", "source_count", "imported_at"]
            return pd.DataFrame(result, columns=columns)

    def import_history(self) -> pd.DataFrame:
        with self._connection() as connection:
            return pd.read_sql_query("""
                SELECT i.id AS import_id,s.label AS snapshot_label,s.is_baseline,s.sealed,
                       i.source_name,i.source_hash,f.byte_count,i.imported_at,i.captured_at,
                       i.imported_rows,i.duplicate_rows,i.source_context,i.interpretation_hash,i.provenance_json
                FROM imports i JOIN snapshots s ON s.id=i.snapshot_id
                JOIN source_files f ON f.hash=i.source_hash ORDER BY i.imported_at DESC,i.id DESC
            """, connection)

    def observation_provenance(self, observation_id: int) -> pd.DataFrame:
        """All contributing source rows, including equal-value overlapping exports."""
        with self._connection() as connection:
            return pd.read_sql_query("""
                SELECT os.source_row,os.worksheet,os.evidence_ref,os.captured_at,os.definition,
                       os.entity_name,i.source_name,i.source_hash,i.imported_at,i.provenance_json
                FROM observation_sources os JOIN imports i ON i.id=os.import_id
                WHERE os.observation_id=? ORDER BY os.id
            """, connection, params=(int(observation_id),))

    def original_source(self, source_hash: str) -> bytes:
        with self._connection() as connection:
            row = connection.execute("SELECT original_bytes,byte_count FROM source_files WHERE hash=?", (source_hash,)).fetchone()
            if row is None:
                raise StorageError("Source hash was not found.")
            raw = bytes(row["original_bytes"])
            if len(raw) != row["byte_count"] or sha256(raw).hexdigest() != source_hash:
                raise StorageError("The original source failed its SHA-256 or byte-count check; no file was changed.")
            return raw

    def seal_snapshot(self, label: str) -> None:
        with self._connection() as connection:
            with connection:
                cursor = connection.execute("UPDATE snapshots SET sealed=1 WHERE label=?", (label,))
                if cursor.rowcount != 1:
                    raise StorageError("Snapshot was not found.")

    def backup(self, path: str | Path) -> Path:
        """Create a transactionally consistent backup, including WAL contents.

        Refuses to replace an existing file. The caller chooses a private path;
        backups contain the original private exports as well as reporting data.
        """
        target = Path(path).expanduser().resolve()
        if target == self.db_path:
            raise StorageError("Backup destination must differ from the live database.")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create prevents silently overwriting an earlier backup.
        with target.open("xb"):
            pass
        try:
            with self._connection() as source:
                destination = sqlite3.connect(target)
                try:
                    source.backup(destination)
                finally:
                    destination.close()
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return target
