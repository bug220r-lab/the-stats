"""Import previews run the actual write rules only on disposable memory copies."""
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from stats_app.storage import ImportConflictError, SnapshotSealedError, SQLiteRepository


@pytest.fixture
def repo(tmp_path):
    return SQLiteRepository(tmp_path / "library.sqlite3")


def record(**updates):
    row = dict(platform="Spotify", account="artist-id", entity_type="track", entity_id="track-1",
               metric="streams", value=123, unit="count", period_start="2026-10-01",
               period_end="2026-10-20", time_grain="period", measurement_type="period_total",
               source_timezone="UTC", status="observed", source_row=2)
    return {**row, **updates}


def contents(repo):
    """All schema and data, including source bytes, without WAL header noise."""
    with sqlite3.connect(repo.db_path.as_uri() + "?mode=ro", uri=True) as connection:
        return tuple(connection.iterdump())


def preview(repo, rows, raw=b"new source", label="October", **kwargs):
    before = contents(repo)
    try:
        return repo.preview_dataset(raw, "source.csv", rows, label, **kwargs)
    finally:
        assert contents(repo) == before


def put(repo, rows=None, raw=b"existing source", label="October", **kwargs):
    return repo.import_dataset(raw, "source.csv", rows or [record()], label, **kwargs)


def test_preview_new_snapshot_and_within_file_duplicates_never_persist(repo):
    rows = [record(), record(source_row=3), record(entity_id="track-2", source_row=4)]
    result = preview(repo, pd.DataFrame(rows))
    assert (result.imported_rows, result.duplicate_rows, result.duplicate_import) == (2, 1, False)
    assert repo.list_snapshots().empty
    assert repo.import_history().empty
    saved = put(repo, rows=rows, raw=b"new source")
    assert (saved.imported_rows, saved.duplicate_rows) == (result.imported_rows, result.duplicate_rows)


def test_preview_distinguishes_equal_overlap_from_new_observations(repo):
    put(repo)
    result = preview(repo, [record(source_row=8), record(entity_id="track-2")])
    assert (result.imported_rows, result.duplicate_rows, result.duplicate_import) == (1, 1, False)
    assert len(repo.observations("October")) == 1
    assert len(repo.import_history()) == 1


def test_preview_exact_replay_reports_unchanged_import(repo):
    first = put(repo)
    result = preview(repo, [record()], raw=b"existing source")
    assert (result.imported_rows, result.duplicate_rows, result.duplicate_import) == (0, 1, True)
    assert result.import_id == first.import_id
    assert result.source_hash == first.source_hash


def test_preview_conflicting_value_rejects_whole_file_without_changes(repo):
    put(repo)
    with pytest.raises(ImportConflictError, match="entire import was cancelled"):
        preview(repo, [record(entity_id="would-be-new"), record(value=999)])


def test_preview_changed_interpretation_is_rejected(repo):
    put(repo)
    with pytest.raises(ImportConflictError, match="different mappings or metadata"):
        preview(repo, [record(metric="listeners")], raw=b"existing source")


def test_preview_sealed_snapshot_refuses_new_source_but_accepts_replay(repo):
    put(repo)
    repo.seal_snapshot("October")
    with pytest.raises(SnapshotSealedError, match="separately labeled snapshot"):
        preview(repo, [record()])
    result = preview(repo, [record()], raw=b"existing source")
    assert result.duplicate_import
    assert result.imported_rows == 0


def test_preview_preserves_account_and_dimension_grain(repo):
    put(repo)
    result = preview(repo, [record(), record(account="other-artist"),
                            record(dimensions_json='{"country":"US"}')])
    assert (result.imported_rows, result.duplicate_rows) == (2, 1)


def test_preview_backup_reads_committed_wal_and_does_not_checkpoint_source(repo):
    keeper = sqlite3.connect(repo.db_path)
    try:
        keeper.execute("PRAGMA journal_mode=WAL")
        keeper.execute("SELECT COUNT(*) FROM snapshots").fetchone()
        put(repo)
        wal = Path(str(repo.db_path) + "-wal")
        assert wal.is_file() and wal.stat().st_size > 0
        wal_before = wal.read_bytes()
        database_before = repo.db_path.read_bytes()
        result = preview(repo, [record()], raw=b"existing source")
        assert result.duplicate_import
        assert wal.read_bytes() == wal_before
        assert repo.db_path.read_bytes() == database_before
    finally:
        keeper.close()
