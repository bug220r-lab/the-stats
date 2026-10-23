"""Private real-source reconciliation; clean checkouts skip this optional fixture.

No private account identity or source URL is embedded in this test. It checks the
same public ingestion, storage and metrics paths as ordinary imports.
"""
import csv
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from stats.metrics import aggregate_metric, derived_ratio
from stats.storage import Store

ROOT = Path(__file__).resolve().parents[1]
CONNECTED = ROOT / "data/connected"
pytestmark = pytest.mark.skipif(not (CONNECTED / "source_inventory.json").exists(),
                                reason="Private connected source package is not in version control")


def loader():
    spec = importlib.util.spec_from_file_location("connected_loader", ROOT / "scripts/load_connected.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_connected


def test_real_source_reconciles_and_reimports_without_changing_totals(tmp_path):
    inventory = json.loads((CONNECTED / "source_inventory.json").read_text())
    expected = json.loads((CONNECTED / "reconciliation.json").read_text())
    with (CONNECTED / "source_archive/raw/artist_timeline_2024-01-01_2026-10-20.csv").open(encoding="utf-8-sig") as handle:
        source = list(csv.DictReader(handle))
    latest = [r for r in source if "2026-09-23" <= r["date"] <= "2026-10-20"]
    load = loader()
    files = {"artist_daily_canonical.csv", "artist_periods_canonical.csv"}
    first = load(tmp_path / "stats.sqlite3", CONNECTED, files)
    store = Store(first["db_path"])
    snapshot = next(s for s in store.snapshots() if s["id"] == first["snapshot_id"])
    assert snapshot["is_baseline"] == 0
    assert snapshot["status"] == "unverified"
    assert snapshot["locked"] == 0
    before = store.read_observations(first["snapshot_id"])
    total = before[(before["account_id"] == inventory["artist_id"]) &
                   (before["entity_type"] == "artist") & (before["dimensions"] == "{}")]
    for metric, key, native_key in (
        ("streams", "latest_28_streams", "streams"),
        ("saves", "latest_28_saves", "saves"),
        ("playlist_adds", "latest_28_playlist_adds", "playlist adds"),
    ):
        source_total = sum(int(r[native_key]) for r in latest)
        result = aggregate_metric(total, metric, "2026-09-23", "2026-10-20")
        assert result["value"] == source_total == expected[key], result
    listeners = aggregate_metric(total, "listeners", "2026-09-23", "2026-10-20")
    assert listeners["value"] == expected["latest_28_unique_listeners_direct_dashboard"]
    followers = aggregate_metric(total, "followers", "2026-09-23", "2026-10-20")
    assert followers["value"] == int(source[-1]["followers"]) == expected["last_followers"]
    rate = derived_ratio(total, "streams", "listeners", "2026-09-23", "2026-10-20")
    assert rate["value"] == pytest.approx(expected["latest_28_streams"] / listeners["value"])
    second = load(tmp_path / "stats.sqlite3", CONNECTED, files)
    assert first["snapshot_id"] == second["snapshot_id"]
    assert all(item["idempotent"] for item in second["files"])
    assert second["source_inventory_import"]["idempotent"]
    pd.testing.assert_frame_equal(before, store.read_observations(first["snapshot_id"]))
    assert len(store.queue()) == expected["queue_rows"]
    assert {row["Status"] for row in store.queue()} == set(expected["queue_status_counts"])
    assert store.mappings()["Canonical observation CSV"]
    assert any(issue["code"] == "baseline_unverified" for issue in store.issues())
