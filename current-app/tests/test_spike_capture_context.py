"""Story backfill enriches spike context without changing Spotify or cadence."""
from copy import deepcopy

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from stats_app.analysis_content import CONTENT_PATH, METRICS, load_content_observations, publication_inventory
from stats_app.analysis_correlation import build_weekly_activity
from stats_app.analysis_spikes import publication_capture_context, publications_around_week, rank_spotify_increases
from test_content_supplement_loading import MemoryRepo, STORY_BACKFILL, bridge, observation


def backfilled_source(include_backfill=True):
    old = dict(observation("recovered"), description="", publication_date="2026-02-20",
               published_local="2026-02-20T14:00:00", views="", views_status="not_supplied")
    edge_first = dict(observation("first"), publication_date="2026-02-16", published_local="2026-02-16T14:00:00")
    edge_last = dict(observation("last"), publication_date="2026-03-01", published_local="2026-03-01T14:00:00")
    daily = [dict(date=day.strftime("%Y-%m-%d"), reporting_timezone="UTC", daily_streams=str(1 if i < 7 else 2),
                  daily_listeners="1", daily_saves="0", daily_playlist_adds="0", followers_stock="10")
             for i, day in enumerate(pd.date_range("2026-02-16", periods=14))]
    tables = {CONTENT_PATH: [old, edge_first, edge_last], "spotify/cleaned/artist_daily.csv": daily}
    if include_backfill:
        detail = dict(old, selected_account_id="mbs", account_id_type="meta_business_suite_asset",
                      description="Recovered full Story caption", views="500000", views_status="observed",
                      link_clicks="0", link_clicks_status="observed_zero", reach="", reach_status="unavailable",
                      publication_date="", published_local="Fri Feb 20, 2:00pm", publication_timezone="",
                      snapshot_timestamp="2026-10-25T12:00:00+00:00")
        tables[STORY_BACKFILL + "content_snapshots.csv"] = [detail, deepcopy(detail)]
        tables[STORY_BACKFILL + "identity_bridges.csv"] = [bridge()]
    return MemoryRepo(tables)


def test_backfill_reaches_spike_caption_and_metric_context_without_inflating_activity():
    before = build_weekly_activity(backfilled_source(False))
    after = build_weekly_activity(backfilled_source())
    pd.testing.assert_frame_equal(before["weekly"], after["weekly"])
    pd.testing.assert_frame_equal(rank_spotify_increases(before["weekly"]), rank_spotify_increases(after["weekly"]))
    previous_items = publications_around_week(before["identities"], "2026-02-23")
    items = publications_around_week(after["identities"], "2026-02-23")
    assert len(items) == items.identity_key.nunique() == len(previous_items) == 3
    recovered = items.loc[items.post_id.eq("recovered")].iloc[0]
    assert not previous_items.loc[previous_items.post_id.eq("recovered"), "caption_available"].item()
    assert recovered.caption_available and recovered.description == "Recovered full Story caption"
    assert recovered.dates == "2026-02-20"
    assert after["observations"].loc[after["observations"].source_table.eq(STORY_BACKFILL + "content_snapshots.csv"), "publication_date"].eq("").all()
    context = publication_capture_context(after["observations"], items)
    context = context.loc[context.post_id.eq("recovered")].set_index("metric")
    assert context.loc["views", "value"] == 500000
    assert context.loc["link_clicks", "value"] == 0 and context.loc["link_clicks", "value_status"] == "observed_zero"
    assert pd.isna(context.loc["reach", "value"]) and context.loc["reach", "value_status"] == "unavailable"
    assert context.snapshot_timestamp.eq("2026-10-25T12:00:00+00:00").all()
    assert context.source_table.eq(STORY_BACKFILL + "content_snapshots.csv").all()
    assert after["weekly"].streams.tolist() == [7, 14]


def test_unresolved_capture_values_keep_their_status_and_scope():
    rows = [observation("one"), dict(observation("one"), views="11"),
            dict(observation("one"), snapshot_timestamp="", views="99"),
            dict(observation("one"), views="90", metric_platform_scope="Facebook and Instagram combined")]
    observations = load_content_observations(MemoryRepo({CONTENT_PATH: rows}))
    context = publication_capture_context(observations, pd.DataFrame({"identity_key": observations.identity_key.unique()}))
    views = context.loc[context.metric.eq("views")]
    assert sorted(views.value) == [10, 11, 90, 99]
    assert set(views.selection_status) == {"same_time_conflict", "capture_time_unknown", "latest_compatible_capture"}
    assert views.loc[views.value.eq(90), "metric_platform_scope"].item() == "Facebook and Instagram combined"


def test_new_same_week_date_disagreement_is_retained_and_excluded_from_exact_day_cadence():
    before = build_weekly_activity(backfilled_source(False))
    source = backfilled_source()
    source.frames[STORY_BACKFILL + "content_snapshots.csv"]["publication_date"] = "2026-02-21"
    source.frames[STORY_BACKFILL + "content_snapshots.csv"]["published_local"] = "Feb 21, 2026"
    after = build_weekly_activity(source)
    pd.testing.assert_frame_equal(before["weekly"], after["weekly"])
    item = publications_around_week(after["identities"], "2026-02-23").set_index("post_id").loc["recovered"]
    assert item.dates == "2026-02-20;2026-02-21" and item.date_conflict
    assert item.timing_status == "week_certain_date_conflict" and item.week_offset == -1
    assert "Retained publication dates disagree" in item.timing_note
    assert publication_inventory(before["observations"]).retained_publications.sum() == 3
    assert publication_inventory(after["observations"]).retained_publications.sum() == 2
    detail = after["observations"].loc[after["observations"].source_table.eq(STORY_BACKFILL + "content_snapshots.csv")]
    assert detail.publication_date.eq("2026-02-21").all() and detail.publication_timezone.eq("").all()
    context = publication_capture_context(after["observations"], pd.DataFrame([item]))
    assert context.loc[context.post_id.eq("recovered"), "publication_date"].eq("2026-02-21").all()
    assert context.loc[context.post_id.eq("recovered"), "published_local"].eq("Feb 21, 2026").all()
    assert context.loc[context.post_id.eq("recovered"), "publication_timezone"].eq("").all()


def test_spike_expander_shows_caption_and_separate_capture_table():
    app = AppTest.from_string('''from test_spike_capture_context import backfilled_source
from stats_app.analysis_correlation import build_weekly_activity
from stats_app.analysis_spikes_ui import render_spikes
repo = backfilled_source()
render_spikes(repo, build_weekly_activity(repo))
''', default_timeout=30).run()
    assert not app.exception and not app.error
    assert "Recovered full Story caption" in [item.value for item in app.text]
    frames = [item.value for item in app.dataframe if "metric" in item.value]
    assert any(frame.loc[frame.metric.eq("views"), "value"].eq(500000).any() for frame in frames)
    assert all(list(frame.columns[:5]) == ["metric", "value", "value_status", "snapshot_timestamp", "caption_evidence"] for frame in frames)
    assert any(frame.caption_evidence.eq("Retained source text").any() for frame in frames)
    assert any("not daily activity or attributed Spotify streams" in item.value for item in app.caption)
    assert any(item.label == "Download surrounding content metric captures · CSV" for item in app.get("download_button"))


@pytest.mark.parametrize("raw,description,expected", [
    ('{"description_status":"native_no_text"}', "", "native_no_text"),
    ('{"description_status":"native_text_present"}', "Visible caption", "native_text_present"),
    ('{"description_status":"native_text_present","description":"Untrusted embedded text"}', "", "native_text_reported_but_not_retained"),
    ('{"description_status":"native_no_text"}', "Contradictory retained caption", "conflicting_native_caption_evidence"),
    ('{"description":"Untrusted embedded text"}', "", "not_collected_or_unavailable"),
    ('{"description_status":{"native_no_text":true}}', "", "not_collected_or_unavailable"),
    ('["native_no_text"]', "", "not_collected_or_unavailable"),
    ('not valid JSON; no executable input', "", "not_collected_or_unavailable"),
    ('', "Retained source caption", "retained_source_text"),
])
def test_capture_caption_evidence_uses_only_explicit_status_and_canonical_text(raw, description, expected):
    source = MemoryRepo({CONTENT_PATH: [observation("one", description=description, native_record_json=raw)]})
    observations = load_content_observations(source)
    items = pd.DataFrame({"identity_key": observations.identity_key.unique()})
    context = publication_capture_context(observations, items)
    assert context.caption_evidence.eq(expected).all()
    assert observations.description.tolist() == [description]
    assert not any("Untrusted embedded text" in value for value in observations.description)


def test_audit_week_preselection_keeps_production_drilldown_rows():
    from scripts.audit_story_backfill_comparison import nearby_publications
    identities = build_weekly_activity(backfilled_source())["identities"]
    distant = identities.iloc[[0]].copy()
    distant["identity_key"], distant["dates"], distant["week"] = "distant", "2024-01-02", "2024-01-01"
    disputed = distant.copy()
    disputed["identity_key"], disputed["dates"], disputed["week"] = "disputed", "2026-02-22;2026-02-23", ""
    identities = pd.concat([identities, distant, disputed], ignore_index=True)
    expected = publications_around_week(identities, "2026-02-23")
    actual = nearby_publications(identities, "2026-02-23")
    pd.testing.assert_frame_equal(actual, expected)


def malformed_then_recovered_source():
    source = backfilled_source()
    old = source.frames[CONTENT_PATH].post_id.eq("recovered")
    source.frames[CONTENT_PATH].loc[old, "measurement_type"] = "content_identity_only"
    for metric in METRICS:
        source.frames[CONTENT_PATH].loc[old, metric] = ""
        source.frames[CONTENT_PATH].loc[old, metric + "_status"] = "unavailable_malformed_source_row"
    source.frames[STORY_BACKFILL + "content_snapshots.csv"]["views"] = "114"
    unknown = source.frames[STORY_BACKFILL + "content_snapshots.csv"].iloc[0].copy()
    unknown["snapshot_timestamp"], unknown["views"] = "", "42"
    source.frames[STORY_BACKFILL + "content_snapshots.csv"] = pd.concat(
        [source.frames[STORY_BACKFILL + "content_snapshots.csv"], unknown.to_frame().T], ignore_index=True)
    return source


def test_spike_table_shows_new_capture_first_without_dropping_old_unavailable_rows_or_sorting_csv(monkeypatch):
    import streamlit as st
    downloads = {}
    original_download = st.download_button

    def capture_download(label, data, file_name, mime, **kwargs):
        downloads[kwargs.get("key")] = data
        return original_download(label, data, file_name, mime, **kwargs)

    monkeypatch.setattr(st, "download_button", capture_download)
    app = AppTest.from_string('''from test_spike_capture_context import malformed_then_recovered_source
from stats_app.analysis_correlation import build_weekly_activity
from stats_app.analysis_spikes_ui import render_spikes
repo = malformed_then_recovered_source()
render_spikes(repo, build_weekly_activity(repo))
''', default_timeout=30).run()
    assert not app.exception and not app.error
    frame = next(item.value for item in app.dataframe if "metric" in item.value
                 and item.value.loc[item.value.metric.eq("views"), "value"].eq(114).any()).reset_index(drop=True)
    assert frame.iloc[0].metric == "views" and frame.iloc[0].value == 114
    old_rows = frame.loc[frame.value_status.eq("unavailable_malformed_source_row")]
    assert len(old_rows) == len(METRICS) and old_rows.value.isna().all()
    assert old_rows.metric.tolist() == METRICS
    known_new = frame.loc[frame.snapshot_timestamp.eq("2026-10-25T12:00:00+00:00")]
    unknown_rows = frame.loc[frame.snapshot_timestamp.eq("")]
    assert known_new.index.max() < old_rows.index.min() < old_rows.index.max() < unknown_rows.index.min()
    assert frame.iloc[-1].snapshot_timestamp == ""
    assert known_new.metric.tolist() == ["views", "reach", "link_clicks"]
    import io
    raw = pd.read_csv(io.BytesIO(downloads["spikes-content-captures-csv"]), dtype={"post_id": str})
    exported = raw.loc[raw.post_id.eq("recovered")]
    assert exported.iloc[0].value_status == "unavailable_malformed_source_row"
    assert exported.loc[exported.value_status.eq("unavailable_malformed_source_row"), "metric"].tolist() == METRICS
    assert exported.loc[exported.metric.eq("views"), "value"].eq(114).any()
