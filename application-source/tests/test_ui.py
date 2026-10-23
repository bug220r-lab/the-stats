"""Focused real Streamlit runtime smoke checks. Synthetic data stays in tmp_path."""
from datetime import date, timedelta
import json
import hashlib
from pathlib import Path

from streamlit.testing.v1 import AppTest

from stats.metrics import METRICS, aggregate_metric, lifetime_content_observations
from stats.storage import Store

APP = Path(__file__).resolve().parents[1] / "app.py"


def find(elements, label):
    return next(element for element in elements if element.label == label)


def assert_clean(app):
    assert not app.exception, [(error.message, error.stack_trace) for error in app.exception]


def test_empty_application_is_ready_to_import(tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DATA_DIR", str(tmp_path))
    app = AppTest.from_file(APP, default_timeout=30).run()
    assert_clean(app)
    assert app.title[0].value == "Import data"
    assert find(app.text_input, "Snapshot name")
    find(app.text_input, "Snapshot name").set_value("Isolated test snapshot").run()
    find(app.button, "Create snapshot").click().run()
    assert_clean(app)
    assert len(Store(tmp_path / "stats.sqlite3").snapshots()) == 1
    assert find(app.selectbox, "Import into snapshot")


def seeded_store(tmp_path):
    store = Store(tmp_path / "stats.sqlite3")
    snapshot = store.create_snapshot("Isolated UI fixtures")
    rows = []
    for platform, metric, entity_type in [("spotify", "streams", "artist"), ("instagram", "views", "account")]:
        for i in range(40):
            day = (date(2026, 9, 11) + timedelta(days=i)).isoformat()
            rows.append(dict(platform=platform, account_id=platform+":test",account_name="Isolated test",
                entity_type=entity_type,entity_id=platform+":test",entity_name="Isolated test",
                metric=metric,value=i+1,unit="count",definition=METRICS[metric]["definition"],
                dimensions="{}",period_start=day,period_end=day,time_grain="daily",
                captured_at="2026-10-21",source_timezone="UTC",measurement_type="period_count",
                status="available",source_row=i+2,evidence_ref="isolated UI fixture"))
    store.commit_import(snapshot,"isolated.csv",b"synthetic isolated UI fixture",rows)
    return store


def test_populated_views_filters_and_annotations(tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DATA_DIR",str(tmp_path))
    store=seeded_store(tmp_path)
    app=AppTest.from_file(APP,default_timeout=40).run()
    assert_clean(app)
    for page in ["Spotify","Social media","Cross-platform","Data & collection","Import data","Overview"]:
        app.sidebar.radio[0].set_value(page).run()
        assert_clean(app)
        assert app.title[0].value == page
    find(app.selectbox,"Reporting window").set_value("7 days").run()
    assert_clean(app)
    values={m.label:m.value for m in app.metric}
    assert values["Streams"] == "259"  # source days 34 through 40, same calculation layer
    find(app.multiselect,"Platforms").set_value([]).run()
    assert_clean(app)
    assert any("No observations match" in info.value for info in app.info)
    app.sidebar.radio[0].set_value("Data & collection").run()
    find(app.text_input,"Date (YYYY-MM-DD)").set_value("2026-10-20")
    find(app.text_input,"Title").set_value("Isolated annotation")
    find(app.button,"Save annotation").click().run()
    assert_clean(app)
    assert store.annotations()[0]["origin"] == "local_user_annotation"


def test_folder_import_preview_commit_and_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DATA_DIR", str(tmp_path / "db"))
    store = Store(tmp_path / "db" / "stats.sqlite3")
    store.create_snapshot("Folder import test")
    folder=tmp_path/"incoming"
    folder.mkdir()
    (folder/"counts.csv").write_text("Date,Streams\n2026-10-20,12\n")
    app=AppTest.from_file(APP,default_timeout=30).run()
    app.sidebar.radio[0].set_value("Import data").run()
    find(app.radio,"Source").set_value("Local folder").run()
    find(app.text_input,"Configured import folder").set_value(str(folder)).run()
    find(app.selectbox,"Default platform").set_value("spotify")
    find(app.text_input,"Default account ID / explicit source key").set_value("fixture:artist")
    find(app.selectbox,"Default entity type").set_value("artist")
    find(app.selectbox,"Default time grain").set_value("daily")
    app.run()
    assert_clean(app)
    find(app.checkbox,"I reviewed metadata, units, mappings and validation issues").check().run()
    find(app.button,"Commit import").click().run()
    assert_clean(app)
    assert len(store.read_observations()) == 1
    assert store.read_observations().iloc[0].value == 12
    restarted=AppTest.from_file(APP,default_timeout=30).run()
    assert_clean(restarted)
    assert len(Store(tmp_path / "db" / "stats.sqlite3").read_observations()) == 1


def add_lifetime_fixture(store, snapshot_id):
    observations = []
    for source_row, (post_id, published, views, reach) in enumerate([
        ("post:recent", "2026-10-15T12:30:00", 12, 8),
        ("post:older", "2025-01-01T08:00:00", 1000, 700),
        ("post:unknown", None, None, 0),
    ], start=2):
        for metric, value in (("views", views), ("reach", reach)):
            observations.append(dict(platform="instagram", account_id="instagram:test", account_name="Isolated test",
                entity_type="post", entity_id=post_id, entity_name="Isolated " + post_id, metric=metric, value=value,
                unit="count", definition="Instagram source-reported lifetime " + metric + "; cutoff not supplied.",
                dimensions=json.dumps({"measurement_window":"lifetime", "post_type":"Reel",
                                       "publication_selection_start":"2025-01-01", "publication_selection_end":"2026-10-22"}),
                period_start=None, period_end=None, time_grain="lifetime", captured_at="2026-10-22T21:00:00-04:00",
                source_timezone="America/Los_Angeles", measurement_type="distinct_audience_count" if metric=="reach" else "cumulative_total",
                status="available" if value is not None else "missing", source_row=source_row,
                evidence_ref="isolated lifetime fixture", published_at=published, source_url="https://example.invalid/" + post_id))
    store.commit_import(snapshot_id,"isolated-lifetime.csv",b"isolated lifetime content fixture",observations)


def lifetime_display(app):
    return next(element.value for element in app.dataframe if "captured_at" in element.value.columns and "entity_name" in element.value.columns)


def test_lifetime_only_snapshot_keeps_values_and_unknown_windows_visible(tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DATA_DIR", str(tmp_path))
    store = Store(tmp_path / "stats.sqlite3")
    snapshot = store.create_snapshot("Isolated lifetime content")
    add_lifetime_fixture(store,snapshot)
    original = store.read_observations()
    assert aggregate_metric(original,"views")["value"] is None
    assert len(lifetime_content_observations(original)) == 6
    app = AppTest.from_file(APP,default_timeout=30).run()
    assert_clean(app)
    assert not any(element.label=="Reporting window" for element in app.selectbox)
    app.sidebar.radio[0].set_value("Social media").run()
    assert_clean(app)
    displayed = lifetime_display(app)
    assert len(displayed) == 6
    assert displayed.iloc[0].entity_id == "post:recent"  # source order, not performance rank
    assert displayed.period_start.isna().all() and displayed.period_end.isna().all()
    assert displayed.captured_at.eq("2026-10-22T21:00:00-04:00").all()
    assert len(app.metric) == 0  # no fabricated period KPI or lifetime conversion ratio
    assert any(element.proto.label=="Download lifetime content observations" for element in app.get("download_button"))
    assert any("does not establish a metric cutoff" in element.value for element in app.info)
    find(app.radio,"Content publication selection").set_value("Custom publication dates").run()
    find(app.date_input,"Content publication dates").set_value((date(2026,10,1),date(2026,10,22))).run()
    find(app.multiselect,"Lifetime content metrics").set_value(["views"]).run()
    assert_clean(app)
    displayed = lifetime_display(app)
    assert set(displayed.entity_id) == {"post:recent","post:unknown"}
    assert displayed.loc[displayed.entity_id.eq("post:recent"),"value"].iloc[0] == 12
    assert displayed.loc[displayed.entity_id.eq("post:unknown"),"value"].isna().all()
    for page in ["Data & collection","Cross-platform","Overview"]:
        app.sidebar.radio[0].set_value(page).run()
        assert_clean(app)
    assert store.read_observations().period_start.isna().all()


def test_lifetime_content_survives_sidebar_period_filter_and_export(tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DATA_DIR",str(tmp_path))
    store = seeded_store(tmp_path)
    add_lifetime_fixture(store,store.snapshots()[0]["id"])
    app = AppTest.from_file(APP,default_timeout=30).run()
    find(app.selectbox,"Reporting window").set_value("7 days").run()
    app.sidebar.radio[0].set_value("Social media").run()
    assert_clean(app)
    displayed = lifetime_display(app)
    assert set(displayed.entity_id)=={"post:recent","post:older","post:unknown"}
    assert len(displayed)==6
    assert {metric.label:metric.value for metric in app.metric}["Views"]=="259"
    # Capture the exact Data download frame; its same selected snapshot must keep
    # lifetime rows even though their publication dates lie outside seven days.
    import stats.ingestion
    captured=[]
    original=stats.ingestion.safe_csv
    def record(frame):
        captured.append(frame.copy())
        return original(frame)
    monkeypatch.setattr(stats.ingestion,"safe_csv",record)
    app.sidebar.radio[0].set_value("Data & collection").run()
    assert_clean(app)
    exported=next(frame for frame in captured if "time_grain" in frame.columns and frame.time_grain.eq("lifetime").any())
    assert exported.time_grain.eq("lifetime").sum()==6
    assert exported[exported.time_grain.eq("lifetime")].period_start.isna().all()
    assert len(exported[exported.time_grain.eq("daily")])==14  # seven days × two platforms


def test_social_default_account_prefers_views_without_merging_native_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DATA_DIR",str(tmp_path))
    store=Store(tmp_path/"stats.sqlite3")
    snapshot=store.create_snapshot("Isolated separate account identities")
    observations=[]
    for account_id,metric,value in [("facebook:source-audience","unique_user_engagements",7),("native-page-123","views",42)]:
        observations.append(dict(platform="facebook",account_id=account_id,account_name="Fixture Page",
            entity_type="account",entity_id=account_id,entity_name="Fixture Page",metric=metric,value=value,
            unit="count",definition=METRICS[metric]["definition"],dimensions="{}",period_start="2026-10-20",
            period_end="2026-10-20",time_grain="daily",captured_at="2026-10-22",source_timezone="UTC",
            measurement_type=METRICS[metric]["measurement_type"],status="available",source_row=2))
    store.commit_import(snapshot,"separate-ids.csv",b"isolated separate account source IDs",observations)
    app=AppTest.from_file(APP,default_timeout=30).run()
    find(app.selectbox,"Reporting window").set_value("All dates").run()
    assert_clean(app)
    account=find(app.selectbox,"Account")
    assert account.value=="native-page-123"
    assert any("Fixture Page" in label and "native-page-123" in label for label in account.options)
    assert {metric.label:metric.value for metric in app.metric}["Views"]=="42"
    account.set_value("facebook:source-audience").run()
    assert_clean(app)
    assert {metric.label:metric.value for metric in app.metric}["Unique user engagements"]=="7"
    assert store.read_observations().account_id.nunique()==2


def test_collection_coverage_and_combined_export_scope_are_visible(tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DATA_DIR",str(tmp_path))
    store=Store(tmp_path/"stats.sqlite3")
    name="Isolated current social capture"
    snapshot=store.create_snapshot(name)
    raw=b"isolated combined-scope observation"
    source=dict(platform="instagram",account_id="meta_asset:fixture",account_name="Fixture Instagram source",
        entity_type="account",entity_id="meta_asset:fixture",entity_name="Fixture",metric="views",value=55,
        unit="count",definition="Native source views with explicitly combined Instagram and Facebook scope.",
        dimensions=json.dumps({"source_report":"meta_account_results","reported_scope":"instagram_and_facebook","account_identity_basis":"selected_meta_asset"}),
        period_start="2026-10-20",period_end="2026-10-20",time_grain="daily",captured_at="2026-10-22",
        source_timezone="America/Los_Angeles",measurement_type="period_count",status="available",source_row=4)
    store.commit_import(snapshot,"combined.csv",raw,[source])
    capture=tmp_path/"social_captures"/"2026-10-22"
    capture.mkdir(parents=True)
    (capture/"capture_manifest.json").write_text(json.dumps({"snapshot_name":name,"files":[{"platform":"instagram","path":"combined.csv","sha256":hashlib.sha256(raw).hexdigest()}],
        "collection_gaps":[{"platform":"tiktok","status":"blocked","reason":"User sign-in required"},{"platform":"instagram","scope":"Stories","status":"unavailable","reason":"Native export disabled"}]}))
    app=AppTest.from_file(APP,default_timeout=30).run()
    find(app.selectbox,"Reporting window").set_value("All dates").run()
    assert_clean(app)
    assert {metric.label:metric.value for metric in app.metric}["Views"]=="55"
    assert any("Instagram and Facebook combined" in element.value for element in app.info)
    assert any("Reported scope: Instagram and Facebook combined" in element.value for element in app.caption)
    app.sidebar.radio[0].set_value("Data & collection").run()
    assert_clean(app)
    coverage=next(element.value for element in app.dataframe if "loaded_manifest_files" in element.value.columns)
    assert coverage.iloc[0].active_observations==1
    assert coverage.iloc[0].loaded_manifest_files==1
    gaps=next(element.value for element in app.dataframe if "reason" in element.value.columns and "snapshot" in element.value.columns)
    assert set(gaps.status)=={"blocked","unavailable"}
    assert gaps.snapshot.eq(name).all()
    catalog=next(element.value for element in app.dataframe if "aggregation" in element.value.columns)
    assert "video_views_3s" in catalog.metric.values
