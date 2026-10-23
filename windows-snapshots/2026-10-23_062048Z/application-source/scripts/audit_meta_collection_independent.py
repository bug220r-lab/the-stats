"""Second-implementation Meta acceptance audit; no producer imports or DB writes.

Reads raw browser evidence, native CSV bytes, normalized tables and immutable
SQLite assets with the standard library. Writes only the requested new report.
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
from urllib.parse import parse_qs, unquote, urlsplit


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def inside(root, relative):
    path = (root / relative).resolve()
    check(path.is_relative_to(root.resolve()), "Evidence path leaves collection: " + relative)
    return path


def csv_rows(raw):
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text, newline="")))


def table(path):
    rows = csv_rows(Path(path).read_bytes())
    check(rows and rows[0] and len(set(rows[0])) == len(rows[0]), "Invalid CSV header: " + str(path))
    check(all(len(r) == len(rows[0]) for r in rows[1:]), "Ragged CSV: " + str(path))
    return [dict(zip(rows[0], row)) for row in rows[1:]]


def native(path, headers):
    rows = csv_rows(Path(path).read_bytes())
    start = next(i for i, row in enumerate(rows) if set(headers).issubset(row))
    result = {}
    for record, row in enumerate(rows[start + 1:], start + 2):
        if not row or row == ["No data available."]:
            continue
        check(len(row) == len(rows[start]), "Ragged native input: " + str(path))
        result[record] = dict(zip(rows[start], row))
    return result


def number(raw):
    value = str(raw).strip() if raw is not None else ""
    if not value or not re.fullmatch(r"[+-]?(?:\d[\d,]*)(?:\.\d+)?", value):
        return None
    value = Decimal(value.replace(",", ""))
    check(value.is_finite(), "Nonfinite value")
    return value


def utc(stamp):
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    check(parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0, "Not explicit UTC: " + stamp)


def browser_url(text):
    found = re.search(r'URL: "(https://[^"\r\n]+)"', text)
    check(found is not None, "Missing captured browser URL")
    return found[1]


def immutable_assets(db_path):
    with sqlite3.connect(db_path.as_uri() + "?mode=ro&immutable=1", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        return {name: bytes(contents) for name, contents in conn.execute("SELECT path, contents FROM assets")}


def asset_table(assets, name):
    rows = csv_rows(assets[name])
    check(all(len(row) == len(rows[0]) for row in rows[1:]), "Bad predecessor CSV")
    return [dict(zip(rows[0], row)) for row in rows[1:]]


def preservation(root):
    preflight = read_json(root / "preflight_preservation.json")
    data_root = Path(preflight["configured_data_dir"]).resolve()
    result = []
    for row in preflight["databases"]:
        path = inside(data_root, row["relative_path"])
        check(digest(path) == row["sha256"], "Preflight database changed: " + row["relative_path"])
        result.append({"relative_path": row["relative_path"], "sha256": row["sha256"], "unchanged": True})
    registry = preflight["registry"]
    check(digest(inside(data_root, registry["relative_path"])) == registry["sha256"], "Preflight registry changed before activation")
    return result, preflight


def audit(root, normalized, package=None):
    root, normalized = root.resolve(), normalized.resolve()
    databases, preflight = preservation(root)
    report = read_json(normalized / "validation_report.json")
    source_db = Path(report["source_database"]).resolve()
    db_sha = digest(source_db)
    check(db_sha == report["source_database_sha256_before"] == report["source_database_sha256_after"], "Normalizer predecessor changed")
    assets = immutable_assets(source_db)
    old_daily = asset_table(assets, "social/account_daily.csv")
    for name, sha in report["input_files_sha256"].items():
        check(digest(inside(root, name)) == sha, "Raw input manifest mismatch: " + name)
    manifests = {}
    for folder in [normalized, root / "mapping"]:
        manifest = read_json(folder / "output_manifest.json")
        for name, sha in manifest.items():
            check(digest(inside(folder, name)) == sha, "Output manifest mismatch: " + name)
        manifests[folder.name] = len(manifest)
    normalized_tables = {p.stem: table(p) for p in normalized.glob("*.csv")}
    for name, count in report["table_rows"].items():
        check(len(normalized_tables[name]) == count, "Normalization count mismatch: " + name)

    # Read the AX Overview tree rather than the collector's structured values.
    story_rows = read_json(root / "raw/story_manual_observations.json")
    if isinstance(story_rows, dict):
        story_rows = story_rows["observations"]
    expected_stories = set(str(v) for v in read_json(root / "raw/quarantined_story_ids.json"))
    normalized_stories = normalized_tables["instagram_stories_manual"]
    by_story = {r["post_id"]: r for r in normalized_stories}
    check(len(by_story) == len(normalized_stories) == len(story_rows), "Duplicate or omitted Story identity")
    story_metrics = Counter()
    story_checked = 0
    names = {"Views": "views", "Reach": "reach", "Interactions": "interactions", "Link clicks": "link_clicks", "Sticker taps": "sticker_taps", "Instagram follows": "follows"}
    for observation in story_rows:
        post_id = observation["post_id"]
        check(isinstance(post_id, str) and post_id.isdecimal() and post_id in expected_stories, "Unexpected/nonstring Story ID")
        evidence = inside(root, observation["evidence_ref"]).read_text(encoding="utf-8-sig")
        url = browser_url(evidence)
        params = parse_qs(urlsplit(url).query)
        check(params.get("content_id") == [post_id] and params.get("asset_id") == ["118246571240106"], "Story URL identity mismatch")
        check(re.search(r"\bimage Instagram(?:\s|$)", evidence), "Story selected platform absent")
        utc(observation["captured_at_utc"])
        lines = evidence.splitlines()
        overview = next(i for i, line in enumerate(lines) if re.search(r"\bheading Overview,", line))
        readings = []
        for line in lines[overview + 1:]:
            node = re.search(r"^\s*\d+ text (.*)$", line)
            if node:
                readings.append(node[1])
            if len(readings) == 8:
                break
        check(readings[0] == "Overview" and readings[1:7] == list(names), "Story Overview label order changed")
        values = readings[7].split()
        check(len(values) == 6, "Story Overview value shape changed")
        row = by_story[post_id]
        check(row["selected_account_id"] == "118246571240106" and row["selected_account_id_type"] == "Meta Business Suite asset", "Story account identity conflated")
        check(row["measurement_type"] == "lifetime_content_snapshot" and row["canonical_update_applied"] == "False", "Story period/baseline mutation")
        for label, raw in zip(names, values):
            metric = names[label]
            expected = number(raw)
            observed = number(row.get(metric, ""))
            check(expected == observed, f"Story AX metric differs: {post_id}/{metric}")
            check(row[metric + "_raw"] == raw, f"Story raw value changed: {post_id}/{metric}")
            check((row[metric + "_status"] in {"observed", "observed_zero"}) == (expected is not None), "Story status false zero/missing")
            story_metrics[metric + (":observed" if expected is not None else ":unavailable")] += 1
            story_checked += 1
    long_story = normalized_tables["instagram_story_metrics"]
    long_keys = set()
    for row in long_story:
        key = (row["post_id"], row["captured_at_utc"], row["metric"])
        check(key not in long_keys, "Repeated Story capture/metric grain")
        long_keys.add(key)
        wide = by_story[row["post_id"]]
        metric = row["metric"]
        check(row["value"] == wide[metric] and row["value_raw"] == wide[metric + "_raw"] and row["value_status"] == wide[metric + "_status"], "Story per-field and wide tables disagree")
        check(row["measurement_type"] == "lifetime_content_snapshot", "Story per-field lifetime scope changed")
    check(len(long_story) == story_checked, "Story per-field observations omitted/added")
    if report["collection_complete"]:
        check(set(by_story) == expected_stories, "Completed pass did not retain every targeted Story ID")

    # A URL date, visible single-day label, selected IG and the isolated Follows
    # card must all agree; a zero elsewhere on the page is insufficient.
    manual = read_json(root / "raw/follows_daily_observations.json")
    if isinstance(manual, dict):
        manual = manual["observations"]
    manual_by_day = {}
    timezone_panels = 0
    for observation in manual:
        day = observation["date"]
        check(day not in manual_by_day, "Repeated manual Follows day")
        evidence = inside(root, observation["evidence_ref"]).read_text(encoding="utf-8-sig")
        timezone_panels += "Pacific Time" in evidence
        params = parse_qs(urlsplit(browser_url(evidence)).query)
        check(params.get("platform") == ["Instagram"] and params.get("asset_id") == ["118246571240106"], "Follows account/platform mismatch")
        raw_range = params["time_range"][0]
        for _ in range(3):
            if raw_range.startswith("{"):
                break
            raw_range = unquote(raw_range)
        bounds = json.loads(raw_range)
        check(bounds["start"] == bounds["end"] == day, "Follows URL is not exact daily window")
        day_obj = datetime.fromisoformat(day)
        expected_label = f"{day_obj.strftime('%b')} {day_obj.day}, {day_obj.year}"
        check(re.search(r"\bbutton " + re.escape(expected_label) + r"(?:, ID:|\s*$)", evidence, re.M), "Follows visible date differs from URL")
        match = re.search(r"^(\s*)\d+ heading Follows,.*$", evidence, re.M)
        check(match is not None, "Follows card absent")
        indent = len(match[1])
        section = []
        for line in evidence[match.end():].splitlines():
            if line.strip() and len(line) - len(line.lstrip()) < indent:
                break
            section.append(line)
        card = "\n".join(section)
        numeric_nodes = [m[1] for m in re.finditer(r"^\s*\d+ text (\d[\d,]*)\s*$", card, re.M)]
        check(numeric_nodes, "Follows card has no explicit numeric observation")
        value = number(numeric_nodes[0])
        check(value == number(observation["value"]), "Follows raw panel numeric mismatch")
        if value == 0:
            check("No activity during selected date range" in card, "Follows zero lacks direct card confirmation")
        check(observation["reporting_timezone"] == "Pacific Time", "Follows timezone not verified source timezone")
        utc(observation["captured_at_utc"])
        manual_by_day[day] = value
    check(timezone_panels > 0, "No saved Follows panel corroborates Pacific Time")
    incoming = normalized_tables["instagram_follows"]
    incoming_days = {}
    for row in incoming:
        value = number(row["value"])
        if row["date"] in incoming_days:
            check(value == incoming_days[row["date"]], "New Follows disagree on same day")
        incoming_days[row["date"]] = value
        if row.get("evidence_ref"):
            check(value == manual_by_day[row["date"]], "Normalized manual Follows differs from panel")
        else:
            source = native(inside(root, row["source_file"]), ["Date", "Primary"])
            source = source[int(row["source_record"])]
            check(row["date"] == source["Date"][:10] and value == number(source["Primary"]), "Native Follows source row mismatch")
    prior_follows = [r for r in old_daily if r["platform_selected"] == "Instagram" and r["metric"] == "follows"]
    prior_by_day = {r["date"]: r for r in prior_follows}
    resolved = normalized_tables["follows_daily_resolved"] + normalized_tables["follows_daily_partial"]
    check(len(resolved) == len(prior_by_day) and len({r['date'] for r in resolved}) == len(resolved), "Follows resolved grain changed")
    newly_observed = 0
    for row in resolved:
        old = prior_by_day[row["date"]]
        prior_value = number(old["value"])
        expected = prior_value if prior_value is not None else incoming_days.get(row["date"])
        check(number(row["value"]) == expected, "Resolved Follows altered prior observation or invented value")
        check(row["canonical_update_applied"] == "False", "Canonical Follows mutation flag")
        if prior_value is None and expected is not None:
            newly_observed += 1
    if report["collection_complete"]:
        complete_rows = normalized_tables["follows_daily_resolved"]
        check(len(complete_rows) == 293 and all(number(r["value"]) is not None for r in complete_rows), "Completed Follows view still has an unobserved complete day")

    # Every native Ads field, notably 18-digit IDs, remains an exact string.
    ad_counts, paid_totals = Counter(), {}
    for row in normalized_tables["ads_history"] + normalized_tables["ads_campaigns"]:
        relative = row["source_file"]
        if relative not in paid_totals:
            paid_totals[relative] = {"spend": Decimal(0), "rows": 0, "nonblank_spend_rows": 0}
        source_path = inside(root, relative)
        if relative not in ad_counts:
            ad_counts[relative] = native(source_path, ["Reporting starts", "Reporting ends"])
        original = ad_counts[relative][int(row["source_record"])]
        check(all(row[k] == v for k, v in original.items()), "Native ad cell changed: " + relative)
        for original_key, normalized_key in (("Account ID", "ad_account_id"), ("Campaign ID", "campaign_id"), ("Ad set ID", "ad_set_id"), ("Ad ID", "ad_id")):
            if original_key in original:
                check(row[normalized_key] == original[original_key], "Native ID precision loss")
        statuses = json.loads(row["metric_value_status_json"])
        for metric, status in statuses.items():
            expected = number(original[metric])
            check((status in {"observed", "observed_zero"}) == (expected is not None), "Ads missing/zero status mismatch")
        spend = number(original.get("Amount spent (USD)"))
        paid_totals[relative]["rows"] += 1
        if spend is not None:
            paid_totals[relative]["spend"] += spend
            paid_totals[relative]["nonblank_spend_rows"] += 1
    for relative, native_rows in ad_counts.items():
        check(len(native_rows) == paid_totals[relative]["rows"], "Native ad rows duplicated/omitted")

    fb_old = {(r["metric"], r["date"]): r for r in old_daily if r["platform_selected"] == "Facebook"}
    fb_seen = set()
    for row in normalized_tables["facebook_daily_recheck"]:
        key = (row["metric"], row["date"])
        check(key not in fb_seen, "Repeated Facebook recheck grain")
        fb_seen.add(key)
        source = native(inside(root, row["source_file"]), ["Date", "Primary"])[int(row["source_record"])]
        check(number(source["Primary"]) == number(row["value"]) == number(fb_old[key]["value"]), "Facebook recheck/source/predecessor disagreement")
        check(row["canonical_update_applied"] == "False", "Facebook canonical mutation")

    mapping = root / "mapping"
    posts = read_json(mapping / "post_evidence.json")
    references = read_json(mapping / "post_song_references.json")
    posts_by_key = {r["post_key"]: r for r in posts}
    check(len(posts_by_key) == len(posts), "Duplicate post mapping identity")
    identity = lambda r: (r["platform_selected"], r["selected_account_id"], r["post_id"])
    old_posts = {identity(r): r for r in asset_table(assets, "social/posts_latest.csv")}
    check(len(old_posts) == len(posts), "Post mapping changed canonical post population")
    for row in posts:
        check(all(isinstance(row[k], str) for k in ["selected_account_id", "post_id"]), "Post ID converted to numeric")
        old = old_posts[identity(row)]
        check(row["description"] == old["description"], "Caption changed before mapping")
        check(hashlib.sha256(assets[row["retained_source_path"]]).hexdigest() == row["retained_source_sha256"], "Mapping source hash mismatch")
    mapping_statuses = Counter()
    for row in references:
        check(row["post_key"] in posts_by_key, "Reference has no source post")
        check(row["audio_use_verified"] is False and row["stream_attribution_available"] is False, "Unsupported audio/stream attribution")
        check(not ({"views", "streams", "reach", "interactions"} & row.keys()), "Metrics copied onto many-to-many bridge")
        check(identity(row) == identity(posts_by_key[row["post_key"]]), "Mapping post identity changed")
        mapping_statuses[row["status"]] += 1
    package_inherited = 0
    if package:
        package = package.resolve()
        for name, raw in assets.items():
            target = "raw/meta_predecessor_metadata/" + name if name in {"metadata.json", "raw_sha256.json", "audit/final_validation.json"} else name
            check(inside(package, target).read_bytes() == raw, "Inherited asset changed: " + name)
            package_inherited += 1
    preservation(root)
    for name, sha in report["input_files_sha256"].items():
        check(digest(inside(root, name)) == sha, "Raw source changed during audit")
    return {"status": "PASS", "audited_at_utc": datetime.now(timezone.utc).isoformat(),
            "audit_implementation": "standard library, no producer imports; second implementation", "audit_script_sha256": digest(Path(__file__)),
            "collection_complete_reported": report["collection_complete"],
            "preflight_databases_unchanged": databases, "preflight_registry_unchanged": True,
            "source_database_sha256": db_sha, "input_hashes_checked": len(report["input_files_sha256"]), "output_manifest_files_checked": manifests,
            "story_id_target": len(expected_stories), "story_ids_checked": len(story_rows), "story_ids_not_collected": sorted(expected_stories - set(by_story)),
            "story_raw_metric_cells_checked": story_checked, "story_per_field_rows_checked": len(long_story), "story_metric_availability": dict(story_metrics),
            "manual_follows_exact_daily_panels_checked": len(manual_by_day), "normalized_follows_evidence_rows": len(incoming),
            "manual_follows_panels_with_direct_Pacific_Time_label": timezone_panels,
            "resolved_follows_complete_rows": len(normalized_tables["follows_daily_resolved"]), "resolved_follows_partial_rows": len(normalized_tables["follows_daily_partial"]),
            "missing_follows_explicitly_recovered": newly_observed, "prior_observed_follows_unchanged": True,
            "ads_by_source": {k: {**v, "spend": str(v["spend"]) if v["nonblank_spend_rows"] else None} for k, v in paid_totals.items()},
            "facebook_native_cells_match_prior": len(fb_seen), "post_mapping_count": len(posts), "song_reference_statuses": dict(mapping_statuses),
            "package_inherited_assets_verified": package_inherited,
            "limitations": ["PASS covers saved source evidence, not independent backend truth or causal effects.",
                            "Story metrics are lifetime readings at different capture times, not period activity; unavailable cells stay missing.",
                            "Ads totals are per native export only; overlapping windows and parent/child levels cannot be added.",
                            "Facebook June discontinuity remains unexplained despite repeated matching native values.",
                            "Follows timezone is corroborated by saved source UI panels; no conversion to Eastern Time.",
                            "Original October 20 baseline membership remains unverified; no baseline relabeling or edits performed."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", required=True, type=Path)
    parser.add_argument("--normalized", required=True, type=Path)
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    check(not args.report.exists(), "Use a new audit report path")
    result = audit(args.collection, args.normalized, args.package_root)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
