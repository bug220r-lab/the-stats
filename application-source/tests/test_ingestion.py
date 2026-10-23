import io
import json
from datetime import datetime

import pandas as pd
import pytest
from openpyxl import Workbook

from stats.ingestion import (FIELDS, parse_date, parse_number, preview_import,
                             read_table, safe_csv, suggest_mapping, worksheets)
from stats.storage import Store


def canonical(value=12, **changes):
    row = dict(platform="spotify", account_id="artist:001", account_name="Test Artist",
               entity_type="track", entity_id="track:0001", entity_name="Test Song",
               metric="streams", value=value, unit="count", definition="Verified stream events",
               dimensions='{"country":"US"}', period_start="2026-10-19", period_end="2026-10-19",
               time_grain="daily", captured_at="2026-10-20", source_timezone="",
               measurement_type="period_count", status="verified", source_row=2,
               evidence_ref="original.csv#row=2", published_at="", source_url="")
    row.update(changes)
    return row


def preview(frame, mapping=None, raw=b"fixture", filename="fixture.csv"):
    return preview_import(frame, mapping or suggest_mapping(frame), filename, raw)


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_canonical_roundtrip_through_store(extension, tmp_path):
    original = pd.DataFrame([canonical(), canonical(0, entity_id="track:0002"),
                             canonical(None, entity_id="track:0003", status="suppressed")], columns=FIELDS)
    if extension == "csv":
        raw = safe_csv(original)
        worksheet = "CSV"
    else:
        buffer = io.BytesIO()
        original.to_excel(buffer, index=False, sheet_name="Readings")
        raw = buffer.getvalue()
        worksheet = "Readings"
    filename = "canonical." + extension
    assert worksheets(raw, filename) == [worksheet]
    frame = read_table(raw, filename, worksheet)
    result = preview_import(frame, suggest_mapping(frame), filename, raw, worksheet)
    assert not [issue for issue in result["issues"] if issue["severity"] == "error"]
    assert len(result["observations"]) == 3
    assert [row["value"] for row in result["observations"]] == [12, 0, None]
    assert [row["status"] for row in result["observations"]] == ["verified", "verified", "suppressed"]
    assert result["observations"][0]["entity_id"] == "track:0001"
    assert result["observations"][0]["captured_at"] == "2026-10-20"
    assert result["observations"][0]["source_timezone"] is None
    store = Store(tmp_path / "test.sqlite3")
    snapshot = store.create_snapshot("Fixture")
    store.commit_import(snapshot, filename, raw, result["observations"], worksheet)
    persisted = store.read_observations(snapshot)
    assert persisted.iloc[0]["value"] == 12
    assert persisted.iloc[1]["value"] == 0
    assert pd.isna(persisted.iloc[2]["value"])
    assert json.loads(persisted.iloc[0]["dimensions"]) == {"country": "US"}


@pytest.mark.parametrize("value,locale,number,status,percent", [
    ("1,234.5", "en_US", 1234.5, "available", False),
    ("1.234,5", "de_DE", 1234.5, "available", False),
    ("12,5%", "de_DE", 12.5, "available", True),
    (0, "en_US", 0, "available", False),
    (0.25, "de_DE", 0.25, "available", False),
    ("0", "en_US", 0, "available", False),
    ("", "en_US", None, "missing", False),
    ("N/A", "en_US", None, "missing", False),
    ("—", "en_US", None, "missing", False),
    ("<5", "en_US", None, "suppressed", False),
    ("suppressed", "en_US", None, "suppressed", False),
])
def test_numeric_locale_and_availability(value, locale, number, status, percent):
    assert parse_number(value, locale) == (number, status, percent)


@pytest.mark.parametrize("value,locale", [("1,23", "en_US"), ("1.23", "de_DE"),
                                          ("1,2,3", "en_US"), (float("inf"), "en_US")])
def test_numeric_ambiguity_and_infinity_are_rejected(value, locale):
    with pytest.raises(ValueError):
        parse_number(value, locale)


def test_percentage_units_and_excel_percentage_cells():
    ratio = pd.DataFrame([canonical("25%", metric="custom_rate", unit="ratio",
                                   definition="Actions divided by impressions", measurement_type="rate")])
    assert preview(ratio)["observations"][0]["value"] == 0.25
    ratio["unit"] = "percent"
    assert preview(ratio)["observations"][0]["value"] == 25
    ratio["unit"] = "count"
    assert not preview(ratio)["observations"]
    assert "Percentage value" in preview(ratio)["issues"][0]["message"]
    book = Workbook()
    sheet = book.active
    sheet.title = "Readings"
    row = canonical(0.25, metric="custom_rate", unit="ratio", measurement_type="rate",
                    definition="Actions divided by impressions")
    sheet.append(FIELDS)
    sheet.append([row.get(field) for field in FIELDS])
    sheet.cell(2, FIELDS.index("value") + 1).number_format = "0.0%"
    buffer = io.BytesIO()
    book.save(buffer)
    table = read_table(buffer.getvalue(), "rate.xlsx", "Readings")
    assert table.loc[0, "value"] == "25%"
    assert preview(table)["observations"][0]["value"] == 0.25


def test_dates_require_explicit_order_and_preserve_source_bucket():
    with pytest.raises(ValueError):
        parse_date("10/11/2026")
    assert parse_date("10/11/2026", "MDY") == "2026-10-11"
    assert parse_date("10/11/2026", "DMY") == "2026-11-10"
    assert parse_date(datetime.fromisoformat("2026-10-20T23:59:00-07:00")) == "2026-10-20"
    assert parse_date("") is None
    data = pd.DataFrame([canonical(captured_at="", source_timezone="")])
    row = preview(data)["observations"][0]
    assert row["captured_at"] is None
    assert row["source_timezone"] is None
    assert row["period_start"] == "2026-10-19"


def test_source_verification_status_is_not_overwritten_by_missing_value():
    result = preview(pd.DataFrame([canonical(None, status="verified")]))
    assert result["observations"][0]["status"] == "verified"
    assert result["observations"][0]["value"] is None
    assert any(issue.get("code") == "missing_value" for issue in result["issues"])


def test_invalid_rows_report_source_positions_without_losing_valid_rows():
    frame = pd.DataFrame([canonical(8), canonical("broken", source_row=3),
                          canonical(3, source_row=4, period_start="10/11/2026")])
    result = preview(frame)
    assert len(result["observations"]) == 1
    errors = [issue for issue in result["issues"] if issue["severity"] == "error"]
    assert [issue["source_row"] for issue in errors] == [3, 4]
    assert errors[0]["raw_value"] == "broken"


def test_source_rows_include_blank_lines_and_do_not_depend_on_dataframe_index():
    raw = b"Date,Streams\n2026-10-19,5\n,\n2026-10-20,7\n"
    frame = read_table(raw, "native.csv")
    frame.index = [100, 200, 300]
    mapping = suggest_mapping(frame, {"platform": "spotify", "account_id": "artist:1",
                                      "entity_type": "artist", "time_grain": "daily"})
    result = preview(frame, mapping, raw=raw)
    assert [row["source_row"] for row in result["observations"]] == ["2", "4"]


def test_ids_never_merge_entities_by_equal_names():
    frame = pd.DataFrame([canonical(10, entity_id="track:1"), canonical(10, entity_id="track:2")])
    result = preview(frame)
    assert {row["entity_id"] for row in result["observations"]} == {"track:1", "track:2"}
    frame["entity_id"] = ""
    frame["source_row"] = [2, 3]
    result = preview(frame)
    assert len({row["entity_id"] for row in result["observations"]}) == 2
    assert any(issue.get("code") == "source_scoped_identity" for issue in result["issues"])
    other = preview(frame, raw=b"other-file")
    assert result["observations"][0]["entity_id"] != other["observations"][0]["entity_id"]


def test_native_spotify_artist_daily_requires_identity_and_preserves_all_metrics():
    raw = (b"date,listeners,monthly listeners,monthly active listeners,super listeners,streams,playlist adds,saves,followers\n"
           b"2024-01-01,6,121,76,4,10,0,0,58\n")
    frame = read_table(raw, "artist_daily.csv")
    inferred = suggest_mapping(frame)
    assert inferred["detected_format"] == "spotify_artist_daily"
    assert inferred["defaults"] == {}
    assert not preview(frame, inferred)["observations"]
    explicit = suggest_mapping(frame, {"platform": "spotify", "account_id": "artist:1", "entity_type": "artist"})
    assert explicit["defaults"]["time_grain"] == "daily"
    result = preview(frame, explicit)
    assert len(result["observations"]) == 8
    assert sum(row["value"] for row in result["observations"] if row["metric"] == "streams") == 10
    by_metric = {row["metric"]: row for row in result["observations"]}
    assert by_metric["monthly_active_listeners"]["measurement_type"] == "rolling_window_count"
    assert by_metric["super_listeners"]["measurement_type"] == "rolling_window_count"
    assert by_metric["followers"]["measurement_type"] == "point_in_time_count"
    assert by_metric["listeners"]["measurement_type"] == "distinct_audience_count"
    assert by_metric["streams"]["captured_at"] is None
    assert by_metric["streams"]["source_timezone"] is None


def test_conflicting_rows_and_changed_status_are_reported():
    for second in [canonical(13), canonical(12, status="unverified")]:
        result = preview(pd.DataFrame([canonical(), second]))
        assert any("Conflicting rows" in issue["message"] for issue in result["issues"])


def test_different_timezone_date_buckets_are_not_duplicate_observations():
    result = preview(pd.DataFrame([canonical(source_timezone="UTC"),
                                   canonical(source_timezone="America/New_York")]))
    assert len(result["observations"]) == 2
    assert not any("Duplicate observation" in issue["message"] or "Conflicting rows" in issue["message"]
                   for issue in result["issues"])


def test_csv_formula_neutralization_keeps_numeric_values():
    exported = safe_csv(pd.DataFrame({"name": ["=SUM(A1:A2)", "+cmd"], "value": [-4, 0]})).decode("utf-8-sig")
    assert "'=SUM" in exported
    assert "'+cmd" in exported
    assert ",-4" in exported
