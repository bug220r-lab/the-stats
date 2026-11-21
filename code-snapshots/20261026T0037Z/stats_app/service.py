"""Validated operations shared by UI and command-line tools."""
import hashlib
import json
from pathlib import Path

from stats_app.access import Principal, require_admin
from stats_app.config import PROJECT_ROOT
from stats_app.ingestion import parse_export, read_table
from stats_app.validation import validate_records

BASELINE_MANIFEST = PROJECT_ROOT / "data" / "source" / "baseline_import_manifest.json"


def commit_import(repo, principal, *, raw_bytes, source_name, records, snapshot_label, provenance=None):
    require_admin(principal)
    issues = validate_records(records)
    if issues:
        raise ValueError("Import validation failed: " + "; ".join(issues[:20]))
    return repo.import_dataset(raw_bytes, source_name, records, snapshot_label, provenance=provenance)


def load_collected_archive(repo, principal, manifest_path=BASELINE_MANIFEST):
    """Hash-check archive exports without claiming original baseline membership.

    A legacy snapshot retains its exact stored metadata. Fresh imports use an
    explicitly unverified archive label and never set the baseline flag.
    """
    require_admin(principal)
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent.resolve()
    prepared = []
    for item in manifest["files"]:
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Source path escapes the baseline package.")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError(f"Original source checksum differs: {path.name}. Baseline import cancelled.")
        table = read_table(raw, path.name)
        if len(table) != item["native_row_count"]:
            raise ValueError(f"Original source row count differs: {path.name}.")
        records = parse_export(table, item["profile"], item["metadata"])
        issues = validate_records(records)
        if issues:
            raise ValueError("; ".join(issues[:20]))
        prepared.append((item, path, raw, records))
    existing = repo.list_snapshots()
    legacy_label = manifest["snapshot_label"]
    legacy = existing.loc[existing.label.eq(legacy_label)] if not existing.empty else existing
    snapshot_label = legacy_label if not legacy.empty else "Windows native Spotify archive · Oct 20 endpoint · baseline unverified"
    legacy_flag = bool(legacy.iloc[0].is_baseline) if not legacy.empty else False
    results = []
    for item, path, raw, records in prepared:
        results.append(repo.import_dataset(
            raw, path.name, records, snapshot_label, baseline=legacy_flag,
            provenance={"baseline_evidence": manifest["baseline_evidence"],
                        "baseline_verification": "unverified; archive membership and reporting endpoint do not prove original baseline membership",
                        "source_path": item["path"], "metadata": item["metadata"],
                        "profile": item["profile"], "package_scope": "Five original native CSVs; other archive datasets are not imported."},
        ))
    # Exact duplicate retries of legacy data should not write even its seal flag.
    if legacy.empty or not bool(legacy.iloc[0].sealed):
        repo.seal_snapshot(snapshot_label)
    return results


# Compatibility for previously saved commands/tests. Semantics are archive-only.
load_collected_baseline = load_collected_archive
