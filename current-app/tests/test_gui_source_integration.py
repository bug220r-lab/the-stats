"""Optional collection failure isolation and honest source metadata."""
from types import SimpleNamespace
from contextlib import contextmanager

import pandas as pd

from streamlit.testing.v1 import AppTest

from stats_app.source_context import repository_context
from stats_app.storage import StorageError


class Source:
    tables = []

    def __init__(self, metadata):
        self.metadata = metadata


class LoadingSnapshotRepo:
    def list_snapshots(self):
        return pd.DataFrame([{"label": "archive::saved", "display_label": "Saved archive"}])

    def observations(self, snapshot):
        import streamlit as st
        assert snapshot == "archive::saved"
        assert st.session_state.get("_snapshot_loading_test") is True
        return pd.DataFrame()


def test_context_keeps_known_calendar_and_missing_capture_distinct():
    context = repository_context(Source({"collection_key": "youtube-test", "channel_name": "Saved channel",
                                         "source_timezone": "America/Los_Angeles", "collected_at": None,
                                         "retrieval_date": "2026-10-23", "store": None}))
    assert context.account == "Saved channel" and context.timezone == "America/Los_Angeles"
    assert context.captured_at == "2026-10-23" and context.reporting_start == "Source-specific"
    unknown = repository_context(Source({"store": {"name": "Saved store", "timezone": "America/New_York"}, "collected_at": None}))
    assert unknown.account == "Saved store" and unknown.timezone == "America/New_York"
    assert unknown.captured_at.startswith("Not supplied")


def test_optional_youtube_failures_leave_independent_content_rendered(monkeypatch):
    import stats_app.youtube_repository as source

    def unavailable(*args, **kwargs):
        raise StorageError("Synthetic unavailable optional collection")

    monkeypatch.setattr(source, "load_registered_youtube", unavailable)
    monkeypatch.setattr(source, "list_registered_youtube", unavailable)
    app = AppTest.from_string('''import streamlit as st
from types import SimpleNamespace
from stats_app.ui import _optional_youtube
settings = SimpleNamespace(data_dir='unused synthetic test path')
assert _optional_youtube(settings) is None
assert _optional_youtube(settings, keys_only=True) == ()
st.metric('Independent Spotify result', 17)
''').run()
    assert not app.exception and not app.error
    assert len(app.warning) == 2 and app.metric[0].value == "17"


def test_snapshot_loading_state_covers_repository_read_and_preserves_empty_state(monkeypatch):
    import stats_app.ui as ui
    events = []
    original_spinner = ui.st.spinner

    @contextmanager
    def loading(*args, **kwargs):
        events.append((args[0], kwargs.get("show_time")))
        with original_spinner(*args, **kwargs):
            ui.st.session_state["_snapshot_loading_test"] = True
            yield
            ui.st.session_state["_snapshot_loading_test"] = False

    monkeypatch.setattr(ui.st, "spinner", loading)
    app = AppTest.from_string('''from test_gui_source_integration import LoadingSnapshotRepo
from stats_app.ui import overview
overview(LoadingSnapshotRepo())
''').run()
    assert not app.exception and not app.error
    assert events == [("Loading saved snapshot observations…", True)]
    assert app.session_state["_snapshot_loading_test"] is False
    assert any("No observations imported yet" in item.value for item in app.info)
