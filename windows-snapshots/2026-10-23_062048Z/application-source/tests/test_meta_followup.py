"""Follow-up evidence cannot rewrite preceding Meta and Spotify snapshots."""
import hashlib
import json
from pathlib import Path
import zipfile

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from stats_app.analysis_repository import AnalysisRepository, stage_analysis_package
from stats_app.meta_followup import PREFIX, RAW_PREFIX, PREDECESSOR_PREFIX, build_meta_followup
from stats_app.storage import StorageError
from scripts.audit_meta_followup_storage import audit


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path / "parent-package"
    raw = b"post_id,caption\n001,unchanged\n"
    files = {
        "raw/old.csv": raw,
        "raw/meta_collection/raw/proof.txt": b"Old captured proof",
        "raw/meta_predecessor_metadata/metadata.json": b'{"analysis_version":"spotify-recovery-20261023"}',
        "social/meta_collection/mapping/post_song_references.csv": b"post_id,song_id,status\n001,,unknown\n",
        "social/meta_collection/collection_status.csv": b"dataset,status,detail,evidence_ref,captured_at_utc\nold,retained,Prior collection,raw/old.csv,2026-10-23T00:00:00Z\n",
        "social/account_daily.csv": b"date,value,value_status\n2026-10-20,,missing\n",
        "spotify/cleaned/track_daily_long.csv": b"song_id,date,value\n001,2026-10-20,3\n",
        "statistical_results.csv": b"analysis_id,status\nprior,no_significance\n",
        "metadata.json": b'{"analysis_version":"meta-collection-20261023"}',
        "audit/final_validation.json": b'{"old_check":true}',
        "raw_sha256.json": json.dumps([{"path": "raw/old.csv", "bytes": len(raw), "sha256": digest(raw)},
              {"path": "raw/meta_collection/raw/proof.txt", "bytes": 18, "sha256": digest(b"Old captured proof")},
              {"path": "raw/meta_predecessor_metadata/metadata.json", "bytes": 47,
               "sha256": digest(b'{"analysis_version":"spotify-recovery-20261023"}')}]).encode(),
    }
    # Derive lengths from bytes rather than relying on the hand-written examples.
    files["raw_sha256.json"] = json.dumps([{"path": name, "bytes": len(contents), "sha256": digest(contents)}
                                           for name, contents in files.items() if name.startswith("raw/")]).encode()
    archive = tmp_path / "parent.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for name, contents in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
            zipped.writestr(root.name + "/" + name, contents)
    library = tmp_path / "data"
    staged = stage_analysis_package(root, archive, library / "analysis/meta-collection-20261023", label="Prior Meta collection",
           metadata={"analysis_version": "meta-collection-20261023", "input_lineage": {"meta_collection": "meta-collection-20261023",
                      "statistical_results": "cleaned-20261022", "social": "cleaned-20261022"}})
    parent = AnalysisRepository(staged["database"])
    registry = library / "archive_registry.json"
    registration = {"key": "meta-collection-20261023", "database": "analysis/meta-collection-20261023/analysis.sqlite3",
                    "evidence_root": "analysis/meta-collection-20261023", "label": "Prior Meta collection"}
    registry.write_text(json.dumps({"archives": [], "analysis_package": registration}), encoding="utf-8")
    collection = tmp_path / "collection"
    (collection / "raw").mkdir(parents=True)
    (collection / "normalized").mkdir()
    (collection / "raw/story.txt").write_text("Labelled source without a song or destination", encoding="utf-8")
    (collection / "preflight_preservation.json").write_text(json.dumps({
        "configured_data_dir": str(library), "active_analysis": registration,
        "databases": [{"relative_path": registration["database"], "sha256": digest(parent.db_path.read_bytes())}],
        "registry": {"relative_path": "archive_registry.json", "sha256": digest(registry.read_bytes())}}), encoding="utf-8")
    (collection / "normalized/collection_status.csv").write_bytes(
        b"dataset,status,detail,evidence_ref,captured_at_utc\nstories,partial,Song not identified,raw/story.txt,2026-10-23T02:00:00Z\n")
    (collection / "normalized/story_song_mapping.csv").write_bytes(
        b"post_id,song_id,mapping_status,destination_url,captured_at_utc\n001,,unknown,,2026-10-23T02:00:00Z\n")
    return parent, collection, files


def package(inputs, tmp_path):
    parent, collection, _ = inputs
    result = build_meta_followup(parent, collection, tmp_path / "followup-package", tmp_path / "followup.zip")
    stage = stage_analysis_package(result["package_root"], result["zip_path"], tmp_path / "followup-stage",
                                   label=result["label"], metadata=result["staging_metadata"])
    return result, AnalysisRepository(stage["database"])


def test_all_parent_assets_and_unknown_mappings_preserved(inputs, tmp_path):
    parent, collection, files = inputs
    before = digest(parent.db_path.read_bytes())
    result, repo = package(inputs, tmp_path)
    assert digest(parent.db_path.read_bytes()) == before
    assert result["inherited_assets"] == len(files) and not result["live_data_changed"]
    for path, contents in files.items():
        destination = PREDECESSOR_PREFIX + path if path in {"metadata.json", "audit/final_validation.json", "raw_sha256.json"} else path
        assert repo.original_bytes(destination) == contents
    assert repo.original_bytes(RAW_PREFIX + "raw/story.txt") == (collection / "raw/story.txt").read_bytes()
    mapping = repo.table(PREFIX + "story_song_mapping.csv")
    assert mapping.post_id.tolist() == ["001"]
    assert pd.isna(mapping.song_id.iloc[0]) and pd.isna(mapping.destination_url.iloc[0])
    assert mapping.mapping_status.iloc[0] == "unknown"
    assert repo.metadata["baseline_status"] == "unverified"
    assert repo.metadata["input_lineage"]["meta_collection"] == "meta-collection-20261023"
    assert repo.metadata["input_lineage"]["statistical_results"] == "cleaned-20261022"
    assert repo.metadata["new_significance_tests"] == 0
    assert repo.metadata["tiktok_collection"] == "excluded"
    assert repo.original_zip() == Path(result["zip_path"]).read_bytes()


@pytest.mark.parametrize("raw,message", [
    (b"value,value_status\n0,unavailable\n", "blank"),
    (b"value,value_status\n,observed\n", "numeric"),
    (b"post_id,song_id\n1,,extra\n", "Malformed"),
    (b"captured_at_utc\n2026-10-23T01:00:00\n", "UTC offset"),
])
def test_invalid_evidence_rejected_before_output(inputs, tmp_path, raw, message):
    parent, collection, _ = inputs
    (collection / "normalized/story_song_mapping.csv").write_bytes(raw)
    with pytest.raises(StorageError, match=message):
        build_meta_followup(parent, collection, tmp_path / "out", tmp_path / "out.zip")
    assert not (tmp_path / "out").exists()


def test_preflight_required_and_parent_hash_checked(inputs, tmp_path):
    parent, collection, _ = inputs
    path = collection / "preflight_preservation.json"
    original = path.read_bytes()
    path.unlink()
    with pytest.raises(StorageError, match="requires preflight"):
        build_meta_followup(parent, collection, tmp_path / "out", tmp_path / "out.zip")
    payload = json.loads(original)
    payload["databases"][0]["sha256"] = "changed"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(StorageError, match="database changed"):
        build_meta_followup(parent, collection, tmp_path / "out", tmp_path / "out.zip")
    assert not (tmp_path / "out").exists()


def test_explicit_collection_status_required(inputs, tmp_path):
    parent, collection, _ = inputs
    (collection / "normalized/collection_status.csv").unlink()
    with pytest.raises(StorageError, match="collection_status"):
        build_meta_followup(parent, collection, tmp_path / "out", tmp_path / "out.zip")
    assert not (tmp_path / "out").exists()


def test_reserved_lineage_table_rejected_before_writing(inputs, tmp_path):
    parent, collection, _ = inputs
    (collection / "normalized/dataset_catalog.csv").write_bytes(b"table,rows\nfake,1\n")
    with pytest.raises(StorageError, match="reserved"):
        build_meta_followup(parent, collection, tmp_path / "out", tmp_path / "out.zip")
    assert not (tmp_path / "out").exists()


def test_registry_change_stops_build_without_output(inputs, tmp_path):
    parent, collection, _ = inputs
    preflight = json.loads((collection / "preflight_preservation.json").read_text())
    registry = Path(preflight["configured_data_dir"]) / "archive_registry.json"
    registry.write_bytes(registry.read_bytes() + b"\n")
    with pytest.raises(StorageError, match="registry changed"):
        build_meta_followup(parent, collection, tmp_path / "out", tmp_path / "out.zip")
    assert not (tmp_path / "out").exists()


def test_independent_storage_audit_matches_parent_and_frozen_collection(inputs, tmp_path):
    parent, collection, files = inputs
    _, repo = package(inputs, tmp_path)
    report = audit(parent.db_path, repo.db_path, collection)
    assert report["passed"] and report["audit_scope"] == "storage_integrity_only"
    assert report["semantic_evidence_review_required"]
    assert report["inherited_asset_count"] == len(files)
    assert report["all_zip_assets_match_database"]
    (collection / "raw/story.txt").write_text("Changed source proof", encoding="utf-8")
    with pytest.raises(StorageError, match="raw source changed"):
        audit(parent.db_path, repo.db_path, collection)


def test_existing_outputs_and_same_namespace_cannot_be_reused(inputs, tmp_path):
    parent, collection, _ = inputs
    result, repo = package(inputs, tmp_path)
    before = Path(result["zip_path"]).read_bytes()
    with pytest.raises(FileExistsError, match="Preserving"):
        build_meta_followup(parent, collection, result["package_root"], result["zip_path"])
    assert Path(result["zip_path"]).read_bytes() == before
    with pytest.raises(StorageError, match="follow-up namespace"):
        build_meta_followup(repo, collection, tmp_path / "again", tmp_path / "again.zip", version_key="meta-followup-other")


def test_followup_ui_exposes_separate_evidence_and_prior_views(inputs, tmp_path):
    _, repo = package(inputs, tmp_path)
    code = ("from stats_app.analysis_repository import AnalysisRepository\n"
            "from stats_app.analysis_meta_ui import render_meta_collection\n"
            f"render_meta_collection(AnalysisRepository({str(repo.db_path)!r}))\n")
    app = AppTest.from_string(code, default_timeout=30).run()
    assert not app.exception and not app.error
    selector = next(item for item in app.radio if item.label == "Collection view")
    assert selector.value == "Follow-up evidence"
    assert any("Spotify conversion" in item.value for item in app.warning)
    assert any("cleaned-20261022" in item.value for item in app.info)
    assert any("mapping_status" in frame.value and pd.isna(frame.value.song_id.iloc[0]) for frame in app.dataframe)
    selector.set_value("Post/song/event map").run()
    assert not app.exception and not app.error
    assert any("status" in frame.value and "unknown" in frame.value.status.tolist() for frame in app.dataframe)


def test_mixed_account_correction_is_visible_without_combining_exports(inputs, tmp_path):
    _, collection, _ = inputs
    (collection / "normalized/ad_identity_scope.csv").write_bytes(b"ad_id,identity_scope\n001,band\n")
    (collection / "normalized/ad_identity_totals.csv").write_bytes(
        b"source_file,identity_scope,spend_usd\nraw/ads_daily_maximum.csv,band,554.52\n"
        b"raw/ads_daily_maximum.csv,nonband,99.79\nraw/ads_daily_maximum.csv,unknown,6.71\n"
        b"raw/ads_daily_recent_window.csv,band,999.00\n")
    _, repo = package(inputs, tmp_path)
    code = ("from stats_app.analysis_repository import AnalysisRepository\n"
            "from stats_app.analysis_meta_ui import render_meta_collection\n"
            f"render_meta_collection(AnalysisRepository({str(repo.db_path)!r}))\n")
    app = AppTest.from_string(code, default_timeout=30).run()
    warnings = [item.value for item in app.warning if "mixed-use" in item.value]
    assert len(warnings) == 1 and "USD 554.52" in warnings[0] and "USD 99.79" in warnings[0] and "USD 6.71" in warnings[0]
    assert "USD 999" not in warnings[0] and "$" not in warnings[0]
    next(item for item in app.radio if item.label == "Collection view").set_value("Ads history").run()
    warnings = [item.value for item in app.warning if "mixed-use" in item.value]
    assert len(warnings) == 2 and not app.exception
