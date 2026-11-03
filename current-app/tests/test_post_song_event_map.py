import csv
import json

import pytest

from scripts.build_post_song_event_map import song_references, caption_dates, caption_events, write_rows


def catalog():
    return [
        dict(song_id="A" * 22, title="Funny Guy", recording_label="Funny Guy", release_memberships="Band Album | Funny Guy"),
        dict(song_id="B" * 22, title="Method Acting", recording_label="Method Acting (album, 2024)", release_memberships="Band Album"),
        dict(song_id="C" * 22, title="Method Acting", recording_label="Method Acting (Lab Tapes, 2023)", release_memberships="Lab Tapes"),
        dict(song_id="D" * 22, title="Crawl", recording_label="Crawl", release_memberships="Band Album | Crawl"),
        dict(song_id="E" * 22, title="The Cut (Starts Tomorrow)", recording_label="The Cut (Starts Tomorrow)", release_memberships="The Cut (Starts Tomorrow)"),
    ]


def test_shared_title_never_chooses_a_recording_without_version():
    row = song_references("Method Acting #punk #altrock", catalog())[0]
    assert row["status"] == "ambiguous_recording_version"
    assert row["song_id"] == ""
    assert set(row["candidate_song_ids"]) == {"B" * 22, "C" * 22}
    row = song_references("Method Acting (Lab Tapes, 2023)", catalog())[0]
    assert row["song_id"] == "C" * 22


def test_nickname_and_generic_prose_not_assigned_as_song():
    row = song_references("Meet Jude, The Funny Guy (lead singer)", catalog())[0]
    assert row["status"] == "candidate_non_song_context" and not row["song_id"]
    row = song_references("We had to crawl back home.", catalog())[0]
    assert row["status"] == "candidate_generic_phrase" and not row["song_id"]


def test_multi_song_and_unknown_remain_distinct():
    refs = song_references("Songs: Funny Guy and Crawl", catalog())
    assert {r["song_id"] for r in refs} == {"A" * 22, "D" * 22}
    assert song_references("A fun night!", catalog())[0]["status"] == "unknown_no_identified_song"
    assert song_references("No music in this clip", catalog())[0]["status"] == "explicit_no_song_claim"


def test_spotify_link_is_known_identity_only_and_other_id_is_unresolved():
    refs = song_references("https://open.spotify.com/track/" + "B" * 22 + "?si=abc", catalog())
    assert refs[0]["status"] == "verified_spotify_link" and refs[0]["song_id"] == "B" * 22
    refs = song_references("spotify:track:" + "Z" * 22, catalog())
    assert refs[0]["status"] == "uncatalogued_spotify_link" and not refs[0]["song_id"]


def test_exact_dates_and_uncertain_years_are_not_conflated():
    found = caption_dates("Live 12/20/25; next May 30; return 5/30. Part 2/3.")
    assert ("2025-12-20", "explicit_caption_date", "12/20/25") in found
    assert ("", "year_not_stated", "May 30") in found
    assert ("", "year_not_stated", "5/30") in found
    assert all(item[2] != "2/3" for item in found)


def test_song_title_tomorrow_is_not_event_date():
    events = caption_events("The Cut (Starts Tomorrow) is out now!", catalog())
    assert events[0]["event_date"] == ""
    assert events[0]["event_date_status"] == "event_date_not_stated"
    events = caption_events("Show tomorrow at the venue!", catalog())
    assert events[0]["event_date_status"] == "relative_date_unresolved"


def test_version_identifier_does_not_assign_other_version_from_title():
    refs = song_references("Method Acting https://open.spotify.com/track/" + "C" * 22, catalog())
    assert [r["song_id"] for r in refs if r["song_id"]] == ["C" * 22]
    assert all(r["song_id"] != "B" * 22 for r in refs)


def test_mixed_release_and_show_caption_does_not_assign_release_date_to_show():
    events = caption_events("NEW The Cut (Starts Tomorrow) OUT 4.24.26. Hear the new single at our next show on 4/2.", catalog())
    exact = next(row for row in events if row["candidate_event_date"])
    assert exact["candidate_event_date"] == "2026-04-24"
    assert exact["event_date"] == ""
    assert exact["event_date_status"] == "explicit_date_event_association_unresolved"
    assert set(exact["mentioned_event_kinds"]) == {"music_release_promotion", "show_or_live_event_mention"}


def test_explicit_new_song_announcement_date_is_retained():
    events = caption_events("NEW BAND - Funny Guy - 2/13/26", catalog())
    assert events[0]["event_kind"] == "music_release_promotion"
    assert events[0]["event_date"] == "2026-02-13"


def test_unresolved_mapping_csv_and_json_preserve_missing_values(tmp_path):
    song = song_references("A fun night!", catalog())[0]
    event = caption_events("Show tomorrow at the venue!", catalog())[0]
    row = {
        "song_id": song["song_id"],
        "song_status": song["status"],
        "event_date": event["event_date"],
        "event_date_status": event["event_date_status"],
        "source_null": None,
        "candidate_song_ids": song["candidate_song_ids"],
        "source_context": {"missing_date": None, "empty_reference": ""},
        "zero_count": 0,
        "audio_use_verified": False,
        "numeric_change": -3,
    }
    write_rows(tmp_path, "unresolved", [row])

    with (tmp_path / "unresolved.csv").open(encoding="utf-8-sig", newline="") as handle:
        actual = list(csv.DictReader(handle))
    assert len(actual) == 1
    actual = actual[0]
    assert actual["song_id"] == actual["event_date"] == actual["source_null"] == ""
    assert actual["song_status"] == "unknown_no_identified_song"
    assert actual["event_date_status"] == "relative_date_unresolved"
    assert json.loads(actual["candidate_song_ids"]) == []
    assert json.loads(actual["source_context"]) == row["source_context"]
    assert actual["zero_count"] == "0"
    assert actual["audio_use_verified"] == "False"
    assert actual["numeric_change"] == "-3"
    assert json.loads((tmp_path / "unresolved.json").read_text(encoding="utf-8")) == [row]


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_mapping_csv_escapes_formula_leading_text_without_altering_json(tmp_path, prefix):
    caption = prefix + "untrusted source text"
    row = {"description": caption, "song_id": "", "event_date": None}
    write_rows(tmp_path, "protected", [row])

    with (tmp_path / "protected.csv").open(encoding="utf-8-sig", newline="") as handle:
        actual = list(csv.DictReader(handle))
    assert actual == [{"description": "'" + caption, "song_id": "", "event_date": ""}]
    assert json.loads((tmp_path / "protected.json").read_text(encoding="utf-8")) == [row]
