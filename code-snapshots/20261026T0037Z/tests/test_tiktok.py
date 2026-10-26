"""Synthetic explicit TikTok contracts; no native export headers are assumed."""
from copy import deepcopy
import csv
import io
import json

import pytest

from stats_app.tiktok import inspect_csv, preview_export, stage_preview
from stats_app.validation import COLUMNS, validate_records


def mapping(metric="video_views", grain="daily", unit="count", basis=None):
    basis = basis or ("cumulative_count" if grain == "snapshot" else "period_count")
    return dict(schema_version=1, encoding="utf-8-sig", delimiter=",", header_row=1, date_format="%Y-%m-%d",
        time_grain=grain, number_format="plain", columns={"date": "Day"} if grain == "daily" else {}, dimensions={},
        metrics=[dict(metric=metric, column="Amount", unit=unit, measurement_basis=basis,
            definition="Synthetic explicit metric definition; not a native export contract.",
            value_tokens={"": "missing", "*": "suppressed", "—": "unavailable"}, allow_percent_suffix=False)])


def metadata(**changes):
    result = dict(source_family="studio_csv", account="account-001", entity_type="account", entity_id="account-001",
                  entity_name="Fixture", content_scope="band_owned", report_scope="Synthetic report", source_timezone="UTC",
                  captured_at="2026-10-25T12:00:00Z", filters={})
    result.update(changes)
    return result


def raw(values, headers=("Day", "Amount")):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(values)
    return stream.getvalue().encode("utf-8-sig")


def preview(values, *, config=None, meta=None, **kwargs):
    return preview_export(raw(values), "native.csv", config or mapping(), metadata() if meta is None else meta, **kwargs)


@pytest.fixture
def stage_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "protected-local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "protected-roaming"))
    monkeypatch.setenv("STATS_DATA_DIR", str(tmp_path / "protected-library"))
    return tmp_path


def test_literal_headers_bounded_schema_preview_and_normalized_collisions():
    result = inspect_csv(raw([["2026-10-01", str(n)] for n in range(8)]), "native.csv")
    assert result["accepted"] and len(result["sample_rows"]) == 5
    collision = raw([["2026-10-01", "1"]], headers=("Day", " day "))
    assert not inspect_csv(collision, "native.csv")["accepted"]
    config = mapping()
    config["columns"]["date"] = "day"
    assert not preview([["2026-10-01", "1"]], config=config)["accepted"]


def test_missingness_and_observed_zero_are_source_qualified_without_aggregation():
    result = preview([["2026-10-01", "0"], ["2026-10-02", ""], ["2026-10-03", "*"], ["2026-10-04", "—"]])
    assert result["accepted"] and result["canonical_import_eligible"]
    assert [row["value"] for row in result["records"]] == [0, None, None, None]
    assert [row["status"] for row in result["records"]] == ["observed", "missing", "suppressed", "unavailable"]
    assert result["summary"]["observed_zero_count"] == 1 and result["summary"]["no_aggregation"]
    assert validate_records(result["records"]) == []


def test_daily_net_followers_is_signed_but_followers_stock_is_not_an_activity_total():
    net = preview([["2026-10-01", "-3"]], config=mapping("net_followers"))
    assert net["accepted"] and net["records"][0]["value"] == -3 and validate_records(net["records"]) == []
    assert not preview([["2026-10-01", "-3"]])["accepted"]
    assert not preview([["2026-10-01", "-0.5"]], config=mapping("net_followers"))["accepted"]
    stock = mapping("followers", "period", basis="point_in_time")
    assert not preview([["unused", "15"]], config=stock, meta=metadata(period_start="2026-10-01", period_end="2026-10-07"))["accepted"]
    assert preview([["2026-10-01", "15"]], config=mapping("followers", basis="point_in_time"))["accepted"]


def test_unique_viewers_is_distinct_and_never_remapped_to_additive_views():
    config = mapping("unique_viewers", "period", basis="distinct_count")
    result = preview([["unused", "12"]], config=config, meta=metadata(period_start="2026-10-01", period_end="2026-10-07"))
    assert result["accepted"] and result["records"][0]["measurement_type"] == "distinct_count"
    config["metrics"][0]["measurement_basis"] = "period_count"
    assert not preview([["unused", "12"]], config=config, meta=metadata(period_start="2026-10-01", period_end="2026-10-07"))["accepted"]


def test_video_lifetime_snapshot_preserves_content_without_inventing_metric_bounds():
    config = mapping(grain="snapshot")
    config["columns"] = {"entity_id": "Video", "caption": "Text", "caption_status": "TextState", "publication_date": "Published",
                         "published_local": "Literal", "permalink": "Link", "sound_id": "Sound", "song_id": "Song"}
    config["publication_date_format"] = "%m/%d/%Y"
    source = raw([["00017", "12", "A native caption", "reported", "10/01/2026", "Thu Oct 1", "https://www.tiktok.com/@fixture/video/17", "0009", "song-x"]],
                 headers=("Video", "Amount", "Text", "TextState", "Published", "Literal", "Link", "Sound", "Song"))
    result = preview_export(source, "native.csv", config, metadata(entity_type="video", captured_at=""))
    row = result["records"][0]
    assert result["accepted"] and not result["canonical_import_eligible"]
    assert row["period_start"] == row["period_end"] == row["captured_at"] == ""
    assert row["entity_id"] == "00017" and row["sound_id"] == "0009" and row["song_id"] == "song-x"
    assert row["publication_date"] == "2026-10-01" and row["published_local"] == "Thu Oct 1"
    assert row["caption"] == "A native caption" and row["caption_status_raw"] == "reported"
    assert row["caption_availability"] == "source_text_available" and row["measurement_type"] == "cumulative_count"
    config["metrics"][0]["measurement_basis"] = "period_count"
    assert not preview_export(source, "native.csv", config, metadata(entity_type="video"))["accepted"]


def test_blank_caption_is_unknown_and_publication_date_cannot_replace_daily_activity():
    config = mapping(grain="snapshot")
    config["columns"] = {"caption": "Text", "publication_date": "Day"}
    result = preview_export(raw([["2026-10-01", "7", ""]], headers=("Day", "Amount", "Text")), "native.csv", config, metadata(entity_type="video"))
    assert result["accepted"] and result["records"][0]["caption_availability"] == "missing_source_blank"
    assert result["records"][0]["publication_date"] == "" and result["records"][0]["publication_date_raw"] == "2026-10-01"
    config["time_grain"], config["metrics"][0]["measurement_basis"] = "daily", "period_count"
    assert not preview_export(raw([["2026-10-01", "7", ""]], headers=("Day", "Amount", "Text")), "native.csv", config, metadata(entity_type="video"))["accepted"]


def test_period_fallback_is_explicit_and_mapped_blank_does_not_fall_back():
    config = mapping(grain="period")
    meta = metadata(period_start="2026-10-01", period_end="2026-10-07")
    assert preview([["unused", "7"]], config=config, meta=meta)["accepted"]
    config["columns"]["period_start"] = "Day"
    assert not preview([["", "7"]], config=config, meta=meta)["accepted"]
    config = mapping(grain="snapshot")
    config["columns"] = {"period_start": "Day"}
    result = preview([["", "7"]], config=config, meta=meta)
    assert result["accepted"] and result["records"][0]["period_start"] == "" and not result["canonical_import_eligible"]


@pytest.mark.parametrize("metric,unit,value,expected", [("completion_rate", "ratio", "0.72", 0.72),
    ("completion_rate", "percent", "0.72", 0.72), ("completion_rate", "percent", "72", 72),
    ("total_watch_time", "seconds", "12.5", 12.5), ("total_watch_time", "hours", "1.5", 1.5),
    ("average_watch_time", "seconds", "4.25", 4.25)])
def test_explicit_rates_and_watchtime_units_are_never_rescaled(metric, unit, value, expected):
    basis = "period_sum" if metric == "total_watch_time" else "average" if metric == "average_watch_time" else "rate"
    result = preview([["2026-10-01", value]], config=mapping(metric, unit=unit, basis=basis))
    assert result["accepted"] and result["records"][0]["value"] == expected and result["records"][0]["unit"] == unit


def test_percent_suffix_requires_explicit_flag_and_cannot_be_interpreted_as_ratio():
    config = mapping("completion_rate", unit="percent", basis="rate")
    assert not preview([["2026-10-01", "72%"]], config=config)["accepted"]
    config["metrics"][0]["allow_percent_suffix"] = True
    assert preview([["2026-10-01", "72%"]], config=config)["records"][0]["value"] == 72
    config["metrics"][0]["unit"] = "ratio"
    assert not preview([["2026-10-01", "0.72%"]], config=config)["accepted"]
    assert not preview([["2026-10-01", "1.01"]], config=config)["accepted"]
    config["metrics"][0]["unit"] = "percent"
    assert not preview([["2026-10-01", "100.1"]], config=config)["accepted"]


def test_source_families_and_song_all_creator_scope_are_portable_and_separate():
    song = mapping("song_video_posts")
    meta = metadata(source_family="artists_csv", entity_type="song", entity_id="song-001", content_scope="all_creators")
    result = preview([["2026-10-01", "3"]], config=song, meta=meta)
    assert result["accepted"] and result["records"][0]["platform"] == "TikTok for Artists"
    scope = json.loads({key: result["records"][0][key] for key in COLUMNS}["dimensions_json"])["_tiktok_scope"]
    assert scope["source_family"] == "artists_csv" and scope["content_scope"] == "all_creators"
    assert not preview([["2026-10-01", "3"]], config=song, meta=metadata())["accepted"]
    assert not preview([["2026-10-01", "3"]], config=song, meta={**meta, "content_scope": "band_owned"})["accepted"]
    assert preview([["2026-10-01", "3"]], meta=metadata(source_family="artists_csv"))["records"][0]["platform"] == "TikTok for Artists"
    config = mapping()
    config["dimensions"] = {" _TikTok_Scope ": "Day"}
    assert not preview([["2026-10-01", "3"]], config=config)["accepted"]


def test_replays_and_revisions_keep_capture_rows_and_do_not_pool_families_or_filters():
    prior = preview([["2026-10-01", "1"]])["records"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(prior[0]))
    writer.writeheader(); writer.writerows(prior)
    existing = list(csv.DictReader(io.StringIO(stream.getvalue())))
    repeated = preview([["2026-10-01", "1.0"]], existing_records=existing)
    assert repeated["accepted"] and repeated["summary"]["duplicate_record_groups"] == 1
    revised = preview([["2026-10-01", "2"]], meta=metadata(captured_at="2026-10-26T12:00:00Z"), existing_records=existing)
    assert revised["accepted"] and revised["summary"]["overlap_pairs"] == 1 and len(revised["records"]) == 1
    for change in ({"source_family": "business_suite_csv"}, {"account": "other"}, {"entity_id": "another"}, {"filters": {"country": "US"}}):
        separate = preview([["2026-10-01", "2"]], meta=metadata(**change), existing_records=existing)
        assert separate["accepted"] and separate["summary"]["overlap_pairs"] == 0


def test_unknown_bound_snapshot_revisions_conflicts_and_unknown_capture_are_honest():
    config = mapping(grain="snapshot")
    meta = metadata(entity_type="video", captured_at="")
    conflict = preview([["unused", "1"], ["unused", "2"]], config=config, meta=meta)
    assert not conflict["accepted"] and len(conflict["records"]) == 2
    prior = preview([["unused", "1"]], config=config, meta=meta)["records"]
    revised = preview([["unused", "2"]], config=config, meta=meta, existing_records=prior)
    assert revised["accepted"] and not revised["canonical_import_eligible"] and revised["summary"]["overlap_pairs"] == 1
    possible = preview([["unused", "1.0"]], config=config, meta=meta, existing_records=prior)
    assert possible["accepted"] and any(item["code"] == "possible_duplicate_unknown_capture" for item in possible["issues"])
    assert not any(item["code"] == "duplicate_observation" for item in possible["issues"])
    broken = deepcopy(prior); broken[0]["value_exact"] = "bad"
    assert not preview([["unused", "2"]], config=config, meta=meta, existing_records=broken)["accepted"]


@pytest.mark.parametrize("change", [{"status": "bogus"}, {"status": "missing", "value": 3},
    {"status": "suppressed", "value": "", "value_exact": "0"}])
def test_invalid_prior_statuses_and_nonobserved_values_are_rejected(change):
    prior = preview([["2026-10-01", "1"]])["records"]
    prior[0].update(change)
    assert not preview([["2026-10-01", "1"]], existing_records=prior)["accepted"]


@pytest.mark.parametrize("value", ["1.2K", "NaN", "inf", "-1", "0.5", "9" * 400])
def test_counts_do_not_guess_rounded_or_nonfinite_values(value):
    assert not preview([["2026-10-01", value]])["accepted"]


def test_underflow_contradictory_status_and_wrong_json_types_are_review_errors():
    assert not preview([["2026-10-01", "0." + "0" * 400 + "1"]], config=mapping("average_watch_time", unit="seconds", basis="average"))["accepted"]
    config = mapping(); config["metrics"][0].update(status_column="Label", status_map={"missing": "missing"})
    source = raw([["2026-10-01", "7", "missing"]], headers=("Day", "Amount", "Label"))
    assert not preview_export(source, "native.csv", config, metadata())["accepted"]
    for change in ({"account": {}}, {"captured_at": 123}, {"source_family": []}, {"source_timezone": "Not/AZone"}):
        assert not preview([["2026-10-01", "1"]], meta=metadata(**change))["accepted"]
    config = mapping(); config["metrics"][0]["metric"] = []
    assert not preview([["2026-10-01", "1"]], config=config)["accepted"]


def test_staging_retains_exact_bytes_rejected_evidence_and_snapshot_eligibility(stage_roots):
    source = raw([["unused", "12"]])
    output = stage_roots / "snapshot"
    receipt = stage_preview(source, "native.csv", mapping(grain="snapshot"), metadata(entity_type="video"), output)
    assert receipt["accepted"] and not receipt["canonical_import_eligible"] and not receipt["library_modified"]
    assert (output / "raw/native.csv").read_bytes() == source
    assert json.loads((output / "preview.json").read_text())["records"][0]["period_start"] == ""
    with pytest.raises(FileExistsError):
        stage_preview(source, "native.csv", mapping(grain="snapshot"), metadata(entity_type="video"), output)
    rejected = stage_preview(raw([["2026-10-01", "1.2K"]]), "native.csv", mapping(), metadata(), stage_roots / "rejected")
    assert not rejected["accepted"] and (stage_roots / "rejected/raw/native.csv").is_file()
    with pytest.raises(ValueError):
        stage_preview(source, "../escape.csv", mapping(), metadata(), stage_roots / "unsafe")
    assert not (stage_roots / "unsafe").exists()
    with pytest.raises(ValueError):
        stage_preview(source, "native.csv", mapping(), metadata(), stage_roots / "protected-library/stage")
