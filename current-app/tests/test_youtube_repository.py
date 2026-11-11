"""YouTube import preserves source grains, statuses, bytes and older stores."""
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import stat
import zipfile

import pandas as pd
import pytest

from stats_app.storage import StorageError
from stats_app.youtube_repository import (
    COLLECTION_KEY, CORE_KEY, EXPECTED_SHA256, PARSED_PATHS, REGISTRY_FILENAME,
    _row_keys, _value, _zip_assets,
    import_youtube_collection, list_registered_youtube, load_registered_youtube,
)

PRIVATE_ZIP = Path.home() / "AppData/Local/Temp/youtube_collection_2026-10-23/The_Stats_YouTube_Collection_2026-10-23.zip"


@pytest.fixture(scope="module")
def actual_collection(tmp_path_factory):
    if not PRIVATE_ZIP.is_file():
        pytest.skip("Private YouTube collection is not distributed with the repository")
    root = tmp_path_factory.mktemp("youtube-collection")
    # The importer must never edit the archive registry or existing database.
    old_registry = b'{"archives":[],"analysis_package":{"unchanged":"baseline remains unverified"}}'
    (root / "archive_registry.json").write_bytes(old_registry)
    (root / "stats.sqlite3").write_bytes(b"existing upload store sentinel")
    report = import_youtube_collection(PRIVATE_ZIP, root)
    return root, report, load_registered_youtube(root), old_registry


def test_exact_source_bytes_and_separate_collection(actual_collection):
    root, report, repo, old_registry = actual_collection
    assert not report["idempotent"] and report["integrity"] == "ok"
    assert repo.metadata["zip_sha256"] == EXPECTED_SHA256
    assert repo.metadata["validation"]["package_manifest_hashes_verified"] == 470
    assert repo.metadata["validation"]["native_members_verified"] == 348
    assert repo.original_zip() == PRIVATE_ZIP.read_bytes()
    with zipfile.ZipFile(PRIVATE_ZIP) as archive:
        assert len(repo.file_catalog()) == len(archive.namelist()) == 471
        for name in archive.namelist():
            assert repo.original_bytes(name) == archive.read(name)
    assert (root / "archive_registry.json").read_bytes() == old_registry
    assert (root / "stats.sqlite3").read_bytes() == b"existing upload store sentinel"
    assert set(repo.tables) == PARSED_PATHS
    assert "normalized/observations.csv" not in repo.tables
    assert "normalized/canonical_observations.csv" not in repo.tables
    assert list_registered_youtube(root)[0]["key"] == COLLECTION_KEY
    with repo._connection() as db, pytest.raises(sqlite3.OperationalError, match="readonly"):
        db.execute("DELETE FROM metadata")


def test_canonical_keys_views_and_calendar_dates(actual_collection):
    _, _, repo, _ = actual_collection
    inventory = repo.table("normalized/video_inventory.csv")
    assert len(inventory) == inventory.video_id.nunique() == 27
    assert inventory.content_format.value_counts().to_dict() == {"videos": 19, "shorts": 8}
    daily = repo.table("normalized/video_daily_wide_365.csv")
    assert len(daily) == len(daily.drop_duplicates(["video_id", "activity_date"])) == 9855
    assert daily.activity_date.min() == "2025-10-22" and daily.activity_date.max() == "2026-10-21"
    assert set(daily.source_timezone) == {"America/Los_Angeles"}
    assert daily.groupby("video_id").size().eq(365).all()
    assert str(daily.views.dtype) == str(daily.engaged_views.dtype) == "Int64"
    assert daily.views.ne(daily.engaged_views).any()
    provenance = repo.row_provenance("normalized/video_daily.csv")
    assert provenance.stable_row_key.nunique() == len(provenance) == 22125
    assert provenance.package_csv_record.tolist() == list(range(2, 22127))
    assert "source_file" in provenance and "retrieved_at_basis" in provenance
    historical = repo.table("normalized/channel_daily.csv")
    historical = historical[historical.period_kind == "baseline365_historical"]
    assert set(historical.snapshot_class) == {"newly_retrieved_historical"}
    assert historical.attrs["baseline_status"] == "newly_retrieved_historical_data"


def test_missing_statuses_signed_retention_and_manual_values(actual_collection):
    _, _, repo, _ = actual_collection
    core = pd.concat([repo.table(f"normalized/{p}.csv") for p in ("channel_daily", "channel_period", "dimension_daily", "dimension_period", "video_daily", "video_period")])
    assert core.value_status.value_counts().to_dict() == {"zero": 36945, "observed": 6833, "unavailable": 1699}
    unavailable = core[core.value_status == "unavailable"]
    assert unavailable.value.isna().all()
    contradicted = unavailable[(unavailable.metric == "new_viewers") & (unavailable.source_value_raw == "0")]
    assert len(contradicted) > 0 and contradicted.value.isna().all()
    assert (core.loc[core.value_status == "zero", "value"] == 0).all()
    curves = repo.table("retention/retention_observations.csv")
    assert curves.value_status.value_counts().to_dict() == {"reported": 20110, "unavailable": 139}
    assert curves.loc[curves.value_status == "unavailable", "value"].isna().all()
    main = curves[(curves.member_name == "All.csv") & (curves.metric == "absolute_audience_retention")]
    assert len(main) == 2700
    assert all(sorted(group.video_position_percent) == list(range(100)) for _, group in main.groupby("video_id"))
    assert curves.loc[curves.metric == "absolute_audience_retention", "value"].gt(100).any()
    assert curves.loc[curves.metric == "compared_to_other_videos", "value"].lt(0).any()
    assert len(set(repo.row_keys("retention/retention_observations.csv"))) == 20249
    assert len(repo.table("retention/retention_ui_summary.csv")) == 27
    source_members = repo.table("retention/retention_source_files.csv")
    assert len(source_members[source_members.native_row_count == 0]) == 100
    assert repo.table("normalized/video_song_mapping.csv").spotify_recording_id.isna().all()


def test_same_package_replay_preserves_all_existing_bytes(actual_collection):
    root, _, repo, _ = actual_collection
    before = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    report = import_youtube_collection(PRIVATE_ZIP, root)
    assert report["idempotent"]
    after = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert len(repo.table("normalized/video_daily_wide_365.csv")) == 9855


def test_partial_daily_metrics_and_blockers_remain_explicit(actual_collection):
    _, _, repo, _ = actual_collection
    coverage = repo.table("normalized/daily_coverage.csv", raw=True)
    annual = coverage[(coverage.period_kind == "annual_current") & (coverage.canonical_content_format == "all")
                      & (coverage.filters_json == "{}") & (coverage.grain == "channel_daily")].set_index("metric")
    for metric in ("watch_time_hours", "average_view_duration_seconds", "subscribers_gained", "subscribers_lost"):
        assert annual.loc[metric, "observed_dates"] == "243"
        assert annual.loc[metric, "missing_dates_count"] == "122"
        assert annual.loc[metric, "date_coverage_status"] == "partial"
    index = repo.table("normalized/collection_index.csv", raw=True)
    assert (index.status == "blocked").sum() == 4
    assert (repo.table("normalized/collection_status.csv", raw=True).status == "blocked").sum() == 2


@pytest.mark.parametrize("name", ["../outside.csv", "/absolute.csv", "C:/absolute.csv", "normal\\outside.csv", "x/../../outside", "bad:file", "trail. "])
def test_unsafe_zip_member_names_rejected(name):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        member = zipfile.ZipInfo("placeholder")
        # ZipInfo's constructor normalizes Windows separators, so retain the
        # deliberately unsafe archive filename after construction.
        member.filename = name
        archive.writestr(member, b"not parsed")
    with pytest.raises(StorageError):
        _zip_assets(target.getvalue())


def test_duplicate_and_symlink_members_rejected():
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("sample.csv", b"a")
        archive.writestr("SAMPLE.csv", b"b")
    with pytest.raises(StorageError, match="Duplicate"):
        _zip_assets(target.getvalue())
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "outside")
    with pytest.raises(StorageError, match="symbolic links"):
        _zip_assets(target.getvalue())


def test_wrong_digest_and_invalid_manifest_publish_nothing(tmp_path):
    incoming = tmp_path / "incoming.zip"
    with zipfile.ZipFile(incoming, "w") as archive:
        archive.writestr("README.txt", b"untrusted fixture")
        archive.writestr("package_manifest.json", json.dumps({"channel_id": "UCkSoRiC9Pz9hEbJOOTYaq_w", "retrieval_date": "2026-10-23", "files": [{"path": "README.txt", "bytes": 17, "sha256": "0" * 64}]}))
    data = tmp_path / "data"
    with pytest.raises(StorageError, match="SHA-256"):
        import_youtube_collection(incoming, data)
    assert not data.exists()
    with pytest.raises(StorageError, match="package hash"):
        import_youtube_collection(incoming, data, expected_sha256=hashlib.sha256(incoming.read_bytes()).hexdigest())
    assert not (data / REGISTRY_FILENAME).exists()
    assert not (data / "collections" / COLLECTION_KEY).exists()
    assert not (data / ".youtube_import.lock").exists()


def test_stable_keys_reject_duplicate_grains_and_keep_scope_distinctions():
    header = list(CORE_KEY)
    original = ["channel", "channel_owned", "current_retrieval", "annual", "2025-10-22", "2026-10-21", "shorts", "{}", "video_daily", "2026-10-20", "video", "", "views"]
    variations = [original]
    for column, value in (("metric", "engaged_views"), ("filters_json", '{"filter":"selected"}'), ("snapshot_class", "historical"), ("report_scope", "another_scope"), ("canonical_content_format", "videos")):
        row = original.copy(); row[header.index(column)] = value; variations.append(row)
    keys = _row_keys("normalized/video_daily.csv", header, variations)
    assert len(keys) == len(set(keys)) == 6
    assert keys == list(reversed(_row_keys("normalized/video_daily.csv", header, list(reversed(variations)))))
    with pytest.raises(StorageError, match="Duplicate canonical"):
        _row_keys("normalized/video_daily.csv", header, [original, original])


def test_status_validation_never_fills_or_clamps():
    _value("", "unavailable", "fixture")
    _value("0", "zero", "fixture")
    _value("134.5", "observed", "fixture")
    _value("-7.2", "reported", "fixture")
    with pytest.raises(StorageError, match="must remain blank"):
        _value("0", "unavailable", "fixture")
    with pytest.raises(StorageError, match="status mismatch"):
        _value("0", "observed", "fixture")


def test_registry_path_escape_rejected_and_empty_state(tmp_path):
    assert load_registered_youtube(tmp_path) is None
    assert list_registered_youtube(tmp_path) == []
    with pytest.raises(StorageError, match="No registered"):
        load_registered_youtube(tmp_path, "unknown")
    (tmp_path / REGISTRY_FILENAME).write_text(json.dumps({"schema_version": 1, "collections": [{"key": COLLECTION_KEY, "database": "../outside.sqlite3", "evidence_root": "collections/" + COLLECTION_KEY}]}))
    with pytest.raises(StorageError, match="Unsafe"):
        list_registered_youtube(tmp_path)
