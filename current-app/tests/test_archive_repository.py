"""Preservation and semantics checks for the read-only handoff integration."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from stats_app.archive_repository import ImportedArchiveRepository
from stats_app.calculations import summarize_metric
from stats_app.library import LibraryRepository
from stats_app.storage import SQLiteRepository, StorageError


@pytest.fixture
def archive(tmp_path):
    db_path = tmp_path / "stats.sqlite3"
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    raw = b"source,date,value\r\noriginal,2026-10-20,7\r\n"
    digest = sha256(raw).hexdigest()
    (source_dir / (digest + ".csv")).write_bytes(raw)
    with sqlite3.connect(db_path) as db:
        db.executescript("""
            CREATE TABLE snapshots(id INTEGER PRIMARY KEY,name TEXT,is_baseline INTEGER,
                locked INTEGER,status TEXT,evidence TEXT,created_at TEXT);
            CREATE TABLE imports(id INTEGER PRIMARY KEY,snapshot_id INTEGER,filename TEXT,
                file_hash TEXT,source_path TEXT,worksheet TEXT,mapping_json TEXT,
                signature TEXT,imported_at TEXT,retired INTEGER,counts_json TEXT);
            CREATE TABLE observations(id INTEGER PRIMARY KEY,snapshot_id INTEGER,import_id INTEGER,
                identity_key TEXT,version INTEGER,active INTEGER,platform TEXT,account_id TEXT,
                account_name TEXT,entity_type TEXT,entity_id TEXT,entity_name TEXT,metric TEXT,
                value REAL,unit TEXT,definition TEXT,dimensions TEXT,period_start TEXT,period_end TEXT,
                time_grain TEXT,captured_at TEXT,source_timezone TEXT,measurement_type TEXT,
                status TEXT,source_row TEXT,evidence_ref TEXT,published_at TEXT,source_url TEXT);
            CREATE TABLE observation_sources(id INTEGER PRIMARY KEY,observation_id INTEGER,
                import_id INTEGER,source_row TEXT,captured_at TEXT,evidence_ref TEXT,
                source_url TEXT,payload_json TEXT);
            CREATE TABLE validation_issues(id INTEGER PRIMARY KEY,import_id INTEGER,severity TEXT,
                code TEXT,message TEXT,source_row TEXT,payload_json TEXT);
            CREATE TABLE collection_queue(id TEXT PRIMARY KEY,source_ref TEXT,captured_at TEXT,
                imported_at TEXT,payload_json TEXT,local_note TEXT);
        """)
        db.execute("INSERT INTO snapshots VALUES(1,?,0,0,'unverified',?,?)", (
            "Archive with an October 20 endpoint", '{"baseline_status":"unverified"}', "2026-10-23T01:00:00Z"))
        db.execute("INSERT INTO snapshots VALUES(2,'Social capture',0,0,'available','{}','2026-10-23T02:00:00Z')")
        for import_id, retired in [(1, 1), (2, 0)]:
            db.execute("INSERT INTO imports VALUES(?,1,?,?,?,?,?,?,?,?,'{\"inserted\":3,\"duplicates\":1}')", (
                import_id, "source.csv", digest, "/obsolete/mac/workspace/data/sources/" + digest + ".csv",
                "CSV", '{"profile":"canonical"}', "signature-" + str(import_id), "2026-10-23T02:00:00Z", retired))
        rows = [
            (1, "spotify", "listeners", 7, "available", "2026-10-19", "2026-10-19", "daily", "distinct_audience_count"),
            (2, "spotify", "listeners", 9, "available", "2026-10-20", "2026-10-20", "daily", "distinct_audience_count"),
            (3, "instagram", "views", 25, "available", None, None, "lifetime", "cumulative_total"),
            (4, "spotify", "listeners", None, "unavailable", "2026-10-18", "2026-10-18", "daily", "distinct_audience_count"),
        ]
        for row_id, platform, metric, value, status, start, end, grain, measurement in rows:
            db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                row_id, 1, 1, "identity-" + str(row_id), 1, 1, platform, "account-1", "Artist",
                "artist", "entity-1", "Name", metric, value, "count", "Do not sum distinct audiences",
                '{"crossposted_scope":"Facebook and Instagram"}', start, end, grain, None,
                "UTC", measurement, status, "2", "original", "2026-07-01T10:30", "https://example.test/source"))
            for import_id in (1, 2):
                db.execute("INSERT INTO observation_sources(observation_id,import_id,source_row,captured_at,evidence_ref,source_url,payload_json) VALUES(?,?,?,?,?,?,?)", (
                    row_id, import_id, str(import_id + 1), "2026-10-22T22:00:00Z" if import_id == 2 else None,
                    "current-evidence" if import_id == 2 else "retired-evidence", "https://example.test/source", '{"original":true}'))
        db.execute("INSERT INTO validation_issues VALUES(1,2,'warning','coverage','Some dates were not collected','2','{}')")
        db.execute("INSERT INTO collection_queue VALUES('q1','https://example.test/report',NULL,'2026-10-23',?, '')", (
            '{"Status":"Pending browser access","Data":"Song stream sources"}',))
    return ImportedArchiveRepository(db_path, source_dir), raw, digest


def test_all_reads_are_byte_preserving_and_connection_is_read_only(archive):
    repo, raw, digest = archive
    before = repo.db_path.read_bytes()
    sources_before = {p.name: p.read_bytes() for p in repo.source_dir.iterdir()}
    assert repo.list_snapshots().is_baseline.eq(0).all()
    assert repo.list_snapshots().iloc[0].status == "unverified"
    data = repo.observations(repo.list_snapshots().iloc[0].label)
    assert len(data) == 4
    assert len(repo.import_history()) == 2
    assert len(repo.observation_provenance(1)) == 2
    assert len(repo.coverage_issues(repo.list_snapshots().iloc[0].label)) == 1
    assert repo.collection_queue().iloc[0]["Status"] == "Pending browser access"
    assert repo.original_source(digest) == raw
    with repo._connection() as db, pytest.raises(sqlite3.OperationalError, match="readonly"):
        db.execute("UPDATE snapshots SET is_baseline=1")
    assert repo.db_path.read_bytes() == before
    assert {p.name: p.read_bytes() for p in repo.source_dir.iterdir()} == sources_before
    assert not Path(str(repo.db_path) + "-wal").exists()


def test_projection_preserves_lifetime_unknowns_missing_values_and_scope(archive):
    repo, _, _ = archive
    data = repo.observations(repo.list_snapshots().iloc[0].label)
    lifetime = data[data.time_grain.eq("lifetime")].iloc[0]
    assert lifetime.period_start == lifetime.period_end == ""
    assert lifetime.published_at == "2026-07-01T10:30"
    assert lifetime.captured_at == "2026-10-22T22:00:00Z"
    assert lifetime.measurement_type == "cumulative_total"
    assert lifetime.status == "observed" and lifetime.source_status == "available"
    assert lifetime.platform == "Instagram" and lifetime.source_platform == "instagram"
    assert lifetime.account == lifetime.account_id == "account-1"
    assert json.loads(lifetime.dimensions_json)["crossposted_scope"] == "Facebook and Instagram"
    missing = data[data.source_status.eq("unavailable")].iloc[0]
    assert pd.isna(missing.value) and missing.status == "unavailable"
    listeners = data[data.metric.eq("listeners")]
    assert summarize_metric(listeners).value is None


def test_last_live_duplicate_supplies_capture_and_retired_provenance_stays(archive):
    repo, _, _ = archive
    row = repo.observations(repo.list_snapshots().iloc[0].label).iloc[0]
    assert row.source_row == "3"
    assert row.evidence_ref == "current-evidence"
    refs = json.loads(row.source_references)
    assert [r["retired"] for r in refs] == [1, 0]
    assert row.source_count == 1
    provenance = repo.observation_provenance(row.observation_id)
    assert provenance.retired.tolist() == [1, 0]
    assert provenance.payload_json.tolist() == ['{"original":true}'] * 2


def test_capture_unknown_is_never_inferred_from_import_time(archive):
    repo, _, _ = archive
    with sqlite3.connect(repo.db_path) as db:
        db.execute("UPDATE observation_sources SET captured_at=NULL")
    assert repo.observations(repo.list_snapshots().iloc[0].label).captured_at.eq("").all()
    assert repo.import_history().captured_at.eq("").all()


def test_original_download_uses_relocated_hash_path_and_verifies_bytes(archive):
    repo, raw, digest = archive
    assert repo.original_source(digest) == raw
    path = repo.source_dir / (digest + ".csv")
    path.write_bytes(b"changed bytes")
    with pytest.raises(StorageError, match="SHA-256"):
        repo.original_source(digest)


def test_missing_source_cannot_be_silently_substituted(archive):
    repo, _, digest = archive
    with sqlite3.connect(repo.db_path) as db:
        db.execute("UPDATE imports SET source_path='/outside/unrelated.csv'")
    with pytest.raises(StorageError, match="identity hash"):
        repo.original_source(digest)
    with pytest.raises(StorageError, match="not found"):
        repo.original_source("0" * 64)


def test_missing_database_does_not_create_directories(tmp_path):
    missing = tmp_path / "missing" / "stats.sqlite3"
    with pytest.raises(StorageError, match="missing"):
        ImportedArchiveRepository(missing, tmp_path / "sources")
    assert not missing.parent.exists()


def test_uncheckpointed_database_is_refused(archive):
    repo, _, _ = archive
    Path(str(repo.db_path) + "-wal").write_bytes(b"uncheckpointed")
    with pytest.raises(StorageError, match="WAL"):
        ImportedArchiveRepository(repo.db_path, repo.source_dir)


def library_fixture(archive):
    recovered, raw, digest = archive
    root = recovered.db_path.parent
    local = SQLiteRepository(root / "local" / "stats.sqlite3")
    row = dict(platform="Spotify", account="account-1", entity_type="artist", entity_id="entity-1",
               entity_name="Artist", metric="streams", value=4, unit="count", period_start="2026-10-20",
               period_end="2026-10-20", time_grain="daily", measurement_type="period_count",
               status="observed", dimensions_json="{}")
    local.import_dataset(b"local original", "local.csv", [row], "Original October 20 baseline",
                         baseline=True, provenance={"baseline_evidence": "Historical designation, now unverified"})
    local.seal_snapshot("Original October 20 baseline")
    registry_path = root / "archive_registry.json"
    registry_path.write_text(json.dumps({"archives": [{"key": "handoff", "database": "stats.sqlite3",
        "source_dir": "sources", "evidence_root": ".", "label": "Recovered handoff"}]}), encoding="utf-8")
    return LibraryRepository(local, registry_path), local, recovered, registry_path


def test_library_namespaces_ids_and_historical_baseline_without_rewriting(archive):
    library, local, recovered, _ = library_fixture(archive)
    local_before = local.observations("Original October 20 baseline")
    recovered_before = recovered.db_path.read_bytes()
    snapshots = library.list_snapshots()
    assert snapshots.backend.tolist() == ["handoff", "handoff", "local"]
    legacy = snapshots[snapshots.backend.eq("local")].iloc[0]
    assert legacy.is_baseline == 0 and legacy.stored_is_baseline == 1
    assert legacy.display_label == "Legacy Windows native archive · baseline unverified"
    assert legacy.stored_label == "Original October 20 baseline"
    assert local.list_snapshots().iloc[0].is_baseline == 1
    archive_rows = library.observations(snapshots.iloc[0].label)
    local_rows = library.observations(legacy.label)
    assert archive_rows.iloc[0].observation_id == "handoff::1"
    assert local_rows.iloc[0].observation_id == "local::1"
    assert library.observation_provenance("handoff::1").backend.eq("handoff").all()
    assert library.observation_provenance("local::1").backend.eq("local").all()
    assert len(library.coverage_issues(snapshots.iloc[0].label)) == 1
    assert library.coverage_issues(legacy.label).empty
    assert library.collection_queue(legacy.label).empty
    assert library.collection_queue(snapshots.iloc[0].label).backend.eq("handoff").all()
    history = library.import_history()
    assert history.import_id.is_unique
    assert library.original_source(sha256(b"local original").hexdigest()) == b"local original"
    assert library.original_source(archive[2]) == archive[1]
    pd.testing.assert_frame_equal(local.observations("Original October 20 baseline"), local_before)
    assert recovered.db_path.read_bytes() == recovered_before


def test_library_writes_only_new_local_snapshot_and_refuses_archive_seal(archive):
    library, local, recovered, _ = library_fixture(archive)
    before = recovered.db_path.read_bytes()
    row = local.observations("Original October 20 baseline").iloc[0].to_dict()
    result = library.import_dataset(b"new local original", "new.csv", [row], "New local capture")
    assert result.imported_rows == 1
    library.seal_snapshot("local::New local capture")
    assert library.observations("local::New local capture").iloc[0].value == 4
    with pytest.raises(StorageError, match="read-only"):
        library.seal_snapshot("handoff::Archive with an October 20 endpoint")
    with pytest.raises(StorageError, match="read-only"):
        library.import_dataset(b"no write", "new.csv", [row], "handoff::Archive with an October 20 endpoint")
    assert recovered.db_path.read_bytes() == before


@pytest.mark.parametrize("entry", [
    {"key": "local", "database": "stats.sqlite3", "source_dir": "sources"},
    {"key": "bad::key", "database": "stats.sqlite3", "source_dir": "sources"},
    {"key": "outside", "database": "../outside.sqlite3", "source_dir": "sources"},
])
def test_library_refuses_ambiguous_or_outside_registry_entries(archive, entry):
    library, local, _, registry = library_fixture(archive)
    registry.write_text(json.dumps({"archives": [entry]}), encoding="utf-8")
    with pytest.raises(StorageError):
        LibraryRepository(local, registry)


def test_missing_registry_keeps_existing_local_application_working(tmp_path):
    local = SQLiteRepository(tmp_path / "local.sqlite3")
    library = LibraryRepository(local)
    assert library.list_snapshots().empty
    assert library.import_history().empty
    assert library.collection_queue().empty


def test_evidence_reports_are_exact_qualified_and_optional(archive):
    library, _, recovered, _ = library_fixture(archive)
    assert library.evidence_reports() == {}
    report = {"coverage": "partial", "missing": ["artist", "dates"]}
    path = recovered.db_path.parent / "spotify_coverage.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    before = path.read_bytes()
    assert library.evidence_reports() == {"handoff::spotify_coverage.json": report}
    assert path.read_bytes() == before


REAL_PACKAGE = Path(__file__).resolve().parents[1] / "data" / "recovery" / "mac_handoff_2026-10-22"
REAL_DB = REAL_PACKAGE / "data" / "stats.sqlite3"


@pytest.mark.skipif(not REAL_DB.exists(), reason="Private handoff package is not included in source control.")
def test_real_recovered_snapshot_counts_lifetime_and_originals_unchanged():
    before = sha256(REAL_DB.read_bytes()).hexdigest()
    repo = ImportedArchiveRepository(REAL_DB, REAL_DB.parent / "sources", REAL_PACKAGE)
    snapshots = repo.list_snapshots()
    assert snapshots.observation_count.tolist() == [82878, 2397]
    assert snapshots.is_baseline.eq(0).all()
    spotify = repo.observations(snapshots.iloc[0].label)
    social = repo.observations(snapshots.iloc[1].label)
    assert len(spotify) == 82878
    assert social.groupby("platform").size().to_dict() == {"Facebook": 1812, "Instagram": 585}
    lifetime = social[social.time_grain.eq("lifetime")]
    assert len(lifetime) == 84
    assert lifetime.period_start.eq("").all() and lifetime.period_end.eq("").all()
    assert social.loc[social.status.ne("observed"), "value"].isna().all()
    for row in repo.import_history().itertuples():
        assert sha256(repo.original_source(row.source_hash)).hexdigest() == row.source_hash
    with sqlite3.connect(REAL_DB.as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        expected = db.execute("SELECT id,value,status,period_start,period_end,dimensions,measurement_type FROM observations WHERE active=1 ORDER BY id").fetchall()
    combined = pd.concat([spotify, social]).sort_values("observation_id")
    actual = [(r.observation_id, None if pd.isna(r.source_value) else r.source_value, r.source_status,
               r.period_start or None, r.period_end or None, r.dimensions_json, r.measurement_type)
              for r in combined.itertuples()]
    # Reconcile every recovered observation and semantic field against the
    # original DB, not just aggregate counts.
    assert actual == expected
    assert sha256(REAL_DB.read_bytes()).hexdigest() == before
