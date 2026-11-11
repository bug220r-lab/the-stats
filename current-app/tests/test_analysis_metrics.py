from pathlib import Path
import io
import json
import pandas as pd
import pytest

from stats_app.analysis_metrics import artist_comparison, catalog_comparison, daily_periods, exact_period_audience, follower_change, require_unique
from stats_app.analysis_repository import AnalysisRepository

DB=Path(__file__).resolve().parents[1]/"data/reconciliation/staged_analysis/analysis.sqlite3"

@pytest.fixture(scope="module")
def real():
    if not DB.exists(): pytest.skip("Private analysis package unavailable")
    return AnalysisRepository(DB)

def test_known_spotify_totals_and_period_unique(real):
    artist=real.table("spotify/cleaned/artist_daily.csv")
    result=artist_comparison(artist,"daily_streams","2026-09-23","2026-10-20")
    assert result["current"]==4246 and result["previous"]==4011
    assert result["change_pct"]==pytest.approx(5.8588880578)
    periods=real.table("spotify/cleaned/artist_period_dashboard.csv")
    row=exact_period_audience(periods,"2026-09-23","2026-10-20")
    assert row.current_value==1062 and row.previous_value==1121
    assert exact_period_audience(periods,"2026-09-22","2026-10-20") is None

def test_unique_audiences_and_incomplete_prior_block_total(real):
    artist=real.table("spotify/cleaned/artist_daily.csv")
    with pytest.raises(ValueError,match="additive"):
        artist_comparison(artist,"daily_listeners","2026-09-23","2026-10-20")
    result=artist_comparison(artist,"daily_streams","2024-01-01","2024-01-28")
    assert result["current"] is not None and result["previous"] is None
    assert result["change_pct"] is None

def test_catalog_totals_reconcile_without_join_fanout(real):
    track=real.table("spotify/cleaned/track_daily_long.csv")
    recordings=real.table("spotify/cleaned/recordings.csv")
    artist=real.table("spotify/cleaned/artist_daily.csv")
    result=catalog_comparison(track,recordings,artist,"streams","2026-09-23","2026-10-20")
    assert len(result)==14 and result.complete.all()
    assert result.current.sum()==4246 and result.previous.sum()==4011
    assert (result.current>result.previous).sum()==11
    assert result.loc[result.recording_label.eq("Funny Guy"),"share_of_artist_pct"].iloc[0]==pytest.approx(35.0447479981)
    old=catalog_comparison(track,recordings,artist,"streams","2024-01-01","2026-10-20")
    assert old.current.isna().sum()==2
    with pytest.raises(ValueError,match="Ambiguous"):
        catalog_comparison(track,pd.concat([recordings,recordings.iloc[:1]]),artist,"streams","2026-09-23","2026-10-20")

def test_different_retrieval_vintages_cannot_be_blended(real):
    artist=real.table("spotify/cleaned/artist_daily.csv")
    altered=artist.iloc[:1].copy();altered["snapshot_class"]="newer_snapshot"
    with pytest.raises(ValueError,match="retrieval"):
        artist_comparison(pd.concat([artist,altered]),"daily_streams","2026-09-23","2026-10-20")


def test_follower_and_complete_period_results_reconcile_to_preserved_native_rows(real):
    daily = real.table("spotify/cleaned/artist_daily.csv")
    path = "raw/spotify_baseline/raw/artist_timeline_2024-01-01_2026-10-20.csv"
    native = pd.read_csv(io.BytesIO(real.original_bytes(path)))
    followers = follower_change(daily, "2026-09-23", "2026-10-20")
    indexed = native.set_index("date")
    assert followers["baseline"] == indexed.loc["2026-09-22", "followers"] == 1616
    assert followers["current"] == indexed.loc["2026-10-20", "followers"] == 1644
    assert followers["net_change"] == 28
    for reference in json.loads(followers["source_references"]):
        assert native.iloc[reference["source_row"]-2].date == reference["date"]
    last = daily_periods(daily, period="28day").iloc[-1]
    assert last.total == native.loc[native.date.between(last.start, last.end), "streams"].sum() == 4246
    assert last.previous_total == 4011 and last.absolute_change == 235
    weekly = daily_periods(daily)
    complete = weekly.loc[weekly.status.eq("complete")].iloc[-1]
    assert (complete.start, complete.end, complete.total) == ("2026-10-12", "2026-10-18", 1224)
    assert complete.total == native.loc[native.date.between(complete.start, complete.end), "streams"].sum()
    assert weekly.iloc[-1].observed_days == 2 and pd.isna(weekly.iloc[-1].total)
