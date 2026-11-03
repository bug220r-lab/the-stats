"""Independently audit final Meta collection tables against retained raw evidence.

Read-only for raw sources and SQLite snapshots. The optional report is a new file
outside normalized/, so its manifest remains immutable. No association tests.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stats_app.analysis_repository import AnalysisRepository


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        records = list(csv.reader(handle))
    require(bool(records) and bool(records[0]), f"Empty CSV: {path}")
    header = records[0]
    require(len(header) == len(set(header)) and all(header), f"Duplicate/empty header: {path}")
    require(all(len(row) == len(header) for row in records[1:]), f"Ragged normalized CSV: {path}")
    return [dict(zip(header, row)) for row in records[1:]]


def native_records(path, expected_header):
    raw = path if isinstance(path, bytes) else Path(path).read_bytes()
    source_label = "retained source bytes" if isinstance(path, bytes) else str(path)
    text = raw.decode("utf-16") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("utf-8-sig")
    records = list(csv.reader(io.StringIO(text, newline="")))
    index = next(i for i, row in enumerate(records) if all(col in row for col in expected_header))
    header = records[index]
    result = {}
    for no, row in enumerate(records[index + 1:], index + 2):
        if not row or not any(row) or row == ["No data available."]:
            continue
        require(len(row) == len(header), f"Ragged source CSV: {source_label}:{no}")
        result[no] = dict(zip(header, row))
    return result


def utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0, "Timestamp is not explicit UTC")
    return parsed


def story_overview(text):
    """Parse the retained AX table independently of structured collector records."""
    labels = ["Views", "Reach", "Interactions", "Link clicks", "Sticker taps", "Instagram follows"]
    values = re.findall(r"^\s*\d+ text (.+)$", text, re.M)
    for i in range(len(values) - len(labels)):
        if values[i:i + len(labels)] == labels:
            row = values[i + len(labels)].split()
            require(len(row) == len(labels), "Story overview values do not match six observed labels")
            return dict(zip(["views", "reach", "interactions", "link_clicks", "sticker_taps", "follows"], row))
    raise ValueError("Story overview six-label table absent from retained evidence")


def sql_summary(rows):
    """Independent SQL grain/coverage queries; no metric attribution or tests."""
    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE TABLE ads(source TEXT, account TEXT, ad TEXT, day TEXT, ending TEXT, spend TEXT, impressions TEXT, clicks TEXT)")
        conn.executemany("INSERT INTO ads VALUES(?,?,?,?,?,?,?,?)", [(r["source_file"], r["ad_account_id"], r["ad_id"], r["reporting_start"], r["reporting_end"], r.get("Amount spent (USD)", ""), r.get("Impressions", ""), r.get("Link clicks", "")) for r in rows])
        duplicates = conn.execute("SELECT source,account,ad,day,ending,COUNT(*) FROM ads GROUP BY source,account,ad,day,ending HAVING COUNT(*)>1").fetchall()
        require(not duplicates, "Duplicate source/account/ad/date grain in normalized Ads")
        overlap = conn.execute("SELECT account,ad,day,COUNT(DISTINCT source) FROM ads GROUP BY account,ad,day HAVING COUNT(DISTINCT source)>1").fetchall()
        require(not overlap, "Overlapping ad-day exports require an explicit selection rule")
        return [dict(zip(["source_file", "rows", "ad_ids", "start", "end", "observed_spend_rows", "observed_impression_rows", "observed_click_rows"], row)) for row in conn.execute("SELECT source,COUNT(*),COUNT(DISTINCT ad),MIN(day),MAX(ending),SUM(spend<>''),SUM(impressions<>''),SUM(clicks<>'') FROM ads GROUP BY source ORDER BY source")]


def audit(collection, normalized, require_targets=False):
    root, folder = Path(collection).resolve(), Path(normalized).resolve()
    validation = json.loads((folder / "validation_report.json").read_text(encoding="utf-8"))
    manifest = json.loads((folder / "output_manifest.json").read_text(encoding="utf-8"))
    require(set(manifest) == {p.name for p in folder.iterdir() if p.is_file()} - {"output_manifest.json"}, "Normalized manifest membership differs")
    for name, expected in manifest.items():
        require(digest(folder / name) == expected, "Normalized manifest hash mismatch: " + name)
    input_hashes = validation["input_files_sha256"]
    for name, expected in input_hashes.items():
        path = (root / name).resolve()
        require(path.is_relative_to(root), "Unsafe input path")
        require(digest(path) == expected, "Raw input changed: " + name)
    tables = {p.stem: strict_csv(p) for p in folder.glob("*.csv")}
    require({name: len(rows) for name, rows in tables.items()} == validation["table_rows"], "Normalized row counts differ from validation report")
    repo = AnalysisRepository(validation["source_database"])
    original_db_hash = digest(repo.db_path)
    require(original_db_hash == validation["source_database_sha256_before"] == validation["source_database_sha256_after"], "Predecessor DB changed")
    catalog = {r["path"]: r for r in repo.file_catalog().to_dict(orient="records")}
    for path, expected in validation["predecessor_asset_hashes"].items():
        require(hashlib.sha256(repo.original_bytes(path)).hexdigest() == expected, "Predecessor asset changed: " + path)
    # Every explicit source/evidence hash, ID and timestamp survives normalization.
    provenance_rows = 0
    for name, rows in tables.items():
        for row in rows:
            for column in ["captured_at_utc", "acquired_at_utc"]:
                if row.get(column):
                    utc(row[column])
            for file_col, hash_col in [("source_file", "source_sha256"), ("evidence_ref", "evidence_sha256")]:
                source, expected = row.get(file_col, ""), row.get(hash_col, "")
                if not source or not expected:
                    continue
                actual = catalog[source]["sha256"] if source in catalog else input_hashes.get(source)
                require(actual == expected, f"Missing/mismatched source lineage: {name}:{source}")
                provenance_rows += 1
            for col in ["post_id", "ad_id", "ad_account_id", "campaign_id", "ad_set_id", "selected_account_id"]:
                if row.get(col):
                    require(row[col].isdigit(), f"Identifier changed or is not exact text: {name}:{col}")

    # Native Ads cells are compared as exact strings, including blank clicks.
    ads = tables["ads_history"]
    ads_all = ads + tables["ads_campaigns"]
    ad_sources = {r["source_file"] for r in ads_all}
    for source in ad_sources:
        raw = native_records(root / source, ["Reporting starts", "Reporting ends"])
        saved = [r for r in ads_all if r["source_file"] == source]
        require(len(saved) == len(raw), "Ads source row count differs: " + source)
        for row in saved:
            original = raw[int(row["source_record"])]
            require(all(row[key] == value for key, value in original.items()), "Native Ads cell changed")
            require(row["reporting_start"] == original["Reporting starts"] and row["reporting_end"] == original["Reporting ends"], "Ads dates relabelled")
            statuses = json.loads(row["metric_value_status_json"])
            for key, status in statuses.items():
                require(not (original[key] == "" and status in {"observed", "observed_zero"}), "Blank Ads cell became observed")
    for report in tables["ads_export_coverage"]:
        require(int(report["rows"]) == len(native_records(root / report["file"], ["Reporting starts", "Reporting ends"])), "Ads export coverage row count wrong")
        if report["export_status"] == "native_no_data_available_notice":
            require(report["spend_total_native_rows"] == "" and report["file"] not in ad_sources, "Empty report became zero spend")
    ads_query = sql_summary(ads)

    # Resolved Follows dates are inherited or refer to explicit daily raw probes.
    prior_daily = repo.table("social/account_daily.csv", raw=True).to_dict(orient="records")
    prior_follows = {r["date"]: r for r in prior_daily if r["platform_selected"] == "Instagram" and r["metric"] == "follows"}
    resolved = tables["follows_daily_resolved"]
    partial = tables["follows_daily_partial"]
    require(len({r["date"] for r in resolved + partial}) == len(resolved + partial) == len(prior_follows), "Resolved Follows date grain changed")
    evidence_rows = tables["instagram_follows"]
    repairs = [r for r in resolved if r["source_kind"] == "verified_daily_repair"]
    for row in resolved + partial:
        old = prior_follows[row["date"]]
        require(row["predecessor_asset_sha256"] == catalog["social/account_daily.csv"]["sha256"], "Follows predecessor lineage mismatch")
        if old["value"] != "":
            require(Decimal(row["value"]) == Decimal(old["value"]), "Inherited Follows value changed")
            inherited_raw = native_records(repo.original_bytes(row["predecessor_raw_file"]), ["Date", "Primary"])
            original = inherited_raw[int(Decimal(old["source_record"]))]
            require(original["Date"][:10] == row["date"] and Decimal(original["Primary"]) == Decimal(row["value"]), "Inherited Follows raw-file lineage mismatch")
        elif row["value"] != "":
            require(row["source_kind"] == "verified_daily_repair", "Missing Follows value filled without explicit repair")
            matches = [r for r in evidence_rows if r["date"] == row["date"] and r["source_file"] == row["source_file"] and r["source_record"] == row["source_record"]]
            require(len(matches) == 1 and matches[0]["value"] == row["value"] and matches[0]["reporting_timezone"] == "Pacific Time", "Follows repair does not match explicit evidence")
        else:
            require(row["resolution_status"] == "unresolved", "Unobserved Follows wrongly resolved")
    for row in evidence_rows:
        if row["source_kind"] == "native_export":
            raw = native_records(root / row["source_file"], ["Date", "Primary"])[int(row["source_record"])]
            require(row["date"] == raw["Date"][:10] and Decimal(row["value"]) == Decimal(raw["Primary"]), "Native Follows cell mismatch")
        else:
            payload = json.loads((root / row["source_file"]).read_text(encoding="utf-8-sig"))
            raw = payload[int(row["source_record"]) - 1]
            text = (root / row["evidence_ref"]).read_text(encoding="utf-8-sig")
            section = text.split("heading Follows", 1)[-1]
            require(raw["date"] == row["date"] and Decimal(str(raw["value"])) == Decimal(row["value"]), "Manual Follows JSON mismatch")
            require(row["source_url"] in text and row["date"] in text, "Follows URL/date missing from evidence")
            if row["value"] == "0":
                require(re.search(r"\btext 0\s*$", section, re.M) and "No activity during selected date range" in section, "Follows zero lacks explicit displayed evidence")

    # Story detail captures are separate lifetime snapshots, not repaired old rows.
    stories = tables["instagram_stories_manual"]
    old_ids = {r["post_id"] for r in repo.table("social/excluded_records.csv", raw=True).to_dict(orient="records")}
    require(len({r["post_id"] for r in stories}) == len(stories), "Duplicate Story detail post ID")
    require({r["post_id"] for r in stories} <= old_ids, "Story detail not one of the known quarantined IDs")
    metrics = ["views", "reach", "interactions", "link_clicks", "sticker_taps", "follows"]
    metric_counts = Counter()
    long_metrics = tables["instagram_story_metrics"]
    long_keys = {(r["post_id"], r["captured_at_utc"], r["metric"]): r for r in long_metrics}
    require(len(long_keys) == len(long_metrics) == len(stories) * len(metrics), "Story per-field grain or metric count differs")
    for row in stories:
        raw_items = json.loads((root / row["source_file"]).read_text(encoding="utf-8-sig"))
        item = raw_items[int(row["source_record"]) - 1]
        text = (root / row["evidence_ref"]).read_text(encoding="utf-8-sig")
        overview = story_overview(text)
        require(item["post_id"] == row["post_id"] and item["source_url"] in text and "content_id=" + row["post_id"] in text, "Story exact ID/source URL mismatch")
        require(row["measurement_type"] == "lifetime_content_snapshot" and row["canonical_update_applied"] == "False", "Story became period activity or canonical repair")
        require((row["reporting_timezone"] or None) == (item.get("reporting_timezone") or None), "Unknown Story timezone was invented")
        for metric in metrics:
            raw = str(item["metrics"][metric]["raw"])
            require(overview[metric] == raw == row[metric + "_raw"], "Story display differs from collected/normalized metric: " + metric)
            observed = row[metric + "_status"] in {"observed", "observed_zero"}
            long = long_keys[(row["post_id"], row["captured_at_utc"], metric)]
            require(long["value"] == row[metric] and long["value_status"] == row[metric + "_status"] and long["value_raw"] == raw, "Story per-field table disagrees with detail evidence")
            metric_counts[metric + ("_observed" if observed else "_unavailable")] += 1
            if observed:
                require(row[metric] != "" and Decimal(row[metric]) == Decimal(raw.replace(",", "")), "Observed Story numeric mismatch")
            else:
                require(row[metric] == "", "Unavailable Story field became numeric")

    # Recheck native Facebook dates/cells, with no rewriting of the original series.
    facebook = tables.get("facebook_daily_recheck", [])
    fb_counts = {}
    for source in {r["source_file"] for r in facebook}:
        raw = native_records(root / source, ["Date", "Primary"])
        saved = [r for r in facebook if r["source_file"] == source]
        require(len(saved) == len(raw), "Facebook native daily coverage changed")
        for row in saved:
            original = raw[int(row["source_record"])]
            require(row["date"] == original["Date"][:10] and row["value"] == original["Primary"], "Facebook native cell changed")
            old = next(r for r in prior_daily if r["platform_selected"] == "Facebook" and r["metric"] == row["metric"] and r["date"] == row["date"])
            require(row["comparison_status"] == "matches_prior_observation" and Decimal(row["value"]) == Decimal(old["value"]), "Facebook recheck changed prior evidence")
        fb_counts[saved[0]["metric"]] = dict(rows=len(saved), known_total=str(sum(Decimal(r["value"]) for r in saved)), explicit_zero_dates=sum(r["value"] == "0" for r in saved))

    if require_targets:
        require(len(resolved) == 293 and resolved[0]["date"] == "2026-01-01" and resolved[-1]["date"] == "2026-10-20" and all(r["value"] != "" for r in resolved), "Complete Jan1-Oct20 Follows repair target not met")
        require(len(old_ids) == 183 and {r["post_id"] for r in stories} == old_ids, "All 183 Story IDs have not been captured")
    require(digest(repo.db_path) == original_db_hash, "Predecessor DB changed during audit")
    require(all(digest(root / name) == expected for name, expected in input_hashes.items()), "Raw source changed during audit")
    return dict(status="passed", generated_at_utc=datetime.now(timezone.utc).isoformat(), require_collection_targets=require_targets,
                normalized_tables=len(tables), table_rows={k: len(v) for k, v in tables.items()}, input_hashes_verified=len(input_hashes), provenance_references_verified=provenance_rows,
                predecessor_database_sha256=original_db_hash, ads_sql_coverage=ads_query,
                follows=dict(complete_dates=len(resolved), observed_complete_dates=sum(r["value"] != "" for r in resolved), repaired_dates=len(repairs), partial_dates=len(partial), unresolved_partial_dates=sum(r["value"] == "" for r in partial)),
                stories=dict(captured_ids=len(stories), original_quarantined_ids=len(old_ids), metric_status_counts=dict(metric_counts), old_quarantine_unchanged=True), facebook=fb_counts,
                limitations=["Audit validates preservation and faithful normalization, not platform truth or marketing causation.", "Story captures recover individual lifetime metric fields; the original malformed rows remain quarantined.", "Follows resolved daily table is a new evidence view; inherited canonical assets remain unchanged."])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", required=True, type=Path)
    parser.add_argument("--normalized", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--require-collection-targets", action="store_true")
    args = parser.parse_args()
    result = audit(args.collection, args.normalized, args.require_collection_targets)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        require(not args.report.exists(), "Audit report already exists; choose a new path")
        require(not args.report.resolve().is_relative_to(args.normalized.resolve()), "Do not mutate the normalized output manifest")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    print(encoded)
