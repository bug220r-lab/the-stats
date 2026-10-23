"""Optional end-to-end dashboard checks against the private staged handoff.

Tests copy the staged archive and register only that temporary copy. No live
database, recovery original, source export, or production registry is edited.
"""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3

import pytest
from streamlit.testing.v1 import AppTest

from stats_app.config import PROJECT_ROOT
from stats_app.library import LibraryRepository
from stats_app.storage import SQLiteRepository


STAGED = PROJECT_ROOT / "data" / "reconciliation" / "staged_handoff"
pytestmark = pytest.mark.skipif(not (STAGED / "data" / "stats.sqlite3").exists(),
                               reason="Private staged handoff is not included in source control.")


@pytest.fixture(scope="module")
def staged_copy(tmp_path_factory):
    root = tmp_path_factory.mktemp("dashboard-archive")
    target = root / "archives" / "handoff"
    original_database = STAGED / "data" / "stats.sqlite3"
    original_hash = sha256(original_database.read_bytes()).hexdigest()
    shutil.copytree(STAGED, target)
    archive_database = target / "data" / "stats.sqlite3"
    before_hash = sha256(archive_database.read_bytes()).hexdigest()
    source_hashes = {p.name: sha256(p.read_bytes()).hexdigest() for p in (target / "data" / "sources").iterdir() if p.is_file()}
    (root / "archive_registry.json").write_text(json.dumps({"archives": [{
        "key": "handoff", "database": "archives/handoff/data/stats.sqlite3",
        "source_dir": "archives/handoff/data/sources", "evidence_root": "archives/handoff",
        "label": "Temporary copy of verified handoff",
    }]}), encoding="utf-8")
    local = SQLiteRepository(root / "stats.sqlite3")
    local.import_dataset(b"synthetic legacy source", "legacy.csv", [dict(
        platform="Spotify", account="legacy-account", entity_type="artist", entity_id="legacy",
        entity_name="Legacy test", metric="streams", value=17, unit="count",
        period_start="2026-10-20", period_end="2026-10-20", time_grain="daily",
        measurement_type="period_count", status="observed")], "Original October 20 baseline",
        baseline=True, provenance={"baseline_evidence": "Historical test designation"})
    local.seal_snapshot("Original October 20 baseline")
    library = LibraryRepository(local)
    snapshot_names = {int(row.snapshot_id): row.label for row in library.list_snapshots().itertuples()
                      if row.backend == "handoff"}
    yield root, snapshot_names
    assert sha256(original_database.read_bytes()).hexdigest() == original_hash
    assert sha256(archive_database.read_bytes()).hexdigest() == before_hash
    assert {p.name: sha256(p.read_bytes()).hexdigest() for p in (target / "data" / "sources").iterdir() if p.is_file()} == source_hashes
    assert local.list_snapshots().iloc[0].label == "Original October 20 baseline"
    assert local.list_snapshots().iloc[0].is_baseline == 1
    assert local.observations("Original October 20 baseline").iloc[0].value == 17


@pytest.fixture
def registered_app(staged_copy, monkeypatch):
    root, names = staged_copy
    monkeypatch.setenv("STATS_DATA_DIR", str(root))
    monkeypatch.setenv("STATS_MODE", "local")
    monkeypatch.delenv("STATS_IMPORT_DIR", raising=False)
    return names


def app():
    return AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=60).run()


def select(at, label, value):
    control = next(item for item in at.selectbox if item.label == label)
    control.set_value(value).run()
    assert not at.exception, [item.value for item in at.exception]
    assert not at.error, [item.value for item in at.error]
    return at


def radio(at, label, value):
    next(item for item in at.radio if item.label == label).set_value(value).run()
    assert not at.exception, [item.value for item in at.exception]
    assert not at.error, [item.value for item in at.error]
    return at


def scope(at, text):
    control = next(item for item in at.selectbox if item.label == "Measurement scope")
    index = next(i for i, option in enumerate(control.options) if option.startswith(text))
    return select(at, "Measurement scope", index)


def test_original_archive_additions_and_historical_supplement_render(registered_app):
    names = registered_app
    at = app()
    assert not at.exception and not at.error
    assert any("82,878 stored observations" in item.value for item in at.caption)
    assert len(at.get("plotly_chart")) == 1
    for snapshot_id, count in [(3, "1,755"), (4, "12,448")]:
        select(at, "Snapshot", names[snapshot_id])
        assert any(f"{count} stored observations" in item.value for item in at.caption)
        assert at.dataframe
        assert any("unverified" in item.value for item in at.warning)
        assert all(str(value).startswith("handoff::") for value in at.dataframe[0].value.observation_id)
    restarted = app()
    assert not restarted.exception and not restarted.error
    assert any("82,878 stored observations" in item.value for item in restarted.caption)


def test_newer_capture_keeps_unknown_windows_out_of_period_charts(registered_app):
    at = app()
    select(at, "Snapshot", registered_app[5])
    assert any("1,472 stored observations" in item.value for item in at.caption)
    radio(at, "Evidence view", "Lifetime / unknown window")
    assert not at.metric
    assert not at.get("plotly_chart")
    assert any("no established reporting bounds" in item.value for item in at.info)
    data = at.dataframe[0].value
    assert len(data) == 62
    assert data.period_start.fillna("").eq("").all() and data.period_end.fillna("").eq("").all()
    assert data.time_grain.eq("unknown").all()
    assert data.captured_at.fillna("").ne("").all()
    assert data.evidence_ref.fillna("").ne("").all()


def test_social_crossposted_scope_and_exact_unique_audiences(registered_app):
    at = app()
    select(at, "Snapshot", registered_app[2])
    select(at, "Platform", "Instagram")
    select(at, "Account", "meta_asset:118246571240106")
    select(at, "Metric", "views")
    assert any("instagram and facebook" in item.value for item in at.info)
    data = at.dataframe[0].value
    assert all(json.loads(value)["reported_scope"] == "instagram_and_facebook" for value in data.dimensions_json)
    select(at, "Platform", "Facebook")
    select(at, "Account", "meta_asset:118246571240106")
    select(at, "Metric", "viewers")
    scope(at, "Daily")
    assert at.metric[0].value == "Unavailable", "Daily unique viewers must not be summed."
    data = at.dataframe[0].value
    assert data.measurement_type.eq("distinct_audience_count").all()
    assert data.time_grain.eq("daily").all()
    scope(at, "Period")
    assert at.metric[0].value == "35"
    data = at.dataframe[0].value
    assert len(data) == 1
    assert data.iloc[0].period_start == "2026-09-24" and data.iloc[0].period_end == "2026-10-21"
    select(at, "Exact source period", ("2026-07-24", "2026-10-21"))
    assert at.metric[0].value == "145"


def test_instagram_lifetime_keeps_source_accounts_and_publication_dates_separate(registered_app):
    at = app()
    select(at, "Snapshot", registered_app[2])
    select(at, "Platform", "Instagram")
    select(at, "Account", "17841454335424545")
    assert any("Lifetime results are not period activity" in item.value for item in at.info)
    assert not at.metric and not at.get("plotly_chart")
    data = at.dataframe[0].value
    assert len(data) == 63
    assert data.time_grain.eq("lifetime").all()
    assert data.period_start.fillna("").eq("").all() and data.period_end.fillna("").eq("").all()
    assert data.published_at.fillna("").ne("").all() and data.captured_at.fillna("").ne("").all()
    assert data.account.eq("17841454335424545").all()
    select(at, "Account", "17841401826640240")
    other = at.dataframe[0].value
    assert len(other) == 7 and other.account.eq("17841401826640240").all()


def test_legacy_baseline_alias_and_coverage_sources_render(registered_app):
    at = app()
    select(at, "Snapshot", "local::Original October 20 baseline")
    assert any("Legacy Windows native archive · baseline unverified" in item.value for item in at.caption)
    assert any("unavailable / unverified" in item.value for item in at.warning)
    assert at.metric[0].value == "17"
    radio(at, "Explore", "Coverage & cross-reference")
    assert any("TikTok access and collection are deferred" in item.value for item in at.info)
    assert any(item.label.endswith("spotify_coverage.json") for item in at.expander)
    assert any(item.label.endswith("spotify_import_report.json") for item in at.expander)
    assert any("queue_scope" in frame.value.columns for frame in at.dataframe)
    radio(at, "Explore", "Sources & provenance")
    assert len(at.dataframe) >= 2
    history = at.dataframe[1].value
    assert set(history.backend) == {"handoff", "local"}
    assert history.import_id.is_unique
    assert not at.exception and not at.error
