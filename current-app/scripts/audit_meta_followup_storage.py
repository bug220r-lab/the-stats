"""Independent storage checks for a staged Meta follow-up, not evidence interpretation.

This module intentionally does not import the package builder. An acceptance
review must additionally establish that song, Ads and destination claims match
the captured source; a storage-only PASS cannot establish those semantics.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from stats_app.analysis_repository import AnalysisRepository
from stats_app.storage import StorageError


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def audit(parent, candidate, collection, *, namespace="meta_followup"):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", namespace):
        raise StorageError("The independent audit namespace must be a safe identifier.")
    parent, candidate = AnalysisRepository(parent), AnalysisRepository(candidate)
    collection = Path(collection).resolve()
    preflight = json.loads((collection / "preflight_preservation.json").read_text(encoding="utf-8"))
    library = Path(preflight["configured_data_dir"]).resolve()
    old_databases = {}
    for item in preflight["databases"]:
        path = (library / item["relative_path"]).resolve()
        if not path.is_relative_to(library) or sha(path.read_bytes()) != item["sha256"]:
            raise StorageError("Prior database changed or path escaped library: " + item["relative_path"])
        old_databases[item["relative_path"]] = item["sha256"]
    registry = (library / preflight["registry"]["relative_path"]).resolve()
    if not registry.is_relative_to(library) or sha(registry.read_bytes()) != preflight["registry"]["sha256"]:
        raise StorageError("Registry changed before follow-up audit.")
    candidate_assets = set(candidate.file_catalog().path)
    metadata_files = {"metadata.json", "raw_sha256.json", "audit/final_validation.json"}
    inherited = {}
    for row in parent.file_catalog().itertuples():
        retained = f"raw/{namespace}_predecessor_metadata/" + row.path if row.path in metadata_files else row.path
        if retained not in candidate_assets or candidate.original_bytes(retained) != parent.original_bytes(row.path):
            raise StorageError("Parent asset was changed or omitted: " + row.path)
        inherited[row.path] = {"retained_path": retained, "sha256": row.sha256}
    source_files = []
    normalized_tables = []
    for path in sorted(collection.rglob("*")):
        relative = path.relative_to(collection).as_posix()
        if relative.startswith("mapping/") and any(part.startswith("draft-") for part in path.relative_to(collection).parts[1:]):
            continue
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise StorageError("Follow-up source contains a link.")
        if not path.is_file():
            continue
        retained = f"raw/{namespace}/" + relative
        raw = path.read_bytes()
        if retained not in candidate_assets or candidate.original_bytes(retained) != raw:
            raise StorageError("Follow-up raw source changed or was omitted: " + relative)
        source_files.append(relative)
        if path.suffix.lower() == ".csv" and path.relative_to(collection).parts[0] in {"normalized", "mapping"}:
            domain = f"social/{namespace}/" + (path.relative_to(collection / "normalized").as_posix()
                    if path.relative_to(collection).parts[0] == "normalized" else relative)
            if domain not in candidate.tables or candidate.original_bytes(domain) != raw:
                raise StorageError("Follow-up normalized bytes differ: " + relative)
            data = candidate.table(domain)
            normalized_tables.append({"path": domain, "rows": len(data), "sha256": sha(raw)})
    for path in candidate.tables:
        candidate.table(path)
    source_version = parent.metadata["analysis_version"]
    if candidate.metadata.get("previous_analysis_version") != source_version:
        raise StorageError("Follow-up metadata names the wrong predecessor.")
    for key, value in parent.metadata.get("input_lineage", {}).items():
        if key != "predecessor_analysis" and candidate.metadata.get("input_lineage", {}).get(key) != value:
            raise StorageError("An inherited input lineage changed: " + key)
    if candidate.metadata.get("baseline_status") != "unverified" or candidate.metadata.get("new_significance_tests") != 0:
        raise StorageError("Follow-up baseline or inference metadata overstates the collection.")
    if candidate.metadata.get("tiktok_collection") != "excluded":
        raise StorageError("TikTok must remain excluded.")
    with zipfile.ZipFile(io.BytesIO(candidate.original_zip())) as zipped:
        files = [item for item in zipped.infolist() if not item.is_dir()]
        paths = [item.filename.split("/", 1)[1] for item in files]
        if len(paths) != len(set(paths)) or set(paths) != candidate_assets:
            raise StorageError("Original ZIP inventory differs from staged assets.")
        for item, relative in zip(files, paths):
            if zipped.read(item) != candidate.original_bytes(relative):
                raise StorageError("Original ZIP bytes differ from staged assets: " + relative)
    return {"passed": True, "audit_scope": "storage_integrity_only", "namespace": namespace, "semantic_evidence_review_required": True,
            "parent_database_sha256": sha(parent.db_path.read_bytes()), "candidate_database_sha256": sha(candidate.db_path.read_bytes()),
            "prior_database_hashes": old_databases, "registry_unchanged": True,
            "inherited_assets": inherited, "inherited_asset_count": len(inherited),
            "source_file_count": len(source_files), "normalized_tables": normalized_tables,
            "all_candidate_table_rows_match_csv": True, "all_zip_assets_match_database": True,
            "baseline_membership": "unverified", "new_significance_tests": 0, "tiktok": "excluded"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--collection", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--namespace", default="meta_followup")
    args = parser.parse_args()
    if args.report.resolve().is_relative_to(args.collection.resolve()):
        raise StorageError("Write the audit outside the frozen collection inventory.")
    report = audit(args.parent, args.candidate, args.collection, namespace=args.namespace)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({key: report[key] for key in ("passed", "audit_scope", "inherited_asset_count", "source_file_count")}))
