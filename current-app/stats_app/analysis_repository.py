"""Immutable, separate SQLite snapshot of an audited analysis package.

Domain tables retain their own grains. Nothing is flattened into the original
observation stores, and package wording never establishes baseline membership.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import mimetypes
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sqlite3
import stat
import zipfile

import pandas as pd

from stats_app.storage import StorageError

SCHEMA_VERSION = 1
LABEL = "Cleaned analysis"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe_name(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise StorageError("Package paths must be relative forward-slash paths.")
    path = PurePosixPath(value)
    if path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts or str(path) != value:
        raise StorageError("Unsafe analysis package path.")
    return value


def _zip_package_files(zipped, package_name):
    """Resolve one complete flat or package-prefixed ZIP without path aliases."""
    files, directories, spellings = {}, set(), {}
    seen = set()
    for member in zipped.infolist():
        name = member.filename
        if member.orig_filename != name:
            raise StorageError("Unsafe or noncanonical analysis ZIP member: " + member.orig_filename)
        if name in seen:
            raise StorageError("Duplicate or ambiguous analysis ZIP member: " + name)
        seen.add(name)
        directory = member.is_dir()
        if directory and member.file_size:
            raise StorageError("Analysis ZIP directory members must not contain file payloads: " + name)
        relative = _safe_name(name[:-1] if directory else name)
        if relative == ".":
            raise StorageError("Unsafe analysis ZIP member: " + name)
        parts = PurePosixPath(relative).parts
        for part in parts:
            # These aliases are unsafe on the supported Windows filesystem,
            # even when a ZIP reader would distinguish their literal names.
            if (part.rstrip(" .") != part or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                    or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.IGNORECASE)):
                raise StorageError("Unsafe analysis ZIP member: " + name)
        for size in range(1, len(parts) + 1):
            spelling = "/".join(parts[:size])
            folded = spelling.casefold()
            if folded in spellings and spellings[folded] != spelling:
                raise StorageError("Case-ambiguous analysis ZIP member: " + name)
            spellings[folded] = spelling
        mode = member.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if kind not in {0, stat.S_IFREG, stat.S_IFDIR} or (kind == stat.S_IFDIR and not directory) or (kind == stat.S_IFREG and directory):
            raise StorageError("Unsafe file type in analysis ZIP member: " + name)
        if directory:
            directories.add(relative)
        else:
            files[relative] = member
    if not files:
        raise StorageError("Analysis ZIP contains no package files.")
    for name in set(files) | directories:
        parents = {str(parent) for parent in PurePosixPath(name).parents if str(parent) != "."}
        if (name in files and name in directories) or parents.intersection(files):
            raise StorageError("Conflicting file and directory analysis ZIP members: " + name)
    prefix = package_name + "/"
    prefixed = any(name.startswith(prefix) for name in files)
    if prefixed:
        if any(not name.startswith(prefix) for name in files) or any(name != package_name and not name.startswith(prefix) for name in directories):
            raise StorageError("Analysis ZIP must use one unambiguous package-root layout.")
        return {name[len(prefix):]: member for name, member in files.items()}
    return files


def _csv(raw, path):
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    header = next(reader, [])
    if not header:
        return [], []
    if len(header) != len(set(header)) or any(not c for c in header):
        raise StorageError(f"Duplicate/blank CSV columns: {path}")
    records = list(reader)
    if any(len(row) != len(header) for row in records):
        raise StorageError(f"Malformed cleaned/domain CSV structure: {path}")
    return header, records


def _dtype(column, values):
    """Conservative types: identity/raw text stays text; missing never means zero."""
    normalized = re.sub(r"[^a-z0-9]+", "_", column.lower()).strip("_")
    tokens = set(normalized.split("_"))
    if tokens & {"id", "ids", "uri", "url", "raw", "hash", "sha256", "filename", "file", "path", "label", "name", "title", "description", "handle", "username", "status", "scope", "class", "date", "timestamp", "time", "timezone", "start", "end"}:
        return "string"
    populated = [v for v in values if v != ""]
    if populated and set(populated) <= {"True", "False", "true", "false"}:
        return "boolean"
    if not populated:
        return "Float64" if normalized == "value" or normalized.startswith(("ci", "p_", "q_", "rho_")) else "string"
    number = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
    if not all(number.fullmatch(v) for v in populated):
        return "string"
    if any(re.fullmatch(r"[+-]?0\d+", v) for v in populated):
        return "string"
    parsed = [float(v) for v in populated]
    if not all(math.isfinite(v) for v in parsed):
        return "string"
    if all(re.fullmatch(r"[+-]?\d+", v) for v in populated) and all(-(2**63) <= int(v) < 2**63 for v in populated):
        return "Int64"
    return "Float64"


class AnalysisRepository:
    def __init__(self, dbpath):
        self.db_path = Path(dbpath).expanduser().resolve()
        if not self.db_path.is_file():
            raise StorageError("The registered cleaned analysis database is missing.")
        for suffix in ("-wal", "-journal"):
            sidecar = Path(str(self.db_path) + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                raise StorageError("The cleaned analysis snapshot must be a fixed checkpointed database.")
        with self._connection() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                raise StorageError("Unsupported analysis snapshot schema.")
            try:
                self._metadata = json.loads(db.execute("SELECT json FROM metadata WHERE key='package'").fetchone()[0])
            except (sqlite3.Error, TypeError, ValueError) as exc:
                raise StorageError("This is not a supported cleaned analysis database.") from exc

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.db_path.as_uri() + "?mode=ro&immutable=1", uri=True)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA query_only=ON")
            yield db
        finally:
            db.close()

    @property
    def metadata(self):
        return dict(self._metadata)

    @property
    def tables(self):
        with self._connection() as db:
            return [r[0] for r in db.execute("SELECT path FROM assets WHERE is_table=1 ORDER BY path")]

    def file_catalog(self):
        with self._connection() as db:
            return pd.read_sql_query("SELECT path,sha256,bytes,media_type,is_table,row_count,columns_json,types_json FROM assets ORDER BY path", db)

    def original_bytes(self, path):
        path = _safe_name(path)
        with self._connection() as db:
            row = db.execute("SELECT contents,sha256 FROM assets WHERE path=?", (path,)).fetchone()
        if row is None:
            raise StorageError("No retained package file at " + path)
        raw = bytes(row["contents"])
        if _sha(raw) != row["sha256"]:
            raise StorageError("Analysis source SHA-256 verification failed.")
        return raw

    def text(self, path):
        return self.original_bytes(path).decode("utf-8-sig")

    def table(self, path, *, raw=False):
        path = _safe_name(path)
        with self._connection() as db:
            asset = db.execute("SELECT * FROM assets WHERE path=? AND is_table=1", (path,)).fetchone()
            if asset is None:
                raise StorageError("No parsed domain CSV at " + path)
            if _sha(bytes(asset["contents"])) != asset["sha256"]:
                raise StorageError("Analysis source SHA-256 verification failed.")
            values = [json.loads(r[0]) for r in db.execute("SELECT row_json FROM analysis_rows WHERE asset_path=? ORDER BY csv_record", (path,))]
        header = json.loads(asset["columns_json"]); types = json.loads(asset["types_json"])
        if len(values) != asset["row_count"]:
            raise StorageError("Persisted analysis row count differs from the source manifest.")
        source_header, source_values = _csv(bytes(asset["contents"]), path)
        if header != source_header or values != source_values:
            raise StorageError("Persisted analysis rows differ from their unchanged source CSV.")
        frame = pd.DataFrame(values, columns=header)
        if not raw:
            for column in header:
                series = frame[column].replace("", pd.NA)
                dtype = types[column]
                if dtype == "boolean":
                    frame[column] = series.map({"True": True, "False": False, "true": True, "false": False}).astype("boolean")
                elif dtype in {"Int64", "Float64"}:
                    frame[column] = pd.to_numeric(series, errors="raise").astype(dtype)
                else:
                    frame[column] = series.astype("string")
        frame.attrs.update(package_path=path, source_sha256=asset["sha256"], csv_record_offset=2,
                           snapshot_label=self._metadata["label"], baseline_status="unverified")
        return frame

    def row_provenance(self, path):
        frame = self.table(path, raw=True)
        columns = [c for c in frame.columns if any(token in c.lower() for token in ("source", "retriev", "snapshot", "reporting", "scope", "status"))]
        result = frame[columns].copy()
        result.insert(0, "package_csv_record", range(2, len(frame) + 2))
        result.insert(0, "package_file", path)
        result["package_file_sha256"] = frame.attrs["source_sha256"]
        return result

    def original_zip(self):
        with self._connection() as db:
            row = db.execute("SELECT contents,sha256 FROM original_zip WHERE id=1").fetchone()
        raw = bytes(row[0])
        if _sha(raw) != row[1]:
            raise StorageError("Original analysis ZIP verification failed.")
        return raw


def analysis_registration_records(registry):
    """Normalize the legacy pointer and version list without modifying either.

    The active pointer remains a complete record so older clients can keep
    loading it. A legacy pointer acquires a stable key from its evidence folder
    only in this returned view, until an explicit promotion writes the registry.
    """
    if not isinstance(registry, dict):
        raise StorageError("The archive registry must be a JSON object.")
    versions = registry.get("analysis_versions", [])
    if not isinstance(versions, list):
        raise StorageError("The analysis versions registration must be a list.")

    def normalize(item, *, legacy=False):
        if not isinstance(item, dict):
            raise StorageError("The analysis package registration must be an object.")
        result = dict(item)
        for field in ("database", "evidence_root"):
            result[field] = _safe_name(item.get(field))
        key = item.get("key")
        if key is None and legacy:
            folder = PurePosixPath(result["evidence_root"]).name
            key = folder if re.fullmatch(r"[A-Za-z0-9_-]+", folder) else "legacy-" + _sha(result["database"].encode())[:12]
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            raise StorageError("Analysis version keys must contain only letters, numbers, underscores or hyphens.")
        result["key"] = key
        result.pop("active", None)
        return result

    records = [normalize(item) for item in versions]
    if len({item["key"] for item in records}) != len(records) or len({item["database"] for item in records}) != len(records):
        raise StorageError("Analysis version keys and database paths must be unique.")
    active = registry.get("analysis_package")
    if active is not None:
        active = normalize(active, legacy=True)
        matching = next((item for item in records if item["key"] == active["key"]), None)
        if matching is not None and matching != active:
            raise StorageError("The active analysis pointer conflicts with its registered version.")
        if matching is None:
            if records or "analysis_versions" in registry:
                raise StorageError("The active analysis pointer must name a registered version.")
            records.append(active)
    return [{**item, "active": active is not None and item["key"] == active["key"]} for item in records]


def _registered_analysis_paths(root, item):
    resolved = {}
    for field in ("database", "evidence_root"):
        path = root / _safe_name(item.get(field))
        if not path.resolve().is_relative_to(root):
            raise StorageError("Registered analysis paths must stay within the data directory.")
        for component in (path, *path.parents):
            if component.is_symlink() or (hasattr(component, "is_junction") and component.is_junction()):
                raise StorageError("Registered analysis paths must not contain links or junctions.")
            if component == root:
                break
        resolved[field] = path
    if not resolved["evidence_root"].is_dir():
        raise StorageError("The registered analysis evidence directory is missing.")
    if resolved["evidence_root"] == root or not resolved["database"].is_relative_to(resolved["evidence_root"]):
        raise StorageError("Analysis databases must live in dedicated registered evidence directories.")
    if not resolved["database"].is_file():
        raise StorageError("The registered cleaned analysis database is missing.")
    return resolved


def list_registered_analyses(data_dir):
    """List explicitly registered immutable versions, with an active flag."""
    root = Path(data_dir).expanduser().resolve()
    registry_path = root / "archive_registry.json"
    if not registry_path.exists():
        return []
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StorageError("Cannot read the registered analysis configuration.") from exc
    records = analysis_registration_records(registry)
    for item in records:
        _registered_analysis_paths(root, item)
    return records


def load_registered_analysis(data_dir, key=None):
    """Load the active package or a named older version, always without writes."""
    root = Path(data_dir).expanduser().resolve()
    records = list_registered_analyses(root)
    item = next((item for item in records if item["key"] == key), None) if key is not None else next((item for item in records if item["active"]), None)
    if item is None:
        if key is not None:
            raise StorageError("No registered analysis version named " + str(key))
        return None
    resolved = _registered_analysis_paths(root, item)
    repository = AnalysisRepository(resolved["database"])
    repository.evidence_root = resolved["evidence_root"]
    repository.registered_label = str(item.get("label") or repository.metadata["label"])
    repository.registered_key = item["key"]
    return repository


def stage_analysis_package(package_root, zip_path, output_dir, source_url="", *, label=None, metadata=None):
    """Persist one exact package, refusing replacement and verifying its raw audit."""
    extra_metadata = dict(metadata or {})
    protected = {"label", "schema_version", "package_sha256", "zip_filename", "zip_sha256", "source_url", "loaded_at", "baseline_status", "files", "parsed_tables", "parsed_records", "raw_hashes_verified", "all_package_files_match_zip", "package_reported_validation", "database", "idempotent", "integrity"}
    if extra_metadata.keys() & protected:
        raise StorageError("Analysis metadata cannot override generated integrity fields or baseline status.")
    try:
        extra_metadata = json.loads(json.dumps(extra_metadata, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise StorageError("Analysis metadata must contain finite JSON values.") from exc
    if label is not None and (not isinstance(label, str) or not label.strip()):
        raise StorageError("An analysis snapshot label must be nonempty text.")
    root, archive, output = Path(package_root).resolve(), Path(zip_path).resolve(), Path(output_dir).resolve()
    if output == root or root in output.parents:
        raise StorageError("Stage analysis outside the immutable package directory.")
    zip_bytes = archive.read_bytes(); zip_hash = _sha(zip_bytes)
    manifest = json.loads((root / "raw_sha256.json").read_text(encoding="utf-8"))
    for entry in manifest:
        path = root / _safe_name(entry["path"])
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise StorageError("Raw source audit escapes the package directory.")
        raw = path.read_bytes()
        if len(raw) != entry["bytes"] or _sha(raw) != entry["sha256"]:
            raise StorageError("Raw package audit failed: " + entry["path"])
    assets = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zipped:
        zip_files = _zip_package_files(zipped, root.name)
        extracted = {}
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise StorageError("Package must not contain symbolic links or junctions.")
            if not path.is_file(): continue
            relative = _safe_name(path.relative_to(root).as_posix())
            extracted[relative] = path
        omitted = sorted(set(zip_files) - set(extracted))
        extra = sorted(set(extracted) - set(zip_files))
        if omitted or extra:
            raise StorageError("Extracted package differs from original ZIP inventory; missing: "
                               + ", ".join(omitted) + "; extra: " + ", ".join(extra))
        for relative, path in extracted.items():
            raw = path.read_bytes()
            if zipped.read(zip_files[relative]) != raw:
                raise StorageError("Extracted package differs from original ZIP: " + relative)
            is_table = path.suffix.lower() == ".csv" and not relative.startswith("raw/")
            header, records = _csv(raw, relative) if is_table else ([], [])
            types = {column: _dtype(column, [r[i] for r in records]) for i, column in enumerate(header)}
            assets.append((relative, raw, _sha(raw), is_table, header, records, types))
    package_hash = _sha(json.dumps([(a[0], a[2]) for a in assets], separators=(",", ":")).encode())
    database = output / "analysis.sqlite3"
    if database.exists():
        existing = AnalysisRepository(database)
        if existing.metadata.get("package_sha256") != package_hash or existing.metadata.get("zip_sha256") != zip_hash:
            raise StorageError("A different analysis snapshot already exists; choose a new output directory.")
        requested = {**extra_metadata, **({"label": label} if label is not None else {}), **({"source_url": source_url} if source_url else {})}
        if any(existing.metadata.get(key) != value for key, value in requested.items()):
            raise StorageError("An existing analysis snapshot has different metadata; choose a new output directory.")
        return {**existing.metadata, "database": str(database), "idempotent": True}
    if output.exists() and any(output.iterdir()):
        raise StorageError("Analysis output directory must be new or empty.")
    output.mkdir(parents=True, exist_ok=True)
    metadata = {"label": label or LABEL, "schema_version": SCHEMA_VERSION, "package_sha256": package_hash,
                "zip_filename": archive.name, "zip_sha256": zip_hash, "source_url": source_url,
                "loaded_at": datetime.now(timezone.utc).isoformat(), "activity_endpoint": None,
                "retrieval_vintage": None, "baseline_status": "unverified",
                "baseline_note": "Package source labels are preserved verbatim; original baseline membership remains unverified and older stores are unchanged.",
                "files": len(assets), "parsed_tables": sum(a[3] for a in assets), "parsed_records": sum(len(a[5]) for a in assets),
                "raw_hashes_verified": len(manifest), "all_package_files_match_zip": True,
                "package_reported_validation": json.loads((root / "audit/final_validation.json").read_text(encoding="utf-8")), **extra_metadata}
    with database.open("xb"):
        pass
    db = sqlite3.connect(database)
    try:
        db.executescript("""
            CREATE TABLE metadata(key TEXT PRIMARY KEY,json TEXT NOT NULL);
            CREATE TABLE original_zip(id INTEGER PRIMARY KEY,filename TEXT,sha256 TEXT,source_url TEXT,contents BLOB);
            CREATE TABLE assets(path TEXT PRIMARY KEY,sha256 TEXT NOT NULL,bytes INTEGER,media_type TEXT,
                is_table INTEGER,row_count INTEGER,columns_json TEXT,types_json TEXT,contents BLOB NOT NULL);
            CREATE TABLE analysis_rows(asset_path TEXT NOT NULL REFERENCES assets(path),csv_record INTEGER NOT NULL,
                row_json TEXT NOT NULL,PRIMARY KEY(asset_path,csv_record));
        """)
        with db:
            db.execute("INSERT INTO metadata VALUES('package',?)", (json.dumps(metadata, ensure_ascii=False),))
            db.execute("INSERT INTO original_zip VALUES(1,?,?,?,?)", (archive.name, zip_hash, source_url, zip_bytes))
            for relative, raw, digest, is_table, header, records, types in assets:
                db.execute("INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)", (relative, digest, len(raw), mimetypes.guess_type(relative)[0] or "application/octet-stream",
                           int(is_table), len(records), json.dumps(header), json.dumps(types), raw))
                db.executemany("INSERT INTO analysis_rows VALUES(?,?,?)", ((relative, i, json.dumps(row, ensure_ascii=False, separators=(",", ":"))) for i, row in enumerate(records, 2)))
            db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise StorageError("Staged analysis SQLite integrity failed.")
    finally:
        db.close()
    repo = AnalysisRepository(database)
    if _sha(repo.original_zip()) != zip_hash:
        raise StorageError("Staged ZIP hash differs")
    report = {**metadata, "database": str(database), "idempotent": False, "integrity": "ok"}
    (output / "analysis_package_import.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", required=True, type=Path)
    parser.add_argument("--zip-path", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-url", default="")
    parser.add_argument("--label")
    parser.add_argument("--metadata-json", type=Path, help="Optional JSON provenance, retrieval vintage, endpoint and version lineage")
    args = parser.parse_args()
    report = stage_analysis_package(args.package_root, args.zip_path, args.output_dir, args.source_url, label=args.label,
                                    metadata=json.loads(args.metadata_json.read_text(encoding="utf-8")) if args.metadata_json else None)
    print(json.dumps({k: report[k] for k in ("database", "files", "parsed_tables", "parsed_records", "raw_hashes_verified", "idempotent")}, indent=2))
