"""Identity, capture ordering and unknown-date behavior for collected content."""
from copy import deepcopy

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from stats_app.analysis_content import (
    BRIDGE_PATH, CONTENT_PATH, INHERITED_PATH, MANUAL_PATH,
    apply_identity_bridges, conflicting_publication_identities, content_identity_inventory, load_content_observations, normalize_content,
    publication_inventory, search_content, select_content_observations,
)


class MemoryRepo:
    def __init__(self, tables):
        self.frames = {path: pd.DataFrame(rows) for path, rows in tables.items()}
        self.tables = list(self.frames)

    def table(self, path, raw=False):
        frame = self.frames[path].copy().fillna("")
        frame.attrs["source_sha256"] = "a" * 64
        return frame

    def original_bytes(self, path):
        return self.frames[path].to_csv(index=False).encode("utf-8")


def observation(post_id="1", *, account="ig-a", platform="Instagram", capture="2026-10-23T12:00:00+00:00", views="12", **extra):
    return {"platform_selected": platform, "selected_account_id": account, "account_id_type": "native_account",
            "post_id": post_id, "post_type": "IG photo", "description": "A retained post " + post_id,
            "permalink": "https://www.instagram.com/p/" + post_id + "/", "publication_date": "2026-05-08",
            "published_local": "2026-05-08T17:52:00", "publication_timezone": "America/Los_Angeles",
            "snapshot_timestamp": capture, "source_file": "native.csv", "source_url": "https://business.facebook.com/",
            "source_sha256": "b" * 64, "metric_platform_scope": "Instagram", "author_scope": "band_authored",
            "measurement_type": "lifetime_content_snapshot", "views": views, "views_status": "observed_zero" if views == "0" else "observed",
            "reach": "", "reach_status": "unavailable", **extra}


def synthetic_repo():
    old = observation(capture="2026-10-22T12:00:00+00:00", views="10")
    fresh = observation()
    unknown_capture = observation(capture="", views="13", source_record="3")
    unknown_date = observation("2", views="0", publication_date="", published_local="Fri May 8, 5:52pm")
    manual = observation("3", account="mbs-a", account_id_type="Meta Business Suite asset", post_type="IG story",
                         description="", publication_date="", published_local="Fri May 8, 5:52pm", views="31",
                         source_kind="manual_story_detail", metric_platform_scope="Story detail; scope otherwise unlabelled")
    conflicting = [observation("4", views=value, source_record=str(i)) for i, value in enumerate(("4", "5"))]
    return MemoryRepo({INHERITED_PATH: [old], CONTENT_PATH: [fresh, unknown_capture, unknown_date, deepcopy(unknown_date),
        observation(account="ig-b", views="20"), observation(platform="Facebook", account="fb-a", views="50", metric_platform_scope="Facebook"), *conflicting],
        MANUAL_PATH: [manual]})


def test_identity_uses_platform_account_type_account_and_post_id():
    data = load_content_observations(synthetic_repo())
    ones = data.loc[data.post_id.eq("1")]
    assert ones.identity_key.nunique() == 3
    assert len(data) == 9, "An exact repeated import row is not another observation."
    manual = data.loc[data.source_table.eq(MANUAL_PATH)].iloc[0]
    assert manual.account_id_type == "meta_business_suite_asset"
    assert manual.selected_account_id == manual.identity_account_id == "mbs-a"


def test_latest_never_adds_lifetime_captures_or_ranks_unknown_capture_time():
    observations = load_content_observations(synthetic_repo())
    latest = select_content_observations(observations)
    item = latest.loc[latest.selected_account_id.eq("ig-a") & latest.post_id.eq("1")]
    assert set(item.views) == {12, 13}
    assert set(item.selection_status) == {"latest_compatible_capture", "capture_time_unknown"}
    assert 10 not in item.views.tolist()
    conflicts = latest.loc[latest.post_id.eq("4")]
    assert set(conflicts.views) == {4, 5}
    assert set(conflicts.selection_status) == {"same_time_conflict"}
    assert len(select_content_observations(observations, "all")) == 9
    assert len(select_content_observations(observations, "unknown_capture")) == 1


def test_unknown_year_does_not_become_date_or_age_and_zero_remains_numeric():
    repo = synthetic_repo()
    before = repo.frames[CONTENT_PATH].copy(deep=True)
    data = load_content_observations(repo)
    unknown = data.loc[data.post_id.isin(["2", "3"])]
    assert unknown.publication_date.eq("").all()
    assert unknown.post_age_days.isna().all()
    assert unknown.published_local.eq("Fri May 8, 5:52pm").all()
    zero = data.loc[data.post_id.eq("2")].iloc[0]
    assert zero.views == 0 and zero.views_status == "observed_zero"
    assert pd.isna(zero.reach) and zero.reach_status == "unavailable"
    assert len(search_content(data, "Fri May 8")) == 2
    cadence = publication_inventory(data)
    assert cadence.retained_publications.sum() == 4
    assert "views" not in cadence
    pd.testing.assert_frame_equal(repo.frames[CONTENT_PATH], before)


def test_rounding_unknown_capture_and_conflicting_publication_dates_are_not_inferred():
    rows = [observation("9", views="1.2K", capture="2026-10-23T12:00:00", views_status="rounded_display_not_exact"),
            observation("9", publication_date="2026-05-09", published_local="2026-05-09T17:52:00")]
    data = load_content_observations(MemoryRepo({CONTENT_PATH: rows}))
    assert pd.isna(data.iloc[0].views)
    assert data.iloc[0].views_raw == "1.2K"
    assert data.iloc[0].capture_time_status == "unknown_or_invalid"
    assert publication_inventory(data).empty
    assert len(conflicting_publication_identities(data)) == 1


def publication_conflict_repo():
    old = observation(capture="2026-10-22T12:00:00+00:00")
    latest = observation(publication_date="2026-05-09", published_local="2026-05-09T17:52:00",
                         impressions="81", impressions_status="observed")
    dated = observation("2")
    undated = observation("2", account="mbs-a", account_id_type="Meta Business Suite asset", post_type="IG story",
                          publication_date="", published_local="Fri May 8, 5:52pm", metric_platform_scope="Story detail")
    bridge = {"platform_selected": "Instagram", "from_account_id_type": "Meta Business Suite asset", "from_account_id": "mbs-a",
              "to_account_id_type": "native Instagram account", "to_account_id": "ig-a", "verification_status": "verified", "evidence_ref": "proof.txt"}
    return MemoryRepo({INHERITED_PATH: [old], CONTENT_PATH: [latest, dated], MANUAL_PATH: [undated], BRIDGE_PATH: [bridge]})


def test_latest_ui_exposes_retained_date_conflicts_and_excludes_them_from_cadence():
    at = AppTest.from_string('''from test_meta_content_views import publication_conflict_repo
from stats_app.analysis_content_ui import render_content_library
render_content_library(publication_conflict_repo())
''', default_timeout=30).run()
    assert not at.exception and not at.error
    shown = at.dataframe[0].value
    assert shown.loc[shown.post_id.eq("1"), "publication_dates"].tolist() == ["2026-05-08; 2026-05-09"]
    assert shown.loc[shown.post_id.eq("1"), "publication_date_status"].tolist() == ["Conflicting known dates"]
    assert "impressions" not in shown
    assert any("1 distinct content identities have conflicting known publication dates" in item.value for item in at.warning)
    assert at.dataframe[1].value.retained_publications.sum() == 1
    assert any("verified selected-account bridge" in item.value and "does not establish authorship" in item.value for item in at.info)
    undated_card = next(item for item in at.metric if item.label == "Identities with undated captures")
    assert undated_card.value == "1", "A dated capture elsewhere does not make this undated capture disappear."
    next(item for item in at.radio if item.label == "Content display").set_value("Capture observations").run()
    shown = at.dataframe[0].value
    assert shown.loc[shown.post_id.eq("1"), "publication_date"].tolist() == ["2026-05-09"]
    assert shown.loc[shown.post_id.eq("1"), "impressions"].tolist() == [81]


def test_impressions_remain_separate_from_views_and_follow_status_masking():
    rows = [observation(views="", views_status="not_supplied", impressions="81", impressions_status="observed"),
            observation("2", impressions="100", impressions_status="suppressed")]
    data = load_content_observations(MemoryRepo({CONTENT_PATH: rows}))
    assert data.iloc[0].impressions == 81 and pd.isna(data.iloc[0].views)
    assert pd.isna(data.iloc[1].impressions) and data.iloc[1].impressions_raw == "100"


def test_only_verified_evidenced_account_bridge_can_unify_manual_and_native_identity():
    native = observation("3")
    manual = observation("3", account="mbs-a", account_id_type="Meta Business Suite asset")
    bridge = {"platform_selected": "Instagram", "from_account_id_type": "Meta Business Suite asset", "from_account_id": "mbs-a",
              "to_account_id_type": "native Instagram account", "to_account_id": "ig-a", "verification_status": "unverified", "evidence_ref": "proof.txt"}
    repo = MemoryRepo({CONTENT_PATH: [native], MANUAL_PATH: [manual], BRIDGE_PATH: [bridge]})
    assert load_content_observations(repo).identity_key.nunique() == 2
    bridge["verification_status"] = "verified"
    repo = MemoryRepo({CONTENT_PATH: [native], MANUAL_PATH: [manual], BRIDGE_PATH: [bridge]})
    data = load_content_observations(repo)
    assert data.identity_key.nunique() == 1
    assert data.loc[data.source_table.eq(MANUAL_PATH), "selected_account_id"].iloc[0] == "mbs-a"
    conflict = dict(bridge, to_account_id="ig-b")
    with pytest.raises(ValueError, match="Conflicting"):
        apply_identity_bridges(data, pd.DataFrame([bridge, conflict]))


def test_incompatible_metric_scopes_remain_separate_for_same_identity():
    rows = [observation(metric_platform_scope="Instagram", views="10", capture="2026-10-22T12:00:00+00:00"),
            observation(metric_platform_scope="Facebook and Instagram combined", views="20")]
    latest = select_content_observations(load_content_observations(MemoryRepo({CONTENT_PATH: rows})))
    assert len(latest) == 2 and latest.identity_key.nunique() == 1
    assert set(latest.views) == {10, 20}


def multi_scope_repo():
    return MemoryRepo({CONTENT_PATH: [
        observation(capture="2026-10-22T12:00:00+00:00", views="10"),
        observation(views="12"), observation(capture="", views="13"),
        observation(views="20", metric_platform_scope="Facebook and Instagram combined"),
    ]})


def test_inventory_groups_identity_without_combining_scope_or_vintage_metrics(monkeypatch):
    import stats_app.analysis_content_ui as ui
    exports = []
    original = ui.filtered_csv
    monkeypatch.setattr(ui, "filtered_csv", lambda frame: (exports.append(frame.copy()), original(frame))[1])
    observations = load_content_observations(multi_scope_repo())
    latest = select_content_observations(observations)
    inventory = content_identity_inventory(latest, observations)
    assert len(inventory) == 1 and inventory.iloc[0].capture_count == 3
    assert len(content_identity_inventory(observations)) == 1
    assert content_identity_inventory(observations).iloc[0].capture_count == 4
    assert not {"views", "reach", "impressions", "interactions"}.intersection(inventory.columns)
    at = AppTest.from_string('''from test_meta_content_views import multi_scope_repo
from stats_app.analysis_content_ui import render_content_library
render_content_library(multi_scope_repo())
''', default_timeout=30).run()
    assert not at.exception and not at.error
    display = next(item for item in at.radio if item.label == "Content display")
    assert display.value == "One row per post"
    assert len(at.dataframe[0].value) == len(exports[0]) == 1
    assert exports[0].identity_key.nunique() == 1 and exports[0].iloc[0].capture_count == 3
    assert len(exports[1]) == 3 and set(exports[1].views) == {12, 13, 20}
    display.set_value("Capture observations").run()
    assert not at.exception and not at.error
    assert len(at.dataframe[0].value) == 3 and set(at.dataframe[0].value.views) == {12, 13, 20}
    next(item for item in at.selectbox if item.label == "Content observation view").set_value("All retained captures").run()
    assert len(at.dataframe[0].value) == 4


def test_content_library_search_unknown_dates_and_filtered_download(monkeypatch):
    import stats_app.analysis_content_ui as ui
    exports = []
    original = ui.filtered_csv
    monkeypatch.setattr(ui, "filtered_csv", lambda frame: (exports.append(frame.copy()), original(frame))[1])
    at = AppTest.from_string('''from test_meta_content_views import synthetic_repo
from stats_app.analysis_content_ui import render_content_library
render_content_library(synthetic_repo())
''', default_timeout=30).run()
    assert not at.exception and not at.error
    assert any("same capture time" in item.value for item in at.warning)
    assert any("unknown capture time" in item.value for item in at.warning)
    assert any("Manual Story recovery" in item.value for item in at.info)
    next(item for item in at.radio if item.label == "Content display").set_value("Capture observations").run()
    next(item for item in at.radio if item.label == "Publication dates").set_value("Unknown dates only").run()
    exports.clear()
    next(item for item in at.text_input if item.label.startswith("Search collected posts")).set_value("Fri May 8").run()
    assert not at.exception and not at.error
    shown = at.dataframe[0].value
    assert len(shown) == len(exports[0]) == 2
    assert shown.publication_date.eq("").all()
    assert set(exports[0].post_id) == {"2", "3"}
    assert [item.value for item in at.metric] == ["2", "2", "2"]
    next(item for item in at.multiselect if item.label == "Content evidence sources").set_value([]).run()
    assert not at.exception and not at.error
    assert any("Choose at least one" in item.value for item in at.info)


def test_social_default_exposes_collected_library_and_keeps_legacy_sections():
    at = AppTest.from_string('''from test_meta_content_views import synthetic_repo
from stats_app.analysis_social_ui import render_social
render_social(synthetic_repo())
''', default_timeout=30).run()
    assert not at.exception and not at.error
    section = next(item for item in at.radio if item.label == "Social view")
    assert section.value == "Collected posts & Stories"
    assert {"Account activity", "Content & publishing", "Audience distribution", "Native period & stock evidence"}.issubset(section.options)
    assert any(item.label == "Content evidence sources" for item in at.multiselect)
    assert any("Manual Story recovery" in item.value for item in at.info)
    assert not any(item.label == "Social platform" for item in at.selectbox)
