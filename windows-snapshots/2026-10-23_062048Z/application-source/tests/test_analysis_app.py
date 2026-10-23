"""Exercise real analytical page bindings using a copied immutable snapshot."""
import json
from pathlib import Path
import shutil
import pytest
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"data/reconciliation/staged_analysis/analysis.sqlite3"

@pytest.fixture(scope="module")
def copied(tmp_path_factory):
    if not SOURCE.exists(): pytest.skip("Private analysis snapshot unavailable")
    root=tmp_path_factory.mktemp("analysis-app")
    dest=root/"analysis/cleaned";dest.mkdir(parents=True)
    shutil.copy2(SOURCE,dest/"analysis.sqlite3")
    (root/"archive_registry.json").write_text(json.dumps({"archives":[],"analysis_package":{
        "database":"analysis/cleaned/analysis.sqlite3","evidence_root":"analysis/cleaned","label":"Test copy"}}))
    return root

@pytest.fixture
def app(copied,monkeypatch):
    monkeypatch.setenv("STATS_DATA_DIR",str(copied));monkeypatch.setenv("STATS_MODE","local")
    at=AppTest.from_file(str(ROOT/"app.py"),default_timeout=30).run()
    assert not at.exception and not at.error
    return at

def choose(at,label,value,kind="selectbox"):
    node=next(item for item in getattr(at,kind) if item.label==label)
    node.set_value(value).run()
    assert not at.exception and not at.error

def test_overview_matching_periods_and_sources(app):
    assert app.metric[0].value=="4,246"
    assert any(item.value=="1,062" for item in app.metric)
    assert len(app.get("plotly_chart"))==1
    choose(app,"Comparison","Year to date, matching prior year")
    assert app.metric[0].value=="58,175"
    assert any("22,825" in item.value for item in app.caption)
    choose(app,"Comparison","Latest 90 days")
    assert app.metric[0].value=="13,775"

def test_spotify_filters_catalog_and_unknown_unique(app):
    choose(app,"Explore","Spotify","radio")
    choose(app,"Artist metric","Daily unique listeners")
    assert any(item.value=="1,062" for item in app.metric)
    choose(app,"Spotify view","Catalog comparison","radio")
    data=app.dataframe[0].value
    assert len(data)==14 and data.current.sum()==4246
    song=data.iloc[0].song_id
    choose(app,"Recordings · empty means all",[song],"multiselect")
    assert len(app.dataframe[0].value)==1
    choose(app,"Recordings · empty means all",[],"multiselect")
    assert len(app.dataframe[0].value)==14
    choose(app,"Spotify view","Release age","radio")
    assert len(app.get("plotly_chart"))==1
    choose(app,"Spotify view","Audience & sources","radio")
    assert any("overlap" in item.value for item in app.warning)
    choose(app,"Audience/source view","Age distribution")
    assert any("1,063" in item.value for item in app.warning)

def test_cross_platform_keeps_all_tests_and_intervals(app):
    choose(app,"Explore","Cross-platform","radio")
    assert [item.value for item in app.metric]==["12","6","0.385"]
    assert len(app.dataframe[0].value)==12
    assert len(app.get("plotly_chart"))==2
    choose(app,"Inspect planned comparison","instagram_link_clicks_lag0")
    assert any("undefined" in item.value for item in app.info)
    assert len(app.dataframe[0].value)==12

def test_quality_and_preserved_import_workflow(app):
    choose(app,"Explore","Data quality","radio")
    assert any("183" in item.value for item in app.markdown)
    assert any(len(item.value)==53 for item in app.dataframe)
    choose(app,"Inspect quality or source table","social/excluded_records.csv")
    assert any(len(item.value)==183 for item in app.dataframe)
    choose(app,"Explore","Import data","radio")
    assert any(item.label=="Load preserved native Spotify archive" for item in app.button)
    choose(app,"Explore","Snapshot explorer","radio")
    assert any("No observations" in item.value for item in app.info)
