"""Conflict gates plus acceptance checks on the real retained recovery package."""
import json
from pathlib import Path

import pandas as pd
import pytest

from stats_app.spotify_recovery import (RecoveryError, compare_values, deduplicate_agreements,
                                        inventory, numeric, verify_manifest)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/reconciliation/additional_20261023/analysis_v2"
ORIGINAL = ROOT / "data/recovery/cleaned_analysis_2026-10-22/analysis_2026-10-22"


def test_missing_is_not_zero_during_deduplication():
    source = pd.DataFrame({"id": ["a", "a"], "value": [None, 0]})
    with pytest.raises(RecoveryError, match="Conflicting"):
        deduplicate_agreements(source, ["id"], ["value"])


def test_duplicate_agreements_preserve_first_provenance():
    source = pd.DataFrame({"id": ["a", "a", "b"], "value": [1, 1, None], "capture": ["first", "second", "third"]})
    frame, count = deduplicate_agreements(source, ["id"], ["value"])
    assert count == 1
    assert frame.iloc[0]["capture"] == "first"
    assert pd.isna(frame.iloc[1]["value"])


def test_conflicts_and_duplicate_grains_are_rejected():
    source = pd.DataFrame({"id": ["a"], "value": [5]})
    with pytest.raises(RecoveryError, match="Conflicting"):
        compare_values(source, source.assign(value=6), ["id"], ["value"])
    with pytest.raises(RecoveryError, match="Duplicate"):
        compare_values(pd.concat([source, source]), source, ["id"], ["value"])


def test_manifest_rejects_modification_and_escape(tmp_path):
    (tmp_path / "normalized").mkdir()
    (tmp_path / "input.csv").write_text("id,value\na,1\n")
    (tmp_path / "manifest.json").write_text('{"datasets": []}')
    expected = inventory(tmp_path)
    (tmp_path / "sha256.json").write_text(json.dumps(expected))
    assert verify_manifest(tmp_path)[0]["verified_files"] == 2
    (tmp_path / "input.csv").write_text("id,value\na,0\n")
    with pytest.raises(RecoveryError, match="checksum"):
        verify_manifest(tmp_path)
    (tmp_path / "sha256.json").write_text(json.dumps({"../escape": "bad"}))
    with pytest.raises(RecoveryError, match="Unsafe"):
        verify_manifest(tmp_path)


def test_dash_and_zero_are_distinct():
    assert numeric("—") is None
    assert numeric("0") == 0
    assert numeric("1,234") == 1234


@pytest.fixture(scope="module")
def integrated():
    if not (OUTPUT / "audit/recovery_changes.json").is_file():
        pytest.skip("Private source recovery integration has not been run in this checkout")
    return OUTPUT


def test_real_original_rows_are_unchanged_and_added_rows_are_chart_evidence(integrated):
    old = pd.read_csv(ORIGINAL / "spotify/cleaned/track_daily_long.csv", low_memory=False)
    new = pd.read_csv(integrated / "spotify/cleaned/track_daily_long.csv", low_memory=False)
    keys = ["song_id", "date", "metric"]
    assert len(new) == 71680 and not new.duplicated(keys).any()
    retained = new[new.snapshot_class.eq("original_baseline")]
    pd.testing.assert_frame_equal(old.sort_values(keys).reset_index(drop=True), retained[old.columns].sort_values(keys).reset_index(drop=True), check_dtype=False)
    added = new[new.snapshot_class.eq("baseline_supplement")]
    assert len(added) == 5049
    assert added.evidence_type.eq("chart_derived").all()
    assert added.captured_utc.notna().all() and added.Evidence.notna().all()
    assert new.groupby(["song_id", "metric"]).date.nunique().eq(1024).all()
    assert new.date.max() == "2026-10-20"
    raw = pd.read_csv(integrated / "raw/recovery_evidence/recovery/normalized/recovered_song_daily.csv")
    checked = added.merge(raw, left_on=keys, right_on=["Spotify ID", "Date", "Metric"], validate="one_to_one", suffixes=("", "_raw"))
    assert checked.value.eq(checked.Value).all()
    assert checked.Evidence.eq(checked.Evidence_raw).all()
    assert checked.captured_utc.eq(checked["Collected UTC"]).all()


def test_real_complete_catalog_and_launch_eligibility(integrated):
    reconciliation = pd.read_csv(integrated / "spotify/cleaned/catalog_artist_daily_reconciliation.csv")
    assert len(reconciliation) == 1024 and reconciliation.difference.eq(0).all()
    launch = pd.read_csv(integrated / "spotify/cleaned/recording_launch_windows.csv")
    son = launch[launch.song_id.eq("2PWQKZvFk6wRGZmcgBzWRy")]
    assert son.complete.all() and len(son) == 3
    earlier = pd.read_csv(ORIGINAL / "spotify/cleaned/recording_launch_windows.csv")
    assert launch.complete.sum() == earlier.complete.sum() == 33
    eligible = ["song_id", "days_since_release", "streams"]
    pd.testing.assert_frame_equal(launch.loc[launch.complete, eligible].reset_index(drop=True), earlier.loc[earlier.complete, eligible].reset_index(drop=True))
    assert not launch[launch.release_date.lt("2024-01-01")].complete.any()
    report = json.loads((integrated / "audit/recovery_changes.json").read_text(encoding="utf-8"))
    assert report["source_audit"]["comparison_agreements"] == 54
    assert report["source_audit"]["daily_agreements"] == 1516
    assert report["source_audit"]["stream_check_outcomes"] == {"match": 252, "table unavailable; chart explicitly zero": 45}
    assert report["conflicts"] == 0


def test_real_source_nulls_hierarchies_and_newer_windows_remain_separate(integrated):
    source = pd.read_csv(integrated / "spotify/cleaned/source_recovery.csv")
    daily = pd.read_csv(integrated / "spotify/cleaned/source_history.csv")
    assert len(source) == 1269 and len(daily) == 37311
    checks = pd.read_csv(integrated / "spotify/cleaned/source_stream_reconciliation.csv")
    assert checks.table_streams.isna().sum() == 45
    assert checks.loc[checks.table_streams.isna(), "daily_stream_sum"].eq(0).all()
    summary = pd.read_csv(integrated / "spotify/cleaned/source_parent_stream_summary.csv")
    assert set(summary.Source) == {"All active sources", "All programmed sources", "Other"}
    assert summary.Metric.eq("streams").all()
    geo = pd.read_csv(integrated / "spotify/cleaned/geography_comparison_daily.csv")
    assert geo["Window end"].eq("2026-10-21").all()
    assert len(pd.read_csv(integrated / "spotify/cleaned/remaining_limits.csv")) == 7


def test_real_statistical_results_and_social_files_preserved(integrated):
    for path in ORIGINAL.rglob("*"):
        if path.is_file() and (path.relative_to(ORIGINAL).parts[0] in {"social", "cross_platform"} or path.name == "statistical_results.csv"):
            assert path.read_bytes() == (integrated / path.relative_to(ORIGINAL)).read_bytes()
    version = json.loads((integrated / "metadata.json").read_text(encoding="utf-8"))
    assert version["input_lineage"]["cross_platform"] == "cleaned-20261022"
    assert version["retrieval_vintage"] == "2026-10-23" and version["activity_endpoint"] == "2026-10-20"


def test_real_final_inventories_and_precise_dictionary(integrated):
    import hashlib
    for filename in ("source_inventory.csv", "spotify/source_file_inventory.csv"):
        for row in pd.read_csv(integrated / filename).itertuples():
            assert hashlib.sha256((integrated / row.path).read_bytes()).hexdigest() == row.sha256
    for row in json.loads((integrated / "raw_sha256.json").read_text(encoding="utf-8")):
        assert hashlib.sha256((integrated / row["path"]).read_bytes()).hexdigest() == row["sha256"]
    dictionary = pd.read_csv(integrated / "spotify/data_dictionary.csv")
    for name in ("canonical_dataset_id", "captured_utc", "parent_stream_total", "Current value", "Window start"):
        rows = dictionary[dictionary.column.eq(name)]
        assert not rows.empty and not rows.definition.str.contains("Preserved source field or explicitly derived").any()
