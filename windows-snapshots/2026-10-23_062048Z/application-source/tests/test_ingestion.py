import io
from datetime import datetime

import pandas as pd
import pytest

from stats_app.ingestion import parse_export, read_table, sheet_names
from stats_app.validation import numeric_value, validate_records


META = {"account": "Fixture artist", "entity_type": "artist", "entity_id": "fixture-id", "source_timezone": "UTC"}


def test_spotify_native_missing_zero_rolling_and_row_provenance():
    raw = b"date,streams,listeners,monthly listeners,followers\n2026-10-20,0,,100,10\n2026-10-21,12,4,105,12\n"
    df = read_table(raw, "native.csv")
    parsed = parse_export(df, "spotify_daily", META)
    assert validate_records(parsed) == []
    streams = parsed[parsed.metric == "streams"]
    assert streams.value.tolist() == [0, 12]
    assert parsed[parsed.metric == "listeners"].iloc[0].status == "missing"
    rolling = parsed[parsed.metric == "monthly_listeners"].iloc[0]
    assert rolling.period_start == "2026-09-23"
    assert rolling.measurement_type == "rolling_count"
    assert streams.source_row.tolist() == [2, 3]
    assert raw.startswith(b"date,streams")


def test_ragged_rows_rejected_not_dropped():
    with pytest.raises(ValueError, match="Source row 3"):
        read_table(b"date,streams\n2026-10-20,2\n2026-10-21,3,extra\n", "x.csv")


def test_malformed_dates_and_rounded_numbers_rejected():
    df = read_table(b"date,streams\n10/11/2026,4\n", "x.csv")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        parse_export(df, "spotify_daily", META)
    with pytest.raises(ValueError, match="exact number"):
        numeric_value("1.2K")
    with pytest.raises(ValueError):
        numeric_value("1,2")
    assert numeric_value("1,234") == (1234, "observed")


def test_meta_utf16_with_preamble_and_missing_dates_preserved():
    text = '"Views"\n"Date","Primary"\n"2026-10-20","10"\n"2026-10-22",""\n'
    df = read_table(text.encode("utf-16"), "Views.csv")
    parsed = parse_export(df, "meta_daily", {**META, "platform": "Facebook", "metric": "views", "measurement_type": "period_count", "unit": "count"})
    assert len(parsed) == 2
    assert parsed.period_start.tolist() == ["2026-10-20", "2026-10-22"]
    assert parsed.source_row.tolist() == [3, 4]
    assert parsed.iloc[1].status == "missing"
    assert validate_records(parsed) == []


def test_mapping_explicit_identity_status_and_percent_units():
    df = read_table(b"When,Amount\n2026-10-20,12%\n", "manual.csv")
    metadata = {**META, "platform": "TikTok", "metric": "completion_rate", "unit": "percent", "time_grain": "period", "measurement_type": "rate"}
    parsed = parse_export(df, "canonical", metadata, {"period_start": "When", "period_end": "When", "value": "Amount"})
    assert parsed.iloc[0].value == 12
    assert validate_records(parsed) == []
    metadata["unit"] = "fraction"
    with pytest.raises(ValueError, match="Percent-marked"):
        parse_export(df, "canonical", metadata, {"period_start": "When", "period_end": "When", "value": "Amount"})


def test_invalid_status_value_pair_blocks_batch():
    df = parse_export(read_table(b"date,streams\n2026-10-20,1\n", "a.csv"), "spotify_daily", META)
    df.loc[0, "status"] = "missing"
    assert any("blank value" in message for message in validate_records(df))
    df.loc[0, "value"] = None
    df.loc[0, "account"] = ""
    assert any("account is required" in message for message in validate_records(df))


def test_excel_worksheet_selection_preserves_string_ids():
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame({"id": ["00123"], "value": [1]}).to_excel(writer, sheet_name="Records", index=False)
        pd.DataFrame({"id": ["other"]}).to_excel(writer, sheet_name="Other", index=False)
    assert sheet_names(buffer.getvalue()) == ["Records", "Other"]
    df = read_table(buffer.getvalue(), "a.xlsx", "Records")
    assert df.iloc[0]["id"] == "00123"
    assert df.attrs["worksheet"] == "Records"


def test_suppression_is_not_zero():
    assert numeric_value("<5") == (None, "suppressed")
    assert numeric_value("unavailable") == (None, "unavailable")
    assert numeric_value("0") == (0, "observed")


def test_excel_dates_are_unambiguous_and_duplicate_headers_fail():
    import openpyxl
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.append(["date", "streams"])
    worksheet.append([datetime(2026, 10, 20), 2])
    buffer = io.BytesIO()
    workbook.save(buffer)
    parsed = parse_export(read_table(buffer.getvalue(), "daily.xlsx"), "spotify_daily", META)
    assert parsed.iloc[0].period_end == "2026-10-20"
    worksheet.cell(1, 2).value = "date"
    buffer = io.BytesIO()
    workbook.save(buffer)
    with pytest.raises(ValueError, match="Duplicate headers"):
        read_table(buffer.getvalue(), "bad.xlsx")


def test_capture_date_preserves_granularity_and_status_contract():
    df = parse_export(read_table(b"date,streams\n2026-10-20,1\n", "a.csv"), "spotify_daily", META)
    df.loc[0, "captured_at"] = "2026-10-22"
    assert validate_records(df) == []
    df.loc[0, "captured_at"] = "2026-10-22T09:00:00"
    assert any("UTC offset" in error for error in validate_records(df))
    df.loc[0, "captured_at"] = "2026-10-22T09:00:00-04:00"
    assert validate_records(df) == []
    df.loc[0, "status"] = "not_applicable"
    df.loc[0, "value"] = None
    assert any("unknown status" in error for error in validate_records(df))
