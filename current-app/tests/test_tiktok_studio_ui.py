"""Studio views retain reporting scope, missingness and native precision."""
import json

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from stats_app.tiktok_ui import exact_values, post_records


def _tables():
    return {
        "account_daily": [
            {"date": "2026-10-24", "video_views": "10", "profile_views": "0", "likes": "2", "shares": "0", "comments_signed_native": "-1", "comments_status": "source_signed_net_semantics_unverified"},
            {"date": "2026-10-25", "video_views": "20", "profile_views": "3", "likes": "4", "shares": "1", "comments_signed_native": "0", "comments_status": "source_signed_net_semantics_unverified"}],
        "post_inventory": [
            {"post_id": "00001", "caption_raw": "A rounded post", "canonical_url": "https://www.tiktok.com/@example/video/00001"},
            {"post_id": "00002", "caption_raw": "An exact post", "canonical_url": ""}],
        "post_summary": [
            {"post_id": "00001", "canonical_index": "1", "views_raw": "1.3M", "views_exact": "", "views_status": "rounded_or_unavailable", "likes_raw": "0", "likes_exact": "0", "likes_status": "exact_displayed", "comments_raw": "4", "comments_exact": "4", "comments_status": "exact_displayed", "shares_raw": "", "saves_raw": "9", "average_watch_time_raw": "8.2s", "completion_rate_raw": "21.7%", "total_play_time_raw": "10h", "new_followers_raw": "3.2K", "captured_at": "2026-10-27T00:00:00Z", "posted_date_raw": "Posted on 10/1/2026"},
            {"post_id": "00002", "canonical_index": "2", "views_raw": "9", "views_exact": "9", "views_status": "exact_displayed", "likes_raw": "1", "likes_exact": "1", "likes_status": "exact_displayed", "comments_raw": "0", "comments_exact": "0", "comments_status": "exact_displayed", "shares_raw": "0", "saves_raw": "0", "captured_at": "2026-10-27T01:00:00Z"}],
        "post_viewers": [{"post_id": "00001", "total_viewers_raw": "900K", "precision": "rounded_or_unavailable", "scope": "not additive", "captured_at": "2026-10-27T00:00:10Z"}],
        "post_breakdowns": [{"post_id": "00001", "dimension": "Traffic source", "label": "Sound", "value_raw": "<0.1%", "value_status": "less_than_bound", "scope": "native snapshot", "captured_at": "2026-10-27T00:00:00Z"}],
        "post_panels": [{"post_id": "00001", "section": "overview", "source_url": "https://www.tiktok.com/tiktokstudio/analytics/00001/overview"}],
        "viewer_daily": [{"date": "2026-10-24", "total_viewers": "4", "total_viewers_raw": "4", "total_viewers_status": "observed_exact"}, {"date": "2026-10-25", "total_viewers": "", "total_viewers_raw": "undefined", "total_viewers_status": "unavailable"}],
        "follower_daily": [{"date": "2026-10-24", "followers": "8", "net_followers": "-2"}, {"date": "2026-10-25", "followers": "9", "net_followers": "1"}],
        "content_rankings": [{"source_file": "likes-7.json", "rank": "1", "row_text": "Example ranking", "semantic_scope": "7 days"}, {"source_file": "views-28.json", "rank": "1", "row_text": "Separate ranking", "semantic_scope": "28 days"}],
        "recent_comments": [{"author": "Example", "row_text": "A comment", "observation_fingerprint": "same", "source_file": "first.json"}, {"author": "Example", "row_text": "A comment", "observation_fingerprint": "same", "source_file": "second.json"}],
        "source_dispositions": [{"source": "later.zip", "disposition": "excluded_from_daily_series", "reason": "duplicate date labels"}],
    }


def _app(tables=None):
    tables = _tables() if tables is None else tables
    payload = json.dumps(tables)
    script = f'''import json
import pandas as pd
from stats_app import dashboard_controls as controls
from stats_app.tiktok_ui import render_tiktok_studio
class Repo:
    metadata = {{"account": "@example", "collected_at": "2026-10-27T00:00:00Z", "date_resolution_summary": "Initial native calendar preferred; later conflicting exports retained separately.", "limitations": ["Timezone unknown."]}}
    def __init__(self):
        self.data = json.loads({payload!r})
        self.datasets = pd.DataFrame([{{"dataset_id": key, "path": key + ".csv", "status": "collected", "row_count": len(rows)}} for key, rows in self.data.items()])
    def table(self, key):
        return pd.DataFrame(self.data[key])
    def sources(self):
        return pd.DataFrame([{{"path": "source.txt", "bytes": 7, "sha256": "test"}}])
    def source_bytes(self, path):
        return b"source\\n"
controls.begin_view("TikTok")
controls.selectbox("Collection", ["one", "two"], key="tiktok_collection_selector")
render_tiktok_studio(Repo())
controls.finish_view()
controls.reset_button("TikTok")
'''
    return AppTest.from_string(script).run(timeout=20)


def test_exact_values_keep_zero_but_not_rounded_unavailable_or_infinite():
    data = pd.DataFrame({"value": ["0", "4", "12", "1.3M", "inf", ""],
                         "value_status": ["observed_zero", "exact_displayed", "unavailable", "rounded_or_unavailable", "observed", "unavailable"]})
    result = exact_values(data)
    assert result.iloc[:2].tolist() == [0, 4]
    assert result.iloc[2:].isna().all()
    assert data.value.tolist() == ["0", "4", "12", "1.3M", "inf", ""]


def test_post_join_rejects_duplicate_identity_and_preserves_summary_scope():
    inventory = pd.DataFrame([{"post_id": "001", "views_exact": "4"}])
    summary = pd.DataFrame([{"post_id": "001", "views_exact": "5", "captured_at": "later"}])
    result = post_records(inventory, summary)
    assert result.iloc[0].views_exact == "5" and result.iloc[0].views_exact_inventory == "4"
    with pytest.raises(pd.errors.MergeError):
        post_records(pd.concat([inventory, inventory]), summary)


def test_daily_ui_uses_reviewed_calendar_and_does_not_chart_signed_comments():
    app = _app()
    assert not app.exception and not app.error
    assert app.metric[0].value == "30"
    assert any("Initial native calendar preferred" in item.value for item in app.info)
    assert any("Artists remains pending" in item.value for item in app.caption)
    assert app.selectbox("control:tiktok:daily:metric").options == ["Video views", "Profile views", "Likes", "Shares"]
    assert any("signed comment values" in item.value for item in app.caption)
    app.selectbox("control:tiktok:daily:metric").set_value("profile_views").run()
    assert not app.exception and app.metric[0].value == "3"


def test_daily_gap_and_duplicate_dates_do_not_manufacture_totals():
    tables = _tables()
    tables["account_daily"][1]["date"] = "2026-10-26"
    app = _app(tables)
    assert not app.exception and len(app.metric) == 0
    assert any("3-day selection" in item.value for item in app.caption)
    tables["account_daily"][1]["date"] = "2026-10-24"
    app = _app(tables)
    assert not app.exception and not app.get("plotly_chart")
    assert any("repeated reporting dates" in item.value for item in app.warning)


def test_posts_retain_rounded_values_bounds_and_missingness_then_sort_exact_only():
    app = _app()
    app.radio("control:tiktok:section").set_value("Owned posts").run()
    assert not app.exception and not app.error
    assert [metric.value for metric in app.metric] == ["1.3M", "0", "4", "Unavailable", "9"]
    assert any("<0.1%" in frame.value.astype(str).to_string() for frame in app.dataframe)
    app.selectbox("control:tiktok:posts:order").set_value("Exact views · highest first").run()
    assert not app.exception
    assert app.dataframe[0].value.post_id.tolist() == ["00002", "00001"]
    app.text_input("control:tiktok:posts:search").set_value("exact post").run()
    assert app.dataframe[0].value.post_id.tolist() == ["00002"]
    assert app.metric[0].value == "9"
    app.text_input("control:tiktok:posts:search").set_value("does not exist").run()
    assert any("No posts match" in item.value for item in app.info)


def test_audience_comments_and_rankings_do_not_merge_snapshots():
    app = _app()
    app.radio("control:tiktok:section").set_value("Audience reports").run()
    assert not app.exception
    assert app.dataframe[0].value.iloc[-1].total_viewers_raw == "undefined"
    assert app.dataframe[0].value.iloc[-1].total_viewers == ""
    assert not app.metric and len(app.get("plotly_chart")) == 1
    assert any("No audience or follower-stock sum" in item.value for item in app.caption)
    app.selectbox("control:tiktok:audience:dataset").set_value("follower_daily").run()
    app.selectbox("control:tiktok:audience:follower_daily:metric").set_value("net_followers").run()
    assert not app.exception and not app.metric
    assert app.dataframe[0].value.iloc[0].net_followers == "-2"
    app.radio("control:tiktok:section").set_value("Rankings & comments").run()
    assert not app.exception and len(app.dataframe[0].value) == 1
    app.selectbox("control:tiktok:interactions:kind").set_value("Recent comments").run()
    assert not app.exception and len(app.dataframe[0].value) == 2
    assert any("2 repeated row observations · 1 distinct row fingerprints" in item.value for item in app.caption)
    assert any("not asserted unique comment IDs" in item.value for item in app.caption)


def test_coverage_sources_and_reset_keep_section_source_and_other_view():
    app = _app()
    app.selectbox("control:tiktok_collection_selector").set_value("two").run()
    app.radio("control:tiktok:section").set_value("Coverage & sources").run()
    assert not app.exception and any("Artists remains pending" in item.value for item in app.info)
    app.text_input("control:tiktok:sources:search").set_value("source").run()
    app.toggle("tiktok:sources:manifest").set_value(True).run()
    app.session_state["selection:spotify:preset"] = "Latest 90 days"
    app.button("reset:TikTok").click().run()
    assert not app.exception
    assert app.radio("control:tiktok:section").value == "Coverage & sources"
    assert app.selectbox("control:tiktok_collection_selector").value == "two"
    assert app.text_input("control:tiktok:sources:search").value == ""
    assert not app.toggle("tiktok:sources:manifest").value
    assert app.session_state["selection:spotify:preset"] == "Latest 90 days"


def test_registered_studio_route_is_independent_of_saved_analysis(tmp_path, monkeypatch):
    import stats_app.analysis_repository as analyses
    from native_navigation_helpers import NativeAppTest, open_page
    from stats_app.config import PROJECT_ROOT
    from stats_app.tiktok_repository import import_tiktok_collection
    from tiktok_studio_fixtures import studio_package

    source = studio_package(tmp_path)
    library = tmp_path / "library"
    import_tiktok_collection(source, library)
    monkeypatch.setenv("STATS_DATA_DIR", str(library))
    monkeypatch.setenv("STATS_MODE", "local")
    app = NativeAppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=30).run()
    def unexpected(*args, **kwargs):
        raise AssertionError("TikTok Studio must not select or mutate saved analyses")
    monkeypatch.setattr(analyses, "list_registered_analyses", unexpected)
    open_page(app, "TikTok")
    assert not app.exception and not app.error
    assert app.metric[0].value == "12"
    assert not any("Preparation only" in item.value for item in app.info)
    assert any("Artists remains pending" in item.value for item in app.caption)
