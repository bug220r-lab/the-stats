"""Activate a new immutable analysis version while retaining every older store."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import tempfile

from stats_app.analysis_repository import AnalysisRepository, list_registered_analyses
from stats_app.backup import _not_link, _registered_paths
from stats_app.config import load_settings
from stats_app.shopify_repository import (
    REGISTRY_FILENAME as SHOPIFY_REGISTRY, _lock as _shopify_import_lock,
    list_registered_shopify, load_registered_shopify,
)
from stats_app.storage import StorageError
from stats_app.youtube_repository import ZIP_FILENAME, _import_lock, list_registered_youtube


def _digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checkpointed_writable_hash(data_dir):
    """Observe only; a main-file digest cannot account for live SQLite sidecars."""
    database = data_dir / "stats.sqlite3"

    def require_no_pending_pages():
        for suffix in ("-wal", "-journal"):
            sidecar = Path(str(database) + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                raise StorageError(
                    "The writable database has a nonempty WAL or rollback journal; "
                    "promotion requires a checkpointed, quiescent library. No checkpoint was performed."
                )

    require_no_pending_pages()
    result = _digest(database) if database.exists() else None
    require_no_pending_pages()
    return result


def _collection_registry_bytes(data_dir):
    path = data_dir / "youtube_collections.json"
    _not_link(path)
    return path.read_bytes() if path.exists() else None


def _verify_collection_snapshot(data_dir, registry_bytes, collections):
    """Verify the separate collection registry and its pinned immutable files."""
    if _collection_registry_bytes(data_dir) != registry_bytes:
        raise StorageError("The YouTube collection registry changed concurrently; retry after reviewing the new source inventory.")
    for collection in collections:
        files = ((collection["database"], collection.get("database_sha256")),
                 (collection["evidence_root"] + "/" + collection.get("zip_filename", ZIP_FILENAME),
                  collection.get("zip_sha256")))
        for relative, expected in files:
            path = (data_dir / relative).resolve()
            if not path.is_relative_to(data_dir) or not _hash(expected) or _digest(path) != expected:
                raise StorageError("Registered YouTube database or ZIP failed SHA-256 verification: " + relative)
    if _collection_registry_bytes(data_dir) != registry_bytes:
        raise StorageError("The YouTube collection registry changed during source verification.")


def _shopify_registry_bytes(data_dir):
    path = data_dir / SHOPIFY_REGISTRY
    _not_link(path)
    return path.read_bytes() if path.exists() else None


def _verify_shopify_snapshot(data_dir, registry_bytes, collections):
    """Keep Shopify's separate registration, database and native evidence pinned."""
    if _shopify_registry_bytes(data_dir) != registry_bytes:
        raise StorageError("The Shopify collection registry changed concurrently; retry after reviewing the new source inventory.")
    for collection in collections:
        database = data_dir / collection["database"]

        def require_fixed_snapshot():
            for suffix in ("-wal", "-journal"):
                sidecar = Path(str(database) + suffix)
                if sidecar.exists() and sidecar.stat().st_size:
                    raise StorageError("A registered Shopify database has pending SQLite journal data; supply a fixed snapshot before promotion.")

        require_fixed_snapshot()
        # The existing loader verifies registered database and retained-asset
        # hashes. Table readback also checks parsed rows against original CSVs.
        repository = load_registered_shopify(data_dir, collection["key"])
        if repository is None:
            raise StorageError("The Shopify collection registry changed during source verification.")
        for table in repository.tables:
            repository.table(table)
        require_fixed_snapshot()
    if _shopify_registry_bytes(data_dir) != registry_bytes:
        raise StorageError("The Shopify collection registry changed during source verification.")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field: " + key)
        result[key] = value
    return result


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _reject_constant(value):
    raise ValueError("Non-finite JSON value: " + value)


def _relative_path(value):
    return (isinstance(value, str) and bool(value) and "\\" not in value
            and not PurePosixPath(value).is_absolute() and not PureWindowsPath(value).drive
            and ".." not in PurePosixPath(value).parts and str(PurePosixPath(value)) == value)


def _acceptance(raw, *, key, database_hash):
    """Validate the two retained semantic acceptance formats, never storage-only PASS.

    Supporting receipt hashes describe provenance; this gate does not impersonate
    the independent reviewer or infer evidence correctness from a successful copy.
    """
    try:
        receipt = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (ValueError, UnicodeError) as exc:
        raise StorageError("Independent acceptance audit must be unambiguous JSON.") from exc
    if not isinstance(receipt, dict) or receipt.get("passed") is not True:
        raise StorageError("Independent acceptance audit must explicitly have passed=true.")
    if "status" in receipt and receipt["status"] != "PASS":
        raise StorageError("Independent acceptance audit has a conflicting status.")
    if "schema_version" in receipt and (type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1):
        raise StorageError("Unsupported independent acceptance audit schema version.")
    for field in ("semantic_evidence_review_required", "semantic_review_required"):
        if field in receipt and receipt[field] is not False:
            raise StorageError("Independent semantic review is still required.")
    if not _hash(receipt.get("candidate_database_sha256")) or receipt["candidate_database_sha256"] != database_hash:
        raise StorageError("Independent acceptance audit does not match the candidate database SHA-256.")
    identities = [receipt[field] for field in ("analysis_key", "analysis_version") if field in receipt]
    if not identities or any(value != key for value in identities):
        raise StorageError("Independent acceptance audit does not match the analysis key.")
    try:
        audited_at = datetime.fromisoformat(receipt["audited_at_utc"])
        if audited_at.utcoffset() is None or audited_at.utcoffset().total_seconds() != 0:
            raise ValueError("UTC timestamp required")
    except (KeyError, TypeError, ValueError) as exc:
        raise StorageError("Independent acceptance audit needs an explicit UTC audit timestamp.") from exc
    prior = receipt.get("all_prior_database_hashes")
    if not isinstance(prior, dict) or any(not _relative_path(path) or not _hash(value) for path, value in prior.items()):
        raise StorageError("Independent acceptance audit needs a prior-database SHA-256 inventory.")
    supporting = receipt.get("supporting_receipts")
    if receipt.get("audit_scope") == "independent_semantic_evidence_and_storage_acceptance":
        semantic, storage = receipt.get("semantic_checks"), receipt.get("storage_checks")
        if (receipt.get("analysis_version") != key or not isinstance(semantic, dict) or not semantic
                or not isinstance(storage, dict) or not storage
                or any(value is False for value in (*semantic.values(), *storage.values()))
                or storage.get("all_candidate_table_rows_match_csv") is not True
                or storage.get("all_zip_assets_match_database") is not True
                or receipt.get("registry_unchanged_before_activation") is not True
                or not isinstance(supporting, dict)
                or set(supporting) != {"semantic_acceptance_audit.json", "independent_storage_audit.json"}
                or any(not _hash(value) for value in supporting.values())):
            raise StorageError("Incomplete semantic-and-storage acceptance audit.")
        schema = "semantic-and-storage-acceptance"
    elif "audit_scope" not in receipt and receipt.get("analysis_key") == key:
        if (receipt.get("status") != "PASS" or not isinstance(receipt.get("approval_scope"), str)
                or not receipt["approval_scope"].strip()
                or not isinstance(receipt.get("summary"), dict) or not receipt["summary"]
                or not _hash(receipt.get("normalization_receipt_sha256"))
                or not isinstance(supporting, list) or len(supporting) != 2):
            raise StorageError("Incomplete scoped semantic acceptance audit.")
        names = []
        for reference in supporting:
            if (not isinstance(reference, dict) or set(reference) != {"path", "sha256"}
                    or not _relative_path(reference["path"]) or not _hash(reference["sha256"])):
                raise StorageError("Malformed supporting acceptance receipt reference.")
            names.append(PurePosixPath(reference["path"]).name)
        if set(names) != {"semantic_acceptance_audit.json", "direct_sql_storage_audit.json"}:
            raise StorageError("Acceptance must identify both semantic and storage review receipts.")
        schema = "scoped-semantic-acceptance"
    else:
        raise StorageError("Unsupported independent acceptance audit; storage-only PASS cannot approve promotion.")
    return schema, prior


def _stage_hashes(stage):
    paths = list(stage.rglob("*"))
    if any(path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()) for path in paths):
        raise StorageError("The analysis stage must not contain links or junctions.")
    return {path.relative_to(stage).as_posix(): _digest(path) for path in paths if path.is_file()}


def _verify_copy(stage, target, hashes, audit, audit_hash):
    expected = dict(hashes, **{"independent_analysis_audit.json": audit_hash})
    copied = _stage_hashes(target)
    copied.pop("activation_receipt.json", None)
    if _stage_hashes(stage) != hashes or copied != expected:
        raise StorageError("Analysis stage changed during promotion or its copy failed verification.")
    if _digest(audit) != audit_hash:
        raise StorageError("Independent audit changed during promotion.")


def promote(stage, audit, data_dir, *, key, label=None):
    """Add a new key; identical replays are read-only and never reactivate.

    The legacy pointer is migrated in the same atomic registry replacement that
    selects the new version. Conflicting copies remain unregistered and intact.
    """
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        raise StorageError("Analysis version keys must contain only letters, numbers, underscores or hyphens.")
    stage, audit, data_dir = (Path(path).expanduser().resolve() for path in (stage, audit, data_dir))
    writable_hash = _checkpointed_writable_hash(data_dir)
    if not (stage / "analysis.sqlite3").is_file():
        raise StorageError("The staged analysis database is missing.")
    candidate_hash = _digest(stage / "analysis.sqlite3")
    source = AnalysisRepository(stage / "analysis.sqlite3")
    for table in source.tables:
        source.table(table)
    source.original_zip()
    if not audit.is_file():
        raise StorageError("An independent analysis audit file is required.")
    audit_raw = audit.read_bytes()
    audit_hash = hashlib.sha256(audit_raw).hexdigest()
    version_label = label or source.metadata["label"]
    if not isinstance(version_label, str) or not version_label.strip():
        raise StorageError("The analysis version label must be nonempty text.")
    target = data_dir / "analysis" / key
    for path in (target, *target.parents):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise StorageError("The analysis destination must not contain links or junctions.")
        if path == data_dir:
            break
    if stage == target or stage.is_relative_to(target) or target.is_relative_to(stage):
        raise StorageError("The analysis stage and destination must be separate directories.")
    stage_hashes = _stage_hashes(stage)
    if stage_hashes.get("analysis.sqlite3") != candidate_hash:
        raise StorageError("The candidate database changed during validation.")
    registry_path = data_dir / "archive_registry.json"
    if registry_path.is_symlink():
        raise StorageError("The registry must not be a symbolic link.")
    before_registry = registry_path.read_bytes() if registry_path.exists() else None
    before_collection_registry = _collection_registry_bytes(data_dir)
    collections = list_registered_youtube(data_dir)
    before_shopify_registry = _shopify_registry_bytes(data_dir)
    shopify_collections = list_registered_shopify(data_dir)
    all_collections = [*collections, *shopify_collections]

    def verify_collection_snapshots():
        _verify_collection_snapshot(data_dir, before_collection_registry, collections)
        _verify_shopify_snapshot(data_dir, before_shopify_registry, shopify_collections)

    verify_collection_snapshots()
    records = list_registered_analyses(data_dir)
    item = {"key": key, "database": f"analysis/{key}/analysis.sqlite3", "evidence_root": f"analysis/{key}", "label": version_label}
    registered = next((entry for entry in records if entry["key"] == key), None)
    if registered is not None:
        same_registration = {field: value for field, value in registered.items() if field != "active"} == item
        same_database = target.is_dir() and _digest(target / "analysis.sqlite3") == candidate_hash
        same_audit = (target / "independent_analysis_audit.json").is_file() and _digest(target / "independent_analysis_audit.json") == audit_hash
        if not (same_registration and same_database and same_audit):
            raise StorageError("This analysis key already identifies different data or evidence; choose a new key.")
        _verify_copy(stage, target, stage_hashes, audit, audit_hash)
        if (registry_path.read_bytes() if registry_path.exists() else None) != before_registry:
            raise StorageError("The registry changed concurrently; retry the read-only replay.")
        if _checkpointed_writable_hash(data_dir) != writable_hash:
            raise StorageError("The writable database changed during the read-only replay.")
        verify_collection_snapshots()
        return {"activated": str(target), "key": key, "idempotent": True, "active": registered["active"],
                "earlier_databases_unchanged": True, "tables": len(source.tables)}
    schema, audited_prior = _acceptance(audit_raw, key=key, database_hash=candidate_hash)
    if target.exists():
        raise FileExistsError("Preserving existing unregistered analysis directory; choose a new key.")
    if "independent_analysis_audit.json" in stage_hashes and stage_hashes["independent_analysis_audit.json"] != audit_hash:
        raise StorageError("The stage contains different independent audit evidence.")
    if "activation_receipt.json" in stage_hashes:
        raise StorageError("Stage a new analysis package without an older activation receipt.")
    data_dir.mkdir(parents=True, exist_ok=True)
    lock = data_dir / "archive_registry.lock"
    with lock.open("x", encoding="utf-8") as handle:
        handle.write("Analysis version promotion in progress.\n")
    collection_lock = ExitStack()
    pending = None
    try:
        # Each supported collection importer uses its own lock. Keep both
        # independent registries stable across the analysis registry commit;
        # replays above remain read-only and do not create lock files.
        collection_lock.enter_context(_import_lock(data_dir))
        collection_lock.enter_context(_shopify_import_lock(data_dir))
        if (registry_path.read_bytes() if registry_path.exists() else None) != before_registry:
            raise StorageError("The registry changed concurrently; promotion was not started.")
        verify_collection_snapshots()
        registry = json.loads(before_registry) if before_registry is not None else {"archives": []}
        records = list_registered_analyses(data_dir)
        _, old_archives = _registered_paths(data_dir, registry, all_collections)
        old_paths = list(dict.fromkeys([data_dir / "stats.sqlite3", *old_archives]))
        before = {path.relative_to(data_dir).as_posix(): _digest(path) for path in old_paths if path.exists()}
        if before != audited_prior:
            raise StorageError("Independent acceptance audit does not match the prior database inventory.")
        if _stage_hashes(stage) != stage_hashes or _digest(audit) != audit_hash:
            raise StorageError("Candidate or independent audit changed after acceptance validation.")
        if _checkpointed_writable_hash(data_dir) != writable_hash:
            raise StorageError("The writable database changed before promotion; the registry is unchanged.")
        verify_collection_snapshots()
        shutil.copytree(stage, target)
        if not (target / "independent_analysis_audit.json").exists():
            shutil.copy2(audit, target / "independent_analysis_audit.json")
        _verify_copy(stage, target, stage_hashes, audit, audit_hash)
        report = {"key": key, "activated_at": datetime.now(timezone.utc).isoformat(),
                  "database_sha256": candidate_hash, "independent_audit_sha256": audit_hash,
                  "acceptance_schema": schema, "earlier_database_hashes": before,
                  "youtube_collections_verified": len(collections),
                  "youtube_registry_sha256": (hashlib.sha256(before_collection_registry).hexdigest()
                                              if before_collection_registry is not None else None),
                  "shopify_collections_verified": len(shopify_collections),
                  "shopify_registry_sha256": (hashlib.sha256(before_shopify_registry).hexdigest()
                                              if before_shopify_registry is not None else None),
                  "earlier_databases_unchanged": True, "metadata": source.metadata}
        with (target / "activation_receipt.json").open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        registry["analysis_versions"] = [{field: value for field, value in entry.items() if field != "active"} for entry in records] + [item]
        registry["analysis_package"] = item
        _registered_paths(data_dir, registry, all_collections)
        # Own a unique same-directory file so rejected attempts cannot block a
        # later promotion or consume an unrelated retained diagnostic artifact.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=data_dir,
                                         prefix=registry_path.name + ".", suffix=".new",
                                         delete=False) as handle:
            pending = Path(handle.name)
            json.dump(registry, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        if (registry_path.read_bytes() if registry_path.exists() else None) != before_registry:
            raise StorageError("The registry changed concurrently; the new analysis remains unregistered.")
        _verify_copy(stage, target, stage_hashes, audit, audit_hash)
        current = {path.relative_to(data_dir).as_posix(): _digest(path) for path in old_paths if path.exists()}
        if current != before:
            raise StorageError("Earlier data or database inventory changed concurrently; the registry is unchanged.")
        if _checkpointed_writable_hash(data_dir) != writable_hash:
            raise StorageError("The writable database changed concurrently; the registry is unchanged.")
        verify_collection_snapshots()
        pending.replace(registry_path)
        pending = None
        verify_collection_snapshots()
        return {"activated": str(target), "key": key, "tables": len(source.tables), "idempotent": False,
                "active": True, "earlier_databases_unchanged": True}
    finally:
        try:
            if pending is not None:
                pending.unlink(missing_ok=True)
        finally:
            try:
                collection_lock.close()
            finally:
                lock.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--key", required=True, help="New stable version key; existing data is never replaced")
    parser.add_argument("--label")
    parser.add_argument("--data-dir", type=Path, help="Defaults to the configured local data directory")
    args = parser.parse_args()
    print(json.dumps(promote(args.stage, args.audit, args.data_dir or load_settings().data_dir, key=args.key, label=args.label)))
