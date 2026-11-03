"""Native window controls, captions and downloads share the selected scope."""
import io
import json

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from test_tiktok_rankings import inventory, rankings


def _app(rows=None):
    tables={"post_inventory":inventory().to_dict("records"),"content_rankings":rankings().to_dict("records") if rows is None else rows,
            "account_panel_metrics":[{"window_days":"28","reporting_start":"2026-09-28","reporting_end":"2026-10-25"},{"window_days":"7","reporting_start":"2026-10-19","reporting_end":"2026-10-25"}],
            "post_summary":[{"post_id":"001","new_followers_raw":"6.6K","views_raw":"1.3M","likes_raw":"104K","saves_raw":"3327","shares_raw":"600","captured_at":"2026-10-27T00:00:00Z"},{"post_id":"004","new_followers_raw":"0","views_raw":"0","likes_raw":"0","saves_raw":"0","shares_raw":"0","captured_at":"2026-10-27T00:00:00Z"}]}
    script=f'''import json
import pandas as pd
from stats_app import dashboard_controls as controls
from stats_app.tiktok_rankings_ui import render_tiktok_rankings
class Repo:
    def __init__(self):
        self.data=json.loads({json.dumps(tables)!r})
        self.datasets=pd.DataFrame([{{"dataset_id":key}} for key in self.data])
    def table(self,name): return pd.DataFrame(self.data[name])
controls.begin_view("TikTok")
render_tiktok_rankings(Repo())
controls.finish_view()
controls.reset_button("TikTok")
'''
    return AppTest.from_string(script,default_timeout=20).run()


def test_default_period_search_precision_and_download_agree(monkeypatch):
    downloads={}
    original=st.download_button
    def capture(*args,**kwargs):
        downloads[kwargs.get("key")]=kwargs.get("data",args[1] if len(args)>1 else None)
        return original(*args,**kwargs)
    monkeypatch.setattr(st,"download_button",capture)
    app=_app()
    assert not app.exception and not app.error
    assert app.selectbox("control:tiktok:strongest:window").value==28
    assert app.selectbox("control:tiktok:strongest:metric").value=="new-followers"
    assert any("2026-09-28 – 2026-10-25" in c.value for c in app.caption)
    assert app.dataframe[0].value["New followers"].tolist()==["14","14","0"]
    app.text_input("control:tiktok:strongest:search").set_value("Repeated").run()
    frame=pd.read_csv(io.BytesIO(downloads["tiktok:strongest:download"]),dtype=str,keep_default_na=False)
    assert frame["rank"].tolist()==["2"] and frame.public_url.tolist()==[""]
    app.text_input("control:tiktok:strongest:search").set_value("").run()
    app.selectbox("control:tiktok:strongest:window").set_value(7).run()
    assert app.selectbox("control:tiktok:strongest:metric").value=="views"
    assert app.dataframe[0].value["Video views"].tolist()==["1.2K"]
    assert any("approximate positions" in c.value for c in app.caption)
    frame=pd.read_csv(io.BytesIO(downloads["tiktok:strongest:download"]),dtype=str)
    assert frame.ranking_value_raw.tolist()==["1.2K"] and "plot_value" not in frame


def test_snapshot_mode_and_empty_search_are_explicit():
    app=_app()
    app.radio("control:tiktok:strongest:mode").set_value("Cumulative post snapshots").run()
    assert not app.exception
    assert app.dataframe[0].value["Acquired followers · cumulative"].tolist()==["6.6K","0"]
    assert not any(s.label=="Native reporting window" for s in app.selectbox)
    assert any("unequal post ages" in c.value for c in app.caption)
    app.text_input("control:tiktok:strongest:search").set_value("does not exist").run()
    assert not app.exception and not app.get("plotly_chart")
    assert any("No posts match" in c.value for c in app.info)


def test_old_fixture_schema_is_unavailable_not_error():
    app=_app([{"rank":"1","source_file":"old.json","row_text":"Old capture"}])
    assert not app.exception and not app.error
    assert any("metric and window" in c.value for c in app.info)
