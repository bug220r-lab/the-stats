"""Synthetic source fixtures exercise supplement staging, never live imports."""
from datetime import date, timedelta
import csv
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from stats_app.storage import SQLiteRepository, StorageError
from stats_app.youtube_daily_supplement import (
    CHANNEL_ID, COLLECTION_KEY, DAILY_PATH, EXPECTED_SHA256, METRICS,
    DailySupplementRepository, build_daily_supplement, import_daily_supplement, normalize_daily_export,
)


def _csv_bytes(header, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n"); writer.writerow(header); writer.writerows(rows)
    return stream.getvalue().encode()


def _zip_bytes(metric, rows=None, header=None):
    if rows is None:
        value = "0:01:32" if metric == "average_view_duration_seconds" else "0.1234" if metric == "watch_time_hours" else "2"
        rows = [[(date(2025, 10, 22) + timedelta(days=i)).isoformat(), value] for i in range(365)]
        # Native availability, explicit zero and raw whitespace are distinct.
        rows[0][1] = "0:00:00" if metric == "average_view_duration_seconds" else "0"
        rows[1][1] = ""
        rows[2][1] = "—"
        rows[3][1] = "suppressed"
        rows[4][1] = "not applicable"
        rows[5][1] = " 0:01:32 " if metric == "average_view_duration_seconds" else " 0.1234 " if metric == "watch_time_hours" else " 2 "
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("Totals.csv", _csv_bytes(header or ["Date", METRICS[metric][0]], rows))
        archive.writestr("Table data.csv", b"Date,Views\nTotal,7\n2026-10-21,7\n")
    return stream.getvalue()


@pytest.fixture
def sources(tmp_path):
    root = tmp_path / "synthetic-source"
    (root / "originals").mkdir(parents=True)
    (root / "evidence").mkdir()
    (root / "evidence/ui.txt").write_bytes(b"Synthetic test fixture; not actual collected evidence.\n")
    channel = {"channel_id": CHANNEL_ID, "channel_name": "[REDACTED] TV", "channel_handle": "@redactedbandoh",
               "channel_type": "standard_channel", "report_scope": "channel_owned", "source_timezone": "America/Los_Angeles"}
    manifest = {"schema_version": 1, "collection_key": "youtube-daily-20261023", "label": "Synthetic test supplement",
                "parent_collection_key": COLLECTION_KEY, "parent_zip_sha256": EXPECTED_SHA256,
                "retrieval_date": "2026-10-23", "channel": channel, "reports": []}
    for metric in METRICS:
        raw = _zip_bytes(metric); original = f"originals/{metric}.zip"
        (root / original).write_bytes(raw)
        manifest["reports"].append({"report_id": "supplement_" + metric, "metric": metric, "original_path": original,
                                    "sha256": hashlib.sha256(raw).hexdigest(), "reporting_start": "2025-10-22", "reporting_end": "2026-10-21",
                                    "source_timezone": "America/Los_Angeles", "report_scope": "channel_owned", "report_content_format": "all", "filters_json": "{}",
                                    "retrieved_at_utc": "2026-10-23T12:30:00+00:00", "retrieved_at_basis": "synthetic_test_timestamp",
                                    "source_url": f"https://studio.youtube.com/channel/{CHANNEL_ID}/analytics",
                                    "evidence_paths": ["evidence/ui.txt"]})
    (root / "collection_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root, manifest


def test_stage_preserves_every_source_and_missing_value_status(sources, tmp_path):
    root, manifest = sources
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    report = build_daily_supplement(root, tmp_path / "staged")
    repo = DailySupplementRepository(report["database"])
    assert report["validation"]["native_daily_rows"] == 1460
    assert report["validation"]["native_exports"] == 4
    assert report["parent_collection_key"] == COLLECTION_KEY
    assert report["parent_zip_sha256"] == EXPECTED_SHA256
    assert not (tmp_path / "youtube_collections.json").exists()
    for name, raw in before.items():
        assert (root / name).read_bytes() == raw
        assert repo.original_bytes(name) == raw
    values = repo.table(DAILY_PATH)
    raw_values = repo.table(DAILY_PATH, raw=True)
    assert len(values) == len(values.drop_duplicates(["collection_key", "report_id", "activity_date", "metric"])) == 1460
    assert values.groupby("metric").size().eq(365).all()
    assert set(values.source_timezone) == {"America/Los_Angeles"}
    assert values.activity_date.min() == "2025-10-22" and values.activity_date.max() == "2026-10-21"
    assert set(values.snapshot_class) == {"newly_retrieved_supplement"}
    for status in ("unavailable", "suppressed", "not_applicable"):
        assert values.loc[values.value_status == status, "value"].isna().all()
    assert (values.loc[values.value_status == "zero", "value"] == 0).all()
    duration = values[(values.metric == "average_view_duration_seconds") & (values.activity_date == "2025-10-27")].iloc[0]
    assert duration.value == 92 and duration.source_value_raw == " 0:01:32 "
    assert duration.aggregation == "nonadditive" and duration.unit == "seconds"
    watch = raw_values[(raw_values.metric == "watch_time_hours") & (raw_values.activity_date == "2025-10-27")].iloc[0]
    assert watch.value == "0.1234" and watch.source_value_raw == " 0.1234 " and watch.unit == "hours"
    coverage = repo.table("normalized/daily_coverage.csv", raw=True)
    assert set(coverage.observed_dates) == {"365"} and set(coverage.missing_dates_count) == {"0"}
    assert set(coverage.numeric_coverage_status) == {"partial"}
    index = repo.table("normalized/collection_index.csv", raw=True)
    assert set(index.status) == {"complete"} and set(index.numeric_coverage_status) == {"partial"}
    assert len(set(repo.row_keys(DAILY_PATH))) == 1460
    provenance = repo.row_provenance(DAILY_PATH)
    assert {"stable_row_key", "source_zip_sha256", "source_sha256", "source_value_raw", "source_row_number"} <= set(provenance)
    with repo._connection() as db, pytest.raises(sqlite3.OperationalError, match="readonly"):
        db.execute("DELETE FROM metadata")


def test_replay_is_exact_and_conflicting_sources_rejected(sources, tmp_path):
    root, _ = sources
    output = tmp_path / "staged"
    first = build_daily_supplement(root, output)
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    replay = build_daily_supplement(root, output)
    assert replay["idempotent"] and replay["zip_sha256"] == first["zip_sha256"]
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}
    (root / "evidence/ui.txt").write_bytes(b"changed evidence")
    with pytest.raises(StorageError, match="conflicting supplement"):
        build_daily_supplement(root, output)
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}


@pytest.mark.parametrize("change", ["date", "duplicate_date", "wrong_metric", "table_only"])
def test_parser_rejects_non_daily_or_incomplete_exports(sources, change):
    root, manifest = sources
    report = manifest["reports"][0]
    if change == "table_only":
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("Table data.csv", b"Date,Watch time (hours)\nTotal,1\n")
        raw = stream.getvalue()
    else:
        dates = [(date(2025, 10, 22) + timedelta(days=i)).isoformat() for i in range(365)]
        if change == "date": dates[-1] = "2026-10-22"
        if change == "duplicate_date": dates[-1] = dates[0]
        raw = _zip_bytes("watch_time_hours", rows=[[day, "1.0001"] for day in dates], header=["Date", "Views"] if change == "wrong_metric" else None)
    report = {**report, "sha256": hashlib.sha256(raw).hexdigest()}
    with pytest.raises(StorageError):
        normalize_daily_export(raw, report, manifest)


@pytest.mark.parametrize("field,value", [("report_scope", "artist_wide"), ("source_timezone", "UTC"), ("reporting_end", "2026-10-22"), ("filters_json", '{"format":"shorts"}'), ("retrieved_at_utc", "2026-10-23T12:00:00"), ("evidence_paths", [])])
def test_manifest_rejects_wrong_scope_period_or_missing_provenance(sources, tmp_path, field, value):
    root, manifest = sources
    manifest["reports"][0][field] = value
    (root / "collection_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "staged"
    with pytest.raises(StorageError):
        build_daily_supplement(root, output)
    assert not output.exists()


def test_hash_change_and_row_tampering_fail_closed(sources, tmp_path):
    root, manifest = sources
    report = build_daily_supplement(root, tmp_path / "staged")
    with sqlite3.connect(report["database"]) as db:
        db.execute("UPDATE analysis_rows SET row_json='[]' WHERE asset_path=? AND csv_record=2", (DAILY_PATH,))
    with pytest.raises(StorageError, match="differ from"):
        DailySupplementRepository(report["database"]).table(DAILY_PATH)
    (root / manifest["reports"][0]["original_path"]).write_bytes(b"mutated original")
    with pytest.raises(StorageError, match="ZIP hash mismatch"):
        build_daily_supplement(root, tmp_path / "new-stage")


def test_import_requires_the_existing_pinned_parent(sources, tmp_path):
    source, _ = sources
    target = tmp_path / "no-parent"
    with pytest.raises(StorageError, match="base YouTube collection must already be registered"):
        import_daily_supplement(source, target)
    assert not (target / "youtube_collections.json").exists()
    assert not (target / "collections").exists()


@pytest.fixture(scope="module")
def registered_parent(tmp_path_factory):
    from stats_app.youtube_repository import import_youtube_collection
    source_zip = Path.home() / "AppData/Local/Temp/youtube_collection_2026-10-23/The_Stats_YouTube_Collection_2026-10-23.zip"
    if not source_zip.is_file():
        pytest.skip("Private base collection is not distributed with the repository")
    root = tmp_path_factory.mktemp("daily-supplement-parent")
    import_youtube_collection(source_zip, root)
    (root / "archive_registry.json").write_bytes(b'{"archives":[],"unchanged_baseline":"unverified"}')
    SQLiteRepository(root / "stats.sqlite3")
    return root


def test_import_replay_conflict_and_backup_preserve_parent_and_analysis(sources, registered_parent, tmp_path):
    from stats_app.backup import backup_library, verify_bundle
    from stats_app.youtube_repository import load_registered_youtube
    source, _ = sources
    root = registered_parent
    before = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    old_registry = json.loads((root / "youtube_collections.json").read_text())
    report = import_daily_supplement(source, root)
    assert not report["idempotent"]
    for relative, digest in before.items():
        if relative != "youtube_collections.json":
            assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest
    registry = json.loads((root / "youtube_collections.json").read_text())
    assert registry["collections"][:1] == old_registry["collections"]
    assert len(registry["collections"]) == 2
    assert registry["collections"][1]["collection_kind"] == "daily_supplement"
    repo = load_registered_youtube(root, report["collection_key"])
    assert isinstance(repo, DailySupplementRepository)
    assert len(repo.table(DAILY_PATH)) == 1460
    after = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    replay = import_daily_supplement(source, root)
    assert replay["idempotent"]
    assert after == {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    (source / "evidence/ui.txt").write_bytes(b"changed source evidence")
    with pytest.raises(StorageError, match="conflicting supplement"):
        import_daily_supplement(source, root)
    assert after == {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    bundle = backup_library(root, tmp_path / "bundle")
    assert verify_bundle(bundle)["youtube_collections_included"] == 2
    relocated = tmp_path / "relocated-bundle"
    bundle.rename(relocated)
    restored = load_registered_youtube(relocated, report["collection_key"])
    assert restored.original_zip() == repo.original_zip()
    assert restored.table(DAILY_PATH, raw=True).equals(repo.table(DAILY_PATH, raw=True))
    assert restored.row_keys(DAILY_PATH) == repo.row_keys(DAILY_PATH)
    assert load_registered_youtube(relocated, COLLECTION_KEY).metadata["zip_sha256"] == EXPECTED_SHA256
