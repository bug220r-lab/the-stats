"""Import the verified October 25 Apple package as separate local snapshots.

Default: rehearse against a consistent backup only. --execute additionally
imports into the configured local library after all rehearsal checks pass.
Retains the pre-import backup, rehearsal DB and machine-readable evidence.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stats_app.backup import backup_database
from stats_app.calculations import summarize_metric
from stats_app.config import load_settings
from stats_app.storage import SQLiteRepository, ImportConflictError
from stats_app.validation import validate_records

TABLES = ("snapshots", "source_files", "imports", "observations", "observation_sources")
LABELS = {"daily": "apple-music-20261025-daily", "aggregate": "apple-music-20261025-aggregate"}
EXPECTED = {"daily": 25738, "aggregate": 950}


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def logical_state(database, limits=None):
    """Fingerprint all original rows, including source bytes and baseline flags."""
    result = {}
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        for table in TABLES:
            cutoff = limits[table]["maximum_rowid"] if limits else None
            sql = f'SELECT rowid, * FROM "{table}"'
            params = ()
            if cutoff is not None:
                sql += " WHERE rowid <= ?"
                params = (cutoff,)
            digest, count, maximum = hashlib.sha256(), 0, 0
            for row in db.execute(sql + " ORDER BY rowid", params):
                converted = [{"blob_bytes": len(v), "sha256": sha(v)} if isinstance(v, bytes) else v for v in row]
                digest.update(json.dumps(converted, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode())
                digest.update(b"\n")
                count += 1
                maximum = row[0]
            result[table] = {"rows": count, "maximum_rowid": maximum, "logical_sha256": digest.hexdigest()}
        db.rollback()
    return result


def protected_files(data_dir):
    paths = set(data_dir.glob("*.json"))
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "database" and isinstance(item, str):
                    target = (data_dir / item).resolve()
                    if not target.is_relative_to(data_dir) or target == data_dir / "stats.sqlite3":
                        raise ValueError("Unexpected registered database path")
                    paths.add(target)
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    for path in list(paths):
        walk(json.loads(path.read_text(encoding="utf-8")))
    return {str(path): file_sha(path) for path in sorted(paths)}


def dashboard_checks(repo):
    daily = repo.observations(LABELS["daily"])
    aggregate = repo.observations(LABELS["aggregate"])
    assert len(daily) == EXPECTED["daily"] and len(aggregate) == EXPECTED["aggregate"]
    assert set(daily.time_grain) == {"daily"}
    assert set(aggregate.time_grain) == {"period", "monthly"}
    assert daily.status.value_counts().to_dict() == {"observed": 25738}
    assert aggregate.status.value_counts().to_dict() == {"observed": 731, "missing": 219}
    assert aggregate.loc[aggregate.status.eq("missing"), "value"].isna().all()
    artist = daily.loc[daily.entity_type.eq("artist") & daily.metric.eq("plays")]
    checks = {}
    for key, start, expected, count in [
        ("latest_7", "2026-10-17", 154, 7),
        ("latest_28", "2026-09-26", 507, 28),
        ("latest_90", "2026-07-26", 1828, 90),
        ("year_to_date", "2026-01-01", 8147, 296),
        ("all_captured_daily", "2023-05-01", 16495, 1272),
    ]:
        rows = artist.loc[artist.period_start.ge(start) & artist.period_end.le("2026-10-23")]
        summary = summarize_metric(rows)
        assert summary.value == expected and summary.observed_rows == count and summary.missing_rows == 0
        checks[key] = {"start": start, "end": "2026-10-23", **asdict(summary)}
    listeners = daily.loc[daily.entity_type.eq("artist") & daily.metric.eq("daily_unique_listeners") & daily.period_start.ge("2026-09-26")]
    listener_summary = summarize_metric(listeners)
    assert listener_summary.value is None and listener_summary.observed_rows == 28
    checks["daily_listener_aggregation_withheld"] = asdict(listener_summary)
    scope = aggregate.loc[aggregate.entity_type.eq("artist") & aggregate.dimensions_json.map(lambda value: json.loads(value).get("entity_scope") == "artist" and set(json.loads(value)) <= {"entity_scope", "precision"}) & aggregate.period_start.eq("2026-09-26") & aggregate.period_end.eq("2026-10-23") & aggregate.time_grain.eq("period")]
    for metric, expected in {"plays": 507, "average_daily_listeners": 11, "shazam_count": 3, "radio_spins": 1, "purchases": 0}.items():
        rows = scope.loc[scope.metric.eq(metric)]
        summary = summarize_metric(rows)
        assert len(rows) == 1 and summary.value == expected, (metric, len(rows), asdict(summary))
        checks["aggregate_latest28_" + metric] = asdict(summary)
    checks["counts"] = {"daily": len(daily), "aggregate": len(aggregate), "aggregate_statuses": aggregate.status.value_counts().to_dict(), "aggregate_grains": aggregate.time_grain.value_counts().to_dict()}
    return checks


def import_and_verify(database, inputs, *, rehearsal):
    repo = SQLiteRepository(database)
    results = []
    for item in inputs:
        result = repo.import_dataset(item["raw"], item["name"], item["records"], LABELS[item["kind"]], baseline=False, provenance=item["provenance"])
        assert result.imported_rows == len(item["records"]) and result.duplicate_rows == 0
        results.append(asdict(result))
    checks = dashboard_checks(repo)
    before_replay = logical_state(database)
    replays = []
    for item in inputs:
        result = repo.import_dataset(item["raw"], item["name"], item["records"], LABELS[item["kind"]], baseline=False, provenance=item["provenance"])
        assert result.imported_rows == 0 and result.duplicate_import and result.duplicate_rows == len(item["records"])
        replays.append(asdict(result))
    assert logical_state(database) == before_replay, "Exact replay changed stored data"
    # Exercise equal-overlap and whole-file conflict protection on the real
    # repository's disposable preview, never with synthetic live sources.
    example = inputs[0]["records"].loc[inputs[0]["records"].status.eq("observed")].iloc[0].to_dict()
    overlap = repo.preview_dataset(b"Preview-only equal overlap\n", "preview-only-overlap.txt", [example], LABELS["daily"], baseline=False)
    assert overlap.imported_rows == 0 and overlap.duplicate_rows == 1
    conflict_rejected = False
    try:
        repo.preview_dataset(b"Preview-only atomic conflict\n", "preview-only-conflict.txt", [{**example, "entity_id": "preview-only-never-committed"}, {**example, "value": float(example["value"]) + 1}], LABELS["daily"], baseline=False)
    except ImportConflictError:
        conflict_rejected = True
    assert conflict_rejected and logical_state(database) == before_replay
    for label in LABELS.values():
        repo.seal_snapshot(label)
    sealed_state = logical_state(database)
    for item in inputs:
        result = repo.import_dataset(item["raw"], item["name"], item["records"], LABELS[item["kind"]], baseline=False, provenance=item["provenance"])
        assert result.imported_rows == 0 and result.duplicate_import
    assert logical_state(database) == sealed_state, "Sealed exact replay changed stored data"
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        snapshots = db.execute("SELECT label,is_baseline,sealed FROM snapshots WHERE label IN (?,?) ORDER BY label", tuple(LABELS.values())).fetchall()
    assert integrity == "ok" and len(snapshots) == 2 and all(not row[1] and row[2] for row in snapshots)
    return {"rehearsal": rehearsal, "first_import": results, "dashboard_calculations": checks, "exact_replay": replays, "exact_replay_new_observations": 0, "replay_all_tables_unchanged": True, "equal_overlap_preview_no_new_fact": True, "conflict_preview_rejected_atomically": True, "synthetic_probes_committed": False, "both_new_snapshots_non_baseline_and_sealed": True, "sealed_exact_replay_no_changes": True, "integrity_check": integrity}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="After a successful rehearsal, import into the configured local library")
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory inside this workspace")
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(ROOT) and not output.exists(), "Choose a new workspace evidence directory"
    settings = load_settings()
    assert settings.mode == "local" and settings.database_path.is_file(), "Existing local library required"
    package = ROOT / "data" / "collection" / "apple-music-20261025"
    manifest = json.loads((package / "collection_manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        assert file_sha(package / item["path"]) == item["sha256"], item["path"]
    handoff = json.loads((package / "HANDOFF_MANIFEST.json").read_text(encoding="utf-8"))
    assert all(file_sha(package / item["path"]) == item["sha256"] for item in handoff["files"])
    before = logical_state(settings.database_path)
    protected = protected_files(settings.data_dir)
    with closing(sqlite3.connect(settings.database_path.as_uri() + "?mode=ro", uri=True)) as db:
        assert not db.execute("SELECT label FROM snapshots WHERE label IN (?,?)", tuple(LABELS.values())).fetchall(), "New Apple snapshot labels already exist; inspect the previous receipt rather than reinserting"
    parse_canonical = runpy.run_path(str(package / "verify_import.py"))["parse_canonical"]
    index = json.loads((package / "normalized" / "import_batches" / "index.json").read_text(encoding="utf-8"))
    inputs = []
    entries = [("daily", package / item["path"]) for item in index["batches"]] + [("aggregate", package / "normalized" / "canonical_aggregate.csv")]
    for kind, path in entries:
        raw = path.read_bytes()
        records = parse_canonical(raw, path.name)
        assert not validate_records(records) and not records.empty
        assert set(records.platform) == {"Apple Music"}
        assert set(records.time_grain) <= ({"daily"} if kind == "daily" else {"monthly", "period"})
        inputs.append({"kind": kind, "name": path.name, "raw": raw, "records": records, "provenance": {"source_package": package.name, "source_manifest_sha256": file_sha(package / "collection_manifest.json"), "source_path": path.relative_to(package).as_posix(), "snapshot_grain_boundary": kind, "original_source_evidence": "Retained in immutable collection package; canonical evidence_ref and provenance_map.csv retain native lineage"}})
    assert {kind: sum(len(item["records"]) for item in inputs if item["kind"] == kind) for kind in LABELS} == EXPECTED
    output.mkdir(parents=True, exist_ok=False)
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "status": "preflight", "database_path": str(settings.database_path), "collection_package": str(package), "snapshot_labels": LABELS, "before": before, "protected_files_before": protected, "source_package_manifest_sha256": file_sha(package / "collection_manifest.json"), "inputs": [{"kind": item["kind"], "name": item["name"], "rows": len(item["records"]), "sha256": sha(item["raw"])} for item in inputs], "execute_requested": args.execute}
    save(output / "import_receipt.json", report)
    backup = backup_database(settings.database_path, output / "pre_import_library.sqlite3")
    report["pre_import_backup"] = {"path": str(backup), "sha256": file_sha(backup), "method": "SQLite consistent online backup"}
    assert logical_state(backup) == before
    rehearsal = backup_database(backup, output / "rehearsal.sqlite3")
    print("Preflight passed; retained consistent backup. Rehearsing complete import and replay.", flush=True)
    report["rehearsal"] = import_and_verify(rehearsal, inputs, rehearsal=True)
    assert logical_state(settings.database_path) == before and protected_files(settings.data_dir) == protected
    report["status"] = "rehearsal_passed"
    save(output / "import_receipt.json", report)
    if args.execute:
        print("Rehearsal passed; importing two new non-baseline snapshots into the configured local library.", flush=True)
        report["status"] = "live_import_in_progress"
        save(output / "import_receipt.json", report)
        report["live"] = import_and_verify(settings.database_path, inputs, rehearsal=False)
        assert logical_state(settings.database_path, before) == before, "An original local row changed"
        assert protected_files(settings.data_dir) == protected, "A registry or registered fixed database changed"
        assert all(file_sha(package / item["path"]) == item["sha256"] for item in manifest["files"])
        report.update(status="passed", original_local_rows_unchanged=True, registries_and_registered_databases_unchanged=True, collection_source_and_normalized_files_unchanged=True, after=logical_state(settings.database_path))
    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    save(output / "import_receipt.json", report)
    print(json.dumps({"status": report["status"], "daily": EXPECTED["daily"], "aggregate": EXPECTED["aggregate"], "new_observations_on_replay": 0, "receipt": str(output / "import_receipt.json")}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
