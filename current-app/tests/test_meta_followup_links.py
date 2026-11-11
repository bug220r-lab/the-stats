"""Protect link identity, observation grain and retained source semantics."""
import csv
import json
from pathlib import Path

import pytest

from scripts.normalize_meta_followup_links import digest, normalize, spotify_identity, embedded_url, validate_ad_observations


ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "data/collection/meta-followup-20261023"
CATALOG = ROOT / "data/reconciliation/meta_20261023/package"


def read(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def normalized(tmp_path_factory):
    if not (COLLECTION/"links/linktree-cards.json").is_file():
        pytest.skip("Private captured link sources unavailable")
    output = tmp_path_factory.mktemp("normalized-links")
    audit = normalize(COLLECTION, CATALOG, output)
    return output, audit


def test_observed_url_identity_rejects_host_and_id_lookalikes():
    identity = "3QVtuSBGLC9fTmLfF6qP7Z"
    assert spotify_identity(f"https://open.spotify.com/track/{identity}?utm_source=linktree") == ("track", identity)
    assert spotify_identity(f"https://open.spotify.com.evil.invalid/track/{identity}") == ("", "")
    assert spotify_identity("https://open.spotify.com/track/too-short") == ("", "")
    assert embedded_url("https://l.instagram.com/?u=https%3A%2F%2Flinktr.ee%2Fredactedoh") == "https://linktr.ee/redactedoh"
    assert embedded_url("https://other.invalid/?u=https%3A%2F%2Flinktr.ee%2Fredactedoh") == ""


def test_linktree_control_grain_exact_ids_and_misleading_label(normalized):
    output, audit = normalized
    rows = read(output/"link_destinations.csv")
    cards = [row for row in rows if row["platform"] == "Linktree"]
    assert len(rows) == 15 and len(cards) == 12
    assert len({row["card_label"] for row in cards}) == 6
    assert len({row["href_raw"] for row in cards}) == 10
    unmatched = [row for row in cards if row["catalog_match_status"] == "unmatched_exact_track_id"]
    assert {row["spotify_entity_id"] for row in unmatched} == {
        "2pyhk8Rc3SqtUvVo5Fkdko", "5WKEXGaj4iAGXMjvLzPeiK", "60woYkT0EsP3PZrVflMs5i"}
    assert all(row["canonical_recording_id"] == "" for row in unmatched)
    debut = [row for row in cards if row["card_label"] == "[REDACTED] - Debut Album"]
    assert len(debut) == 2
    assert {row["canonical_recording_id"] for row in debut} == {"3QVtuSBGLC9fTmLfF6qP7Z"}
    assert all(row["canonical_title"] == "Funny Guy" and row["card_label_match_status"] == "does_not_match_catalog_destination_title" for row in debut)
    assert all(row["canonical_recording_id"] == "" for row in cards if row["spotify_entity_type"] == "album")
    assert audit["source_files_unchanged"] and audit["catalog_files_unchanged"]


def test_current_capture_not_historical_attribution_and_empty_not_zero(normalized):
    output, _ = normalized
    rows = read(output/"link_destinations.csv")
    assert all(row["temporal_scope"] == "current_destination_at_capture" for row in rows)
    assert all(row["reporting_start"] == row["reporting_end"] == "" for row in rows)
    post = next(row for row in rows if row["source_post_id"] == "998829296519708")
    assert post["destination_kind"] == "community_music_submission"
    assert post["canonical_recording_id"] == post["spotify_entity_id"] == ""
    assert post["destination_resolution"] == "observed_browser_navigation"
    profiles = [row for row in rows if row["source_kind"] == "profile_link"]
    assert all(row["destination_resolution"] == "decoded_redirect_parameter_only" for row in profiles)
    issues = read(output/"link_evidence_issues.csv")
    empty = next(row for row in issues if row["issue"] == "empty_transient_capture")
    assert empty["card_label"] == "Crawl" and empty["status"] == "superseded_by_later_capture"


def test_all_ad_source_fields_blanks_and_draft_status_preserved(normalized):
    output, audit = normalized
    source = json.loads((COLLECTION/"ads/ad_destination_observations.json").read_text("utf-8-sig"))
    rows = read(output/"ad_destinations.csv")
    assert len(rows) == len(source) == 6
    for raw, actual in zip(source, rows):
        assert all(actual[key] == str(value) for key, value in raw.items())
    draft = next(row for row in rows if row["source_status"] == "unpublished_draft")
    assert draft["Link"] == "" and draft["destination_status"] == "unavailable_blank_configuration_field"
    assert all(row["delivery_in_period"] == "not_established_by_configuration" for row in rows)
    assert all(row["captured_at_utc"] == "" for row in rows)
    assert all(row["capture_timestamp_status"] == "unavailable_in_native_export" for row in rows)
    assert all(row["acquired_at_utc"] == "2026-10-23T05:07:43.552Z" for row in rows)
    assert audit["native_ad_field_checks"] == 96
    damaged = [dict(source[1], Link="https://open.spotify.com/track/3QVtuSBGLC9fTmLfF6qP7Z")]
    with pytest.raises(ValueError, match="differs from native export"):
        validate_ad_observations(COLLECTION, damaged)


def test_csv_reproduction_is_deterministic(normalized, tmp_path):
    original, audit = normalized
    repeated = normalize(COLLECTION, CATALOG, tmp_path)
    assert audit["output_sha256"] == repeated["output_sha256"]
    for name, expected in audit["output_sha256"].items():
        assert digest(original/name) == digest(tmp_path/name) == expected
