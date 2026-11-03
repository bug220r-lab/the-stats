"""Consequential import/readback regressions from the October 25 program audit."""
from contextlib import closing
from decimal import Decimal
from hashlib import sha256
import sqlite3

import numpy as np
import pytest

from stats_app.access import Principal
from stats_app.service import commit_import
from stats_app.storage import ImportConflictError, SQLiteRepository, StorageError
from stats_app.validation import finite_number, numeric_value, validate_records


def row(**updates):
    return {**dict(platform="Instagram", account="synthetic-account", entity_type="video",
                   entity_id="synthetic-video", metric="views", value=25, unit="count",
                   period_start="2026-10-01", period_end="2026-10-01", time_grain="daily",
                   measurement_type="period_count", source_timezone="UTC", status="observed",
                   dimensions_json="{}", definition="Organic video views", source_row=2), **updates}


def dump(repo):
    with closing(sqlite3.connect(repo.db_path.as_uri() + "?mode=ro", uri=True)) as connection:
        return tuple(connection.iterdump())


def save(repo, records, raw=b"first synthetic source"):
    return repo.import_dataset(raw, "synthetic.csv", records, "Synthetic capture")


@pytest.mark.parametrize("preview", [False, True])
def test_different_definition_refuses_entire_source_and_keeps_existing_history(tmp_path, preview):
    repo = SQLiteRepository(tmp_path / "library.sqlite3")
    first = save(repo, [row()])
    before = dump(repo)
    import_method = repo.preview_dataset if preview else repo.import_dataset
    with pytest.raises(ImportConflictError, match="definition or scope"):
        import_method(b"second synthetic source", "second.csv",
                      [row(entity_id="would-be-new"), row(definition="Paid video views")],
                      "Synthetic capture")
    assert dump(repo) == before
    assert repo.original_source(first.source_hash) == b"first synthetic source"
    assert repo.observations("Synthetic capture").definition.tolist() == ["Organic video views"]


def test_definition_conflicts_inside_first_source_leave_no_snapshot(tmp_path):
    repo = SQLiteRepository(tmp_path / "library.sqlite3")
    with pytest.raises(ImportConflictError, match="definition or scope"):
        save(repo, [row(), row(definition="Paid video views", source_row=3)])
    assert repo.list_snapshots().empty
    assert repo.import_history().empty


def test_explicit_different_dimensions_preserve_both_definitions(tmp_path):
    repo = SQLiteRepository(tmp_path / "library.sqlite3")
    result = save(repo, [row(dimensions_json='{"traffic":"organic"}'),
                         row(dimensions_json='{"traffic":"paid"}', definition="Paid video views")])
    assert (result.imported_rows, result.duplicate_rows) == (2, 0)
    assert set(repo.observations("Synthetic capture").definition) == {"Organic video views", "Paid video views"}


def test_equal_definition_keeps_overlap_and_exact_replay_idempotent(tmp_path):
    repo = SQLiteRepository(tmp_path / "library.sqlite3")
    first = save(repo, [row()])
    overlapping = save(repo, [row(definition="  Organic video views  ")], b"second source")
    assert (overlapping.imported_rows, overlapping.duplicate_rows) == (0, 1)
    before = dump(repo)
    replay = save(repo, [row()])
    assert replay.duplicate_import and replay.import_id == first.import_id
    assert dump(repo) == before


@pytest.mark.parametrize("corruption", ["bytes", "length"])
def test_original_source_readback_refuses_corruption_without_repairing_it(tmp_path, corruption):
    repo = SQLiteRepository(tmp_path / "library.sqlite3")
    result = save(repo, [row()], b"original bytes")
    with closing(sqlite3.connect(repo.db_path)) as connection:
        if corruption == "bytes":
            connection.execute("UPDATE source_files SET original_bytes=? WHERE hash=?", (b"corrupt! bytes", result.source_hash))
        else:
            connection.execute("UPDATE source_files SET byte_count=byte_count+1 WHERE hash=?", (result.source_hash,))
        connection.commit()
    before = dump(repo)
    with pytest.raises(StorageError, match="SHA-256 or byte-count"):
        repo.original_source(result.source_hash)
    assert dump(repo) == before


@pytest.mark.parametrize("raw, expected", [("0", 0), ("0.1", 0.1), ("1,234.50", 1234.5),
                                          ("9007199254740992", 9007199254740992),
                                          ("9007199254740994", 9007199254740994)])
def test_source_numbers_that_survive_roundtrip_remain_accepted(raw, expected):
    assert numeric_value(raw) == (expected, "observed")


@pytest.mark.parametrize("raw", ["9007199254740993", "-9007199254740993",
                                 "0.100000000000000001", "0." + "0" * 399 + "1"])
def test_source_numbers_cannot_silently_round_or_underflow(raw):
    with pytest.raises(ValueError, match="precision|underflow"):
        numeric_value(raw)


@pytest.mark.parametrize("raw", [9007199254740993, Decimal("9007199254740993"),
                                 Decimal("0.100000000000000001"), Decimal("1e-400")])
def test_direct_storage_boundary_rejects_unsafe_numbers_without_writes(tmp_path, raw):
    repo = SQLiteRepository(tmp_path / "library.sqlite3")
    before = dump(repo)
    with pytest.raises(StorageError, match="precision|underflow"):
        save(repo, [row(value=raw)])
    assert dump(repo) == before


def test_adjacent_large_counts_are_a_refusal_never_a_duplicate(tmp_path):
    repo = SQLiteRepository(tmp_path / "library.sqlite3")
    save(repo, [row(value=9007199254740992)])
    before = dump(repo)
    with pytest.raises(StorageError, match="precision"):
        save(repo, [row(value=9007199254740993)], b"different exact count")
    assert dump(repo) == before
    assert len(repo.import_history()) == 1


def test_validation_preserves_integer_evidence_before_dataframe_coercion(tmp_path):
    records = [row(value=9007199254740993), row(entity_id="unknown", value=None, status="unavailable")]
    assert any("precision" in issue for issue in validate_records(records))
    repo = SQLiteRepository(tmp_path / "library.sqlite3")
    with pytest.raises(ValueError, match="precision"):
        commit_import(repo, Principal("Synthetic admin", "admin"), raw_bytes=b"unsafe source",
                      source_name="source.csv", records=records, snapshot_label="Synthetic capture")
    assert repo.import_history().empty and repo.list_snapshots().empty


def test_valid_original_bytes_and_source_hash_still_agree(tmp_path):
    repo = SQLiteRepository(tmp_path / "library.sqlite3")
    result = save(repo, [row()])
    returned = repo.original_source(result.source_hash)
    assert sha256(returned).hexdigest() == result.source_hash
    assert finite_number(Decimal("0.1")) == 0.1


@pytest.mark.parametrize("value", [1e23, np.float64(1e23), 1e100, 0.30000000000000004])
def test_existing_binary64_inputs_are_preserved_without_inventing_original_digits(tmp_path, value):
    assert finite_number(value) == value
    repo = SQLiteRepository(tmp_path / "library.sqlite3")
    save(repo, [row(value=value)])
    assert repo.observations("Synthetic capture").iloc[0].value == value
