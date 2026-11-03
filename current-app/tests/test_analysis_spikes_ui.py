"""Exercise spike navigation, complete captions and exact filtered CSVs."""
from datetime import date
from hashlib import file_digest
import io
import json
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.testing.v1 import AppTest

from stats_app.analysis_content import CONTENT_PATH
from stats_app.analysis_repository import load_registered_analysis
from stats_app.config import load_settings

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


@pytest.fixture(scope="module")
def source():
    repo = load_registered_analysis(load_settings().data_dir)
    if repo is None or CONTENT_PATH not in repo.tables:
        pytest.skip("Private collected-content analysis unavailable")
    before = digest(repo.db_path)
    yield repo
    assert digest(repo.db_path) == before


@pytest.fixture
def dashboard(source, monkeypatch):
    downloads, links = {}, []
    original_download, original_link = st.download_button, st.link_button

    def capture_download(*args, **kwargs):
        if kwargs.get("key"):
            downloads[kwargs["key"]] = (kwargs.get("file_name", args[2] if len(args) > 2 else None),
                                      kwargs.get("data", args[1] if len(args) > 1 else None))
        return original_download(*args, **kwargs)

    def capture_link(label, url, **kwargs):
        links.append((label, url))
        return original_link(label, url, **kwargs)

    monkeypatch.setattr(st, "download_button", capture_download)
    monkeypatch.setattr(st, "link_button", capture_link)
    script = f"""
import streamlit as st
from stats_app.analysis_repository import AnalysisRepository
from stats_app.analysis_ui import render_cross_platform
from stats_app.analysis_spikes_ui import _choose_bar, _remember_week
repo = AnalysisRepository({str(source.db_path)!r})
repo.registered_key = {getattr(source, 'registered_key', '')!r}
# AppTest cannot click Plotly points. Deliver a selection to the real callback
# inside the app context, then retain the event to exercise later reruns.
if '_qa_pending_selection' in st.session_state:
    selected = st.session_state.pop('_qa_pending_selection')
    st.session_state['_qa_chart_event'] = {{'selection': {{'points': [{{'customdata': [selected]}}]}}}}
    _choose_bar('_qa_chart_event', ['2025-08-04', '2026-02-23'])
if '_qa_stale_picker' in st.session_state:
    _remember_week(*st.session_state.pop('_qa_stale_picker'))
render_cross_platform(repo)
"""
    app = AppTest.from_string(script, default_timeout=40).run()
    healthy(app)
    return app, downloads, links


def healthy(app):
    assert not app.exception, [item.value for item in app.exception]
    assert not app.error, [item.value for item in app.error]


def node(app, kind, label):
    return next(item for item in getattr(app, kind) if item.label == label)


def choose(app, kind, label, value):
    node(app, kind, label).set_value(value).run()
    healthy(app)


def filter_editor(app):
    editor = next(item for item in app.get("popover") if item.key == "spikes-filter-editor")
    assert editor.proto.popover.label == "Edit filters"
    return editor


def assert_filter_summary(app, expected):
    assert expected in [item.value for item in app.markdown]


def ranking_spec(app):
    return json.loads(app.get("plotly_chart")[0].proto.spec)


def spike_downloads(downloads):
    return {key: value for key, value in downloads.items() if key.startswith("spikes-")}


def assert_no_chart_size_button(app):
    assert not any(item.label == "Show fewer" or
                   (item.label.startswith("Show ") and item.label.endswith(" spikes"))
                   for item in app.button)


def csv(downloads, key):
    filename, raw = downloads[key]
    assert filename.endswith(".csv") and isinstance(raw, bytes)
    return pd.read_csv(io.BytesIO(raw), dtype={"post_id": str, "identity_key": str})


def assert_daily_source_matches(frame, source, start, end):
    raw = pd.read_csv(io.BytesIO(source.original_bytes("spotify/cleaned/artist_daily.csv")))
    raw.date = pd.to_datetime(raw.date)
    expected = raw.loc[raw.date.between(start, end), ["date", "daily_streams", "daily_listeners"]].reset_index(drop=True)
    actual = frame[["date", "daily_streams", "daily_listeners"]].copy()
    actual.date = pd.to_datetime(actual.date)
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False)


def test_default_top_stream_increase_and_downloads_match_source(dashboard, source):
    app, downloads, _ = dashboard
    assert app.tabs[0].label == "Spotify spikes"
    assert node(app, "selectbox", "Rank increases by").value == "streams"
    assert node(app, "selectbox", "Inspect Spotify week").value == "2025-08-04"
    assert_filter_summary(app, "Streams · All history · Aug 04, 2025 (+1,703)")
    assert [item.label for item in filter_editor(app).selectbox] == [
        "Rank increases by", "Spike period", "Inspect Spotify week"]
    assert node(app, "metric", "Weekly streams").value == "3,030"
    assert node(app, "metric", "Weekly streams").delta == "+1,703 (+128.3%)"
    assert "%" not in node(app, "metric", "Average daily listeners").delta
    assert "Aug 04–Aug 10, 2025 · vs Jul 28–Aug 03, 2025" in [item.value for item in app.caption]
    assert "Previous 1,327" in [item.value for item in app.caption]
    assert "Previous 47.6" in [item.value for item in app.caption]
    assert not any(item.value.startswith("Week of ") for item in app.subheader)
    assert not any(item.value.startswith("Selected measure change:") for item in app.caption)
    figure = ranking_spec(app)
    assert len(figure["data"][0]["customdata"]) == 5
    assert figure["layout"]["height"] == 215
    assert "5 largest weekly increases" in [item.value for item in app.caption]
    node(app, "button", "Show 12 spikes")
    rankings = csv(downloads, "spikes-ranking-csv")
    assert pd.Timestamp(rankings.iloc[0].week_start) == pd.Timestamp("2025-08-04")
    assert rankings.iloc[0].increase == 1703
    assert rankings.iloc[0].prior == 1327 and rankings.iloc[0].current == 3030
    assert rankings.increase.gt(0).all()
    assert rankings.increase.is_monotonic_decreasing
    daily = csv(downloads, "spikes-daily-csv")
    assert len(daily) == 14
    assert_daily_source_matches(daily, source, "2025-07-28", "2025-08-10")
    content = csv(downloads, "spikes-content-csv")
    assert len(content) == content.identity_key.nunique() == 11
    assert set(content.week_offset) == {-1, 0}
    assert "686726001063374" in set(content.post_id)
    assert any("not weekly unique people" in item.value for item in app.caption)
    assert any("cannot be inferred from the date alone" in item.value for item in app.info)


def test_listener_selection_full_caption_link_and_search_export_consistency(dashboard, source):
    app, downloads, links = dashboard
    choose(app, "selectbox", "Rank increases by", "mean_daily_listeners")
    choose(app, "selectbox", "Inspect Spotify week", "2026-02-23")
    assert_filter_summary(app, "Average daily listeners · All history · Feb 23, 2026 (+74.4)")
    assert node(app, "metric", "Average daily listeners").value == "200.1"
    assert node(app, "metric", "Average daily listeners").delta == "+74.4 (+59.2%)"
    assert node(app, "metric", "Weekly streams").delta == "+500"
    assert "Feb 23–Mar 01, 2026 · vs Feb 16–Feb 22, 2026" in [item.value for item in app.caption]
    assert "Previous 1,701" in [item.value for item in app.caption]
    assert "Previous 125.7" in [item.value for item in app.caption]
    rankings = csv(downloads, "spikes-ranking-csv")
    row = rankings.loc[pd.to_datetime(rankings.week_start).eq(pd.Timestamp("2026-02-23"))].iloc[0]
    assert row.increase == pytest.approx(74.42857142857143)
    assert row.current == pytest.approx(200.14285714285714)
    before_daily = csv(downloads, "spikes-daily-csv")
    assert_daily_source_matches(before_daily, source, "2026-02-16", "2026-03-01")
    assert before_daily.loc[pd.to_datetime(before_daily.date).eq(pd.Timestamp("2026-02-23")), "daily_streams"].item() == 603
    choose(app, "multiselect", "Content types", ["instagram_feed"])
    links.clear()
    choose(app, "text_input", "Search surrounding captions, IDs or links", "17897081085403947")
    content = csv(downloads, "spikes-content-csv")
    assert content.post_id.tolist() == ["17897081085403947"]
    assert content.exposure.tolist() == ["instagram_feed"]
    exact_caption = "THE DEVIL WEARS DOCS OFFICIAL MUSIC VIDEO OUT THIS FRIDAY 2/27/26"
    assert content.description.item() == exact_caption
    assert exact_caption in [item.value for item in app.text]
    assert ("Open original post", "https://www.instagram.com/reel/DVMEGA5Dcqj/") in links
    assert any("2026-02-25" in item.label and "Spike week" in item.label for item in app.expander)
    pd.testing.assert_frame_equal(csv(downloads, "spikes-ranking-csv"), rankings)
    pd.testing.assert_frame_equal(csv(downloads, "spikes-daily-csv"), before_daily)
    links.clear()
    choose(app, "text_input", "Search surrounding captions, IDs or links", "[no such caption or post]")
    assert csv(downloads, "spikes-content-csv").empty
    assert not links
    assert any("No retained posts or Stories match" in item.value for item in app.info)


def test_before_current_after_windows_pagination_and_type_scope_exports(dashboard, source):
    app, downloads, _ = dashboard
    choose(app, "selectbox", "Inspect Spotify week", "2026-02-23")
    baseline_ranking = csv(downloads, "spikes-ranking-csv")
    assert len(csv(downloads, "spikes-content-csv")) == 27
    choose(app, "selectbox", "Content window", "Spike week only")
    current = csv(downloads, "spikes-content-csv")
    assert len(current) == 20 and current.week_offset.eq(0).all()
    assert len(csv(downloads, "spikes-daily-csv")) == 7
    choose(app, "selectbox", "Content window", "Previous + spike + following week")
    all_content = csv(downloads, "spikes-content-csv")
    assert len(all_content) == all_content.identity_key.nunique() == 52
    assert all_content.groupby("week_offset").size().to_dict() == {-1: 7, 0: 20, 1: 25}
    expanded_daily = csv(downloads, "spikes-daily-csv")
    assert len(expanded_daily) == 21
    assert_daily_source_matches(expanded_daily, source, "2026-02-16", "2026-03-08")
    assert node(app, "selectbox", "Content page").value == 1
    choose(app, "selectbox", "Content page", 2)
    pd.testing.assert_frame_equal(csv(downloads, "spikes-content-csv"), all_content)
    choose(app, "multiselect", "Content types", ["facebook_posts"])
    facebook = csv(downloads, "spikes-content-csv")
    assert len(facebook) == 16 and facebook.platform.eq("Facebook").all()
    assert facebook.groupby("week_offset").size().to_dict() == {-1: 2, 0: 6, 1: 8}
    pd.testing.assert_frame_equal(csv(downloads, "spikes-daily-csv"), expanded_daily)
    pd.testing.assert_frame_equal(csv(downloads, "spikes-ranking-csv"), baseline_ranking)
    choose(app, "multiselect", "Content types", [])
    assert csv(downloads, "spikes-content-csv").empty
    assert node(app, "metric", "Weekly streams").value == "2,201"


def test_chart_callback_then_dropdown_and_period_do_not_restore_stale_week(dashboard):
    app, downloads, _ = dashboard
    compact_downloads = spike_downloads(downloads)
    node(app, "button", "Show 12 spikes").click().run()
    healthy(app)
    figure = ranking_spec(app)
    assert len(figure["data"][0]["customdata"]) == 12
    assert figure["layout"]["height"] == 425
    assert "2026-02-23" in [row[0] for row in figure["data"][0]["customdata"]]
    assert spike_downloads(downloads) == compact_downloads
    stale_week_picker = node(app, "selectbox", "Inspect Spotify week")
    stale_week_state = stale_week_picker._widget_state
    stale_week_key = stale_week_picker.key
    app.session_state['_qa_pending_selection'] = '2026-02-23'
    app.run()
    healthy(app)
    assert node(app, "selectbox", "Inspect Spotify week").value == "2026-02-23"
    assert_filter_summary(app, "Streams · All history · Feb 23, 2026 (+500)")
    selected_downloads = spike_downloads(downloads)
    node(app, "button", "Show fewer").click()
    # A closed popover cannot apply the server's changed week to its unmounted
    # browser widget. Replay that old wire value with the resize click; ordinary
    # AppTest.run() would use the latest server value and miss this regression.
    selected_week_id = node(app, "selectbox", "Inspect Spotify week").id
    resize_state = WidgetStates()
    resize_state.widgets.extend(
        item for item in app._tree.get_widget_states().widgets if item.id != selected_week_id)
    resize_state.widgets.append(stale_week_state)
    # An interrupted run can also retain the old picker callback itself.
    app.session_state['_qa_stale_picker'] = (stale_week_key, '2025-08-04')
    app._run(widget_state=resize_state)
    healthy(app)
    assert len(ranking_spec(app)["data"][0]["customdata"]) == 5
    assert node(app, "selectbox", "Inspect Spotify week").value == "2026-02-23"
    assert_filter_summary(app, "Streams · All history · Feb 23, 2026 (+500)")
    assert "Selected week is #8, outside the top 5." in [item.value for item in app.caption]
    assert node(app, "metric", "Weekly streams").value == "2,201"
    assert node(app, "metric", "Weekly streams").delta == "+500 (+29.4%)"
    assert node(app, "metric", "Average daily listeners").delta == "+74.4"
    assert spike_downloads(downloads) == selected_downloads
    node(app, "button", "Show 12 spikes")
    choose(app, "selectbox", "Inspect Spotify week", "2025-07-14")
    app.run()
    healthy(app)
    assert node(app, "selectbox", "Inspect Spotify week").value == "2025-07-14"
    assert node(app, "metric", "Weekly streams").value == "831"
    delta = node(app, "metric", "Weekly streams").delta.split(" (")[0]
    assert_filter_summary(app, f"Streams · All history · Jul 14, 2025 ({delta})")
    choose(app, "selectbox", "Spike period", "2024")
    selected = node(app, "selectbox", "Inspect Spotify week").value
    assert selected.startswith("2024-")
    assert pd.to_datetime(csv(downloads, "spikes-ranking-csv").week_start).dt.year.eq(2024).all()
    delta = node(app, "metric", "Weekly streams").delta.split(" (")[0]
    assert_filter_summary(app, f"Streams · 2024 · {pd.Timestamp(selected):%b %d, %Y} ({delta})")
    assert any("earlier selection is unavailable" in item.value for item in app.caption)


def test_no_complete_predecessor_clears_spike_exports(dashboard):
    app, downloads, _ = dashboard
    choose(app, "selectbox", "Spike period", "Custom")
    downloads.clear()
    choose(app, "date_input", "Spike comparison dates", (date(2024, 1, 1), date(2024, 1, 7)))
    assert any("No positive increases with a complete preceding week" in item.value for item in app.info)
    assert_filter_summary(app, "Streams · Jan 01, 2024 – Jan 07, 2024 · No rising weeks")
    assert_no_chart_size_button(app)
    filter_editor(app)
    assert not any(key.startswith('spikes-') for key in downloads)
    assert not any(item.label == "Weekly streams" for item in app.metric)
    choose(app, "date_input", "Spike comparison dates", (date(2026, 2, 23),))
    assert_filter_summary(app, "Streams · Custom dates incomplete · Choose both dates")
    assert_no_chart_size_button(app)
    assert any("Choose both the start and end date" in item.value for item in app.info)
    filter_editor(app)
    assert not any(key.startswith('spikes-') for key in downloads)
    assert not any(item.label == "Inspect Spotify week" for item in app.selectbox)
    choose(app, "date_input", "Spike comparison dates", (date(2026, 2, 23), date(2026, 3, 1)))
    assert_filter_summary(app, "Streams · Feb 23, 2026 – Mar 01, 2026 · Feb 23, 2026 (+500)")
    assert node(app, "selectbox", "Inspect Spotify week").value == "2026-02-23"
    assert node(app, "metric", "Weekly streams").value == "2,201"
    assert len(csv(downloads, "spikes-ranking-csv")) == 1
    assert len(csv(downloads, "spikes-content-csv")) == 27
    assert len(ranking_spec(app)["data"][0]["customdata"]) == 1
    assert ranking_spec(app)["layout"]["height"] == 150
    assert "1 largest weekly increase" in [item.value for item in app.caption]
    assert_no_chart_size_button(app)
    filter_editor(app)


def test_no_source_is_explicit_without_rank_controls_or_downloads():
    script = """
import pandas as pd
from stats_app.analysis_spikes_ui import render_spikes
class MissingSource:
    tables = []
render_spikes(MissingSource(), {'weekly': pd.DataFrame()})
"""
    app = AppTest.from_string(script, default_timeout=15).run()
    healthy(app)
    assert any("need consecutive complete weeks" in item.value for item in app.info)
    assert not app.selectbox
    assert not app.get("download_button")
    assert_no_chart_size_button(app)


def test_missing_following_days_and_unavailable_values_remain_gaps(monkeypatch):
    from stats_app import analysis_spikes_ui

    downloads, figures = {}, {}
    original_download, original_chart = st.download_button, analysis_spikes_ui.chart

    def capture_download(*args, **kwargs):
        downloads[kwargs["key"]] = (args[2], args[1])
        return original_download(*args, **kwargs)

    def capture_chart(figure, key):
        figures[key] = figure
        return original_chart(figure, key)

    monkeypatch.setattr(st, "download_button", capture_download)
    monkeypatch.setattr(analysis_spikes_ui, "chart", capture_chart)
    script = """
import pandas as pd
import streamlit as st
from stats_app.analysis_correlation import weekly_spotify
from stats_app.analysis_spikes_ui import render_spikes
daily = pd.DataFrame({
    'date': pd.date_range('2024-01-01', periods=21),
    'daily_streams': [0] * 7 + [20] * 7 + [30] * 7,
    'daily_listeners': [1] * 7 + [2] * 7 + [3] * 7,
    'daily_streams_status': 'observed',
    'daily_listeners_status': 'observed',
})
daily = daily.loc[daily.date.ne('2024-01-16')].copy()
daily.loc[daily.date.eq('2024-01-17'), ['daily_streams', 'daily_streams_status']] = [999, 'unavailable']
class GapSource:
    tables = ['spotify/cleaned/artist_daily.csv']
    def table(self, name, raw=False):
        return daily.copy()
st.session_state['selection:spikes:window'] = 'Previous + spike + following week'
render_spikes(GapSource(), {'weekly': weekly_spotify(daily), 'identities': pd.DataFrame()})
"""
    app = AppTest.from_string(script, default_timeout=15).run()
    healthy(app)
    assert node(app, "selectbox", "Inspect Spotify week").value == "2024-01-08"
    assert node(app, "metric", "Weekly streams").value == "140"
    assert node(app, "metric", "Weekly streams").delta == "+140 (% unavailable)"
    assert "Previous 0" in [item.value for item in app.caption]
    daily = csv(downloads, "spikes-daily-csv").set_index("date")
    assert len(daily) == 21
    assert daily.loc["2024-01-16", ["daily_streams", "daily_listeners"]].isna().all()
    assert pd.isna(daily.loc["2024-01-17", "daily_streams"])
    assert daily.loc["2024-01-17", "daily_streams_status"] == "unavailable"
    assert daily.loc["2024-01-17", "daily_listeners"] == 3
    figure = figures["spikes-daily"]
    assert all(trace.connectgaps is False for trace in figure.data)
    assert all(len(trace.x) == 21 for trace in figure.data)
    assert pd.isna(figure.data[0].y[15]) and pd.isna(figure.data[0].y[16])
    assert pd.isna(figure.data[1].y[15]) and figure.data[1].y[16] == 3
