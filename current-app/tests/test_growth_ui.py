"""The diagnostic controls, findings and exports share one displayed scope."""
from datetime import date
from hashlib import sha256
import io

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from stats_app.analysis_repository import load_registered_analysis
from stats_app.config import load_settings


@pytest.fixture(scope="module")
def source():
    repo = load_registered_analysis(load_settings().data_dir)
    if repo is None:
        pytest.skip("Private immutable source unavailable")
    before = sha256(repo.db_path.read_bytes()).hexdigest()
    yield repo
    assert sha256(repo.db_path.read_bytes()).hexdigest() == before


def test_diagnostics_custom_dates_and_recording_filter_update_export_and_evidence(source, monkeypatch):
    downloads = {}
    original = st.download_button
    def capture(*args, **kwargs):
        key = kwargs.get("key")
        if key:
            downloads[key] = kwargs.get("data", args[1] if len(args)>1 else None)
        return original(*args, **kwargs)
    monkeypatch.setattr(st,"download_button",capture)
    code = f"""
from stats_app.analysis_repository import AnalysisRepository
from stats_app.growth_ui import render_growth_diagnostics
repo=AnalysisRepository({str(source.db_path)!r})
repo.registered_key={source.registered_key!r}
render_growth_diagnostics(repo)
"""
    app = AppTest.from_string(code,default_timeout=60).run()
    assert not app.exception and not app.error
    assert next(m for m in app.metric if m.label=="Selected artist streams").value == "13,838"
    first = pd.read_csv(io.BytesIO(downloads["growth_recordings_csv"]))
    assert first.current.sum()==13838 and first.previous.sum()==20153
    next(s for s in app.selectbox if s.label=="Diagnostic comparison").set_value("Custom").run()
    assert not app.exception and not app.error
    dates = (date(2026,10,1),date(2026,10,20))
    next(s for s in app.date_input if s.label=="Diagnostic UTC dates").set_value(dates).run()
    assert not app.exception and not app.error
    song = first.song_id.iloc[0]
    next(s for s in app.multiselect if s.label=="Diagnostic recordings · empty means all").set_value([song]).run()
    assert not app.exception and not app.error
    shown = pd.read_csv(io.BytesIO(downloads["growth_recordings_csv"]))
    assert shown.song_id.tolist()==[song]
    native = source.table("spotify/cleaned/track_daily_long.csv")
    expected = native.loc[native.song_id.eq(song) & native.metric.eq("streams") & native.date.between("2026-10-01","2026-10-20"),"value"].sum()
    assert shown.current.iloc[0]==expected
    import json
    receipt=json.loads(downloads["growth_findings_json"])
    assert receipt["period"]["start"]=="2026-10-01"
    assert receipt["selected_song_ids"]==[song]
    assert all(f["source_version"]==source.registered_key and f["evidence"] for f in receipt["findings"])
    assert all(f["period"]["end"]=="2026-10-20" for f in receipt["findings"])
    # Details are selected, so hidden chart sections do not execute/render.
    assert not any(s.label=="Release-age comparison recordings · empty means all" for s in app.multiselect)
    for section, export_key in [("Playback routes","growth_sources_csv"),("Release age","growth_release_ages_csv"),("Nearby social","growth_nearby_csv")]:
        next(r for r in app.radio if r.label=="Diagnostic detail").set_value(section).run()
        assert not app.exception and not app.error, section
        if section != "Nearby social":
            assert export_key in downloads
    app.session_state["growth-findings:activity"] = True
    app.run()
    assert not app.exception and not app.error
    assert "growth-findings:source:activity0" in downloads
    assert downloads["growth-findings:source:activity0"]==source.original_bytes("spotify/cleaned/artist_daily.csv")


def test_overview_three_primary_metrics_and_content_shortcut(source):
    code=f"""
import streamlit as st
from stats_app.analysis_repository import AnalysisRepository
from stats_app.analysis_ui import render_overview
repo=AnalysisRepository({str(source.db_path)!r})
repo.registered_key={source.registered_key!r}
render_overview(repo)
"""
    app=AppTest.from_string(code,default_timeout=60).run()
    assert not app.exception and not app.error
    assert [metric.label for metric in app.metric]==["Streams","Period-unique listeners","Net Spotify followers"]
    assert any("Saves:" in item.value and "Playlist additions:" in item.value for item in app.markdown)
    next(button for button in app.button if button.label=="Review social content").click().run()
    assert app.session_state["selection:analysis-social-view"]=="Collected posts & Stories"


def test_derived_report_cache_is_bound_to_inputs_and_does_not_repeat_source_reads(source, monkeypatch):
    from stats_app.growth_ui import report_for, _cached_report
    _cached_report.clear()
    reads=[]
    original=source.table
    def count(path, **kwargs):
        reads.append(path)
        return original(path,**kwargs)
    monkeypatch.setattr(source,"table",count)
    first=report_for(source,"2026-07-20","2026-10-18",include_details=False)
    count_first=len(reads)
    second=report_for(source,"2026-07-20","2026-10-18",include_details=False)
    assert count_first>0 and len(reads)==count_first
    assert first["fingerprint"]==second["fingerprint"]
    different=report_for(source,"2026-09-23","2026-10-20",include_details=False)
    assert len(reads)>count_first and different["fingerprint"]!=first["fingerprint"]


def test_saved_diagnosis_is_a_fixed_manifest_verified_view():
    code="from stats_app.growth_ui import render_saved_diagnosis\nrender_saved_diagnosis()"
    app=AppTest.from_string(code,default_timeout=30).run()
    assert not app.exception and not app.error
    assert not app.selectbox and not app.date_input
    assert next(m for m in app.metric if m.label=="Historical selected streams").value=="13,838"
    assert any("meta-story-backfill-20261024" in c.value for c in app.caption)


@pytest.mark.parametrize("current_end,prior_end,expected", [
    ("2024-12-30","2023-12-31","Preceding equal interval"),
    ("2024-10-20","2023-10-20","Matching prior-year dates"),
])
def test_finding_shortcut_keeps_comparison_calendar_semantics(current_end,prior_end,expected):
    from stats_app.growth_analysis import paired_periods
    period=paired_periods("2024-01-01",current_end,"2023-01-01",prior_end)
    finding=dict(id="activity",title="Fixture activity",observed_statement="Synthetic calendar regression",period=period,
                 source_version="synthetic",source_refs=[],limitation="Fixture only",method_version="test",evidence=[],
                 interpretation="Synthetic test",input_fingerprint="test")
    code="from stats_app.growth_ui import render_findings\nrender_findings("+repr([finding])+",compact=True,key='shortcut')"
    app=AppTest.from_string(code,default_timeout=15).run()
    assert not app.exception
    app.button("shortcut:jump:activity").click().run()
    assert not app.exception
    assert app.session_state["selection:growth:comparison"]==expected
    assert app.session_state["selection:growth:dates"]==(date(2024,1,1),date.fromisoformat(current_end))
