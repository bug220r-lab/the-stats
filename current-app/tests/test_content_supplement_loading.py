"""Additive capture supplements preserve identity, scope and source evidence."""
from copy import deepcopy

import pandas as pd
import pytest

from stats_app.analysis_content import (
    BRIDGE_PATH, CONTENT_PATH, MANUAL_PATH, content_table_paths,
    identity_bridge_paths, load_content_observations, select_content_observations,
)
from stats_app.content_summaries import content_source_paths, content_summary

SUPPLEMENT = "social/meta_refresh_20261024/"
SUPPLEMENT_CONTENT = SUPPLEMENT + "content_snapshots.csv"
SUPPLEMENT_BRIDGES = SUPPLEMENT + "identity_bridges.csv"
STORY_BACKFILL = "social/meta_story_backfill_20261024/"


class MemoryRepo:
    def __init__(self, tables):
        self.frames = {path: pd.DataFrame(rows) for path, rows in tables.items()}
        self.tables = list(self.frames)

    def table(self, path, raw=False):
        frame = self.frames[path].copy().fillna("")
        frame.attrs["source_sha256"] = "a" * 64
        return frame


def observation(post_id, **extra):
    row = dict(platform_selected="Instagram", selected_account_id="ig", account_id_type="native_account",
                post_id=post_id, post_type="IG story", description="Story " + post_id,
                publication_date="2026-10-22", publication_timezone="UTC", published_local="2026-10-22T14:00:00",
                snapshot_timestamp="2026-10-23T12:00:00+00:00", metric_platform_scope="Instagram",
                author_scope="band_authored", measurement_type="lifetime_content_snapshot",
                views="10", views_status="observed", link_clicks="", link_clicks_status="")
    row.update(extra)
    return row


def bridge(target="ig"):
    return dict(platform_selected="Instagram", from_account_id_type="meta_business_suite_asset",
                from_account_id="mbs", to_account_id_type="native_account", to_account_id=target,
                verification_status="verified", evidence_ref="retained-account-proof.txt")


def test_supplement_adds_captures_and_sources_without_repeating_publications():
    old = observation("one")
    later = dict(old, snapshot_timestamp="2026-10-24T12:00:00+00:00", views="12")
    zero = observation("two", link_clicks="0", link_clicks_status="observed_zero")
    native = observation("shared")
    manual = dict(native, selected_account_id="mbs", account_id_type="meta_business_suite_asset")
    source = MemoryRepo({CONTENT_PATH: [old, native], MANUAL_PATH: [manual],
                         BRIDGE_PATH: [dict(bridge(), verification_status="unverified")],
                         SUPPLEMENT_CONTENT: [deepcopy(old), later, zero], SUPPLEMENT_BRIDGES: [bridge()]})
    before = {path: frame.copy(deep=True) for path, frame in source.frames.items()}
    data, selected, coverage, _ = content_summary(source)
    assert len(data) == 5 and coverage["identities"] == coverage["stories"] == 3
    assert len(selected) == 3
    assert selected.loc[selected.post_id.eq("one"), "views"].tolist() == [12]
    assert selected.loc[selected.post_id.eq("two"), "link_clicks"].tolist() == [0]
    assert selected.loc[selected.post_id.eq("shared"), "supporting_observation_count"].tolist() == [2]
    assert data.loc[data.source_table.eq(SUPPLEMENT_CONTENT), "source_table_sha256"].eq("a" * 64).all()
    assert content_source_paths(source) == [CONTENT_PATH, MANUAL_PATH, SUPPLEMENT_CONTENT, BRIDGE_PATH, SUPPLEMENT_BRIDGES]
    for path, frame in source.frames.items():
        pd.testing.assert_frame_equal(frame, before[path])


def test_conflicting_account_bridges_across_capture_namespaces_are_rejected():
    source = MemoryRepo({CONTENT_PATH: [observation("one")],
                         BRIDGE_PATH: [bridge()], SUPPLEMENT_BRIDGES: [bridge("other-ig")]})
    with pytest.raises(ValueError, match="Conflicting verified content account identity bridges"):
        load_content_observations(source)


def test_only_explicit_supplement_namespaces_are_content_sources():
    source = MemoryRepo({CONTENT_PATH: [observation("one")],
                         "social/unregistered/content_snapshots.csv": [observation("unregistered")],
                         SUPPLEMENT + "raw/content_snapshots.csv": [observation("raw")],
                         "social/unregistered/identity_bridges.csv": [bridge()]})
    assert content_table_paths(source) == content_source_paths(source) == [CONTENT_PATH]
    assert identity_bridge_paths(source) == []
    assert load_content_observations(source).post_id.tolist() == ["one"]


def test_older_selected_version_without_supplement_keeps_existing_capture():
    source = MemoryRepo({CONTENT_PATH: [observation("one")]})
    selected = select_content_observations(load_content_observations(source))
    assert selected.post_id.tolist() == ["one"] and selected.views.tolist() == [10]
    assert content_source_paths(source) == [CONTENT_PATH]


def test_story_backfill_extends_refresh_and_uses_its_verified_account_bridge():
    native = observation("shared")
    detail = dict(native, selected_account_id="mbs", account_id_type="meta_business_suite_asset",
                  description="Recovered full caption", snapshot_timestamp="2026-10-25T12:00:00+00:00", views="21")
    source = MemoryRepo({CONTENT_PATH: [native], SUPPLEMENT_CONTENT: [observation("refreshed")],
                         STORY_BACKFILL + "content_snapshots.csv": [detail],
                         STORY_BACKFILL + "identity_bridges.csv": [bridge()]})
    observations, selected, coverage, _ = content_summary(source)
    assert coverage["identities"] == 2 and len(observations) == 3
    latest = selected.loc[selected.post_id.eq("shared")].iloc[0]
    assert latest.description == "Recovered full caption" and latest.views == 21
    assert latest.source_table == STORY_BACKFILL + "content_snapshots.csv"
    assert latest.identity_account_id == "ig" and latest.selected_account_id == "mbs"
    assert content_source_paths(source) == [CONTENT_PATH, SUPPLEMENT_CONTENT,
                                          STORY_BACKFILL + "content_snapshots.csv",
                                          STORY_BACKFILL + "identity_bridges.csv"]
