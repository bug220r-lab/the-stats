"""Immutable TikTok Studio file collections, separate from saved analyses.

The package retains original exports and evidence alongside explicitly declared
derived tables. No date repair, metric aggregation, or missing-value conversion
is performed by this repository.
"""
from __future__ import annotations

from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import tempfile

import pandas as pd

from stats_app.storage import StorageError
from stats_app.native_paths import native_path


SCHEMA_VERSION = 1
REGISTRY_FILENAME = "tiktok_collections.json"
MANIFEST = "manifest.json"
KEY_PATTERN = r"tiktok-\d{8}(?:-[a-z0-9]+)*"
STATUSES = {"collected", "partial", "verified_empty", "unavailable", "blocked", "pending"}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise StorageError("TikTok paths must be relative forward-slash names.")
    path = PurePosixPath(value)
    if path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts or str(path) != value or value == ".":
        raise StorageError("Unsafe TikTok asset path: " + value)
    for part in path.parts:
        if (part.rstrip(" .") != part or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.I)):
            raise StorageError("Unsafe TikTok asset path: " + value)
    return value


def _not_link(path):
    path = Path(path).absolute()
    for current in [path, *path.parents]:
        physical = native_path(current)
        if physical.exists() or physical.is_symlink():
            info = physical.lstat()
            if physical.is_symlink() or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise StorageError("Linked TikTok collection paths are not supported.")
    return path


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _json(raw, label):
    def invalid_constant(value):
        raise ValueError("nonfinite JSON value")
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_pairs,
                           parse_constant=invalid_constant)
    except (UnicodeError, ValueError) as exc:
        raise StorageError("Invalid TikTok JSON: " + label) from exc
    if not isinstance(value, dict):
        raise StorageError("TikTok JSON must be an object: " + label)
    return value


def _read_csv(raw, label):
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        header = next(reader, [])
        if not header or any(not name.strip() for name in header):
            raise StorageError("TikTok table requires nonempty headers: " + label)
        folded = [name.strip().casefold() for name in header]
        if len(set(folded)) != len(header):
            raise StorageError("Duplicate TikTok table headers: " + label)
        rows = []
        for record, values in enumerate(reader, 2):
            if not values:
                continue
            if len(values) != len(header):
                raise StorageError(f"TikTok {label} CSV record {record} has the wrong field count.")
            rows.append((record, values))
        return header, rows
    except (UnicodeError, csv.Error) as exc:
        raise StorageError("Invalid TikTok UTF-8 CSV: " + label) from exc


def _package_files(root):
    root = _not_link(root)
    if not native_path(root).is_dir():
        raise StorageError("TikTok package directory is missing.")
    files, folded = {}, set()
    for physical in sorted(native_path(root).rglob("*")):
        path = root / physical.relative_to(native_path(root))
        _not_link(path)
        if native_path(path).is_dir():
            continue
        if not stat.S_ISREG(native_path(path).stat().st_mode):
            raise StorageError("TikTok package contains a nonregular file.")
        name = _safe_path(path.relative_to(root).as_posix())
        if name.casefold() in folded:
            raise StorageError("Case-ambiguous TikTok asset names.")
        files[name] = path
        folded.add(name.casefold())
    return files


def _validated_rows(raw, path, dataset):
    """Validate each consumed table, including when its repository loads lazily."""
    header, rows = _read_csv(raw, path)
    if dataset["row_count"] != len(rows):
        raise StorageError("TikTok table row count differs: " + path)
    if dataset["status"] == "verified_empty" and rows:
        raise StorageError("Verified-empty TikTok dataset contains rows.")
    primary_key = dataset.get("primary_key", [])
    if any(field not in header for field in primary_key):
        raise StorageError("Invalid TikTok primary-key declaration: " + path)
    if primary_key:
        positions = [header.index(field) for field in primary_key]
        identities = [tuple(values[index] for index in positions) for _, values in rows]
        if any(any(not value.strip() for value in identity) for identity in identities):
            raise StorageError("Blank TikTok primary key: " + path)
        if len(set(identities)) != len(identities):
            raise StorageError("Duplicate TikTok primary key: " + path)
    return header, rows


class TikTokRepository:
    """Hash-pinned file package with literal CSV tokens and stable row lineage."""

    def __init__(self, package_dir, *, manifest_sha256=None, package_sha256=None, verify_all=True):
        if not verify_all and (manifest_sha256 is None or package_sha256 is None):
            raise StorageError("Lazy TikTok loading requires externally pinned manifest and package hashes.")
        self.package_dir = _not_link(package_dir)
        files = _package_files(self.package_dir) if verify_all else None
        manifest_path = _not_link(self.package_dir / MANIFEST)
        if not native_path(manifest_path).is_file():
            raise StorageError("TikTok package requires manifest.json.")
        manifest_raw = native_path(manifest_path).read_bytes()
        self.manifest_sha256 = _sha(manifest_raw)
        if manifest_sha256 is not None and manifest_sha256 != self.manifest_sha256:
            raise StorageError("Registered TikTok manifest hash differs.")
        manifest = _json(manifest_raw, MANIFEST)
        if (manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("platform") != "tiktok"
                or not re.fullmatch(KEY_PATTERN, str(manifest.get("collection_key", "")))
                or not isinstance(manifest.get("account"), str) or not manifest["account"].strip()):
            raise StorageError("Unsupported TikTok manifest or collection identity.")
        try:
            captured = datetime.fromisoformat(manifest["collected_at"].replace("Z", "+00:00"))
            if captured.utcoffset() is None:
                raise ValueError("missing UTC offset")
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            raise StorageError("TikTok collected_at requires an ISO timestamp with UTC offset.") from exc
        assets = manifest.get("assets")
        if not isinstance(assets, list) or not assets:
            raise StorageError("TikTok manifest requires its complete asset inventory.")
        expected, folded = {}, {MANIFEST.casefold()}
        for entry in assets:
            if not isinstance(entry, dict):
                raise StorageError("Invalid TikTok asset inventory entry.")
            name = _safe_path(entry.get("path"))
            if (name.casefold() in folded or type(entry.get("bytes")) is not int or entry["bytes"] < 0
                    or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", "")))):
                raise StorageError("Invalid or duplicate TikTok asset inventory entry.")
            expected[name] = dict(entry)
            folded.add(name.casefold())
        if verify_all and set(files) != set(expected) | {MANIFEST}:
            raise StorageError("TikTok package contains missing or unexpected assets.")
        self._expected = {**expected, MANIFEST: {"path": MANIFEST, "bytes": len(manifest_raw),
                                               "sha256": self.manifest_sha256}}
        if verify_all:
            for name in files:
                self.source_bytes(name)
        datasets = manifest.get("datasets")
        if not isinstance(datasets, list) or not datasets:
            raise StorageError("TikTok manifest requires dataset declarations.")
        self._tables, self._datasets = {}, {}
        seen_ids = set()
        for dataset in datasets:
            if not isinstance(dataset, dict):
                raise StorageError("Invalid TikTok dataset declaration.")
            key = dataset.get("dataset_id")
            if (not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", key)
                    or key in seen_ids or dataset.get("status") not in STATUSES):
                raise StorageError("Invalid or duplicate TikTok dataset identity/status.")
            seen_ids.add(key)
            self._datasets[key] = dataset
            source_paths = dataset.get("source_paths", [])
            if not isinstance(source_paths, list):
                raise StorageError("TikTok source_paths must be a list.")
            for source in source_paths:
                if _safe_path(source) not in self._expected:
                    raise StorageError("TikTok dataset references an unknown source asset.")
            path = dataset.get("path")
            if not path:
                if dataset["status"] in {"collected", "partial", "verified_empty"}:
                    raise StorageError("Collected TikTok dataset requires a table path.")
                continue
            path = _safe_path(path)
            if not path.endswith(".csv") or path not in expected or path in self._tables:
                raise StorageError("Invalid or duplicate TikTok table path.")
            if type(dataset.get("row_count")) is not int or dataset["row_count"] < 0:
                raise StorageError("TikTok table row count must be a nonnegative integer: " + path)
            primary_key = dataset.get("primary_key", [])
            if (not isinstance(primary_key, list)
                    or any(not isinstance(field, str) or not field.strip() for field in primary_key)
                    or len(primary_key) != len(set(primary_key))):
                raise StorageError("Invalid TikTok primary-key declaration: " + path)
            self._tables[path] = dict(dataset)
            if verify_all:
                header, _ = _validated_rows(self.source_bytes(path), path, dataset)
                self._tables[path]["columns"] = header
        self.tables = tuple(sorted(self._tables))
        self.package_sha256 = _sha(json.dumps([(name, item["bytes"], item["sha256"])
                                               for name, item in sorted(self._expected.items())],
                                              separators=(",", ":")).encode("utf-8"))
        if package_sha256 is not None and package_sha256 != self.package_sha256:
            raise StorageError("Registered TikTok package hash differs.")
        self._manifest = manifest

    @property
    def metadata(self):
        value = json.loads(json.dumps(self._manifest))
        value.pop("assets", None)
        value.update(manifest_sha256=self.manifest_sha256, package_sha256=self.package_sha256,
                     baseline_status="separate_retrospective_collection_not_original_baseline")
        return value

    @property
    def datasets(self):
        return pd.DataFrame(json.loads(json.dumps(list(self._datasets.values()))))

    def sources(self):
        return pd.DataFrame([{**entry, "is_table": name in getattr(self, "_tables", {})}
                             for name, entry in sorted(self._expected.items())])

    def source_bytes(self, path):
        name = _safe_path(path)
        expected = self._expected.get(name)
        if expected is None:
            raise StorageError("Unknown TikTok source asset: " + name)
        source = _not_link(self.package_dir / name)
        if not native_path(source).is_file():
            raise StorageError("TikTok source asset is missing: " + name)
        raw = native_path(source).read_bytes()
        if len(raw) != expected["bytes"] or _sha(raw) != expected["sha256"]:
            raise StorageError("TikTok source failed size/SHA-256 verification: " + name)
        return raw

    original_bytes = source_bytes

    def _table_path(self, dataset):
        if dataset in self._tables:
            return dataset
        item = self._datasets.get(dataset)
        if item is None or item.get("path") not in self._tables:
            raise StorageError("TikTok dataset has no collected table: " + str(dataset))
        return item["path"]

    def table(self, dataset):
        path = self._table_path(dataset)
        header, rows = _validated_rows(self.source_bytes(path), path, self._tables[path])
        frame = pd.DataFrame([values for _, values in rows], columns=header, dtype=object)
        frame.attrs.update(collection_key=self._manifest["collection_key"],
                           source_timezone=self._manifest.get("reporting_timezone") or "unknown",
                           baseline_status="separate_retrospective_collection_not_original_baseline")
        return frame

    def row_provenance(self, dataset):
        path = self._table_path(dataset)
        header, rows = _validated_rows(self.source_bytes(path), path, self._tables[path])
        result = []
        for record, values in rows:
            row = dict(zip(header, values))
            payload = json.dumps([self._manifest["collection_key"], path, record, values],
                                 ensure_ascii=False, separators=(",", ":"))
            result.append({"collection_key": self._manifest["collection_key"], "asset_path": path,
                           "csv_record": record, "source_sha256": self._expected[path]["sha256"],
                           "source_reference": row.get("source_reference", row.get("evidence_ref", "")),
                           "stable_row_key": _sha(payload.encode("utf-8"))})
        return pd.DataFrame(result, columns=["collection_key", "asset_path", "csv_record", "source_sha256",
                                            "source_reference", "stable_row_key"])


def _registry(data_dir):
    path = _not_link(Path(data_dir) / REGISTRY_FILENAME)
    registry = _json(native_path(path).read_bytes(), REGISTRY_FILENAME) if path.exists() else {"schema_version": 1, "collections": []}
    if registry.get("schema_version") != SCHEMA_VERSION or not isinstance(registry.get("collections"), list):
        raise StorageError("Unsupported TikTok collection registry.")
    seen = set()
    for row in registry["collections"]:
        if not isinstance(row, dict) or not re.fullmatch(KEY_PATTERN, str(row.get("key", ""))):
            raise StorageError("Invalid TikTok collection registration.")
        key = row["key"]
        if key in seen or row.get("evidence_root") != f"collections/{key}" or row.get("package_dir") != f"collections/{key}/package":
            raise StorageError("Conflicting TikTok collection registration.")
        seen.add(key)
        if any(not re.fullmatch(r"[0-9a-f]{64}", str(row.get(field, "")))
               for field in ("manifest_sha256", "package_sha256")):
            raise StorageError("TikTok registration requires manifest and package hashes.")
    return registry


def list_registered_tiktok(data_dir):
    root = _not_link(data_dir)
    records = _registry(root)["collections"]
    for row in records:
        if not _not_link(root / row["package_dir"]).is_dir():
            raise StorageError("Registered TikTok package directory is missing.")
    return json.loads(json.dumps(records))


def load_registered_tiktok(data_dir, key=None, *, verify_all=False):
    """Load pinned metadata quickly; consumed assets are rehashed on every read.

    Import, replay, and complete-library backup use verify_all=True to verify
    every retained file and the complete namespace. The default performs no
    recursive evidence walk and never caches a table or its source bytes.
    """
    root = _not_link(data_dir)
    records = list_registered_tiktok(root)
    if not records:
        return None
    row = next((item for item in records if item["key"] == key), None) if key else records[-1]
    if row is None:
        raise StorageError("Unknown TikTok collection: " + str(key))
    repo = TikTokRepository(root / row["package_dir"], manifest_sha256=row["manifest_sha256"],
                            package_sha256=row["package_sha256"], verify_all=verify_all)
    if repo.metadata["collection_key"] != row["key"]:
        raise StorageError("TikTok registration differs from package identity.")
    return repo


@contextmanager
def _lock(root):
    path = _not_link(root / ".tiktok_import.lock")
    try:
        handle = path.open("x", encoding="ascii")
    except FileExistsError as exc:
        raise StorageError("Another TikTok import is active.") from exc
    try:
        handle.write(str(os.getpid()))
        handle.close()
        yield
    finally:
        handle.close()
        path.unlink()


def _atomic_registry(root, registry):
    descriptor, temporary = tempfile.mkstemp(prefix=".tiktok-registry-", suffix=".json", dir=root)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(registry, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, root / REGISTRY_FILENAME)
    finally:
        Path(temporary).unlink(missing_ok=True)


def import_tiktok_collection(package_dir, data_dir):
    """Verify, copy, and register; replay of an identical key is read-only."""
    incoming = TikTokRepository(package_dir)
    root, source = _not_link(data_dir), incoming.package_dir
    if root.is_relative_to(source) or source.is_relative_to(root):
        raise StorageError("Keep the incoming TikTok package outside the destination library.")
    root.mkdir(parents=True, exist_ok=True)
    key = incoming.metadata["collection_key"]
    with _lock(root):
        registry = _registry(root)
        old = next((row for row in registry["collections"] if row["key"] == key), None)
        if old:
            retained = load_registered_tiktok(root, key, verify_all=True)
            if retained.package_sha256 != incoming.package_sha256:
                raise StorageError("TikTok collection exists with different source bytes; use a new dated collection.")
            return {"key": key, "idempotent": True, "package_sha256": retained.package_sha256,
                    "manifest_sha256": retained.manifest_sha256, "package_dir": str(retained.package_dir),
                    "tables": len(retained.tables), "integrity": "ok"}
        parent = _not_link(root / "collections")
        parent.mkdir(exist_ok=True)
        output = _not_link(parent / key)
        if output.exists():
            raise StorageError("Unregistered TikTok destination exists; preserve and inspect it.")
        with tempfile.TemporaryDirectory(prefix=".tiktok-stage-", dir=parent) as temporary:
            stage = Path(temporary)
            package = stage / "package"
            package.mkdir()
            for name in incoming.sources().path:
                target = package / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as handle:
                    handle.write(incoming.source_bytes(name))
            copied = TikTokRepository(package, manifest_sha256=incoming.manifest_sha256,
                                      package_sha256=incoming.package_sha256)
            if TikTokRepository(source).package_sha256 != incoming.package_sha256:
                raise StorageError("Incoming TikTok collection changed during import.")
            stage.rename(output)
        record = {"key": key, "evidence_root": f"collections/{key}", "package_dir": f"collections/{key}/package",
                  "label": incoming.metadata.get("label", key), "manifest_sha256": copied.manifest_sha256,
                  "package_sha256": copied.package_sha256, "registered_at": datetime.now(timezone.utc).isoformat()}
        registry["collections"].append(record)
        _atomic_registry(root, registry)
        return {"key": key, "idempotent": False, "package_dir": str(output / "package"),
                "manifest_sha256": copied.manifest_sha256, "package_sha256": copied.package_sha256,
                "tables": len(copied.tables), "assets": len(copied.sources()), "integrity": "ok"}
