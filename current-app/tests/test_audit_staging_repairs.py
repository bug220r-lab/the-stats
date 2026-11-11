"""Staging requires a complete, unambiguous archive and explicit provenance."""
import hashlib
import json
from pathlib import Path
import stat
import warnings
import zipfile

import pytest

from stats_app.analysis_repository import AnalysisRepository, stage_analysis_package
from stats_app.storage import StorageError


def package(tmp_path, *, prefixed=True, directories=False):
    root = tmp_path / "analysis_package"
    files = {
        "raw/source.csv": b"date,streams\n2026-10-24,7\n",
        "spotify/cleaned/artist_daily.csv": b"date,daily_streams\n2026-10-24,7\n",
        "social/posts_latest.csv": b"post_id,views\n00123,0\n",
        "audit/final_validation.json": b'{"checks":{"raw_source_files_unchanged":true}}',
    }
    raw = files["raw/source.csv"]
    files["raw_sha256.json"] = json.dumps([
        {"path": "raw/source.csv", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    ]).encode()
    archive = tmp_path / "package.zip"
    prefix = root.name + "/" if prefixed else ""
    with zipfile.ZipFile(archive, "w") as zipped:
        if directories:
            for directory in ("raw/", "spotify/", "spotify/cleaned/", "social/", "audit/", "empty/"):
                zipped.writestr(prefix + directory, b"")
            if prefix:
                zipped.writestr(prefix, b"")
        for name, contents in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
            zipped.writestr(prefix + name, contents)
    return root, archive, files


@pytest.mark.parametrize("prefixed", [True, False])
@pytest.mark.parametrize("directories", [True, False])
def test_complete_archive_keeps_exact_bytes_in_both_supported_layouts(tmp_path, prefixed, directories):
    root, archive, files = package(tmp_path, prefixed=prefixed, directories=directories)
    zip_before = archive.read_bytes()
    staged = stage_analysis_package(root, archive, tmp_path / "stage")
    repository = AnalysisRepository(staged["database"])
    assert set(repository.file_catalog().path) == set(files)
    assert staged["all_package_files_match_zip"] is True
    assert repository.original_zip() == zip_before == archive.read_bytes()
    for name, contents in files.items():
        assert repository.original_bytes(name) == contents == (root / name).read_bytes()


def test_omitted_nonraw_table_is_rejected_before_output_creation(tmp_path):
    root, archive, _ = package(tmp_path)
    (root / "social/posts_latest.csv").unlink()
    output = tmp_path / "stage"
    with pytest.raises(StorageError, match="missing: social/posts_latest.csv"):
        stage_analysis_package(root, archive, output)
    assert not output.exists()


def test_extra_extracted_table_is_rejected_before_output_creation(tmp_path):
    root, archive, _ = package(tmp_path)
    (root / "extra.csv").write_text("value\n7\n", encoding="utf-8")
    output = tmp_path / "stage"
    with pytest.raises(StorageError, match="extra: extra.csv"):
        stage_analysis_package(root, archive, output)
    assert not output.exists()


@pytest.mark.parametrize("contents", [b"post_id,views\n00123,0\n", b"conflicting bytes"])
def test_duplicate_zip_file_members_are_rejected_even_when_identical(tmp_path, contents):
    root, archive, _ = package(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(archive, "a") as zipped:
            zipped.writestr(root.name + "/social/posts_latest.csv", contents)
    with pytest.raises(StorageError, match="Duplicate or ambiguous"):
        stage_analysis_package(root, archive, tmp_path / "stage")
    assert not (tmp_path / "stage").exists()


@pytest.mark.parametrize("name", [
    "../outside.csv", "/absolute.csv", "C:/absolute.csv", "C:relative.csv", "raw\\source.csv",
    "raw/../source.csv", "raw/./source.csv", "raw//source.csv", "raw/stream.csv:payload",
    "raw/name. ", "raw/CON.csv", "raw/NUL", "raw/lpt1.txt", "./",
])
def test_unsafe_zip_members_are_not_hidden_by_a_valid_package_prefix(tmp_path, name):
    root, archive, _ = package(tmp_path)
    member = zipfile.ZipInfo()
    # Assign after construction: ZipInfo normalizes Windows backslashes when
    # constructing a new member, unlike an untrusted ZIP's literal name bytes.
    member.filename = member.orig_filename = name
    with zipfile.ZipFile(archive, "a") as zipped:
        zipped.writestr(member, b"")
    with pytest.raises(StorageError, match="Unsafe|relative forward-slash"):
        stage_analysis_package(root, archive, tmp_path / "stage")
    assert not (tmp_path / "stage").exists()


@pytest.mark.parametrize("name", ["analysis_package/Social/posts_latest.csv", "analysis_package/social/POSTS_LATEST.csv"])
def test_case_ambiguous_members_or_parent_directories_are_rejected(tmp_path, name):
    root, archive, _ = package(tmp_path)
    with zipfile.ZipFile(archive, "a") as zipped:
        zipped.writestr(name, b"other")
    with pytest.raises(StorageError, match="Case-ambiguous"):
        stage_analysis_package(root, archive, tmp_path / "stage")


@pytest.mark.parametrize("kind", [stat.S_IFLNK, stat.S_IFIFO])
def test_zip_link_and_special_file_members_are_rejected(tmp_path, kind):
    root, archive, _ = package(tmp_path)
    member = zipfile.ZipInfo(root.name + "/untrusted")
    member.create_system = 3
    member.external_attr = (kind | 0o777) << 16
    with zipfile.ZipFile(archive, "a") as zipped:
        zipped.writestr(member, b"raw/source.csv")
    with pytest.raises(StorageError, match="Unsafe file type"):
        stage_analysis_package(root, archive, tmp_path / "stage")


def test_file_and_implicit_directory_conflict_is_rejected(tmp_path):
    root, archive, _ = package(tmp_path)
    with zipfile.ZipFile(archive, "a") as zipped:
        zipped.writestr(root.name + "/folder", b"file")
        zipped.writestr(root.name + "/folder/nested/", b"")
    with pytest.raises(StorageError, match="Conflicting file and directory"):
        stage_analysis_package(root, archive, tmp_path / "stage")


def test_duplicate_directory_members_are_rejected(tmp_path):
    root, archive, _ = package(tmp_path, directories=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(archive, "a") as zipped:
            zipped.writestr(root.name + "/empty/", b"")
    with pytest.raises(StorageError, match="Duplicate or ambiguous"):
        stage_analysis_package(root, archive, tmp_path / "stage")


def test_directory_members_cannot_hide_file_payloads(tmp_path):
    root, archive, _ = package(tmp_path)
    with zipfile.ZipFile(archive, "a") as zipped:
        zipped.writestr(root.name + "/hidden.csv/", b"value\n123\n")
    with pytest.raises(StorageError, match="directory members must not contain file payloads"):
        stage_analysis_package(root, archive, tmp_path / "stage")


@pytest.mark.parametrize("outside", ["social/posts_latest.csv", "unrelated/readme.txt"])
def test_mixed_flat_and_prefixed_layouts_are_rejected(tmp_path, outside):
    root, archive, _ = package(tmp_path)
    with zipfile.ZipFile(archive, "a") as zipped:
        zipped.writestr(outside, b"must not be silently omitted")
    with pytest.raises(StorageError, match="one unambiguous package-root layout"):
        stage_analysis_package(root, archive, tmp_path / "stage")


def test_generic_stage_does_not_infer_dates_from_label_or_source_rows(tmp_path):
    root, archive, _ = package(tmp_path)
    staged = stage_analysis_package(root, archive, tmp_path / "stage", label="New October 24 collection")
    assert staged["label"] == "New October 24 collection"
    assert staged["activity_endpoint"] is None
    assert staged["retrieval_vintage"] is None
    assert staged["baseline_status"] == "unverified"
    assert AnalysisRepository(staged["database"]).metadata["activity_endpoint"] is None


def test_default_stage_label_is_neutral(tmp_path):
    root, archive, _ = package(tmp_path)
    staged = stage_analysis_package(root, archive, tmp_path / "stage")
    assert staged["label"] == "Cleaned analysis"
    assert staged["activity_endpoint"] is None and staged["retrieval_vintage"] is None


def test_explicit_provenance_and_existing_snapshot_replay_are_preserved(tmp_path):
    root, archive, _ = package(tmp_path)
    metadata = {"activity_endpoint": "2026-10-24", "retrieval_vintage": "2026-10-25", "analysis_version": "explicit-new", "version_lineage": [{"key": "prior"}]}
    output = tmp_path / "stage"
    original = stage_analysis_package(root, archive, output, label="Explicit source label", metadata=metadata)
    before = Path(original["database"]).read_bytes()
    replay = stage_analysis_package(root, archive, output)
    assert replay["idempotent"] is True
    assert all(replay[key] == value for key, value in metadata.items())
    assert replay["label"] == "Explicit source label"
    assert Path(original["database"]).read_bytes() == before
    with pytest.raises(StorageError, match="different metadata"):
        stage_analysis_package(root, archive, output, metadata={"activity_endpoint": "2026-10-26"})
    assert Path(original["database"]).read_bytes() == before
