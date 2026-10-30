"""Studio import preserves source strings, isolates versions and rejects damage."""
import json

import pandas as pd
import pytest

from tiktok_studio_fixtures import seal, studio_package
from stats_app.storage import StorageError
from stats_app.tiktok_repository import (
    REGISTRY_FILENAME, TikTokRepository, import_tiktok_collection, load_registered_tiktok,
    list_registered_tiktok,
)


def test_exact_originals_missingness_provenance_and_isolation(tmp_path):
    package = studio_package(tmp_path)
    library = tmp_path / "library"
    library.mkdir()
    unrelated = {"stats.sqlite3": b"existing", "archive_registry.json": b"original analysis pointer",
                 "shopify_collections.json": b"separate shopify"}
    for name, raw in unrelated.items():
        (library / name).write_bytes(raw)
    original = {p.relative_to(package).as_posix(): p.read_bytes() for p in package.rglob("*") if p.is_file()}
    receipt = import_tiktok_collection(package, library)
    assert not receipt["idempotent"] and receipt["integrity"] == "ok"
    repo = load_registered_tiktok(library)
    assert repo.metadata["artists_status"] == "pending"
    assert repo.metadata["baseline_status"] == "separate_retrospective_collection_not_original_baseline"
    daily = repo.table("account_daily")
    assert daily.comments.tolist() == ["-3", "0"]
    assert daily.viewer_total.tolist() == ["", "undefined"]
    assert repo.table("posts").post_id.tolist() == ["001", "002"]
    assert repo.table("empty").empty
    with pytest.raises(StorageError, match="no collected table"):
        repo.table("artists")
    lineage = repo.row_provenance("account_daily")
    assert lineage.csv_record.tolist() == [2, 3]
    assert lineage.source_reference.tolist() == ["raw/native.txt", "raw/native.txt"]
    assert lineage.stable_row_key.nunique() == 2
    for name, raw in original.items():
        assert repo.source_bytes(name) == raw == (package / name).read_bytes()
    for name, raw in unrelated.items():
        assert (library / name).read_bytes() == raw
    altered = repo.metadata
    altered["account"] = "changed"
    assert repo.metadata["account"] == "@synthetic"
    assert len(list_registered_tiktok(library)) == 1


def test_replay_is_read_only_and_same_key_changed_package_rejected(tmp_path):
    package = studio_package(tmp_path)
    library = tmp_path / "library"
    import_tiktok_collection(package, library)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in library.rglob("*") if p.is_file()}
    assert import_tiktok_collection(package, library)["idempotent"]
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in library.rglob("*") if p.is_file()}
    manifest = json.loads((package / "manifest.json").read_text())
    (package / "raw/native.txt").write_bytes(b"changed original")
    seal(package, manifest)
    with pytest.raises(StorageError, match="different source bytes"):
        import_tiktok_collection(package, library)
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in library.rglob("*") if p.is_file()}


@pytest.mark.parametrize("mutation,match", [
    (lambda m: m.update(collected_at="2026-10-27T03:00:00"), "UTC offset"),
    (lambda m: m.update(account=""), "identity"),
    (lambda m: m["datasets"][0].update(row_count=99), "row count"),
    (lambda m: m["datasets"][0].update(status="unknown"), "status"),
    (lambda m: m["datasets"][0].update(primary_key=["absent"]), "primary-key"),
    (lambda m: m["datasets"][0].update(primary_key=[["date"]]), "primary-key"),
    (lambda m: m["datasets"][0].update(source_paths=["../outside"]), "Unsafe"),
    (lambda m: m["datasets"][0].update(source_paths="raw/native.txt"), "source_paths"),
    (lambda m: m["datasets"][0].update(status="verified_empty"), "contains rows"),
    (lambda m: m["datasets"][0].update(path="../outside.csv"), "Unsafe"),
    (lambda m: m["datasets"].append(dict(m["datasets"][0])), "duplicate"),
    (lambda m: m["assets"][0].update(path="../outside"), "Unsafe"),
    (lambda m: m["assets"].append(dict(m["assets"][0])), "duplicate"),
])
def test_manifest_failures_rejected_before_library_creation(tmp_path, mutation, match):
    package = studio_package(tmp_path)
    path = package / "manifest.json"
    manifest = json.loads(path.read_text())
    mutation(manifest)
    path.write_text(json.dumps(manifest))
    with pytest.raises(StorageError, match=match):
        import_tiktok_collection(package, tmp_path / "library")
    assert not (tmp_path / "library").exists()


@pytest.mark.parametrize("rows,match", [
    (b"post_id,caption,views_raw\n001,a,1\n001,b,2\n", "Duplicate TikTok primary key"),
    (b"post_id,caption,views_raw\n,a,1\n002,b,2\n", "Blank TikTok primary key"),
    (b"post_id,caption, caption \n001,a,1\n002,b,2\n", "Duplicate TikTok table headers"),
    (b"post_id,caption,views_raw\n001,a\n002,b,2\n", "wrong field count"),
])
def test_table_grain_and_structure_are_validated(tmp_path, rows, match):
    package = studio_package(tmp_path)
    manifest = json.loads((package / "manifest.json").read_text())
    (package / "tables/posts.csv").write_bytes(rows)
    seal(package, manifest)
    with pytest.raises(StorageError, match=match):
        TikTokRepository(package)


@pytest.mark.parametrize("kind", ["changed", "extra", "missing", "manifest", "escape"])
def test_registered_package_damage_is_detected(tmp_path, kind):
    library = tmp_path / "library"
    import_tiktok_collection(studio_package(tmp_path), library)
    package = library / "collections/tiktok-20261027-studio/package"
    if kind == "changed":
        (package / "raw/native.txt").write_bytes(b"changed")
    elif kind == "extra":
        (package / "surprise.txt").write_bytes(b"extra")
    elif kind == "missing":
        (package / "raw/native.txt").unlink()
    elif kind == "manifest":
        (package / "manifest.json").write_bytes(b"{}")
    else:
        registry = json.loads((library / REGISTRY_FILENAME).read_text())
        registry["collections"][0]["package_dir"] = "../outside"
        (library / REGISTRY_FILENAME).write_text(json.dumps(registry))
    with pytest.raises(StorageError):
        load_registered_tiktok(library, verify_all=True)


def test_lazy_loading_requires_external_pins_and_does_not_walk_files(tmp_path, monkeypatch):
    import stats_app.tiktok_repository as module
    package = studio_package(tmp_path)
    with pytest.raises(StorageError, match="externally pinned"):
        TikTokRepository(package, verify_all=False)
    library = tmp_path / "library"
    import_tiktok_collection(package, library)
    def unexpected(*args, **kwargs):
        raise AssertionError("Registered lazy loading must not scan the package namespace")
    monkeypatch.setattr(module, "_package_files", unexpected)
    repo = load_registered_tiktok(library)
    assert len(repo.table("account_daily")) == 2
    assert repo.source_bytes("raw/native.txt").startswith(b"Original")


def test_lazy_assets_rechecked_on_read_without_stale_cache(tmp_path):
    library = tmp_path / "library"
    import_tiktok_collection(studio_package(tmp_path), library)
    repo = load_registered_tiktok(library)
    assert len(repo.table("posts")) == 2
    (repo.package_dir / "tables/posts.csv").write_bytes(b"changed after first display")
    # Metadata is externally pinned; a later read may not reuse prior table data.
    reloaded = load_registered_tiktok(library)
    for current in (repo, reloaded):
        with pytest.raises(StorageError, match="SHA-256"):
            current.table("posts")
        assert len(current.table("account_daily")) == 2
    with pytest.raises(StorageError, match="SHA-256"):
        load_registered_tiktok(library, verify_all=True)


def test_lazy_unused_asset_damage_still_fails_explicit_read_and_full_validation(tmp_path):
    library = tmp_path / "library"
    import_tiktok_collection(studio_package(tmp_path), library)
    repo = load_registered_tiktok(library)
    (repo.package_dir / "raw/native.txt").write_bytes(b"damaged unused original")
    reloaded = load_registered_tiktok(library)
    assert len(reloaded.table("posts")) == 2
    with pytest.raises(StorageError, match="SHA-256"):
        reloaded.source_bytes("raw/native.txt")
    with pytest.raises(StorageError, match="SHA-256"):
        load_registered_tiktok(library, verify_all=True)


def test_empty_registry_and_unknown_collection(tmp_path):
    assert list_registered_tiktok(tmp_path / "absent") == []
    assert load_registered_tiktok(tmp_path / "absent") is None
    library = tmp_path / "library"
    import_tiktok_collection(studio_package(tmp_path), library)
    with pytest.raises(StorageError, match="Unknown TikTok collection"):
        load_registered_tiktok(library, "tiktok-20261028-studio")


def test_relocation_preserves_table_provenance(tmp_path):
    library = tmp_path / "library"
    import_tiktok_collection(studio_package(tmp_path), library)
    original = load_registered_tiktok(library)
    frames = {name: original.table(name) for name in original.tables}
    provenance = {name: original.row_provenance(name) for name in original.tables}
    library.rename(tmp_path / "relocated")
    moved = load_registered_tiktok(tmp_path / "relocated")
    for name in moved.tables:
        pd.testing.assert_frame_equal(frames[name], moved.table(name))
        pd.testing.assert_frame_equal(provenance[name], moved.row_provenance(name))
