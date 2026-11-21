"""Expanded summary correctness across identities, captures and missing evidence."""
from copy import deepcopy

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from stats_app.analysis_content import BRIDGE_PATH, CONTENT_PATH, INHERITED_PATH, MANUAL_PATH, load_content_observations
from stats_app.content_summaries import content_summary


class MemoryRepo:
    def __init__(self, tables):
        self.frames = {path: pd.DataFrame(rows) for path, rows in tables.items()}
        self.tables = list(self.frames)

    def table(self, path, raw=False):
        frame = self.frames[path].copy().fillna("")
        frame.attrs["source_sha256"] = "a" * 64
        return frame

    def original_bytes(self, path):
        return self.frames[path].to_csv(index=False).encode()


def post(identifier, value="10", **extra):
    return dict(platform_selected="Instagram", selected_account_id="ig", account_id_type="native_account",
                post_id=identifier, post_type="IG story", description="Retained story " + identifier,
                publication_date="2026-02-20", published_local="2026-02-20T14:00:00", publication_timezone="UTC",
                snapshot_timestamp="2026-10-23T12:00:00+00:00", metric_platform_scope="Instagram", author_scope="band_authored",
                measurement_type="lifetime_content_snapshot", views=value, views_status="observed_zero" if value == "0" else "observed",
                **extra)


def repo():
    old = post("one", "5")
    old["snapshot_timestamp"] = "2026-10-22T12:00:00+00:00"
    latest = post("one", "10")
    scoped = post("one", "900")
    scoped["metric_platform_scope"] = "Facebook and Instagram combined"
    typed = post("one", "30")
    typed["account_id_type"] = "meta_business_suite_asset"
    conflict_date = post("one", "4")
    conflict_date.update(publication_date="2026-02-21", snapshot_timestamp="2026-10-21T12:00:00+00:00")
    unknown = post("unknown", "99")
    unknown["snapshot_timestamp"] = ""
    same_time = [post("disputed", value) for value in ("1", "200")]
    missing = post("missing", "0")
    missing["views_status"] = "not_supplied"
    undated = post("undated", "3")
    undated.update(publication_date="", published_local="Friday 2pm", publication_timezone="")
    return MemoryRepo({INHERITED_PATH: [old], CONTENT_PATH: [latest, deepcopy(latest), scoped, typed, conflict_date,
                       unknown, *same_time, missing, post("zero", "0"), undated]})


def test_expanded_coverage_deduplicates_identity_and_preserves_date_conflicts():
    source = repo()
    before = {path: frame.copy(deep=True) for path, frame in source.frames.items()}
    observations, selected, coverage, rows = content_summary(source)
    assert coverage["identities"] == 7
    assert coverage["stories"] == 7
    assert coverage["conflicting_date_identities"] == 1
    assert coverage["unknown_date_identities"] == 1
    assert coverage["unknown_capture_observations"] == 1
    assert coverage["conflicting_capture_observations"] == 2
    assert len(observations) == 11  # exact duplicate is not another capture
    assert len(selected) == 9     # older compatible lifetime observations disappear
    for path, frame in source.frames.items():
        pd.testing.assert_frame_equal(frame, before[path])


def test_metrics_never_weight_repeated_conflicting_unknown_or_other_scope_captures():
    _, _, _, rows = content_summary(repo())
    target = next(row for row in rows if row["identity_account_id_type"] == "native_account"
                  and row["metric_platform_scope"] == "Instagram" and row["capture_cohort"] == "2026-10-23 UTC" and row["metric"] == "views")
    assert target["posts"] == 5
    assert target["observed"] == 3 and target["missing"] == 2
    assert target["excluded_metric_identities"] == 1
    assert target["median"] == 3  # [10, 0, 3], not repeated captures, 99, 900 or 30
    assert target["maximum"] == 10
    assert target["age_observed"] == 2, "Contradictory publication dates cannot establish an age."
    unknown = next(row for row in rows if row["capture_cohort"] == "Unknown capture time" and row["metric"] == "views")
    assert unknown["posts"] == unknown["missing"] == 1 and unknown["observed"] == 0
    assert pd.isna(unknown["median"])
    assert all(row["posts"] == row["observed"] + row["missing"] for row in rows)


def test_inherited_only_saved_versions_fall_back_without_expansion():
    source = MemoryRepo({INHERITED_PATH: [post("one")]})
    _, _, coverage, rows = content_summary(source)
    assert coverage["identities"] == coverage["stories"] == 1
    assert all(row["source_table"] == INHERITED_PATH for row in rows)
    assert next(row for row in rows if row["metric"] == "views")["median"] == 10


def test_expanded_social_renders_inventory_with_all_scopes_and_sources(monkeypatch):
    from stats_app import analysis_social_ui
    source = repo()
    monkeypatch.setattr(analysis_social_ui, "load_content_observations", lambda ignored: load_content_observations(source))
    monkeypatch.setattr(analysis_social_ui, "_download", lambda *args: None)
    # The fake repo supports unchanged original-table downloads in the evidence expander.
    monkeypatch.setattr(analysis_social_ui, "_expanded_test_repo", source, raising=False)
    code = "from stats_app.analysis_social_ui import _content, _expanded_test_repo\n_content(_expanded_test_repo, 'Instagram')"
    app = AppTest.from_string(code, default_timeout=30).run()
    assert not app.exception and not app.error
    assert next(item for item in app.metric if item.label == "Distinct content identities").value == "7"
    assert any("conflicting publication dates" in item.value for item in app.warning)
    assert len(app.get("plotly_chart")) >= 1
    next(item for item in app.text_input if item.label == "Find a post · caption, ID or link").set_value("missing").run()
    assert not app.exception and not app.error
    assert next(item for item in app.metric if item.label == "Distinct content identities").value == "1"
    next(item for item in app.text_input if item.label == "Find a post · caption, ID or link").set_value("").run()
    assert next(item for item in app.metric if item.label == "Distinct content identities").value == "7"


def test_social_presentation_filters_cannot_promote_old_captions_or_resolve_conflicts(monkeypatch):
    from stats_app import analysis_social_ui
    old = post("changing", "5")
    old.update(description="Funny old caption", snapshot_timestamp="2026-10-22T12:00:00+00:00")
    new = post("changing", "10")
    new.update(description="Changed latest caption")
    disputed = post("disputed", "1")
    disputed.update(description="Funny conflict", author_scope="band_authored")
    alternate = post("disputed", "200")
    alternate.update(description="Different conflict", author_scope="associated_account_authorship_unverified")
    source = MemoryRepo({INHERITED_PATH: [old], CONTENT_PATH: [new, disputed, alternate]})
    monkeypatch.setattr(analysis_social_ui, "load_content_observations", lambda ignored: load_content_observations(source))
    monkeypatch.setattr(analysis_social_ui, "_expanded_test_repo", source, raising=False)
    exported = {}
    def capture(data, name, key):
        exported[key] = data.copy()
    monkeypatch.setattr(analysis_social_ui, "_download", capture)
    code = "from stats_app.analysis_social_ui import _content, _expanded_test_repo\n_content(_expanded_test_repo, 'Instagram')"
    app = AppTest.from_string(code, default_timeout=30).run()
    assert not app.exception and not app.error
    assert exported["social-content-records"].views.tolist() == [10]
    search = next(item for item in app.text_input if item.label == "Find a post · caption, ID or link")
    exported.clear()
    search.set_value("Funny old").run()
    assert not app.exception and not app.error
    assert any("No latest captures match" in item.value for item in app.info)
    assert "social-content-records" not in exported, "A matching historical caption cannot promote its 5 views."
    search = next(item for item in app.text_input if item.label == "Find a post · caption, ID or link")
    search.set_value("Funny conflict").run()
    assert not app.exception and not app.error
    assert exported["social-content-records"].empty, "One matching conflict caption cannot select its 1 view."
    assert any("unresolved identity or capture chronology" in item.value for item in app.caption)
    next(item for item in app.text_input if item.label == "Find a post · caption, ID or link").set_value("").run()
    next(item for item in app.multiselect if item.label == "Content author scope").set_value(["band_authored"]).run()
    assert not app.exception and not app.error
    assert exported["social-content-records"].views.tolist() == [10], "Authorship filtering cannot resolve the same-time conflict."
