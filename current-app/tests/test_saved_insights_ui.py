"""The native readout, source inspection and full-report exports keep their scope."""
import io
import json

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from stats_app.config import PROJECT_ROOT
from stats_app.saved_insights import load_saved_insights
from stats_app.storage import StorageError


SCRIPT = """
from stats_app import dashboard_controls as controls
from stats_app.saved_insights_ui import render_saved_insights
controls.begin_view('TikTok insights')
render_saved_insights()
controls.reset_button('TikTok insights')
controls.finish_view()
"""


def test_report_sections_render_known_values_and_charts_without_external_runtime():
    app = AppTest.from_string(SCRIPT, default_timeout=30).run()
    assert not app.exception and not app.error
    assert any("30.6%" in text.value and "34.6%" in text.value for text in app.markdown)
    assert any("Artists remains pending" in text.value for text in app.caption)
    assert not any(s.label == "Analysis version" for s in app.selectbox)
    expected = {"Trends": 2, "Song priorities": 1, "Post examples": 0, "Other platforms": 0, "Sources & downloads": 0}
    for view, charts in expected.items():
        app.radio("control:insights:section").set_value(view).run()
        assert not app.exception and not app.error, view
        assert len(app.get("plotly_chart")) == charts
        if view == "Song priorities":
            payload = json.loads(app.get("plotly_chart")[0].proto.spec)
            assert "Funny Guy" in str(payload)
            assert any("1,488" in text.value and "539" in text.value for text in app.markdown)


def test_evidence_search_download_and_reset_preserve_report_view(monkeypatch):
    downloads = {}
    original = st.download_button
    def capture(*args, **kwargs):
        key = kwargs.get("key")
        if key:
            downloads[key] = kwargs.get("data", args[1] if len(args) > 1 else None)
        return original(*args, **kwargs)
    monkeypatch.setattr(st, "download_button", capture)
    # Downloads inside columns call DeltaGenerator directly rather than the
    # module-level bound method, so inspect both public rendering paths.
    from streamlit.delta_generator import DeltaGenerator
    original_column_download = DeltaGenerator.download_button
    def capture_column(self, *args, **kwargs):
        key = kwargs.get("key")
        if key:
            downloads[key] = kwargs.get("data", args[1] if len(args) > 1 else None)
        return original_column_download(self, *args, **kwargs)
    monkeypatch.setattr(DeltaGenerator, "download_button", capture_column)
    app = AppTest.from_string(SCRIPT).run()
    app.radio("control:insights:section").set_value("Sources & downloads").run()
    app.selectbox("control:insights:evidence").set_value("songs").run()
    assert len(app.dataframe[0].value) == 14
    full_html = downloads["insights:html-download"]
    provenance = json.loads(downloads["insights:provenance-download"])
    assert provenance["source_receipts"]["tiktok_tables"]["post_inventory"]["rows"] == 615
    assert "sources.json" in provenance["manifest"]["assets"]
    app.text_input("control:insights:search").set_value("Funny Guy").run()
    assert not app.exception and not app.error
    filtered = pd.read_csv(io.StringIO(downloads["insights:evidence-download"].decode("utf-8-sig")))
    assert filtered.recording_label.tolist() == ["Funny Guy"]
    assert filtered.streams.iloc[0] == 1488
    assert downloads["insights:html-download"] == full_html
    assert "Shopify" in full_html and "The Cut" in full_html
    app.text_input("control:insights:search").set_value("no-matching-record-8274").run()
    assert any("No evidence rows match" in item.value for item in app.info)
    app.session_state["selection:spotify:preset"] = "Latest 90 days"
    app.button("reset:TikTok insights").click().run()
    assert app.radio("control:insights:section").value == "Sources & downloads"
    assert app.text_input("control:insights:search").value == ""
    assert app.session_state["selection:spotify:preset"] == "Latest 90 days"


def test_unavailable_or_failed_report_is_explicit(monkeypatch):
    import stats_app.saved_insights_ui as module
    monkeypatch.setattr(module, "load_saved_insights", lambda root=None: None)
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception and any("No saved TikTok" in item.value for item in app.info)
    def tampered(root=None):
        raise StorageError("hash mismatch")
    monkeypatch.setattr(module, "load_saved_insights", tampered)
    app.run()
    assert not app.exception
    assert any("could not be verified" in item.value for item in app.error)
    assert not app.get("plotly_chart")


def test_insights_native_route_does_not_depend_on_selected_analysis(tmp_path, monkeypatch):
    import stats_app.analysis_repository as analyses
    from native_navigation_helpers import NativeAppTest, open_page
    monkeypatch.setenv("STATS_DATA_DIR", str(tmp_path / "library"))
    monkeypatch.setenv("STATS_MODE", "local")
    app = NativeAppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=30).run()
    def unexpected(*args, **kwargs):
        raise AssertionError("Fixed report must not load the live analysis selection")
    monkeypatch.setattr(analyses, "list_registered_analyses", unexpected)
    open_page(app, "TikTok insights")
    assert not app.exception and not app.error
    assert app.session_state["_native_routes"]["TikTok insights"].url_path == "tiktok-insights"
    assert any("meta-story-backfill-20261024" in item.value for item in app.caption)
