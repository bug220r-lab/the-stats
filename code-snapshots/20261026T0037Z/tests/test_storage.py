from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pandas as pd
import pytest

from stats_app.storage import ImportConflictError, SnapshotSealedError, SQLiteRepository, StorageError


@pytest.fixture
def repo(tmp_path):
    return SQLiteRepository(tmp_path / "private" / "reporting.sqlite3")


def record(**updates):
    row = {
        "platform": "spotify", "account": "The Stats", "entity_type": "track",
        "entity_id": "track-1", "entity_name": "Example title", "metric": "streams",
        "value": 123, "unit": "count", "period_start": "2026-10-01",
        "period_end": "2026-10-20", "time_grain": "period", "measurement_type": "period_total",
        "source_timezone": "", "captured_at": "", "status": "observed",
        "evidence_ref": "", "dimensions_json": "{}", "definition": "Streams as reported",
        "source_row": 2, "worksheet": "",
    }
    row.update(updates)
    return row


def put(repo, rows=None, source=b"original-export", label="Snapshot 2026-10-22", **kwargs):
    return repo.import_dataset(source, "export.csv", rows if rows is not None else [record()], label, **kwargs)


def test_original_bytes_and_provenance_are_preserved(repo):
    raw = b"\xef\xbb\xbfexact,source\r\n123,bytes\r\n"
    result = put(repo, source=raw, captured_at="2026-10-22", provenance={"export_note": "Manual export"})
    assert result.imported_rows == 1
    assert repo.original_source(result.source_hash) == raw
    assert result.source_hash == sha256(raw).hexdigest()
    observation = repo.observations("Snapshot 2026-10-22").iloc[0]
    assert observation["captured_at"] == "2026-10-22"
    assert observation["period_start"] == "2026-10-01"
    history = repo.import_history().iloc[0]
    assert history["captured_at"] == "2026-10-22"
    assert history["imported_at"].endswith("+00:00")
    assert json.loads(history["provenance_json"])["export_note"] == "Manual export"
    assert history["byte_count"] == len(raw)


def test_unknown_capture_date_is_not_import_date(repo):
    put(repo)
    assert repo.observations("Snapshot 2026-10-22").iloc[0]["captured_at"] == ""
    assert repo.import_history().iloc[0]["captured_at"] == ""


def test_exact_duplicate_does_not_add_rows_imports_or_totals(repo):
    first = put(repo)
    second = put(repo)
    assert second.duplicate_import
    assert second.import_id == first.import_id
    assert second.imported_rows == 0
    assert len(repo.import_history()) == 1
    assert repo.observations("Snapshot 2026-10-22")["value"].tolist() == [123.0]


def test_overlapping_different_sources_keep_links_without_double_counting(repo):
    put(repo)
    result = put(repo, rows=[record(source_row=9, evidence_ref="second export"), record(entity_id="track-2", value=20)], source=b"different-file")
    assert result.imported_rows == 1
    assert result.duplicate_rows == 1
    data = repo.observations("Snapshot 2026-10-22")
    assert len(data) == 2
    assert data["value"].sum() == 143
    assert data.iloc[0]["source_count"] == 2
    provenance = repo.observation_provenance(data.iloc[0]["observation_id"])
    assert provenance["source_row"].tolist() == [2, 9]
    assert provenance.iloc[1]["evidence_ref"] == "second export"
    assert len(repo.import_history()) == 2


def test_duplicate_rows_inside_one_export_do_not_inflate_values(repo):
    result = put(repo, [record(), record(source_row=3)])
    assert (result.imported_rows, result.duplicate_rows) == (1, 1)
    assert len(repo.observations("Snapshot 2026-10-22")) == 1


def test_one_workbook_can_import_distinct_worksheets(repo):
    first = put(repo, [record(worksheet="Tracks")], source=b"same-workbook")
    second = put(repo, [record(worksheet="Audience", entity_type="account", entity_id="account", metric="listeners", value=5)], source=b"same-workbook")
    assert not first.duplicate_import
    assert not second.duplicate_import
    assert len(repo.observations("Snapshot 2026-10-22")) == 2
    assert len(repo.import_history()) == 2
    with sqlite3.connect(repo.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM source_files").fetchone()[0] == 1


def test_changed_mapping_for_same_file_and_worksheet_is_explicit_conflict(repo):
    put(repo)
    with pytest.raises(ImportConflictError, match="different mappings or metadata"):
        put(repo, [record(metric="listeners")])
    assert len(repo.import_history()) == 1
    assert repo.observations("Snapshot 2026-10-22").iloc[0]["metric"] == "streams"


def test_conflict_rolls_back_every_part_of_import(repo):
    put(repo)
    with pytest.raises(ImportConflictError, match="entire import was cancelled"):
        put(repo, [record(entity_id="new-track"), record(value=999)], source=b"conflicting-file")
    assert len(repo.observations("Snapshot 2026-10-22")) == 1
    assert len(repo.import_history()) == 1
    with sqlite3.connect(repo.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM source_files").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM observation_sources").fetchone()[0] == 1


def test_conflicting_duplicates_in_first_import_leave_no_snapshot(repo):
    with pytest.raises(ImportConflictError):
        put(repo, [record(), record(value=999)])
    assert repo.list_snapshots().empty
    assert repo.import_history().empty


def test_missing_is_sql_null_and_zero_is_an_observed_number(repo):
    put(repo, [record(value=None, status="missing"), record(entity_id="track-2", value=0)])
    with sqlite3.connect(repo.db_path) as connection:
        assert connection.execute("SELECT value,status FROM observations ORDER BY id").fetchall() == [(None, "missing"), (0.0, "observed")]
    data = repo.observations("Snapshot 2026-10-22")
    assert pd.isna(data.iloc[0]["value"])
    assert data.iloc[1]["value"] == 0


@pytest.mark.parametrize("updates", [
    {"value": None}, {"value": "not numeric"}, {"value": float("inf")},
    {"status": "missing", "value": 0}, {"status": "suppressed", "value": 3},
    {"status": "invented"}, {"period_start": "2026-10-21"},
    {"period_end": "2026-02-30"}, {"account": ""}, {"entity_id": ""},
    {"metric": ""}, {"dimensions_json": "[]"}, {"dimensions_json": "invalid"},
    {"captured_at": "yesterday"}, {"source_row": -1}, {"source_row": 1.5},
])
def test_invalid_record_rejects_whole_import_without_persistence(repo, updates):
    with pytest.raises(StorageError):
        put(repo, [record(entity_id="valid"), record(**updates)])
    assert repo.import_history().empty
    assert repo.list_snapshots().empty


@pytest.mark.parametrize("status", ["missing", "suppressed", "unavailable"])
def test_each_missing_status_preserved(repo, status):
    put(repo, [record(status=status, value=None)])
    assert repo.observations("Snapshot 2026-10-22").iloc[0]["status"] == status


def test_dataframe_and_dimension_key_normalization(repo):
    put(repo, pd.DataFrame([record(dimensions_json='{"country":"US","device":"mobile"}')]))
    result = put(repo, [record(dimensions_json='{"device": "mobile", "country": "US"}')], source=b"reordered-dimensions")
    assert result.duplicate_rows == 1
    assert len(repo.observations("Snapshot 2026-10-22")) == 1


def test_dimension_account_and_reporting_period_define_separate_observations(repo):
    put(repo, [record(), record(account="Another account"), record(dimensions_json='{"country":"US"}'), record(period_start="2026-10-02")])
    assert len(repo.observations("Snapshot 2026-10-22")) == 4


def test_baseline_requires_evidence(repo):
    with pytest.raises(StorageError, match="baseline_evidence"):
        put(repo, baseline=True)
    assert repo.list_snapshots().empty


def test_baseline_seed_seal_and_newer_snapshot_preserve_original(repo):
    evidence = {"baseline_evidence": "Verified reporting baseline dated October 20, 2026"}
    label = "Spotify baseline 2026-10-20"
    put(repo, label=label, baseline=True, provenance=evidence)
    put(repo, [record(entity_id="track-2", value=20)], source=b"baseline-second-source", label=label, baseline=True, provenance=evidence)
    repo.seal_snapshot(label)
    original = repo.observations(label).copy()
    assert put(repo, label=label, baseline=True, provenance=evidence).duplicate_import
    with pytest.raises(SnapshotSealedError):
        put(repo, source=b"unrecognized-source", label=label, baseline=True, provenance=evidence)
    with pytest.raises(StorageError, match="designation"):
        put(repo, label=label)
    with pytest.raises(StorageError, match="already exists"):
        put(repo, label="Second baseline", baseline=True, provenance=evidence)
    put(repo, [record(value=999)], source=b"new-export", label="Spotify 2026-10-22")
    pd.testing.assert_frame_equal(repo.observations(label), original)
    assert repo.observations("Spotify 2026-10-22").iloc[0]["value"] == 999
    snapshots = repo.list_snapshots().set_index("label")
    assert snapshots.loc[label, "sealed"] == 1
    assert snapshots.loc[label, "is_baseline"] == 1


def test_unsealed_baseline_still_cannot_replace_existing_measurement(repo):
    evidence = {"baseline_evidence": "Original report"}
    put(repo, baseline=True, provenance=evidence)
    with pytest.raises(ImportConflictError):
        put(repo, [record(value=999)], source=b"replacement", baseline=True, provenance=evidence)
    assert repo.observations("Snapshot 2026-10-22").iloc[0]["value"] == 123


def test_process_restart_reads_same_data_and_raw_source(repo):
    imported = put(repo)
    script = (
        "import json,sys; from stats_app.storage import SQLiteRepository; "
        "r=SQLiteRepository(sys.argv[1]); "
        "print(json.dumps({'rows':len(r.observations(sys.argv[2])), "
        "'value':float(r.observations(sys.argv[2]).iloc[0]['value']), "
        "'source':r.original_source(sys.argv[3]).decode()}))"
    )
    completed = subprocess.run([sys.executable, "-c", script, str(repo.db_path), "Snapshot 2026-10-22", imported.source_hash],
                               cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=True)
    assert json.loads(completed.stdout) == {"rows": 1, "value": 123.0, "source": "original-export"}


def test_concurrent_same_source_imports_are_idempotent(repo):
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: put(repo), range(4)))
    assert sum(result.imported_rows for result in results) == 1
    assert sum(result.duplicate_import for result in results) == 3
    assert len(repo.import_history()) == 1


def test_simultaneous_first_open_initializes_database_safely(tmp_path):
    path = tmp_path / "new-database.sqlite3"
    with ThreadPoolExecutor(max_workers=8) as executor:
        repositories = list(executor.map(lambda _: SQLiteRepository(path), range(8)))
    assert all(repository.list_snapshots().empty for repository in repositories)
    put(repositories[0])
    assert len(repositories[-1].import_history()) == 1


def test_consistent_backup_includes_data_and_source_bytes(repo, tmp_path):
    imported = put(repo)
    path = repo.backup(tmp_path / "backups" / "snapshot.sqlite3")
    restored = SQLiteRepository(path)
    pd.testing.assert_frame_equal(repo.observations("Snapshot 2026-10-22"), restored.observations("Snapshot 2026-10-22"))
    assert restored.original_source(imported.source_hash) == b"original-export"
    with pytest.raises(FileExistsError):
        repo.backup(path)
    with pytest.raises(StorageError):
        repo.backup(repo.db_path)


def test_empty_state_has_stable_dataframe_columns(repo):
    assert repo.list_snapshots().empty
    assert "label" in repo.list_snapshots()
    assert "metric" in repo.observations("unknown")
    assert "source_hash" in repo.import_history()


def test_unknown_schema_is_not_modified(tmp_path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=999")
    with pytest.raises(StorageError, match="Unsupported database schema"):
        SQLiteRepository(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 999
