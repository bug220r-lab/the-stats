"""Availability, scope and interaction checks in an isolated Linktree view."""
import json

import pandas as pd
from streamlit.testing.v1 import AppTest

from linktree_fixtures import synthetic_package
from stats_app.linktree_ui import numeric_values, inspection_csv


def test_numeric_values_keep_zero_and_over_100_percent_but_not_unavailable():
    data = pd.DataFrame({"value": ["0", "162.5", "5", "", "inf"],
                         "availability_status": ["observed", "observed", "unavailable", "unavailable", "observed"]})
    assert numeric_values(data).iloc[:2].tolist() == [0, 162.5]
    assert numeric_values(data).iloc[2:].isna().all()
    assert data.value.tolist() == ["0", "162.5", "5", "", "inf"]


def test_inspection_csv_neutralizes_formulas_without_modifying_originals():
    data = pd.DataFrame({"value": [" =UNTRUSTED()", "+link", "-1.5", "0"]})
    text = inspection_csv(data).decode("utf-8-sig")
    assert "' =UNTRUSTED()" in text and "'+link" in text and "'-1.5" not in text
    assert data.iloc[0].value == " =UNTRUSTED()"


def test_ui_overview_daily_missingness_and_selected_row_are_scoped(tmp_path):
    source = synthetic_package(tmp_path)
    app = AppTest.from_string("from stats_app.linktree_repository import LinktreeRepository\n"
                              "from stats_app.linktree_ui import render_linktree\n"
                              f"render_linktree(LinktreeRepository({json.dumps(str(source))}))\n")
    app.run(timeout=20)
    assert not app.exception
    assert any("unknown" in item.value for item in app.info)
    assert any("incomplete" in item.value for item in app.warning)
    assert {item.value for item in app.metric} == {"8", "13", "162.5%"}
    app.radio[0].set_value("Daily activity").run(timeout=20)
    assert not app.exception
    assert any("Daily unique" in item.value or "daily unique" in item.value for item in app.caption)
    assert any("partial source day" in item.value for item in app.warning)
    app.radio[0].set_value("Links & destinations").run(timeout=20)
    assert not app.exception
    app.text_input[0].set_value("not-present").run(timeout=20)
    assert any("No records match" in item.value for item in app.info)
    app.text_input[0].set_value("").run(timeout=20)
    app.toggle[0].set_value(True).run(timeout=20)
    assert not app.exception and len(app.json) == 1
    assert "00001" in app.json[0].value


def test_absent_collection_has_useful_empty_state():
    app = AppTest.from_string("from stats_app.linktree_ui import render_linktree\nrender_linktree(None)").run()
    assert not app.exception
    assert "No verified Linktree collection" in app.info[0].value


def test_linktree_reset_clears_detail_panels_and_search_but_keeps_source_section_and_other_view(tmp_path):
    source = synthetic_package(tmp_path)
    script = "from stats_app.linktree_repository import LinktreeRepository\n" \
             "from stats_app.linktree_ui import render_linktree\n" \
             "from stats_app import dashboard_controls as controls\n" \
             "controls.begin_view('Linktree')\n" \
             "controls.selectbox('Collection', ['first', 'second'], key='linktree_collection_selector')\n" \
             f"render_linktree(LinktreeRepository({json.dumps(str(source))}))\n" \
             "controls.finish_view()\ncontrols.reset_button('Linktree')\n"
    app = AppTest.from_string(script).run()
    app.selectbox('control:linktree_collection_selector').set_value('second').run()
    app.toggle('linktree:summary:rows').set_value(True).run()
    app.toggle('linktree:limitations').set_value(True).run()
    app.radio[0].set_value('Source details').run()
    app.text_input[0].set_value('total_views').run()
    app.toggle('linktree:originals').set_value(True).run()
    app.session_state['selection:spotify:preset'] = 'Latest 90 days'
    app.button('reset:Linktree').click().run()
    assert not app.exception
    assert app.selectbox('control:linktree_collection_selector').value == 'second'
    assert app.radio[0].value == 'Source details'
    assert app.text_input[0].value == ''
    assert app.toggle('linktree:originals').value is False
    assert app.session_state['selection:spotify:preset'] == 'Latest 90 days'
    app.radio[0].set_value('Overview').run()
    assert app.toggle('linktree:summary:rows').value is False
    assert app.toggle('linktree:limitations').value is False
