"""Session-persistent controls with explicit source-native reporting windows.

Durable session keys survive Streamlit's cleanup of widgets on other pages.
No selections or defaults are written to the source databases.
"""
from datetime import date, timedelta
import streamlit as st

SOURCE_KEYS = {"analysis_version", "youtube_collection_selector", "shopify_collection_selector",
               "linktree_collection_selector", "tiktok_collection_selector", "apple:snapshot", "snapshot:source"}
VIEW_KEYS = {"spotify:view", "analysis-social-view", "cross-platform:view", "apple:view", "linktree:section",
             "tiktok:section", "insights:section", "content-plan:view", "content-plan:start", "correlation:tabs", "yt_supplement_view", "youtube_view_selector_saved"}
LEGACY_PREFIXES = {"YouTube collection": ("yt_", "youtube_view_selector"), "Shopify": ("shopify_",),
                   "Social": ("content-library", "social-partial", "social-content-undated", "social-content-search", "selection:social-content-search"), "Linktree": ("linktree:inspect:",),
                   "Apple Music": ("apple:evidence",), "Cross-platform": ("correlation:",)}


def begin_view(scope):
    st.session_state["_active_view_scope"] = scope
    summaries = dict(st.session_state.get("_view_filter_summaries", {}))
    summaries[scope] = {}
    st.session_state["_view_filter_summaries"] = summaries
    for key, value in st.session_state.get("_legacy_view_selections", {}).get(scope, {}).items():
        if key not in st.session_state:
            st.session_state[key] = value


def active_scope():
    return st.session_state.get("_active_view_scope", "Overview")


def finish_view():
    scope = active_scope()
    prefixes = LEGACY_PREFIXES.get(scope, ())
    keys = [key for key in st.session_state if key.startswith(prefixes) and key not in SOURCE_KEYS
            and not any(word in key for word in ("download", "jump", "open_", "entry"))]
    own_keys(*keys)
    saved = dict(st.session_state.get("_legacy_view_selections", {}))
    saved[scope] = {key: st.session_state[key] for key in keys
                    if type(st.session_state[key]) in (str, int, float, tuple, list)
                    or key in {"social-partial", "social-content-undated"}}
    st.session_state["_legacy_view_selections"] = saved


def own_keys(*keys, scope=None):
    scope = scope or st.session_state.get("_active_view_scope")
    if not scope:
        return
    owned = dict(st.session_state.get("_view_owned_keys", {}))
    owned[scope] = sorted(set(owned.get(scope, [])) | set(keys))
    st.session_state["_view_owned_keys"] = owned


def reset_view(scope):
    for key in st.session_state.get("_view_owned_keys", {}).get(scope, []):
        raw = key.removeprefix("control:").removeprefix("selection:")
        if raw not in SOURCE_KEYS | VIEW_KEYS and raw not in {"youtube_view_selector", "shopify_view_selector"}:
            st.session_state.pop(key, None)
    saved = dict(st.session_state.get("_legacy_view_selections", {}))
    saved.pop(scope, None)
    st.session_state["_legacy_view_selections"] = saved
    summaries = dict(st.session_state.get("_view_filter_summaries", {}))
    summaries.pop(scope, None)
    st.session_state["_view_filter_summaries"] = summaries


def reset_button(scope, *, label="Reset this view"):
    st.button(label, key="reset:" + scope, on_click=reset_view, args=(scope,),
              help="Restore this view's default filters. Source and other views stay selected.")


def _record(label, key, value, options=None, formatter=str):
    if key in SOURCE_KEYS:
        return
    scope = st.session_state.get("_active_view_scope")
    if not scope:
        return
    widget, saved = _keys(key)
    own_keys(widget, saved)
    summaries = dict(st.session_state.get("_view_filter_summaries", {}))
    current = dict(summaries.get(scope, {}))
    if isinstance(value, tuple) and options is not None and value in options:
        text = str(formatter(value))
    elif isinstance(value, (tuple, list)):
        text = ", ".join(str(formatter(v)) for v in value) or ("All available" if "empty means all" in label.lower() else "None selected")
        if options is not None and value and len(value) == len(options):
            text = "All available"
    else:
        text = formatter(value) if value not in (None, "") else "No restriction"
    current[key] = f"{label}: {text}"
    summaries[scope] = current
    st.session_state["_view_filter_summaries"] = summaries


def filter_summary(scope):
    values = st.session_state.get("_view_filter_summaries", {}).get(scope, {})
    if values:
        with st.expander("Active selections", expanded=False):
            for text in values.values():
                st.caption(text)


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
    _record(label, key, result, options, kwargs.get("format_func", str))
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
    _record(label, key, result, options, kwargs.get("format_func", str))
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
    _record(label, key, result, options, kwargs.get("format_func", str))
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
    _record(label, key, chosen)
    if len(chosen) != 2:
        st.info("Choose both the start and end date to calculate this view.")
        return None
    return tuple(chosen)


def text_input(label, *, key, **kwargs):
    widget, saved = _keys(key)
    st.session_state[widget] = st.session_state.get(saved, "")
    value = st.text_input(label, key=widget, on_change=_remember, args=(widget, saved), **kwargs)
    st.session_state[saved] = value
    _record(label, key, value)
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
    routes = st.session_state.get("_native_routes", {})
    if page in routes:
        st.session_state["_requested_page"] = page
        st.switch_page(routes[page])


def jump(label, page, *, key, **selections):
    st.button(label, key=key, on_click=navigate, args=(page,), kwargs=selections, width="stretch")
