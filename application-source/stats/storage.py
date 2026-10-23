"""Local, provenance-preserving SQLite persistence for The Stats.

An observation's identity includes its reporting window and measurement semantics,
but not the file that happened to contain it. Each changed reading creates a version;
the most recently committed, non-retired version is active. Duplicate readings keep
all source-row references. No operation may mutate a sealed snapshot.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sqlite3
from typing import Any

import pandas as pd


OBSERVATION_FIELDS = [
    "platform", "account_id", "account_name", "entity_type", "entity_id",
    "entity_name", "metric", "value", "unit", "definition", "dimensions",
    "period_start", "period_end", "time_grain", "captured_at", "source_timezone",
    "measurement_type", "status", "source_row", "evidence_ref", "published_at",
    "source_url",
]
IDENTITY_FIELDS = [
    "platform", "account_id", "entity_type", "entity_id", "metric", "unit",
    "definition", "dimensions", "period_start", "period_end", "time_grain",
    "measurement_type", "source_timezone",
]
IDENTITY_SCHEMA_VERSION = 2
EXTRA_FIELDS = [
    "id", "snapshot_id", "snapshot_name", "import_id", "source_filename",
    "worksheet", "file_hash", "imported_at", "active", "version",
    "source_references", "import_retired",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple)):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Store:
    """One database and its unchanged source archive, suitable for local use."""

    def __init__(self, path: str | Path = "data/stats.sqlite3"):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.source_dir = self.path.parent / "sources"
        self.source_dir.mkdir(exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                    is_baseline INTEGER NOT NULL DEFAULT 0,
                    locked INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL,
                    evidence TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS imports (
                    id INTEGER PRIMARY KEY, snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
                    filename TEXT NOT NULL, file_hash TEXT NOT NULL, source_path TEXT NOT NULL,
                    worksheet TEXT NOT NULL, mapping_json TEXT NOT NULL, signature TEXT NOT NULL UNIQUE,
                    imported_at TEXT NOT NULL, retired INTEGER NOT NULL DEFAULT 0,
                    counts_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY, snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
                    import_id INTEGER NOT NULL REFERENCES imports(id), identity_key TEXT NOT NULL,
                    version INTEGER NOT NULL, active INTEGER NOT NULL,
                    platform TEXT, account_id TEXT, account_name TEXT, entity_type TEXT,
                    entity_id TEXT, entity_name TEXT, metric TEXT NOT NULL, value REAL,
                    unit TEXT, definition TEXT, dimensions TEXT NOT NULL DEFAULT '{}',
                    period_start TEXT, period_end TEXT, time_grain TEXT, captured_at TEXT,
                    source_timezone TEXT, measurement_type TEXT, status TEXT,
                    source_row TEXT, evidence_ref TEXT, published_at TEXT, source_url TEXT,
                    UNIQUE(snapshot_id, identity_key, version)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_observation
                    ON observations(snapshot_id, identity_key) WHERE active = 1;
                CREATE TABLE IF NOT EXISTS observation_sources (
                    id INTEGER PRIMARY KEY, observation_id INTEGER NOT NULL REFERENCES observations(id),
                    import_id INTEGER NOT NULL REFERENCES imports(id), source_row TEXT,
                    captured_at TEXT, evidence_ref TEXT, source_url TEXT, payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS observation_sources_observation_id
                    ON observation_sources(observation_id);
                CREATE INDEX IF NOT EXISTS observation_sources_import_id
                    ON observation_sources(import_id);
                CREATE TABLE IF NOT EXISTS validation_issues (
                    id INTEGER PRIMARY KEY, import_id INTEGER NOT NULL REFERENCES imports(id),
                    severity TEXT NOT NULL, code TEXT NOT NULL, message TEXT NOT NULL,
                    source_row TEXT, payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mappings (
                    name TEXT PRIMARY KEY, mapping_json TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS annotations (
                    id INTEGER PRIMARY KEY, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS collection_queue (
                    id TEXT PRIMARY KEY, source_ref TEXT NOT NULL, captured_at TEXT,
                    imported_at TEXT NOT NULL, payload_json TEXT NOT NULL,
                    local_note TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
                INSERT OR IGNORE INTO state(key, value) VALUES('revision', 0);
            """)
        self._migrate_identity_schema()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, factory=_ClosingConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    @contextmanager
    def _transaction(self):
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _bump(db):
        db.execute("UPDATE state SET value = value + 1 WHERE key = 'revision'")

    @staticmethod
    def _timezone(value):
        value = _clean(value)
        return str(value).strip() or None if value is not None else None

    @staticmethod
    def _reselect_active(db, snapshot_id=None):
        where = " WHERE snapshot_id = ?" if snapshot_id is not None else ""
        params = (snapshot_id,) if snapshot_id is not None else ()
        db.execute("UPDATE observations SET active = 0" + where, params)
        candidates = db.execute("""SELECT o.id FROM observations o JOIN (
            SELECT candidate.snapshot_id, candidate.identity_key, MAX(candidate.version) AS version
            FROM observations candidate WHERE EXISTS (
                SELECT 1 FROM observation_sources os JOIN imports i ON i.id = os.import_id
                WHERE os.observation_id = candidate.id AND i.retired = 0)
            GROUP BY candidate.snapshot_id, candidate.identity_key
            ) winner ON winner.snapshot_id = o.snapshot_id
            AND winner.identity_key = o.identity_key AND winner.version = o.version"""
            + (" WHERE o.snapshot_id = ?" if snapshot_id is not None else ""), params).fetchall()
        db.executemany("UPDATE observations SET active = 1 WHERE id = ?", [(row[0],) for row in candidates])

    def _migrate_identity_schema(self):
        """Recover timezone-specific identities from retained evidence, once.

        The prior identity omitted timezone, so merely rehashing observations
        would leave already-merged duplicates incorrect. Source payloads allow
        those duplicates to be separated without changing any source reading.
        The transaction also recalculates versions within each corrected scope.
        """
        with self._transaction() as db:
            state = db.execute("SELECT value FROM state WHERE key = 'identity_schema_version'").fetchone()
            version = state[0] if state else 1
            if version > IDENTITY_SCHEMA_VERSION:
                raise ValueError("This database uses a newer identity schema. Update the application before opening it.")
            if version == IDENTITY_SCHEMA_VERSION:
                return
            observations = [dict(row) for row in db.execute("SELECT * FROM observations ORDER BY id")]
            refs = {}
            for ref in db.execute("SELECT * FROM observation_sources ORDER BY id"):
                refs.setdefault(ref["observation_id"], []).append(dict(ref))
            # Temporarily isolate each chain while reassigning its identity and
            # versions; the entire migration is committed or rolled back.
            db.execute("DROP INDEX IF EXISTS one_active_observation")
            db.execute("UPDATE observations SET identity_key = 'migration:' || id, active = 0")
            candidates = []
            split_count = 0
            for original in observations:
                original_zone = self._timezone(original["source_timezone"])
                groups = {}
                for ref in refs.get(original["id"], []):
                    payload = json.loads(ref["payload_json"])
                    zone = self._timezone(payload.get("source_timezone", original_zone))
                    groups.setdefault(zone, []).append(ref)
                if not groups:
                    groups[original_zone] = []
                preferred_zone = original_zone if original_zone in groups else next(iter(groups))
                for zone, source_refs in groups.items():
                    record = dict(original)
                    record["source_timezone"] = zone
                    if zone == preferred_zone:
                        observation_id = original["id"]
                    else:
                        first = source_refs[0]
                        record.update({key: first[key] for key in ("import_id", "source_row", "captured_at", "evidence_ref", "source_url")})
                        columns = ["snapshot_id", "import_id", "identity_key", "version", "active"] + OBSERVATION_FIELDS
                        record.update(identity_key=f"migration-split:{original['id']}:{split_count}", version=1, active=0)
                        cursor = db.execute(f"INSERT INTO observations ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                                            [record[key] for key in columns])
                        observation_id = cursor.lastrowid
                        split_count += 1
                        db.executemany("UPDATE observation_sources SET observation_id = ? WHERE id = ?",
                                       [(observation_id, ref["id"]) for ref in source_refs])
                    identity = _hash([record[field] for field in IDENTITY_FIELDS])
                    candidates.append((original["id"], observation_id, record["snapshot_id"], identity, zone))
            versions = {}
            for _, observation_id, snapshot_id, identity, zone in sorted(candidates):
                key = (snapshot_id, identity)
                versions[key] = versions.get(key, 0) + 1
                db.execute("UPDATE observations SET identity_key = ?, version = ?, source_timezone = ? WHERE id = ?",
                           (identity, versions[key], zone, observation_id))
            self._reselect_active(db)
            db.execute("CREATE UNIQUE INDEX one_active_observation ON observations(snapshot_id, identity_key) WHERE active = 1")
            db.execute("INSERT INTO state(key, value) VALUES('identity_schema_version', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                       (IDENTITY_SCHEMA_VERSION,))
            db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, detail_json TEXT NOT NULL)")
            db.execute("INSERT OR REPLACE INTO schema_migrations VALUES(?, ?, ?)",
                       (IDENTITY_SCHEMA_VERSION, _now(), _json({"original_observations": len(observations), "timezone_splits": split_count})))
            self._bump(db)

    @staticmethod
    def _snapshot(db, snapshot_id: int, writable: bool = False):
        row = db.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        if row is None:
            raise ValueError("Snapshot does not exist.")
        if writable and row["locked"]:
            raise ValueError("This snapshot is sealed and immutable. Create a newer snapshot to import data.")
        return row

    def snapshots(self) -> list[dict]:
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM snapshots ORDER BY id DESC")]

    def create_snapshot(self, name: str, is_baseline: bool = False,
                        status: str = "unverified", evidence: str = "") -> int:
        name = str(name).strip()
        if not name:
            raise ValueError("Give the snapshot a name.")
        if is_baseline and (status != "verified" or not str(evidence).strip()):
            raise ValueError("An original baseline requires verified status and evidence identifying its original files and reporting windows.")
        with self._transaction() as db:
            if is_baseline and db.execute("SELECT 1 FROM snapshots WHERE is_baseline = 1").fetchone():
                raise ValueError("An original baseline already exists; its identity cannot be replaced.")
            cursor = db.execute(
                "INSERT INTO snapshots(name, is_baseline, status, evidence, created_at) VALUES(?, ?, ?, ?, ?)",
                (name, int(is_baseline), "staging" if is_baseline else status, evidence, _now()),
            )
            self._bump(db)
            return int(cursor.lastrowid)

    def lock_snapshot(self, snapshot_id: int) -> None:
        """Seal a staged multi-file snapshot; the baseline becomes verified here."""
        with self._transaction() as db:
            snapshot = self._snapshot(db, snapshot_id)
            if snapshot["locked"]:
                return
            if snapshot["is_baseline"] and not db.execute(
                "SELECT 1 FROM observations WHERE snapshot_id = ? AND active = 1", (snapshot_id,)
            ).fetchone():
                raise ValueError("An empty baseline cannot be verified or sealed.")
            db.execute("UPDATE snapshots SET locked = 1, status = ? WHERE id = ?",
                       ("verified" if snapshot["is_baseline"] else snapshot["status"], snapshot_id))
            self._bump(db)

    def _normalize(self, row: dict, file_hash: str, worksheet: str) -> tuple[dict, list[dict]]:
        data = {field: _clean(row.get(field)) for field in OBSERVATION_FIELDS}
        if not data["metric"] or not data["platform"]:
            raise ValueError("Platform and metric are required.")
        data["platform"] = str(data["platform"]).strip().lower()
        data["metric"] = str(data["metric"]).strip()
        data["entity_type"] = data["entity_type"] or "account"
        data["status"] = data["status"] or ("missing" if data["value"] is None else "unverified")
        if data["value"] is not None:
            try:
                data["value"] = float(data["value"])
            except (ValueError, TypeError) as exc:
                raise ValueError("Value must be a parsed number or missing, not an unparsed string.") from exc
            if not math.isfinite(data["value"]):
                raise ValueError("Value must be finite or missing.")
        dimensions = data["dimensions"] or {}
        if isinstance(dimensions, str):
            try:
                dimensions = json.loads(dimensions)
            except json.JSONDecodeError as exc:
                raise ValueError("Dimensions must be a JSON object.") from exc
        if not isinstance(dimensions, dict):
            raise ValueError("Dimensions must be a JSON object.")
        data["dimensions"] = _json(dimensions)
        data["source_timezone"] = self._timezone(data["source_timezone"])
        warnings = []
        for id_field, name_field in [("account_id", "account_name"), ("entity_id", "entity_name")]:
            if not data[id_field]:
                scope = _hash([file_hash, worksheet, data["platform"], data.get(name_field), data["entity_type"]])[:20]
                data[id_field] = f"source:{scope}"
                warnings.append({"severity": "warning", "code": "source_scoped_identity",
                                 "message": f"Missing {id_field}; retained a source-scoped identity. Explicit mapping is needed to join other files.",
                                 "source_row": data["source_row"], "field": id_field})
        for field in OBSERVATION_FIELDS:
            if field != "value" and data[field] is not None:
                data[field] = str(data[field])
        return data, warnings

    def commit_import(self, snapshot_id: int, filename: str, raw_bytes: bytes,
                      observations: list[dict], worksheet: str = "", mapping=None,
                      issues=None) -> dict:
        """Commit original bytes, readings, validation, and each source-row link atomically.

        Baselines accept additive files during staging, but never a changed reading.
        Sealing ends staging. Exact reimports are harmless even after sealing.
        """
        if not isinstance(raw_bytes, bytes):
            raise ValueError("The unchanged source file must be supplied as bytes.")
        filename = Path(filename).name
        file_hash = hashlib.sha256(raw_bytes).hexdigest()
        mapping_json = _json(mapping or {})
        signature = _hash([snapshot_id, file_hash, worksheet, mapping_json])
        suffix = Path(filename).suffix.lower()
        suffix = suffix if suffix in {".csv", ".xlsx", ".json", ".tsv", ".txt"} else ".bin"
        archive = self.source_dir / (file_hash + suffix)
        counts = {"inserted": 0, "revised": 0, "duplicates": 0, "rejected": 0,
                  "total": len(observations), "idempotent": False}
        with self._transaction() as db:
            prior = db.execute("SELECT * FROM imports WHERE signature = ?", (signature,)).fetchone()
            if prior:
                if prior["retired"]:
                    raise ValueError("This exact import was retired. Correct its mapping or import into a new snapshot.")
                result = json.loads(prior["counts_json"])
                result.update(idempotent=True, import_id=prior["id"])
                return result
            snapshot = self._snapshot(db, snapshot_id, writable=True)
            if archive.exists():
                if hashlib.sha256(archive.read_bytes()).hexdigest() != file_hash:
                    raise ValueError("The archived source does not match its hash. Restore the archive before importing.")
            else:
                # Exclusive creation protects an existing original from accidental overwrite.
                with archive.open("xb") as output:
                    output.write(raw_bytes)
            cursor = db.execute(
                "INSERT INTO imports(snapshot_id, filename, file_hash, source_path, worksheet, mapping_json, signature, imported_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (snapshot_id, filename, file_hash, str(archive), worksheet, mapping_json, signature, _now()),
            )
            import_id = int(cursor.lastrowid)
            recorded_issues = list(issues or [])
            for raw_row in observations:
                try:
                    data, warnings = self._normalize(raw_row, file_hash, worksheet)
                except (ValueError, TypeError) as exc:
                    counts["rejected"] += 1
                    recorded_issues.append({"severity": "error", "code": "rejected_row", "message": str(exc),
                                            "source_row": raw_row.get("source_row"), "row": raw_row})
                    continue
                recorded_issues.extend(warnings)
                identity = _hash([data[field] for field in IDENTITY_FIELDS])
                previous = db.execute(
                    "SELECT * FROM observations WHERE snapshot_id = ? AND identity_key = ? AND active = 1",
                    (snapshot_id, identity),
                ).fetchone()
                identical = previous and previous["value"] == data["value"] and previous["status"] == data["status"]
                if identical:
                    observation_id = previous["id"]
                    counts["duplicates"] += 1
                else:
                    if previous and snapshot["is_baseline"]:
                        raise ValueError("A staged baseline contains a conflicting reading. Original baseline values cannot be revised; inspect the source before continuing.")
                    version = db.execute(
                        "SELECT COALESCE(MAX(version), 0) + 1 FROM observations WHERE snapshot_id = ? AND identity_key = ?",
                        (snapshot_id, identity),
                    ).fetchone()[0]
                    if previous:
                        db.execute("UPDATE observations SET active = 0 WHERE id = ?", (previous["id"],))
                        counts["revised"] += 1
                    else:
                        counts["inserted"] += 1
                    fields = ["snapshot_id", "import_id", "identity_key", "version", "active"] + OBSERVATION_FIELDS
                    values = [snapshot_id, import_id, identity, version, 1] + [data[field] for field in OBSERVATION_FIELDS]
                    cursor = db.execute(f"INSERT INTO observations ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", values)
                    observation_id = int(cursor.lastrowid)
                db.execute(
                    "INSERT INTO observation_sources(observation_id, import_id, source_row, captured_at, evidence_ref, source_url, payload_json) VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (observation_id, import_id, data["source_row"], data["captured_at"], data["evidence_ref"], data["source_url"], _json(raw_row)),
                )
            for issue in recorded_issues:
                if not isinstance(issue, dict):
                    issue = {"message": str(issue)}
                db.execute("INSERT INTO validation_issues(import_id, severity, code, message, source_row, payload_json) VALUES(?, ?, ?, ?, ?, ?)",
                           (import_id, issue.get("severity", "warning"), issue.get("code", "validation"),
                            str(issue.get("message", issue)), str(issue["source_row"]) if issue.get("source_row") is not None else None, _json(issue)))
            counts["import_id"] = import_id
            counts["issues"] = len(recorded_issues)
            counts["file_hash"] = file_hash
            db.execute("UPDATE imports SET counts_json = ? WHERE id = ?", (_json(counts), import_id))
            self._bump(db)
        return counts

    def read_observations(self, snapshot_id: int | None = None, include_history: bool = False) -> pd.DataFrame:
        conditions, params = [], []
        if snapshot_id is not None:
            conditions.append("o.snapshot_id = ?")
            params.append(snapshot_id)
        if not include_history:
            conditions.append("o.active = 1")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self._connect() as db:
            rows = db.execute("""SELECT o.*, s.name AS snapshot_name, i.filename AS source_filename,
                i.worksheet, i.file_hash, i.imported_at, i.retired AS import_retired
                FROM observations o JOIN snapshots s ON s.id = o.snapshot_id
                JOIN imports i ON i.id = o.import_id""" + where + " ORDER BY o.id", params).fetchall()
            references = {}
            for ref in db.execute("""SELECT os.observation_id, os.import_id, os.source_row, os.captured_at,
                os.evidence_ref, os.source_url, i.filename AS source_filename, i.worksheet,
                i.file_hash, i.imported_at, i.retired FROM observation_sources os
                JOIN imports i ON i.id = os.import_id JOIN observations o ON o.id = os.observation_id"""
                + where + " ORDER BY os.id", params):
                item = dict(ref)
                references.setdefault(item.pop("observation_id"), []).append(item)
            result = []
            for row in rows:
                item = dict(row)
                item.pop("identity_key", None)
                refs = references.get(row["id"], [])
                item["source_references"] = _json(refs)
                # A duplicate can remain valid after its initial import is retired.
                # The live view must identify a current supporting source, and use
                # that source's reported capture date rather than the import date.
                if not include_history:
                    live_refs = [ref for ref in refs if not ref["retired"]]
                    if live_refs:
                        selected = live_refs[-1]
                        for field in ("import_id", "source_row", "captured_at", "evidence_ref",
                                      "source_url", "source_filename", "worksheet", "file_hash", "imported_at"):
                            item[field] = selected[field]
                        item["import_retired"] = selected["retired"]
                result.append(item)
        return pd.DataFrame(result, columns=OBSERVATION_FIELDS + EXTRA_FIELDS)

    def retire_import(self, import_id: int) -> None:
        """Undo a mistaken import in an unlocked ordinary snapshot, preserving its audit trail."""
        with self._transaction() as db:
            row = db.execute("SELECT * FROM imports WHERE id = ?", (import_id,)).fetchone()
            if row is None:
                raise ValueError("Import does not exist.")
            snapshot = self._snapshot(db, row["snapshot_id"], writable=True)
            if snapshot["is_baseline"]:
                raise ValueError("Baseline imports cannot be retired or remapped.")
            if row["retired"]:
                return
            db.execute("UPDATE imports SET retired = 1 WHERE id = ?", (import_id,))
            self._reselect_active(db, row["snapshot_id"])
            self._bump(db)

    def imports(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT i.*, s.name AS snapshot_name FROM imports i JOIN snapshots s ON s.id = i.snapshot_id ORDER BY i.id DESC").fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["mapping"] = json.loads(item.pop("mapping_json"))
                item["counts"] = json.loads(item.pop("counts_json"))
                result.append(item)
            return result

    def inventory(self) -> list[dict]:
        return self.imports()

    def issues(self) -> list[dict]:
        with self._connect() as db:
            return [dict(row) for row in db.execute("""SELECT v.*, i.filename AS source_filename,
                i.worksheet, i.snapshot_id, i.retired AS import_retired FROM validation_issues v
                JOIN imports i ON i.id = v.import_id ORDER BY v.id DESC""")]

    def save_mapping(self, name: str, mapping: dict) -> None:
        if not str(name).strip():
            raise ValueError("A saved mapping needs a name.")
        with self._transaction() as db:
            db.execute("INSERT INTO mappings VALUES(?, ?, ?) ON CONFLICT(name) DO UPDATE SET mapping_json = excluded.mapping_json, updated_at = excluded.updated_at",
                       (str(name).strip(), _json(mapping), _now()))
            self._bump(db)

    def mappings(self) -> dict:
        with self._connect() as db:
            return {row["name"]: json.loads(row["mapping_json"]) for row in db.execute("SELECT * FROM mappings ORDER BY name")}

    def annotations(self) -> list[dict]:
        with self._connect() as db:
            return [dict(json.loads(row["payload_json"]), id=row["id"], updated_at=row["updated_at"]) for row in db.execute("SELECT * FROM annotations ORDER BY id")]

    def save_annotation(self, annotation: dict) -> int:
        payload = dict(annotation)
        annotation_id = payload.pop("id", None)
        payload.pop("updated_at", None)
        payload["origin"] = "local_user_annotation"
        with self._transaction() as db:
            if annotation_id is None:
                cursor = db.execute("INSERT INTO annotations(payload_json, updated_at) VALUES(?, ?)", (_json(payload), _now()))
                annotation_id = int(cursor.lastrowid)
            else:
                cursor = db.execute("UPDATE annotations SET payload_json = ?, updated_at = ? WHERE id = ?", (_json(payload), _now(), annotation_id))
                if cursor.rowcount != 1:
                    raise ValueError("Annotation does not exist.")
            self._bump(db)
            return int(annotation_id)

    def save_queue(self, rows: list[dict], source_ref: str, captured_at: str | None = None) -> int:
        """Preserve source queue fields verbatim; local notes never change source status."""
        with self._transaction() as db:
            for position, row in enumerate(rows):
                key = _hash([source_ref, row.get("source_row", row.get("id", position))])
                db.execute("""INSERT INTO collection_queue(id, source_ref, captured_at, imported_at, payload_json)
                    VALUES(?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET
                    source_ref = excluded.source_ref, captured_at = excluded.captured_at,
                    imported_at = excluded.imported_at, payload_json = excluded.payload_json""",
                           (key, source_ref, captured_at, _now(), _json(row)))
            self._bump(db)
        return len(rows)

    def queue(self) -> list[dict]:
        with self._connect() as db:
            result = []
            for row in db.execute("SELECT * FROM collection_queue ORDER BY rowid"):
                item = json.loads(row["payload_json"])
                item["source_record"] = dict(item)
                item.update({key: row[key] for key in ("id", "source_ref", "captured_at", "imported_at", "local_note")})
                result.append(item)
            return result

    def save_queue_note(self, row_id: str, note: str) -> None:
        with self._transaction() as db:
            cursor = db.execute("UPDATE collection_queue SET local_note = ? WHERE id = ?", (note, row_id))
            if cursor.rowcount != 1:
                raise ValueError("Collection queue row does not exist.")
            self._bump(db)

    def cache_token(self) -> str:
        with self._connect() as db:
            revision = db.execute("SELECT value FROM state WHERE key = 'revision'").fetchone()[0]
        return f"{self.path}:{revision}"

    def backup(self, destination: str | Path) -> Path:
        """Copy a consistent SQLite database plus original source files to a new directory."""
        target = Path(destination).expanduser().resolve()
        if target.exists():
            raise ValueError("Choose a new backup directory; existing backups are never overwritten.")
        target.mkdir(parents=True)
        with self._connect() as source, sqlite3.connect(target / self.path.name, factory=_ClosingConnection) as copy:
            source.backup(copy)
        shutil.copytree(self.source_dir, target / "sources")
        # Paths are portable after restoring a backup directory on another machine.
        with sqlite3.connect(target / self.path.name, factory=_ClosingConnection) as copy:
            for import_id, source_path in copy.execute("SELECT id, source_path FROM imports").fetchall():
                copy.execute("UPDATE imports SET source_path = ? WHERE id = ?", (str(target / "sources" / Path(source_path).name), import_id))
        return target
