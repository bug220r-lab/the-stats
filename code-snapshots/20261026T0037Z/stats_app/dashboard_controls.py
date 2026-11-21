"""Session-persistent controls with explicit source-native reporting windows.

Durable session keys survive Streamlit's cleanup of widgets on other pages.
No selections or defaults are written to the source databases.
"""
from datetime import date, timedelta
import streamlit as st


def _remember(widget, saved):
    st.session_state[saved] = st.session_state[widget]


def _keys(key):
    return "control:" + key, "selection:" + key


def selectbox(label, options, *, key, index=0, **kwargs):
    options = list(options)
    if not options:
        return None
    widget, saved = _keys(key)
    value = st.session_state.get(saved, options[index])
    if value not in options:
        value = options[index]
        display = kwargs.get("format_func", str)(value)
        st.caption(f"{label}: the earlier selection is unavailable in this source; showing {display}.")
    st.session_state[widget] = value
    result = st.selectbox(label, options, key=widget, on_change=_remember, args=(widget, saved), **kwargs)
    st.session_state[saved] = result
    return result


def radio(label, options, *, key, index=0, **kwargs):
    options = list(options)
    if not options:
        return None
    widget, saved = _keys(key)
    value = st.session_state.get(saved, options[index])
    if value not in options:
        value = options[index]
        display = kwargs.get("format_func", str)(value)
        st.caption(f"{label}: the earlier selection is unavailable in this source; showing {display}.")
    st.session_state[widget] = value
    result = st.radio(label, options, key=widget, on_change=_remember, args=(widget, saved), **kwargs)
    st.session_state[saved] = result
    return result


def multiselect(label, options, *, key, **kwargs):
    options = list(options)
    widget, saved = _keys(key)
    previous = st.session_state.get(saved, kwargs.pop("default", []))
    value = [v for v in previous if v in options]
    if len(value) != len(previous):
        st.caption(f"{label}: selections absent from this source were removed.")
    st.session_state[widget] = value
    result = st.multiselect(label, options, key=widget, on_change=_remember, args=(widget, saved), **kwargs)
    st.session_state[saved] = result
    return result


def date_range(label, low, high, default, *, key):
    widget, saved = _keys(key)
    chosen = tuple(st.session_state.get(saved, default))
    if any(d < low or d > high for d in chosen):
        chosen = default
        st.caption("The saved date range falls outside this source's coverage; showing the available range.")
    st.session_state[widget] = chosen
    chosen = st.date_input(label, min_value=low, max_value=high, key=widget,
                           on_change=_remember, args=(widget, saved))
    st.session_state[saved] = chosen
    if len(chosen) != 2:
        st.info("Choose both the start and end date to calculate this view.")
        return None
    return tuple(chosen)


def text_input(label, *, key, **kwargs):
    widget, saved = _keys(key)
    st.session_state[widget] = st.session_state.get(saved, "")
    value = st.text_input(label, key=widget, on_change=_remember, args=(widget, saved), **kwargs)
    st.session_state[saved] = value
    return value


def reporting_window(data, *, label="Reporting period", key="spotify", allow_ytd=False):
    low, high = date.fromisoformat(str(data.date.min())), date.fromisoformat(str(data.date.max()))
    options = ["Latest 28 days", "Latest 90 days", "Latest 7 days", "All available", "Custom"]
    if allow_ytd:
        options.insert(3, "Year to date, matching prior year")
    preset = selectbox(label, options, key=key + ":preset")
    days = {"Latest 28 days": 28, "Latest 90 days": 90, "Latest 7 days": 7}.get(preset)
    start, end = max(low, high - timedelta(days=days-1)) if days else low, high
    if preset == "Year to date, matching prior year":
        start = max(low, date(high.year, 1, 1))
    if preset == "Custom":
        selected = date_range("UTC activity dates", low, high, (start, end), key=key + ":dates")
        if selected is None:
            return None
        start, end = selected
    st.caption(f"Applies to this view: {start:%b %d, %Y} – {end:%b %d, %Y} · UTC · {(end-start).days+1} calendar days. Latest loaded date: {high}.")
    return start, end, preset


def navigate(page, **selections):
    st.session_state["explore_page"] = page
    for key, value in selections.items():
        st.session_state["selection:" + key] = value


def jump(label, page, *, key, **selections):
    st.button(label, key=key, on_click=navigate, args=(page,), kwargs=selections, width="stretch")
