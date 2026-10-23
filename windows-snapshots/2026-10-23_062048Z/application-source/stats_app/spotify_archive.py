"""Append preserved Spotify evidence to a COPY of the recovered handoff database.

Original snapshots and source bytes are immutable inputs. Reporting-window labels
never establish original baseline membership. Unknown bounds stay SQL NULL.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

from stats_app.retained_store import Store

VERSION = 1
ARTIST = "6X14XfGTmB560PF063wXDk"
ARCHIVE_URL = "https://drive.google.com/file/d/1T7ZsJq-iyR3IMoc4hQOqXnzOdTidtbJx/view"
LABELS = {
    "archive_additions": "Spotify archive additions · Oct 20 endpoint · baseline unverified",
    "historical_supplement": "Spotify historical-window supplement · Oct 20 endpoint · baseline unverified",
    "newer_supplement": "Spotify newer capture · Oct 21 endpoint or bounds unavailable",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value):
    if value is None or str(value).strip() in ("", "-", "—", "–", "�"):
        return None
    result = float(str(value).replace(",", ""))
    if not __import__("math").isfinite(result):
        raise ValueError("Nonfinite source value")
    return result


def timestamp(value):
    if not value:
        return None
    value = value.replace(" (UTC date only)", "")
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def observation(path, index, row, metric, value, *, start=None, end=None,
                kind="artist", entity_id=ARTIST, name="[REDACTED]", dims=None,
                grain="period", measurement=None, captured=None, status=None,
                evidence=None, source_url=None, definition=None, unit=None):
    parsed = number(value)
    for bound in (start, end):
        if bound:
            date.fromisoformat(bound)
    if bool(start) != bool(end) or (start and start > end):
        raise ValueError("Invalid reporting window")
    measurement = measurement or ("rate" if "per_listener" in metric or "pct" in metric else
                                   "distinct_audience_count" if "listeners" in metric else "period_count")
    return dict(platform="spotify", account_id=ARTIST, account_name="[REDACTED]",
                entity_type=kind, entity_id=entity_id, entity_name=name, metric=metric,
                value=parsed, unit=unit or ("percent" if "pct" in metric else "ratio" if measurement == "rate" else "count"),
                definition=definition or f"Spotify source-reported {metric.replace('_', ' ')}; retain source population, measurement type and bounds.",
                dimensions=dims or {}, period_start=start or None, period_end=end or None,
                time_grain=grain if start else "unknown", captured_at=timestamp(captured or row.get("collected_at") or row.get("observed_at")),
                source_timezone="UTC", measurement_type=measurement,
                status=status or ("missing" if parsed is None else "available"), source_row=index,
                evidence_ref=f"{path.as_posix()}#row={index}; evidence={evidence or row.get('source') or row.get('evidence_file') or ''}",
                published_at=row.get("first_released") or row.get("release_date") or None,
                source_url=source_url or row.get("source_url") or ARCHIVE_URL)


def source_dims(category, level=None):
    return {"breakdown": "stream_source", "source_category": category,
            "hierarchy_level": level or ("aggregate" if category.startswith("All ") else "detail"),
            "scope": "Source populations overlap; aggregate rows include their detailed children"}


def build_import_plan(recovery_root, supplement_zip=None):
    """Read retained files only; return explicit records plus a complete coverage ledger.

    supplement_zip, when supplied, verifies the retained ZIP bytes against this
    recovery's ZIP. Extraction is deliberately not implicit in this importer.
    """
    recovery = Path(recovery_root).resolve()
    archive = recovery / "data/connected/source_archive"
    supplement = recovery / "data/collection_attempts/2026-10-22/drive/supplement/The_Stats_Collection_Supplement_2026-10-22"
    if supplement_zip and sha(supplement_zip) != sha(supplement.parent.parent / "The_Stats_Collection_Supplement_2026-10-22.zip"):
        raise ValueError("Supplement differs from retained recovery; stage and review separately.")
    plans = {key: {"key": key, "label": label, "files": []} for key, label in LABELS.items()}
    coverage = []
    used = set()

    def add(key, path, records, note):
        records = list(records)
        plans[key]["files"].append({"path": path, "sha256": sha(path), "records": records,
                                    "issues": [{"severity": "warning", "code": "source_scope", "message": note}]})
        used.add(path)
        coverage.append({"snapshot": key, "file": path.relative_to(recovery).as_posix(),
                         "source_rows": len(rows(path)), "observations": len(records),
                         "status": "imported source observations", "note": note, "sha256": sha(path)})

    norm = archive / "normalized"
    # Independent recording geography. City and country series never share scope.
    for filename, daily in [("song_locations.csv", False), ("song_location_country_comparison_daily.csv", True)]:
        path = norm / filename; result = []
        for i, r in enumerate(rows(path), 2):
            dims = {k: r[k] for k in ("location_type", "country", "city", "region", "coverage", "scope") if r.get(k)}
            dims["breakdown"] = "selected_country_comparison" if daily else "recording_geography"
            result.append(observation(path, i, r, "streams", r["streams"],
                          start=r["date"] if daily else r["period_start"], end=r["date"] if daily else r["period_end"],
                          kind="track", entity_id=r["song_id"], name=r["recording_label"], dims=dims,
                          grain="daily" if daily else "period"))
        add("archive_additions", path, result, "Top/default selected locations only; country and city populations are separate; coverage is not exhaustive.")

    path = norm / "audience_segment_daily.csv"; result = []
    for i, r in enumerate(rows(path), 2):
        for metric in ("total_audience", "monthly_active_listeners", "previously_active", "programmed", "super_listeners", "moderate_listeners", "light_listeners"):
            result.append(observation(path, i, r, metric, r[metric], start=r["date"], end=r["date"],
                          dims={"breakdown": "audience_segment_history", "scope": "Source-defined rolling audience stock; totals and components overlap"},
                          grain="daily", measurement="rolling_window_count"))
    add("archive_additions", path, result, "Rolling audience balances, not new listeners; never sum across dates or overlapping segment totals.")

    for filename, metrics in [("audience_development.csv", ["listeners"]),
                              ("audience_active_subsegments.csv", ["listeners", "share_pct_displayed", "streams_per_listener_displayed"]),
                              ("audience_top_countries.csv", ["active_listeners"])]:
        path = norm / filename; result = []
        for i, r in enumerate(rows(path), 2):
            dims = {k: r[k] for k in ("geography", "segment", "country", "coverage", "metric") if r.get(k)}
            dims["breakdown"] = filename.removesuffix(".csv")
            for metric in metrics:
                extra = {"precision": "rounded displayed"} if "displayed" in metric else {}
                result.append(observation(path, i, r, metric, r[metric], start=r["period_start"], end=r["period_end"], dims={**dims, **extra}))
        add("archive_additions", path, result, "Source-specific distinct populations; displayed ratios/percentages are rounded; missing counts remain missing.")

    # Cumulative engagement is preserved as cumulative, never daily activity.
    release_id = "0FZy84bsG7mJls6CXtx2HX"
    for filename, metrics in [("release_engagement_daily.csv", ["cumulative_engaged_listeners"]),
                              ("release_engagement_snapshot.csv", ["engaged_listeners", "cohort_listeners", "engagement_pct_displayed"])]:
        path = norm / filename; result = []
        for i, r in enumerate(rows(path), 2):
            dims = {k: r[k] for k in ("cohort_date", "geography", "audience_segment", "source_filter", "cohort_listeners")}
            dims["breakdown"] = "release_engagement"
            dims["conflict_note"] = "Segment totals and artist timeline cohort baselines disagree; preserve source values."
            for metric in metrics:
                measurement = "cumulative_count" if metric == "cumulative_engaged_listeners" else "point_in_time_count" if metric == "cohort_listeners" else "rate" if "pct" in metric else "distinct_audience_count"
                result.append(observation(path, i, r, metric, r[metric], start=r["cohort_date"] if metric == "cohort_listeners" else r["release_date"],
                              end=r["cohort_date"] if metric == "cohort_listeners" else r.get("date", r.get("period_end")),
                              kind="release", entity_id=release_id, name=r["release"], dims={**dims, **({"precision": "rounded displayed"} if "pct" in metric else {})},
                              grain="cumulative" if metric == "cumulative_engaged_listeners" else "period", measurement=measurement))
        add("archive_additions", path, result, "Only The Cut; overlapping segment/source cohorts, cumulative curves and source disagreements; no additive daily aggregation.")

    path = norm / "song_source_comparisons.csv"; result = []
    for i, r in enumerate(rows(path), 2):
        # Bounds confirmed by the retained original coverage manifest and capture text.
        if r["displayed_period"] != "Sep 23, 2026 - Oct 20, 2026":
            raise ValueError("Unexpected recording source reporting bounds")
        for side, start, end in [("current", "2026-09-23", "2026-10-20"), ("previous", "2026-08-26", "2026-09-22")]:
            result.append(observation(path, i, r, r["metric"], r[side], start=start, end=end,
                          kind="track", entity_id=r["song_id"], name=r["recording_label"], dims=source_dims(r["stream_source"])))
    add("archive_additions", path, result, "The Cut source comparisons only; current/prior windows and hierarchy retained; source audiences overlap.")

    # Unknown reporting bounds are valid evidence, but never period-aligned KPIs.
    for filename, metrics in [("artist_playlists.csv", ["streams", "listeners"]), ("song_playlists.csv", ["streams"])]:
        path = norm / filename; result = []
        for i, r in enumerate(rows(path), 2):
            dims = {k: r[k] for k in ("period_label", "playlist_title", "playlist_url", "playlist_uri", "category", "author_displayed", "made_by", "date_added", "coverage") if r.get(k)}
            dims.update(breakdown="playlist_evidence", bounds_status="not_exposed", coverage="Top/displayed playlist rows only; not exhaustive")
            for metric in metrics:
                result.append(observation(path, i, r, metric, r[metric], kind="track" if "song_id" in r else "artist",
                              entity_id=r.get("song_id", ARTIST), name=r.get("song_title", "[REDACTED]"), dims=dims))
        add("archive_additions", path, result, "Evidence only: exact bounds not exposed. Keep selected-period labels; never infer calendar bounds or sum playlist listeners.")

    for filename, field, kind in [("song_alltime_counters.csv", "all_time_streams", "track"), ("release_metadata.csv", "all_time_streams_displayed", "release")]:
        path = norm / filename; result = []
        for i, r in enumerate(rows(path), 2):
            result.append(observation(path, i, r, "streams", r[field], kind=kind,
                          entity_id=r.get("song_id", r.get("release_id")), name=r.get("recording_label", r.get("release_title")),
                          dims={"breakdown": "lifetime_counter", "measurement_cutoff": "unknown", "source_conflict_status": r.get("all_time_comparison_status", "not_reconciled")},
                          measurement="lifetime_count"))
        add("archive_additions", path, result, "Lifetime display with unknown measurement cutoff, separate from available-history activity; source discrepancies retained.")

    path = norm / "content_feature_status.csv"; result = []
    for i, r in enumerate(rows(path), 2):
        # Numeric exact UI cells and missing feature evidence stay distinct.
        try:
            value = number(r["value"])
        except ValueError:
            continue
        dims = {k: r[k] for k in ("feature", "entity", "ui_status", "date_scope", "note", "value_status")}
        result.append(observation(path, i, r, r["metric"], value, dims={"breakdown": "feature_evidence", **dims},
                      measurement="point_in_time_count", status="available" if value is not None else "unavailable", unit=r["unit"]))
    add("archive_additions", path, result, "Specific UI list observations only. Empty campaign lists do not establish zero spend/ROI; unavailable features remain unavailable.")

    def basis(r):
        return "historical_supplement" if r["Reporting basis"] == "baseline supplement" else "newer_supplement"

    path = supplement / "normalized/recovered_source_periods.csv"
    grouped = {key: [] for key in LABELS if key != "archive_additions"}
    for i, r in enumerate(rows(path), 2):
        for side, start_key, end_key in [("Current value", "Period start", "Period end"), ("Previous value", "Previous start", "Previous end")]:
            grouped[basis(r)].append(observation(path, i, r, r["Metric"], r[side], start=r[start_key], end=r[end_key],
                         kind="artist" if r["Scope"] == "artist" else "track", entity_id=r["Spotify ID"], name=r["Recording"],
                         dims=source_dims(r["Source"], r["Hierarchy level"]), captured=r["Collected UTC"], evidence=r["Evidence"], source_url=r["Source URL"]))
    for key, result in grouped.items():
        add(key, path, result, "Exact source-period values; dashboard dashes remain missing, not inferred chart zeros. Historical labels do not verify baseline membership.")

    path = supplement / "normalized/source_daily_supplement.csv"; source_rows = rows(path)
    source_columns = list(source_rows[0])[7:16]
    grouped = {key: [] for key in grouped}
    for i, r in enumerate(source_rows, 2):
        for category in source_columns:
            grouped[basis(r)].append(observation(path, i, r, r["Metric"], r[category], start=r["Date"], end=r["Date"],
                         kind="track", entity_id=r["Spotify ID"], name=r["Recording"], dims=source_dims(category), grain="daily",
                         captured=r["Collected UTC"], evidence=r["Evidence"] + "; source_window=" + r["Window start"] + "/" + r["Window end"],
                         source_url=f"https://artists.spotify.com/c/artist/{ARTIST}/song/{r['Spotify ID']}/stats"))
    for key, result in grouped.items():
        add(key, path, result, "Overlapping daily window captures attach duplicate references. Distinct daily listeners and ratios are never additive; source aggregates overlap children.")

    path = supplement / "normalized/recovered_artist_metrics.csv"; result = []
    for i, r in enumerate(rows(path), 2):
        result.append(observation(path, i, r, "listeners", r["Value"], start=r["Period start"], end=r["Period end"],
                      dims={"population": r["Population"], "method": r["Method"]}, captured=r["Collected UTC"], evidence=r["Evidence"], source_url=r["Source URL"]))
    add("historical_supplement", path, result, "Direct period-unique 3,077 listeners Jan1–Oct20 2025, manually transcribed; capture UTC date known, time unknown; not original-baseline evidence.")

    path = supplement / "normalized/resume_snapshots.csv"; result = []
    for i, r in enumerate(rows(path), 2):
        dims = {"breakdown": r["Dataset"], "dimension": r["Dimension"], "selected_period": r["Selected period"], "coverage": r["Coverage note"]}
        if not r["Period start"]:
            dims["bounds_status"] = "not_exposed"
        for key in ("Creator", "Date added"):
            if r[key]: dims[key.lower().replace(" ", "_")] = r[key]
        result.append(observation(path, i, r, r["Metric"], r["Value"], start=r["Period start"], end=r["Period end"],
                      kind="track", entity_id=r["Spotify ID"], name=r["Recording"], dims=dims,
                      captured=r["Collected UTC"], evidence=r["Evidence"], source_url=r["Source URL"]))
    add("newer_supplement", path, result, "60 bounded John Doe geography readings; 62 playlist/catalog readings with unknown bounds excluded from aligned KPIs; two Canvas dashes remain missing.")

    already = {"artist_daily.csv", "artist_period_dashboard.csv", "song_daily_long.csv", "song_period_canonical.csv", "song_catalog_periods.csv", "release_daily_streams.csv", "release_periods.csv", "artist_sources_28day.csv", "audience_top_countries.csv", "audience_top_cities.csv", "audience_demographics_age.csv", "audience_demographics_gender.csv", "audience_demographics_age_gender.csv", "audience_segment_snapshot.csv"}
    for root in (norm, supplement / "normalized"):
        for path in sorted(root.glob("*.csv")):
            if path in used: continue
            note = "Already represented in unchanged archived snapshot 1." if path.name in already else "Retained source evidence/metadata, derived analysis or QA; not counted again as independent activity."
            if path.name in {"canvas_card_inventory.csv", "song_canvas_status.csv"}:
                note = "UI asset/card evidence only; no publication/performance claim. Full original rows retained."
            if path.name == "collection_log.csv":
                note = "Newer collection queue evidence retained separately; original historical queue remains unchanged."
            coverage.append({"snapshot": "retained evidence", "file": path.relative_to(recovery).as_posix(), "source_rows": len(rows(path)),
                             "observations": 0, "status": "retained evidence", "note": note, "sha256": sha(path)})
    gaps = ["Original October 20 baseline membership remains unverified.",
            "Artist available history starts Jan 1, 2024; not lifetime.",
            "GOOMH daily history: 365 stream days, other four metrics missing; Son streams: 730 days. Later unsaved browser readings are not imported.",
            "Recording geography: original 7 of 14 available; supplement adds John Doe newer geography. Top/default selected locations are not exhaustive.",
            "Playlist exact bounds and newer catalog exact bounds remain unavailable; excluded from period-aligned totals.",
            "Demographic, release lifetime/history and release cohort disagreements remain unresolved source evidence.",
            "Spotify source aggregates overlap children. Listeners overlap populations and dates; never sum daily unique audiences.",
            "No new native CSV exports or missing full song histories were acquired in the supplement.",
            "TikTok deferred by user; Instagram Stories export remains unavailable; no fabricated zeros."]
    return {"recovery_root": recovery, "plans": list(plans.values()), "coverage": coverage, "gaps": gaps}


def original_audit(database):
    """Stable full-row hashes for original snapshots and every supporting table."""
    with sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True) as db:
        queries = {
            "snapshots": "SELECT * FROM snapshots WHERE id IN (1,2) ORDER BY id",
            "imports": "SELECT * FROM imports WHERE snapshot_id IN (1,2) ORDER BY id",
            "observations": "SELECT * FROM observations WHERE snapshot_id IN (1,2) ORDER BY id",
            "observation_sources": "SELECT * FROM observation_sources WHERE import_id IN (SELECT id FROM imports WHERE snapshot_id IN (1,2)) ORDER BY id",
            "validation_issues": "SELECT * FROM validation_issues WHERE import_id IN (SELECT id FROM imports WHERE snapshot_id IN (1,2)) ORDER BY id",
            **{t: f"SELECT * FROM {t} ORDER BY 1" for t in ("mappings", "annotations", "collection_queue", "schema_migrations")},
        }
        result = {}
        for key, query in queries.items():
            digest = hashlib.sha256(); count = 0
            for row in db.execute(query):
                digest.update(json.dumps(list(row), ensure_ascii=False, separators=(",", ":")).encode()); count += 1
            result[key] = {"rows": count, "sha256": digest.hexdigest()}
        return result


def stage_import(recovery_root, staging_dir, supplement_zip=None):
    plan = build_import_plan(recovery_root, supplement_zip)
    recovery = plan["recovery_root"]; staging = Path(staging_dir).resolve()
    if staging == recovery or recovery in staging.parents:
        raise ValueError("Staging must be outside recovered originals.")
    original_db = recovery / "data/stats.sqlite3"; db = staging / "data/stats.sqlite3"
    original_digest = sha(original_db); before = original_audit(original_db)
    db.parent.mkdir(parents=True, exist_ok=True)
    if not db.exists():
        with sqlite3.connect(original_db.as_uri() + "?mode=ro", uri=True) as src, sqlite3.connect(db) as dest:
            src.backup(dest)
    if original_audit(db) != before:
        raise ValueError("Existing staged database does not preserve recovered original rows.")
    source_dir = db.parent / "sources"; source_dir.mkdir(exist_ok=True)
    original_source_hashes = {}
    for path in (recovery / "data/sources").iterdir():
        if not path.is_file(): continue
        original_source_hashes[path.name] = sha(path)
        target = source_dir / path.name
        if target.exists() and sha(target) != sha(path):
            raise ValueError("Existing staged source differs from recovered original")
        if not target.exists(): shutil.copy2(path, target)
    store = Store(db); results = []; snapshot_ids = {}
    for snapshot in plan["plans"]:
        evidence = json.dumps({"kind": "retained_spotify_archive_import", "version": VERSION, "key": snapshot["key"], "baseline_status": "unverified"}, sort_keys=True)
        matches = [s for s in store.snapshots() if s["evidence"] == evidence and s["name"] == snapshot["label"]]
        sid = matches[0]["id"] if matches else store.create_snapshot(snapshot["label"], status="unverified", evidence=evidence)
        snapshot_ids[snapshot["key"]] = sid
        for item in snapshot["files"]:
            if sha(item["path"]) != item["sha256"]: raise ValueError("Source changed after planning")
            result = store.commit_import(sid, item["path"].name, item["path"].read_bytes(), item["records"],
                                        worksheet="CSV", mapping={"adapter": "spotify_archive", "version": VERSION, "snapshot_kind": snapshot["key"]}, issues=item["issues"])
            if result["rejected"] or result["revised"]:
                raise ValueError(f"Unexpected rejected/revised rows in staged import: {item['path']}")
            results.append({"snapshot_id": sid, "snapshot": snapshot["key"], "file": item["path"].name, **result})
    ledger = json.dumps({"coverage": plan["coverage"], "gaps": plan["gaps"]}, ensure_ascii=False, indent=2).encode()
    store.commit_import(snapshot_ids["archive_additions"], "spotify_coverage.json", ledger, [], worksheet="source evidence ledger", mapping={"adapter": "coverage", "version": VERSION},
                        issues=[{"severity": "warning", "code": "coverage_gap", "message": gap} for gap in plan["gaps"]])
    after = original_audit(db)
    if after != before or sha(original_db) != original_digest:
        raise AssertionError("Original snapshot preservation failed")
    if any(sha(source_dir / name) != digest for name, digest in original_source_hashes.items()):
        raise AssertionError("Original source preservation failed")
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        counts = [dict(zip(["id", "name", "active_observations"], r)) for r in conn.execute("SELECT s.id,s.name,count(o.id) FROM snapshots s LEFT JOIN observations o ON s.id=o.snapshot_id AND o.active=1 GROUP BY s.id ORDER BY s.id")]
    report = {"original_database_sha256": original_digest, "original_unchanged": True, "earlier_snapshot_rows_unchanged": before == after,
              "original_audit": before, "original_source_files_unchanged": len(original_source_hashes), "integrity": integrity,
              "snapshots": counts, "imports": results, "gaps": plan["gaps"], "database": str(db), "coverage_path": str(staging / "spotify_coverage.json")}
    (staging / "spotify_coverage.json").write_bytes(ledger)
    (staging / "spotify_import_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recovery-root", required=True, type=Path)
    parser.add_argument("--staging-dir", required=True, type=Path)
    args = parser.parse_args()
    report = stage_import(args.recovery_root, args.staging_dir)
    print(json.dumps({k: report[k] for k in ("original_unchanged", "earlier_snapshot_rows_unchanged", "integrity", "snapshots", "database")}, ensure_ascii=True, indent=2))
