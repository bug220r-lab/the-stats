"""Preparation remains reachable without pretending an export was collected."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from stats_app.config import PROJECT_ROOT
from stats_app.tiktok_collection import create_collection


def test_empty_preparation_is_honest_and_read_only(tmp_path):
    root = tmp_path / "collection"
    app = AppTest.from_string(f'''from pathlib import Path
from stats_app.tiktok_ui import render_tiktok_preparation
render_tiktok_preparation(Path({str(root)!r}))
''').run()
    assert not app.exception and not app.error
    assert any("No TikTok preparation workspace" in item.value for item in app.info)
    assert not root.exists()
    assert not app.metric and not app.get("plotly_chart")


def test_preparation_shows_queue_without_performance_or_mutation(tmp_path):
    root = tmp_path / "collection"
    package = root / "tiktok-synthetic"
    create_collection(package, profile_url="https://www.tiktok.com/@synthetic_account", prepared_on="2026-10-26")
    before = {p.relative_to(package): p.read_bytes() for p in package.rglob("*") if p.is_file()}
    app = AppTest.from_string(f'''from pathlib import Path
from stats_app.tiktok_ui import render_tiktok_preparation
render_tiktok_preparation(Path({str(root)!r}))
''').run()
    assert not app.exception and not app.error
    assert any("ownership not verified" in item.value for item in app.caption)
    assert any("Preparation only" in item.value for item in app.info)
    assert len(app.dataframe) == 2
    queue = app.dataframe[0].value
    assert set(queue.Status) == {"Not collected"}
    assert not app.metric and not app.get("plotly_chart")
    assert before == {p.relative_to(package): p.read_bytes() for p in package.rglob("*") if p.is_file()}


def test_main_route_does_not_require_saved_analysis(tmp_path, monkeypatch):
    import stats_app.analysis_repository as analyses
    import stats_app.tiktok_ui as tiktok_ui
    from native_navigation_helpers import NativeAppTest, open_page
    monkeypatch.setenv("STATS_DATA_DIR", str(tmp_path / "library"))
    monkeypatch.setenv("STATS_MODE", "local")
    # This route-isolation test must not scan the user's private acquisition
    # workspace, which can contain thousands of retained source captures.
    monkeypatch.setattr(tiktok_ui, "PROJECT_ROOT", tmp_path)
    app = NativeAppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=30).run()

    def unexpected(*args, **kwargs):
        raise AssertionError("TikTok preparation must be independent of saved analysis")

    monkeypatch.setattr(analyses, "list_registered_analyses", unexpected)
    open_page(app, "TikTok")
    assert not app.exception and not app.error
    assert app.session_state["explore_page"] == "TikTok"
    assert app.session_state["_native_routes"]["TikTok"].url_path == "tiktok"
    assert any("Preparation only" in item.value for item in app.info)
