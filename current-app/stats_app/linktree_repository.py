"""Read-only, hash-verified Linktree file collections, independent of analyses.

The adapter preserves literal source tokens.  Import copies the sealed package;
it does not manufacture generic observations or change an analysis pointer.
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


REGISTRY_FILENAME = "linktree_collections.json"
SCHEMA_VERSION = 1
KEY_PATTERN = r"linktree-\d{8}(?:-[a-z0-9]+)*"
MANIFEST = "collection_manifest.json"
INVENTORY = "FILES_SHA256.json"
EXCLUDED = {MANIFEST, INVENTORY}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise StorageError("Linktree paths must be relative forward-slash names.")
    path = PurePosixPath(value)
    if path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts or str(path) != value or value == ".":
        raise StorageError("Unsafe Linktree asset path: " + value)
    for part in path.parts:
        if (part.rstrip(" .") != part or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.I)):
            raise StorageError("Unsafe Linktree asset path: " + value)
    return value


def _not_link(path):
    """Inspect every existing ancestor; do not resolve a link before rejecting it."""
    path = Path(path).absolute()
    for current in [path, *path.parents]:
        physical = native_path(current)
        if physical.exists() or physical.is_symlink():
            info = physical.lstat()
            if physical.is_symlink() or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise StorageError("Linked Linktree collection paths are not supported.")
    return path


def _json(raw, label):
    try:
        result = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise StorageError("Invalid Linktree JSON: " + label) from exc
    if not isinstance(result, dict):
        raise StorageError("Linktree JSON must be an object: " + label)
    return result


def _read_csv(raw, label):
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        header = next(reader, [])
        if not header or any(not column.strip() for column in header):
            raise StorageError("Linktree table needs nonempty headers: " + label)
        folded = [column.strip().casefold() for column in header]
        if len(set(folded)) != len(folded):
            raise StorageError("Duplicate Linktree table headers: " + label)
        rows = []
        for record, row in enumerate(reader, 2):
            if not row:
                continue
            if len(row) != len(header):
                raise StorageError(f"Linktree {label} CSV record {record} has the wrong field count.")
            rows.append((record, row))
        return header, rows
    except (UnicodeError, csv.Error) as exc:
        raise StorageError("Invalid Linktree UTF-8 CSV: " + label) from exc


def _package_files(root):
    root = _not_link(root)
    if not native_path(root).is_dir():
        raise StorageError("Linktree package directory is missing.")
    files, folded = {}, set()
    for physical in sorted(native_path(root).rglob("*")):
        path = root / physical.relative_to(native_path(root))
        _not_link(path)
        if "__pycache__" in path.relative_to(root).parts:
            continue
        if native_path(path).is_dir():
            continue
        if not stat.S_ISREG(native_path(path).stat().st_mode):
            raise StorageError("Linktree package contains a nonregular file.")
        name = _safe_path(path.relative_to(root).as_posix())
        if name.casefold() in folded:
            raise StorageError("Case-ambiguous Linktree asset names.")
        files[name] = path
        folded.add(name.casefold())
    return files


class LinktreeRepository:
    """A file-package adapter with exact bytes, table tokens and row lineage.

    Registered instances pin manifest and inventory hashes externally. Direct
    instances validate the package's internal checksums, useful before import.
    """

    def __init__(self, package_dir, *, manifest_sha256=None, inventory_sha256=None, package_sha256=None):
        self.package_dir = _not_link(package_dir)
        files = _package_files(self.package_dir)
        if not EXCLUDED.issubset(files):
            raise StorageError("Linktree package requires its manifest and checksum inventory.")
        manifest_raw, inventory_raw = native_path(files[MANIFEST]).read_bytes(), native_path(files[INVENTORY]).read_bytes()
        self.manifest_sha256, self.inventory_sha256 = _sha(manifest_raw), _sha(inventory_raw)
        if manifest_sha256 is not None and manifest_sha256 != self.manifest_sha256:
            raise StorageError("Registered Linktree manifest hash differs.")
        if inventory_sha256 is not None and inventory_sha256 != self.inventory_sha256:
            raise StorageError("Registered Linktree inventory hash differs.")
        manifest, inventory = _json(manifest_raw, MANIFEST), _json(inventory_raw, INVENTORY)
        key = manifest.get("collection_id")
        if manifest.get("schema_version") != SCHEMA_VERSION or not re.fullmatch(KEY_PATTERN, str(key or "")):
            raise StorageError("Unsupported Linktree manifest or collection identity.")
        identity = manifest.get("identity")
        if (not isinstance(identity, dict) or identity.get("collection_id") != key
                or str(identity.get("platform", "")).lower() != "linktree" or not identity.get("account")):
            raise StorageError("Linktree manifest needs a consistent account identity.")
        if (manifest.get("checksums_file") != INVENTORY
                or manifest.get("checksums_file_sha256") != self.inventory_sha256
                or inventory.get("algorithm") != "SHA-256"):
            raise StorageError("Linktree manifest and checksum inventory differ.")
        if set(inventory.get("excludes", [])) != {MANIFEST, INVENTORY, "__pycache__/"}:
            raise StorageError("Unsupported Linktree checksum exclusions.")
        entries = inventory.get("files")
        if not isinstance(entries, list) or not entries:
            raise StorageError("Linktree checksum inventory is empty or invalid.")
        expected, folded = {}, set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise StorageError("Invalid Linktree checksum entry.")
            name = _safe_path(entry.get("path"))
            if (name in EXCLUDED or name.casefold() in folded or type(entry.get("bytes")) is not int
                    or entry["bytes"] < 0 or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", "")))):
                raise StorageError("Invalid or duplicate Linktree checksum entry.")
            expected[name] = entry
            folded.add(name.casefold())
        if set(files) != set(expected) | EXCLUDED:
            raise StorageError("Linktree package contains missing or unexpected assets.")
        declared = manifest.get("file_inventory")
        if not isinstance(declared, list) or declared != entries:
            raise StorageError("Linktree manifest file inventory differs from checksums.")
        self._expected = {**expected,
                          MANIFEST: {"path": MANIFEST, "bytes": len(manifest_raw), "sha256": self.manifest_sha256},
                          INVENTORY: {"path": INVENTORY, "bytes": len(inventory_raw), "sha256": self.inventory_sha256}}
        for name in files:
            self.original_bytes(name)
        if "collection_identity.json" not in files or _json(self.original_bytes("collection_identity.json"), "identity") != identity:
            raise StorageError("Linktree identity evidence differs from manifest.")
        datasets = manifest.get("dataset_tables")
        if not isinstance(datasets, list) or not datasets:
            raise StorageError("Linktree manifest needs its dataset table inventory.")
        self._tables = {}
        for dataset in datasets:
            if not isinstance(dataset, dict) or not isinstance(dataset.get("file"), str):
                raise StorageError("Invalid Linktree dataset declaration.")
            # The collected manifest uses native Windows separators only here.
            path = _safe_path(dataset["file"].replace("\\", "/"))
            if not path.startswith("normalized/") or not path.endswith(".csv") or path not in files or path in self._tables:
                raise StorageError("Invalid or duplicate Linktree normalized table path.")
            header, rows = _read_csv(self.original_bytes(path), path)
            if type(dataset.get("row_count")) is not int or dataset["row_count"] != len(rows):
                raise StorageError("Linktree dataset row count differs: " + path)
            if "account" in header and any(row[header.index("account")] != identity["account"] for _, row in rows):
                raise StorageError("Linktree table account identity differs: " + path)
            self._tables[path] = {"dataset_id": PurePosixPath(path).stem, "path": path,
                                  "row_count": len(rows), "columns": header}
        normalized = {name for name in files if name.startswith("normalized/") and name.endswith(".csv")}
        if normalized != set(self._tables):
            raise StorageError("Linktree manifest omits a normalized table.")
        self.tables = tuple(sorted(self._tables))
        self.package_sha256 = _sha(json.dumps([(name, item["bytes"], item["sha256"])
                                               for name, item in sorted(self._expected.items())],
                                              separators=(",", ":")).encode("utf-8"))
        if package_sha256 is not None and package_sha256 != self.package_sha256:
            raise StorageError("Registered Linktree package hash differs.")
        self._manifest = manifest

    @property
    def metadata(self):
        result = json.loads(json.dumps(self._manifest))
        result.update(collection_key=result["collection_id"], platform="linktree",
                      account=result["identity"]["account"],
                      account_display_name=result["identity"].get("profile_display_name", result["identity"]["account"]),
                      label="Linktree · " + result["identity"].get("profile_display_name", result["identity"]["account"]),
                      collected_at=result["identity"].get("collection_ended_at_utc"),
                      reporting_timezone=result["identity"].get("reporting_timezone") or "unknown",
                      reporting_start=result.get("coverage", {}).get("earliest_accessible_date"),
                      reporting_end=result.get("coverage", {}).get("latest_accessible_date"),
                      baseline_status="separate_retrospective_collection_not_original_baseline",
                      manifest_sha256=self.manifest_sha256, inventory_sha256=self.inventory_sha256,
                      package_sha256=self.package_sha256)
        return result

    @property
    def datasets(self):
        return pd.DataFrame([dict(value) for value in self._tables.values()])

    def sources(self):
        return pd.DataFrame([{**item, "is_table": name in self._tables} for name, item in sorted(self._expected.items())])

    def original_bytes(self, path):
        name = _safe_path(path)
        expected = self._expected.get(name)
        if expected is None:
            raise StorageError("Unknown Linktree source asset: " + name)
        path = _not_link(self.package_dir / name)
        if not native_path(path).is_file():
            raise StorageError("Linktree source asset is missing: " + name)
        raw = native_path(path).read_bytes()
        if len(raw) != expected["bytes"] or _sha(raw) != expected["sha256"]:
            raise StorageError("Linktree source asset failed size/SHA-256 verification: " + name)
        return raw

    source_bytes = original_bytes

    def _table_path(self, dataset):
        if dataset in self._tables:
            return dataset
        matches = [path for path, item in self._tables.items() if item["dataset_id"] == dataset]
        if len(matches) != 1:
            raise StorageError("Unknown Linktree dataset: " + str(dataset))
        return matches[0]

    def table(self, dataset):
        path = self._table_path(dataset)
        header, rows = _read_csv(self.original_bytes(path), path)
        frame = pd.DataFrame([row for _, row in rows], columns=header, dtype=object)
        frame.attrs.update(collection_key=self._manifest["collection_id"],
                           source_timezone=self._manifest["identity"].get("reporting_timezone") or "unknown",
                           baseline_status="separate_retrospective_collection_not_original_baseline")
        return frame

    def row_provenance(self, dataset):
        path = self._table_path(dataset)
        header, rows = _read_csv(self.original_bytes(path), path)
        result = []
        for record, values in rows:
            row = dict(zip(header, values))
            payload = json.dumps([self._manifest["collection_id"], path, record, values], separators=(",", ":"), ensure_ascii=False)
            result.append({"collection_key": self._manifest["collection_id"], "asset_path": path,
                           "csv_record": record, "source_sha256": self._expected[path]["sha256"],
                           "source_reference": row.get("source_reference", row.get("evidence_ref", "")),
                           "stable_row_key": _sha(payload.encode("utf-8"))})
        return pd.DataFrame(result, columns=["collection_key", "asset_path", "csv_record", "source_sha256", "source_reference", "stable_row_key"])


def _registry(data_dir):
    path = _not_link(Path(data_dir) / REGISTRY_FILENAME)
    registry = _json(native_path(path).read_bytes(), REGISTRY_FILENAME) if native_path(path).exists() else {"schema_version": 1, "collections": []}
    if registry.get("schema_version") != SCHEMA_VERSION or not isinstance(registry.get("collections"), list):
        raise StorageError("Unsupported Linktree collection registry.")
    seen = set()
    for row in registry["collections"]:
        if not isinstance(row, dict) or not re.fullmatch(KEY_PATTERN, str(row.get("key", ""))):
            raise StorageError("Invalid Linktree collection registration.")
        key = row["key"]
        if key in seen or row.get("evidence_root") != f"collections/{key}" or row.get("package_dir") != f"collections/{key}/package":
            raise StorageError("Conflicting Linktree collection registration.")
        seen.add(key)
        if any(not re.fullmatch(r"[0-9a-f]{64}", str(row.get(field, "")))
               for field in ("manifest_sha256", "inventory_sha256", "package_sha256")):
            raise StorageError("Linktree registration requires manifest, inventory and package hashes.")
    return registry


def list_registered_linktree(data_dir):
    root = _not_link(data_dir)
    records = _registry(root)["collections"]
    for row in records:
        if not native_path(_not_link(root / row["package_dir"])).is_dir():
            raise StorageError("Registered Linktree package directory is missing.")
    return json.loads(json.dumps(records))


def load_registered_linktree(data_dir, key=None):
    root = _not_link(data_dir)
    records = list_registered_linktree(root)
    if not records:
        return None
    row = next((record for record in records if record["key"] == key), None) if key else records[-1]
    if row is None:
        raise StorageError("Unknown Linktree collection: " + str(key))
    repo = LinktreeRepository(root / row["package_dir"], **{field: row[field]
                              for field in ("manifest_sha256", "inventory_sha256", "package_sha256")})
    if repo.metadata["collection_key"] != row["key"]:
        raise StorageError("Linktree registration differs from package identity.")
    return repo


@contextmanager
def _lock(root):
    path = _not_link(root / ".linktree_import.lock")
    try:
        handle = native_path(path).open("x", encoding="ascii")
    except FileExistsError as exc:
        raise StorageError("Another Linktree import is active.") from exc
    try:
        handle.write(str(os.getpid()))
        handle.close()
        yield
    finally:
        handle.close()
        native_path(path).unlink()


def _atomic_registry(root, registry):
    descriptor, temporary = tempfile.mkstemp(prefix=".linktree-registry-", suffix=".json", dir=native_path(root))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(registry, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, native_path(root / REGISTRY_FILENAME))
    finally:
        native_path(temporary).unlink(missing_ok=True)


def import_linktree_collection(package_dir, data_dir):
    """Verify and copy a sealed package; same-key exact replay writes no records."""
    incoming = LinktreeRepository(package_dir)
    root, source = _not_link(data_dir), incoming.package_dir
    if root.is_relative_to(source) or source.is_relative_to(root):
        raise StorageError("Keep the incoming Linktree package outside the destination library.")
    native_path(root).mkdir(parents=True, exist_ok=True)
    key = incoming.metadata["collection_key"]
    with _lock(root):
        registry = _registry(root)
        old = next((row for row in registry["collections"] if row["key"] == key), None)
        if old:
            retained = load_registered_linktree(root, key)
            if retained.package_sha256 != incoming.package_sha256:
                raise StorageError("Linktree collection exists with different source bytes; use a new dated collection.")
            return {"key": key, "idempotent": True, "package_sha256": retained.package_sha256,
                    "manifest_sha256": retained.manifest_sha256, "inventory_sha256": retained.inventory_sha256,
                    "package_dir": str(retained.package_dir), "tables": len(retained.tables), "integrity": "ok"}
        parent = _not_link(root / "collections")
        native_path(parent).mkdir(exist_ok=True)
        output = _not_link(parent / key)
        if native_path(output).exists():
            raise StorageError("Unregistered Linktree destination exists; preserve and inspect it.")
        with tempfile.TemporaryDirectory(prefix=".linktree-stage-", dir=native_path(parent)) as temporary:
            # Keep extended paths at the I/O boundary, out of portable records.
            stage = parent / Path(temporary).name
            package = stage / "package"
            native_path(package).mkdir()
            for name in incoming.sources().path:
                target = package / name
                native_path(target.parent).mkdir(parents=True, exist_ok=True)
                with native_path(target).open("xb") as handle:
                    handle.write(incoming.original_bytes(name))
            copied = LinktreeRepository(package, manifest_sha256=incoming.manifest_sha256,
                                       inventory_sha256=incoming.inventory_sha256, package_sha256=incoming.package_sha256)
            # Recheck the complete incoming namespace after copying to detect changes.
            final = LinktreeRepository(source)
            if final.package_sha256 != incoming.package_sha256:
                raise StorageError("Incoming Linktree collection changed during import.")
            native_path(stage).rename(native_path(output))
        record = {"key": key, "evidence_root": f"collections/{key}", "package_dir": f"collections/{key}/package",
                  "label": incoming.metadata["label"], "manifest_sha256": copied.manifest_sha256,
                  "inventory_sha256": copied.inventory_sha256, "package_sha256": copied.package_sha256,
                  "registered_at": datetime.now(timezone.utc).isoformat()}
        registry["collections"].append(record)
        _atomic_registry(root, registry)
        return {"key": key, "idempotent": False, "package_dir": str(output / "package"),
                "manifest_sha256": copied.manifest_sha256, "inventory_sha256": copied.inventory_sha256,
                "package_sha256": copied.package_sha256, "tables": len(copied.tables),
                "assets": len(copied.sources()), "integrity": "ok"}
