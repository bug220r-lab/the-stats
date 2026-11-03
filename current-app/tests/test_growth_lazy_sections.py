"""Hidden evidence and inactive analysis sections do not read original sources."""
import pandas as pd
from streamlit.testing.v1 import AppTest


class CountingRepo:
    def original_bytes(self, path):
        import streamlit as st
        st.session_state["original_reads"] = st.session_state.get("original_reads", 0) + 1
        return b"value\n0\n"

    def table(self, path):
        import streamlit as st
        st.session_state["dictionary_reads"] = st.session_state.get("dictionary_reads", 0) + 1
        return pd.DataFrame({"table": ["source.csv"], "definition": ["Source count"]})


def test_shared_evidence_defers_original_bytes_and_dictionary_until_open():
    app = AppTest.from_string('''import pandas as pd
import streamlit as st
from test_growth_lazy_sections import CountingRepo
from stats_app.analysis_ui_common import evidence
opened = st.checkbox('Exercise evidence open branch', key='test_open')
st.session_state['sample_evidence'] = opened
evidence(CountingRepo(), 'source.csv', pd.DataFrame({'value': [0]}), 'sample')
''').run()
    assert not app.exception and not app.error
    assert "original_reads" not in app.session_state and "dictionary_reads" not in app.session_state
    assert app.dataframe[0].value.value.tolist() == [0]
    app.checkbox("test_open").set_value(True).run()
    assert not app.exception and not app.error
    assert app.session_state["original_reads"] == app.session_state["dictionary_reads"] == 1
    app.checkbox("test_open").set_value(False).run()
    assert app.session_state["original_reads"] == app.session_state["dictionary_reads"] == 1


def test_row_callback_updates_stable_identity_once_without_mutating_records():
    app = AppTest.from_string('''import pandas as pd
import streamlit as st
from stats_app.row_details import remember_selection
data = pd.DataFrame({'identity_key': ['Instagram/a/7', 'Instagram/b/7'], 'description': ['Same text', 'Same text']})
st.session_state['row_event'] = {'selection': {'rows': [1]}}
remember_selection('row_event', data, 'identity_key', 'selection:detail')
st.text(st.session_state['selection:detail'])
st.dataframe(data)
''').run()
    assert not app.exception and not app.error
    assert app.text[0].value == "Instagram/b/7"
    assert app.dataframe[0].value.identity_key.tolist() == ["Instagram/a/7", "Instagram/b/7"]


def test_cross_platform_only_executes_active_native_tab(monkeypatch):
    from stats_app import analysis_correlation_ui as ui
    calls = []
    monkeypatch.setattr(ui, "_activity", lambda _: {})
    monkeypatch.setattr(ui, "render_spikes", lambda *_: calls.append("spikes"))
    monkeypatch.setattr(ui, "_timeline", lambda *_: calls.append("timeline"))
    monkeypatch.setattr(ui, "_reviewed", lambda *_: calls.append("reviewed"))
    app = AppTest.from_string('''import streamlit as st
from stats_app.analysis_correlation_ui import render_posts_spotify
st.session_state['correlation:tabs'] = st.session_state.get('test_tab', 'Spotify spikes')
render_posts_spotify(object())
''').run()
    assert not app.exception and not app.error and calls == ["spikes"]
    app.session_state["test_tab"] = "Reviewed results"
    app.run()
    assert not app.exception and not app.error and calls == ["spikes", "reviewed"]
