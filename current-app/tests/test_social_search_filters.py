"""Search must intersect stable social filters, never redefine their bounds."""
from datetime import date
from hashlib import sha256
import io

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from stats_app.analysis_repository import load_registered_analysis
from stats_app.config import load_settings


def test_search_and_clear_preserve_publication_dates_age_selection_and_export(monkeypatch):
    repo = load_registered_analysis(load_settings().data_dir)
    if repo is None:
        pytest.skip("Private immutable source package unavailable")
    before = sha256(repo.db_path.read_bytes()).hexdigest()
    exported = {}
    original_download = st.download_button

    def capture(*args, **kwargs):
        if kwargs.get("key") == "social-content-records":
            exported["records"] = kwargs.get("data", args[1] if len(args) > 1 else None)
        return original_download(*args, **kwargs)

    monkeypatch.setattr(st, "download_button", capture)
    code = ("from stats_app.analysis_repository import AnalysisRepository\n"
            "from stats_app.analysis_social_ui import _legacy_content\n"
            f"_legacy_content(AnalysisRepository({str(repo.db_path)!r}), 'Instagram')")
    app = AppTest.from_string(code, default_timeout=30).run()

    def widget(kind, label):
        return next(w for w in getattr(app, kind) if w.label == label)

    def choose(kind, label, value):
        widget(kind, label).set_value(value).run()
        assert not app.exception and not app.error

    dates = (date(2026, 1, 5), date(2026, 8, 16))
    choose("date_input", "Publication date range", dates)
    slider = widget("slider", "Post age at capture · days")
    age_bounds = (slider.proto.min, slider.proto.max)
    chosen_age = (1, slider.value[1] - 1)
    choose("slider", "Post age at capture · days", chosen_age)
    baseline = pd.read_csv(io.BytesIO(exported["records"]), dtype={"post_id": str})
    baseline_ids = set(baseline.post_id)
    assert len(baseline_ids) > 1
    choose("text_input", "Find a post · caption, ID or link", "Funny")
    assert widget("date_input", "Publication date range").value == dates
    assert widget("slider", "Post age at capture · days").value == chosen_age
    slider = widget("slider", "Post age at capture · days")
    assert (slider.proto.min, slider.proto.max) == age_bounds
    selected = pd.read_csv(io.BytesIO(exported["records"]), dtype={"post_id": str})
    assert 0 < len(selected) < len(baseline)
    assert set(selected.post_id) < baseline_ids
    assert selected.publication_date.between(str(dates[0]), str(dates[1])).all()
    assert selected.post_age_days.between(*chosen_age).all()
    assert widget("metric", "Retained publications").value == str(len(selected))
    choose("text_input", "Find a post · caption, ID or link", "")
    assert widget("date_input", "Publication date range").value == dates
    assert widget("slider", "Post age at capture · days").value == chosen_age
    restored = pd.read_csv(io.BytesIO(exported["records"]), dtype={"post_id": str})
    assert set(restored.post_id) == baseline_ids
    assert widget("metric", "Retained publications").value == str(len(restored))
    # Empty searches retain the controls so clearing can recover the same set.
    choose("text_input", "Find a post · caption, ID or link", "no-such-caption-reaudit")
    assert widget("date_input", "Publication date range").value == dates
    assert widget("slider", "Post age at capture · days").value == chosen_age
    assert any("within the selected date and age filters" in item.value for item in app.info)
    choose("text_input", "Find a post · caption, ID or link", "")
    restored = pd.read_csv(io.BytesIO(exported["records"]), dtype={"post_id": str})
    assert set(restored.post_id) == baseline_ids
    assert sha256(repo.db_path.read_bytes()).hexdigest() == before
