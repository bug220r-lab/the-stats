"""Native history imports preserve identity, grain, missingness and lineage."""
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pandas as pd
import pytest

from stats_app.analysis_content import load_content_observations, select_content_observations
from stats_app.analysis_repository import AnalysisRepository, stage_analysis_package
from stats_app.meta_content import build_meta_content, normalize_collection, normalize_content_file, normalize_story_observations, parse_count


HEADER = ["Post ID", "Account ID", "Account username", "Account name", "Description", "Publish time",
          "Permalink", "Post type", "Date", "Views", "Reach", "Likes", "Shares", "Follows", "Unknown native field"]
FB_HEADER = ["Post ID", "Page ID", "Page name", "Title", "Description", "Duration (sec)", "Publish time",
             "Caption type", "Permalink", "Is crosspost", "Is share", "Post type", "Languages", "Custom labels",
             "Funded content status", "Data comment", "Date", "Views", "Reactions, Comments and Shares", "Reactions",
             "Comments", "Shares", "Total clicks", "Other Clicks", "Matched Audience Targeting Consumption (Photo Click)",
             "Link Clicks", "Seconds viewed", "Average Seconds viewed", "Estimated earnings (USD)", "Ad CPM (USD)", "Ad impressions"]


def raw_csv(path, rows, header=HEADER, encoding="utf-8-sig"):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(header)
    writer.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(stream.getvalue().encode(encoding))
    return path


def source_row(post="0018216593050358711", account="17841454335424545", publication="03/17/2024 09:18", views="1,200"):
    return [post, account, "redactedbandoh", "[REDACTED]", "A real multiline\ncaption, intact", publication,
            "https://www.instagram.com/p/explicit-native-link/", "IG reel", "Lifetime", views, "", "0", "--", "1.2K", "preserve me"]


def metadata(**changes):
    return {"platform_selected": "Instagram", "selected_account_id": "17841454335424545", "account_id_type": "native_instagram_account",
            "captured_at_utc": "2026-10-23T08:00:00Z", "acquired_at_utc": "2026-10-23T08:00:10Z",
            "requested_start": "2022-01-01", "requested_end": "2026-10-22", "publication_timezone": "Pacific Time",
            "timezone_evidence_ref": "captures/export_options.txt", "metric_platform_scope": "Instagram",
            "source_url": "https://business.facebook.com/latest/insights/content", **changes}


def test_exact_ids_metrics_and_native_evidence_survive(tmp_path):
    path = raw_csv(tmp_path / "raw/instagram.csv", [source_row()], encoding="utf-16")
    before = path.read_bytes()
    rows, bad, coverage = normalize_content_file(path, metadata(), collection_root=tmp_path)
    row = rows[0]
    assert row["post_id"] == "0018216593050358711"
    assert row["selected_account_id"] == "17841454335424545"
    assert row["description"] == "A real multiline\ncaption, intact"
    assert row["views"] == "1200" and row["views_raw"] == "1,200"
    assert row["reach"] == "" and row["reach_status"] == "missing_source_blank"
    assert row["likes"] == "0" and row["likes_status"] == "observed_zero"
    assert row["shares"] == "" and row["shares_status"] == "unavailable_source_marker"
    assert row["follows"] == "" and row["follows_status"] == "rounded_display_not_exact"
    assert row["comments"] == "" and row["comments_status"] == "metric_not_in_export"
    assert row["published_local"] == "2024-03-17T09:18:00"
    assert row["published_utc"] == "2024-03-17T16:18:00+00:00"
    assert json.loads(row["native_record_json"])["Unknown native field"] == "preserve me"
    assert row["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert row["snapshot_timestamp"] == "2026-10-23T08:00:00+00:00"
    assert coverage["actual_publication_start"] == "2024-03-17"
    assert coverage["requested_start"] == "2022-01-01" and coverage["completeness_status"] == "not_established"
    assert not bad and path.read_bytes() == before


def test_unknown_year_timezone_and_capture_are_not_inferred(tmp_path):
    path = raw_csv(tmp_path / "raw/instagram.csv", [source_row(publication="Fri May 8, 5:52pm"), source_row(post="002", publication="2024-03-17 09:18:00")])
    rows, bad, _ = normalize_content_file(path, metadata(publication_timezone="", reporting_timezone="Pacific Time", captured_at_utc=""))
    assert rows[0]["publication_date"] == "" and rows[0]["published_local"] == "Fri May 8, 5:52pm"
    assert rows[1]["publication_date"] == "2024-03-17" and rows[1]["published_utc"] == ""
    assert rows[1]["publication_timezone"] == ""
    assert rows[1]["snapshot_timestamp"] == "" and rows[1]["acquired_at_utc"]
    assert not bad


@pytest.mark.parametrize("publication", ["11/03/2024 01:30", "03/10/2024 02:30"])
def test_dst_ambiguous_or_nonexistent_time_is_not_chosen(tmp_path, publication):
    path = raw_csv(tmp_path / "raw/instagram.csv", [source_row(publication=publication)])
    row = normalize_content_file(path, metadata())[0][0]
    assert row["published_utc"] == ""
    assert row["published_utc_status"] == "ambiguous_or_nonexistent_local_time"


def test_ragged_rows_and_daily_grain_quarantined_without_column_shift(tmp_path):
    normal = source_row()
    daily = source_row(post="002")
    daily[8] = "10/22/2026"
    path = raw_csv(tmp_path / "raw/instagram.csv", [normal, normal[:-1], daily, normal])
    rows, bad, coverage = normalize_content_file(path, metadata())
    assert len(rows) == 1
    assert {r["reason"] for r in bad} == {"native_field_count_mismatch_no_alignment_guess", "non_lifetime_or_unknown_measurement_basis", "exact_duplicate_native_record_retained_raw"}
    assert len(json.loads(bad[0]["raw_record_json"])) == len(HEADER) - 1
    assert coverage["native_data_rows"] == 4 and coverage["exact_duplicate_rows"] == 1


def test_associated_author_identity_remains_separate(tmp_path):
    path = raw_csv(tmp_path / "raw/instagram.csv", [source_row(account="00099887766554433")])
    row = normalize_content_file(path, metadata())[0][0]
    assert row["selected_account_id"] == "17841454335424545"
    assert row["author_account_id"] == "00099887766554433"
    assert row["author_scope"] == "associated_account_authorship_unverified"


def test_facebook_metrics_not_combined_or_assigned_crosspost_scope(tmp_path):
    header = ["Post ID", "Page ID", "Page name", "Publish time", "Post type", "Date", "Views", "Reactions, Comments and Shares", "Reactions", "Comments", "Shares", "Is crosspost"]
    path = raw_csv(tmp_path / "raw/facebook.csv", [["998829296519708", "100091779409539", "Redacted OH", "01/05/2023 14:00", "Videos", "Lifetime", "100", "12", "7", "1", "4", "1"]], header)
    row = normalize_content_file(path, metadata(platform_selected="Facebook", selected_account_id="100091779409539", account_id_type="native_facebook_page", metric_platform_scope="unknown"))[0][0]
    assert row["engagement_actions"] == "12" and row["engagement_actions_native_label"] == "Reactions, Comments and Shares"
    assert row["interactions"] == "" and row["likes"] == ""
    assert row["is_crosspost_raw"] == "1" and row["metric_platform_scope"] == "unknown"


def facebook_short_row():
    return ["0521630644239578", "100091779409539", "Redacted OH", "Happy New Year", "", "0", "01/01/2025 10:37",
            "N/A", "https://www.facebook.com/redactedbandoh/posts/native-pfbid/", "0", "0", "Photos", "", "", "", "",
            "Lifetime", "69", "5", "5", "0", "0", "3", "", "3", "", "", "", "", ""]


def test_malformed_suffix_recovers_only_anchored_identity_keeps_quarantine(tmp_path):
    native = facebook_short_row()
    path = raw_csv(tmp_path / "raw/facebook.csv", [native, native], FB_HEADER)
    rows, bad, coverage = normalize_content_file(path, metadata(platform_selected="Facebook", selected_account_id="100091779409539", account_id_type="native_facebook_page"))
    assert len(rows) == 1 and len(bad) == 2
    row = rows[0]
    assert row["post_id"] == "0521630644239578" and row["publication_date"] == "2025-01-01"
    assert row["permalink"] == native[8] and row["post_type"] == "Photos"
    assert row["source_kind"] == "native_export_identity_only" and row["measurement_type"] == "content_identity_only"
    assert row["views"] == "" and row["views_raw"] == "" and row["views_status"] == "unavailable_malformed_source_row"
    assert row["reactions"] == "" and row["reactions_status"] == "unavailable_malformed_source_row"
    assert json.loads(row["native_record_json"]) == native
    assert json.loads(bad[0]["raw_record_json"]) == native
    assert bad[0]["recovery_status"] == "identity_only_prefix_verified_metrics_unavailable"
    assert bad[1]["recovery_status"] == "exact_duplicate_identity_only_record_omitted"
    assert coverage["native_data_rows"] == 2 and coverage["identity_only_rows"] == 1
    assert coverage["metric_eligible_rows"] == 0 and coverage["unique_post_ids"] == 1


@pytest.mark.parametrize("broken", ["missing_prefix", "bad_permalink", "foreign_account", "yearless_date", "shifted_lifetime", "extra_field"])
def test_malformed_identity_is_not_recovered_without_every_anchor(tmp_path, broken):
    native = facebook_short_row()
    if broken == "missing_prefix":
        del native[4]
    elif broken == "bad_permalink":
        native[8] = "https://facebook.com.evil.example/redactedbandoh/posts/native-pfbid/"
    elif broken == "foreign_account":
        native[1] = "999"
    elif broken == "yearless_date":
        native[6] = "Jan 1 at 10:37"
    elif broken == "shifted_lifetime":
        native[16] = "69"
    elif broken == "extra_field":
        native += ["", ""]
    path = raw_csv(tmp_path / "raw/facebook.csv", [native], FB_HEADER)
    rows, bad, coverage = normalize_content_file(path, metadata(platform_selected="Facebook", selected_account_id="100091779409539", account_id_type="native_facebook_page"))
    assert not rows and len(bad) == 1
    assert bad[0]["recovery_status"] == "not_recovered" and coverage["identity_only_rows"] == 0


@pytest.mark.parametrize("value", ["nan", "inf", "-1", "1.5", "1,20", "1e3"])
def test_nonexact_or_invalid_count_is_retained_unavailable(value):
    number, status = parse_count(value)
    assert number == "" and status.startswith("invalid_")


@pytest.mark.parametrize("changes,error", [
    ({"selected_account_id": 17841454335424545}, "string"),
    ({"selected_account_id": "1.7841454335424545e16"}, "string"),
    ({"account_id_type": "meta_business_suite_asset"}, "native account"),
    ({"captured_at_utc": "2026-10-23T08:00:00"}, "UTC offset"),
    ({"source_sha256": "wrong"}, "hash"),
    ({"requested_start": "2027-01-01"}, "start follows"),
])
def test_invalid_capture_metadata_stops_import(tmp_path, changes, error):
    path = raw_csv(tmp_path / "raw/instagram.csv", [source_row()])
    with pytest.raises(ValueError, match=error):
        normalize_content_file(path, metadata(**changes))


def test_multiple_exports_keep_captures_and_report_honest_coverage(tmp_path):
    for name, views, capture in [("old", "10", "2026-10-22T08:00:00Z"), ("new", "13", "2026-10-23T08:00:00Z")]:
        path = raw_csv(tmp_path / f"raw/{name}.csv", [source_row(views=views)])
        path.with_suffix(".csv.metadata.json").write_text(json.dumps(metadata(captured_at_utc=capture)), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in (tmp_path / "raw").iterdir()}
    result = normalize_collection(tmp_path)
    snapshots = pd.read_csv(tmp_path / "normalized/content_snapshots.csv", dtype=str, keep_default_na=False)
    assert len(snapshots) == 2 and set(snapshots.views) == {"10", "13"}
    assert snapshots.post_id.nunique() == 1 and snapshots.observation_id.nunique() == 2
    assert snapshots.metadata_sha256.str.len().eq(64).all()
    assert not result["complete_history_claim"] and not result["inherited_assets_modified"]
    statuses = pd.read_csv(tmp_path / "normalized/collection_status.csv", dtype=str, keep_default_na=False)
    assert len(statuses) == 2 and statuses.dataset.is_unique
    assert statuses.detail.str.contains("Complete account history is not established", regex=False).all()
    assert before == {p.name: p.read_bytes() for p in (tmp_path / "raw").iterdir()}
    with pytest.raises(FileExistsError):
        normalize_collection(tmp_path)


def test_header_only_export_is_not_zero_posts_or_complete_history(tmp_path):
    path = raw_csv(tmp_path / "raw/empty.csv", [])
    path.with_suffix(".metadata.json").write_text(json.dumps(metadata()), encoding="utf-8")
    result = normalize_collection(tmp_path)
    assert result["source_exports"][0]["actual_publication_start"] == ""
    assert not result["complete_history_claim"]
    status = pd.read_csv(tmp_path / "normalized/collection_status.csv").iloc[0]
    assert status.status == "no_valid_native_snapshots"


def test_new_package_preserves_old_assets_and_library_selects_new_capture(tmp_path):
    files = {"metadata.json": b'{"analysis_version":"prior"}', "raw_sha256.json": b'[]', "audit/final_validation.json": b'{}',
             "social/posts_latest.csv": b"platform_selected,selected_account_id,post_id,post_type,publication_date,snapshot_timestamp,metric_platform_scope,views,views_status\nInstagram,17841454335424545,0018216593050358711,IG reel,2024-03-17,2026-10-22T08:00:00Z,Instagram,10,observed\n",
             "statistical_results.csv": b"test,p_value\nuntouched,0.72\n"}
    parent_root = tmp_path / "parent"
    parent_root.mkdir()
    archive = tmp_path / "parent.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for name, raw in files.items():
            path = parent_root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            zipped.writestr("parent/" + name, raw)
    library = tmp_path / "library"
    staged = stage_analysis_package(parent_root, archive, library / "analysis/prior", label="Prior", metadata={"analysis_version": "prior"})
    parent = AnalysisRepository(staged["database"])
    registry = library / "archive_registry.json"
    registry.write_text('{"prior":"preserved"}', encoding="utf-8")
    collection = tmp_path / "collection"
    source = raw_csv(collection / "raw/instagram.csv", [source_row(views="13")])
    source.with_suffix(".metadata.json").write_text(json.dumps(metadata()), encoding="utf-8")
    old_hash = hashlib.sha256(parent.db_path.read_bytes()).hexdigest()
    registration = {"database": "analysis/prior/analysis.sqlite3"}
    (collection / "preflight_preservation.json").write_text(json.dumps({
        "configured_data_dir": str(library), "active_analysis": registration,
        "databases": [{"relative_path": registration["database"], "sha256": old_hash}],
        "registry": {"relative_path": "archive_registry.json", "sha256": hashlib.sha256(registry.read_bytes()).hexdigest()}}), encoding="utf-8")
    normalize_collection(collection)
    result = build_meta_content(parent, collection, tmp_path / "package", tmp_path / "package.zip")
    staged_new = stage_analysis_package(result["package_root"], result["zip_path"], tmp_path / "stage", label=result["label"], metadata=result["staging_metadata"])
    repo = AnalysisRepository(staged_new["database"])
    assert parent.db_path.read_bytes() and hashlib.sha256(parent.db_path.read_bytes()).hexdigest() == old_hash
    assert repo.original_bytes("social/posts_latest.csv") == files["social/posts_latest.csv"]
    assert repo.original_bytes("statistical_results.csv") == files["statistical_results.csv"]
    observations = load_content_observations(repo)
    selected = select_content_observations(observations)
    assert len(observations) == 2 and len(selected) == 1
    assert selected.iloc[0].views == 13
    assert not result["live_data_changed"] and repo.metadata["new_significance_tests"] == 0


def manual_story(tmp_path, **changes):
    for name in ('panel.txt', 'panel.dom.txt'):
        (tmp_path / name).write_text('Captured native Story panel evidence', encoding='utf-8')
    return {
        'post_id': '0017938760384419916', 'platform_selected': 'Instagram',
        'selected_account_id': '118246571240106', 'account_id_type': 'meta_business_suite_asset',
        'source_url': 'https://business.facebook.com/latest/insights/object_insights/?asset_id=118246571240106&content_id=0017938760384419916',
        'captured_at_utc': '2026-10-23T19:00:00Z', 'published_local': 'Dec 31, 2022',
        'archive_requested_start': '2022-01-01', 'archive_requested_end': '2022-12-31',
        'account_handle': 'Loading preview', 'panel_text': 'Story · Published on: Dec 31, 2022',
        'measurement_type': 'lifetime_content_snapshot',
        'metrics_raw': {'Reach': '‑‑', 'Impressions': '1.0K', 'Interactions': '2', 'Instagram follows': '0'},
        'ax_path': 'panel.txt', 'dom_path': 'panel.dom.txt', **changes,
    }


def write_manual(tmp_path, observations):
    path = tmp_path / 'raw/story_detail_observations.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(observations), encoding='utf-8')
    return path


def test_manual_story_named_metrics_dates_and_evidence_preserved(tmp_path):
    observation = manual_story(tmp_path)
    path = write_manual(tmp_path, [observation])
    before = path.read_bytes()
    rows, bad, coverage = normalize_story_observations(path, collection_root=tmp_path)
    row = rows[0]
    assert not bad and len(rows) == 1
    assert row['post_id'] == '0017938760384419916' and row['account_id_type'] == 'meta_business_suite_asset'
    assert row['publication_date'] == '2022-12-31' and row['published_utc'] == ''
    assert row['views'] == '' and row['views_status'] == 'metric_not_in_export'
    assert row['impressions'] == '' and row['impressions_raw'] == '1.0K'
    assert row['impressions_status'] == 'rounded_display_not_exact'
    assert row['interactions'] == '2' and row['follows'] == '0'
    assert row['reach_status'] == 'unavailable_source_marker' and row['account_handle'] == ''
    assert row['description'] == '' and row['permalink'] == ''
    assert json.loads(row['native_record_json']) == observation
    assert len(json.loads(row['evidence_refs_json'])) == 2
    assert coverage['actual_publication_start'] == '2022-12-31' and coverage['completeness_status'] == 'not_established'
    assert path.read_bytes() == before


@pytest.mark.parametrize('text_fields,expected', [
    ({'description': 'Caption with a link\nhttps://example.org/?a=1&b=2'}, 'Caption with a link\nhttps://example.org/?a=1&b=2'),
    ({'caption': 'Native caption, exact whitespace  '}, 'Native caption, exact whitespace  '),
    ({'description': '', 'caption': 'Separate retained alias'}, ''),
    ({'description': 'Native description', 'caption': 'Separate retained alias'}, 'Native description'),
])
def test_manual_story_explicit_text_and_permalink_survive_normalized_csv(tmp_path, text_fields, expected):
    permalink = 'https://www.instagram.com/stories/redactedbandoh/99999999999999999/'
    observation = manual_story(tmp_path, **text_fields, permalink=permalink,
                               metric_platform_scope='Instagram detail; Views scope unknown')
    path = write_manual(tmp_path, [observation])
    before = path.read_bytes()
    normalize_collection(tmp_path)
    with (tmp_path / 'normalized/content_snapshots.csv').open(encoding='utf-8', newline='') as handle:
        row = next(csv.DictReader(handle))
    assert row['description'] == expected and row['permalink'] == permalink
    # The source permalink may use another native ID system. It is neither
    # rewritten from the MBS ID nor used as an identity bridge.
    assert row['post_id'] == observation['post_id']
    assert row['source_url'] == observation['source_url']
    assert row['metric_platform_scope'] == observation['metric_platform_scope']
    assert row['author_scope'] == 'selected_account_detail_authorship_unverified'
    assert row['publication_timezone_status'] == 'unknown'
    assert row['views_status'] == 'metric_not_in_export'
    assert json.loads(row['native_record_json']) == observation
    assert path.read_bytes() == before


@pytest.mark.parametrize('field,value', [('description', None), ('caption', 12), ('permalink', {'url': 'https://example.org'})])
def test_manual_story_nonstring_content_is_quarantined_without_coercion(tmp_path, field, value):
    observation = manual_story(tmp_path, **{field: value})
    path = write_manual(tmp_path, [observation])
    rows, bad, _ = normalize_story_observations(path, collection_root=tmp_path)
    assert not rows and len(bad) == 1
    assert bad[0]['reason'] == 'manual_story_content_fields_not_explicit_strings'
    assert json.loads(bad[0]['raw_record_json']) == observation


@pytest.mark.parametrize('bounds,expected', [
    ({'archive_requested_start': '', 'archive_requested_end': ''},
     'Direct native Story detail; no archive date filter applied'),
    ({'archive_requested_start': '2022-01-01', 'archive_requested_end': '2022-12-31'},
     'Archive requested dates; panel publication date retained separately'),
])
def test_manual_story_publication_filter_describes_only_evidenced_bounds(tmp_path, bounds, expected):
    correction = {'reason': 'Direct recapture had no archive picker', 'original_observation_retained': True}
    observation = manual_story(tmp_path, **bounds, scope_metadata_correction=correction)
    path = write_manual(tmp_path, [observation])
    before = path.read_bytes()
    rows, bad, _ = normalize_story_observations(path, collection_root=tmp_path)
    assert not bad and rows[0]['publication_filter'] == expected
    assert rows[0]['requested_start'] == bounds['archive_requested_start']
    assert rows[0]['requested_end'] == bounds['archive_requested_end']
    assert json.loads(rows[0]['native_record_json'])['scope_metadata_correction'] == correction
    assert path.read_bytes() == before


@pytest.mark.parametrize('changes', [
    {'source_url': 'https://business.facebook.com/latest/insights/object_insights/?asset_id=999&content_id=0017938760384419916'},
    {'source_url': 'https://business.facebook.com/latest/insights/object_insights/?asset_id=118246571240106&content_id=999'},
    {'ax_path': '../outside.txt'}, {'dom_path': 'absent.txt'}, {'captured_at_utc': ''},
    {'metrics_raw': {'Views': 12}}, {'measurement_type': 'daily'},
])
def test_manual_story_rejects_unverified_identity_evidence_or_metric_contract(tmp_path, changes):
    path = write_manual(tmp_path, [manual_story(tmp_path, **changes)])
    rows, bad, _ = normalize_story_observations(path, collection_root=tmp_path)
    assert not rows and len(bad) == 1
    assert json.loads(bad[0]['raw_record_json'])['post_id'] == '0017938760384419916'


def test_manual_story_yearless_date_stays_unknown_and_duplicate_capture_is_not_added(tmp_path):
    observation = manual_story(tmp_path, published_local='Dec 31', account_handle='redactedbandoh')
    path = write_manual(tmp_path, [observation, observation])
    result = normalize_collection(tmp_path)
    with (tmp_path / 'normalized/content_snapshots.csv').open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1 and rows[0]['publication_date'] == ''
    assert rows[0]['account_handle'] == 'redactedbandoh'
    assert result['retained_snapshots'] == 1 and result['quarantined_rows'] == 1


def test_malformed_instagram_story_keeps_only_verified_prefix(tmp_path):
    header = ['Post ID', 'Account ID', 'Account username', 'Account name', 'Description', 'Duration (sec)',
              'Publish time', 'Permalink', 'Post type', 'Data comment', 'Date', 'Views', 'Reach', 'Likes',
              'Shares', 'Replies', 'Navigation', 'Profile visits', 'Sticker taps', 'Follows']
    prefix = ['0017938760384419916', '17841454335424545', 'redactedbandoh', '[REDACTED]', '', '15',
              '12/31/2025 10:34', 'https://www.instagram.com/stories/redactedbandoh/0017938760384419916/',
              'IG story', '', 'Lifetime']
    valid_malformed = prefix + ['5', '0', '0', '12', '0', '0', '0', '0']
    bad_url = valid_malformed.copy(); bad_url[7] = 'https://not-instagram.example/stories/123'
    missing_prefix = valid_malformed.copy(); del missing_prefix[4]
    bad_account = valid_malformed.copy(); bad_account[1] = '999'
    path = raw_csv(tmp_path / 'raw/stories.csv', [valid_malformed, bad_url, missing_prefix, bad_account], header=header)
    rows, quarantine, coverage = normalize_content_file(path, metadata(publication_timezone=''), collection_root=tmp_path)
    assert len(rows) == 1 and len(quarantine) == 4
    row = rows[0]
    assert row['post_id'] == '0017938760384419916' and row['publication_date'] == '2025-12-31'
    assert row['source_kind'] == 'native_export_identity_only' and row['measurement_type'] == 'content_identity_only'
    assert row['likes'] == '' and row['likes_raw'] == '' and row['likes_status'] == 'unavailable_malformed_source_row'
    assert json.loads(row['native_record_json']) == valid_malformed
    assert coverage['identity_only_rows'] == 1 and coverage['metric_eligible_rows'] == 0


def grid_page(tmp_path):
    for name in ('grid.txt','grid.json','grid.png'):
        (tmp_path/name).write_bytes(b'captured evidence')
    labels = ['','Title','Date published','Views','Reach','Likes and reactions','Interactions']
    values = ['','Caption\nPhoto\nCrossposted','Dec 31, 2025','1.2K','401','42','52']
    return dict(platform_selected='Instagram',selected_account_id='118246571240106',account_id_type='meta_business_suite_asset',
                placement_filter='Instagram Feed',measurement_type='native_content_grid_snapshot',
                source_url='https://business.facebook.com/latest/posts/published_posts?asset_id=118246571240106',
                captured_at_utc='2026-10-23T19:30:00Z',requested_start='2025-01-01',requested_end='2025-12-31',
                headers=[{'index':str(i),'text':label} for i,label in enumerate(labels,1)],
                rows=[dict(row_label='Select item with id 00123456789012345',platform_alts=['Instagram','Facebook'],
                           cells=[{'index':str(i),'text':value} for i,value in enumerate(values,1)])],
                ax_path='grid.txt',dom_path='grid.json',screenshot_path='grid.png')


def test_grid_aligns_by_column_labels_and_keeps_compound_reactions_separate(tmp_path):
    from stats_app.meta_content import normalize_content_grid
    page=grid_page(tmp_path)
    page['rows'][0]['cells'].reverse()  # DOM order is not metric order.
    path=tmp_path/'instagram_feed_grid_pages.json';path.write_text(json.dumps([page,page]),encoding='utf-8')
    rows,bad,coverage=normalize_content_grid(path,collection_root=tmp_path)
    assert len(rows)==1 and not bad and coverage['exact_duplicate_rows']==1
    row=rows[0]
    assert row['post_id']=='00123456789012345' and row['publication_date']=='2025-12-31'
    assert row['views']=='' and row['views_raw']=='1.2K' and row['reach']=='401'
    assert row['likes_and_reactions']=='42' and row['likes']=='' and row['reactions']==''
    assert row['interactions']=='52' and row['measurement_type']=='native_content_grid_snapshot'
    assert len(json.loads(row['evidence_refs_json']))==3


def test_grid_changed_capture_is_not_summed_or_erased(tmp_path):
    from stats_app.meta_content import normalize_content_grid
    page=grid_page(tmp_path); changed=json.loads(json.dumps(page))
    changed['captured_at_utc']='2026-10-23T19:31:00Z';changed['rows'][0]['cells'][4]['text']='410'
    path=tmp_path/'instagram_feed_grid_pages.json';path.write_text(json.dumps([page,changed]),encoding='utf-8')
    rows,bad,coverage=normalize_content_grid(path,collection_root=tmp_path)
    assert [r['reach'] for r in rows]==['401','410'] and not bad
    assert coverage['unique_post_ids']==1 and coverage['retained_snapshots']==2


def test_grid_incomplete_loading_or_unverified_platform_is_quarantined(tmp_path):
    from stats_app.meta_content import normalize_content_grid
    page=grid_page(tmp_path); other=json.loads(json.dumps(page['rows'][0]))
    page['rows'][0]['cells'][3]['text']='Loading...';other['platform_alts']=['Facebook'];page['rows'].append(other)
    path=tmp_path/'instagram_feed_grid_pages.json';path.write_text(json.dumps([page]),encoding='utf-8')
    rows,bad,_=normalize_content_grid(path,collection_root=tmp_path)
    assert not rows and {r['reason'] for r in bad}=={'grid_incomplete_or_ambiguous_cells','grid_identity_or_platform_unverified'}


def test_grid_requires_explicit_filter_and_traceable_capture(tmp_path):
    from stats_app.meta_content import normalize_content_grid
    page=grid_page(tmp_path);page['placement_filter']='All platforms'
    path=tmp_path/'instagram_feed_grid_pages.json';path.write_text(json.dumps([page]),encoding='utf-8')
    with pytest.raises(ValueError,match='explicit Instagram Feed'):
        normalize_content_grid(path,collection_root=tmp_path)


def test_grid_associated_author_is_preserved_without_band_ownership(tmp_path):
    from stats_app.meta_content import normalize_content_grid
    page=grid_page(tmp_path)
    page['rows'][0]['cells'][1]['text']='Caption mentions @redactedbandoh\nReel\nblindboxingband\nBoost\nOpen Dropdown\n\u200b'
    path=tmp_path/'instagram_feed_grid_pages.json';path.write_text(json.dumps([page]),encoding='utf-8')
    rows,bad,_=normalize_content_grid(path,collection_root=tmp_path)
    assert not bad and rows[0]['author_username']=='blindboxingband'
    assert rows[0]['author_scope']=='associated_account_authorship_unverified' and rows[0]['post_type']=='IG reel'


def test_explicit_collection_limitations_survive_reproduction(tmp_path):
    raw=raw_csv(tmp_path/'raw/instagram.csv',[source_row()])
    raw.with_suffix('.metadata.json').write_text(json.dumps(metadata()),encoding='utf-8')
    limitation=dict(dataset='facebook_stories',status='insights_not_enabled_not_collected',detail='No Story history was inferred.',evidence_ref='capture.txt',captured_at_utc='2026-10-23T19:00:00Z')
    (tmp_path/'collection_status_additions.json').write_text(json.dumps([limitation]),encoding='utf-8')
    normalize_collection(tmp_path)
    with (tmp_path/'normalized/collection_status.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
    assert rows[-1]==limitation
