"""Stable identities for read-only dataframe selection and detail panels."""
from __future__ import annotations

import hashlib
import json


def selection_key(prefix, data, identity_columns):
    """A reordered or filtered table gets fresh positional selection state."""
    columns = [column for column in identity_columns if column in data]
    rows = data[columns].fillna("").astype(str).values.tolist()
    signature = hashlib.sha256(json.dumps(rows, ensure_ascii=True).encode()).hexdigest()[:16]
    return f"{prefix}:{signature}"


def selected_identity(event, data, column):
    """Resolve a selected original-data position, never a displayed title."""
    selection = event.get("selection", {}) if hasattr(event, "get") else {}
    rows = selection.get("rows", [])
    if not rows or column not in data:
        return None
    position = rows[-1]
    if not isinstance(position, int) or isinstance(position, bool) or not 0 <= position < len(data):
        return None
    return str(data.iloc[position][column])


def remember_selection(event_key, data, column, target_key):
    """Apply a row click once, before detail widgets render on the rerun."""
    import streamlit as st
    identity = selected_identity(st.session_state.get(event_key, {}), data, column)
    if identity is not None:
        st.session_state[target_key] = identity


def safe_web_url(value):
    """Only retained HTTP(S) destinations are offered as clickable links."""
    from urllib.parse import urlsplit
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None
