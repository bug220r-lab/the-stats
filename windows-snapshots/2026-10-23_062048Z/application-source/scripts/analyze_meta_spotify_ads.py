"""Read-only, descriptive alignment of retained Meta paid activity and Spotify.

Dates are native calendar labels (Eastern Ads and UTC Spotify), not rebinned
timestamps. No causal estimator, lag search, significance test or missing-zero
imputation is used. All output paths are separate from the immutable package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


INPUTS = {
    "ads": "social/meta_collection/ads_history.csv",
    "coverage": "social/meta_collection/ads_export_coverage.csv",
    "tracks": "spotify/cleaned/track_daily_long.csv",
    "artist": "spotify/cleaned/artist_daily.csv",
    "recordings": "spotify/cleaned/recordings.csv",
    "releases": "spotify/cleaned/release_events.csv",
}
GROUPS = {
    "december_2023_quote": ["120201685640080452", "120201709179830452"],
    "february_2024_new_year_music": ["120203880378270452", "120203882112190452"],
    "funny_guy_april_2024": ["120206480105450452"],
    "crawl_may_2024": ["120207675294870452"],
    "album_june_2024": ["120208168782620452", "120208172507140452"],
}
EXPLICIT_SONG_HINTS = {
    "funny_guy_april_2024": "3QVtuSBGLC9fTmLfF6qP7Z",
    "crawl_may_2024": "6k07tSrPUEgdDoKZiLze3z",
}


def read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_safe(value):
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and pd.isna(value):
        return None
    if hasattr(value, "item"):
        return json_safe(value.item())
    return value


def analyze(package: Path, output: Path) -> dict:
    if output.resolve() == package.resolve() or package.resolve() in output.resolve().parents:
        raise ValueError("Output must be outside the immutable package")
    output.mkdir(parents=True, exist_ok=True)
    hashes_before = {name: sha256(package / path) for name, path in INPUTS.items()}
    frames = {name: read(package / path) for name, path in INPUTS.items()}
    ads, tracks, artist = frames["ads"], frames["tracks"], frames["artist"]
    recordings = frames["recordings"].set_index("song_id")
    assert not ads.duplicated(["ad_id", "reporting_start"]).any()
    assert set(ads["ad_id"]) == {a for group in GROUPS.values() for a in group}
    assert (ads.reporting_start == ads.reporting_end).all()
    for field in ["Amount spent (USD)", "Impressions", "Link clicks"]:
        ads[field] = pd.to_numeric(ads[field], errors="coerce")
    assert ads[["Amount spent (USD)", "Impressions"]].notna().all().all()
    ads["date"] = pd.to_datetime(ads.reporting_start)
    tracks = tracks.loc[tracks.metric == "streams"].copy()
    tracks["date"] = pd.to_datetime(tracks.date)
    tracks["value"] = pd.to_numeric(tracks.value, errors="raise")
    artist["date"] = pd.to_datetime(artist.date)
    artist["value"] = pd.to_numeric(artist.daily_streams, errors="raise")
    assert not tracks.duplicated(["song_id", "date"]).any()
    assert not artist.date.duplicated().any()
    assert (tracks.value_status == "observed").all()
    assert (artist.value_status == "observed").all()

    ad_rows, group_rows, window_rows, daily_rows = [], [], [], []
    for group_key, ids in GROUPS.items():
        group = ads.loc[ads.ad_id.isin(ids)].copy()
        positive = group.loc[group["Amount spent (USD)"] > 0]
        start, end = positive.date.min(), positive.date.max()
        span = int((end - start).days) + 1
        explicit_song = EXPLICIT_SONG_HINTS.get(group_key, "")
        for ad_id, ad in group.groupby("ad_id", sort=True):
            delivered = ad.loc[ad["Amount spent (USD)"] > 0]
            ad_rows.append({
                "group_key": group_key, "ad_account_id": ad.ad_account_id.iloc[0],
                "ad_id": ad_id, "campaign_id": ad.campaign_id.iloc[0],
                "ad_set_id": ad.ad_set_id.iloc[0], "ad_name": ad["Ad name"].iloc[0],
                "positive_spend_start": delivered.reporting_start.min(),
                "positive_spend_end": delivered.reporting_start.max(),
                "positive_ad_days": len(delivered),
                "spend_usd": round(ad["Amount spent (USD)"].sum(), 2),
                "impressions": int(ad.Impressions.sum()),
                "link_clicks_observed_sum": ad["Link clicks"].sum(min_count=1),
                "link_clicks_populated_cells": int(ad["Link clicks"].notna().sum()),
                "link_clicks_missing_cells": int(ad["Link clicks"].isna().sum()),
                "native_coverage_start": ad.reporting_start.min(),
                "native_coverage_end": ad.reporting_end.max(),
                "source_files": json.dumps(sorted(set(ad.source_file))),
                "source_hashes": json.dumps(sorted(set(ad.source_sha256))),
                "song_title_hint": explicit_song,
                "creative_post_join_status": "unavailable; title hint only",
                "destination_status": "not identified by link-click metric",
            })
        group_rows.append({
            "group_key": group_key, "ad_ids": json.dumps(ids),
            "campaign_ids": json.dumps(sorted(set(group.campaign_id))),
            "ad_names": json.dumps(sorted(set(group["Ad name"])), ensure_ascii=False),
            "positive_spend_start": start.date().isoformat(),
            "positive_spend_end": end.date().isoformat(), "calendar_days": span,
            "spend_usd": round(group["Amount spent (USD)"].sum(), 2),
            "impressions": int(group.Impressions.sum()),
            "link_clicks_observed_sum": group["Link clicks"].sum(min_count=1),
            "explicit_song_title_hint": explicit_song,
            "spotify_history_available": start >= tracks.date.min(),
        })

        windows = {
            "before": (start - pd.Timedelta(days=span), start - pd.Timedelta(days=1)),
            "during": (start, end),
            "after": (end + pd.Timedelta(days=1), end + pd.Timedelta(days=span)),
        }
        entities = [("artist", "[REDACTED] artist", "", artist)] + [
            (song_id, recordings.loc[song_id, "recording_label"],
             recordings.loc[song_id, "first_released"], rows)
            for song_id, rows in tracks.groupby("song_id", sort=True)
        ]
        for scope_id, label, released, frame in entities:
            for window_name, (ws, we) in windows.items():
                data = frame.loc[frame.date.between(ws, we)].sort_values("date")
                expected = pd.date_range(ws, we)
                complete = len(data) == len(expected) and set(data.date) == set(expected)
                release = pd.Timestamp(released) if released else None
                total = float(data.value.sum()) if complete else None
                peak = float(data.value.max()) if complete else None
                window_rows.append({
                    "group_key": group_key, "scope_id": scope_id, "recording_label": label,
                    "explicit_ad_title_match": scope_id == explicit_song,
                    "first_released": released, "window": window_name,
                    "window_start": ws.date().isoformat(), "window_end": we.date().isoformat(),
                    "expected_days": len(expected), "observed_days": len(data),
                    "complete": complete, "streams": total,
                    "mean_daily_streams": total / len(expected) if complete else None,
                    "prerelease_days": int(sum(d < release for d in expected)) if release is not None else None,
                    "peak_day_streams": peak,
                    "peak_date": data.loc[data.value.idxmax(), "date"].date().isoformat() if complete else "",
                    "peak_share_pct": 100 * peak / total if complete and total else None,
                    "date_alignment": "Ads Eastern labels vs Spotify UTC labels; not rebinned",
                    "interpretation": "descriptive co-occurrence only; release and other activity uncontrolled",
                })
                for _, row in data.iterrows():
                    daily_rows.append({"group_key": group_key, "scope_id": scope_id,
                                       "recording_label": label, "window": window_name,
                                       "date": row.date.date().isoformat(), "streams": row.value,
                                       "source_file": row.source_file, "source_row": row.source_row})

    # Fixed seven-day, fully post-release comparison avoids Crawl's pre-release
    # zero in the full eight-day pre-period. It is not a lag or window search.
    crawl = tracks.loc[tracks.song_id == EXPLICIT_SONG_HINTS["crawl_may_2024"]]
    sensitivity_rows = []
    for name, start, end in [
        ("release_week_before_ads", "2024-05-10", "2024-05-16"),
        ("first_seven_paid_days", "2024-05-17", "2024-05-23"),
        ("first_seven_after_paid", "2024-05-25", "2024-05-31"),
    ]:
        rows = crawl.loc[crawl.date.between(start, end)]
        assert len(rows) == 7 and rows.date.nunique() == 7
        sensitivity_rows.append({"window": name, "start": start, "end": end,
                                 "streams": float(rows.value.sum()), "observed_days": 7,
                                 "confounder": "Single release May10; album release May31; all native UTC labels"})

    tables = {
        "ads_by_id.csv": pd.DataFrame(ad_rows),
        "paid_activity_groups.csv": pd.DataFrame(group_rows),
        "spotify_adjacent_windows.csv": pd.DataFrame(window_rows),
        "spotify_window_daily_evidence.csv": pd.DataFrame(daily_rows),
        "crawl_release_aware_windows.csv": pd.DataFrame(sensitivity_rows),
    }
    for name, frame in tables.items():
        frame.to_csv(output / name, index=False)
    hashes_after = {name: sha256(package / path) for name, path in INPUTS.items()}
    assert hashes_before == hashes_after
    result = {
        "status": "passed", "method": "Fixed adjacent equal-duration descriptive windows around observed positive ad delivery; all 14 catalog recordings retained",
        "inputs": {name: {"path": path, "sha256": hashes_before[name]} for name, path in INPUTS.items()},
        "outputs": {name: {"rows": len(frame), "sha256": sha256(output / name)} for name, frame in tables.items()},
        "input_hashes_unchanged": True, "paid_rows": len(ads),
        "spend_usd": round(ads["Amount spent (USD)"].sum(), 2),
        "impressions": int(ads.Impressions.sum()),
        "known_link_clicks": int(ads["Link clicks"].sum(min_count=1)),
        "inference": "No p-values, significance tests, causal effects, ROI or conversion rates estimated",
        "cautions": [
            "Paid maximum actually covers Sep23,2023-Jul9,2024; later report has only one ad",
            "No-data 2026 export is not evidence of complete zero spend",
            "Spotify daily history begins Jan1,2024; December2023 effects are unevaluable",
            "Ad names supply hints, not verified creative/post or Spotify destination identity",
            "Release timing, performance/show events, playlist activity and paid targeting are uncontrolled",
            "Only streams are summed; no daily unique audience, reach, ratio or campaign/ad-level double counting",
            "Original October20 archive baseline membership remains unverified",
        ],
    }
    (output / "analysis_manifest.json").write_text(json.dumps(json_safe(result), indent=2, ensure_ascii=False), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(json_safe(analyze(args.package, args.output)), indent=2, ensure_ascii=False))
