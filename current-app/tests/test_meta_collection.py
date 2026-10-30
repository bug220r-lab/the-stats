"""Separate Meta evidence must never rewrite historical analysis or infer zeros."""
import hashlib
import json
from pathlib import Path
import zipfile

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from stats_app.analysis_repository import AnalysisRepository, stage_analysis_package
from stats_app.meta_collection import PREFIX, RAW_PREFIX, build_meta_collection
from stats_app.storage import StorageError


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path / "parent-package"
    raw = b"date,value\n2026-10-20,\n"
    files = {
        "raw/old_follows.csv": raw,
        "social/account_daily.csv": b"date,value,value_status\n2026-10-20,,missing\n",
        "social/excluded_records.csv": b"source_record,reason\n2,malformed_original_story\n",
        "cross_platform/statistical_results.csv": b"analysis_id,q_bh_12_tests\nkept,0.4\n",
        "statistical_results.csv": b"analysis_id,status\nkept,no_significance\n",
        "spotify/cleaned/track_daily_long.csv": b"song_id,date,metric,value\n001,2026-10-20,streams,7\n",
        "metadata.json": b'{"analysis_version":"spotify-recovery-20261023"}',
        "audit/final_validation.json": b'{"checks":{"old_check":true}}',
        "raw_sha256.json": json.dumps([{"path": "raw/old_follows.csv", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}]).encode(),
    }
    archive = tmp_path / "parent.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for name, contents in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
            zipped.writestr(root.name + "/" + name, contents)
    staged = stage_analysis_package(root, archive, tmp_path / "parent-stage", label="Prior analytical results",
                                   metadata={"analysis_version": "spotify-recovery-20261023", "input_lineage": {"social": "cleaned-20261022", "statistical_results": "cleaned-20261022"}})
    parent = AnalysisRepository(staged["database"])
    collection = tmp_path / "collection"
    (collection / "raw").mkdir(parents=True)
    (collection / "raw/export.csv").write_bytes(b"Date,Spend\n2026-10-20,0\n2026-10-21,\n")
    (collection / "normalized").mkdir()
    pd.DataFrame([
        {"ad_account_id": "000123", "campaign_id": "campaign-1", "ad_id": "001", "date": "2026-10-20",
         "spend": "0", "impressions": "20", "reporting_start": "2026-10-20", "reporting_end": "2026-10-21",
         "reporting_level": "ad_daily", "currency": "USD", "reporting_timezone": "America/Los_Angeles",
         "attribution_setting": "unknown", "captured_at_utc": "2026-10-23T01:00:00Z", "source_file": "raw/export.csv"},
        {"ad_account_id": "000123", "campaign_id": "campaign-1", "ad_id": "001", "date": "2026-10-21",
         "spend": "", "impressions": "", "reporting_start": "2026-10-20", "reporting_end": "2026-10-21",
         "reporting_level": "ad_daily", "currency": "USD", "reporting_timezone": "America/Los_Angeles",
         "attribution_setting": "unknown", "captured_at_utc": "2026-10-23T01:00:00Z", "source_file": "raw/export.csv"},
    ]).to_csv(collection / "normalized/ads_history.csv", index=False)
    pd.DataFrame([{"dataset": "instagram_follows", "status": "blocked", "detail": "Historical daily export unavailable",
                   "evidence_ref": "raw/access.txt", "captured_at_utc": "2026-10-23T01:00:00Z"}]).to_csv(collection / "normalized/collection_status.csv", index=False)
    (collection / "raw/access.txt").write_text("Access limitation observed", encoding="utf-8")
    pd.DataFrame([{"dataset": "instagram_follows", "status": "unresolved", "detail": "No exact daily evidence",
                   "evidence_ref": "raw/access.txt", "captured_at_utc": "2026-10-23T01:00:00Z"}]).to_csv(collection / "normalized/repair_status.csv", index=False)
    (collection / "mapping").mkdir()
    mapping = b"post_key,platform_selected,post_id,song_id,status,stream_attribution_available\npost-1,Instagram,001,track-a,explicit_caption_reference,False\npost-1,Instagram,001,track-b,explicit_caption_reference,False\npost-2,Facebook,002,,unknown_no_identified_song,False\n"
    (collection / "mapping/post_song_references.csv").write_bytes(mapping)
    (collection / "mapping/post_song_map.csv").write_bytes(b"post_key,assigned_song_ids,song_cardinality\npost-1,track-a|track-b,multiple\npost-2,,unknown\n")
    (collection / "mapping/draft-v1").mkdir()
    (collection / "mapping/draft-v1/invalid.csv").write_bytes(b"bad,headers\nnot,rectangular,ignored\n")
    (collection / "mapping/coverage.json").write_text(json.dumps({"source_database_sha256_before": hashlib.sha256(parent.db_path.read_bytes()).hexdigest(),
          "source_database_sha256_after": hashlib.sha256(parent.db_path.read_bytes()).hexdigest(),
          "input_assets_sha256": {"social/account_daily.csv": hashlib.sha256(files["social/account_daily.csv"]).hexdigest()}}))
    return parent, collection, files


def package(inputs, tmp_path):
    parent, collection, _ = inputs
    result = build_meta_collection(parent, collection, tmp_path / "meta-package", tmp_path / "meta.zip")
    staged = stage_analysis_package(result["package_root"], result["zip_path"], tmp_path / "meta-stage",
                                    label=result["label"], metadata=result["staging_metadata"])
    return result, AnalysisRepository(staged["database"])


def test_packaging_preserves_parent_sources_and_adds_separate_evidence(inputs, tmp_path):
    parent, collection, files = inputs
    before = parent.db_path.read_bytes()
    result, repo = package(inputs, tmp_path)
    assert parent.db_path.read_bytes() == before and not result["live_data_changed"]
    for path in ("social/account_daily.csv", "social/excluded_records.csv", "cross_platform/statistical_results.csv",
                 "statistical_results.csv", "spotify/cleaned/track_daily_long.csv"):
        assert repo.original_bytes(path) == files[path]
    assert repo.original_bytes("raw/meta_predecessor_metadata/metadata.json") == files["metadata.json"]
    assert repo.original_bytes(RAW_PREFIX + "raw/export.csv") == (collection / "raw/export.csv").read_bytes()
    assert repo.metadata["input_lineage"]["social"] == "cleaned-20261022"
    assert repo.metadata["input_lineage"]["statistical_results"] == "cleaned-20261022"
    assert repo.metadata["baseline_status"] == "unverified"
    assert repo.metadata["tiktok_collection"] == "excluded"
    assert not any("draft-v1" in path for path in repo.file_catalog().path)
    ads = repo.table(PREFIX + "ads_history.csv")
    assert ads.ad_account_id.tolist() == ["000123", "000123"]
    assert ads.spend.iloc[0] == 0 and pd.isna(ads.spend.iloc[1])
    catalog = repo.table(PREFIX + "dataset_catalog.csv")
    lineage = catalog[catalog.table.eq(PREFIX + "ads_history.csv")].iloc[0]
    assert hashlib.sha256(repo.original_bytes(lineage.retained_input_path)).hexdigest() == lineage.input_sha256
    assert pd.isna(repo.table("social/account_daily.csv").value.iloc[0])
    assert repo.original_zip() == Path(result["zip_path"]).read_bytes()


def test_blocked_and_absent_collection_statuses_are_not_zero(inputs, tmp_path):
    _, repo = package(inputs, tmp_path)
    status = repo.table(PREFIX + "collection_status.csv").set_index("dataset")
    assert status.loc["instagram_follows", "status"] == "blocked"
    assert status.loc["instagram_stories", "status"] == "not_collected"
    assert status.loc["ads_manager", "status"] == "retained_separate_evidence"
    assert "value" not in status
    mapping = repo.table(PREFIX + "mapping/post_song_references.csv")
    assert len(mapping) == 3 and mapping.post_key.nunique() == 2
    assert not mapping.stream_attribution_available.any()
    assert "views" not in mapping and "streams" not in mapping


def test_existing_output_refused_without_mutation(inputs, tmp_path):
    parent, collection, _ = inputs
    first = build_meta_collection(parent, collection, tmp_path / "output", tmp_path / "output.zip")
    before = Path(first["zip_path"]).read_bytes()
    with pytest.raises(FileExistsError, match="Preserving"):
        build_meta_collection(parent, collection, tmp_path / "output", tmp_path / "output.zip")
    assert Path(first["zip_path"]).read_bytes() == before


@pytest.mark.parametrize("raw,message", [
    (b"value,value_status\n0,unavailable\n", "blank"),
    (b"value,value_status\n,observed\n", "numeric"),
    (b"value,value_status\ninf,observed\n", "finite"),
    (b"captured_at_utc,value,value_status\n2026-10-23T01:00:00,1,observed\n", "UTC offset"),
    (b"one,two\n1,2,3\n", "Malformed"),
])
def test_invalid_collection_evidence_rejected_before_output(inputs, tmp_path, raw, message):
    parent, collection, _ = inputs
    (collection / "normalized/follows_daily.csv").write_bytes(raw)
    with pytest.raises(StorageError, match=message):
        build_meta_collection(parent, collection, tmp_path / "output", tmp_path / "output.zip")
    assert not (tmp_path / "output").exists()


def test_mapping_predecessor_mismatch_rejected(inputs, tmp_path):
    parent, collection, _ = inputs
    (collection / "mapping/coverage.json").write_text('{"source_database_sha256_before":"wrong"}')
    with pytest.raises(StorageError, match="different analysis"):
        build_meta_collection(parent, collection, tmp_path / "output", tmp_path / "output.zip")


def test_collected_empty_report_is_distinct_from_unavailable(inputs, tmp_path):
    _, collection, _ = inputs
    (collection / "normalized/ads_history.csv").write_bytes(b"ad_account_id,spend,reporting_start,reporting_end\n")
    _, repo = package(inputs, tmp_path)
    status = repo.table(PREFIX + "collection_status.csv").set_index("dataset")
    assert status.loc["ads_manager", "status"] == "retained_empty_report"
    assert repo.table(PREFIX + "ads_history.csv").empty


def test_collection_dashboard_has_ads_repairs_mapping_and_pinned_statistics(inputs, tmp_path):
    _, repo = package(inputs, tmp_path)
    code = ("from stats_app.analysis_repository import AnalysisRepository\n"
            "from stats_app.analysis_meta_ui import render_meta_collection\n"
            f"render_meta_collection(AnalysisRepository({str(repo.db_path)!r}))\n")
    app = AppTest.from_string(code, default_timeout=30).run()
    assert not app.exception and not app.error
    assert any("no total" in warning.value.lower() for warning in app.warning)
    assert any("cleaned-20261022" in info.value for info in app.info)
    assert any(len(frame.value) == 2 and "spend" in frame.value for frame in app.dataframe)
    next(item for item in app.radio if item.label == "Collection view").set_value("Repairs status").run()
    assert not app.exception and not app.error
    assert any("follower stock" in info.value for info in app.info)
    next(item for item in app.radio if item.label == "Collection view").set_value("Post/song/event map").run()
    assert not app.exception and not app.error
    assert any("bridge rows must never multiply" in warning.value for warning in app.warning)
    assert any(len(frame.value) == 3 and "song_id" in frame.value for frame in app.dataframe)


def test_repairs_show_story_metrics_and_reset_filters_between_tables(inputs, tmp_path):
    _, collection, _ = inputs
    (collection / "normalized/instagram_story_metrics.csv").write_bytes(
        b"metric,value,value_status\nviews,0,observed_zero\nreach,,unavailable_source_marker\n")
    (collection / "normalized/instagram_stories_manual.csv").write_bytes(
        b"post_id,views,views_status\n001,0,observed_zero\n")
    (collection / "normalized/follows_daily_resolved.csv").write_bytes(
        b"date,value,value_status\n2026-10-19,1,observed\n2026-10-20,0,observed_zero\n")
    _, repo = package(inputs, tmp_path)
    code = ("from stats_app.analysis_repository import AnalysisRepository\n"
            "from stats_app.analysis_meta_ui import render_meta_collection\n"
            f"render_meta_collection(AnalysisRepository({str(repo.db_path)!r}))\n")
    app = AppTest.from_string(code, default_timeout=30).run()
    app.radio[0].set_value("Repairs status").run()
    selector = next(item for item in app.selectbox if item.label == "Repair evidence table")
    assert "instagram_story_metrics.csv" in selector.options
    assert "instagram_stories_manual.csv" in selector.options
    assert "repair_status.csv" in selector.options
    assert "ads_history.csv" not in selector.options
    selector.set_value(PREFIX + "instagram_story_metrics.csv").run()
    filter_widget = next(item for item in app.multiselect if item.label.startswith("Value status"))
    story_filter_key = filter_widget.key
    filter_widget.set_value(["unavailable_source_marker"]).run()
    assert len(app.dataframe[-1].value) == 1
    assert pd.isna(app.dataframe[-1].value.value.iloc[0])
    next(item for item in app.selectbox if item.label == "Repair evidence table").set_value(
        PREFIX + "follows_daily_resolved.csv").run()
    assert not app.exception and not app.error
    new_filter = next(item for item in app.multiselect if item.label.startswith("Value status"))
    assert new_filter.key != story_filter_key and new_filter.value == []
    assert len(app.dataframe[-1].value) == 2


def test_dependent_collection_filter_resets_when_options_change():
    code = """
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
import streamlit as st
from stats_app.analysis_meta_ui import _filter
data = pd.DataFrame({'scope': ['Facebook', 'Facebook', 'Instagram', 'Instagram'],
                     'status': ['fb_a', 'fb_b', 'ig_a', 'ig_b']})
st.dataframe(_filter(data, ['scope', 'status'], SimpleNamespace(db_path=Path('test.sqlite3')), 'test-table'))
"""
    app = AppTest.from_string(code).run()
    app.multiselect[1].set_value(["fb_a"]).run()
    previous_key = app.multiselect[1].key
    app.multiselect[0].set_value(["Instagram"]).run()
    assert not app.exception and not app.error
    assert app.multiselect[1].options == ["ig_a", "ig_b"]
    assert app.multiselect[1].key != previous_key and app.multiselect[1].value == []
    assert len(app.dataframe[0].value) == 2


def test_mapping_platform_filters_do_not_carry_between_tables(inputs, tmp_path):
    _, collection, _ = inputs
    (collection / "mapping/event_map.csv").write_bytes(
        b"event_kind,platform_selected\ncaption_claim,Instagram\nrelease_metadata,Facebook\n")
    _, repo = package(inputs, tmp_path)
    code = ("from stats_app.analysis_repository import AnalysisRepository\n"
            "from stats_app.analysis_meta_ui import render_meta_collection\n"
            f"render_meta_collection(AnalysisRepository({str(repo.db_path)!r}))\n")
    app = AppTest.from_string(code, default_timeout=30).run()
    app.radio[0].set_value("Post/song/event map").run()
    platforms = next(item for item in app.multiselect if item.label.startswith("Mapping platforms"))
    previous_key = platforms.key
    platforms.set_value(["Instagram"]).run()
    assert len(app.dataframe[-1].value) == 2
    next(item for item in app.selectbox if item.label == "Mapping evidence table").set_value(
        PREFIX + "mapping/event_map.csv").run()
    assert not app.exception and not app.error
    platforms = next(item for item in app.multiselect if item.label.startswith("Mapping platforms"))
    assert platforms.key != previous_key and platforms.value == []
    assert len(app.dataframe[-1].value) == 2
