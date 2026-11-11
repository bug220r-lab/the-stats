"""Filter summaries distinguish one tuple option from multiple values."""
from datetime import date
from unittest.mock import patch

import pytest

from stats_app import dashboard_controls as controls


@pytest.mark.parametrize("label,value,options,formatter,expected", [
    ("Apple artist or content", ("artist", "apple-id"), [("artist", "apple-id")],
     {("artist", "apple-id"): "All Songs · artist"}.get, "All Songs · artist"),
    ("Exact Apple source period", ("2026-09-26", "2026-10-23"), [("2026-09-26", "2026-10-23")],
     lambda period: f"{period[0]} – {period[1]}", "2026-09-26 – 2026-10-23"),
    ("Reporting dates", (date(2026, 9, 26), date(2026, 10, 23)), None,
     str, "2026-09-26, 2026-10-23"),
    ("Recordings · empty means all", [], ["one", "two"], str, "All available"),
    ("Content platforms", [], ["Instagram", "Facebook"], str, "None selected"),
    ("Content platforms", ["Instagram", "Facebook"], ["Instagram", "Facebook"], str, "All available"),
])
def test_filter_summary_formats_one_tuple_or_multiple_values(label, value, options, formatter, expected):
    state = {"_active_view_scope": "Apple Music", "selection:analysis_version": "source-one",
             "_view_filter_summaries": {"Spotify": {"spotify:preset": "Spotify period: Latest 90 days"}}}
    with patch.object(controls.st, "session_state", state):
        controls._record(label, "test:filter", value, options, formatter)
    assert state["_view_filter_summaries"]["Apple Music"]["test:filter"] == f"{label}: {expected}"
    assert state["_view_filter_summaries"]["Spotify"] == {"spotify:preset": "Spotify period: Latest 90 days"}
    assert state["selection:analysis_version"] == "source-one"
