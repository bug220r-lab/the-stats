import hashlib
import json
import sqlite3

import pandas as pd
import pytest

from stats.storage import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "data" / "stats.sqlite3")


def reading(value=12, **updates):
    row = dict(platform="spotify", account_id="artist:42", account_name="Artist",
               entity_type="track", entity_id="track:99", entity_name="Song", metric="streams",
               value=value, unit="count", definition="Recorded streams", dimensions={},
               period_start="2026-10-19", period_end="2026-10-19", time_grain="daily",
               captured_at="2026-10-20T12:00:00", source_timezone=None,
               measurement_type="period_count", status="verified", source_row=2)
    row.update(updates)
    return row


def test_reimport_is_idempotent_and_raw_bytes_survive(store):
    snap = store.create_snapshot("October capture")
    raw = b"\xef\xbb\xbfDate,Streams\r\n2026-10-19,12\r\n"
    first = store.commit_import(snap, "data.csv", raw, [reading()], mapping={"streams": "Streams"})
    token = store.cache_token()
    second = store.commit_import(snap, "renamed.csv", raw, [reading()], mapping={"streams": "Streams"})
    assert second["idempotent"] is True
    assert second["import_id"] == first["import_id"]
    assert store.cache_token() == token
    assert len(store.imports()) == len(store.read_observations()) == 1
    archived = store.source_dir / (hashlib.sha256(raw).hexdigest() + ".csv")
    assert archived.read_bytes() == raw


def test_overlap_and_revisions_preserve_every_source_reference(store):
    snap = store.create_snapshot("Capture")
    store.commit_import(snap, "one.csv", b"one", [reading()])
    overlap = store.commit_import(snap, "two.csv", b"two", [reading(source_row=7)])
    assert overlap["duplicates"] == 1
    refs = json.loads(store.read_observations().iloc[0]["source_references"])
    assert [ref["source_row"] for ref in refs] == ["2", "7"]
    revision = store.commit_import(snap, "three.csv", b"three", [reading(15)])
    assert revision["revised"] == 1
    assert store.read_observations()["value"].tolist() == [15]
    history = store.read_observations(include_history=True)
    assert history["value"].tolist() == [12, 15]
    assert history["active"].tolist() == [0, 1]
    assert history["version"].tolist() == [1, 2]


def test_original_baseline_is_identified_staged_and_sealed(store):
    with pytest.raises(ValueError, match="evidence"):
        store.create_snapshot("October 20", is_baseline=True)
    baseline = store.create_snapshot("Original October 20", is_baseline=True,
                                     status="verified", evidence="Original export filenames and reporting windows verified")
    assert store.snapshots()[0]["status"] == "staging"
    first = store.commit_import(baseline, "original.csv", b"original", [reading()])
    with pytest.raises(ValueError, match="conflicting"):
        store.commit_import(baseline, "revision.csv", b"revision", [reading(99)])
    assert len(store.imports()) == 1
    store.commit_import(baseline, "original2.csv", b"original2", [reading(4, entity_id="track:100")])
    with pytest.raises(ValueError, match="cannot be retired"):
        store.retire_import(first["import_id"])
    store.lock_snapshot(baseline)
    assert store.snapshots()[0]["status"] == "verified"
    with pytest.raises(ValueError, match="immutable"):
        store.commit_import(baseline, "new.csv", b"new", [reading(99)])
    newer = store.create_snapshot("New capture")
    store.commit_import(newer, "new.csv", b"new", [reading(99)])
    assert store.read_observations(baseline)["value"].tolist() == [12, 4]
    assert store.read_observations(newer)["value"].tolist() == [99]
    assert store.commit_import(baseline, "original.csv", b"original", [reading()])["idempotent"]


def test_missing_zero_and_unparsed_rows_are_distinct(store):
    snap = store.create_snapshot("Capture")
    result = store.commit_import(snap, "file.csv", b"file", [reading(None), reading(0, entity_id="zero"), reading("suppressed", entity_id="bad")])
    frame = store.read_observations()
    assert pd.isna(frame.loc[0, "value"])
    assert frame.loc[1, "value"] == 0
    assert result["rejected"] == 1
    assert store.issues()[0]["code"] == "rejected_row"
    assert frame["source_timezone"].isna().all()


def test_semantics_and_dimensions_prevent_accidental_merge(store):
    snap = store.create_snapshot("Capture")
    store.commit_import(snap, "file.csv", b"file", [
        reading(), reading(3, dimensions={"country": "US"}),
        reading(7, measurement_type="cumulative_total"),
        reading(9, period_end="2026-10-20"),
    ])
    assert len(store.read_observations()) == 4


def test_missing_ids_are_source_scoped(store):
    snap = store.create_snapshot("Capture")
    row = reading(account_id=None, entity_id=None)
    store.commit_import(snap, "one.csv", b"one", [row])
    store.commit_import(snap, "two.csv", b"two", [row])
    frame = store.read_observations()
    assert len(frame) == 2
    assert frame["entity_id"].nunique() == 2
    assert all(value.startswith("source:") for value in frame["entity_id"])
    assert len(store.issues()) == 4


def test_retire_revision_restores_previous_version(store):
    snap = store.create_snapshot("Capture")
    first = store.commit_import(snap, "one.csv", b"one", [reading()])
    second = store.commit_import(snap, "two.csv", b"two", [reading(30)])
    store.retire_import(second["import_id"])
    assert store.read_observations()["value"].tolist() == [12]
    store.retire_import(first["import_id"])
    assert store.read_observations().empty
    assert len(store.read_observations(include_history=True)) == 2


def test_duplicate_source_keeps_reading_active_when_original_import_retired(store):
    snap = store.create_snapshot("Capture")
    first = store.commit_import(snap, "one.csv", b"one", [reading()])
    store.commit_import(snap, "two.csv", b"two", [reading(captured_at="2026-10-22T09:00:00")])
    store.retire_import(first["import_id"])
    assert store.read_observations()["value"].tolist() == [12]
    assert store.read_observations().iloc[0]["source_filename"] == "two.csv"
    assert store.read_observations().iloc[0]["captured_at"] == "2026-10-22T09:00:00"
    assert store.read_observations().iloc[0]["import_retired"] == 0


def test_restart_mappings_annotations_queue_and_backup(store, tmp_path):
    snap = store.create_snapshot("Capture")
    store.commit_import(snap, "file.csv", b"file", [reading()])
    store.save_mapping("Spotify", {"metric": "Streams"})
    annotation_id = store.save_annotation({"date": "2026-10-20", "kind": "release", "title": "Release", "links": ["track:99"]})
    store.save_queue([{"source_row": 2, "status": "Pending", "timestamp": "2026-10-20 09:30", "task": "Collect"}], "sheet:queue")
    queue_id = store.queue()[0]["id"]
    store.save_queue_note(queue_id, "Local follow-up only")
    store.save_queue([{"source_row": 2, "status": "Pending", "timestamp": "2026-10-20 09:30", "task": "Collect"}], "sheet:queue")
    restarted = Store(store.path)
    assert restarted.read_observations()["value"].tolist() == [12]
    assert restarted.mappings() == {"Spotify": {"metric": "Streams"}}
    assert restarted.annotations()[0]["id"] == annotation_id
    assert restarted.annotations()[0]["origin"] == "local_user_annotation"
    queue = restarted.queue()[0]
    assert queue["status"] == "Pending"
    assert queue["timestamp"] == "2026-10-20 09:30"
    assert queue["local_note"] == "Local follow-up only"
    assert queue["captured_at"] is None
    backup = restarted.backup(tmp_path / "backup")
    restored = Store(backup / store.path.name)
    assert restored.read_observations()["value"].tolist() == [12]
    assert (restored.source_dir / (hashlib.sha256(b"file").hexdigest() + ".csv")).read_bytes() == b"file"


def test_same_date_different_timezone_never_deduplicates_or_revises(store):
    snap = store.create_snapshot("Capture")
    store.commit_import(snap, "utc.csv", b"utc", [reading(12, source_timezone="UTC")])
    different = store.commit_import(snap, "new-york.csv", b"ny", [reading(12, source_timezone="America/New_York")])
    same = store.commit_import(snap, "utc-overlap.csv", b"utc2", [reading(12, source_timezone="UTC")])
    assert different["inserted"] == 1
    assert different["duplicates"] == different["revised"] == 0
    assert same["duplicates"] == 1
    frame = store.read_observations(snap)
    assert len(frame) == 2
    assert set(frame["source_timezone"]) == {"UTC", "America/New_York"}
    assert frame["version"].tolist() == [1, 1]
    store.commit_import(snap, "utc-revision.csv", b"utc3", [reading(15, source_timezone="UTC")])
    readings = store.read_observations(snap).set_index("source_timezone")["value"].to_dict()
    assert readings == {"UTC": 15, "America/New_York": 12}


def test_unknown_timezone_is_distinct_from_known_and_blank_is_normalized(store):
    snap = store.create_snapshot("Capture")
    store.commit_import(snap, "unknown.csv", b"unknown", [reading(source_timezone=None)])
    blank = store.commit_import(snap, "blank.csv", b"blank", [reading(source_timezone="  ")])
    known = store.commit_import(snap, "known.csv", b"known", [reading(source_timezone="UTC")])
    assert blank["duplicates"] == 1
    assert known["inserted"] == 1
    assert len(store.read_observations(snap)) == 2


def test_migration_recovers_timezone_duplicates_from_original_source_payloads(store):
    snap = store.create_snapshot("Legacy capture")
    store.commit_import(snap, "utc.csv", b"utc", [reading(source_timezone="UTC")])
    store.commit_import(snap, "ny.csv", b"ny", [reading(source_timezone="America/New_York")])
    # Reproduce the old schema's wrong merge, retaining both original payloads.
    with sqlite3.connect(store.path) as db:
        ids = [row[0] for row in db.execute("SELECT id FROM observations ORDER BY id")]
        db.execute("UPDATE observation_sources SET observation_id = ? WHERE observation_id = ?", ids)
        db.execute("DELETE FROM observations WHERE id = ?", (ids[1],))
        db.execute("UPDATE state SET value = 1 WHERE key = 'identity_schema_version'")
    migrated = Store(store.path)
    frame = migrated.read_observations(snap)
    assert len(frame) == 2
    assert set(frame["source_timezone"]) == {"UTC", "America/New_York"}
    assert frame["value"].tolist() == [12, 12]
    assert frame.set_index("source_timezone")["source_filename"].to_dict() == {
        "UTC": "utc.csv", "America/New_York": "ny.csv"}
    assert all(len(json.loads(value)) == 1 for value in frame["source_references"])
    token = migrated.cache_token()
    restarted = Store(store.path)
    assert restarted.cache_token() == token
    assert len(restarted.read_observations(snap)) == 2
    with sqlite3.connect(store.path) as db:
        detail = json.loads(db.execute("SELECT detail_json FROM schema_migrations WHERE version = 2").fetchone()[0])
    assert detail == {"original_observations": 1, "timezone_splits": 1}


def test_migration_reactivates_distinct_timezone_scopes_and_retirement_uses_versions(store):
    snap = store.create_snapshot("Legacy versions")
    store.commit_import(snap, "utc.csv", b"utc", [reading(12, source_timezone="UTC")])
    ny = store.commit_import(snap, "ny.csv", b"ny", [reading(15, source_timezone="America/New_York")])
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE observations SET active = 0 WHERE source_timezone = 'UTC'")
        db.execute("UPDATE observations SET version = 2 WHERE source_timezone = 'America/New_York'")
        db.execute("UPDATE state SET value = 1 WHERE key = 'identity_schema_version'")
    migrated = Store(store.path)
    assert migrated.read_observations(snap).set_index("source_timezone")["value"].to_dict() == {
        "UTC": 12, "America/New_York": 15}
    assert migrated.read_observations(snap)["version"].tolist() == [1, 1]
    migrated.retire_import(ny["import_id"])
    assert migrated.read_observations(snap)["source_timezone"].tolist() == ["UTC"]


def test_migration_split_does_not_override_a_later_revision(store):
    snap = store.create_snapshot("Legacy split and revision")
    store.commit_import(snap, "utc.csv", b"utc", [reading(12, source_timezone="UTC")])
    store.commit_import(snap, "ny-first.csv", b"ny1", [reading(12, source_timezone="America/New_York")])
    latest = store.commit_import(snap, "ny-latest.csv", b"ny2", [reading(15, source_timezone="America/New_York")])
    with sqlite3.connect(store.path) as db:
        ids = [row[0] for row in db.execute("SELECT id FROM observations ORDER BY id")]
        db.execute("UPDATE observation_sources SET observation_id = ? WHERE observation_id = ?", (ids[0], ids[1]))
        db.execute("DELETE FROM observations WHERE id = ?", (ids[1],))
        db.execute("UPDATE observations SET active = 0 WHERE id = ?", (ids[0],))
        db.execute("UPDATE state SET value = 1 WHERE key = 'identity_schema_version'")
    migrated = Store(store.path)
    assert migrated.read_observations(snap).set_index("source_timezone")["value"].to_dict() == {
        "UTC": 12, "America/New_York": 15}
    migrated.retire_import(latest["import_id"])
    assert migrated.read_observations(snap).set_index("source_timezone")["value"].to_dict() == {
        "UTC": 12, "America/New_York": 12}
