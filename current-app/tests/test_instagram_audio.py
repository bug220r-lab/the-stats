"""A later post audio label cannot rewrite the unresolved Story evidence."""
import csv
import hashlib
import json
from pathlib import Path
import zipfile

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from scripts.audit_meta_followup_storage import audit
from stats_app.analysis_repository import AnalysisRepository, stage_analysis_package
from stats_app.instagram_audio import PREFIX, PREDECESSOR_PREFIX, RAW_PREFIX, STORY_IDS, build_instagram_audio
from stats_app.storage import StorageError


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def csv_write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def audio_inputs(tmp_path):
    root = tmp_path / "parent-package"
    files = {
        "raw/old.csv": b"post_id,caption\n001,unchanged\n",
        "raw/meta_followup/stories/proof.txt": b"Earlier Story capture",
        "raw/meta_followup_predecessor_metadata/metadata.json": b'{"analysis_version":"meta-collection-20261023"}',
        "social/meta_collection/collection_status.csv": b"dataset,status,detail,evidence_ref,captured_at_utc\nold,retained,Earlier evidence,raw/old.csv,\n",
        "social/meta_collection/mapping/post_song_references.csv": b"post_id,song_id,status\n001,,unknown\n",
        "social/meta_followup/collection_status.csv": b"dataset,status,detail,evidence_ref,captured_at_utc\nstories,unresolved,Evidence unavailable,raw/old.csv,\n",
        "social/meta_followup/story_song_map.csv": b"post_id,assigned_song_ids,audio_use_verified,mapping_status\n001,[],False,unresolved\n",
        "spotify/cleaned/recordings.csv": b"song_id,title,artist_id\n3HqynH6ObSuDPZM0RMnFxN,The Cut (Starts Tomorrow),artist\n",
        "statistical_results.csv": b"analysis_id,status\nprior,no_significance\n",
        "audit/meta_followup_import.json": b'{"old_audit":true}',
        "META_FOLLOWUP_HANDOFF.md": b"Earlier handoff unchanged",
        "metadata.json": b'{"analysis_version":"meta-followup-20261023"}',
        "audit/final_validation.json": b'{"old_check":true}',
    }
    files["raw_sha256.json"] = json.dumps([{"path": name, "bytes": len(raw), "sha256": digest(raw)}
                                            for name, raw in files.items() if name.startswith("raw/")]).encode()
    archive = tmp_path / "parent.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for name, raw in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            zipped.writestr(root.name + "/" + name, raw)
    library = tmp_path / "library"
    staged = stage_analysis_package(root, archive, library / "analysis/meta-followup-20261023", label="Parent",
        metadata={"analysis_version": "meta-followup-20261023", "input_lineage": {
            "meta_followup": "meta-followup-20261023", "meta_collection": "meta-collection-20261023",
            "statistical_results": "cleaned-20261022", "social": "cleaned-20261022", "predecessor_analysis": "meta-collection-20261023"}})
    parent = AnalysisRepository(staged["database"])
    registration = {"key": "meta-followup-20261023", "database": "analysis/meta-followup-20261023/analysis.sqlite3",
                    "evidence_root": "analysis/meta-followup-20261023", "label": "Parent"}
    registry = library / "archive_registry.json"
    registry.write_text(json.dumps({"archives": [], "analysis_package": registration}), encoding="utf-8")
    collection = tmp_path / "collection"
    (collection / "normalized").mkdir(parents=True)
    (collection / "proof.txt").write_text("Native post audio label; Stories unresolved", encoding="utf-8")
    (collection / "preflight_preservation.json").write_text(json.dumps({
        "configured_data_dir": str(library), "active_analysis": registration,
        "databases": [{"relative_path": registration["database"], "sha256": digest(parent.db_path.read_bytes())}],
        "registry": {"relative_path": "archive_registry.json", "sha256": digest(registry.read_bytes())}}), encoding="utf-8")
    posts = []
    for i in range(3):
        verified = i == 0
        posts.append(dict(post_id=str(100 + i), content_kind="Reel" if verified else "Carousel",
            native_audio_label="[REDACTED] • The Cut (Starts Tomorrow)" if verified else "",
            native_audio_title="The Cut (Starts Tomorrow)" if verified else "", native_audio_artist="[REDACTED]" if verified else "",
            native_audio_url="https://www.instagram.com/reels/audio/960372056504905/" if verified else "",
            native_audio_id="960372056504905" if verified else "", native_audio_label_verified=verified,
            audio_evidence_status="native_label_verified" if verified else "not_visible_in_inspected_post",
            spotify_catalog_candidate_id="3HqynH6ObSuDPZM0RMnFxN" if verified else "",
            catalog_match_status="unique_title_artist_match" if verified else "not_applicable",
            spotify_recording_identity_verified=False, story_relationship_status="no_verified_link_to_six_stories",
            evidence_ref="proof.txt", captured_at_utc="2026-10-23T05:37:00Z"))
    stories = [dict(post_id=story_id, mapping_status="unresolved_after_personal_post_search", assigned_song_id="",
                    audio_use_verified=False, matched_feed_post_id="", evidence_ref="proof.txt") for story_id in sorted(STORY_IDS)]
    csv_write(collection / "normalized/post_audio_evidence.csv", posts)
    csv_write(collection / "normalized/story_match_status.csv", stories)
    csv_write(collection / "normalized/collection_status.csv", [dict(dataset="instagram_audio", status="partial",
              detail="One post label; six Stories unresolved", evidence_ref="proof.txt", captured_at_utc="2026-10-23T05:37:00Z")])
    return parent, collection, files, posts, stories


def staged_review(audio_inputs, tmp_path):
    parent, collection, *_ = audio_inputs
    result = build_instagram_audio(parent, collection, tmp_path / "review-package", tmp_path / "review.zip")
    stage = stage_analysis_package(result["package_root"], result["zip_path"], tmp_path / "review-stage",
                                   label=result["label"], metadata=result["staging_metadata"])
    return result, AnalysisRepository(stage["database"])


def test_current_followup_parent_bytes_and_lineage_preserved(audio_inputs, tmp_path):
    parent, collection, files, *_ = audio_inputs
    parent_hash = digest(parent.db_path.read_bytes())
    result, repo = staged_review(audio_inputs, tmp_path)
    for name, raw in files.items():
        retained = PREDECESSOR_PREFIX + name if name in {"metadata.json", "raw_sha256.json", "audit/final_validation.json"} else name
        assert repo.original_bytes(retained) == raw
    assert parent_hash == digest(parent.db_path.read_bytes())
    assert repo.original_bytes(RAW_PREFIX + "proof.txt") == (collection / "proof.txt").read_bytes()
    assert repo.metadata["input_lineage"]["meta_followup"] == "meta-followup-20261023"
    assert repo.metadata["input_lineage"]["statistical_results"] == "cleaned-20261022"
    assert repo.metadata["input_lineage"]["instagram_audio"] == "instagram-audio-20261023"
    assert repo.metadata["baseline_status"] == "unverified" and repo.metadata["new_significance_tests"] == 0
    story = repo.table(PREFIX + "story_match_status.csv")
    assert len(story) == 6 and story.assigned_song_id.isna().all() and not story.audio_use_verified.any()
    report = audit(parent.db_path, repo.db_path, collection, namespace="instagram_audio_20261023")
    assert report["passed"] and report["inherited_asset_count"] == len(files)
    assert report["semantic_evidence_review_required"] and report["all_zip_assets_match_database"]
    assert repo.original_zip() == Path(result["zip_path"]).read_bytes()


@pytest.mark.parametrize("change,reason", [
    ("story_assignment", "cannot assign"), ("story_missing", "six exact"),
    ("exact_recording", "exact Spotify"), ("label_without_id", "native identity"),
    ("wrong_catalog", "catalog title and ID"), ("post_claims_story", "separate"),
])
def test_unjustified_identity_claims_rejected_before_packaging(audio_inputs, tmp_path, change, reason):
    parent, collection, _, posts, stories = audio_inputs
    if change == "story_assignment": stories[0]["assigned_song_id"] = "3HqynH6ObSuDPZM0RMnFxN"
    if change == "story_missing": stories.pop()
    if change == "exact_recording": posts[0]["spotify_recording_identity_verified"] = True
    if change == "label_without_id": posts[0]["native_audio_id"] = ""
    if change == "wrong_catalog": posts[0]["spotify_catalog_candidate_id"] = "unknown"
    if change == "post_claims_story": posts[0]["story_relationship_status"] = "same_date_match"
    csv_write(collection / "normalized/post_audio_evidence.csv", posts)
    csv_write(collection / "normalized/story_match_status.csv", stories)
    with pytest.raises(StorageError, match=reason):
        build_instagram_audio(parent, collection, tmp_path / "out", tmp_path / "out.zip")
    assert not (tmp_path / "out").exists()


def test_new_version_refuses_replacement_or_different_parent(audio_inputs, tmp_path):
    parent, collection, *_ = audio_inputs
    result, repo = staged_review(audio_inputs, tmp_path)
    original = Path(result["zip_path"]).read_bytes()
    with pytest.raises(FileExistsError, match="Preserving"):
        build_instagram_audio(parent, collection, result["package_root"], result["zip_path"])
    assert Path(result["zip_path"]).read_bytes() == original
    with pytest.raises(StorageError, match="predecessor"):
        build_instagram_audio(repo, collection, tmp_path / "other", tmp_path / "other.zip")


def test_audio_ui_separates_native_post_label_from_unresolved_stories(audio_inputs, tmp_path):
    _, repo = staged_review(audio_inputs, tmp_path)
    code = ("from stats_app.analysis_repository import AnalysisRepository\n"
            "from stats_app.analysis_meta_ui import render_meta_collection\n"
            f"render_meta_collection(AnalysisRepository({str(repo.db_path)!r}))\n")
    app = AppTest.from_string(code, default_timeout=30).run()
    assert not app.exception and not app.error
    selector = next(item for item in app.radio if item.label == "Collection view")
    assert selector.value == "Instagram audio review"
    assert {"Follow-up evidence", "Post/song/event map"}.issubset(selector.options)
    assert any("six Story matches remain unresolved" in item.value for item in app.warning)
    posts = next(frame.value for frame in app.dataframe if "native_audio_label_verified" in frame.value)
    assert posts.native_audio_label_verified.astype(str).str.lower().eq("true").sum() == 1
    assert not posts.spotify_recording_identity_verified.any()
    next(item for item in app.selectbox if item.label == "Instagram audio evidence table").set_value(PREFIX + "story_match_status.csv").run()
    assert not app.exception and not app.error
    stories = next(frame.value for frame in app.dataframe if "assigned_song_id" in frame.value)
    assert len(stories) == 6 and stories.assigned_song_id.isna().all()
    next(item for item in app.radio if item.label == "Collection view").set_value("Follow-up evidence").run()
    assert not app.exception and not app.error
    assert any("assigned_song_ids" in frame.value for frame in app.dataframe)
