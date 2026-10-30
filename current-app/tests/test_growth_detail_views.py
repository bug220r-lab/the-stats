"""Read-only detail identity and Apple source-grain UI contracts."""
from datetime import date
import json

import pandas as pd
from streamlit.testing.v1 import AppTest

from stats_app.apple_music_ui import apple_snapshot_catalog, daily_statistics, matched_artist_activity
from stats_app.row_details import selected_identity, selection_key, safe_web_url


def apple_rows(metric="plays", values=(0, 6, 9)):
    rows = []
    for number, value in enumerate(values, 1):
        rows.append(dict(platform="Apple Music", account="apple-artist", entity_type="artist", entity_id="apple-id",
                         entity_name="All Songs", metric=metric, unit="count", time_grain="daily",
                         measurement_type="distinct_count" if metric == "daily_unique_listeners" else "period_count",
                         source_timezone="UTC", dimensions_json='{"entity_scope":"artist"}', definition="Retained source definition",
                         period_start=f"2026-10-{number:02d}", period_end=f"2026-10-{number:02d}",
                         value=value, status="observed" if value is not None else "missing", observation_id=f"local::{number}",
                         source_names="source.csv", captured_at="2026-10-25T12:00:00Z"))
    return pd.DataFrame(rows)


class AppleRepo:
    def list_snapshots(self):
        return pd.DataFrame([dict(label="local::apple-aggregate", stored_label="apple-aggregate", sealed=1),
                             dict(label="local::apple-daily", stored_label="apple-daily", sealed=1),
                             dict(label="local::apple-draft", stored_label="apple-draft", sealed=0)])

    def observations(self, snapshot):
        if snapshot.endswith("daily"):
            return pd.concat([apple_rows(), apple_rows("daily_unique_listeners", (0, 2, 3))], ignore_index=True)
        row = apple_rows().iloc[[0]].copy()
        row.loc[:, "time_grain"] = "monthly"
        row.loc[:, "period_end"] = "2026-10-03"
        row.loc[:, "value"] = 17  # Deliberate retained discrepancy against daily sum 15.
        return row

    def observation_provenance(self, observation):
        return pd.DataFrame([dict(observation_id=observation, source_hash="test-source")])

    def original_source(self, digest):
        raise AssertionError("Closed source panels must not read original bytes")


def test_selection_resolves_stable_ids_and_invalid_positions():
    frame = pd.DataFrame({"identity": ["ig/account-a/7", "ig/account-b/7"], "title": ["Same title", "Same title"]})
    assert selected_identity({"selection": {"rows": [1]}}, frame, "identity") == "ig/account-b/7"
    assert selected_identity({"selection": {"rows": [-1]}}, frame, "identity") is None
    assert selected_identity({"selection": {"rows": [3]}}, frame, "identity") is None
    assert selection_key("rows", frame, ["identity"]) != selection_key("rows", frame.iloc[::-1], ["identity"])
    assert safe_web_url("javascript:alert(1)") is None
    assert safe_web_url("https://example.com/post/7") == "https://example.com/post/7"


def test_apple_missingness_daily_unique_and_scope_are_not_combined():
    start, end = date(2026, 10, 1), date(2026, 10, 3)
    plays = apple_rows()
    result = daily_statistics(plays, start, end)
    assert result["complete"] and result["summary"].value == 15
    assert plays.value.tolist() == [0, 6, 9]
    partial = daily_statistics(apple_rows(values=(0, None, 9)), start, end)
    assert not partial["complete"] and partial["summary"].value == 9
    unique = daily_statistics(apple_rows("daily_unique_listeners", (0, 2, 3)), start, end)
    assert unique["summary"].value is None and unique["mean_daily"] == 5 / 3
    duplicate = pd.concat([plays, plays.iloc[[0]]], ignore_index=True)
    assert not daily_statistics(duplicate, start, end)["complete"]


def test_apple_spotify_matching_uses_only_complete_exact_utc_artist_dates():
    apple = apple_rows()
    spotify = pd.DataFrame({"date": ["2026-10-01", "2026-10-02"], "daily_streams": [10, 20]})
    result = matched_artist_activity(apple, spotify, date(2026, 10, 1), date(2026, 10, 3))
    assert result == {"start": date(2026, 10, 1), "end": date(2026, 10, 2), "apple_plays": 6,
                      "spotify_streams": 30, "days": 2}
    apple["dimensions_json"] = json.dumps({"entity_scope": "artist", "country": "US"})
    assert matched_artist_activity(apple, spotify, date(2026, 10, 1), date(2026, 10, 3)) is None
    apple["dimensions_json"] = '{"entity_scope":"artist"}'
    spotify.loc[1, "daily_streams"] = None
    assert matched_artist_activity(apple, spotify, date(2026, 10, 1), date(2026, 10, 3)) is None


def test_apple_ui_keeps_daily_listener_and_monthly_source_facts_separate():
    assert len(apple_snapshot_catalog(AppleRepo())) == 2
    script = '''from test_growth_detail_views import AppleRepo
from stats_app.apple_music_ui import render_apple_music
render_apple_music(AppleRepo())
'''
    app = AppTest.from_string(script).run()
    assert not app.exception and not app.error
    assert next(item for item in app.metric if item.label == "Apple plays").value == "15"
    next(item for item in app.selectbox if item.label == "Apple metric").set_value("daily_unique_listeners").run()
    assert not app.exception and not app.error
    assert next(item for item in app.metric if item.label == "Period-unique listeners").value == "Unavailable"
    next(item for item in app.selectbox if item.label == "Apple Music snapshot").set_value("local::apple-aggregate").run()
    assert not app.exception and not app.error
    assert next(item for item in app.radio if item.label == "Apple Music view").value == "Monthly source facts"
    assert next(item for item in app.metric if item.label == "Apple Music plays").value == "17"
