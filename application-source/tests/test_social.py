import hashlib
import json

import pandas as pd
import pytest

from scripts.load_social import load_social
from stats.metrics import aggregate_metric
from stats.social import FACEBOOK_AUDIENCE_METRICS, FACEBOOK_POST_METRICS, INSTAGRAM_CONTENT_METRICS, parse_social_export
from stats.storage import Store


def metadata(**changes):
    result = {"platform": "facebook", "account_id": "001234", "account_name": "Fixture Band",
              "captured_at": "2026-10-23T01:49:31+00:00", "source_timezone": "America/Los_Angeles",
              "timezone_evidence": "Export-settings screenshot states Pacific time",
              "period_start": "2026-07-24", "period_end": "2026-07-25"}
    result.update(changes)
    return result


def audience_bytes(**changes):
    rows = []
    for day in ("07/24/2026", "07/25/2026"):
        row = {"Page ID": "001234", "Page name": "Fixture Band", "Data comment": "", "Date": day,
               **{column: 0 for column in FACEBOOK_AUDIENCE_METRICS}}
        row["Unique user engagements"] = 3
        row.update(changes)
        rows.append(row)
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")


def instagram_bytes():
    rows = []
    for post_id, account_id, username in [("post001", "ig001", "fixtureband"), ("post002", "ig002", "collaborator")]:
        rows.append({"Post ID": post_id, "Account ID": account_id, "Account username": username,
                     "Account name": "Fixture Band" if account_id == "ig001" else "Other Account",
                     "Description": "Fixture caption", "Duration (sec)": 11, "Publish time": "08/16/2026 10:38",
                     "Permalink": f"https://instagram.com/p/{post_id}/", "Post type": "IG reel",
                     "Data comment": "", "Date": "Lifetime", **{column: 4 for column in INSTAGRAM_CONTENT_METRICS}})
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")


def test_facebook_native_columns_keep_distinct_and_action_metrics_separate():
    result = parse_social_export(audience_bytes(), "audience.csv", "facebook_page_audience_daily_v1", metadata())
    assert len(result["observations"]) == 16
    assert not result["issues"]
    frame = pd.DataFrame(result["observations"])
    assert set(frame["account_id"]) == {"001234"}
    assert set(frame["source_timezone"]) == {"America/Los_Angeles"}
    assert set(frame["period_start"]) == {"2026-07-24", "2026-07-25"}
    unique = frame[frame["metric"] == "unique_user_engagements"]
    assert set(unique["measurement_type"]) == {"distinct_audience_count"}
    assert aggregate_metric(unique, "unique_user_engagements", "2026-07-24", "2026-07-25")["value"] is None
    assert "additive_period_total" not in result["reconciliation"]["unique_user_engagements"]
    assert result["reconciliation"]["negative_feedback_total"]["additive_period_total"] == 0


def test_unknown_or_missing_native_columns_fail_closed():
    raw = audience_bytes(**{"New ambiguous measure": 8})
    with pytest.raises(ValueError, match="Unknown columns"):
        parse_social_export(raw, "audience.csv", "facebook_page_audience_daily_v1", metadata())
    frame = pd.read_csv(__import__("io").BytesIO(audience_bytes())).drop(columns=["Unique user engagements"])
    with pytest.raises(ValueError, match="missing columns"):
        parse_social_export(frame.to_csv(index=False).encode(), "audience.csv", "facebook_page_audience_daily_v1", metadata())


def test_missing_suppressed_zero_and_invalid_values_are_reported():
    raw = audience_bytes(**{"Unique user engagements": "<5", "Overall negative feedback": "", "Overall negative feedback: Hide": 0,
                            "Overall negative feedback: Hide all": "broken"})
    result = parse_social_export(raw, "audience.csv", "facebook_page_audience_daily_v1", metadata())
    first = {row["metric"]: row for row in result["observations"] if row["source_row"] == 2}
    assert first["unique_user_engagements"]["value"] is None and first["unique_user_engagements"]["status"] == "suppressed"
    assert first["negative_feedback_total"]["value"] is None and first["negative_feedback_total"]["status"] == "missing"
    assert first["negative_feedback_hide"]["value"] == 0
    assert len([issue for issue in result["issues"] if issue["severity"] == "error"]) == 2


def test_unknown_capture_or_timezone_is_not_reconstructed():
    result = parse_social_export(audience_bytes(), "2026-10-22.csv", "facebook_page_audience_daily_v1", {})
    assert all(row["captured_at"] is None and row["source_timezone"] is None for row in result["observations"])
    assert {issue["code"] for issue in result["issues"]} == {"unknown_capture", "unknown_timezone"}
    with pytest.raises(ValueError, match="timezone_evidence"):
        parse_social_export(audience_bytes(), "a.csv", "facebook_page_audience_daily_v1", {"source_timezone": "America/Los_Angeles"})


def test_instagram_lifetime_keeps_accounts_and_has_no_invented_reporting_window():
    source = {"platform": "instagram", "account_id": "ig001", "account_username": "fixtureband",
              "captured_at": "2026-10-23T01:51:55+00:00", "source_timezone": "America/Los_Angeles",
              "timezone_evidence": "Export settings screenshot", "publication_selection_start": "2026-07-24",
              "publication_selection_end": "2026-10-21"}
    result = parse_social_export(instagram_bytes(), "instagram.csv", "instagram_post_lifetime_v1", source)
    assert len(result["observations"]) == 14
    assert set(result["accounts"]) == {"ig001", "ig002"}
    assert len([issue for issue in result["issues"] if issue["code"] == "other_exported_account"]) == 1
    assert all(row["period_start"] is None and row["period_end"] is None for row in result["observations"])
    assert all(row["time_grain"] == "lifetime" for row in result["observations"])
    assert all(row["published_at"] == "2026-08-16T10:38" for row in result["observations"])
    assert all(row["measurement_type"] == ("distinct_audience_count" if row["metric"] == "reach" else "cumulative_total") for row in result["observations"])
    assert all("additive_period_total" not in metric for metric in result["reconciliation"].values())
    collaborator = next(row for row in result["observations"] if row["account_id"] == "ig002")
    assert collaborator["entity_id"] == "post002"
    assert collaborator["source_url"].endswith("post002/")
    dimensions = json.loads(collaborator["dimensions"])
    assert dimensions["source_account_relationship"] == "other_exported_account"
    assert dimensions["publication_selection_start"] == "2026-07-24"
    with pytest.raises(ValueError, match="publication_selection"):
        parse_social_export(instagram_bytes(), "instagram.csv", "instagram_post_lifetime_v1", {**source, "period_start": "2026-07-24"})


def write_manifest(tmp_path, **file_changes):
    raw = audience_bytes()
    (tmp_path / "audience.csv").write_bytes(raw)
    file = {"path": "audience.csv", "sha256": hashlib.sha256(raw).hexdigest(),
            "parser": "facebook_page_audience_daily_v1", **metadata(), **file_changes}
    manifest = {"schema_version": 1, "snapshot_key": "test-meta-capture", "snapshot_name": "Separate Meta capture", "files": [file]}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path, raw


def test_loader_preview_never_creates_database_and_commit_is_separate_and_idempotent(tmp_path):
    manifest, original_raw = write_manifest(tmp_path)
    db = tmp_path / "stats.sqlite3"
    assert not load_social(manifest, db)["committed"]
    assert not db.exists()
    store = Store(db)
    older = store.create_snapshot("Existing snapshot")
    old_state = store.snapshots()
    first = load_social(manifest, db, commit=True)
    assert first["snapshot_id"] != older
    assert next(row for row in store.snapshots() if row["id"] == older) == old_state[0]
    assert store.read_observations(older).empty
    second = load_social(manifest, db, commit=True)
    assert second["snapshot_id"] == first["snapshot_id"]
    assert second["files"][0]["import_result"]["idempotent"]
    assert len(store.read_observations(first["snapshot_id"])) == 16
    assert (tmp_path / "audience.csv").read_bytes() == original_raw
    assert (store.source_dir / (hashlib.sha256(original_raw).hexdigest() + ".csv")).read_bytes() == original_raw


@pytest.mark.parametrize("changes,error", [({"sha256": "wrong"}, "checksum"),
                                          ({"captured_at": None}, "capture time"),
                                          ({"account_id": "other-account"}, "validation failed")])
def test_loader_finishes_all_preflight_before_creating_database(tmp_path, changes, error):
    manifest, _ = write_manifest(tmp_path, **changes)
    db = tmp_path / "stats.sqlite3"
    with pytest.raises(ValueError, match=error):
        load_social(manifest, db, commit=True)
    assert not db.exists()


def result_bytes(label="Views", days=("2026-07-24", "2026-07-25"), values=(8, 4)):
    return ('sep=,\n"' + label + '"\n"Date","Primary"\n' +
            "".join(f'"{day}T00:00:00","{value}"\n' for day, value in zip(days, values))).encode("utf-16")


def test_account_results_require_explicit_identity_and_parse_native_title():
    source = metadata(account_id="meta_asset:001234", account_identity_basis="selected_meta_asset", selected_meta_asset_id="001234")
    result = parse_social_export(result_bytes(), "Views.csv", "facebook_account_results_daily_v1", source)
    assert [row["source_row"] for row in result["observations"]] == [4, 5]
    assert all(row["account_id"] == "meta_asset:001234" for row in result["observations"])
    assert result["reconciliation"]["views"]["additive_period_total"] == 12
    with pytest.raises(ValueError, match="account_identity_basis"):
        parse_social_export(result_bytes(), "Views.csv", "facebook_account_results_daily_v1", metadata())
    with pytest.raises(ValueError, match="Unregistered"):
        parse_social_export(result_bytes("Ambiguous activity"), "activity.csv", "facebook_account_results_daily_v1", source)


def test_sparse_instagram_follows_remain_missing_and_are_flow_counts():
    source = metadata(platform="instagram", account_id="meta_asset:instagram1", account_identity_basis="selected_meta_asset")
    result = parse_social_export(result_bytes("Instagram follows", days=("2026-07-24",), values=(5,)),
                                 "Follows.csv", "instagram_account_results_daily_v1", source)
    assert len(result["observations"]) == 1
    observation = result["observations"][0]
    assert observation["metric"] == "new_followers"
    assert observation["measurement_type"] == "period_count"
    assert result["coverage"][0]["missing_dates"] == ["2026-07-25"]
    assert result["reconciliation"]["new_followers"]["observed_additive_value_sum"] == 5
    assert "additive_period_total" not in result["reconciliation"]["new_followers"]
    assert aggregate_metric(pd.DataFrame(result["observations"]), "new_followers", "2026-07-24", "2026-07-25")["value"] is None


def test_account_overlap_deduplicates_across_export_windows_and_capture_evidence(tmp_path):
    store = Store(tmp_path / "stats.sqlite3")
    snapshot = store.create_snapshot("Separate social capture")
    source = metadata(account_id="meta_asset:001234", account_identity_basis="selected_meta_asset", capture_time_basis="first receipt")
    first_raw = result_bytes()
    first = parse_social_export(first_raw, "long.csv", "facebook_account_results_daily_v1", source)
    store.commit_import(snapshot, "long.csv", first_raw, first["observations"])
    source.update(period_start="2026-07-25", capture_time_basis="later receipt", captured_at="2026-10-23T02:00:00Z")
    overlap_raw = result_bytes(days=("2026-07-25",), values=(4,))
    overlap = parse_social_export(overlap_raw, "short.csv", "facebook_account_results_daily_v1", source)
    imported = store.commit_import(snapshot, "short.csv", overlap_raw, overlap["observations"])
    assert imported["duplicates"] == 1
    assert len(store.read_observations(snapshot)) == 2


def test_facebook_native_post_identity_and_prepublication_zeros():
    rows = []
    for day in ("07/24/2026", "07/25/2026"):
        rows.append({"Post ID": "post01", "Page ID": "001234", "Page name": "Fixture Band", "Title": "Post",
                     "Description": "", "Duration (sec)": 0, "Publish time": "07/25/2026 10:13", "Caption type": "N/A",
                     "Permalink": "https://facebook.com/post01", "Is crosspost": 0, "Is share": 1, "Post type": "Links",
                     "Languages": "", "Custom labels": "", "Funded content status": "", "Data comment": "", "Date": day,
                     **{column: 0 for column in FACEBOOK_POST_METRICS}})
    raw = pd.DataFrame(rows).to_csv(index=False).encode()
    result = parse_social_export(raw, "post.csv", "facebook_post_daily_v1", metadata(selected_meta_asset_id="different-ui-asset"))
    assert len(result["observations"]) == 12
    assert all(row["account_id"] == "001234" and row["entity_id"] == "post01" for row in result["observations"])
    assert sum(row["status"] == "unavailable" for row in result["observations"]) == 6
    assert all(row["value"] == 0 for row in result["observations"])
    assert json.loads(result["observations"][0]["dimensions"])["selected_meta_asset_id"] == "different-ui-asset"
    assert any(issue["code"] == "prepublication_export_row" for issue in result["issues"])
    assert any(issue["code"] == "zero_limited_content_export" for issue in result["issues"])


def ui_reading(**changes):
    row = {"platform": "facebook", "account_id": "meta_asset:001234", "account_name": "Fixture Band",
           "captured_at": "2026-10-23T01:49:31+00:00", "source_timezone": "America/Los_Angeles",
           "evidence_ref": "ui-results.ax.txt", "source_url": "https://business.facebook.com/",
           "dimensions": {"source_report": "meta_account_results", "account_identity_basis": "selected_meta_asset",
                          "selected_meta_asset_id": "001234"},
           "metric": "views", "value": 12, "exactness": "exact", "period_start": "2026-07-24",
           "period_end": "2026-07-25", "time_grain": "period", "measurement_type": "period_count", "unit": "count"}
    row.update(changes)
    return row


def parse_ui(*readings):
    return parse_social_export(json.dumps({"schema_version": 1, "readings": readings}).encode(),
                               "readings.json", "meta_ui_readings_v1")


def test_ui_exact_period_matches_daily_scope_and_is_not_double_counted():
    source = metadata(account_id="meta_asset:001234", account_identity_basis="selected_meta_asset", selected_meta_asset_id="001234")
    daily = parse_social_export(result_bytes(), "Views.csv", "facebook_account_results_daily_v1", source)
    direct = parse_ui(ui_reading(measurement_type="additive_count"))
    assert not direct["issues"]
    observed = direct["observations"][0]
    assert observed["measurement_type"] == "period_count"
    assert observed["dimensions"] == daily["observations"][0]["dimensions"]
    assert observed["definition"] == daily["observations"][0]["definition"]
    total = aggregate_metric(pd.DataFrame(daily["observations"] + direct["observations"]), "views", "2026-07-24", "2026-07-25")
    assert total["value"] == 12
    assert total["coverage"]["method"] == "exact_reported_window"


def test_ui_rounding_is_archived_but_never_converted_to_exact_count():
    result = parse_ui(ui_reading(value=1200, exactness="rounded", display_value="1.2K"), ui_reading(value=12))
    assert len(result["observations"]) == 1
    assert result["observations"][0]["value"] == 12
    assert result["reconciliation"]["rounded_readings_excluded"] == 1


def test_ui_distinct_period_uses_native_total_instead_of_daily_audience_sum():
    source = metadata(account_id="meta_asset:001234", account_identity_basis="selected_meta_asset", selected_meta_asset_id="001234")
    daily = parse_social_export(result_bytes("Viewers", values=(8, 4)), "Viewers.csv", "facebook_account_results_daily_v1", source)
    direct = parse_ui(ui_reading(metric="viewers", value=9, measurement_type="distinct_audience_count"))
    assert not direct["issues"]
    total = aggregate_metric(pd.DataFrame(daily["observations"] + direct["observations"]), "viewers", "2026-07-24", "2026-07-25")
    assert total["value"] == 9
    assert total["coverage"]["method"] == "exact_reported_window"


def test_ui_follower_balance_is_point_observation_and_retains_source_scope():
    row = ui_reading(metric="followers", value=144, measurement_type="point_in_time_count", time_grain="point_in_time",
                     period_start="2026-10-21", period_end="2026-10-21",
                     dimensions={"source_report": "meta_account_audience", "account_identity_basis": "selected_meta_asset",
                                 "selected_meta_asset_id": "001234"})
    result = parse_ui(row)
    assert not result["issues"]
    observed = result["observations"][0]
    assert observed["time_grain"] == "point"
    assert observed["account_id"] == observed["entity_id"] == "meta_asset:001234"
    assert "Audience UI" in observed["definition"]
    assert observed["period_end"] == "2026-10-21"
    assert observed["captured_at"] == "2026-10-23T01:49:31+00:00"
    invalid = parse_ui({**row, "period_start": "2023-09-22"})
    assert not invalid["observations"]
    assert invalid["issues"][0]["severity"] == "error"


def test_ui_instagram_view_scope_is_explicit_and_separate_from_crossposted_total():
    source = metadata(platform="instagram", account_id="meta_asset:001234", account_identity_basis="selected_meta_asset",
                      selected_meta_asset_id="001234", reported_scope="instagram_and_facebook")
    daily = parse_social_export(result_bytes(), "Views.csv", "instagram_account_results_daily_v1", source)
    dimensions = {"source_report": "meta_account_results", "account_identity_basis": "selected_meta_asset",
                  "selected_meta_asset_id": "001234", "reported_scope": "instagram_only"}
    component = parse_ui(ui_reading(platform="instagram", value=8, dimensions=dimensions))
    assert not component["issues"]
    assert component["observations"][0]["dimensions"] != daily["observations"][0]["dimensions"]
    assert aggregate_metric(pd.DataFrame(daily["observations"] + component["observations"]), "views", "2026-07-24", "2026-07-25")["value"] is None
    invalid = parse_ui(ui_reading(platform="instagram"))
    assert not invalid["observations"]
    assert invalid["issues"][0]["severity"] == "error"
