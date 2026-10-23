"""Decision outputs reconcile to real retained evidence; fixtures stay isolated."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from stats_app.analysis_repository import AnalysisRepository, load_registered_analysis
from stats_app.config import load_settings
from stats_app.decision_report import build_report, safe_ratio, social_series, coverage_and_social, markdown_report

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def real():
    try:
        repo=load_registered_analysis(load_settings().data_dir)
    except (OSError,ValueError):
        repo=None
    if repo is None:
        path=ROOT/'data/reconciliation/staged_analysis/analysis.sqlite3'
        if not path.is_file(): pytest.skip('Private source package unavailable')
        repo=AnalysisRepository(path)
    return repo


@pytest.fixture(scope="module")
def report(real):
    before=hashlib.sha256(real.db_path.read_bytes()).hexdigest()
    result=build_report(real)
    assert hashlib.sha256(real.db_path.read_bytes()).hexdigest()==before
    return result


@pytest.mark.parametrize('a,b',[(None,1),(2,None),(1,0),(1,-1),(float('inf'),2),(2,float('nan'))])
def test_invalid_ratios_explicit(a,b):
    assert safe_ratio(a,b)['value'] is None
    assert safe_ratio(a,b)['status']=='unavailable'


def test_real_counts_denominators_reconciliation(report):
    assert report['growth28']['current']==4246
    assert report['growth28']['previous']==4011
    assert report['period_unique_listeners']['current_value']==1062
    assert report['listening_intensity']['value']==pytest.approx(4246/1062)
    assert report['follower_change']['net_change']==28
    assert report['reconciliation']==dict(status='passed',artist_streams=4246,catalog_streams=4246,difference=0)
    assert len(report['songs'])==14
    assert sum(row['current'] for row in report['songs'])==4246
    assert report['cross_platform']['planned']==12
    assert report['cross_platform']['adjusted_significant']==0
    assert report['weekly'][-1]['total'] is None
    assert len(report['experiments'])==3
    json.dumps(report,allow_nan=False)
    assert 'unverified' in markdown_report(report)


def test_repaired_follows_is_selected_once_without_mutating_original(real):
    repair='social/meta_collection/follows_daily_resolved.csv'
    if repair not in real.tables: pytest.skip('Version predates follows repair')
    before=real.table('social/account_daily.csv')
    chosen=social_series(real)
    inherited=chosen[0][1]
    assert not ((inherited.platform_selected=='Instagram')&(inherited.metric=='follows')).any()
    repaired=chosen[1][1]
    assert len(repaired)==293 and not repaired.date.duplicated().any()
    _, comparisons=coverage_and_social(real)
    follows=[r for r in comparisons if r['platform_selected']=='Instagram' and r['metric']=='follows']
    assert len(follows)==1
    assert follows[0]['current']['total']==15 and follows[0]['previous']['total']==15
    assert len(comparisons)==12
    assert all(row['current']['end']=='2026-10-20' for row in comparisons)
    pd.testing.assert_frame_equal(before,real.table('social/account_daily.csv'))


def test_missing_content_is_not_zero_and_no_equal_age_claim(report):
    for row in report['content_distributions']:
        assert row['observed']+row['missing']==row['posts']
        assert row['measurement']=='lifetime_snapshot'
        assert 'Unequal post ages' in row['limitation']
        if row['observed']==0: assert row['median'] is None
    assert all(item['sha256'] and item['csv_record_offset']==2 for item in report['sources'].values())


def test_all_decision_views_render_from_same_report(real,report,monkeypatch):
    # Freeze only the expensive report computation; use its real verified output.
    from stats_app import decision_ui
    monkeypatch.setattr(decision_ui,'report_for',lambda repo:report)
    code="from stats_app.analysis_repository import AnalysisRepository\nfrom stats_app.decision_ui import render_decision_report\nrender_decision_report(AnalysisRepository("+repr(str(real.db_path))+"))"
    at=AppTest.from_string(code,default_timeout=30).run()
    assert not at.exception and not at.error
    for section in ['Songs','Content','Audience','Quality & methods','Experiments','Growth & persistence']:
        at.radio[0].set_value(section).run()
        assert not at.exception and not at.error, section
    assert any(x.value=='28' for x in at.metric)


def test_refresh_refuses_existing_output_and_source_library(tmp_path,real,monkeypatch):
    spec=importlib.util.spec_from_file_location('refresh_analysis_test',ROOT/'scripts/refresh_analysis.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'load_registered_analysis',lambda *args: real)
    library=tmp_path/'library';library.mkdir()
    with pytest.raises(ValueError,match='outside'):
        module.refresh(library,library/'output')
    output=tmp_path/'existing';output.mkdir()
    with pytest.raises(ValueError,match='already exists'):
        module.refresh(library,output)
