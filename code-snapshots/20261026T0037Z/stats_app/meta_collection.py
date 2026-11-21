"""Package a Meta collection as a new immutable analysis, never a live mutation.

Collection tables remain evidence at their supplied grain. This module does not
repair old daily rows, allocate lifetime outcomes, rerun inference or collect
from any service. Every earlier analytical asset remains unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile

import pandas as pd

from stats_app.analysis_repository import AnalysisRepository, _csv, _safe_name, load_registered_analysis
from stats_app.config import load_settings
from stats_app.storage import StorageError

VERSION = "meta-collection-20261023"
LABEL = "Meta collection · October 23, 2026 · source-specific reporting windows"
PREFIX = "social/meta_collection/"
RAW_PREFIX = "raw/meta_collection/"
PACKAGING_ASSETS = {"metadata.json", "raw_sha256.json", "audit/final_validation.json"}
STATUS_COLUMNS = ["dataset", "status", "detail", "evidence_ref", "captured_at_utc"]
EXPECTED_DATASETS = {
    "ads_manager": "ads_history.csv",
    "instagram_follows": "follows_daily.csv",
    "instagram_stories": "stories_repaired.csv",
    "post_song_event_mapping": "mapping/post_song_map.csv",
}


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        parts = path.relative_to(root).parts
        if parts and parts[0] == "mapping" and any(part.startswith("draft-") for part in parts[1:]):
            continue
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise StorageError("Collection inputs must not contain links or junctions.")
        if path.is_file():
            relative = _safe_name(path.relative_to(root).as_posix())
            result[relative] = {"bytes": path.stat().st_size, "sha256": _hash(path.read_bytes())}
    return result


def _read_csv(raw, path):
    columns, rows = _csv(raw, path)
    return pd.DataFrame(rows, columns=columns)


def validate_collection_table(data, path):
    """Check supplied evidence without filling unknowns or inventing semantics."""
    if not len(data.columns):
        raise StorageError("Collection CSV needs explicit columns: " + path)
    if {"value", "value_status"}.issubset(data.columns):
        value = data.value.replace("", pd.NA)
        numeric = pd.to_numeric(value, errors="coerce")
        observed = data.value_status.isin({"observed", "observed_zero"})
        if (observed & numeric.isna()).any():
            raise StorageError("Observed collection values need exact numeric evidence: " + path)
        if numeric.dropna().isin([float("inf"), -float("inf")]).any():
            raise StorageError("Collection values must be finite: " + path)
        if ((~observed) & value.notna()).any():
            raise StorageError("Unavailable collection values must remain blank: " + path)
    if "captured_at_utc" in data:
        for value in data.captured_at_utc:
            if not value:
                continue
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise StorageError("Invalid collection capture timestamp: " + path) from exc
            if parsed.tzinfo is None:
                raise StorageError("Collection capture timestamps need an explicit UTC offset: " + path)
    for start, end in (("reporting_start", "reporting_end"), ("reporting_window_start", "reporting_window_end")):
        if start in data and end in data:
            known = data[start].ne("") & data[end].ne("")
            if (data.loc[known, start] > data.loc[known, end]).any():
                raise StorageError("Collection reporting start follows end: " + path)
    return data


def _preflight_check(collection, parent):
    path = collection / "preflight_preservation.json"
    if not path.exists():
        return {"provided": False, "note": "Separate live-library preservation audit required before activation."}
    preflight = json.loads(path.read_text(encoding="utf-8"))
    root = Path(preflight["configured_data_dir"]).resolve()
    results = []
    for item in preflight["databases"]:
        db = root / _safe_name(item["relative_path"])
        if _hash(db.read_bytes()) != item["sha256"]:
            raise StorageError("A preflight database changed before collection packaging: " + item["relative_path"])
        results.append(item["relative_path"])
    registry = root / _safe_name(preflight["registry"]["relative_path"])
    if _hash(registry.read_bytes()) != preflight["registry"]["sha256"]:
        raise StorageError("The live registry changed since the Meta preservation gate.")
    if parent.db_path not in [root / item["relative_path"] for item in preflight["databases"]]:
        raise StorageError("The analysis predecessor is not in the collection preservation audit.")
    return {"provided": True, "database_hashes_unchanged": results, "registry_unchanged": True}


def build_meta_collection(parent, collection_root, output_dir, zip_path, *, version_key=VERSION, label=LABEL):
    """Build a new package and ZIP. No staging, activation or live writes occur.

    Accepted inputs are raw/**, normalized/*.csv, mapping/**, and supporting
    collection documentation. Every input file is retained under raw/. Supplied
    rectangular normalized and mapping CSVs are also exposed as domain tables.
    Missing expected datasets get explicit unavailable status rows, never zeros.
    """
    if not isinstance(parent, AnalysisRepository):
        parent = AnalysisRepository(parent)
    collection = Path(collection_root).resolve()
    output, archive = Path(output_dir).resolve(), Path(zip_path).resolve()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", version_key):
        raise StorageError("Collection version key must be a safe stable identifier.")
    if not isinstance(label, str) or not label.strip():
        raise StorageError("Collection version needs an explicit nonempty label.")
    if not collection.is_dir():
        raise StorageError("The collection input directory is missing.")
    if output.exists() or archive.exists():
        raise FileExistsError("Preserving an existing collection package or ZIP; choose new output paths.")
    if output.is_relative_to(collection) or archive.is_relative_to(collection) or archive.is_relative_to(output):
        raise StorageError("Package output and ZIP must be separate from the collection inputs and each other.")
    if parent.db_path.is_relative_to(output):
        raise StorageError("The package output cannot contain the predecessor database.")
    parent_hash = _hash(parent.db_path.read_bytes())
    previous = parent.metadata.get("analysis_version", getattr(parent, "registered_key", "original-analysis"))
    if previous == version_key:
        raise StorageError("The new collection version must differ from its predecessor.")
    inputs = _inventory(collection)
    preservation = _preflight_check(collection, parent)

    # Verify the mapping producer's manifest and exact analytical input lineage.
    mapping_manifest = collection / "mapping/output_manifest.json"
    if mapping_manifest.exists():
        for relative, digest in json.loads(mapping_manifest.read_text(encoding="utf-8")).items():
            relative = _safe_name(relative)
            if _hash((collection / "mapping" / relative).read_bytes()) != digest:
                raise StorageError("Mapping output manifest mismatch: " + relative)
    mapping_coverage = collection / "mapping/coverage.json"
    if mapping_coverage.exists():
        coverage = json.loads(mapping_coverage.read_text(encoding="utf-8"))
        for field in ("source_database_sha256_before", "source_database_sha256_after"):
            if coverage.get(field) and coverage[field] != parent_hash:
                raise StorageError("Mapping evidence was produced from a different analysis database.")
        for path, digest in coverage.get("input_assets_sha256", {}).items():
            if _hash(parent.original_bytes(path)) != digest:
                raise StorageError("Mapping analytical input differs from its predecessor: " + path)

    tables = {}
    for relative in inputs:
        path = Path(relative)
        if path.suffix.lower() != ".csv" or path.parts[0] not in {"normalized", "mapping"}:
            continue
        domain_name = path.relative_to("normalized").as_posix() if path.parts[0] == "normalized" else relative
        destination = PREFIX + domain_name
        raw = (collection / relative).read_bytes()
        frame = validate_collection_table(_read_csv(raw, relative), relative)
        if destination in tables:
            raise StorageError("Two collection files resolve to the same domain table.")
        tables[destination] = {"raw": raw, "frame": frame, "source": relative}
    status_path = PREFIX + "collection_status.csv"
    supplied_status = tables.get(status_path)
    if supplied_status:
        status = supplied_status["frame"].copy()
        if not set(STATUS_COLUMNS).issubset(status):
            raise StorageError("collection_status.csv requires: " + ", ".join(STATUS_COLUMNS))
        if status.dataset.eq("").any() or status.status.eq("").any() or status.dataset.duplicated().any():
            raise StorageError("Each collection dataset needs one explicit nonempty status.")
    else:
        status = pd.DataFrame(columns=STATUS_COLUMNS)
    for dataset, table in EXPECTED_DATASETS.items():
        if dataset in status.dataset.values:
            continue
        supplied = PREFIX + table in tables
        retained = supplied and not tables[PREFIX + table]["frame"].empty
        state = "retained_separate_evidence" if retained else "retained_empty_report" if supplied else "not_collected"
        detail = ("Retained evidence has not been merged into historical results." if retained else
                  "A collected table contains no rows; other accounts and reporting scopes remain unknown." if supplied else
                  "No validated table supplied for this collection; no zero value is inferred.")
        row = {"dataset": dataset, "status": state, "detail": detail,
               "evidence_ref": PREFIX + table if supplied else "", "captured_at_utc": ""}
        status = pd.concat([status, pd.DataFrame([row])], ignore_index=True)
    status_raw = status.to_csv(index=False).encode("utf-8")
    tables[status_path] = {"raw": status_raw, "frame": status, "source": "normalized/collection_status.csv" if supplied_status else "generated from supplied table inventory"}

    output.mkdir(parents=True, exist_ok=False)

    def put(relative, raw):
        destination = output / _safe_name(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            handle.write(raw)

    def put_json(relative, value):
        put(relative, (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))

    inherited = {}
    for row in parent.file_catalog().itertuples():
        raw = parent.original_bytes(row.path)
        if row.path.startswith((PREFIX, RAW_PREFIX)):
            raise StorageError("The predecessor already contains this collection namespace; use a distinct integration design.")
        retained_path = "raw/meta_predecessor_metadata/" + row.path if row.path in PACKAGING_ASSETS else row.path
        put(retained_path, raw)
        inherited[row.path] = {"sha256": _hash(raw), "retained_path": retained_path}
    for relative, info in inputs.items():
        raw = (collection / relative).read_bytes()
        if _hash(raw) != info["sha256"]:
            raise StorageError("Collection source changed while packaging: " + relative)
        put(RAW_PREFIX + relative, raw)
    catalog = []
    for path, item in tables.items():
        put(path, item["raw"])
        frame = item["frame"]
        timestamps = sorted({str(value) for column in ("captured_at_utc", "snapshot_timestamp") if column in frame for value in frame[column] if value})
        catalog.append({"table": path, "source_file": item["source"],
                        "retained_input_path": RAW_PREFIX + item["source"] if item["source"] in inputs else "",
                        "input_sha256": inputs[item["source"]]["sha256"] if item["source"] in inputs else "",
                        "sha256": _hash(item["raw"]), "rows": len(frame),
                        "capture_timestamps_supplied": " | ".join(timestamps),
                        "grain": "Supplied source grain; no metric aggregation or historical repair performed",
                        "scope_status": "Retained as supplied; absent scope and dates remain unknown"})
    put(PREFIX + "dataset_catalog.csv", pd.DataFrame(catalog).to_csv(index=False).encode("utf-8"))
    now = datetime.now(timezone.utc).isoformat()
    lineage = dict(parent.metadata.get("input_lineage", {}))
    lineage.update(meta_collection=version_key, predecessor_analysis=previous)
    lineage.setdefault("statistical_results", previous)
    lineage.setdefault("cross_platform", previous)
    lineage.setdefault("social", previous)
    captured_dates = sorted({stamp[:10] for item in catalog for stamp in item["capture_timestamps_supplied"].split(" | ") if stamp})
    metadata = {"analysis_version": version_key, "previous_analysis_version": previous, "label": label,
                "input_lineage": lineage, "retrieval_vintage": "; ".join(captured_dates) if captured_dates else "unknown; see retained source evidence",
                "activity_endpoint": parent.metadata.get("activity_endpoint", "2026-10-20"),
                "baseline_endpoint": parent.metadata.get("baseline_endpoint", "2026-10-20"),
                "baseline_note": parent.metadata.get("baseline_note", "Original baseline membership remains unverified."),
                "parent_package_sha256": parent.metadata["package_sha256"], "parent_zip_sha256": parent.metadata["zip_sha256"],
                "collection_reporting_basis": "Source-specific reporting windows, capture timestamps and statuses; unknown dates remain blank.",
                "collection_built_at_utc": now, "evidence_type": "Separate Meta collection evidence and caption-based mapping; historical canonical inputs unchanged",
                "new_significance_tests": 0, "tiktok_collection": "excluded"}
    put_json("metadata.json", metadata)
    inherited_verified = all(_hash((output / item["retained_path"]).read_bytes()) == item["sha256"] for item in inherited.values())
    if not inherited_verified or _inventory(collection) != inputs or _hash(parent.db_path.read_bytes()) != parent_hash:
        raise StorageError("An input or inherited analytical asset changed during collection packaging.")
    _preflight_check(collection, parent)
    report = {"analysis_version": version_key, "previous_analysis_version": previous, "parent_database_sha256": parent_hash,
              "inherited_assets": inherited, "collection_inputs": inputs, "new_domain_tables": catalog,
              "preservation_gate": preservation, "historical_daily_repairs_applied": False,
              "statistical_results_input_version": lineage["statistical_results"],
              "no_new_significance_tests": True, "no_live_database_or_registry_writes": True,
              "tiktok_collection": "excluded", "new_collection_semantics": "Evidence retained at supplied grain; independent collection audit required for activation."}
    put_json("audit/meta_collection_import.json", report)
    put_json("audit/final_validation.json", {"analysis_version": version_key, "previous_analysis_version": previous,
             "checks": {"inherited_assets_unchanged": True, "collection_input_bytes_unchanged": True,
                        "new_csv_structure_valid": True, "parent_database_unchanged": True,
                        "historical_canonical_tables_unchanged": True, "historical_statistical_results_unchanged": True,
                        "tik_tok_not_collected": True, "no_new_significance_tests": True},
             "limitations": ["No historical Follows or Stories values are replaced by this packaging operation.",
                             "Manual/paid/reporting evidence remains at its original grain; unknown values are not zeros.",
                             "Caption references do not establish audio use, exposure, conversion or causal effects."]})
    note = f"""# Meta collection\n\nVersion `{version_key}` inherits `{previous}` without changing its analytical tables or statistical results. New Ads reporting, repair status and post/song/event references are separate evidence under `social/meta_collection/`. Original collection files are under `raw/meta_collection/`. No historical daily repairs are applied by this package builder.\n\nCollection timestamps and reporting windows differ. Unknown dates and unavailable values remain explicit; lifetime observations are not period activity. Ads breakdowns and campaign/ad-set/ad levels overlap, and unique audiences/ratios are nonadditive. Caption references and event mentions do not prove audio use, an event occurrence or streaming attribution. Historical tests retain input version `{lineage['statistical_results']}`. TikTok collection is excluded.\n\nSee `audit/meta_collection_import.json`, `social/meta_collection/collection_status.csv`, and the predecessor metadata preserved under `raw/meta_predecessor_metadata/`.\n"""
    put("META_COLLECTION_HANDOFF.md", note.encode("utf-8"))
    raw_manifest = [{"path": path.relative_to(output).as_posix(), "bytes": path.stat().st_size, "sha256": _hash(path.read_bytes())}
                    for path in sorted((output / "raw").rglob("*")) if path.is_file()]
    put_json("raw_sha256.json", raw_manifest)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                zipped.write(path, output.name + "/" + path.relative_to(output).as_posix())
    return {"package_root": str(output), "zip_path": str(archive), "zip_sha256": _hash(archive.read_bytes()),
            "label": label, "staging_metadata": {key: value for key, value in metadata.items() if key != "label"},
            "input_files": len(inputs), "inherited_assets": len(inherited), "collection_tables": len(tables) + 1,
            "historical_daily_repairs_applied": False, "live_data_changed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--zip-path", required=True, type=Path)
    parser.add_argument("--parent-database", type=Path, help="Defaults to the active registered analysis")
    parser.add_argument("--version-key", default=VERSION)
    parser.add_argument("--label", default=LABEL)
    args = parser.parse_args()
    predecessor = AnalysisRepository(args.parent_database) if args.parent_database else load_registered_analysis(load_settings().data_dir)
    if predecessor is None:
        raise StorageError("An existing analysis predecessor is required.")
    print(json.dumps(build_meta_collection(predecessor, args.collection_root, args.output_dir, args.zip_path,
                                          version_key=args.version_key, label=args.label), ensure_ascii=False, indent=2))
