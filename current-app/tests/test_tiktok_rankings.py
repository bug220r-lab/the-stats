"""Rankings preserve grain, original precision, missingness and safe identity."""
import pandas as pd
import pytest

from stats_app.tiktok_rankings import (caption_key, native_number, public_post_url,
    prepare_native_rankings, prepare_snapshot_rankings, ranking_period, select_native_rankings)


def inventory():
    return pd.DataFrame([
        {"post_id": "001", "caption_raw": "Unique caption", "canonical_url": "https://www.tiktok.com/@example/video/001"},
        {"post_id": "002", "caption_raw": "Repeated", "canonical_url": "https://www.tiktok.com/@example/video/002"},
        {"post_id": "003", "caption_raw": "Repeated", "canonical_url": "https://www.tiktok.com/@example/video/003"},
        {"post_id": "004", "caption_raw": "No public link", "canonical_url": ""}])


def rankings():
    return pd.DataFrame([
        {"source_file": "followers-28.json", "window_days": "28", "ranking_metric": "new-followers", "rank": "1", "post_display": "00:58\nUnique caption", "ranking_value_raw": "14", "all_views_raw": "1.3M", "posted_on_raw": "Aug 7, 2025"},
        {"source_file": "followers-28.json", "window_days": "28", "ranking_metric": "new-followers", "rank": "2", "post_display": "Repeated", "ranking_value_raw": "14", "all_views_raw": "1.2K", "posted_on_raw": "2w ago"},
        {"source_file": "followers-28.json", "window_days": "28", "ranking_metric": "new-followers", "rank": "3", "post_display": "No public link", "ranking_value_raw": "0", "all_views_raw": "200", "posted_on_raw": "2w ago"},
        {"source_file": "views-7.json", "window_days": "7", "ranking_metric": "views", "rank": "1", "post_display": "Unique caption", "ranking_value_raw": "1.2K", "all_views_raw": "1.3M", "posted_on_raw": "Aug 7, 2025"}])


@pytest.mark.parametrize("raw,value,precision", [("0",0,"exact"),("1,181",1181,"exact"),("1.2K",1200,"rounded"),("1.3M",1300000,"rounded"),("undefined",None,"unavailable"),("NaN",None,"unavailable"),("",None,"unavailable"),("1,2",None,"unavailable"),("-2",None,"unavailable"),("inf",None,"unavailable")])
def test_native_precision(raw,value,precision):
    assert native_number(raw)==(value,precision)


def test_only_unambiguous_observed_identity_links_and_no_period_counter_replacement():
    source=rankings(); before=source.copy(deep=True)
    data=prepare_native_rankings(source, inventory())
    assert data.iloc[0].post_id=="001" and data.iloc[0].public_url.endswith("/001")
    assert data.iloc[1].post_id=="" and data.iloc[1].identity_status=="ambiguous_caption"
    assert data.iloc[2].post_id=="004" and data.iloc[2].public_url==""
    assert data.iloc[0].ranking_value_raw=="14" and data.iloc[0].all_views_raw=="1.3M"
    pd.testing.assert_frame_equal(source,before)
    selected=select_native_rankings(data,28,"new-followers","followers-28.json")
    assert selected["rank"].tolist()==["1","2","3"]
    searched=select_native_rankings(data,28,"new-followers","followers-28.json","Repeated")
    assert searched["rank"].tolist()==["2"]


@pytest.mark.parametrize("url", ["javascript:alert(1)","https://evil.example/video/001","https://www.tiktok.com.evil.example/@x/video/001","https://www.tiktok.com/@x/video/002","https://user:pass@www.tiktok.com/@x/video/001","https://www.tiktok.com:bad/@x/video/001","https://www.tiktok.com/@x/video/001?token=secret"])
def test_public_link_must_be_observed_safe_identity(url):
    assert public_post_url(url,"001")==""


def test_duration_prefix_only_not_fuzzy_caption_matching():
    assert caption_key("00:58\nUnique   caption")=="Unique caption"
    assert caption_key("Unique caption…")!="Unique caption"
    assert caption_key("00:58 Unique caption")=="00:58 Unique caption"


def test_missing_schema_and_conflicting_capture_are_explicit():
    data=prepare_native_rankings(pd.DataFrame([{"rank":"1","row_text":"old"}]),inventory())
    assert data.empty and "metric and window" in data.attrs["unavailable_reason"]
    data=prepare_native_rankings(pd.concat([rankings(),rankings().iloc[[0]]]),inventory())
    with pytest.raises(ValueError,match="repeated ranks"):
        select_native_rankings(data,28,"new-followers","followers-28.json")


def test_reporting_bounds_require_unambiguous_complete_native_window():
    panels=pd.DataFrame([{"window_days":"28","reporting_start":"2026-09-28","reporting_end":"2026-10-25"}])
    assert ranking_period(panels,28)==("2026-09-28","2026-10-25")
    assert ranking_period(panels,7) is None
    conflict=pd.concat([panels,pd.DataFrame([{"window_days":"28","reporting_start":"2026-09-27","reporting_end":"2026-10-24"}])])
    assert ranking_period(conflict,28) is None
    panels.loc[0,"reporting_end"]="2026-10-24"
    assert ranking_period(panels,28) is None


def test_cumulative_ordering_preserves_rounding_unknowns_and_zero():
    summary=pd.DataFrame([{"post_id":"001","new_followers_raw":"6.6K","views_raw":"1.3M"},{"post_id":"002","new_followers_raw":"128","views_raw":"5582"},{"post_id":"003","new_followers_raw":"undefined","views_raw":"1K"},{"post_id":"004","new_followers_raw":"0","views_raw":"0"}])
    rows=prepare_snapshot_rankings(summary,inventory())
    assert rows.post_id.tolist()==["001","002","004","003"]
    assert rows.value_precision.tolist()==["rounded","exact","exact","unavailable"]
    assert rows.ranking_value_raw.tolist()==["6.6K","128","0","undefined"]
    assert rows.iloc[-1].plot_value!=rows.iloc[-1].plot_value
    with pytest.raises(ValueError,match="one retained row"):
        prepare_snapshot_rankings(pd.concat([summary,summary.iloc[[0]]]),inventory())
