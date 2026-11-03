"""Import and read the immutable October 23 YouTube collection separately.

Canonical tables retain their source grains; no observations are added to the
upload database or any analysis version. Original ZIP and every member survive.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import zipfile

import pandas as pd

from stats_app.analysis_repository import AnalysisRepository, SCHEMA_VERSION, _csv, _dtype, _safe_name, _sha
from stats_app.config import load_settings
from stats_app.storage import StorageError

COLLECTION_KEY = "youtube-20261023"
EXPECTED_SHA256 = "33da7c508f443ebc883a6c2f86425d1284917526ea5ba1cbbe7f1e0ad08ba6ef"
CHANNEL_ID = "UCkSoRiC9Pz9hEbJOOTYaq_w"
LABEL = "YouTube · October 23, 2026 retrieval · channel-owned collection"
ZIP_FILENAME = "The_Stats_YouTube_Collection_2026-10-23.zip"
SOURCE_URL = "https://drive.google.com/file/d/1_vRFRVCXJ2dONKFS39nHFMb_Tf02irRm/view"
REGISTRY_FILENAME = "youtube_collections.json"
DOMAIN_NAMES = ("channel_daily", "channel_period", "dimension_daily", "dimension_period", "video_daily", "video_period")
DOMAIN_PATHS = tuple(f"normalized/{name}.csv" for name in DOMAIN_NAMES)
PARSED_PATHS = frozenset(DOMAIN_PATHS + tuple(f"normalized/{name}.csv" for name in (
    "channel_daily_wide", "video_daily_wide_365", "video_inventory", "video_song_mapping",
    "collection_index", "collection_status", "daily_coverage", "field_dictionary",
    "metric_dictionary", "source_files", "validation_checks", "value_status_dictionary",
)) + tuple(f"retention/retention_{name}.csv" for name in (
    "observations", "ui_summary", "collection_index", "data_dictionary", "source_files", "validation_checks",
)))
CORE_KEY = ("channel_id", "report_scope", "snapshot_class", "period_kind", "reporting_start", "reporting_end",
            "canonical_content_format", "filters_json", "grain", "activity_date", "video_id", "dimension_json", "metric")
WIDE_KEY = tuple(c for c in CORE_KEY if c not in {"grain", "dimension_json", "metric"})
RETENTION_KEY = ("channel_id", "video_id", "report_id", "report_scope", "period", "reporting_start", "reporting_end",
                 "member_name", "segment_dimension", "segment_value", "video_position_percent", "metric")


def _json(raw, name):
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise StorageError("Invalid YouTube JSON: " + name) from exc


def _member_name(name):
    name = _safe_name(name)
    if any(":" in p or p.endswith((".", " ")) or any(ord(c) < 32 for c in p) for p in name.split("/")):
        raise StorageError("Unsafe YouTube package path.")
    return name


def _zip_assets(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            assets, seen = {}, set()
            for entry in archive.infolist():
                # ZipInfo normalizes host separators and truncates NULs in
                # filename; validate the original archive spelling first.
                original_name = entry.orig_filename
                name = _member_name(original_name.rstrip("/") if entry.is_dir() else original_name)
                if name.casefold() in seen:
                    raise StorageError("Duplicate YouTube ZIP member: " + name)
                seen.add(name.casefold())
                if stat.S_ISLNK(entry.external_attr >> 16):
                    raise StorageError("YouTube ZIP must not contain symbolic links.")
                if entry.flag_bits & 1:
                    raise StorageError("Encrypted YouTube ZIP members are unsupported.")
                if not entry.is_dir():
                    assets[name] = archive.read(entry)
            return assets
    except (zipfile.BadZipFile, RuntimeError, UnicodeError) as exc:
        raise StorageError("Cannot read the YouTube source ZIP.") from exc


def _records(assets, path):
    if path not in assets:
        raise StorageError("Required YouTube package member is missing: " + path)
    header, rows = _csv(assets[path], path)
    return header, rows, [dict(zip(header, row)) for row in rows]


def _key_columns(path):
    if path in DOMAIN_PATHS:
        return CORE_KEY
    if path in {"normalized/channel_daily_wide.csv", "normalized/video_daily_wide_365.csv"}:
        return WIDE_KEY
    if path == "retention/retention_observations.csv":
        return RETENTION_KEY
    if path in {"normalized/video_inventory.csv", "normalized/video_song_mapping.csv"}:
        return ("channel_id", "video_id")
    if path == "retention/retention_ui_summary.csv":
        return ("channel_id", "video_id", "report_scope", "period", "reporting_start", "reporting_end", "selected_segment", "collection_method")
    return None


def _row_keys(path, header, rows):
    """Observation keys include identity and every source scope dimension.

    Evidence/dictionary rows instead use exact row content and a duplicate
    occurrence ordinal. Row numbering is never a domain observation key.
    """
    columns = _key_columns(path)
    if columns and not set(columns) <= set(header):
        raise StorageError("Missing stable-key columns: " + path)
    indexes = [header.index(c) for c in columns] if columns else list(range(len(header)))
    occurrences, result = Counter(), []
    for row in rows:
        values = [row[i] for i in indexes]
        signature = json.dumps([path, values], ensure_ascii=False, separators=(",", ":"))
        if columns and occurrences[signature]:
            raise StorageError("Duplicate canonical YouTube key: " + path)
        occurrences[signature] += 1
        if not columns:
            signature += ":" + str(occurrences[signature])
        result.append(_sha(signature.encode("utf-8")))
    return result


def _require(condition, message):
    if not condition:
        raise StorageError("YouTube validation failed: " + message)


def _value(value, status, path):
    unavailable = {"unavailable", "suppressed", "not_applicable", "not_yet_collected", "missing"}
    if status in unavailable:
        _require(value == "", "unavailable values must remain blank in " + path)
        return
    _require(status in {"observed", "reported", "zero"}, "unknown value status in " + path)
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise StorageError("YouTube numeric value is invalid in " + path) from exc
    _require(number.is_finite(), "nonfinite numeric value in " + path)
    _require((number == 0) == (status == "zero"), "explicit zero/status mismatch in " + path)


def _validate(assets):
    """Verify source bytes and acceptance invariants before publishing anything."""
    manifest = _json(assets.get("package_manifest.json", b""), "package_manifest.json")
    _require(manifest.get("channel_id") == CHANNEL_ID and manifest.get("retrieval_date") == "2026-10-23", "package identity/date")
    entries = manifest.get("files", [])
    _require(isinstance(entries, list) and entries, "empty package manifest")
    indexed = {}
    for entry in entries:
        path = _member_name(entry["path"])
        _require(path not in indexed, "duplicate manifest member")
        _require(path in assets, "manifest member missing: " + path)
        raw = assets[path]
        _require(len(raw) == entry["bytes"] and _sha(raw) == entry["sha256"], "package hash: " + path)
        indexed[path] = entry
    _require(set(indexed) == set(assets) - {"package_manifest.json"}, "manifest must cover every other ZIP member")
    _require(PARSED_PATHS <= set(assets), "required canonical/dictionary tables missing")
    parsed = {p: _records(assets, p) for p in sorted(PARSED_PATHS)}
    for path, (header, rows, _) in parsed.items():
        _row_keys(path, header, rows)
    reports = _json(assets["report_manifest.json"], "report_manifest.json")
    retention_manifest = _json(assets["retention/retention_manifest.json"], "retention/retention_manifest.json")
    channel = reports.get("channel", {})
    _require(channel.get("channel_id") == CHANNEL_ID and channel.get("report_scope") == "channel_owned"
             and channel.get("source_timezone") == "America/Los_Angeles", "channel identity/scope/timezone")
    native_count, member_count = 0, 0
    for prefix, report_list in (("", reports["reports"]), ("retention/", retention_manifest["reports"])):
        ids = [r["report_id"] for r in report_list]
        _require(len(ids) == len(set(ids)), "duplicate report ID")
        for report in report_list:
            path = _member_name(report["original_path"])
            _require(path in assets and _sha(assets[path]) == report["sha256"], "native export hash: " + path)
            if "byte_count" in report:
                _require(len(assets[path]) == report["byte_count"], "native export byte count")
            native = _zip_assets(assets[path])
            for member, raw in native.items():
                extracted = prefix + "extracted/" + report["report_id"] + "/" + member
                _require(assets.get(extracted) == raw, "native extracted member mismatch: " + extracted)
                member_count += 1
            native_count += 1
    for path, source_path in (("normalized/source_files.csv", "source_path"), ("retention/retention_source_files.csv", "source_file")):
        for row in parsed[path][2]:
            _require(row[source_path] in assets and _sha(assets[row[source_path]]) == row["sha256"], "source member hash")
    inventory = parsed["normalized/video_inventory.csv"][2]
    video_ids = {r["video_id"] for r in inventory}
    _require(len(inventory) == len(video_ids) == 27, "expected 27 unique video IDs")
    _require(Counter(r["content_format"] for r in inventory) == {"videos": 19, "shorts": 8}, "expected 19 videos and 8 Shorts")
    formats = {r["video_id"]: r["content_format"] for r in inventory}
    for path, (_, _, rows) in parsed.items():
        for row in rows:
            if "channel_id" in row:
                _require(row["channel_id"] == CHANNEL_ID, "unexpected channel ID in " + path)
            if "source_timezone" in row:
                _require(row["source_timezone"] == "America/Los_Angeles", "reporting timezone in " + path)
            if row.get("video_id"):
                _require(row["video_id"] in video_ids, "unknown video ID in " + path)
                if "content_format" in row:
                    _require(row["content_format"] == formats[row["video_id"]], "video format mismatch")
            if "value_status" in row and "value" in row:
                _value(row["value"], row["value_status"], path)
            if row.get("source_file"):
                _require(row["source_file"] in assets, "missing source reference in " + path)
            for name in ("reporting_start", "reporting_end", "activity_date"):
                if row.get(name):
                    try:
                        _require(date.fromisoformat(row[name]).isoformat() == row[name], "calendar date format")
                    except ValueError as exc:
                        raise StorageError("Invalid YouTube calendar date") from exc
            if row.get("activity_date"):
                _require(row["reporting_start"] <= row["activity_date"] <= row["reporting_end"], "date outside reporting bounds")
    dictionary = {r["metric"]: r for r in parsed["normalized/metric_dictionary.csv"][2]}
    core_statuses = Counter()
    for path in DOMAIN_PATHS:
        for row in parsed[path][2]:
            _require(row["report_scope"] == "channel_owned", "core scope")
            _require(row["grain"] == Path(path).stem, "canonical grain")
            metric = dictionary.get(row["metric"])
            _require(metric is not None and row["unit"] == metric["unit"] and row["aggregation"] == metric["aggregation"], "metric unit/additivity")
            core_statuses[row["value_status"]] += 1
    wide = parsed["normalized/video_daily_wide_365.csv"][2]
    annual_dates = {(date(2025, 10, 22) + timedelta(days=n)).isoformat() for n in range(365)}
    _require(len(wide) == 9855 and {(r["video_id"], r["activity_date"]) for r in wide} == {(v, d) for v in video_ids for d in annual_dates}, "9,855 unique annual video-days")
    annual_long = {tuple(r[c] for c in WIDE_KEY) + (r["metric"],): r for r in parsed["normalized/video_daily.csv"][2]}
    for row in wide:
        _require(row["period_kind"] == "annual_current" and row["reporting_start"] == "2025-10-22"
                 and row["reporting_end"] == "2026-10-21", "annual video reporting period")
        for metric in ("views", "engaged_views"):
            _value(row[metric], row[metric + "_status"], "annual video wide")
            original = annual_long.get(tuple(row[c] for c in WIDE_KEY) + (metric,))
            _require(original is not None and original["value"] == row[metric] and original["value_status"] == row[metric + "_status"]
                     and original["report_id"] == row[metric + "_source_report_id"], "wide/long video metric disagreement")
    for row in parsed["normalized/channel_daily_wide.csv"][2]:
        for metric in dictionary:
            if metric in row:
                _value(row[metric], row[metric + "_status"], "channel daily wide")
    curves = parsed["retention/retention_observations.csv"][2]
    bins = defaultdict(list)
    for row in curves:
        _require(row["report_scope"] == "channel_owned_selected_video", "retention selected-video scope")
        position = Decimal(row["video_position_percent"])
        _require(position.is_finite() and 0 <= position < 100, "elapsed-video position must be 0-99, without endpoint 100")
        if row["member_name"] == "All.csv" and row["metric"] == "absolute_audience_retention":
            bins[row["video_id"]].append(position)
    _require(set(bins) == video_ids and all(sorted(v) == list(range(100)) for v in bins.values()), "2,700 main retention points, 100 per video")
    manual = parsed["retention/retention_ui_summary.csv"][2]
    _require(len(manual) == 27 and {r["video_id"] for r in manual} == video_ids
             and all("manual" in r["collection_method"].lower() for r in manual), "separate manual UI summaries")
    _require(all(not r["spotify_recording_id"] for r in parsed["normalized/video_song_mapping.csv"][2]), "Spotify recording IDs must remain unresolved")
    summary = _json(assets["validation_summary.json"], "validation_summary.json")
    _require(all(len(parsed[f"normalized/{grain}.csv"][1]) == count for grain, count in summary["rows_by_grain"].items()), "canonical source summary row counts")
    _require(sum(len(parsed[p][1]) for p in DOMAIN_PATHS) == summary["canonical_metric_observations"], "canonical observation count")
    retention_summary = _json(assets["retention/retention_summary.json"], "retention/retention_summary.json")
    _require(len(curves) == retention_summary["normalized_metric_observations"] and retention_summary["validation_failures"] == 0, "retention source validation")
    _require(native_count == 67 and member_count == 348, "67 native ZIPs and 348 exact source members")
    status_counts = dict(Counter(r["value_status"] for r in curves))
    _require(status_counts == retention_summary["numeric_value_status_counts"], "retention value status counts")
    return parsed, {"package_manifest_hashes_verified": len(entries), "native_zip_hashes_verified": native_count,
                    "native_members_verified": member_count, "video_count": 27, "regular_video_count": 19, "shorts_count": 8,
                    "annual_video_days": len(wide), "main_retention_points": 2700, "retention_observations": len(curves),
                    "core_value_status_counts": dict(core_statuses), "retention_value_status_counts": status_counts}, reports


class YouTubeRepository(AnalysisRepository):
    """Read-only source-compatible tables plus stable observation provenance."""

    def __init__(self, dbpath):
        super().__init__(dbpath)
        if self._metadata.get("collection_key") != COLLECTION_KEY or self._metadata.get("platform") != "youtube":
            raise StorageError("This is not the supported YouTube collection database.")

    def table(self, path, *, raw=False):
        frame = super().table(path, raw=raw)
        frame.attrs.update(collection_key=COLLECTION_KEY, source_timezone="America/Los_Angeles", baseline_status="newly_retrieved_historical_data")
        return frame

    def row_keys(self, path):
        frame = self.table(path, raw=True)
        expected = _row_keys(path, list(frame.columns), frame.values.tolist())
        with self._connection() as db:
            stored = [r[0] for r in db.execute("SELECT row_key FROM youtube_row_keys WHERE asset_path=? ORDER BY csv_record", (path,))]
        if expected != stored:
            raise StorageError("Persisted YouTube stable keys differ from source rows.")
        return stored

    def row_provenance(self, path):
        result = super().row_provenance(path)
        result.insert(0, "collection_key", COLLECTION_KEY)
        result.insert(1, "stable_row_key", self.row_keys(path))
        return result


def _no_links(path, root):
    path = Path(path)
    _require(path.resolve().is_relative_to(root), "registered path outside data directory")
    for component in (path, *path.parents):
        if component.is_symlink() or (hasattr(component, "is_junction") and component.is_junction()):
            raise StorageError("YouTube storage paths must not contain links or junctions.")
        if component == root:
            break
    return path


def youtube_registration_records(registry):
    if not isinstance(registry, dict) or registry.get("schema_version") != 1 or not isinstance(registry.get("collections"), list):
        raise StorageError("Unsupported YouTube collection registry.")
    records = []
    for item in registry["collections"]:
        if not isinstance(item, dict):
            raise StorageError("Unsupported YouTube collection registration.")
        key = item.get("key", "")
        supplement = item.get("collection_kind") == "daily_supplement"
        if supplement:
            if (not isinstance(key, str) or not re.fullmatch(r"youtube-daily-\d{8}(?:-[a-z0-9]+)?", key)
                    or item.get("zip_filename") != "supplement.zip"
                    or item.get("parent_collection_key") != COLLECTION_KEY
                    or item.get("parent_zip_sha256") != EXPECTED_SHA256):
                raise StorageError("Unsupported YouTube daily supplement registration.")
        elif (key != COLLECTION_KEY or item.get("collection_kind") not in (None, "collection")
                or item.get("zip_filename", ZIP_FILENAME) != ZIP_FILENAME):
            raise StorageError("Unsupported YouTube collection registration.")
        result = dict(item)
        for field in ("database", "evidence_root"):
            result[field] = _safe_name(item.get(field))
        expected = f"collections/{key}"
        if result["evidence_root"] != expected or result["database"] != expected + "/youtube.sqlite3":
            raise StorageError("YouTube registration must use its dedicated collection directory.")
        records.append(result)
    if len({r["key"] for r in records}) != len(records):
        raise StorageError("Duplicate YouTube collection registrations.")
    return records


def _read_registry(root):
    path = _no_links(root / REGISTRY_FILENAME, root)
    if not path.exists():
        return {"schema_version": 1, "collections": []}
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StorageError("Cannot read the YouTube collection registry.") from exc
    youtube_registration_records(registry)
    return registry


def list_registered_youtube(data_dir):
    root = Path(data_dir).expanduser().resolve()
    records = youtube_registration_records(_read_registry(root))
    for item in records:
        for relative in (item["database"], item["evidence_root"] + "/" + item.get("zip_filename", ZIP_FILENAME)):
            if not _no_links(root / relative, root).is_file():
                raise StorageError("Registered YouTube collection file is missing: " + relative)
    return records


def load_registered_youtube(data_dir, key=None):
    root = Path(data_dir).expanduser().resolve()
    records = list_registered_youtube(root)
    item = next((r for r in records if key is None or r["key"] == key), None)
    if item is None:
        if key is not None:
            raise StorageError("No registered YouTube collection named " + str(key))
        return None
    if item.get("collection_kind") == "daily_supplement":
        from stats_app.youtube_daily_supplement import DailySupplementRepository
        repo = DailySupplementRepository(root / item["database"])
    else:
        repo = YouTubeRepository(root / item["database"])
    if (repo.metadata["zip_sha256"] != item.get("zip_sha256")
            or repo.metadata["collection_key"] != item["key"]):
        raise StorageError("YouTube registry/package identity mismatch.")
    repo.evidence_root = root / item["evidence_root"]
    repo.registered_label = item.get("label") or repo.metadata["label"]
    repo.registered_key = item["key"]
    return repo


def _write_db(path, zip_raw, assets, parsed, metadata):
    with path.open("xb"):
        pass
    db = sqlite3.connect(path)
    try:
        db.executescript("""
            CREATE TABLE metadata(key TEXT PRIMARY KEY,json TEXT NOT NULL);
            CREATE TABLE original_zip(id INTEGER PRIMARY KEY,filename TEXT,sha256 TEXT,source_url TEXT,contents BLOB);
            CREATE TABLE assets(path TEXT PRIMARY KEY,sha256 TEXT NOT NULL,bytes INTEGER,media_type TEXT,
                is_table INTEGER,row_count INTEGER,columns_json TEXT,types_json TEXT,contents BLOB NOT NULL);
            CREATE TABLE analysis_rows(asset_path TEXT NOT NULL REFERENCES assets(path),csv_record INTEGER NOT NULL,
                row_json TEXT NOT NULL,PRIMARY KEY(asset_path,csv_record));
            CREATE TABLE youtube_row_keys(asset_path TEXT NOT NULL,csv_record INTEGER NOT NULL,row_key TEXT NOT NULL UNIQUE,
                PRIMARY KEY(asset_path,csv_record));
        """)
        with db:
            db.execute("INSERT INTO metadata VALUES('package',?)", (json.dumps(metadata, ensure_ascii=False),))
            db.execute("INSERT INTO original_zip VALUES(1,?,?,?,?)", (ZIP_FILENAME, metadata["zip_sha256"], SOURCE_URL, zip_raw))
            for name, raw in sorted(assets.items()):
                header, rows, _ = parsed.get(name, ([], [], []))
                types = {c: _dtype(c, [r[i] for r in rows]) for i, c in enumerate(header)}
                db.execute("INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)", (name, _sha(raw), len(raw), mimetypes.guess_type(name)[0] or "application/octet-stream",
                           int(name in parsed), len(rows), json.dumps(header), json.dumps(types), raw))
                db.executemany("INSERT INTO analysis_rows VALUES(?,?,?)", ((name, i, json.dumps(row, ensure_ascii=False, separators=(",", ":"))) for i, row in enumerate(rows, 2)))
                keys = _row_keys(name, header, rows) if name in parsed else []
                db.executemany("INSERT INTO youtube_row_keys VALUES(?,?,?)", ((name, i, key) for i, key in enumerate(keys, 2)))
            db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        _require(db.execute("PRAGMA quick_check").fetchone()[0] == "ok", "SQLite integrity")
    finally:
        db.close()


@contextmanager
def _import_lock(root):
    lock = _no_links(root / ".youtube_import.lock", root)
    try:
        handle = lock.open("x", encoding="ascii")
    except FileExistsError as exc:
        raise StorageError("Another YouTube import is active; retry after it finishes.") from exc
    try:
        handle.write(str(os.getpid())); handle.close()
        yield
    finally:
        handle.close()
        lock.unlink()


def _atomic_json(path, value):
    descriptor, name = tempfile.mkstemp(prefix=".youtube-registry-", suffix=".json", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2); stream.write("\n")
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def import_youtube_collection(zip_path, data_dir, *, expected_sha256=EXPECTED_SHA256):
    """Copy, verify, and atomically register this collection; replay is read-only.

    The digest override exists for controlled offline fixtures. The CLI always
    uses the user-specified pinned digest and never reinterprets newer packages.
    """
    archive, root = Path(zip_path).expanduser().resolve(), Path(data_dir).expanduser().resolve()
    zip_raw = archive.read_bytes()
    digest = _sha(zip_raw)
    if digest != expected_sha256:
        raise StorageError("YouTube ZIP SHA-256 does not match the expected package.")
    root.mkdir(parents=True, exist_ok=True)
    collection_parent = _no_links(root / "collections", root)
    collection_parent.mkdir(exist_ok=True)
    output = _no_links(collection_parent / COLLECTION_KEY, root)
    with _import_lock(root):
        registry = _read_registry(root)
        records = youtube_registration_records(registry)
        existing = next((r for r in records if r["key"] == COLLECTION_KEY), None)
        if output.exists():
            _require(output.is_dir() and (output / "youtube.sqlite3").is_file(), "conflicting collection directory")
            repo = YouTubeRepository(_no_links(output / "youtube.sqlite3", root))
            preserved_zip = _no_links(output / ZIP_FILENAME, root)
            _require(preserved_zip.is_file() and preserved_zip.read_bytes() == zip_raw and repo.original_zip() == zip_raw, "conflicting retained ZIP")
            metadata = repo.metadata
            _require(metadata["zip_sha256"] == digest, "conflicting existing collection identity")
            database_hash = _sha(repo.db_path.read_bytes())
            if existing:
                _require(existing.get("database_sha256") == database_hash, "registered database hash differs")
            # Check all parsed source rows and keys on an idempotent replay.
            for path in repo.tables:
                repo.row_keys(path)
            report = {**metadata, "database": str(repo.db_path), "idempotent": True, "integrity": "ok"}
        else:
            _require(existing is None, "registered collection directory is missing")
            with tempfile.TemporaryDirectory(prefix=".youtube-stage-", dir=collection_parent) as temporary:
                stage = Path(temporary)
                # The durable copy precedes parsing and integration. Runtime
                # never reads archive from the incoming temporary directory.
                with (stage / ZIP_FILENAME).open("xb") as stream:
                    stream.write(zip_raw); stream.flush(); os.fsync(stream.fileno())
                assets = _zip_assets((stage / ZIP_FILENAME).read_bytes())
                parsed, validation, manifest = _validate(assets)
                periods = sorted({(r["period_kind"], r["reporting_start"], r["reporting_end"], r["snapshot_class"]) for r in manifest["reports"]})
                metadata = {"schema_version": SCHEMA_VERSION, "collection_key": COLLECTION_KEY, "platform": "youtube", "label": LABEL,
                            "zip_filename": ZIP_FILENAME, "zip_sha256": digest, "source_url": SOURCE_URL,
                            "package_sha256": _sha(json.dumps([(p, _sha(raw)) for p, raw in sorted(assets.items())], separators=(",", ":")).encode()),
                            "loaded_at": datetime.now(timezone.utc).isoformat(), "retrieval_date": "2026-10-23",
                            "baseline_status": "newly_retrieved_historical_data", "baseline_note": "Historical windows newly retrieved October 23; existing Spotify baseline metadata is unchanged.",
                            **manifest["channel"], "reporting_periods": [dict(zip(("period_kind", "reporting_start", "reporting_end", "snapshot_class"), p)) for p in periods],
                            "files": len(assets), "parsed_tables": len(parsed), "parsed_records": sum(len(v[1]) for v in parsed.values()),
                            "all_package_files_match_zip": True, "validation": validation,
                            "table_rows": {p: len(v[1]) for p, v in parsed.items()}, "report_status_counts": dict(Counter(r["status"] for r in manifest["reports"]))}
                _write_db(stage / "youtube.sqlite3", zip_raw, assets, parsed, metadata)
                repo = YouTubeRepository(stage / "youtube.sqlite3")
                _require(repo.original_zip() == zip_raw, "persisted original ZIP")
                for path in repo.tables:
                    repo.row_keys(path)
                report = {**metadata, "database": str(output / "youtube.sqlite3"), "idempotent": False, "integrity": "ok"}
                (stage / "youtube_collection_import.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                stage.rename(output)
            database_hash = _sha((output / "youtube.sqlite3").read_bytes())
        record = {"key": COLLECTION_KEY, "database": f"collections/{COLLECTION_KEY}/youtube.sqlite3",
                  "evidence_root": f"collections/{COLLECTION_KEY}", "label": LABEL,
                  "zip_sha256": digest, "database_sha256": database_hash}
        if existing:
            _require(existing == record, "existing registration metadata conflicts")
        else:
            registry["collections"].append(record)
            _atomic_json(root / REGISTRY_FILENAME, registry)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip-path", required=True, type=Path)
    parser.add_argument("--data-dir", type=Path, help="Defaults to configured STATS_DATA_DIR")
    args = parser.parse_args()
    data_dir = (args.data_dir or load_settings().data_dir).expanduser().resolve()
    if any(part.casefold().startswith("onedrive") for part in data_dir.parts):
        parser.error("Keep the active SQLite collection outside OneDrive; choose local STATS_DATA_DIR.")
    result = import_youtube_collection(args.zip_path, data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
