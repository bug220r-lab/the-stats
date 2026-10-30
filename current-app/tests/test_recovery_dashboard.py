"""Recovery version bindings preserve earlier results and aggregation boundaries."""
import json
from pathlib import Path
import shutil

import pandas as pd
import pytest
from native_navigation_helpers import NativeAppTest as AppTest

from native_navigation_helpers import open_page

from stats_app.analysis_metrics import catalog_comparison, source_ratio_plot_values
from stats_app.analysis_repository import AnalysisRepository

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "data/reconciliation/staged_analysis/analysis.sqlite3"
NEW = ROOT / "data/reconciliation/additional_20261023/staged_analysis_v2/analysis.sqlite3"


def test_reported_zero_ratio_is_not_a_valid_zero_when_denominator_zero():
    source = pd.DataFrame({"Date":["2026-10-18","2026-10-19","2026-10-20"], "Source":[0.0, 2.0, 3.0]})
    listeners = pd.DataFrame({"Date":["2026-10-18","2026-10-19"], "Source":[0, 1]})
    shown, undefined, unknown = source_ratio_plot_values(source, listeners, ["Date"], ["Source"])
    assert pd.isna(shown.Source.iloc[0]) and shown.Source.iloc[1] == 2.0 and pd.isna(shown.Source.iloc[2])
    assert undefined == 1 and unknown == 1 and source.Source.iloc[0] == 0


@pytest.fixture(scope="module")
def recovered():
    if not NEW.exists(): pytest.skip("Private recovery version not staged")
    return AnalysisRepository(NEW)


def test_full_history_now_complete_and_old_results_preserved(recovered):
    original = AnalysisRepository(OLD)
    track = recovered.table("spotify/cleaned/track_daily_long.csv")
    recordings = recovered.table("spotify/cleaned/recordings.csv")
    artist = recovered.table("spotify/cleaned/artist_daily.csv")
    result = catalog_comparison(track, recordings, artist, "streams", "2024-01-01", "2026-10-20")
    assert len(track) == 71680 and len(result) == 14 and result.complete.all()
    assert result.current.sum() == artist.daily_streams.sum()
    old = catalog_comparison(original.table("spotify/cleaned/track_daily_long.csv"), recordings, artist,
                             "streams", "2024-01-01", "2026-10-20")
    assert old.current.isna().sum() == 2
    assert recovered.original_bytes("cross_platform/statistical_results.csv") == original.original_bytes("cross_platform/statistical_results.csv")


def test_canonical_marker_does_not_allow_duplicate_grain(recovered):
    track = recovered.table("spotify/cleaned/track_daily_long.csv")
    recordings = recovered.table("spotify/cleaned/recordings.csv")
    artist = recovered.table("spotify/cleaned/artist_daily.csv")
    duplicate = track.loc[track.metric.eq("streams")].iloc[:1].copy()
    duplicate["snapshot_class"] = "arbitrary_later_capture"
    with pytest.raises(ValueError, match="Ambiguous"):
        catalog_comparison(pd.concat([track, duplicate]), recordings, artist, "streams", "2024-01-01", "2026-10-20")
    with pytest.raises(ValueError, match="retrieval"):
        catalog_comparison(track.drop(columns="canonical_dataset_id"), recordings, artist, "streams", "2024-01-01", "2026-10-20")
    with pytest.raises(ValueError, match="unique listeners"):
        catalog_comparison(track, recordings, artist, "listeners", "2024-01-01", "2026-10-20")


@pytest.fixture(scope="module")
def versions(tmp_path_factory, recovered):
    root = tmp_path_factory.mktemp("recovery-version-ui")
    records = []
    for key, source, label in [("v1", OLD, "Original analysis"), ("v2", NEW, "Expanded Spotify recovery")]:
        dest = root / "analysis" / key
        dest.mkdir(parents=True)
        shutil.copy2(source, dest / "analysis.sqlite3")
        records.append(dict(key=key, label=label, database=f"analysis/{key}/analysis.sqlite3", evidence_root=f"analysis/{key}"))
    (root / "archive_registry.json").write_text(json.dumps(dict(archives=[], analysis_versions=records, analysis_package=records[1])))
    return root


def choose(app, label, value, kind="selectbox"):
    next(item for item in getattr(app, kind) if item.label == label).set_value(value).run()
    assert not app.error and not app.exception


def test_version_selection_and_recovered_source_scopes(versions, monkeypatch):
    monkeypatch.setenv("STATS_DATA_DIR", str(versions)); monkeypatch.setenv("STATS_MODE", "local")
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=50).run()
    assert not app.exception and not app.error
    assert app.metric[0].value == "4,246"
    open_page(app, "Spotify")
    assert not app.error and not app.exception
    choose(app, "Spotify view", "Catalog comparison", "radio")
    choose(app, "Spotify date window", "All available")
    assert app.dataframe[0].value.complete.all()
    choose(app, "Spotify view", "Recovered sources", "radio")
    assert any("never summed" in w.value for w in app.warning)
    assert len(app.get("plotly_chart")) >= 1
    choose(app, "Recovered source metric", "streams_per_listener")
    assert any("No sum" in c.value for c in app.caption)
    choose(app, "Spotify view", "Recovery evidence", "radio")
    assert any(m.value == "71,680" for m in app.metric)
    open_page(app, "Cross-platform")
    assert not app.error and not app.exception
    assert any("original cleaned analysis inputs" in i.value for i in app.info)
    choose(app, "Analysis version", "v1")
    open_page(app, "Spotify")
    assert not app.error and not app.exception
    choose(app, "Spotify view", "Catalog comparison", "radio")
    choose(app, "Spotify date window", "All available")
    assert app.dataframe[0].value.current.isna().sum() == 2

