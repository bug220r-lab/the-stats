"""Build canonical imports from a preserved source archive; never fetch or edit sources.

Run from the project root after the connected archive has been downloaded to
data/connected/originals and safely extracted into data/connected/source_archive.
All generated account-specific files stay in the ignored data directory.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "data" / "connected"
SRC = BASE / "source_archive"
OUT = BASE / "archive_snapshot"
FIELDS = "platform account_id account_name entity_type entity_id entity_name metric value unit definition dimensions period_start period_end time_grain captured_at source_timezone measurement_type status source_row evidence_ref published_at source_url".split()
DEFINITIONS = {
    "streams": "Spotify streams in the reporting period.",
    "listeners": "Distinct Spotify listeners within this entity, population and reporting period; never sum across dates or entities.",
    "followers": "Spotify follower balance at the observation date; never sum balances.",
    "monthly_listeners": "Distinct Spotify listeners in the rolling 28 days ending on the observation date; never sum dates.",
    "monthly_active_listeners": "Spotify listeners who intentionally listened within the rolling 28 days; never sum dates.",
    "super_listeners": "Spotify monthly active listeners with at least 15 intentional streams in the rolling 28 days; never sum dates.",
    "playlist_adds": "Spotify playlist addition activity during the reporting period.",
    "saves": "Spotify save activity during the reporting period; not a distinct-person conversion measure.",
    "streams_per_listener": "Spotify streams divided by distinct listeners within the same entity, population and reporting period; displayed values may be rounded.",
    "canvas_views": "Spotify Canvas views during the reported period; separate from audio streams.",
}


def read_csv(relative: str):
    with (SRC / relative).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = read_csv("file_manifest.csv")
    bad = [r["path"] for r in manifest if not (SRC / r["path"]).is_file()
           or (SRC / r["path"]).stat().st_size != int(r["bytes"])
           or digest(SRC / r["path"]) != r["sha256"]]
    if bad:
        raise ValueError(f"Archive manifest failed: {bad}")
    readme = (SRC / "README.md").read_text()
    artist_id = re.search(r"Spotify artist ID: ([A-Za-z0-9]+)", readme).group(1)
    artist_name = re.search(r"Artist name as displayed: (.*?)\. Spotify", readme).group(1)
    acquisition = json.loads((BASE / "acquisition.json").read_text())
    archive_url = acquisition["archive_url"]
    captured = {}
    for file in (SRC / "captured").glob("*manifest.json"):
        obj = json.loads(file.read_text())
        for row in obj if isinstance(obj, list) else [obj]:
            if isinstance(row, dict):
                for field in ("file", "chart_file", "tables"):
                    if row.get(field) and row.get("collected_at"):
                        captured[Path(row[field]).name] = row
    songs = {r["song_id"]: r for r in read_csv("normalized/song_catalog.csv")}
    releases = {r["release_id"]: r for r in read_csv("normalized/release_metadata.csv")}
    counts = {}
    staged = []
    excluded = []

    def observation(file, rownum, row, metric, value, start, end, *, kind="artist", entity_id=None,
                    name=None, grain="period", dimensions=None, measurement=None, status=None, source=None):
        metric = metric.replace(" ", "_")
        entity_id = entity_id or artist_id
        name = name or artist_name
        source = source or row.get("source_file") or row.get("source") or file
        meta = captured.get(Path(source).name, {})
        if measurement is None:
            measurement = ("point_in_time_count" if metric == "followers" else
                           "rolling_window_count" if metric in ("monthly_listeners", "monthly_active_listeners", "super_listeners") else
                           "distinct_audience_count" if metric == "listeners" else
                           "rate" if metric.endswith("per_listener") else "period_count")
        missing = value is None or str(value).strip() in ("", "—", "-", "–")
        if status is None:
            status = "missing" if missing else "available"
        url = row.get("source_url") or meta.get("url") or archive_url
        definition = DEFINITIONS.get(metric, "Spotify source-reported " + metric.replace("_", " ") + "; retain source population and period.")
        if kind == "track" and metric in ("streams", "listeners", "saves", "playlist_adds", "streams_per_listener"):
            definition += " Song statistics pages state audio-track-only scope."
        return dict(zip(FIELDS, [
            "spotify", artist_id, artist_name, kind, entity_id, name, metric,
            "" if missing else value, "ratio" if measurement == "rate" else "count",
            definition,
            json.dumps(dimensions or {}, ensure_ascii=False, sort_keys=True), start, end, grain,
            row.get("collected_at") or meta.get("collected_at", ""), "UTC", measurement,
            status, rownum, f"source_archive/{file}#row={rownum}; evidence={source}",
            songs.get(entity_id, {}).get("first_released", "") if kind == "track" else releases.get(entity_id, {}).get("release_date", "") if kind == "release" else "",
            url,
        ]))

    def save(name, rows):
        path = OUT / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        counts[name] = len(rows)
        staged.append({"path": str(path.relative_to(BASE)), "sha256": digest(path), "observations": len(rows)})

    # Native daily artist observations are reconciled against their normalized copy.
    native = read_csv("raw/artist_timeline_2024-01-01_2026-10-20.csv")
    daily = read_csv("normalized/artist_daily.csv")
    assert len(native) == len(daily)
    for n, d in zip(native, daily):
        assert n == d, (n, d)
    rows = []
    for i, row in enumerate(daily, 2):
        for metric, value in row.items():
            if metric == "date":
                continue
            rows.append(observation("normalized/artist_daily.csv", i, row, metric, value,
                                    row["date"], row["date"], grain="daily",
                                    source="raw/artist_timeline_2024-01-01_2026-10-20.csv"))
    save("artist_daily_canonical.csv", rows)

    rows = []
    for i, row in enumerate(read_csv("normalized/artist_period_dashboard.csv"), 2):
        for side in ("current", "previous"):
            start = row["start_date"] if side == "current" else row["previous_period_start"]
            end = row["end_date"] if side == "current" else row["previous_period_end"]
            if row["metric"] == "followers":
                start = end = row.get(side + "_snapshot_date", "")
            if not start or not end:
                excluded.append({"file": "normalized/artist_period_dashboard.csv", "row": i, "side": side, "reason": "No source reporting bounds; preserved in original source"})
                continue
            rows.append(observation("normalized/artist_period_dashboard.csv", i, row, row["metric"], row[side + "_value"], start, end,
                                    grain="daily" if row["metric"] == "followers" else "period",
                                    status="available" if row[side + "_status"] == "available" else "missing"))
    save("artist_periods_canonical.csv", rows)

    rows = []
    for i, row in enumerate(read_csv("normalized/song_daily_long.csv"), 2):
        rows.append(observation("normalized/song_daily_long.csv", i, row, row["metric"], row["value"], row["date"], row["date"],
                                kind="track", entity_id=row["song_id"], name=row["recording_label"], grain="daily"))
    save("track_daily_canonical.csv", rows)

    rows = []
    for i, row in enumerate(read_csv("normalized/song_period_canonical.csv"), 2):
        if row["capture_valid"] != "True":
            excluded.append({"file": "normalized/song_period_canonical.csv", "row": i, "reason": row["invalid_reason"]})
            continue
        for metric in ("streams", "listeners", "streams_per_listener", "playlist_adds", "saves"):
            rows.append(observation("normalized/song_period_canonical.csv", i, row, metric, row[metric], row["chart_start_date"], row["chart_end_date"],
                                    kind="track", entity_id=row["song_id"], name=row["recording_label"]))
    for i, row in enumerate(read_csv("normalized/song_catalog_periods.csv"), 2):
        rows.append(observation("normalized/song_catalog_periods.csv", i, row, "canvas_views", row["canvas_views"], row["start_date"], row["end_date"],
                                kind="track", entity_id=row["song_id"], name=row["title"]))
    save("track_periods_canonical.csv", rows)

    rows = []
    for i, row in enumerate(read_csv("normalized/release_daily_streams.csv"), 2):
        rows.append(observation("normalized/release_daily_streams.csv", i, row, "streams", row["streams"], row["date"], row["date"],
                                kind="release", entity_id=row["release_id"], name=row["release_title"], grain="daily"))
    for i, row in enumerate(read_csv("normalized/release_periods.csv"), 2):
        for metric in ("streams", "listeners", "playlist_adds", "saves", "streams_per_listener"):
            value = row["streams_per_listener_displayed"] if metric == "streams_per_listener" else row[metric]
            rows.append(observation("normalized/release_periods.csv", i, row, metric, value, row["start_date"], row["end_date"],
                                    kind="release", entity_id=row["release_id"], name=row["release_title"]))
    save("release_canonical.csv", rows)

    rows = []
    for i, row in enumerate(read_csv("normalized/artist_sources_28day.csv"), 2):
        dimensions = {k: row[k] for k in ("level", "source_category", "source_group")}
        dimensions["breakdown"] = "stream_source"
        for side in ("current", "previous"):
            rows.append(observation("normalized/artist_sources_28day.csv", i, row, row["metric"], row[side + "_value"],
                                    row["start_date"] if side == "current" else row["previous_start_date"],
                                    row["end_date"] if side == "current" else row["previous_end_date"], dimensions=dimensions,
                                    status="available" if row[side + "_status"] == "available" else "missing"))
    for file, dimension_keys, value_field in (
        ("audience_top_countries.csv", ("country",), "listeners"),
        ("audience_top_cities.csv", ("city", "country", "region"), "listeners"),
        ("audience_demographics_age.csv", ("age_range",), "listeners_from_gender_sum"),
        ("audience_demographics_gender.csv", ("gender",), "listeners"),
        ("audience_demographics_age_gender.csv", ("age_range", "gender"), "listeners"),
    ):
        relative = "normalized/" + file
        for i, row in enumerate(read_csv(relative), 2):
            dims = {k: row[k] for k in dimension_keys}
            dims["breakdown"] = file.removesuffix(".csv")
            if row.get("coverage"):
                dims["coverage"] = row["coverage"]
            rows.append(observation(relative, i, row, "listeners", row[value_field], row["period_start"], row["period_end"], dimensions=dims))
    for i, row in enumerate(read_csv("normalized/audience_segment_snapshot.csv"), 2):
        rows.append(observation("normalized/audience_segment_snapshot.csv", i, row, "listeners", row["listeners"], row["as_of_date"], row["as_of_date"],
                                kind="audience_segment", entity_id="source:" + artist_id + ":segment:" + row["segment"], name=row["segment"], grain="daily",
                                dimensions={"segment": row["segment"], "audience_window": row["audience_window"], "breakdown": "audience_segment"}, measurement="rolling_window_count"))
    save("audience_breakdowns_canonical.csv", rows)

    queue_response = json.loads((BASE / "workbook_capture/collection_queue_response.json").read_text())
    values = queue_response["structuredContent"]["values"]
    queue_header, queue_rows = values[4], values[5:]
    with (BASE / "collection_queue.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(queue_header + ["source_sheet_row", "source_recorded_review_date", "retrieved_at"])
        for i, row in enumerate(queue_rows, 6):
            writer.writerow(row + [""] * (len(queue_header) - len(row)) + [i, "2026-10-22", ""])
    daily_latest = [r for r in daily if "2026-09-23" <= r["date"] <= "2026-10-20"]
    daily_previous = [r for r in daily if "2026-08-26" <= r["date"] <= "2026-09-22"]
    reconciliation = {
        "artist_daily_rows": len(daily), "artist_daily_native_exact_normalized_match": True,
        "artist_daily_first": daily[0]["date"], "artist_daily_last": daily[-1]["date"],
        "available_history_streams": sum(int(r["streams"]) for r in daily),
        "latest_28_streams": sum(int(r["streams"]) for r in daily_latest),
        "previous_28_streams": sum(int(r["streams"]) for r in daily_previous),
        "latest_28_saves": sum(int(r["saves"]) for r in daily_latest),
        "latest_28_playlist_adds": sum(int(r["playlist adds"]) for r in daily_latest),
        "last_followers": int(daily[-1]["followers"]),
        "latest_28_unique_listeners_direct_dashboard": float(next(r["current_value"] for r in read_csv("normalized/artist_period_dashboard.csv") if r["period"] == "28day" and r["metric"] == "listeners")),
        "queue_rows": len(queue_rows), "queue_status_counts": dict(Counter(r[5] for r in queue_rows)),
    }
    dashboard = read_csv("normalized/artist_period_dashboard.csv")
    assert reconciliation["available_history_streams"] == float(next(r["current_value"] for r in dashboard if r["period"] == "full" and r["metric"] == "streams"))
    assert reconciliation["latest_28_streams"] == float(next(r["current_value"] for r in dashboard if r["period"] == "28day" and r["metric"] == "streams"))
    assert reconciliation["previous_28_streams"] == float(next(r["previous_value"] for r in dashboard if r["period"] == "28day" and r["metric"] == "streams"))
    inventory = {
        "snapshot_label": "Archived source package · Oct 20 reporting endpoint · collected Oct 22",
        "baseline_status": "unverified", "baseline_reason": "Archive explicitly records collection on Oct 22 and reporting endpoint Oct 20; no evidence establishes membership in the original Oct 20 reporting baseline. It is preserved as a separate archived source snapshot.",
        "artist_name_as_displayed": artist_name, "artist_name_status": "redacted_in_source", "artist_id": artist_id,
        "accounts": [{"platform": "spotify", "account_id": artist_id, "account_name": artist_name}],
        "platform_gaps": ["No Facebook exports or verified account handles in supplied source package", "No Instagram exports or verified account handles in supplied source package", "No TikTok account/content or TikTok for Artists exports or verified handles in supplied source package"],
        "source_archive": {"path": "originals/The_Stats_Source_Data.zip", "sha256": digest(BASE / "originals/The_Stats_Source_Data.zip"), "url": archive_url, "members": len(list(SRC.rglob("*.*"))), "listed_member_checksums_passed": len(manifest), "collected_date_as_documented": "2026-10-22", "reporting_endpoint": "2026-10-20"},
        "source_timezone": "UTC", "source_timezone_evidence": "source_archive/README.md and analysis/definitions_notes.md; workbook display timezone is not used as reporting timezone",
        "capture_timestamp_handling": "Exact retained manifest timestamps only. Other observation captured_at values remain blank; the archive documents collection date only.",
        "canonical_files": staged, "canonical_counts": counts, "excluded_from_canonical": excluded,
        "reconciliation": reconciliation,
        "retained_noncanonical": ["All 581 archive members retained unchanged", "Artist and song playlist tables retained with exact bounds unavailable", "Original source discrepancies, raw captures, native exports and calculation scripts retained", "Current workbook queue is a separate read-only capture; local application does not complete collection tasks"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (BASE / "source_inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n")
    (BASE / "reconciliation.json").write_text(json.dumps(reconciliation, indent=2) + "\n")
    print(json.dumps({"files": counts, "total_observations": sum(counts.values()), "reconciliation": reconciliation}, indent=2))


if __name__ == "__main__":
    main()
