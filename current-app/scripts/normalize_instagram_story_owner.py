"""Normalize owner archive identity evidence without assigning unverified music."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from stats_app.analysis_repository import load_registered_analysis
from stats_app.config import load_settings
from stats_app.instagram_audio import STORY_IDS
from stats_app.storage import StorageError


ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "data/collection/instagram-story-owner-20261023"
PRIOR_MAP = "social/meta_followup/story_song_map.csv"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(parent, collection=COLLECTION):
    collection = Path(collection)
    output = collection / "normalized"
    receipt_path = collection / "normalization_receipt.json"
    if output.exists() or receipt_path.exists():
        raise FileExistsError("Preserving the normalized owner collection; choose a separate version.")
    if parent.metadata["analysis_version"] != "instagram-audio-20261023":
        raise StorageError("Owner review requires the current Instagram audio predecessor.")
    evidence = collection / "browser_evidence"
    inputs = {path.relative_to(collection).as_posix(): digest(path)
              for path in sorted(collection.rglob("*")) if path.is_file()}
    limits = json.loads((evidence / "collection_limits.json").read_text(encoding="utf-8"))
    if not (limits["owner_access_verified"] is True and limits["viewer_account"] == "redactedbandoh"
            and limits["stories_visually_reviewed"] == 6 and limits["native_story_audio_labels_visible"] == 0
            and limits["audio_listening_or_fingerprinting_performed"] is False):
        raise StorageError("This owner snapshot must reflect the six inspected, audio-unverified Stories.")
    prior = parent.table(PRIOR_MAP, raw=True).set_index("post_id", drop=False)
    stories, links = [], []
    for path in sorted(evidence.glob("oct*-paused.json")):
        capture = json.loads(path.read_text(encoding="utf-8"))
        post_id = capture["meta_story_id"]
        if post_id not in STORY_IDS or post_id not in prior.index:
            raise StorageError("Owner capture must identify a retained target Story.")
        row = prior.loc[post_id]
        native_id = row.permalink.rstrip("/").split("/")[-1]
        if (native_id != capture["instagram_native_story_id"] or capture["viewer_account"] != row.account_handle
                or capture["native_audio_label_visible"] is not False):
            raise StorageError("Owner capture conflicts with retained account/Story identity or audio availability.")
        stem = path.stem.removesuffix("-paused")
        if row.published_local[:10] != "2026-10-" + stem.removeprefix("oct"):
            raise StorageError("Owner calendar day and prior Story publication date differ.")
        archive_id = capture["archive_story_id"]
        if f"/stories/archive/{archive_id}/" not in capture["source_url"]:
            raise StorageError("Owner archive ID and captured URL differ.")
        proof = [path, path.with_suffix(".txt"), path.with_suffix(".png")]
        for item in proof:
            if not item.is_file():
                raise StorageError("Owner identity capture is missing its screenshot or accessibility evidence.")
        linked_path = evidence / (stem + "-linked-post.json")
        source_url = ""
        if linked_path.exists():
            linked = json.loads(linked_path.read_text(encoding="utf-8"))
            if (linked["origin_meta_story_id"] != post_id or linked["origin_archive_story_id"] != archive_id
                    or linked["viewer_account"] != row.account_handle or linked["link_type"] != "embedded_see_post"
                    or linked["relationship"] != "source_meme_post_not_verified_story_soundtrack"
                    or f"/p/{linked['destination_shortcode']}/" not in linked["source_url"]):
                raise StorageError("Linked meme source identity conflicts with its owner Story capture.")
            source_url = linked["source_url"]
            linked_proof = [linked_path, linked_path.with_suffix(".txt"), linked_path.with_suffix(".png")]
            for item in linked_proof:
                if not item.is_file():
                    raise StorageError("Source-post capture is missing its screenshot or accessibility evidence.")
            links.append({"post_id": post_id, "archive_story_id": archive_id, "published_local": row.published_local,
                "publication_timezone": row.publication_timezone, "archive_source_url": capture["source_url"],
                "destination_url": source_url, "destination_shortcode": linked["destination_shortcode"],
                "destination_account": linked["destination_account"], "link_type": linked["link_type"],
                "destination_scope": "third_party_source_meme_post", "source_post_link_verified": True,
                "story_audio_use_verified": False, "spotify_destination_verified": False,
                "click_metric_value": "", "click_metric_status": "not_collected", "stream_attribution_available": False,
                "relationship": linked["relationship"], "captured_at_utc": linked["captured_at_utc"],
                "evidence_ref": ";".join(p.relative_to(collection).as_posix() for p in linked_proof),
                "source_json_sha256": digest(linked_path)})
        stories.append({"post_id": post_id, "platform_selected": row.platform_selected,
            "selected_account_id": row.selected_account_id, "account_handle": row.account_handle,
            "viewer_account": capture["viewer_account"], "published_local": row.published_local,
            "published_utc": row.published_utc, "publication_timezone": row.publication_timezone,
            "publication_source": "Unchanged inherited Meta export; owner calendar date independently matched",
            "public_story_url": row.permalink, "instagram_native_story_id": native_id,
            "archive_story_id": archive_id, "archive_source_url": capture["source_url"],
            "native_archive_identity_verified": True, "identity_match_basis": capture["matched_by"],
            "identity_match_status": "owner_account_calendar_date_identical_artwork_bridge",
            "prior_mapping_status": row.mapping_status, "candidate_song_title": row.candidate_song_title,
            "candidate_song_ids": row.candidate_song_ids, "assigned_song_id": "", "audio_use_verified": False,
            "native_audio_label_visible": False, "audio_label_status": "not_visible_in_owner_archive_player",
            "mapping_status": "unresolved_after_owner_archive_review", "audio_listening_or_fingerprinting_performed": False,
            "embedded_source_post_url": source_url,
            "source_post_link_status": "verified_embedded_source_meme_post" if source_url else "not_observed_in_inspected_story",
            "source_post_audio_as_story_audio_verified": False, "stream_attribution_available": False,
            "captured_at_utc": capture["captured_at_utc"],
            "evidence_ref": ";".join(p.relative_to(collection).as_posix() for p in proof),
            "source_json_sha256": digest(path), "screenshot_sha256": digest(path.with_suffix(".png")),
            "prior_evidence_table": PRIOR_MAP,
            "limitation": "No native music label was displayed. Audio was not listened to or fingerprinted; absence of a label does not establish silence."})
    if len(stories) != 6 or {r["post_id"] for r in stories} != STORY_IDS or len(links) != 4:
        raise StorageError("Expected exactly six owner Story inspections and four embedded source-post destinations.")
    status = [
        {"dataset": "owner_story_identity", "status": "six_archive_identities_verified", "detail": "Six owner archive URLs matched to retained Meta/public Story identities using owner account, calendar date and identical artwork; the three ID systems remain distinct.", "evidence_ref": "normalized/story_owner_review.csv", "captured_at_utc": limits["captured_at_utc"]},
        {"dataset": "story_song_audio", "status": "all_six_unresolved", "detail": "No native audio labels were displayed. Audio listening/fingerprinting was not performed. The prior Oct 11 The Cut candidate remains unverified; no song is assigned.", "evidence_ref": "normalized/story_owner_review.csv;browser_evidence/collection_limits.json", "captured_at_utc": limits["captured_at_utc"]},
        {"dataset": "embedded_source_posts", "status": "four_source_meme_destinations_verified", "detail": "Four See Post controls resolve to third-party meme posts. These are provenance links, not Spotify destinations, Story soundtrack evidence, link clicks or stream conversions.", "evidence_ref": "normalized/story_source_links.csv", "captured_at_utc": limits["captured_at_utc"]},
        {"dataset": "media_identification", "status": "not_performed", "detail": "A visible-video download attempt returned browser does not support blob downloads. No original media was acquired and no listening or fingerprinting was performed.", "evidence_ref": "browser_evidence/collection_limits.json", "captured_at_utc": limits["captured_at_utc"]},
    ]
    output.mkdir()
    for filename, rows in (("story_owner_review.csv", stories), ("story_source_links.csv", links), ("collection_status.csv", status)):
        pd.DataFrame(rows).to_csv(output / filename, index=False)
    if any(digest(collection / path) != sha for path, sha in inputs.items()):
        raise StorageError("Original owner capture changed during normalization.")
    receipt = {"normalized_at_utc": datetime.now(timezone.utc).isoformat(), "parent_analysis": parent.metadata["analysis_version"],
        "source_hashes_unchanged": inputs, "normalized_hashes": {p.relative_to(collection).as_posix(): digest(p) for p in sorted(output.iterdir())},
        "owner_story_rows": 6, "native_archive_identities_verified": 6, "song_audio_matches_verified": 0,
        "source_meme_post_links": 4, "candidate_song_rows": 1, "previous_maps_modified": False,
        "historical_metrics_or_statistics_recomputed": False}
    with receipt_path.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2); handle.write("\n")
    return receipt


if __name__ == "__main__":
    parent = load_registered_analysis(load_settings().data_dir, key="instagram-audio-20261023")
    result = normalize(parent)
    print(json.dumps({key: result[key] for key in ("owner_story_rows", "native_archive_identities_verified", "song_audio_matches_verified", "source_meme_post_links")}, indent=2))
