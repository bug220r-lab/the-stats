"""Preserve a Shopify collection as a separate immutable SQLite snapshot.

Shopify report tables retain their native grains and string tokens.  This store
does not change the existing analysis, observation database, or source bytes.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sqlite3
import stat
import tempfile

import pandas as pd

from stats_app.storage import StorageError


SCHEMA_VERSION = 1
REGISTRY_FILENAME = "shopify_collections.json"
STATUSES = {"collected", "partial", "verified_empty", "unavailable", "blocked"}
KEY_PATTERN = r"shopify-\d{8}(?:-[a-z0-9]+)*"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise StorageError("Shopify asset paths must use relative forward-slash names.")
    path = PurePosixPath(value)
    if (path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts
            or str(path) != value or value == "."):
        raise StorageError("Unsafe Shopify asset path: " + value)
    for part in path.parts:
        if (part.rstrip(" .") != part or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.I)):
            raise StorageError("Unsafe Shopify asset path: " + value)
    return value


def _no_links(path, root):
    path, root = Path(path), Path(root)
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise StorageError("Shopify path leaves its collection directory.") from exc
    current = root
    for part in ("", *relative.parts):
        current = current / part if part else current
        if current.exists() or current.is_symlink():
            info = current.lstat()
            if current.is_symlink() or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise StorageError("Linked Shopify collection paths are not supported.")
    return path


def _read_csv(raw, name):
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        header = next(reader, [])
        if not header or any(not value.strip() for value in header):
            raise StorageError("Shopify table needs nonempty headers: " + name)
        normalized = [value.strip().casefold() for value in header]
        if len(set(normalized)) != len(header):
            raise StorageError("Duplicate Shopify table headers: " + name)
        rows = []
        for number, row in enumerate(reader, 2):
            if not row:
                continue  # CSV permits blank separator/trailing lines; exact bytes remain archived.
            if len(row) != len(header):
                raise StorageError(f"Shopify table {name} row {number} has the wrong field count.")
            rows.append(row)
        return header, rows
    except (UnicodeError, csv.Error) as exc:
        raise StorageError("Cannot parse Shopify UTF-8 CSV: " + name) from exc


def _package(directory):
    root = Path(directory).absolute()
    _no_links(root, root)
    if not root.is_dir():
        raise StorageError("Shopify package directory does not exist.")
    assets, folded = {}, set()
    for path in sorted(root.rglob("*")):
        _no_links(path, root)
        if path.is_dir():
            continue
        if not path.is_file():
            raise StorageError("Shopify package contains a non-regular file.")
        name = _safe_path(path.relative_to(root).as_posix())
        if name.casefold() in folded:
            raise StorageError("Case-ambiguous Shopify asset name.")
        folded.add(name.casefold())
        assets[name] = path.read_bytes()
    try:
        manifest = json.loads(assets["manifest.json"].decode("utf-8-sig"))
    except (KeyError, ValueError, UnicodeError) as exc:
        raise StorageError("Shopify package needs a valid manifest.json.") from exc
    parsed = _validate_manifest(manifest, assets)
    digest = _sha(json.dumps([(name, _sha(raw)) for name, raw in sorted(assets.items())],
                             ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return manifest, assets, parsed, digest


def _validate_manifest(manifest, assets):
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise StorageError("Unsupported Shopify manifest schema.")
    for field in ("assets", "files"):
        declared = manifest.get(field)
        if declared is None or declared == []:
            continue
        if not isinstance(declared, list):
            raise StorageError("Shopify declared file inventory must be a list.")
        names = set()
        for item in declared:
            if not isinstance(item, dict):
                raise StorageError("Shopify declared file inventory needs hash records.")
            name = _safe_path(item.get("path"))
            if name in names or name == "manifest.json" or name not in assets:
                raise StorageError("Shopify declared file inventory is duplicated or incomplete.")
            names.add(name)
            raw = assets[name]
            size = item.get("bytes", item.get("size"))
            if item.get("sha256") != _sha(raw) or type(size) is not int or size != len(raw):
                raise StorageError("Shopify declared source hash/size differs: " + name)
        if names != set(assets) - {"manifest.json"}:
            raise StorageError("Shopify declared file inventory omits package assets.")
    if not re.fullmatch(KEY_PATTERN, str(manifest.get("collection_key", ""))):
        raise StorageError("Shopify collection key must include its actual collection date.")
    try:
        captured = datetime.fromisoformat(manifest["collected_at"].replace("Z", "+00:00"))
        if captured.tzinfo is None:
            raise ValueError("offset required")
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        raise StorageError("Shopify collected_at needs an ISO timestamp with UTC offset.") from exc
    if not isinstance(manifest.get("store"), dict) or not manifest["store"].get("domain"):
        raise StorageError("Shopify store identity must include its verified domain.")
    privacy = manifest.get("privacy", {})
    if not isinstance(privacy, dict) or privacy.get("customer_pii_included") is not False:
        raise StorageError("Explicitly confirm this Shopify collection excludes customer personal information.")
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise StorageError("Shopify manifest needs a dataset status inventory.")
    ids, parsed = set(), {}
    for dataset in datasets:
        if not isinstance(dataset, dict):
            raise StorageError("Shopify dataset metadata must be an object.")
        key = dataset.get("dataset_id")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", key) or key in ids:
            raise StorageError("Shopify dataset IDs must be unique stable names.")
        ids.add(key)
        status = str(dataset.get("status", "")).replace(" ", "_")
        if status not in STATUSES:
            raise StorageError("Unsupported Shopify dataset status: " + str(status))
        if status in {"partial", "unavailable", "blocked"} and not dataset.get("reason"):
            raise StorageError("Limited Shopify datasets need an explicit reason: " + key)
        path = dataset.get("path")
        if path:
            path = _safe_path(path)
            if path not in assets or not path.lower().endswith(".csv"):
                raise StorageError("Shopify dataset table is absent or is not CSV: " + key)
            if path not in parsed:
                parsed[path] = _read_csv(assets[path], path)
            count = len(parsed[path][1])
            if "row_count" in dataset and (type(dataset["row_count"]) is not int or dataset["row_count"] != count):
                raise StorageError("Shopify declared row_count differs from source table: " + key)
            if status == "verified_empty" and count:
                raise StorageError("Verified empty Shopify dataset contains rows: " + key)
            if status == "collected" and not count:
                raise StorageError("Empty Shopify datasets need verified_empty status: " + key)
            if status in {"unavailable", "blocked"} and count:
                raise StorageError("Unavailable Shopify datasets cannot expose collected rows: " + key)
            primary_key = dataset.get("primary_key", [])
            if (not isinstance(primary_key, list) or any(not isinstance(field, str) for field in primary_key)
                    or len(set(primary_key)) != len(primary_key)):
                raise StorageError("Shopify primary_key must list unique literal table columns: " + key)
            if primary_key:
                header, rows = parsed[path]
                if not set(primary_key).issubset(header):
                    raise StorageError("Shopify primary key columns are absent: " + key)
                positions = [header.index(field) for field in primary_key]
                seen = set()
                for row in rows:
                    identity = tuple(row[position] for position in positions)
                    if any(not value.strip() for value in identity) or identity in seen:
                        raise StorageError("Shopify primary key is blank or duplicated: " + key)
                    seen.add(identity)
        elif status in {"collected", "verified_empty"}:
            raise StorageError("Collected Shopify datasets need a table with its source schema: " + key)
        source_paths = dataset.get("source_paths", [])
        if not isinstance(source_paths, list):
            raise StorageError("Shopify source_paths must list retained assets: " + key)
        for source in source_paths:
            if _safe_path(source) not in assets:
                raise StorageError("Shopify dataset source asset is missing: " + source)
        bounds = {}
        for field in ("reporting_start", "reporting_end"):
            value = dataset.get(field)
            if value:
                try:
                    bounds[field] = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except (ValueError, TypeError, AttributeError) as exc:
                    raise StorageError("Invalid Shopify reporting boundary: " + key) from exc
        if len(bounds) == 2:
            start, end = bounds["reporting_start"], bounds["reporting_end"]
            if bool(start.tzinfo) != bool(end.tzinfo):
                raise StorageError("Shopify reporting boundaries need compatible timezone precision: " + key)
            if start > end:
                raise StorageError("Shopify reporting bounds are reversed: " + key)
    return parsed


def _registry(root):
    path = _no_links(root / REGISTRY_FILENAME, root)
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "collections": []}
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StorageError("Cannot read Shopify collection registry.") from exc
    if (not isinstance(registry, dict) or registry.get("schema_version") != SCHEMA_VERSION
            or not isinstance(registry.get("collections"), list)):
        raise StorageError("Unsupported Shopify collection registry.")
    seen = set()
    for row in registry["collections"]:
        if not isinstance(row, dict) or not re.fullmatch(KEY_PATTERN, str(row.get("key", ""))):
            raise StorageError("Invalid Shopify collection registration.")
        key = row["key"]
        if key in seen or row.get("database") != f"collections/{key}/shopify.sqlite3" or row.get("evidence_root") != f"collections/{key}":
            raise StorageError("Conflicting Shopify collection registration.")
        seen.add(key)
        if any(not re.fullmatch(r"[0-9a-f]{64}", str(row.get(field, "")))
               for field in ("database_sha256", "package_sha256")):
            raise StorageError("Shopify registration needs exact asset hashes.")
    return registry


def _atomic_json(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix=".shopify-registry-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def _lock(root):
    path = _no_links(root / ".shopify_import.lock", root)
    try:
        handle = path.open("x", encoding="ascii")
    except FileExistsError as exc:
        raise StorageError("Another Shopify import is active.") from exc
    try:
        handle.write(str(os.getpid()))
        handle.close()
        yield
    finally:
        handle.close()
        path.unlink()


def _write_database(path, metadata, assets, parsed):
    with path.open("xb"):
        pass
    db = sqlite3.connect(path)
    try:
        db.executescript("""
            CREATE TABLE metadata(key TEXT PRIMARY KEY,json TEXT NOT NULL);
            CREATE TABLE assets(path TEXT PRIMARY KEY,sha256 TEXT NOT NULL,bytes INTEGER NOT NULL,
                media_type TEXT NOT NULL,is_table INTEGER NOT NULL,row_count INTEGER,
                columns_json TEXT,contents BLOB NOT NULL);
            CREATE TABLE source_rows(asset_path TEXT NOT NULL,csv_record INTEGER NOT NULL,row_json TEXT NOT NULL,
                PRIMARY KEY(asset_path,csv_record),FOREIGN KEY(asset_path) REFERENCES assets(path));
        """)
        with db:
            db.execute("INSERT INTO metadata VALUES('collection',?)", (json.dumps(metadata, ensure_ascii=False),))
            for name, raw in sorted(assets.items()):
                header, rows = parsed.get(name, ([], []))
                db.execute("INSERT INTO assets VALUES(?,?,?,?,?,?,?,?)",
                           (name, _sha(raw), len(raw), mimetypes.guess_type(name)[0] or "application/octet-stream",
                            int(name in parsed), len(rows) if name in parsed else None,
                            json.dumps(header, ensure_ascii=False), raw))
                db.executemany("INSERT INTO source_rows VALUES(?,?,?)",
                               ((name, number, json.dumps(row, ensure_ascii=False)) for number, row in enumerate(rows, 2)))
            db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise StorageError("Shopify SQLite integrity check failed.")
    finally:
        db.close()


class ShopifyRepository:
    """Read-only collection with exact archived bytes and native table tokens."""

    def __init__(self, db_path):
        self.db_path = Path(db_path).absolute()
        if not self.db_path.is_file() or self.db_path.is_symlink():
            raise StorageError("Shopify collection database is missing or linked.")
        with self._connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                raise StorageError("Unsupported Shopify database schema.")
            row = db.execute("SELECT json FROM metadata WHERE key='collection'").fetchone()
            self._metadata = json.loads(row[0]) if row else {}
            if self._metadata.get("platform") != "shopify":
                raise StorageError("This is not a Shopify collection database.")
            self.tables = tuple(row[0] for row in db.execute("SELECT path FROM assets WHERE is_table=1 ORDER BY path"))

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path.as_uri() + "?mode=ro&immutable=1", uri=True)
        try:
            yield db
        finally:
            db.close()

    @property
    def metadata(self):
        return json.loads(json.dumps(self._metadata))

    @property
    def datasets(self):
        return pd.DataFrame(self.metadata["datasets"])

    def sources(self):
        with self._connect() as db:
            return pd.read_sql_query("SELECT path,sha256,bytes,media_type,is_table,row_count FROM assets ORDER BY path", db)

    def source_bytes(self, path):
        path = _safe_path(path)
        with self._connect() as db:
            row = db.execute("SELECT sha256,contents FROM assets WHERE path=?", (path,)).fetchone()
        if row is None:
            raise StorageError("Unknown Shopify source asset: " + path)
        if _sha(row[1]) != row[0]:
            raise StorageError("Shopify source hash mismatch: " + path)
        return row[1]

    def table(self, dataset_id_or_path):
        path = dataset_id_or_path
        matches = [row for row in self._metadata["datasets"] if row["dataset_id"] == path]
        if matches:
            path = matches[0].get("path")
        if path not in self.tables:
            raise StorageError("Shopify dataset has no collected table: " + str(dataset_id_or_path))
        header, rows = _read_csv(self.source_bytes(path), path)
        with self._connect() as db:
            stored = [json.loads(row[0]) for row in db.execute(
                "SELECT row_json FROM source_rows WHERE asset_path=? ORDER BY csv_record", (path,))]
        if stored != rows:
            raise StorageError("Shopify parsed rows differ from retained source: " + path)
        frame = pd.DataFrame(rows, columns=header, dtype=object)
        frame.attrs.update(collection_key=self._metadata["collection_key"],
                           source_timezone=self._metadata["store"].get("timezone", ""),
                           baseline_status=self._metadata["baseline_status"])
        return frame

    def row_provenance(self, dataset_id_or_path):
        """One deterministic reference per native CSV row, including header offset."""
        dataset = next((row for row in self._metadata["datasets"]
                        if row["dataset_id"] == dataset_id_or_path or row.get("path") == dataset_id_or_path), None)
        if dataset is None:
            raise StorageError("Unknown Shopify dataset: " + str(dataset_id_or_path))
        table = self.table(dataset["dataset_id"])
        rows = []
        for number, row in enumerate(table.to_dict("records"), 2):
            identity = ({field: row[field] for field in dataset["primary_key"]}
                        if dataset.get("primary_key") else {"csv_record": number})
            key = json.dumps([self._metadata["collection_key"], dataset["dataset_id"], identity],
                             ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            rows.append({"collection_key": self._metadata["collection_key"], "dataset_id": dataset["dataset_id"],
                         "asset_path": dataset["path"], "csv_record": number, "identity_json": json.dumps(identity),
                         "stable_row_key": _sha(key.encode("utf-8"))})
        return pd.DataFrame(rows, columns=["collection_key", "dataset_id", "asset_path", "csv_record", "identity_json", "stable_row_key"])


def list_registered_shopify(data_dir):
    root = Path(data_dir).absolute()
    registry = _registry(root)
    records = registry["collections"]
    for record in records:
        path = _no_links(root / record["database"], root)
        if not path.is_file():
            raise StorageError("Registered Shopify database is missing: " + record["database"])
    return json.loads(json.dumps(records))


def load_registered_shopify(data_dir, key=None):
    root = Path(data_dir).absolute()
    records = list_registered_shopify(root)
    if not records:
        return None
    row = next((item for item in records if item["key"] == key), None) if key else records[-1]
    if row is None:
        raise StorageError("Unknown Shopify collection: " + str(key))
    path = _no_links(root / row["database"], root)
    if _sha(path.read_bytes()) != row["database_sha256"]:
        raise StorageError("Registered Shopify database hash differs.")
    repo = ShopifyRepository(path)
    if repo.metadata.get("package_sha256") != row["package_sha256"] or repo.metadata.get("collection_key") != row["key"]:
        raise StorageError("Shopify registration differs from collection metadata.")
    evidence = _no_links(root / row["evidence_root"] / "package", root)
    for asset in repo.sources().itertuples():
        retained = _no_links(evidence / _safe_path(asset.path), root)
        if not retained.is_file() or _sha(retained.read_bytes()) != asset.sha256:
            raise StorageError("Registered Shopify evidence is missing or changed: " + asset.path)
    return repo


def import_shopify_collection(package_dir, data_dir):
    """Validate, copy and atomically register one package; exact replay is read-only."""
    manifest, assets, parsed, digest = _package(package_dir)
    root = Path(data_dir).absolute()
    package = Path(package_dir).absolute()
    if root == package or package in root.parents:
        raise StorageError("Keep the Shopify library outside its incoming source package.")
    _no_links(root, root)
    root.mkdir(parents=True, exist_ok=True)
    key = manifest["collection_key"]
    parent = _no_links(root / "collections", root)
    parent.mkdir(exist_ok=True)
    output = _no_links(parent / key, root)
    with _lock(root):
        registry = _registry(root)
        existing = next((row for row in registry["collections"] if row["key"] == key), None)
        if existing:
            repo = load_registered_shopify(root, key)
            if repo.metadata["package_sha256"] != digest:
                raise StorageError("Shopify collection already exists with different source bytes.")
            for name, raw in assets.items():
                if repo.source_bytes(name) != raw:
                    raise StorageError("Shopify replay source bytes differ: " + name)
            for path in repo.tables:
                repo.table(path)
            return {"key": key, "database": str(repo.db_path), "package_sha256": digest,
                    "idempotent": True, "integrity": "ok", "datasets": len(manifest["datasets"])}
        if output.exists():
            raise StorageError("Unregistered Shopify destination already exists; preserve and inspect it.")
        label = manifest.get("label") or f"Shopify · {manifest['store'].get('name', manifest['store']['domain'])} · {key[8:16]} collection"
        metadata = {**manifest, "platform": "shopify", "label": label, "package_sha256": digest,
                    "loaded_at": datetime.now(timezone.utc).isoformat(),
                    "baseline_status": "newly_collected_separate_source",
                    "table_rows": {name: len(rows) for name, (_, rows) in parsed.items()}}
        with tempfile.TemporaryDirectory(prefix=".shopify-stage-", dir=parent) as temporary:
            stage = Path(temporary)
            evidence = stage / "package"
            evidence.mkdir()
            for name, raw in assets.items():
                target = evidence / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            _write_database(stage / "shopify.sqlite3", metadata, assets, parsed)
            repo = ShopifyRepository(stage / "shopify.sqlite3")
            for name, raw in assets.items():
                if repo.source_bytes(name) != raw or (evidence / name).read_bytes() != raw:
                    raise StorageError("Shopify durable source readback failed: " + name)
            for path in repo.tables:
                repo.table(path)
            database_hash = _sha((stage / "shopify.sqlite3").read_bytes())
            stage.rename(output)
        record = {"key": key, "database": f"collections/{key}/shopify.sqlite3",
                  "evidence_root": f"collections/{key}", "label": label,
                  "database_sha256": database_hash, "package_sha256": digest}
        registry["collections"].append(record)
        _atomic_json(root / REGISTRY_FILENAME, registry)
        return {"key": key, "database": str(output / "shopify.sqlite3"), "package_sha256": digest,
                "database_sha256": database_hash, "idempotent": False, "integrity": "ok",
                "datasets": len(manifest["datasets"]), "assets": len(assets),
                "table_rows": metadata["table_rows"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True,
                        help="Separate durable library destination; use a workspace staging directory for review.")
    args = parser.parse_args()
    try:
        # Windows consoles may use a legacy code page; JSON escapes retain the
        # complete Unicode path without failing after a successful registration.
        print(json.dumps(import_shopify_collection(args.package_dir, args.data_dir), ensure_ascii=True, indent=2))
    except (OSError, sqlite3.Error, ValueError) as exc:
        parser.exit(2, f"Shopify import failed: {exc}\n")


if __name__ == "__main__":
    main()
