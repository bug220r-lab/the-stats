"""Collection-readiness checks use synthetic identities and isolated storage."""
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.manage_tiktok_collection import main
import scripts.manage_tiktok_collection as collection_cli
import stats_app.config as app_config
from stats_app.tiktok_collection import create_collection, assess_collection, list_collections, QUEUE_COLUMNS


PROFILE = "https://www.tiktok.com/@synthetic_fixture"


@pytest.fixture
def collection(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "protected-local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "protected-roaming"))
    monkeypatch.setenv("STATS_DATA_DIR", str(tmp_path / "protected-library"))
    path = tmp_path / "collections" / "fixture"
    create_collection(path, profile_url=PROFILE)
    return path


def rewrite_queue(path, modify):
    with (path / "collection_queue.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    modify(rows)
    with (path / "collection_queue.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=QUEUE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_initial_workspace_is_honest_and_templates_preserve_source_contracts(collection):
    result = assess_collection(collection)
    assert result["profile_url"] == PROFILE and result["handle"] == "@synthetic_fixture"
    assert result["status"] == "preparation_only" and result["issues"] == []
    assert result["identity_status"] == "user_supplied_unverified"
    assert result["raw_file_count"] == result["evidence_file_count"] == 0
    assert not result["integration_ready"] and not result["library_modified"]
    assert len(result["queue"]) == 7 and {row["status"] for row in result["queue"]} == {"not_collected"}
    assert result["snapshot_target_ages_hours"] == [24, 72, 168, 672]
    for name in ("post_log.csv", "snapshot_schedule.csv", "config/sound_recording_crosswalk.csv"):
        with (collection / name).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames and list(reader) == []
    source = Path(__file__).resolve().parents[1] / "templates"
    assert (collection / "config/video_snapshot.mapping.json").read_bytes() == (source / "tiktok.video_snapshot.mapping.template.json").read_bytes()
    song = json.loads((collection / "config/song_daily.metadata.json").read_text())
    assert (song["source_family"], song["entity_type"], song["content_scope"]) == ("artists_csv", "song", "all_creators")
    assert song["entity_id"] == "" and song["captured_at"] == "" and song["source_timezone"] == "unknown"


def test_no_overwrite_and_protected_library_paths(collection, tmp_path):
    before = (collection / "collection.json").read_bytes()
    with pytest.raises(FileExistsError):
        create_collection(collection, profile_url=PROFILE)
    assert (collection / "collection.json").read_bytes() == before
    for name in ("protected-local", "protected-roaming", "protected-library"):
        destination = tmp_path / name / "new"
        with pytest.raises(ValueError, match="outside AppData"):
            create_collection(destination, profile_url=PROFILE)
        assert not destination.exists()


@pytest.mark.parametrize("profile", ["http://www.tiktok.com/@fixture", "https://evil.test/@fixture",
    "https://www.tiktok.com.evil.test/@fixture", "https://www.tiktok.com/@fixture/video/1",
    "https://www.tiktok.com/@fixture?x=1", "https://user@www.tiktok.com/@fixture", "https://www.tiktok.com:443/@fixture",
    "https://www.tiktok.com/@fixture#x", "https://www.tiktok.com/@", " https://www.tiktok.com/@fixture"])
def test_invalid_profile_never_creates_folder(tmp_path, profile):
    path = tmp_path / "invalid"
    with pytest.raises(ValueError):
        create_collection(path, profile_url=profile)
    assert not path.exists()


def test_invalid_date_never_creates_folder(tmp_path):
    with pytest.raises(ValueError):
        create_collection(tmp_path / "invalid", profile_url=PROFILE, prepared_on="2026-02-30")
    assert not (tmp_path / "invalid").exists()


def test_hash_inventory_and_read_only_status_do_not_certify_native_data(collection):
    payload = b"Synthetic source bytes\x00\xff\r\n"
    (collection / "raw" / "fixture.bin").write_bytes(payload)
    (collection / "evidence" / "identity.txt").write_text("Synthetic evidence", encoding="utf-8")
    rewrite_queue(collection, lambda rows: rows[0].update(status="collected", evidence_ref="evidence/identity.txt"))
    before = {path.relative_to(collection).as_posix(): path.read_bytes() for path in collection.rglob("*") if path.is_file()}
    result = assess_collection(collection)
    after = {path.relative_to(collection).as_posix(): path.read_bytes() for path in collection.rglob("*") if path.is_file()}
    assert before == after
    assert result["raw_file_count"] == result["evidence_file_count"] == 1
    raw = next(item for item in result["inventory"] if item["category"] == "raw")
    assert raw["sha256"] == hashlib.sha256(payload).hexdigest() and raw["bytes"] == len(payload)
    assert result["status"] == "collection_in_progress" and result["issues"] == []
    assert not result["integration_ready"] and result["identity_status"] == "user_supplied_unverified"


@pytest.mark.parametrize("reference", ["../outside.txt", "raw/missing.csv", "/outside.txt", "evidence", ""])
def test_completion_needs_real_contained_evidence(collection, reference):
    rewrite_queue(collection, lambda rows: rows[0].update(status="collected", evidence_ref=reference))
    result = assess_collection(collection)
    assert result["status"] == "needs_review"
    assert any(issue["code"] in {"invalid_evidence_reference", "evidence_required"} for issue in result["issues"])
    assert not result["integration_ready"]


@pytest.mark.parametrize("status", ["", "done", "not_applicable"])
def test_invalid_or_inapplicable_required_status_is_rejected(collection, status):
    rewrite_queue(collection, lambda rows: rows[0].update(status=status))
    assert assess_collection(collection)["status"] == "needs_review"


def test_missing_queue_rows_and_empty_claims_remain_visible(collection):
    rewrite_queue(collection, lambda rows: rows.pop())
    assert any(issue["code"] == "queue_items_missing" for issue in assess_collection(collection)["issues"])


@pytest.mark.parametrize("status", ["blocked", "unavailable", "not_applicable"])
def test_unavailable_optional_outcomes_need_explanation(collection, status):
    rewrite_queue(collection, lambda rows: rows[3].update(status=status, notes=""))
    result = assess_collection(collection)
    assert any(issue["code"] == "outcome_explanation_missing" for issue in result["issues"])
    assert not result["integration_ready"]


def test_configuration_is_not_sufficient_native_evidence(collection):
    rewrite_queue(collection, lambda rows: rows[0].update(status="collected", evidence_ref="config/account_daily.metadata.json"))
    result = assess_collection(collection)
    assert any(issue["code"] == "non_source_evidence" for issue in result["issues"])
    assert not result["integration_ready"] and result["raw_file_count"] == 0


def test_manifest_cannot_claim_identity_verification_or_activation(collection):
    path = collection / "collection.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update(identity_status="verified", status="active", integration_ready=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = assess_collection(collection)
    assert result["status"] == "needs_review" and not result["integration_ready"]
    assert result["identity_status"] == "user_supplied_unverified"
    assert {issue["code"] for issue in result["issues"]} >= {"identity_review_required", "activation_not_supported"}


def test_list_only_matching_direct_collections(collection):
    root = collection.parent
    unrelated = root / "unrelated"
    unrelated.mkdir()
    (unrelated / "collection.json").write_text('{"collection_type":"shopify"}', encoding="utf-8")
    create_collection(unrelated / "nested-tiktok", profile_url=PROFILE)
    listed = list_collections(root)
    assert len(listed) == 1 and listed[0]["path"] == str(collection.resolve())
    assert list_collections(root / "absent") == []


def test_cli_status_receipt_is_exclusive_and_does_not_change_package(collection, tmp_path, capsys):
    receipt = tmp_path / "status.json"
    assert main(["status", "--collection", str(collection), "--output", str(receipt)]) == 0
    before = receipt.read_bytes()
    assert json.loads(before)["status"] == "preparation_only"
    assert main(["status", "--collection", str(collection), "--output", str(receipt)]) == 2
    assert receipt.read_bytes() == before and "already exists" in capsys.readouterr().err


def test_cli_status_receipt_refuses_live_library_destination(collection, tmp_path, capsys):
    destination = tmp_path / "protected-library" / "receipt.json"
    assert main(["status", "--collection", str(collection), "--output", str(destination)]) == 2
    assert not destination.exists() and "outside AppData" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["init", "status"])
def test_relative_live_library_uses_project_root_from_foreign_cwd(collection, tmp_path, monkeypatch, capsys, command):
    project = tmp_path / "isolated-project"
    project.mkdir()
    foreign = tmp_path / "foreign-working-directory"
    foreign.mkdir()
    monkeypatch.setattr(app_config, "PROJECT_ROOT", project)
    monkeypatch.setenv("STATS_DATA_DIR", "relative-live-library")
    monkeypatch.chdir(foreign)
    live = app_config.load_settings().data_dir
    assert live == project / "relative-live-library"
    output = live / ("forbidden-collection" if command == "init" else "forbidden-receipt.json")
    args = ["init", "--output", str(output), "--profile-url", PROFILE] if command == "init" else ["status", "--collection", str(collection), "--output", str(output)]
    assert main(args) == 2
    assert "outside AppData" in capsys.readouterr().err
    assert not output.exists() and not live.exists()


def test_non_utf8_console_can_report_success_after_creation(collection, tmp_path, monkeypatch):
    output = tmp_path / "fixture_\u2122\ufe0f_\u97f3"
    raw_console = io.BytesIO()
    console = io.TextIOWrapper(raw_console, encoding="cp1252", errors="strict")
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", console)
        assert main(["init", "--output", str(output), "--profile-url", PROFILE]) == 0
        console.flush()
    result = json.loads(raw_console.getvalue().decode("ascii"))
    assert result["path"] == str(output.resolve()) and (output / "collection.json").is_file()


def test_non_utf8_console_can_report_unicode_error(collection, tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("Synthetic error \u2122\ufe0f \u97f3")
    raw_console = io.BytesIO()
    console = io.TextIOWrapper(raw_console, encoding="cp1252", errors="strict")
    with monkeypatch.context() as patch:
        patch.setattr(collection_cli, "create_collection", fail)
        patch.setattr(sys, "stderr", console)
        assert main(["init", "--output", str(tmp_path / "unused"), "--profile-url", PROFILE]) == 2
        console.flush()
    result = json.loads(raw_console.getvalue().decode("ascii"))
    assert result["error"] == "Synthetic error \u2122\ufe0f \u97f3" and result["library_modified"] is False


def test_real_cli_runs_from_foreign_directory(collection, tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/manage_tiktok_collection.py"
    destination = tmp_path / "cli-collection"
    result = subprocess.run([sys.executable, "-X", "utf8", str(script), "init", "--output", str(destination),
                             "--profile-url", PROFILE, "--prepared-on", "2026-10-26"],
                            cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "preparation_only"
    assert json.loads(result.stdout)["integration_ready"] is False
