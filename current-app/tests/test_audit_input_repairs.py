"""Regression boundaries from the October 25 input/program audit."""
from copy import deepcopy
import warnings

import pandas as pd
import pytest

from stats_app.analysis_content import CONTENT_PATH, load_content_observations, normalize_content
from stats_app.analysis_spikes import publication_capture_context
from stats_app.apple_music import preview_export
from stats_app.content_summaries import content_distribution_rows
from stats_app.ingestion import parse_export, read_table
from stats_app.validation import validate_records


@pytest.mark.parametrize("filename,delimiter,encoding", [
    ("mapped.csv", ",", "utf-8"), ("mapped.tsv", "\t", "utf-8"), ("mapped.csv", ",", "utf-16"),
])
def test_data_day_date_values_do_not_replace_an_established_header(filename, delimiter, encoding):
    text = "\n".join(delimiter.join(row) for row in [
        ("ID", "Value"), ("first", "1"), ("Day", "25"), ("Date", "36"), ("last", "2"),
    ])
    frame = read_table(text.encode(encoding), filename)
    assert frame.columns.tolist() == ["ID", "Value"]
    assert frame.ID.tolist() == ["first", "Day", "Date", "last"]
    assert frame.attrs["source_rows"] == [2, 3, 4, 5]
    assert frame.attrs["header_row"] == 1
    records = parse_export(frame, "canonical", dict(platform="TikTok", account="synthetic", entity_type="video",
        metric="video_views", unit="count", period_start="2026-10-01", period_end="2026-10-01",
        time_grain="daily", measurement_type="period_count"), {"entity_id": "ID", "value": "Value"})
    assert validate_records(records) == []
    assert records.entity_id.tolist() == frame.ID.tolist()
    assert records.value.tolist() == [1, 25, 36, 2]


def test_known_utf16_meta_title_preamble_keeps_native_lineage_and_missing_values():
    raw = '"Views"\r\n\r\n"Date","Primary"\r\n"2026-10-20","0"\r\n"2026-10-22",""\r\n'.encode("utf-16")
    frame = read_table(raw, "Views.csv")
    assert frame.columns.tolist() == ["Date", "Primary"]
    assert frame.attrs["header_row"] == 3
    records = parse_export(frame, "meta_daily", dict(platform="Facebook", account="synthetic", entity_type="account",
        entity_id="synthetic", metric="views", unit="count", measurement_type="period_count"))
    assert validate_records(records) == []
    assert records.source_row.tolist() == [4, 5]
    assert records.status.tolist() == ["observed", "missing"]
    assert records.iloc[0].value == 0 and pd.isna(records.iloc[1].value)


@pytest.mark.parametrize("raw", [
    b'"Views"\n"Unverified subtitle"\nDate,Primary\n2026-10-20,1\n',
    b'"Views"\nMeta,Report\nDate,Primary\n2026-10-20,1\n',
    b'"Views"\nDay,25\nlast,2\n',
])
def test_ambiguous_preamble_is_rejected_instead_of_skipping_records(raw):
    with pytest.raises(ValueError, match="Ambiguous CSV preamble"):
        read_table(raw, "source.csv")


def test_single_column_day_date_records_remain_ordinary_data():
    frame = read_table(b"ID\nDay\nDate\nlast\n", "one.csv")
    assert frame.ID.tolist() == ["Day", "Date", "last"]


def apple_contract():
    mapping = dict(schema_version=1, time_grain="daily", date_format="%Y-%m-%d",
        columns={"date": "Day"}, dimensions={}, metrics=[dict(metric="plays", column="Amount", unit="count",
        measurement_basis="period_count", definition="Synthetic reviewed Apple plays")])
    metadata = dict(source_kind="artists_csv", account="synthetic", entity_type="artist", entity_id="synthetic",
        source_timezone="UTC", report_scope="Synthetic export", captured_at="2026-10-25T00:00:00Z")
    return mapping, metadata


@pytest.mark.parametrize("status,value,exact", [
    ("invented", None, ""), ("", None, ""), ("missing", 1, ""), ("suppressed", 0, ""),
    ("unavailable", None, "0"), ("observed", None, ""),
])
def test_apple_malformed_prior_status_value_relationship_rejects_review(status, value, exact):
    mapping, metadata = apple_contract()
    raw = b"Day,Amount\n2026-10-01,1\n"
    initial = preview_export(raw, "native.csv", mapping, metadata)
    prior = deepcopy(initial["records"])
    prior[0].update(status=status, value=value, value_exact=exact)
    metadata["captured_at"] = "2026-10-26T00:00:00Z"
    result = preview_export(raw, "native.csv", mapping, metadata, existing_records=prior)
    assert not result["accepted"]
    assert any(item["code"] == "invalid_comparison_record" for item in result["issues"])
    assert initial["records"][0]["value"] == 1


@pytest.mark.parametrize("status", ["missing", "suppressed", "unavailable"])
def test_apple_valid_blank_prior_status_stays_distinct_from_observed_zero(status):
    mapping, metadata = apple_contract()
    raw = b"Day,Amount\n2026-10-01,0\n"
    prior = deepcopy(preview_export(raw, "native.csv", mapping, metadata)["records"])
    prior[0].update(status=status, value=None, value_exact="")
    metadata["captured_at"] = "2026-10-26T00:00:00Z"
    result = preview_export(raw, "native.csv", mapping, metadata, existing_records=prior)
    assert result["accepted"]
    assert result["records"][0]["value"] == 0
    assert result["records"][0]["value_status"] == "observed_zero"
    assert result["summary"]["duplicate_record_groups"] == 0


def content_record(post_id, value, status):
    return dict(platform_selected="Instagram", selected_account_id="synthetic", account_id_type="native_account",
        post_id=post_id, post_type="IG story", views=value, views_status=status, author_scope="band_authored",
        metric_platform_scope="Instagram", measurement_type="lifetime_content_snapshot", publication_date="2026-10-01",
        snapshot_timestamp="2026-10-25T00:00:00Z", publication_timezone="UTC")


@pytest.mark.parametrize("value,status,expected", [
    ("-5", "observed", "invalid_count_source_value"),
    ("1.5", "observed", "invalid_count_source_value"),
    ("7", "observed_zero", "invalid_count_status"),
    ("7", "zero", "invalid_count_status"),
    ("", "observed", "invalid_count_status"),
    ("unparsed", "observed", "invalid_count_source_value"),
    ("9007199254740993", "observed", "invalid_count_source_value"),
    ("7", "unavailable", "invalid_count_status"),
])
def test_invalid_content_counts_keep_raw_values_and_have_no_analytical_quantity(value, status, expected):
    frame = pd.DataFrame([content_record("one", value, status)])
    before = frame.copy(deep=True)
    row = normalize_content(frame, CONTENT_PATH).iloc[0]
    assert pd.isna(row.views)
    assert row.views_raw == value and row.views_normalized_raw == value
    assert row.views_status_raw == status and row.views_status == expected
    pd.testing.assert_frame_equal(frame, before)


def test_invalid_content_values_do_not_enter_distributions_or_spike_quantities():
    source = [content_record("negative", "-5", "observed"), content_record("fraction", "1.5", "observed"),
              content_record("zero-conflict", "7", "observed_zero"), content_record("zero", "0", "observed_zero"),
              content_record("nine", "9", "observed")]
    class Repo:
        tables = [CONTENT_PATH]
        def table(self, path, raw=False):
            return pd.DataFrame(source)
    observations = load_content_observations(Repo())
    distribution = next(row for row in content_distribution_rows(observations) if row["metric"] == "views")
    assert distribution["observed"] == 2 and distribution["missing"] == 3
    assert distribution["median"] == 4.5 and distribution["maximum"] == 9
    context = publication_capture_context(observations, observations[["identity_key"]])
    views = context.loc[context.metric.eq("views")].set_index("post_id")
    assert views.loc[["negative", "fraction", "zero-conflict"], "value"].isna().all()
    assert views.loc[["negative", "fraction", "zero-conflict"], "value_status"].str.startswith("invalid_").all()
    assert views.loc["zero", "value"] == 0 and views.loc["zero", "value_status"] == "observed_zero"


def test_content_original_raw_token_is_not_replaced_by_normalized_invalid_value():
    source = content_record("one", "-5", "observed")
    source["views_raw"] = "Native retained token"
    row = normalize_content(pd.DataFrame([source]), CONTENT_PATH).iloc[0]
    assert row.views_raw == "Native retained token"
    assert row.views_normalized_raw == "-5" and row.views_status_raw == "observed"
    assert pd.isna(row.views) and row.views_status.startswith("invalid_")


def test_story_audit_week_preselection_keeps_boundaries_without_timedelta_deprecation(monkeypatch):
    from scripts import audit_story_backfill_comparison as audit
    identities = pd.DataFrame(dict(week=["", "2026-02-09", "2026-02-16", "2026-02-23", "2026-03-02"]))
    seen = {}
    def strict_selector(candidates, target):
        seen["target"] = target
        return candidates.copy()
    monkeypatch.setattr(audit, "publications_around_week", strict_selector)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        result = audit.nearby_publications(identities, "2026-02-23")
    assert result.week.tolist() == ["2026-02-16", "2026-02-23"]
    assert seen["target"] == pd.Timestamp("2026-02-23")
