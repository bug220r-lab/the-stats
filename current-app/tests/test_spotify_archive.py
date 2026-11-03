"""Retained-source semantics and staged preservation checks.

The real archive checks skip only on machines without the private recovery data.
"""
import json
from pathlib import Path
import sqlite3

import pytest

from stats_app.spotify_archive import build_import_plan, number, original_audit, stage_import, timestamp


ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "data/recovery/mac_handoff_2026-10-22"


@pytest.mark.parametrize("value", [None, "", "-", "—", "–"])
def test_missing_not_zero(value):
    assert number(value) is None


def test_explicit_zero_and_date_only_capture():
    assert number("0") == 0
    assert timestamp("2026-10-23 (UTC date only)") == "2026-10-23"
    with pytest.raises(ValueError):
        number("2.6K")


@pytest.fixture(scope="module")
def real_plan():
    if not (RECOVERY / "data/stats.sqlite3").is_file():
        pytest.skip("Private recovery package is not installed on this test machine")
    return build_import_plan(RECOVERY)


def file_rows(plan, key, filename):
    snapshot = next(p for p in plan["plans"] if p["key"] == key)
    return next(f["records"] for f in snapshot["files"] if f["path"].name == filename)


def test_real_supplement_bounds_and_missing_values(real_plan):
    records = file_rows(real_plan, "newer_supplement", "resume_snapshots.csv")
    assert len(records) == 122
    undated = [r for r in records if r["period_start"] is None]
    assert len(undated) == 62
    assert all(r["period_end"] is None and r["time_grain"] == "unknown" for r in undated)
    assert sum(r["status"] == "missing" and r["value"] is None for r in records) == 2
    period = sum((file_rows(real_plan, key, "recovered_source_periods.csv") for key in ("historical_supplement", "newer_supplement")), [])
    assert len(period) == 414
    assert sum(r["value"] is None for r in period) == 66


def test_audience_and_lifetime_scopes(real_plan):
    daily = file_rows(real_plan, "historical_supplement", "source_daily_supplement.csv")
    assert all(r["measurement_type"] == "distinct_audience_count" for r in daily if r["metric"] == "listeners")
    assert all(r["dimensions"]["hierarchy_level"] == "aggregate" for r in daily if r["dimensions"]["source_category"].startswith("All "))
    assert all(r["measurement_type"] == "rolling_window_count" for r in file_rows(real_plan, "archive_additions", "audience_segment_daily.csv"))
    lifetime = file_rows(real_plan, "archive_additions", "song_alltime_counters.csv")
    assert len(lifetime) == 14
    assert all(r["measurement_type"] == "lifetime_count" and r["period_start"] is None and r["period_end"] is None for r in lifetime)
    cohort = file_rows(real_plan, "archive_additions", "release_engagement_daily.csv")
    assert len(cohort) == 224
    assert all(r["measurement_type"] == "cumulative_count" for r in cohort)


def test_staged_import_preserves_and_replays(real_plan, tmp_path):
    original = original_audit(RECOVERY / "data/stats.sqlite3")
    first = stage_import(RECOVERY, tmp_path / "stage")
    assert first["integrity"] == "ok"
    assert first["earlier_snapshot_rows_unchanged"]
    assert first["original_source_files_unchanged"] == 27
    assert [r["active_observations"] for r in first["snapshots"]] == [82878, 2397, 1755, 12448, 1472]
    assert all(r["rejected"] == 0 and r["revised"] == 0 for r in first["imports"])
    replay = stage_import(RECOVERY, tmp_path / "stage")
    assert all(r["idempotent"] for r in replay["imports"])
    assert original_audit(RECOVERY / "data/stats.sqlite3") == original
    assert original_audit(first["database"]) == original
    with sqlite3.connect(first["database"]) as connection:
        assert connection.execute("select sum(is_baseline) from snapshots").fetchone()[0] == 0
        assert connection.execute("select count(*) from collection_queue").fetchone()[0] == 43
    ledger = json.loads(Path(first["coverage_path"]).read_text(encoding="utf-8"))
    assert any("bounds" in gap for gap in ledger["gaps"])
