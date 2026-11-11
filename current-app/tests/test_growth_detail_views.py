"""Read-only detail identity and Apple source-grain UI contracts."""
from datetime import date
import json

import pandas as pd
import pytest
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


def spotify_rows(values=(10, 20, 30)):
    return pd.DataFrame({
        "date": [f"2026-10-{number:02d}" for number in range(1, len(values) + 1)],
        "daily_streams": pd.Series(values, dtype=float),
        "artist_id": "spotify-artist",
        "snapshot_class": "original_baseline",
        "reporting_timezone": "UTC",
        "value_status": "observed",
        "partial_day": pd.Series([False] * len(values), dtype="boolean"),
    })


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
    spotify = spotify_rows((10, 20))
    result = matched_artist_activity(apple, spotify, date(2026, 10, 1), date(2026, 10, 3))
    assert result == {"start": date(2026, 10, 1), "end": date(2026, 10, 2), "apple_plays": 6,
                      "spotify_streams": 30, "days": 2}
    apple["dimensions_json"] = json.dumps({"entity_scope": "artist", "country": "US"})
    assert matched_artist_activity(apple, spotify, date(2026, 10, 1), date(2026, 10, 3)) is None
    apple["dimensions_json"] = '{"entity_scope":"artist"}'
    spotify.loc[1, "daily_streams"] = None
    assert matched_artist_activity(apple, spotify, date(2026, 10, 1), date(2026, 10, 3)) is None


@pytest.mark.parametrize("column,value", [
    ("daily_streams", None),
    ("daily_streams", float("inf")),
    ("daily_streams", float("-inf")),
    ("daily_streams", -1),
    ("value_status", "unavailable"),
    ("value_status", "suppressed"),
    ("daily_streams_status", "unavailable"),
    ("partial_day", True),
    ("partial_day", None),
    ("reporting_timezone", "America/Los_Angeles"),
    ("reporting_timezone", None),
    ("artist_id", "another-artist"),
    ("artist_id", ""),
    ("snapshot_class", "later_capture"),
    ("snapshot_class", None),
])
def test_matched_activity_withholds_invalid_or_incompatible_spotify_evidence(column, value):
    spotify = spotify_rows()
    if column not in spotify:
        spotify[column] = "observed"
    spotify.loc[2, column] = value
    original = spotify.copy(deep=True)
    assert matched_artist_activity(apple_rows(), spotify, date(2026, 10, 1), date(2026, 10, 3)) is None
    pd.testing.assert_frame_equal(spotify, original)


@pytest.mark.parametrize("column", ["artist_id", "snapshot_class", "reporting_timezone"])
def test_matched_activity_requires_identified_spotify_scope(column):
    spotify = spotify_rows().drop(columns=column)
    assert matched_artist_activity(apple_rows(), spotify, date(2026, 10, 1), date(2026, 10, 3)) is None


def test_matched_activity_keeps_genuine_zero_but_withholds_missing_or_duplicate_dates():
    spotify = spotify_rows((0, 0, 0))
    spotify["value_status"] = "observed_zero"
    result = matched_artist_activity(apple_rows(), spotify, date(2026, 10, 1), date(2026, 10, 3))
    assert result["spotify_streams"] == 0 and result["days"] == 3
    assert matched_artist_activity(apple_rows(), spotify.drop(index=1), date(2026, 10, 1), date(2026, 10, 3)) is None
    duplicate = pd.concat([spotify, spotify.iloc[[0]]], ignore_index=True)
    assert matched_artist_activity(apple_rows(), duplicate, date(2026, 10, 1), date(2026, 10, 3)) is None


@pytest.mark.parametrize("partial", [False, True])
def test_apple_ui_only_labels_valid_spotify_overlap_as_complete(partial):
    script = f'''from types import SimpleNamespace
from test_growth_detail_views import AppleRepo, spotify_rows
from stats_app.apple_music_ui import render_apple_music
spotify = spotify_rows()
spotify.loc[2, "partial_day"] = {partial!r}
analysis = SimpleNamespace(table=lambda path: spotify)
render_apple_music(AppleRepo(), analysis)
'''
    app = AppTest.from_string(script).run()
    assert not app.exception and not app.error
    matched = [item for item in app.metric if item.label == "Spotify streams · matched dates"]
    assert next(item for item in app.metric if item.label == "Apple plays").value == "15"
    if partial:
        assert not matched
        assert any("complete matching UTC artist window on Spotify is unavailable" in item.value for item in app.caption)
        assert not any("3 complete UTC days" in item.value for item in app.caption)
    else:
        assert len(matched) == 1 and matched[0].value == "60"
        assert any("3 complete UTC days" in item.value for item in app.caption)


@pytest.mark.parametrize("error", [
    pytest.param("No parsed domain CSV at spotify/cleaned/artist_daily.csv", id="missing-table"),
    pytest.param("Analysis source SHA-256 verification failed.", id="failed-hash"),
])
def test_apple_ui_preserves_original_sources_when_spotify_table_is_unreadable(error):
    script = f'''from types import SimpleNamespace
from test_growth_detail_views import AppleRepo
from stats_app.apple_music_ui import render_apple_music
from stats_app.storage import StorageError

class ReadableAppleRepo(AppleRepo):
    def original_source(self, digest):
        assert digest == "test-source"
        return b"date,plays\\n2026-10-01,0\\n"

def unreadable_spotify_table(path):
    assert path == "spotify/cleaned/artist_daily.csv"
    raise StorageError({error!r})

render_apple_music(ReadableAppleRepo(), SimpleNamespace(table=unreadable_spotify_table))
'''
    app = AppTest.from_string(script)
    app.session_state["apple:evidence"] = True
    app.run()
    assert not app.exception and not app.error
    assert any("daily Spotify data could not be read" in item.value for item in app.caption)
    assert all(item.label != "Spotify streams · matched dates" for item in app.metric)
    assert next(item for item in app.metric if item.label == "Apple plays").value == "15"
    assert {item.label for item in app.get("download_button")} >= {
        "Download filtered records · CSV", "Download unchanged Apple source",
    }


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
