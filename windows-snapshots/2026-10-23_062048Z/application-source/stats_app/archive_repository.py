"""Read-only view of the preserved handoff database in the Windows dashboard.

The handoff schema deliberately permits unknown lifetime reporting windows and
keeps version/source histories. It must not be opened through a writable store
or flattened into the local import schema. This adapter changes display aliases
only; the SQLite database and every archived export stay byte-for-byte intact.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3

import pandas as pd

from stats_app.storage import RECORD_FIELDS, StorageError


PLATFORMS = {"spotify": "Spotify", "facebook": "Facebook", "instagram": "Instagram",
             "tiktok": "TikTok", "tiktok_for_artists": "TikTok for Artists"}
SNAPSHOT_COLUMNS = ["label", "is_baseline", "sealed", "captured_at", "created_at",
                    "observation_count", "import_count", "snapshot_id", "status", "evidence"]
EXTRA_COLUMNS = ["observation_id", "snapshot_label", "source_names", "source_count", "imported_at",
                 "account_id", "account_name", "published_at", "source_url", "source_status",
                 "source_platform", "source_value", "source_references", "source_filename", "source_path",
                 "file_hash", "snapshot_id", "version", "active", "dimensions"]


class ImportedArchiveRepository:
    """Project a fixed, verified recovery copy without performing any writes.

    Snapshot/observation identifiers belong to this backend only. The caller
    must select a repository before a snapshot; never merge IDs across stores.
    ``evidence_root`` identifies the extracted package for UI/reporting use.
    Archived sources are located by their hash filename, never by old absolute
    machine-specific paths recorded in the original database.
    """

    def __init__(self, db_path: str | Path, source_dir: str | Path,
                 evidence_root: str | Path | None = None):
        self.db_path = Path(db_path).expanduser().resolve()
        self.source_dir = Path(source_dir).expanduser().resolve()
        self.evidence_root = Path(evidence_root).expanduser().resolve() if evidence_root else self.db_path.parent
        if not self.db_path.is_file():
            raise StorageError("The preserved handoff database is missing. Restore its verified recovery copy; do not create an empty replacement.")
        # immutable=1 is appropriate only for a fixed, fully checkpointed copy.
        wal = Path(str(self.db_path) + "-wal")
        if wal.exists() and wal.stat().st_size:
            raise StorageError("The handoff database has a WAL file. Supply a consistent checkpointed recovery copy before reading it.")
        with self._connection() as db:
            required = {"snapshots", "imports", "observations", "observation_sources",
                        "validation_issues", "collection_queue"}
            available = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required.issubset(available):
                raise StorageError("This is not a supported handoff database; no migration or replacement was attempted.")

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.db_path.as_uri() + "?mode=ro&immutable=1", uri=True)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def _snapshot_id(db, label):
        rows = db.execute("SELECT id FROM snapshots WHERE name=?", (str(label),)).fetchall()
        if len(rows) != 1:
            raise StorageError("The archived snapshot name is missing or ambiguous; select one identified snapshot.")
        return rows[0][0]

    def list_snapshots(self) -> pd.DataFrame:
        with self._connection() as db:
            rows = db.execute("""
                SELECT s.name AS label,s.is_baseline,s.locked AS sealed,'' AS captured_at,s.created_at,
                    (SELECT COUNT(*) FROM observations o WHERE o.snapshot_id=s.id AND o.active=1) AS observation_count,
                    (SELECT COUNT(*) FROM imports i WHERE i.snapshot_id=s.id) AS import_count,
                    s.id AS snapshot_id,s.status,s.evidence
                FROM snapshots s ORDER BY s.id
            """).fetchall()
        return pd.DataFrame([dict(row) for row in rows], columns=SNAPSHOT_COLUMNS)

    def observations(self, snapshot_label: str) -> pd.DataFrame:
        with self._connection() as db:
            snapshot_id = self._snapshot_id(db, snapshot_label)
            rows = db.execute("""
                SELECT o.*,i.filename AS source_filename,i.source_path,i.worksheet,i.file_hash,i.imported_at
                FROM observations o JOIN imports i ON i.id=o.import_id
                WHERE o.snapshot_id=? AND o.active=1 ORDER BY o.id
            """, (snapshot_id,)).fetchall()
            sources = db.execute("""
                SELECT os.observation_id,os.import_id,os.source_row,os.captured_at,os.evidence_ref,
                    os.source_url,i.filename AS source_filename,i.source_path,i.worksheet,
                    i.file_hash,i.imported_at,i.retired
                FROM observation_sources os JOIN imports i ON i.id=os.import_id
                JOIN observations o ON o.id=os.observation_id
                WHERE o.snapshot_id=? AND o.active=1 ORDER BY os.id
            """, (snapshot_id,)).fetchall()
        references = {}
        for source in sources:
            item = dict(source)
            references.setdefault(item.pop("observation_id"), []).append(item)
        result = []
        for row in rows:
            original = dict(row)
            refs = references.get(original["id"], [])
            live = [ref for ref in refs if not ref["retired"]]
            # Match the recovered store's live view, including a valid duplicate
            # whose first supporting import was later retired.
            if live:
                for key, value in live[-1].items():
                    if key != "retired":
                        original[key] = value
            item = {column: original.get(column, "") for column in (*RECORD_FIELDS, *EXTRA_COLUMNS)}
            item.update(
                observation_id=original["id"], snapshot_label=snapshot_label,
                account=original.get("account_id") or "", source_status=original["status"],
                source_value=original["value"],
                value=original["value"] if original["status"] == "available" else None,
                status="observed" if original["status"] == "available" else original["status"],
                source_platform=original["platform"],
                platform=PLATFORMS.get(original["platform"], original["platform"]),
                dimensions_json=original.get("dimensions") or "{}",
                source_names="; ".join(dict.fromkeys(ref["source_filename"] for ref in live)),
                source_count=len({ref["import_id"] for ref in live}), source_references=json.dumps(refs, ensure_ascii=False),
            )
            # Blank means unknown. Do not substitute publication, acquisition,
            # or import dates for missing lifetime reporting windows.
            for field in RECORD_FIELDS:
                if field not in {"value", "source_row"} and item.get(field) is None:
                    item[field] = ""
            result.append(item)
        return pd.DataFrame(result, columns=list(dict.fromkeys((*RECORD_FIELDS, *EXTRA_COLUMNS))))

    def observation_provenance(self, observation_id: int) -> pd.DataFrame:
        with self._connection() as db:
            return pd.read_sql_query("""
                SELECT os.source_row,i.worksheet,os.evidence_ref,os.captured_at,os.source_url,
                    os.payload_json,i.filename AS source_name,i.file_hash AS source_hash,
                    i.source_path,i.imported_at,i.mapping_json AS provenance_json,i.retired
                FROM observation_sources os JOIN imports i ON i.id=os.import_id
                WHERE os.observation_id=? ORDER BY os.id
            """, db, params=(int(observation_id),))

    def _source_path(self, source_hash: str, recorded_path: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", str(source_hash)):
            raise StorageError("The archived source hash is invalid.")
        name = PurePosixPath(str(recorded_path).replace("\\", "/")).name
        if name != source_hash and not name.startswith(source_hash + "."):
            raise StorageError("The archived source filename does not match its identity hash.")
        path = (self.source_dir / name).resolve()
        if not path.is_relative_to(self.source_dir):
            raise StorageError("The archived source resolves outside its source directory.")
        return path

    def original_source(self, source_hash: str) -> bytes:
        with self._connection() as db:
            row = db.execute("SELECT source_path FROM imports WHERE file_hash=? ORDER BY id LIMIT 1", (source_hash,)).fetchone()
        if row is None:
            raise StorageError("The archived source hash was not found.")
        path = self._source_path(source_hash, row["source_path"])
        if not path.is_file():
            raise StorageError("The archived original source is missing from the recovery copy.")
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != source_hash:
            raise StorageError("The archived original failed its SHA-256 check; no file was changed.")
        return raw

    def import_history(self) -> pd.DataFrame:
        with self._connection() as db:
            rows = db.execute("""
                SELECT i.*,s.name AS snapshot_label,s.is_baseline,s.locked AS sealed
                FROM imports i JOIN snapshots s ON s.id=i.snapshot_id ORDER BY i.id DESC
            """).fetchall()
            captures = {}
            for row in db.execute("SELECT import_id,captured_at FROM observation_sources GROUP BY import_id,captured_at"):
                captures.setdefault(row["import_id"], []).append(row["captured_at"] or "")
        result = []
        for row in rows:
            item = dict(row)
            counts = json.loads(item["counts_json"])
            captured = captures.get(item["id"], [])
            path = self._source_path(item["file_hash"], item["source_path"])
            provenance = {"mapping": json.loads(item["mapping_json"]), "counts": counts,
                          "recorded_source_path": item["source_path"], "retired": item["retired"],
                          "backend": "preserved_handoff", "source_capture_timestamps": captured}
            item.update(import_id=item["id"], source_name=item["filename"], source_hash=item["file_hash"],
                        byte_count=path.stat().st_size if path.is_file() else None,
                        captured_at=captured[0] if len(captured) == 1 else "",
                        imported_rows=counts.get("inserted", 0), duplicate_rows=counts.get("duplicates", 0),
                        source_context=item["worksheet"], interpretation_hash=item["signature"],
                        provenance_json=json.dumps(provenance, ensure_ascii=False))
            result.append(item)
        return pd.DataFrame(result)

    def coverage_issues(self, snapshot_label: str) -> pd.DataFrame:
        with self._connection() as db:
            snapshot_id = self._snapshot_id(db, snapshot_label)
            return pd.read_sql_query("""
                SELECT v.*,i.filename AS source_name,i.worksheet,i.file_hash,i.retired AS import_retired
                FROM validation_issues v JOIN imports i ON i.id=v.import_id
                WHERE i.snapshot_id=? ORDER BY v.id
            """, db, params=(snapshot_id,))

    def collection_queue(self) -> pd.DataFrame:
        with self._connection() as db:
            rows = db.execute("SELECT * FROM collection_queue ORDER BY rowid").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            payload = json.loads(item["payload_json"])
            if isinstance(payload, dict):
                # Original payload remains available even if a friendly field
                # conflicts with audit metadata such as source_ref.
                item = {**payload, **item}
            result.append(item)
        return pd.DataFrame(result)
