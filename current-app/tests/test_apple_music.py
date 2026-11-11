"""Synthetic mapping contracts; no native Apple header contract is assumed."""
from copy import deepcopy
import csv
import hashlib
import io
import json

import pytest

from stats_app.apple_music import inspect_csv, preview_export, stage_preview
from stats_app.validation import COLUMNS, validate_records


def mapping(metric="plays", grain="daily"):
    basis = "average" if metric == "average_daily_listeners" else "distinct_count" if "listeners" in metric else "period_count"
    return dict(schema_version=1, encoding="utf-8-sig", delimiter=",", header_row=1, date_format="%Y-%m-%d",
                time_grain=grain, number_format="plain", columns={"date": "Day"} if grain == "daily" else {},
                dimensions={}, metrics=[dict(metric=metric, column="Amount", unit="count", measurement_basis=basis,
                    definition="Synthetic reviewed definition, not a native Apple schema.", value_tokens={"": "missing", "*": "suppressed", "<5": "suppressed", "—": "unavailable"})])


def metadata(**changes):
    result = dict(account="artist-001", entity_type="artist", entity_id="artist-001", entity_name="Fixture",
                  source_kind="artists_csv", source_timezone="UTC", captured_at="2026-10-25T12:00:00Z",
                  report_scope="Synthetic native report scope", filters={})
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


def test_schema_inspection_is_bounded_and_does_not_guess_headers():
    source = raw([["2026-10-01", str(n)] for n in range(8)])
    result = inspect_csv(source, "native.csv")
    assert result["accepted"] and result["source_row_count"] == 8
    assert result["headers"] == ["Day", "Amount"] and len(result["sample_rows"]) == 5
    assert result["sample_rows"][0] == dict(source_row=2, source_record=2, values={"Day": "2026-10-01", "Amount": "0"})
    assert result["source"]["sha256"] == hashlib.sha256(source).hexdigest()
    collision = raw([["2026-10-01", "1"]], headers=("Day", " day "))
    assert not inspect_csv(collision, "native.csv")["accepted"]
    config = mapping()
    config["columns"]["date"] = "day"
    assert not preview([["2026-10-01", "1"]], config=config)["accepted"]


def test_zero_missing_suppressed_unavailable_stay_distinct_with_raw_evidence():
    result = preview([["2026-10-01", "0"], ["2026-10-02", ""], ["2026-10-03", "*"], ["2026-10-04", "—"]])
    assert result["accepted"] and result["summary"]["observed_zero_count"] == 1
    assert [row["status"] for row in result["records"]] == ["observed", "missing", "suppressed", "unavailable"]
    assert [row["value"] for row in result["records"]] == [0, None, None, None]
    assert [row["source_value_raw"] for row in result["records"]] == ["0", "", "*", "—"]
    assert set(COLUMNS).issubset(result["records"][0]) and validate_records(result["records"]) == []


@pytest.mark.parametrize("value", ["-1", "NaN", "inf", "1.2K", "0.5", "1e3", "1%"])
def test_ambiguous_invalid_and_nonintegral_counts_are_rejected(value):
    assert not preview([["2026-10-01", value]])["accepted"]


def test_period_catalog_uses_only_explicit_global_bounds_and_preserves_native_ids():
    config = mapping("average_daily_listeners", "period")
    config["columns"] = {"entity_id": "Song ID"}
    source = raw([["000123", "2.5"]], headers=("Song ID", "Amount"))
    result = preview_export(source, "catalog.csv", config, metadata(period_start="2026-10-01", period_end="2026-10-07"))
    row = result["records"][0]
    assert result["accepted"] and row["entity_id"] == "000123" and row["value"] == 2.5
    assert row["measurement_type"] == "average" and row["period_start"] == "2026-10-01"
    config["columns"]["period_start"] = "Bound"
    source = raw([["000123", "2.5", ""]], headers=("Song ID", "Amount", "Bound"))
    assert not preview_export(source, "catalog.csv", config, metadata(period_start="2026-10-01", period_end="2026-10-07"))["accepted"]


@pytest.mark.parametrize("metric,grain,basis", [("daily_unique_listeners", "period", "distinct_count"),
    ("period_unique_listeners", "daily", "distinct_count"), ("average_daily_listeners", "period", "distinct_count"),
    ("listeners", "daily", "distinct_count"), ("streams", "daily", "period_count")])
def test_listener_grains_bases_and_platform_metrics_are_not_interchanged(metric, grain, basis):
    config = mapping(metric, grain)
    config["metrics"][0]["measurement_basis"] = basis
    assert not preview([["2026-10-01", "2"]], config=config, meta=metadata(period_start="2026-10-01", period_end="2026-10-07"))["accepted"]


def test_unknown_metadata_is_not_fabricated_and_ambiguous_dates_need_explicit_format():
    result = preview([["2026-10-01", "2"]], meta=metadata(captured_at="", source_timezone=""))
    assert result["accepted"] and result["records"][0]["captured_at"] == "" and result["records"][0]["source_timezone"] == "unknown"
    assert not preview([["10/01/2026", "2"]])["accepted"]
    config = mapping()
    config["date_format"] = "%m/%d/%Y"
    assert preview([["10/01/2026", "2"]], config=config)["accepted"]


def test_duplicates_revisions_and_unknown_capture_conflicts_are_reported_without_aggregation():
    equivalent = preview([["2026-10-01", "1"], ["2026-10-01", "1.0"]], meta=metadata(captured_at=""))
    assert equivalent["accepted"] and equivalent["summary"]["duplicate_record_groups"] == 1
    assert len(equivalent["records"]) == 2 and [row["value_exact"] for row in equivalent["records"]] == ["1", "1.0"]
    conflict = preview([["2026-10-01", "1"], ["2026-10-01", "2"]], meta=metadata(captured_at=""))
    assert not conflict["accepted"] and len(conflict["records"]) == 2
    prior = preview([["2026-10-01", "1"]])["records"]
    strings = list(csv.DictReader(io.StringIO(_csv_for_test(prior))))
    same = preview([["2026-10-01", "1.0"]], existing_records=strings)
    assert same["accepted"] and same["summary"]["duplicate_record_groups"] == 1
    revised = preview([["2026-10-01", "3"]], meta=metadata(captured_at="2026-10-26T12:00:00Z"), existing_records=strings)
    assert revised["accepted"] and len(revised["records"]) == 1 and revised["summary"]["overlap_pairs"] == 1


def _csv_for_test(records):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(records[0]))
    writer.writeheader()
    writer.writerows(records)
    return stream.getvalue()


@pytest.mark.parametrize("change", [{"account": "other-artist"}, {"entity_id": "other-entity"},
    {"filters": {"country": "US"}}, {"report_scope": "different report"}])
def test_different_artist_entity_filter_and_report_scopes_are_not_pooled(change):
    prior = preview([["2026-10-01", "1"]])["records"]
    result = preview([["2026-10-01", "8"]], meta=metadata(**change), existing_records=prior)
    assert result["accepted"] and result["summary"]["overlap_pairs"] == 0


def test_different_definitions_are_separate_and_bad_prior_values_are_review_errors():
    prior = preview([["2026-10-01", "1"]])["records"]
    config = mapping()
    config["metrics"][0]["definition"] = "A different reviewed metric definition."
    result = preview([["2026-10-01", "8"]], config=config, existing_records=prior)
    assert result["accepted"] and result["summary"]["overlap_pairs"] == 0
    broken = deepcopy(prior)
    broken[0].update(value_exact="", value="bad")
    assert not preview([["2026-10-01", "1"]], existing_records=broken)["accepted"]
    del broken[0]["report_scope"]
    assert not preview([["2026-10-01", "1"]], existing_records=broken)["accepted"]


def test_fixed_scope_survives_canonical_column_projection_and_reserved_dimensions_cannot_shadow_it():
    unrestricted = preview([["2026-10-01", "1"]])["records"][0]
    filtered = preview([["2026-10-01", "1"]], meta=metadata(filters={"country": "US"}))["records"][0]
    projected = {key: filtered[key] for key in COLUMNS}
    scope = json.loads(projected["dimensions_json"])["_apple_music_scope"]
    assert scope == {"source_kind": "artists_csv", "report_scope": "Synthetic native report scope", "filters": {"country": "US"}}
    assert projected["dimensions_json"] != unrestricted["dimensions_json"]
    config = mapping()
    config["dimensions"] = {"_apple_music_scope": "Day"}
    assert not preview([["2026-10-01", "1"]], config=config)["accepted"]


def test_contradictory_status_and_overflow_never_silently_remove_or_create_numeric_values():
    config = mapping()
    config["metrics"][0].update(status_column="Label", status_map={"Not available": "unavailable"})
    source = raw([["2026-10-01", "7", "Not available"]], headers=("Day", "Amount", "Label"))
    assert not preview_export(source, "native.csv", config, metadata())["accepted"]
    config = mapping("average_daily_listeners", "period")
    assert not preview([["unused", "9" * 400 + ".1"]], config=config, meta=metadata(period_start="2026-10-01", period_end="2026-10-07"))["accepted"]
    assert not preview([["unused", "0." + "0" * 400 + "1"]], config=config, meta=metadata(period_start="2026-10-01", period_end="2026-10-07"))["accepted"]
    assert not preview([["2026-10-01", "9" * 400]])["accepted"]


@pytest.mark.parametrize("change", [{"account": {"bad": "object"}}, {"account": "<APPLE_ID>"}, {"captured_at": 123}, {"source_kind": "provider_api"}])
def test_wrong_identity_capture_and_source_family_types_are_rejected(change):
    assert not preview([["2026-10-01", "1"]], meta=metadata(**change))["accepted"]


def test_malformed_mapping_json_types_return_review_errors():
    for field, value in (("time_grain", []), ("metrics", [{"metric": []}]), ("columns", {"date": []})):
        config = mapping()
        config[field] = value
        assert not preview([["2026-10-01", "1"]], config=config)["accepted"]


def test_staging_is_exclusive_source_preserving_and_retains_rejected_review(stage_roots):
    source = raw([["2026-10-01", "0"]])
    output = stage_roots / "stage"
    receipt = stage_preview(source, "native.csv", mapping(), metadata(), output)
    assert receipt["accepted"] and not receipt["library_modified"]
    assert (output / "raw/native.csv").read_bytes() == source
    assert json.loads((output / "preview.json").read_text())["records"][0]["value_status"] == "observed_zero"
    with pytest.raises(FileExistsError):
        stage_preview(source, "native.csv", mapping(), metadata(), output)
    rejected = stage_roots / "rejected"
    receipt = stage_preview(raw([["2026-10-01", "1.2K"]]), "native.csv", mapping(), metadata(), rejected)
    assert not receipt["accepted"] and (rejected / "raw/native.csv").is_file()
    with pytest.raises(ValueError):
        stage_preview(source, "../escape.csv", mapping(), metadata(), stage_roots / "unsafe")
    assert not (stage_roots / "unsafe").exists()
    with pytest.raises(ValueError):
        stage_preview(source, "native.csv", mapping(), metadata(), stage_roots / "protected-library/stage")
