"""Immutable analysis history, atomic activation and portable version backups."""
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

import scripts.promote_analysis as promotion
from scripts.promote_analysis import promote
from stats_app.analysis_repository import (
    AnalysisRepository, list_registered_analyses, load_registered_analysis, stage_analysis_package,
)
from stats_app.backup import backup_library, verify_bundle
from stats_app.storage import SQLiteRepository, StorageError


def write_acceptance(stage, path, key, live, *, style="meta"):
    """Synthetic acceptance metadata for isolated test libraries only."""
    receipt = {
        "passed": True,
        "audited_at_utc": "2026-10-23T05:00:00+00:00",
        "candidate_database_sha256": hashlib.sha256((stage / "analysis.sqlite3").read_bytes()).hexdigest(),
        "all_prior_database_hashes": {
            candidate.relative_to(live).as_posix(): hashlib.sha256(candidate.read_bytes()).hexdigest()
            for candidate in live.rglob("*.sqlite3")
        },
    }
    if style == "meta":
        receipt.update(
            audit_scope="independent_semantic_evidence_and_storage_acceptance",
            analysis_version=key,
            semantic_checks={"source_claims_reviewed": True, "unresolved_assignments": 0},
            storage_checks={"all_candidate_table_rows_match_csv": True, "all_zip_assets_match_database": True},
            registry_unchanged_before_activation=True,
            supporting_receipts={"semantic_acceptance_audit.json": "1" * 64, "independent_storage_audit.json": "2" * 64},
        )
    else:
        receipt.update(
            status="PASS", analysis_key=key,
            approval_scope="Accept this isolated test candidate after semantic and storage review.",
            summary={"verified_rows": 1, "unresolved_assignments": 0},
            normalization_receipt_sha256="3" * 64,
            supporting_receipts=[
                {"path": "review/semantic_acceptance_audit.json", "sha256": "1" * 64},
                {"path": "review/direct_sql_storage_audit.json", "sha256": "2" * 64},
            ],
        )
    path.write_text(json.dumps(receipt), encoding="utf-8")
    return receipt


def make_package(tmp_path, name, streams):
    root = tmp_path / name
    raw = f"date,streams\n2026-10-20,{streams}\n".encode()
    files = {
        "raw/source.csv": raw,
        "spotify/cleaned/artist_daily.csv": raw,
        "audit/final_validation.json": b'{"checks":{"raw_source_files_unchanged":true}}',
        "raw_sha256.json": json.dumps([{"path": "raw/source.csv", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}]).encode(),
    }
    archive = tmp_path / (name + ".zip")
    with zipfile.ZipFile(archive, "w") as zipped:
        for name, contents in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
            zipped.writestr(root.name + "/" + name, contents)
    return root, archive


@pytest.fixture
def versions(tmp_path):
    live = tmp_path / "live"
    SQLiteRepository(live / "stats.sqlite3")
    old_root, old_zip = make_package(tmp_path, "original", 7)
    old_dir = live / "analysis/cleaned-20261022"
    stage_analysis_package(old_root, old_zip, old_dir)
    registry = {"archives": [], "analysis_package": {
        "database": "analysis/cleaned-20261022/analysis.sqlite3", "evidence_root": "analysis/cleaned-20261022", "label": "Original cleaned analysis",
    }}
    (live / "archive_registry.json").write_text(json.dumps(registry), encoding="utf-8")
    new_root, new_zip = make_package(tmp_path, "combined", 9)
    stage = tmp_path / "stage"
    stage_analysis_package(new_root, new_zip, stage, "https://example.test/collection",
                           label="Expanded Spotify collection", metadata={"activity_endpoint": "2026-10-21", "retrieval_vintage": "2026-10-23",
                           "version_lineage": [{"key": "cleaned-20261022", "purpose": "preserved predecessor"}]})
    audit = tmp_path / "independent_audit.json"
    write_acceptance(stage, audit, "expanded", live)
    return live, stage, audit, old_zip, new_zip


def test_legacy_key_is_inferred_without_rewriting_registry(versions):
    live, _, _, _, _ = versions
    before = (live / "archive_registry.json").read_bytes()
    records = list_registered_analyses(live)
    assert len(records) == 1 and records[0]["key"] == "cleaned-20261022"
    assert records[0]["active"]
    assert load_registered_analysis(live).registered_key == "cleaned-20261022"
    assert load_registered_analysis(live, "cleaned-20261022").table("spotify/cleaned/artist_daily.csv").streams.tolist() == [7]
    assert (live / "archive_registry.json").read_bytes() == before
    with pytest.raises(StorageError, match="No registered"):
        load_registered_analysis(live, "not-imported")


def test_activation_keeps_prior_versions_exact_and_replay_is_read_only(versions, tmp_path):
    live, stage, audit, old_zip, new_zip = versions
    write_acceptance(stage, audit, "expanded-20261023", live)
    old = {p: p.read_bytes() for p in live.rglob("*.sqlite3")}
    report = promote(stage, audit, live, key="expanded-20261023")
    assert report["active"] and not report["idempotent"]
    assert all(path.read_bytes() == contents for path, contents in old.items())
    assert [r["active"] for r in list_registered_analyses(live)] == [False, True]
    assert load_registered_analysis(live).registered_key == "expanded-20261023"
    assert load_registered_analysis(live).original_zip() == new_zip.read_bytes()
    assert load_registered_analysis(live, "cleaned-20261022").original_zip() == old_zip.read_bytes()
    assert load_registered_analysis(live).metadata["baseline_status"] == "unverified"
    receipt = json.loads((live / "analysis/expanded-20261023/activation_receipt.json").read_text())
    assert set(receipt["earlier_database_hashes"]) == {"stats.sqlite3", "analysis/cleaned-20261022/analysis.sqlite3"}
    registry_before = (live / "archive_registry.json").read_bytes()
    assert promote(stage, audit, live, key="expanded-20261023")["idempotent"]
    assert (live / "archive_registry.json").read_bytes() == registry_before
    assert not (live / "archive_registry.lock").exists()

    next_root, next_zip = make_package(tmp_path, "later", 12)
    next_stage = tmp_path / "next-stage"
    stage_analysis_package(next_root, next_zip, next_stage, label="Later collection")
    next_audit = tmp_path / "next-audit.json"
    write_acceptance(next_stage, next_audit, "later-20261024", live)
    promote(next_stage, next_audit, live, key="later-20261024")
    prior_registry = (live / "archive_registry.json").read_bytes()
    replay = promote(stage, audit, live, key="expanded-20261023")
    assert replay["idempotent"] and not replay["active"]
    assert (live / "archive_registry.json").read_bytes() == prior_registry
    assert load_registered_analysis(live).registered_key == "later-20261024"


def test_different_data_same_key_refused_without_registry_or_store_changes(versions, tmp_path):
    live, stage, audit, _, _ = versions
    promote(stage, audit, live, key="expanded")
    root, archive = make_package(tmp_path, "different", 10)
    changed = tmp_path / "different-stage"
    stage_analysis_package(root, archive, changed)
    before = {p: p.read_bytes() for p in live.rglob("*") if p.is_file()}
    with pytest.raises(StorageError, match="already identifies different"):
        promote(changed, audit, live, key="expanded")
    assert all(p.read_bytes() == contents for p, contents in before.items())
    with pytest.raises(StorageError, match="keys must"):
        promote(stage, audit, live, key="../escape")


def test_every_version_survives_backup_and_relocation(versions, tmp_path):
    live, stage, audit, old_zip, new_zip = versions
    promote(stage, audit, live, key="expanded")
    bundle = backup_library(live, tmp_path / "backup")
    manifest = verify_bundle(bundle)
    assert manifest["analysis_versions_included"] == 2
    paths = [item["path"] for item in manifest["files"]]
    assert len(paths) == len(set(paths))
    for name in ("cleaned-20261022", "expanded"):
        relative = f"analysis/{name}/analysis.sqlite3"
        assert paths.count(relative) == 1
        assert (bundle / relative).read_bytes() == (live / relative).read_bytes()
    assert (bundle / "archive_registry.json").read_bytes() == (live / "archive_registry.json").read_bytes()
    assert load_registered_analysis(bundle, "cleaned-20261022").original_zip() == old_zip.read_bytes()
    assert load_registered_analysis(bundle).original_zip() == new_zip.read_bytes()
    assert load_registered_analysis(bundle).table("spotify/cleaned/artist_daily.csv").streams.tolist() == [9]
    with sqlite3.connect((bundle / "stats.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_pointer_conflicts_duplicate_versions_and_unsafe_prior_paths_fail_closed(versions):
    live, stage, audit, _, _ = versions
    promote(stage, audit, live, key="expanded")
    path = live / "archive_registry.json"
    original = json.loads(path.read_text())
    modified = json.loads(json.dumps(original))
    modified["analysis_package"]["label"] = "Incorrect pointer"
    path.write_text(json.dumps(modified))
    with pytest.raises(StorageError, match="conflicts"):
        load_registered_analysis(live)
    modified = json.loads(json.dumps(original))
    modified["analysis_versions"].append(modified["analysis_versions"][0])
    path.write_text(json.dumps(modified))
    with pytest.raises(StorageError, match="must be unique"):
        list_registered_analyses(live)
    modified = json.loads(json.dumps(original))
    modified["analysis_versions"][0]["database"] = "../private.sqlite3"
    path.write_text(json.dumps(modified))
    with pytest.raises(StorageError, match="Unsafe"):
        load_registered_analysis(live)


def test_failed_registry_replace_never_switches_active_version(versions, monkeypatch):
    live, stage, audit, _, _ = versions
    registry = live / "archive_registry.json"
    before = registry.read_bytes()
    old_replace = Path.replace

    def fail_registry_replace(self, target):
        if Path(target) == registry:
            raise OSError("simulated registry write failure")
        return old_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_registry_replace)
    with pytest.raises(OSError, match="simulated"):
        promote(stage, audit, live, key="expanded")
    assert registry.read_bytes() == before
    assert load_registered_analysis(live).registered_key == "cleaned-20261022"
    assert (live / "analysis/expanded/analysis.sqlite3").is_file()
    assert not (live / "archive_registry.lock").exists()


def test_staging_custom_metadata_preserves_integrity_fields_and_source_bytes(versions, tmp_path):
    _, stage, _, _, new_zip = versions
    repo = AnalysisRepository(stage / "analysis.sqlite3")
    assert repo.metadata["label"] == "Expanded Spotify collection"
    assert repo.metadata["activity_endpoint"] == "2026-10-21"
    assert repo.metadata["version_lineage"][0]["key"] == "cleaned-20261022"
    assert repo.original_zip() == new_zip.read_bytes()
    root = tmp_path / "combined"
    with pytest.raises(StorageError, match="integrity fields"):
        stage_analysis_package(root, new_zip, tmp_path / "unsafe", metadata={"baseline_status": "verified"})
    with pytest.raises(StorageError, match="different metadata"):
        stage_analysis_package(root, new_zip, stage, label="Relabeled old package")
    assert repo.metadata["label"] == "Expanded Spotify collection"


@pytest.mark.parametrize("style", ["meta", "instagram"])
def test_both_retained_semantic_acceptance_formats_bind_the_activation(versions, style):
    live, stage, audit, _, _ = versions
    write_acceptance(stage, audit, "expanded", live, style=style)
    promote(stage, audit, live, key="expanded")
    receipt = json.loads((live / "analysis/expanded/activation_receipt.json").read_text())
    assert receipt["database_sha256"] == hashlib.sha256((stage / "analysis.sqlite3").read_bytes()).hexdigest()
    assert receipt["independent_audit_sha256"] == hashlib.sha256(audit.read_bytes()).hexdigest()
    assert receipt["acceptance_schema"] in {"semantic-and-storage-acceptance", "scoped-semantic-acceptance"}


@pytest.mark.parametrize("overrides,remove", [
    ({"passed": False}, None), ({"passed": "true"}, None), ({"passed": 1}, None), ({}, "passed"),
    ({"candidate_database_sha256": "0" * 64}, None), ({"candidate_database_sha256": "invalid"}, None),
    ({}, "candidate_database_sha256"), ({"analysis_version": "different-key"}, None),
    ({"analysis_key": "contradictory-key"}, None), ({}, "analysis_version"),
    ({"status": "FAIL"}, None), ({"schema_version": 2}, None), ({"schema_version": True}, None),
    ({"audit_scope": "storage_integrity_only"}, None), ({"audit_scope": "unknown"}, None),
    ({"semantic_evidence_review_required": True}, None), ({"semantic_review_required": "false"}, None),
    ({"semantic_checks": {}}, None), ({"semantic_checks": {"source_claims_match": False}}, None),
    ({"storage_checks": {"all_candidate_table_rows_match_csv": True}}, None),
    ({"registry_unchanged_before_activation": False}, None),
    ({"supporting_receipts": {}}, None), ({"audited_at_utc": "2026-10-23T05:00:00"}, None),
    ({"all_prior_database_hashes": []}, None),
])
def test_invalid_acceptance_is_refused_before_destination_writes(versions, overrides, remove):
    live, stage, audit, _, _ = versions
    receipt = json.loads(audit.read_text())
    receipt.update(overrides)
    if remove:
        receipt.pop(remove)
    audit.write_text(json.dumps(receipt))
    before = {p: p.read_bytes() for p in live.rglob("*") if p.is_file()}
    with pytest.raises(StorageError):
        promote(stage, audit, live, key="expanded")
    assert {p: p.read_bytes() for p in live.rglob("*") if p.is_file()} == before
    assert not (live / "analysis/expanded").exists()


@pytest.mark.parametrize("raw", ["", "not json", "[]", "null", '{"passed":false,"passed":true}', '{"passed":NaN}'])
def test_invalid_json_audits_cannot_create_a_library(versions, tmp_path, raw):
    _, stage, audit, _, _ = versions
    audit.write_text(raw)
    absent_library = tmp_path / "absent-library"
    with pytest.raises(StorageError):
        promote(stage, audit, absent_library, key="expanded")
    assert not absent_library.exists()


def test_pass_and_candidate_hash_alone_are_not_semantic_acceptance(versions):
    live, stage, audit, _, _ = versions
    receipt = json.loads(audit.read_text())
    audit.write_text(json.dumps({field: receipt[field] for field in ("passed", "candidate_database_sha256")}))
    with pytest.raises(StorageError):
        promote(stage, audit, live, key="expanded")
    assert not (live / "analysis/expanded").exists()


@pytest.mark.parametrize("field,value", [
    ("approval_scope", ""), ("status", "FAIL"), ("summary", {}), ("normalization_receipt_sha256", "invalid"),
    ("supporting_receipts", [{"path": "../semantic_acceptance_audit.json", "sha256": "1" * 64},
                             {"path": "direct_sql_storage_audit.json", "sha256": "2" * 64}]),
    ("supporting_receipts", [{"path": "storage_only.json", "sha256": "1" * 64},
                             {"path": "direct_sql_storage_audit.json", "sha256": "2" * 64}]),
])
def test_scoped_acceptance_requires_semantic_provenance(versions, field, value):
    live, stage, audit, _, _ = versions
    receipt = write_acceptance(stage, audit, "expanded", live, style="instagram")
    receipt[field] = value
    audit.write_text(json.dumps(receipt))
    with pytest.raises(StorageError):
        promote(stage, audit, live, key="expanded")
    assert not (live / "analysis/expanded").exists()


def test_stale_prior_database_inventory_refused_before_copy(versions):
    live, stage, audit, _, _ = versions
    receipt = json.loads(audit.read_text())
    receipt["all_prior_database_hashes"]["stats.sqlite3"] = "0" * 64
    audit.write_text(json.dumps(receipt))
    before = (live / "archive_registry.json").read_bytes()
    with pytest.raises(StorageError, match="prior database inventory"):
        promote(stage, audit, live, key="expanded")
    assert (live / "archive_registry.json").read_bytes() == before
    assert not (live / "analysis/expanded").exists()
    assert not (live / "archive_registry.lock").exists()


def test_legacy_registered_replay_performs_no_writes_and_cannot_approve_new_key(versions, monkeypatch):
    live, stage, audit, _, _ = versions
    promote(stage, audit, live, key="expanded")
    # Model an earlier registered receipt lacking candidate-bound acceptance.
    audit.write_text('{"verified":true}')
    (live / "analysis/expanded/independent_analysis_audit.json").write_bytes(audit.read_bytes())
    before = {p: p.read_bytes() for p in live.rglob("*") if p.is_file()}
    original_open = Path.open

    def read_only_open(self, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in "wax+"), "Replay attempted a write"
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", read_only_open)
    assert promote(stage, audit, live, key="expanded")["idempotent"]
    with pytest.raises(StorageError, match="passed=true"):
        promote(stage, audit, live, key="new-key")
    assert {p: p.read_bytes() for p in live.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("change", ["database", "audit", "extra-file", "copied-database"])
def test_changed_copy_inputs_cannot_switch_the_active_registry(versions, monkeypatch, change):
    live, stage, audit, _, _ = versions
    before = {p: p.read_bytes() for p in live.rglob("*") if p.is_file()}
    original_copytree = promotion.shutil.copytree

    def changed_copytree(source, target, *args, **kwargs):
        result = original_copytree(source, target, *args, **kwargs)
        if Path(source) == stage:
            if change == "database":
                with (stage / "analysis.sqlite3").open("ab") as handle:
                    handle.write(b"changed after approval")
            elif change == "copied-database":
                with (Path(target) / "analysis.sqlite3").open("ab") as handle:
                    handle.write(b"changed copy")
            elif change == "audit":
                audit.write_text('{"passed":false}')
            else:
                (stage / "unexpected.txt").write_text("added during copy")
        return result

    monkeypatch.setattr(promotion.shutil, "copytree", changed_copytree)
    with pytest.raises(StorageError, match="changed|verification"):
        promote(stage, audit, live, key="expanded")
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert load_registered_analysis(live).registered_key == "cleaned-20261022"
    assert not (live / "archive_registry.lock").exists()


@pytest.mark.parametrize("moment", ["after-acceptance", "before-registry-replace"])
def test_audit_is_pinned_from_validation_through_registry_commit(versions, monkeypatch, moment):
    live, stage, audit, _, _ = versions
    before = (live / "archive_registry.json").read_bytes()
    if moment == "after-acceptance":
        original = promotion._acceptance

        def change_after_acceptance(*args, **kwargs):
            result = original(*args, **kwargs)
            audit.write_text('{"passed":false}')
            return result

        monkeypatch.setattr(promotion, "_acceptance", change_after_acceptance)
    else:
        original = promotion._registered_paths

        def change_before_commit(*args, **kwargs):
            result = original(*args, **kwargs)
            if (live / "analysis/expanded/activation_receipt.json").exists():
                audit.write_text('{"passed":false}')
            return result

        monkeypatch.setattr(promotion, "_registered_paths", change_before_commit)
    with pytest.raises(StorageError, match="changed"):
        promote(stage, audit, live, key="expanded")
    assert (live / "archive_registry.json").read_bytes() == before
    assert load_registered_analysis(live).registered_key == "cleaned-20261022"
    assert not (live / "archive_registry.lock").exists()


@pytest.fixture
def wal_library(versions):
    """Hold an isolated connection open so committed pages remain in its WAL."""
    live, stage, audit, _, _ = versions
    connection = sqlite3.connect(live / "stats.sqlite3")
    try:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE approval_wal_probe (value INTEGER)")
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        write_acceptance(stage, audit, "expanded", live)
        yield versions, connection
    finally:
        connection.close()


def commit_wal_change(live, connection):
    before_main = (live / "stats.sqlite3").read_bytes()
    connection.execute("INSERT INTO approval_wal_probe VALUES (1)")
    connection.commit()
    assert connection.execute("SELECT COUNT(*) FROM approval_wal_probe").fetchone()[0] > 0
    assert (live / "stats.sqlite3-wal").stat().st_size > 0
    assert (live / "stats.sqlite3").read_bytes() == before_main


@pytest.mark.parametrize("replay", [False, True])
def test_committed_wal_is_not_mistaken_for_an_unchanged_main_database(wal_library, replay):
    versions, connection = wal_library
    live, stage, audit, _, _ = versions
    if replay:
        promote(stage, audit, live, key="expanded")
    commit_wal_change(live, connection)
    before = {path: path.read_bytes() for path in live.rglob("*") if path.is_file()}
    with pytest.raises(StorageError, match="nonempty WAL or rollback journal"):
        promote(stage, audit, live, key="expanded")
    assert {path: path.read_bytes() for path in live.rglob("*") if path.is_file()} == before
    assert not (live / "archive_registry.lock").exists()


@pytest.mark.parametrize("moment", ["after-acceptance", "before-registry-replace", "during-replay"])
def test_concurrent_wal_commit_cannot_activate_or_claim_unchanged(wal_library, monkeypatch, moment):
    versions, connection = wal_library
    live, stage, audit, _, _ = versions
    if moment == "during-replay":
        promote(stage, audit, live, key="expanded")
    registry_before = (live / "archive_registry.json").read_bytes()
    if moment == "after-acceptance":
        original = promotion._acceptance

        def commit_after_acceptance(*args, **kwargs):
            result = original(*args, **kwargs)
            commit_wal_change(live, connection)
            return result

        monkeypatch.setattr(promotion, "_acceptance", commit_after_acceptance)
    else:
        original = promotion._verify_copy
        calls = 0

        def commit_after_copy_verification(*args, **kwargs):
            nonlocal calls
            result = original(*args, **kwargs)
            calls += 1
            if calls == (1 if moment == "during-replay" else 2):
                commit_wal_change(live, connection)
            return result

        monkeypatch.setattr(promotion, "_verify_copy", commit_after_copy_verification)
    with pytest.raises(StorageError, match="nonempty WAL or rollback journal"):
        promote(stage, audit, live, key="expanded")
    assert (live / "archive_registry.json").read_bytes() == registry_before
    if moment == "after-acceptance":
        assert not (live / "analysis/expanded").exists()
    assert not (live / "archive_registry.lock").exists()


def test_nonempty_rollback_journal_is_refused_without_touching_it(versions):
    live, stage, audit, _, _ = versions
    journal = live / "stats.sqlite3-journal"
    journal.write_bytes(b"isolated pending rollback-journal fixture")
    before = {path: path.read_bytes() for path in live.rglob("*") if path.is_file()}
    with pytest.raises(StorageError, match="nonempty WAL or rollback journal"):
        promote(stage, audit, live, key="expanded")
    assert {path: path.read_bytes() for path in live.rglob("*") if path.is_file()} == before
    assert not (live / "analysis/expanded").exists()


def test_new_writable_database_during_copy_changes_prior_inventory(versions, monkeypatch):
    live, stage, audit, _, _ = versions
    # Only the temporary fixture library is changed; model an analysis-only store.
    (live / "stats.sqlite3").unlink()
    write_acceptance(stage, audit, "expanded", live)
    registry_before = (live / "archive_registry.json").read_bytes()
    original = promotion.shutil.copytree

    def create_writable_during_copy(source, target, *args, **kwargs):
        result = original(source, target, *args, **kwargs)
        if Path(source) == stage:
            SQLiteRepository(live / "stats.sqlite3")
        return result

    monkeypatch.setattr(promotion.shutil, "copytree", create_writable_during_copy)
    with pytest.raises(StorageError, match="database inventory changed"):
        promote(stage, audit, live, key="expanded")
    assert (live / "archive_registry.json").read_bytes() == registry_before
    assert load_registered_analysis(live).registered_key == "cleaned-20261022"
    assert (live / "stats.sqlite3").is_file()
    assert not (live / "archive_registry.lock").exists()


@pytest.fixture
def versions_with_youtube(versions):
    """Two synthetic registered collections alongside the analysis library."""
    from stats_app.youtube_repository import COLLECTION_KEY, EXPECTED_SHA256, ZIP_FILENAME

    live, stage, audit, _, _ = versions
    records = []
    for key, filename in ((COLLECTION_KEY, ZIP_FILENAME), ("youtube-daily-20261023", "supplement.zip")):
        directory = live / "collections" / key
        SQLiteRepository(directory / "youtube.sqlite3")
        with zipfile.ZipFile(directory / filename, "w") as archive:
            archive.writestr("fixture.txt", key + " isolated fixture")
        record = {"key": key, "database": f"collections/{key}/youtube.sqlite3",
                  "evidence_root": f"collections/{key}", "zip_filename": filename,
                  "database_sha256": hashlib.sha256((directory / "youtube.sqlite3").read_bytes()).hexdigest(),
                  "zip_sha256": hashlib.sha256((directory / filename).read_bytes()).hexdigest()}
        if filename == "supplement.zip":
            record.update(collection_kind="daily_supplement", parent_collection_key=COLLECTION_KEY,
                          parent_zip_sha256=EXPECTED_SHA256)
        records.append(record)
    (live / "youtube_collections.json").write_text(json.dumps({"schema_version": 1, "collections": records}))
    write_acceptance(stage, audit, "expanded", live)
    return live, stage, audit, records


def test_activation_preserves_separately_registered_collection_inventory_and_read_only_replay(versions_with_youtube, monkeypatch):
    live, stage, audit, collections = versions_with_youtube
    collection_before = {p: p.read_bytes() for p in (live / "collections").rglob("*") if p.is_file()}
    registry_before = (live / "youtube_collections.json").read_bytes()
    accepted_inventory = json.loads(audit.read_text())["all_prior_database_hashes"]
    assert len(accepted_inventory) == 4  # writable, prior analysis, collection and supplement
    promote(stage, audit, live, key="expanded")
    activation = json.loads((live / "analysis/expanded/activation_receipt.json").read_text())
    assert activation["earlier_database_hashes"] == accepted_inventory
    assert activation["youtube_collections_verified"] == 2
    assert activation["youtube_registry_sha256"] == hashlib.sha256(registry_before).hexdigest()
    assert {item["database"] for item in collections}.issubset(activation["earlier_database_hashes"])
    assert (live / "youtube_collections.json").read_bytes() == registry_before
    assert all(path.read_bytes() == raw for path, raw in collection_before.items())
    assert not (live / ".youtube_import.lock").exists()
    original_open = Path.open

    def read_only_open(self, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in "wax+"), "Replay attempted a write"
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", read_only_open)
    assert promote(stage, audit, live, key="expanded")["idempotent"]
    assert (live / "youtube_collections.json").read_bytes() == registry_before


@pytest.mark.parametrize("field", ["database_sha256", "zip_sha256"])
def test_stale_registered_collection_hash_is_refused_before_copy(versions_with_youtube, field):
    live, stage, audit, _ = versions_with_youtube
    collection_registry = live / "youtube_collections.json"
    registration = json.loads(collection_registry.read_text())
    registration["collections"][0][field] = "0" * 64
    collection_registry.write_text(json.dumps(registration))
    before = {p: p.read_bytes() for p in live.rglob("*") if p.is_file()}
    with pytest.raises(StorageError, match="YouTube database or ZIP failed SHA-256"):
        promote(stage, audit, live, key="expanded")
    assert {p: p.read_bytes() for p in live.rglob("*") if p.is_file()} == before
    assert not (live / "analysis/expanded").exists()
    assert not (live / "archive_registry.lock").exists()
    assert not (live / ".youtube_import.lock").exists()


def test_acceptance_cannot_drop_a_separately_registered_collection_database(versions_with_youtube):
    live, stage, audit, collections = versions_with_youtube
    receipt = json.loads(audit.read_text())
    receipt["all_prior_database_hashes"].pop(collections[0]["database"])
    audit.write_text(json.dumps(receipt))
    registry_before = (live / "archive_registry.json").read_bytes()
    with pytest.raises(StorageError, match="prior database inventory"):
        promote(stage, audit, live, key="expanded")
    assert (live / "archive_registry.json").read_bytes() == registry_before
    assert not (live / "analysis/expanded").exists()
    assert not (live / "archive_registry.lock").exists()
    assert not (live / ".youtube_import.lock").exists()


@pytest.mark.parametrize("moment", ["after-acceptance", "during-copy", "before-registry-replace", "during-replay"])
def test_concurrent_collection_registry_changes_cannot_switch_analysis(versions_with_youtube, monkeypatch, moment):
    live, stage, audit, _ = versions_with_youtube
    if moment == "during-replay":
        promote(stage, audit, live, key="expanded")
    analysis_registry = live / "archive_registry.json"
    collection_registry = live / "youtube_collections.json"
    before = analysis_registry.read_bytes()

    def change_collection_registry():
        # Whitespace alone still changes the pinned bytes and invalidates the
        # source snapshot; simulate an external concurrent writer.
        collection_registry.write_bytes(collection_registry.read_bytes() + b"\n")

    if moment == "after-acceptance":
        original = promotion._acceptance

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            change_collection_registry()
            return result

        monkeypatch.setattr(promotion, "_acceptance", changed)
    elif moment == "during-copy":
        original = promotion.shutil.copytree

        def changed(source, target, *args, **kwargs):
            result = original(source, target, *args, **kwargs)
            if Path(source) == stage:
                change_collection_registry()
            return result

        monkeypatch.setattr(promotion.shutil, "copytree", changed)
    elif moment == "before-registry-replace":
        original = promotion._registered_paths

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            if (live / "analysis/expanded/activation_receipt.json").exists():
                change_collection_registry()
            return result

        monkeypatch.setattr(promotion, "_registered_paths", changed)
    else:
        original = promotion._verify_copy

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            change_collection_registry()
            return result

        monkeypatch.setattr(promotion, "_verify_copy", changed)
    with pytest.raises(StorageError, match="collection registry changed"):
        promote(stage, audit, live, key="expanded")
    assert analysis_registry.read_bytes() == before
    if moment == "after-acceptance":
        assert not (live / "analysis/expanded").exists()
    assert not (live / "archive_registry.lock").exists()
    assert not (live / ".youtube_import.lock").exists()


def test_active_collection_import_prevents_new_analysis_promotion_before_copy(versions_with_youtube):
    from stats_app.youtube_repository import _import_lock

    live, stage, audit, _ = versions_with_youtube
    registry_before = (live / "archive_registry.json").read_bytes()
    with _import_lock(live):
        with pytest.raises(StorageError, match="Another YouTube import is active"):
            promote(stage, audit, live, key="expanded")
        assert (live / ".youtube_import.lock").exists()
        assert not (live / "archive_registry.lock").exists()
        assert not (live / "analysis/expanded").exists()
        assert (live / "archive_registry.json").read_bytes() == registry_before
    assert not (live / ".youtube_import.lock").exists()
