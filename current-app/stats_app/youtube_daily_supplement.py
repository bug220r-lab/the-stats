"""Stage a separate, source-backed annual YouTube daily-data supplement.

The input manifest describes four newly retrieved native exports and their
retained UI evidence. Native ZIP bytes and all members remain unchanged.
Registration only appends the new collection after verifying its base lineage;
base collections, existing databases and analysis pointers are never edited.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import csv
import io
import json
import mimetypes
from pathlib import Path
import re
import sqlite3
import tempfile
import zipfile

from stats_app.analysis_repository import AnalysisRepository, SCHEMA_VERSION, _csv, _dtype, _sha
from stats_app.storage import StorageError
from stats_app.youtube_repository import (
    CHANNEL_ID, COLLECTION_KEY, EXPECTED_SHA256, CORE_KEY, _member_name, _row_keys, _zip_assets,
)

SUPPLEMENT_KIND = "daily_supplement"
ZIP_FILENAME = "supplement.zip"
MANIFEST_NAME = "collection_manifest.json"
REPORTING_START = "2025-10-22"
REPORTING_END = "2026-10-21"
EXPECTED_DATES = {(date(2025, 10, 22) + timedelta(days=n)).isoformat() for n in range(365)}
METRICS = {
    "watch_time_hours": ("Watch time (hours)", "hours", "additive"),
    "average_view_duration_seconds": ("Average view duration", "seconds", "nonadditive"),
    "subscribers_gained": ("Subscribers gained", "count", "additive"),
    "subscribers_lost": ("Subscribers lost", "count", "additive"),
}
DAILY_PATH = "normalized/channel_daily.csv"
DAILY_COLUMNS = (
    "collection_key", "parent_collection_key", "channel_id", "channel_name", "channel_handle", "channel_type",
    "report_scope", "source_timezone", "report_id", "grain", "snapshot_class", "period_kind", "reporting_start",
    "reporting_end", "activity_date", "report_content_format", "canonical_content_format", "content_format",
    "filters_json", "report_breakdown", "video_id", "video_title", "dimension_json", "metric", "value",
    "value_status", "unit", "aggregation", "source_field", "source_value_raw", "source_file", "source_row_number",
    "source_table_role", "source_sha256", "source_zip_path", "source_zip_sha256", "retrieved_at_utc",
    "retrieved_at_basis", "source_url", "source_export_url", "evidence_paths_json", "quality_notes",
)


def _require(condition, message):
    if not condition:
        raise StorageError("YouTube daily supplement validation failed: " + message)


def _json(raw, name):
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise StorageError("Invalid supplement JSON: " + name) from exc


def _csv_bytes(records, fields):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader(); writer.writerows(records)
    return output.getvalue().encode("utf-8")


def _number(raw, metric):
    """Normalize documented source units, retaining the exact cell elsewhere."""
    text = raw.strip()
    if not text or text in {"-", "–", "—", "�"}:
        return "", "unavailable", "source_blank_or_dash; no suppression cause inferred"
    if text.casefold() in {"n/a", "not applicable"}:
        return "", "not_applicable", "source_explicit_not_applicable"
    if text.casefold() in {"suppressed", "privacy threshold"}:
        return "", "suppressed", "source_explicit_suppression"
    try:
        if metric == "average_view_duration_seconds":
            # Do not guess the unit of an unlabelled numeric duration cell.
            _require(bool(re.fullmatch(r"\d+:[0-5]\d:[0-5]\d(?:\.\d+)?", text)), "expected native h:mm:ss average duration")
            hours, minutes, seconds = (Decimal(p) for p in text.split(":"))
            number = hours * 3600 + minutes * 60 + seconds
        else:
            _require(bool(re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text)), "unexpected native numeric format")
            number = Decimal(text.replace(",", ""))
            if metric in {"subscribers_gained", "subscribers_lost"}:
                _require(number == number.to_integral_value(), "subscriber counts must be integral")
        _require(number.is_finite(), "nonfinite numeric source value")
        return format(number, "f"), "zero" if number == 0 else "observed", ""
    except InvalidOperation as exc:
        raise StorageError("Invalid native daily metric value") from exc


def normalize_daily_export(zip_bytes, report, collection):
    """Read only the selected metric's native daily total series.

    The native table may omit dates; it is preserved as evidence and is never
    substituted for the complete daily chart total series.
    """
    metric = report["metric"]
    _require(metric in METRICS, "unsupported requested metric")
    source_field, unit, aggregation = METRICS[metric]
    members = _zip_assets(zip_bytes)
    _require("Totals.csv" in members, "native Totals.csv daily series is required")
    header, rows = _csv(members["Totals.csv"], "Totals.csv")
    _require(header == ["Date", source_field], "Totals.csv must contain exactly Date and the selected metric")
    dates = [row[0] for row in rows]
    _require(len(dates) == len(set(dates)), "duplicate dates in native daily total series")
    _require(set(dates) == EXPECTED_DATES and len(rows) == 365, "native daily series must supply all 365 dates; no dates are fabricated")
    native_digest = _sha(zip_bytes)
    _require(report["sha256"] == native_digest, "native ZIP hash differs from collection manifest")
    member_path = f"extracted/{report['report_id']}/Totals.csv"
    records = []
    for row_number, (activity_date, raw) in enumerate(rows, 2):
        value, status, quality = _number(raw, metric)
        records.append({
            "collection_key": collection["collection_key"], "parent_collection_key": COLLECTION_KEY,
            "channel_id": CHANNEL_ID, "channel_name": collection["channel"]["channel_name"],
            "channel_handle": collection["channel"]["channel_handle"], "channel_type": "standard_channel",
            "report_scope": "channel_owned", "source_timezone": "America/Los_Angeles", "report_id": report["report_id"],
            "grain": "channel_daily", "snapshot_class": "newly_retrieved_supplement", "period_kind": "annual_current",
            "reporting_start": REPORTING_START, "reporting_end": REPORTING_END, "activity_date": activity_date,
            "report_content_format": "all", "canonical_content_format": "all", "content_format": "all",
            "filters_json": "{}", "report_breakdown": "date", "video_id": "", "video_title": "", "dimension_json": "",
            "metric": metric, "value": value, "value_status": status, "unit": unit, "aggregation": aggregation,
            "source_field": source_field, "source_value_raw": raw, "source_file": member_path,
            "source_row_number": str(row_number), "source_table_role": "chart_total_daily", "source_sha256": _sha(members["Totals.csv"]),
            "source_zip_path": report["original_path"], "source_zip_sha256": native_digest,
            "retrieved_at_utc": report["retrieved_at_utc"], "retrieved_at_basis": report["retrieved_at_basis"],
            "source_url": report["source_url"], "source_export_url": report.get("source_export_url", ""),
            "evidence_paths_json": json.dumps(report["evidence_paths"], ensure_ascii=False), "quality_notes": quality,
        })
    return records, members


def _read_sources(root):
    assets = {}
    for path in sorted(root.rglob("*")):
        _require(not path.is_symlink() and not (hasattr(path, "is_junction") and path.is_junction()), "source links/junctions are forbidden")
        if path.is_file():
            relative = _member_name(path.relative_to(root).as_posix())
            _require(not relative.startswith(("normalized/", "extracted/")) and relative != "package_manifest.json", "input must contain originals/evidence, not derived outputs")
            assets[relative] = path.read_bytes()
    _require(MANIFEST_NAME in assets, "collection_manifest.json is required")
    return assets


def _validate_manifest(assets):
    manifest = _json(assets[MANIFEST_NAME], MANIFEST_NAME)
    _require(manifest.get("schema_version") == 1, "unsupported collection manifest schema")
    key = manifest.get("collection_key", "")
    _require(bool(re.fullmatch(r"youtube-daily-\d{8}(?:-[a-z0-9]+)?", key)), "new dated daily supplement key is required")
    _require(isinstance(manifest.get("label"), str) and manifest["label"].strip(), "collection label is required")
    _require(manifest.get("parent_collection_key") == COLLECTION_KEY and manifest.get("parent_zip_sha256") == EXPECTED_SHA256, "base collection lineage must remain pinned")
    try:
        retrieved = date.fromisoformat(manifest["retrieval_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise StorageError("A calendar retrieval_date is required") from exc
    _require(retrieved.isoformat() == manifest["retrieval_date"], "retrieval date must be ISO calendar date")
    _require(key.split("-")[2] == retrieved.strftime("%Y%m%d"), "dated supplement key must match retrieval date")
    channel = manifest.get("channel", {})
    expected_channel = {"channel_id": CHANNEL_ID, "channel_name": "[REDACTED] TV", "channel_handle": "@redactedbandoh", "channel_type": "standard_channel", "report_scope": "channel_owned", "source_timezone": "America/Los_Angeles"}
    _require(all(channel.get(k) == v for k, v in expected_channel.items()), "verified channel account/scope/timezone required")
    reports = manifest.get("reports", [])
    _require(isinstance(reports, list) and len(reports) == 4 and {r.get("metric") for r in reports} == set(METRICS), "exactly four distinct requested metric exports required")
    _require(len({r.get("report_id") for r in reports}) == 4, "distinct report IDs are required")
    for report in reports:
        _require(bool(re.fullmatch(r"[a-zA-Z0-9_-]+", report.get("report_id", ""))), "safe report ID required")
        _require(report.get("reporting_start") == REPORTING_START and report.get("reporting_end") == REPORTING_END, "inclusive annual reporting bounds required")
        _require(report.get("source_timezone") == "America/Los_Angeles" and report.get("report_scope") == "channel_owned"
                 and report.get("report_content_format") == "all" and report.get("filters_json") == "{}", "unfiltered all-format channel-owned scope required")
        original = _member_name(report.get("original_path"))
        _require(original.startswith("originals/") and original in assets, "retained original native ZIP is required")
        _require(_sha(assets[original]) == report.get("sha256"), "native ZIP hash mismatch")
        _require(isinstance(report.get("source_url"), str) and CHANNEL_ID in report["source_url"] and report["source_url"].startswith("https://studio.youtube.com/"), "channel Studio source URL required")
        try:
            timestamp = datetime.fromisoformat(report["retrieved_at_utc"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError) as exc:
            raise StorageError("UTC retrieval timestamp is required") from exc
        _require(timestamp.utcoffset() == timedelta(0), "retrieval timestamp must explicitly be UTC")
        _require(isinstance(report.get("retrieved_at_basis"), str) and bool(report["retrieved_at_basis"].strip()), "retrieval timestamp basis must be explicit")
        evidence = report.get("evidence_paths", [])
        _require(isinstance(evidence, list) and evidence, "retained account/date/metric/scope UI evidence is required")
        for name in evidence:
            _require(_member_name(name) in assets and not name.startswith("originals/"), "UI evidence file is missing")
    return manifest


def _supplement_keys(collection_key, path, header, rows):
    keys = _row_keys(path, header, rows)
    return [_sha((collection_key + ":" + key).encode("utf-8")) for key in keys]


def _build_assets(source_assets, manifest):
    assets = dict(source_assets)
    records, source_files, index, coverage, checks = [], [], [], [], []
    for report in manifest["reports"]:
        native_rows, members = normalize_daily_export(assets[report["original_path"]], report, manifest)
        records.extend(native_rows)
        for name, raw in members.items():
            member_path = f"extracted/{report['report_id']}/{name}"
            assets[member_path] = raw
            source_files.append({"report_id": report["report_id"], "member": name, "source_path": member_path,
                                 "sha256": _sha(raw), "bytes": str(len(raw))})
        statuses = Counter(row["value_status"] for row in native_rows)
        numeric_dates = statuses["zero"] + statuses["observed"]
        index.append({**report, "evidence_paths": json.dumps(report["evidence_paths"], ensure_ascii=False),
                      "native_members": len(members), "reported_dates": 365, "numeric_dates": numeric_dates,
                      "status": "complete", "numeric_coverage_status": "complete" if numeric_dates == 365 else "partial",
                      "status_note": "All 365 native calendar rows retained; numeric availability is separate from date coverage."})
        coverage.append({"collection_key": manifest["collection_key"], "report_id": report["report_id"], "channel_id": CHANNEL_ID,
                         "metric": report["metric"], "unit": METRICS[report["metric"]][1], "reporting_start": REPORTING_START,
                         "reporting_end": REPORTING_END, "source_timezone": "America/Los_Angeles", "report_scope": "channel_owned",
                         "expected_dates": 365, "observed_dates": 365, "numeric_dates": numeric_dates, "missing_dates_count": 0,
                         "unavailable_values": statuses["unavailable"], "suppressed_values": statuses["suppressed"],
                         "not_applicable_values": statuses["not_applicable"], "explicit_zero_values": statuses["zero"],
                         "date_coverage_status": "complete", "numeric_coverage_status": "complete" if numeric_dates == 365 else "partial"})
        checks.extend([{"report_id": report["report_id"], "check": "native_zip_sha256", "status": "pass", "detail": report["sha256"]},
                       {"report_id": report["report_id"], "check": "native_daily_dates", "status": "pass", "detail": "365 unique source dates, exactly 2025-10-22 through 2026-10-21 inclusive Pacific"}])
    records.sort(key=lambda r: (r["metric"], r["activity_date"]))
    assets[DAILY_PATH] = _csv_bytes(records, DAILY_COLUMNS)
    table_records = {"normalized/collection_index.csv": index, "normalized/source_files.csv": source_files,
                     "normalized/daily_coverage.csv": coverage, "normalized/validation_checks.csv": checks,
                     "normalized/metric_dictionary.csv": [{"metric": metric, "source_field": spec[0], "unit": spec[1], "aggregation": spec[2]} for metric, spec in METRICS.items()]}
    for path, rows in table_records.items():
        # Report metadata may have optional evidence fields on just one report.
        header = list(dict.fromkeys(c for row in rows for c in row))
        assets[path] = _csv_bytes(rows, header)
    parsed = {path: _csv(raw, path) for path, raw in assets.items() if path.startswith("normalized/") and path.endswith(".csv")}
    for path, (header, rows) in parsed.items():
        _supplement_keys(manifest["collection_key"], path, header, rows)
    package_manifest = {"collection_key": manifest["collection_key"], "files": [{"path": name, "bytes": len(raw), "sha256": _sha(raw)} for name, raw in sorted(assets.items())]}
    assets["package_manifest.json"] = (json.dumps(package_manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return assets, parsed, {"native_exports": 4, "native_daily_rows": len(records), "native_members": len(source_files),
                            "value_status_counts": dict(Counter(r["value_status"] for r in records)), "metric_coverage": coverage}


class DailySupplementRepository(AnalysisRepository):
    def __init__(self, dbpath):
        super().__init__(dbpath)
        _require(self._metadata.get("collection_kind") == SUPPLEMENT_KIND and self._metadata.get("parent_collection_key") == COLLECTION_KEY, "not a daily supplement database")

    def table(self, path, *, raw=False):
        frame = super().table(path, raw=raw)
        frame.attrs.update(collection_key=self.metadata["collection_key"], collection_kind=SUPPLEMENT_KIND,
                           baseline_status="newly_retrieved_supplement", source_timezone="America/Los_Angeles")
        return frame

    def row_keys(self, path):
        frame = self.table(path, raw=True)
        expected = _supplement_keys(self.metadata["collection_key"], path, list(frame.columns), frame.values.tolist())
        with self._connection() as db:
            stored = [r[0] for r in db.execute("SELECT row_key FROM youtube_row_keys WHERE asset_path=? ORDER BY csv_record", (path,))]
        _require(stored == expected, "persisted stable keys differ from source")
        return stored

    def row_provenance(self, path):
        frame = super().row_provenance(path)
        frame.insert(0, "collection_key", self.metadata["collection_key"])
        frame.insert(1, "stable_row_key", self.row_keys(path))
        return frame


def _write_database(path, assets, parsed, zip_bytes, metadata):
    with path.open("xb"):
        pass
    db = sqlite3.connect(path)
    try:
        db.executescript("""
            CREATE TABLE metadata(key TEXT PRIMARY KEY,json TEXT NOT NULL);
            CREATE TABLE original_zip(id INTEGER PRIMARY KEY,filename TEXT,sha256 TEXT,source_url TEXT,contents BLOB);
            CREATE TABLE assets(path TEXT PRIMARY KEY,sha256 TEXT NOT NULL,bytes INTEGER,media_type TEXT,is_table INTEGER,
                row_count INTEGER,columns_json TEXT,types_json TEXT,contents BLOB NOT NULL);
            CREATE TABLE analysis_rows(asset_path TEXT NOT NULL,csv_record INTEGER NOT NULL,row_json TEXT NOT NULL,PRIMARY KEY(asset_path,csv_record));
            CREATE TABLE youtube_row_keys(asset_path TEXT NOT NULL,csv_record INTEGER NOT NULL,row_key TEXT UNIQUE NOT NULL,PRIMARY KEY(asset_path,csv_record));
        """)
        with db:
            db.execute("INSERT INTO metadata VALUES('package',?)", (json.dumps(metadata, ensure_ascii=False),))
            db.execute("INSERT INTO original_zip VALUES(1,?,?,?,?)", (ZIP_FILENAME, _sha(zip_bytes), metadata["source_url"], zip_bytes))
            for name, raw in sorted(assets.items()):
                header, rows = parsed.get(name, ([], []))
                types = {c: _dtype(c, [r[i] for r in rows]) for i, c in enumerate(header)}
                db.execute("INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)", (name, _sha(raw), len(raw), mimetypes.guess_type(name)[0] or "application/octet-stream",
                           int(name in parsed), len(rows), json.dumps(header), json.dumps(types), raw))
                db.executemany("INSERT INTO analysis_rows VALUES(?,?,?)", ((name, i, json.dumps(row, ensure_ascii=False, separators=(",", ":"))) for i, row in enumerate(rows, 2)))
                keys = _supplement_keys(metadata["collection_key"], name, header, rows) if name in parsed else []
                db.executemany("INSERT INTO youtube_row_keys VALUES(?,?,?)", ((name, i, key) for i, key in enumerate(keys, 2)))
            db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        _require(db.execute("PRAGMA quick_check").fetchone()[0] == "ok", "SQLite integrity")
    finally:
        db.close()


def build_daily_supplement(source_root, output_dir):
    """Stage a new immutable supplement; registration is a separate operation."""
    source, output = Path(source_root).resolve(), Path(output_dir).resolve()
    _require(source.is_dir() and not output.is_relative_to(source) and not source.is_relative_to(output), "stage outside the frozen collection source directory")
    source_assets = _read_sources(source)
    manifest = _validate_manifest(source_assets)
    assets, parsed, validation = _build_assets(source_assets, manifest)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(assets.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)); entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, raw)
    zip_bytes = stream.getvalue(); zip_hash = _sha(zip_bytes)
    if output.exists():
        _require((output / "youtube.sqlite3").is_file() and (output / ZIP_FILENAME).is_file(), "output directory already exists without a complete supplement")
        repo = DailySupplementRepository(output / "youtube.sqlite3")
        _require(repo.original_zip() == zip_bytes and (output / ZIP_FILENAME).read_bytes() == zip_bytes, "conflicting supplement package")
        for path in repo.tables:
            repo.row_keys(path)
        return {**repo.metadata, "database": str(repo.db_path), "database_sha256": _sha(repo.db_path.read_bytes()), "idempotent": True, "integrity": "ok"}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".youtube-daily-stage-", dir=output.parent) as temporary:
        stage = Path(temporary)
        (stage / ZIP_FILENAME).write_bytes(zip_bytes)
        metadata = {"schema_version": SCHEMA_VERSION, "platform": "youtube", "collection_kind": SUPPLEMENT_KIND,
                    "collection_key": manifest["collection_key"], "label": manifest["label"], "parent_collection_key": COLLECTION_KEY,
                    "parent_zip_sha256": EXPECTED_SHA256, "retrieval_date": manifest["retrieval_date"],
                    "baseline_status": "newly_retrieved_supplement", "loaded_at": datetime.now(timezone.utc).isoformat(),
                    "source_url": f"https://studio.youtube.com/channel/{CHANNEL_ID}/analytics", "zip_filename": ZIP_FILENAME,
                    "zip_sha256": zip_hash, "package_sha256": _sha(assets["package_manifest.json"]),
                    "files": len(assets), "parsed_tables": len(parsed), "parsed_records": sum(len(v[1]) for v in parsed.values()),
                    "table_rows": {p: len(v[1]) for p, v in parsed.items()}, "validation": validation,
                    "reporting_periods": [{"period_kind": "annual_current", "reporting_start": REPORTING_START, "reporting_end": REPORTING_END,
                                           "snapshot_class": "newly_retrieved_supplement"}], **manifest["channel"]}
        _write_database(stage / "youtube.sqlite3", assets, parsed, zip_bytes, metadata)
        repo = DailySupplementRepository(stage / "youtube.sqlite3")
        _require(repo.original_zip() == zip_bytes, "persisted package ZIP")
        for path in repo.tables:
            repo.row_keys(path)
        report = {**metadata, "database": str(output / "youtube.sqlite3"), "database_sha256": _sha((stage / "youtube.sqlite3").read_bytes()),
                  "idempotent": False, "integrity": "ok"}
        (stage / "youtube_daily_supplement_import.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stage.rename(output)
    return report


def import_daily_supplement(source_root, data_dir):
    """Atomically append a verified supplement to its existing parent library."""
    # Imported here so the shared registry can dispatch to this repository
    # without a module-import cycle.
    from stats_app.youtube_repository import (
        REGISTRY_FILENAME, ZIP_FILENAME as BASE_ZIP_FILENAME,
        _atomic_json, _import_lock, _no_links, _read_registry, load_registered_youtube,
    )

    source = Path(source_root).resolve()
    manifest = _validate_manifest(_read_sources(source))
    root = Path(data_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    with _import_lock(root):
        registry = _read_registry(root)
        parent_record = next((r for r in registry["collections"] if r["key"] == COLLECTION_KEY), None)
        _require(parent_record is not None, "the pinned base YouTube collection must already be registered")
        _require(parent_record.get("zip_sha256") == EXPECTED_SHA256, "registered parent ZIP identity differs")
        parent = load_registered_youtube(root, COLLECTION_KEY)
        parent_hash = _sha(parent.db_path.read_bytes())
        _require(parent_hash == parent_record.get("database_sha256"), "registered parent database hash differs")
        parent_zip = _no_links(root / parent_record["evidence_root"] / parent_record.get("zip_filename", BASE_ZIP_FILENAME), root)
        _require(parent_zip.is_file() and _sha(parent_zip.read_bytes()) == EXPECTED_SHA256
                 and _sha(parent.original_zip()) == EXPECTED_SHA256, "retained parent source ZIP hash differs")
        collection_parent = _no_links(root / "collections", root)
        collection_parent.mkdir(exist_ok=True)
        key = manifest["collection_key"]
        output = _no_links(collection_parent / key, root)
        existing = next((r for r in registry["collections"] if r["key"] == key), None)
        _require(existing is None or output.exists(), "registered supplement directory is missing; refusing reconstruction")
        report = build_daily_supplement(source, output)
        _require(_sha(parent.db_path.read_bytes()) == parent_hash and _sha(parent_zip.read_bytes()) == EXPECTED_SHA256,
                 "parent collection changed during supplement import")
        record = {"key": key, "database": f"collections/{key}/youtube.sqlite3", "evidence_root": f"collections/{key}",
                  "label": report["label"], "collection_kind": SUPPLEMENT_KIND, "zip_filename": ZIP_FILENAME,
                  "zip_sha256": report["zip_sha256"], "database_sha256": report["database_sha256"],
                  "parent_collection_key": COLLECTION_KEY, "parent_zip_sha256": EXPECTED_SHA256}
        if existing is not None:
            _require(existing == record, "registered supplement metadata or database hash conflicts")
        else:
            registry["collections"].append(record)
            _atomic_json(root / REGISTRY_FILENAME, registry)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output-dir", type=Path, help="Stage only; do not register")
    destination.add_argument("--data-dir", type=Path, help="Register a new supplement beside its pinned parent")
    args = parser.parse_args()
    if args.data_dir:
        if any(part.casefold().startswith("onedrive") for part in args.data_dir.expanduser().resolve().parts):
            parser.error("Keep active SQLite collections outside OneDrive; choose local durable storage.")
        result = import_daily_supplement(args.source_root, args.data_dir)
    else:
        result = build_daily_supplement(args.source_root, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
