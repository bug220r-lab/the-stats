from pathlib import Path
import json
import pytest

from scripts.normalize_meta_collection import number, native_csv, ads_rows, follow_rows, compare_follows, manual_follows, manual_story_rows, reconcile_ad_levels, resolved_follows, story_metric_rows


def meta():
    return dict(captured_at_utc="2026-10-23T04:00:00+00:00", acquired_at_utc="", capture_precision="exact_observation",
                filesystem_modified_at_utc="2026-10-23T04:00:01+00:00", reporting_timezone="Eastern Time", ad_account_id="123",
                reporting_start="2023-09-23", reporting_end="2026-10-23")


def test_blank_is_not_zero_and_nonfinite_is_rejected():
    assert number("") == ("", "missing_source_blank")
    assert number("0") == ("0", "observed_zero")
    assert number("1,234.50") == ("1234.50", "observed")
    assert number("‑‑") == ("", "unavailable_source_marker")
    with pytest.raises(ValueError): number("NaN")


def test_csv_ragged_records_are_quarantined_without_guessing(tmp_path):
    p = tmp_path / "stories.csv"
    p.write_text('Post ID,Views,Reach\n123,4,3\n124,9\n', encoding="utf-8")
    header, rows, bad = native_csv(p)
    assert rows == [(2, {"Post ID": "123", "Views": "4", "Reach": "3"})]
    assert bad[0]["actual_fields"] == 2 and bad[0]["expected_fields"] == 3


def test_native_ads_window_not_ui_window_and_blank_clicks_not_zero(tmp_path):
    p = tmp_path / "ads_campaigns.csv"
    p.write_text('Reporting starts,Reporting ends,Campaign name,Campaign delivery,Amount spent (USD),Link clicks\n2023-09-23,2024-07-09,Same,archived,4.07,\n2023-09-23,2024-07-09,Same,inactive,104.98,110\n', encoding="utf-8")
    rows, summary = ads_rows(tmp_path, p, meta())
    assert len(rows) == 2 and rows[0]["reporting_end"] == "2024-07-09"
    assert rows[0]["native_window_vs_ui"] == "differs"
    assert rows[0]["Link clicks"] == ""
    assert summary["spend_total_native_rows"] == "109.05"
    assert summary["native_id_missing_rows"] == 2


def test_repeated_daily_ad_identity_refused(tmp_path):
    p = tmp_path / "ads_daily.csv"
    p.write_text('Reporting starts,Reporting ends,Ad ID,Ad name,Amount spent (USD)\n2024-04-12,2024-04-12,123,Name,5\n2024-04-12,2024-04-12,123,Name,6\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        ads_rows(tmp_path, p, meta())


def test_no_data_available_notice_is_not_a_zero_spend_row(tmp_path):
    p = tmp_path / "ads_daily_2026.csv"
    p.write_text('Reporting starts,Reporting ends,Ad name,Amount spent (USD)\n"No data available."\n', encoding="utf-8")
    rows, report = ads_rows(tmp_path, p, meta())
    assert rows == []
    assert report["export_status"] == "native_no_data_available_notice"
    assert report["spend_total_native_rows"] == "" and report["native_start"] == ""


def test_unique_reach_and_frequency_never_receive_export_sums(tmp_path):
    p = tmp_path / "ads_daily.csv"
    p.write_text('Reporting starts,Reporting ends,Ad ID,Ad name,Reach,Frequency,Amount spent (USD)\n2024-04-12,2024-04-12,123,Name,20,1.2,5\n2024-04-13,2024-04-13,123,Name,20,1.3,6\n', encoding="utf-8")
    _, report = ads_rows(tmp_path, p, meta())
    coverage = json.loads(report["metric_coverage_json"])
    assert coverage["Reach"]["observed_sum"] == coverage["Frequency"]["observed_sum"] == ""
    assert coverage["Amount spent (USD)"]["observed_sum"] == "11"


def test_sparse_follows_does_not_create_absent_dates(tmp_path):
    p = tmp_path / "instagram_follows.csv"
    p.write_text('sep=,\n"Instagram follows"\n"Date","Primary"\n"2026-10-04T00:00:00","2"\n"2026-10-08T00:00:00","1"\n', encoding="utf-8")
    rows = follow_rows(tmp_path, p, meta())
    assert [r["date"] for r in rows] == ["2026-10-04", "2026-10-08"]


def test_explicit_zero_resolves_only_its_day_and_conflicts_stay_visible():
    prior = [dict(selected_account_id="a", date="2026-10-01", platform_selected="Instagram", metric="follows", value=None, value_status="missing"),
             dict(selected_account_id="a", date="2026-10-02", platform_selected="Instagram", metric="follows", value=2, value_status="observed")]
    rows = compare_follows([dict(selected_account_id="a", date="2026-10-01", value="0", reporting_timezone="Pacific Time"), dict(selected_account_id="a", date="2026-10-02", value="3", reporting_timezone="Pacific Time")], prior)
    assert rows[0]["comparison_status"] == "prior_missing_resolved_by_explicit_daily_evidence"
    assert rows[1]["comparison_status"] == "conflicts_with_prior_observation"
    assert all(not r["canonical_update_applied"] for r in rows)


def test_disagreeing_new_follows_evidence_refused():
    with pytest.raises(ValueError, match="disagrees"):
        compare_follows([dict(selected_account_id="a", date="2026-10-01", value="0"), dict(selected_account_id="a", date="2026-10-01", value="1")], [])


def test_unknown_timezone_cannot_resolve_a_missing_canonical_date():
    prior = [dict(selected_account_id="a", date="2026-10-01", platform_selected="Instagram", metric="follows", value=None, value_status="missing")]
    row = compare_follows([dict(selected_account_id="a", date="2026-10-01", value="0", reporting_timezone="")], prior)[0]
    assert row["comparison_status"] == "comparison_requires_verified_matching_timezone"


def test_manual_zero_requires_single_day_url_and_explicit_panel(tmp_path):
    url = 'https://business.facebook.com/latest/insights/results?asset_id=118246571240106&platform=Instagram&time_range=%7B%22start%22%3A%222026-10-01%22%2C%22end%22%3A%222026-10-01%22%7D'
    evidence = tmp_path / "screen.txt"
    evidence.write_text(url + '\n1 heading Follows\n2 text 0\n3 heading No activity during selected date range\n', encoding="utf-8")
    payload = [dict(date="2026-10-01", value=0, evidence_ref="screen.txt", source_url=url, captured_at_utc="2026-10-23T04:00:00Z")]
    (tmp_path / "manual_follows_observations.json").write_text(json.dumps(payload), encoding="utf-8")
    assert manual_follows(tmp_path)[0]["value_status"] == "observed_zero"
    evidence.write_text(url + '\n1 heading Follows\n2 heading No activity during selected date range\n', encoding="utf-8")
    with pytest.raises(ValueError, match="explicit zero"):
        manual_follows(tmp_path)


def test_manual_story_only_observed_fields_and_unknown_timezone(tmp_path):
    (tmp_path / "raw").mkdir()
    url = 'https://business.facebook.com/latest/insights/object_insights/?asset_id=118246571240106&content_id=18021252035662859'
    (tmp_path / "raw/story.txt").write_text(url + '\nViews 31\nReach --\nInteractions 2', encoding="utf-8")
    payload = [dict(post_id="18021252035662859", selected_account_id="118246571240106", selected_account_id_type="Meta Business Suite asset",
                    evidence_ref="raw/story.txt", source_url=url, captured_at_utc="2026-10-23T04:00:00Z", published_local="Fri May 8, 5:52pm",
                    metrics={"Views": {"value": 31}, "Reach": {"value": None, "raw": "‑‑"}, "Interactions": {"value": 2}})]
    (tmp_path / "raw/story_manual_observations.json").write_text(json.dumps(payload), encoding="utf-8")
    row = manual_story_rows(tmp_path)[0]
    assert row["views"] == "31" and row["interactions"] == "2"
    assert row["reach"] == "" and row["reach_status"] == "unavailable_source_marker"
    assert row["reporting_timezone"] == "" and not row["canonical_update_applied"]
    assert row["selected_account_id"] == "118246571240106" and row["selected_account_id_type"] == "Meta Business Suite asset"
    fields = story_metric_rows([row])
    assert len(fields) == 3
    unavailable = next(r for r in fields if r["metric"] == "reach")
    assert unavailable["value"] == "" and unavailable["value_status"] == "unavailable_source_marker"
    assert unavailable["measurement_type"] == "lifetime_content_snapshot"


def test_ad_reconciliation_does_not_promote_blank_click_cells_to_observed():
    common = dict(ad_account_id="123", currency="USD", reporting_timezone="Eastern Time", attribution_setting="7-day click", metric_platform_scope="Meta", breakdowns_json="{}", reporting_start="2024-04-12", reporting_end="2024-04-12")
    parent = [{**common, "source_file": "campaign.csv", "Amount spent (USD)": "2", "Impressions": "10", "Link clicks": ""}]
    child = [{**common, "source_file": "daily.csv", "Amount spent (USD)": "2", "Impressions": "10", "Link clicks": ""}]
    rows = reconcile_ad_levels(parent, child)
    assert rows[0]["known_sums_match"]
    click = next(r for r in rows if r["metric"] == "Link clicks")
    assert click["known_sums_match"] and not click["all_metric_rows_observed"]


def test_resolved_daily_view_keeps_lineage_and_only_explicitly_repairs():
    common = dict(platform_selected="Instagram", metric="follows", selected_account_id="a", source_file="follows.csv", reporting_timezone="Pacific Time", snapshot_timestamp="2026-10-22T00:00:00Z")
    prior = [{**common, "date": "2026-10-18", "value": 2, "value_status": "observed", "partial_day": False},
             {**common, "date": "2026-10-19", "value": None, "value_status": "missing", "partial_day": False},
             {**common, "date": "2026-10-20", "value": None, "value_status": "missing", "partial_day": False},
             {**common, "date": "2026-10-21", "value": None, "value_status": "missing", "partial_day": True}]
    repair = dict(selected_account_id="a", date="2026-10-19", value="0", value_status="observed_zero", reporting_timezone="Pacific Time", source_file="manual.json", source_sha256="manualhash", source_record=1, evidence_ref="screen.txt", evidence_sha256="screenhash", captured_at_utc="2026-10-23T00:00:00Z")
    rows, partial = resolved_follows(prior, compare_follows([repair], prior), "dbhash", "assethash", {"raw/meta/follows.csv": "rawhash"})
    assert [r["value"] for r in rows] == ["2", "0", ""]
    assert rows[0]["source_file"] == "raw/meta/follows.csv" and rows[0]["source_sha256"] == "rawhash"
    assert rows[1]["source_kind"] == "verified_daily_repair" and rows[1]["evidence_sha256"] == "screenhash"
    assert rows[1]["predecessor_csv_record"] == 3 and rows[1]["predecessor_snapshot_timestamp"] == "2026-10-22T00:00:00Z"
    assert rows[1]["snapshot_timestamp"] == "2026-10-23T00:00:00Z"
    assert rows[2]["resolution_status"] == "unresolved"
    assert len(partial) == 1 and partial[0]["date"] == "2026-10-21" and partial[0]["value"] == ""
    assert prior[1]["value"] is None


def test_resolved_view_retains_prior_value_when_new_evidence_conflicts():
    prior = [dict(platform_selected="Instagram", metric="follows", selected_account_id="a", source_file="follows.csv", date="2026-10-20", value=2, value_status="observed")]
    incoming = dict(selected_account_id="a", date="2026-10-20", value="3", reporting_timezone="Pacific Time")
    rows, _ = resolved_follows(prior, compare_follows([incoming], prior), "dbhash", "assethash")
    assert rows[0]["value"] == "2"
    assert rows[0]["resolution_status"] == "prior_observation_retained_conflicting_new_evidence"
