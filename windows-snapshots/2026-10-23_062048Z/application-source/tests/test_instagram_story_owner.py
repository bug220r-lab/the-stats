"""Owner visual identity and meme links cannot imply Story soundtrack evidence."""
import csv
from pathlib import Path

import pytest

from stats_app.analysis_repository import AnalysisRepository
from stats_app.instagram_story_owner import build_instagram_story_owner
from stats_app.storage import StorageError


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/collection/instagram-story-owner-20261023/normalized"
PARENT = ROOT / "data/reconciliation/instagram_audio_20261023/staged_analysis/analysis.sqlite3"


@pytest.fixture
def owner_inputs(tmp_path):
    if not PARENT.is_file() or not SOURCE.is_dir():
        pytest.skip("Private owner collection is unavailable; no synthetic Story identity is substituted.")
    collection = tmp_path / "collection"
    normalized = collection / "normalized"
    normalized.mkdir(parents=True)
    rows = {}
    for name in ("story_owner_review.csv", "story_source_links.csv", "collection_status.csv"):
        rows[name] = list(csv.DictReader((SOURCE / name).open(encoding="utf-8", newline="")))
        (normalized / name).write_bytes((SOURCE / name).read_bytes())
    return AnalysisRepository(PARENT), collection, rows


@pytest.mark.parametrize("change,reason", [
    ("invent_song", "separate from unresolved"),
    ("lose_candidate", "inherited Story"),
    ("confuse_identity", "public Story ID"),
    ("claim_music_label", "separate from unresolved"),
    ("source_post_soundtrack", "cannot become soundtrack"),
    ("click_zero", "cannot become soundtrack"),
    ("wrong_story", "six Stories"),
])
def test_owner_evidence_rejects_unsupported_claims_before_packaging(owner_inputs, tmp_path, change, reason):
    parent, collection, tables = owner_inputs
    stories, links = tables["story_owner_review.csv"], tables["story_source_links.csv"]
    if change == "invent_song": stories[0]["assigned_song_id"] = "3HqynH6ObSuDPZM0RMnFxN"
    if change == "lose_candidate":
        next(row for row in stories if row["post_id"] == "18430983631182631")["candidate_song_title"] = ""
    if change == "confuse_identity": stories[0]["instagram_native_story_id"] = stories[0]["archive_story_id"]
    if change == "claim_music_label": stories[0]["native_audio_label_visible"] = "True"
    if change == "source_post_soundtrack": links[0]["story_audio_use_verified"] = "True"
    if change == "click_zero": links[0]["click_metric_value"] = "0"
    if change == "wrong_story": stories[0]["post_id"] = "999"
    for name, rows in tables.items():
        with (collection / "normalized" / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, list(rows[0])); writer.writeheader(); writer.writerows(rows)
    with pytest.raises(StorageError, match=reason):
        build_instagram_story_owner(parent, collection, tmp_path / "out", tmp_path / "out.zip")
    assert not (tmp_path / "out").exists()
