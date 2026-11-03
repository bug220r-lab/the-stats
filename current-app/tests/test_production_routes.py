"""Exercise the real page handlers without discovering private report packages."""
import pytest

from native_navigation_helpers import NativeAppTest as AppTest, open_page
from stats_app.config import PROJECT_ROOT
from stats_app.navigation import PAGE_PATHS


@pytest.fixture
def empty_app(tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DATA_DIR", str(tmp_path / "library"))
    monkeypatch.setenv("STATS_MODE", "local")
    monkeypatch.delenv("STATS_IMPORT_DIR", raising=False)
    # These optional historical views use source-relative packages rather than
    # STATS_DATA_DIR. Redirect their lookup roots, keeping production renderers.
    from stats_app import growth_ui, saved_insights, tiktok_ui
    for module in (growth_ui, saved_insights, tiktok_ui):
        monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path / "optional")
    at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception and not at.error
    return at


@pytest.mark.parametrize("page", tuple(PAGE_PATHS))
def test_production_routes_render_without_private_packages(empty_app, page):
    open_page(empty_app, page)
    assert not empty_app.error
    assert empty_app.session_state["explore_page"] == page


def test_content_plan_shortcut_returns_to_campaign_workflow(empty_app):
    open_page(empty_app, "Campaigns")
    empty_app.button("campaigns:open-content-plan").click().run()
    assert not empty_app.exception and not empty_app.error
    assert empty_app.session_state["explore_page"] == "Content plan"
    assert any("content plan" in message.value.lower() and "unavailable" in message.value.lower()
               for message in empty_app.info)
    empty_app.button("content-plan:open-campaigns").click().run()
    assert not empty_app.exception and not empty_app.error
    assert empty_app.session_state["explore_page"] == "Campaigns"
