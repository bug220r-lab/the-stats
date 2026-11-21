"""Build a separate immutable snapshot of Meta Story, Ads and link evidence.

Packaging preserves every predecessor asset, including the previous collection
and statistical results. It never infers a song, missing value or conversion.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import zipfile

import pandas as pd

from stats_app.analysis_repository import AnalysisRepository, _safe_name, load_registered_analysis
from stats_app.config import load_settings
from stats_app.meta_collection import (
    PACKAGING_ASSETS, STATUS_COLUMNS, _hash, _inventory, _preflight_check,
    _read_csv, validate_collection_table,
)
from stats_app.storage import StorageError

VERSION = "meta-followup-20261023"
LABEL = "Meta follow-up · October 23, 2026 · Stories, Ads coverage and links"
PREFIX = "social/meta_followup/"
RAW_PREFIX = "raw/meta_followup/"
PREDECESSOR_PREFIX = "raw/meta_followup_predecessor_metadata/"


@dataclass(frozen=True)
class SupplementSpec:
    """Names and descriptive context for an additive evidence collection."""

    namespace: str
    lineage_key: str
    title: str
    handoff_filename: str
    evidence_type: str
    limitations: tuple[str, ...]


FOLLOWUP_SPEC = SupplementSpec(
    namespace="meta_followup", lineage_key="meta_followup", title="Meta follow-up",
    handoff_filename="META_FOLLOWUP_HANDOFF.md",
    evidence_type="Separate recent Story mapping, Ads coverage and destination evidence; previous snapshots unchanged",
    limitations=("Song/link evidence does not establish exposure, a click or a Spotify stream.",
                 "Lifetime metrics remain separate from reporting-period activity.",
                 "Empty Ads reports apply only to their captured account and reporting scope.",
                 "Original October 20 baseline membership remains unverified."),
)


def build_meta_followup(parent, collection_root, output_dir, zip_path, *, version_key=VERSION, label=LABEL):
    """Retain the original Meta follow-up namespace and public interface."""
    return build_evidence_supplement(parent, collection_root, output_dir, zip_path,
                                    version_key=version_key, label=label, spec=FOLLOWUP_SPEC)


def build_evidence_supplement(parent, collection_root, output_dir, zip_path, *, version_key, label, spec):
    """Copy reviewed evidence into a new package and ZIP, without live writes.

    All collection files are retained raw. Only normalized/*.csv and mapping/
    CSVs become new analytical tables. An explicit normalized collection status
    is required so an absent or empty table cannot imply coverage or zero spend.
    This is a storage gate; the collector's independent semantic audit remains
    required before promotion.
    """
    if not isinstance(parent, AnalysisRepository):
        parent = AnalysisRepository(parent)
    collection = Path(collection_root).resolve()
    output, archive = Path(output_dir).resolve(), Path(zip_path).resolve()
    if not isinstance(spec, SupplementSpec) or not all(
        re.fullmatch(r"[A-Za-z0-9_-]+", value) for value in (spec.namespace, spec.lineage_key)
    ):
        raise StorageError("Supplement namespace and lineage key must be safe stable identifiers.")
    prefix = f"social/{spec.namespace}/"
    raw_prefix = f"raw/{spec.namespace}/"
    predecessor_prefix = f"raw/{spec.namespace}_predecessor_metadata/"
    audit_path = f"audit/{spec.namespace}_import.json"
    _safe_name(spec.handoff_filename)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", version_key):
        raise StorageError("Follow-up version key must be a safe stable identifier.")
    if not isinstance(label, str) or not label.strip():
        raise StorageError("Follow-up version needs a nonempty label.")
    if not collection.is_dir():
        raise StorageError("The follow-up input directory is missing.")
    if output.exists() or archive.exists():
        raise FileExistsError("Preserving an existing follow-up package or ZIP; choose new paths.")
    if output.is_relative_to(collection) or archive.is_relative_to(collection) or archive.is_relative_to(output):
        raise StorageError("Output package and ZIP must be separate from inputs and each other.")
    if parent.db_path.is_relative_to(output):
        raise StorageError("Output cannot contain the predecessor database.")
    parent_hash = _hash(parent.db_path.read_bytes())
    previous = parent.metadata.get("analysis_version", getattr(parent, "registered_key", "original-analysis"))
    if previous == version_key:
        raise StorageError("The follow-up must have a new version key.")
    previous_catalog = parent.file_catalog()
    if any(path.startswith((prefix, raw_prefix, predecessor_prefix)) for path in previous_catalog.path):
        raise StorageError("The predecessor already contains this follow-up namespace; use a distinct design.")
    if audit_path in set(previous_catalog.path) or spec.handoff_filename in set(previous_catalog.path):
        raise StorageError("The supplement would replace a predecessor evidence asset.")
    inputs = _inventory(collection)
    preservation = _preflight_check(collection, parent)
    if not preservation["provided"]:
        raise StorageError("Follow-up packaging requires preflight_preservation.json.")
    preflight = json.loads((collection / "preflight_preservation.json").read_text(encoding="utf-8"))
    active = preflight.get("active_analysis", {})
    if active.get("database") and (Path(preflight["configured_data_dir"]) / _safe_name(active["database"])).resolve() != parent.db_path:
        raise StorageError("The follow-up parent must be the active analysis captured in preflight.")

    tables = {}
    for relative in inputs:
        path = Path(relative)
        if path.suffix.lower() != ".csv" or path.parts[0] not in {"normalized", "mapping"}:
            continue
        name = path.relative_to("normalized").as_posix() if path.parts[0] == "normalized" else relative
        destination = prefix + name
        if destination == prefix + "dataset_catalog.csv":
            raise StorageError("dataset_catalog.csv is reserved for verified packaging lineage.")
        if destination in tables:
            raise StorageError("Two follow-up inputs resolve to the same analytical table.")
        raw = (collection / relative).read_bytes()
        frame = validate_collection_table(_read_csv(raw, relative), relative)
        tables[destination] = {"raw": raw, "frame": frame, "source": relative}
    status = tables.get(prefix + "collection_status.csv")
    if status is None or not set(STATUS_COLUMNS).issubset(status["frame"]):
        raise StorageError("Follow-up requires normalized/collection_status.csv with explicit scope and availability.")
    frame = status["frame"]
    if frame.empty or frame.dataset.str.strip().eq("").any() or frame.status.str.strip().eq("").any() or frame.dataset.duplicated().any():
        raise StorageError("Each follow-up dataset needs one explicit nonempty status.")

    output.mkdir(parents=True, exist_ok=False)

    def put(relative, raw):
        path = output / _safe_name(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(raw)

    def put_json(relative, value):
        put(relative, (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))

    inherited = {}
    for row in previous_catalog.itertuples():
        raw = parent.original_bytes(row.path)
        retained = predecessor_prefix + row.path if row.path in PACKAGING_ASSETS else row.path
        put(retained, raw)
        inherited[row.path] = {"sha256": _hash(raw), "retained_path": retained}
    for relative, info in inputs.items():
        raw = (collection / relative).read_bytes()
        if _hash(raw) != info["sha256"]:
            raise StorageError("Follow-up input changed during packaging: " + relative)
        put(raw_prefix + relative, raw)
    catalog = []
    for path, item in tables.items():
        put(path, item["raw"])
        frame = item["frame"]
        stamps = sorted({str(value) for column in ("captured_at_utc", "snapshot_timestamp") if column in frame for value in frame[column] if value})
        catalog.append({"table": path, "source_file": item["source"], "retained_input_path": raw_prefix + item["source"],
                        "input_sha256": inputs[item["source"]]["sha256"], "sha256": _hash(item["raw"]), "rows": len(frame),
                        "capture_timestamps_supplied": " | ".join(stamps),
                        "grain": "Supplied source grain; no metric aggregation or historical replacement",
                        "scope_status": "Source-specific scope; missing settings remain unknown"})
    put(prefix + "dataset_catalog.csv", pd.DataFrame(catalog).to_csv(index=False).encode("utf-8"))
    lineage = dict(parent.metadata.get("input_lineage", {}))
    lineage.update({spec.lineage_key: version_key, "predecessor_analysis": previous})
    for kind in ("statistical_results", "cross_platform", "social"):
        lineage.setdefault(kind, previous)
    stamps = sorted({stamp[:10] for item in catalog for stamp in item["capture_timestamps_supplied"].split(" | ") if stamp})
    metadata = {
        "analysis_version": version_key, "previous_analysis_version": previous, "label": label, "input_lineage": lineage,
        "retrieval_vintage": "; ".join(stamps) if stamps else "unknown; see source evidence",
        "activity_endpoint": parent.metadata.get("activity_endpoint", "2026-10-20"),
        "baseline_endpoint": parent.metadata.get("baseline_endpoint", "2026-10-20"),
        "baseline_note": parent.metadata.get("baseline_note", "Original October 20 baseline membership remains unverified."),
        "parent_package_sha256": parent.metadata["package_sha256"], "parent_zip_sha256": parent.metadata["zip_sha256"],
        "collection_built_at_utc": datetime.now(timezone.utc).isoformat(),
        "collection_reporting_basis": "Supplied source-specific reporting windows, captures and statuses; unknown dates remain blank.",
        "evidence_type": spec.evidence_type,
        "new_significance_tests": 0, "tiktok_collection": "excluded",
    }
    put_json("metadata.json", metadata)
    if not all(_hash((output / item["retained_path"]).read_bytes()) == item["sha256"] for item in inherited.values()):
        raise StorageError("Inherited asset verification failed.")
    if _inventory(collection) != inputs or _hash(parent.db_path.read_bytes()) != parent_hash:
        raise StorageError("A follow-up input or predecessor changed during packaging.")
    _preflight_check(collection, parent)
    report = {
        "analysis_version": version_key, "previous_analysis_version": previous, "parent_database_sha256": parent_hash,
        "inherited_assets": inherited, "collection_inputs": inputs, "new_domain_tables": catalog,
        "preservation_gate": preservation, "historical_daily_repairs_applied": False,
        "statistical_results_input_version": lineage["statistical_results"], "no_new_significance_tests": True,
        "no_live_database_or_registry_writes": True, "tiktok_collection": "excluded",
        "semantics": "Evidence retained at supplied grain; independent semantic audit is required before activation.",
    }
    put_json(audit_path, report)
    put_json("audit/final_validation.json", {
        "analysis_version": version_key, "previous_analysis_version": previous,
        "checks": {"inherited_assets_unchanged": True, "collection_input_bytes_unchanged": True,
                   "new_csv_structure_valid": True, "parent_database_unchanged": True,
                   "prior_meta_collection_unchanged": True, "historical_statistical_results_unchanged": True,
                   "tiktok_not_collected": True, "no_new_significance_tests": True},
        "limitations": list(spec.limitations),
    })
    note = (f"# {spec.title}\n\nVersion `{version_key}` inherits `{previous}`. All predecessor assets, including the previous Meta "
            f"collection and statistical results, remain byte-identical. New evidence is under `{prefix}`; originals are "
            f"under `{raw_prefix}`. Only package metadata is relocated into `{predecessor_prefix}`.\n\n"
            "No song assignment, missing metric, paid coverage, conversion or causal effect is inferred by this package builder. "
            "Collection status records the scope and unresolved gaps. TikTok is excluded.\n")
    put(spec.handoff_filename, note.encode("utf-8"))
    manifest = [{"path": path.relative_to(output).as_posix(), "bytes": path.stat().st_size, "sha256": _hash(path.read_bytes())}
                for path in sorted((output / "raw").rglob("*")) if path.is_file()]
    put_json("raw_sha256.json", manifest)
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
    parser.add_argument("--collection-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-path", type=Path, required=True)
    parser.add_argument("--parent-database", type=Path)
    args = parser.parse_args()
    parent = AnalysisRepository(args.parent_database) if args.parent_database else load_registered_analysis(load_settings().data_dir)
    if parent is None:
        raise StorageError("An existing active analysis predecessor is required.")
    print(json.dumps(build_meta_followup(parent, args.collection_root, args.output_dir, args.zip_path), ensure_ascii=False, indent=2))
