"""Independent, read-only audit of additional Spotify collection evidence.

Uses only the standard library. Does not import or execute package build code.
Every derived check starts from immutable ZIP bytes, CSV cells, or saved raw
browser chart labels/table cells; no Spotify connection or database write occurs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import parse_qs, urlparse
import zipfile


SOURCES = [
    "All active sources", "Artist profile and catalog",
    "Listener's own playlists and library", "Listener’s queue",
    "All programmed sources", "Editorial and personalized editorial playlists",
    "Personalized playlists, autoplay and mixes", "Other listeners’ playlists", "Other",
]
PERIOD_KEY = ["Scope", "Spotify ID", "Population", "Period start", "Period end", "Metric", "Source"]
DAILY_KEY = ["Scope", "Spotify ID", "Population", "Window start", "Window end", "Date", "Metric"]
DAILY_LABELS = [
    "goomh_baseline_full_streams", "goomh_baseline_full_listeners",
    "goomh_baseline_full_streams_per_listener", "goomh_baseline_full_playlist_adds",
    "goomh_baseline_full_saves_confirmed", "son_baseline_full_streams",
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    assert all(None not in row for row in rows), f"Malformed CSV: {path}"
    return rows


def number(value):
    if value in (None, "", "—", "-"):
        return None
    return Decimal(str(value).replace(",", "").replace("%", ""))


def identity(row, fields):
    return tuple(row[field] for field in fields)


def indexed(rows, fields):
    result = {identity(row, fields): row for row in rows}
    assert len(result) == len(rows), ("Duplicate canonical key", fields)
    return result


def chart_date(label):
    match = re.match(r"^([A-Za-z]+) (\d{1,2}),? (\d{4})(?:,|\s)", label)
    assert match, ("Unrecognized chart date", label)
    observed = datetime.strptime(" ".join((match[1][:3], match[2], match[3])), "%b %d %Y").date()
    return observed.isoformat(), match.end()


def zip_check(archive, destination):
    checked, paths = [], set()
    with zipfile.ZipFile(archive) as handle:
        for member in handle.infolist():
            if member.is_dir():
                continue
            relative = PurePosixPath(member.filename)
            assert not relative.is_absolute() and ".." not in relative.parts
            assert member.filename not in paths, "Duplicate ZIP member"
            paths.add(member.filename)
            target = destination.joinpath(*relative.parts)
            raw = handle.read(member)
            digest = hashlib.sha256(raw).hexdigest()
            assert target.is_file() and target.read_bytes() == raw, target
            checked.append({"path": member.filename, "bytes": len(raw), "sha256": digest})
    extracted = {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}
    assert extracted == paths, {"extra": sorted(extracted-paths), "missing": sorted(paths-extracted)}
    return {"archive": str(archive), "sha256": sha(archive), "extracted_files": len(checked), "byte_identity": True, "files": checked}


def manifest_check(root):
    checks = []
    for manifest in sorted(root.rglob("sha256.json")):
        entries = read_json(manifest)
        for relative, expected in entries.items():
            path = PurePosixPath(relative)
            assert not path.is_absolute() and ".." not in path.parts
            target = manifest.parent.joinpath(*path.parts)
            assert target.is_file() and sha(target) == expected, target
        checks.append({"manifest": str(manifest), "entries": len(entries), "nested_prior_pass_entries": sum(key.startswith("prior_pass/") for key in entries), "all_match": True})
    return checks


def baseline_check(project, recovery):
    cleaned = project / "data/recovery/cleaned_analysis_2026-10-22/analysis_2026-10-22/raw/spotify_baseline/normalized/song_daily_long.csv"
    retained = recovery / "raw/original_song_daily_long.csv"
    assert cleaned.read_bytes() == retained.read_bytes(), "Original cleaned daily file differs from recovery copy"
    fields = ["song_id", "date", "metric"]
    original = indexed(read_csv(retained), fields)
    complete = indexed(read_csv(recovery / "normalized/song_daily_long_complete_baseline.csv"), fields)
    additions_rows = read_csv(recovery / "normalized/recovered_song_daily.csv")
    additions = indexed(additions_rows, ["Spotify ID", "Date", "Metric"])
    assert len(original) == 66631 and len(complete) == 71680 and len(additions) == 5049
    assert set(original).isdisjoint(additions) and set(original) | set(additions) == set(complete)
    for key, old in original.items():
        assert old == complete[key], ("Changed original row", key)
    for key, added in additions.items():
        assert number(added["Value"]) == number(complete[key]["value"])
        assert added["Origin"] == complete[key]["origin"] == "rendered_chart_labels"
        assert added["Baseline end"] == "2026-10-20" and added["Reporting basis"] == "baseline supplement"
        assert complete[key]["source"] == added["Evidence"] + ".json"
    dates = defaultdict(set)
    for song, day, metric in complete:
        dates[(song, metric)].add(day)
    expected_dates = {(date(2024, 1, 1)+timedelta(days=i)).isoformat() for i in range(1024)}
    assert len(dates) == 70 and all(days == expected_dates for days in dates.values())

    raw = read_json(recovery / "raw/retained_browser_captures.json")
    by_label = {capture["label"]: capture for capture in raw}
    recaptured_keys, recaptured_rows, overlaps, new_count = set(), 0, 0, 0
    series = []
    for label in DAILY_LABELS:
        capture = by_label[label]
        query = parse_qs(urlparse(capture["url"]).query)
        assert "sourceOfStreams" not in query
        song = re.search(r"/song/([^/]+)/", capture["url"])[1]
        metric = query["metric"][0]
        observed_dates, values, added, overlap = [], [], 0, 0
        for chart in capture["chartLabels"]:
            observed_date, tail_start = chart_date(chart)
            match = re.match(r"[ ,]*([\d,.]+)\s", chart[tail_start:])
            assert match, (label, chart)
            value = number(match[1])
            key = (song, observed_date, metric)
            assert key not in recaptured_keys
            recaptured_keys.add(key)
            assert value == number(complete[key]["value"]), (label, key, value, complete[key]["value"])
            observed_dates.append(observed_date)
            values.append(value)
            if key in original:
                overlap += 1
            else:
                added += 1
                assert additions[key]["Evidence"] == label
                assert additions[key]["Collected UTC"] == capture["collected_at"]
                assert additions[key]["Source URL"] == capture["url"]
        assert len(observed_dates) == len(set(observed_dates)) == 1024 and set(observed_dates) == expected_dates
        result = {"evidence": label, "metric": metric, "days": len(observed_dates), "overlap_agreements": overlap, "added_observed_values": added}
        if metric in {"streams", "saves", "playlist_adds"}:
            header = capture["tables"][0][0]
            current_column = header.index("This Period")
            table_value = number(capture["tables"][0][1][current_column])
            assert sum(values) == table_value
            result["raw_additive_sum_equals_table"] = table_value
        else:
            result["period_aggregation"] = "Not summed: daily uniqueness or ratio"
        series.append(result)
        recaptured_rows += len(observed_dates)
        overlaps += overlap
        new_count += added
    assert recaptured_rows == 6144 and overlaps == 1095 and new_count == 5049

    old_periods = read_csv(recovery / "raw/original_song_periods_from_daily.csv")
    periods = read_csv(recovery / "normalized/song_periods_complete_baseline.csv")
    recovered_periods = read_csv(recovery / "normalized/recovered_song_periods.csv")
    period_fields = ["song_id", "period", "metric", "start_date", "end_date"]
    old_period_map = indexed(old_periods, period_fields)
    period_map = indexed(periods, period_fields)
    recovered_map = indexed(recovered_periods, period_fields)
    assert set(old_period_map).isdisjoint(recovered_map) and set(old_period_map) | set(recovered_map) == set(period_map)
    for key, row in period_map.items():
        assert row["metric"] in {"streams", "saves", "playlist_adds"}
        dates_in_window = [row["start_date"] <= day <= row["end_date"] for day in expected_dates]
        values = [number(value["value"]) for (song, day, metric), value in complete.items() if song == row["song_id"] and metric == row["metric"] and row["start_date"] <= day <= row["end_date"]]
        assert len(values) == sum(dates_in_window) == (date.fromisoformat(row["end_date"])-date.fromisoformat(row["start_date"])).days+1
        assert sum(values) == number(row["value"])
        if key in old_period_map:
            assert number(old_period_map[key]["value"]) == number(row["value"])
    assert len(old_period_map) == 434 and len(period_map) == 462 and len(recovered_map) == 28
    return {"original_cleaned_copy_byte_identity": True, "original_rows_unchanged": len(original), "new_observed_values": len(additions), "complete_observations": len(complete), "complete_series": len(dates), "raw_recovered_chart_observations": recaptured_rows, "raw_duplicate_value_agreements": overlaps, "series_audit": series, "original_additive_period_values_unchanged": len(old_periods), "recomputed_additive_periods": len(periods), "new_additive_periods": len(recovered_periods)}


def source_check(recovery, continuation):
    period_before = indexed(read_csv(recovery / "normalized/source_collection.csv"), PERIOD_KEY)
    daily_before = indexed(read_csv(recovery / "normalized/source_daily_collection.csv"), DAILY_KEY)
    period_after = indexed(read_csv(continuation / "normalized/source_collection.csv"), PERIOD_KEY)
    daily_after = indexed(read_csv(continuation / "normalized/source_daily_collection.csv"), DAILY_KEY)
    for key, row in period_before.items():
        assert row == period_after[key], ("Changed prior source comparison", key)
    for key, row in daily_before.items():
        assert row == daily_after[key], ("Changed prior source daily row", key)
    period_seen = {key: (number(row["Current value"]), number(row["Previous value"])) for key, row in period_before.items()}
    daily_seen = {key: tuple(number(row[source]) for source in SOURCES) for key, row in daily_before.items()}
    checks, excluded, valid = [], [], []
    period_duplicates, daily_duplicates = 0, 0
    new_period_keys, new_daily_keys = set(), set()
    for capture in read_json(continuation / "raw/browser_captures.json"):
        if "sources" not in capture["label"]:
            continue
        if not capture.get("tables") or len(capture["tables"][0]) != 10 or not capture.get("chartLabels"):
            excluded.append(capture["label"])
            continue
        query = parse_qs(urlparse(capture["url"]).query)
        metric = query.get("metric", ["streams"])[0]
        label, table = capture["label"], capture["tables"][0]
        scope = "release" if "/release/" in capture["url"] else "song" if "/song/" in capture["url"] else "artist"
        entity = re.search(r"/" + scope + r"/([^/?]+)", capture["url"])[1]
        population = query.get("country", ["Worldwide"])[0]
        if population == "US":
            population = "United States"
        metric_heading = {"streams": "Streams", "listeners": "Listeners", "streams_per_listener": "Streams / Listener"}[metric]
        assert table[0][0].startswith(metric_heading + " ·"), (label, "Metric heading mismatch")
        previous_column = table[0].index("Previous Period")
        current_column = table[0].index("This Period")
        points = [(chart_date(chart)[0], chart) for chart in capture["chartLabels"]]
        days = [point[0] for point in points]
        start, end = min(days), max(days)
        assert len(set(days)) == len(days) == (date.fromisoformat(end)-date.fromisoformat(start)).days+1
        assert query.get("fromDate", [start])[0] == start and query.get("toDate", [end])[0] == end == "2026-10-20"
        currents, parsed_sources = {}, set()
        for row in table[1:]:
            matches = [source for source in SOURCES if row[0] == source]
            if not matches:
                candidates = [source for source in SOURCES if row[0].startswith(source + " ")]
                matches = sorted(candidates, key=len, reverse=True)[:1]
            assert len(matches) == 1, (label, row[0], matches)
            source = matches[0]
            assert source not in parsed_sources
            parsed_sources.add(source)
            pair = (number(row[current_column]), number(row[previous_column]))
            currents[source] = pair[0]
            key = (scope, entity, population, start, end, metric, source)
            assert pair == (number(period_after[key]["Current value"]), number(period_after[key]["Previous value"]))
            if key in period_seen:
                assert pair == period_seen[key], (label, "Conflicting comparison", key)
                period_duplicates += 1
            else:
                period_seen[key] = pair
                new_period_keys.add(key)
                assert period_after[key]["Evidence"] == label and period_after[key]["Source URL"] == capture["url"]
                assert period_after[key]["Collected UTC"] == capture["collected_at"]
        assert parsed_sources == set(SOURCES)
        totals = {source: Decimal(0) for source in SOURCES}
        for observed_date, chart in points:
            values = []
            for source in SOURCES:
                pattern = re.compile(re.escape(source) + r" ([\d,.]+) " + re.escape(metric) + r"(?=,|\s|$)")
                found = pattern.findall(chart)
                assert len(found) == 1, (label, source, chart)
                value = number(found[0])
                if metric == "streams":
                    totals[source] += value
                values.append(value)
            key = (scope, entity, population, start, end, observed_date, metric)
            values = tuple(values)
            assert values == tuple(number(daily_after[key][source]) for source in SOURCES)
            if key in daily_seen:
                assert values == daily_seen[key], (label, "Conflicting daily source values", key)
                daily_duplicates += 1
            else:
                daily_seen[key] = values
                new_daily_keys.add(key)
                assert daily_after[key]["Evidence"] == label and daily_after[key]["Collected UTC"] == capture["collected_at"]
        if metric == "streams":
            for source in SOURCES:
                unavailable = currents[source] is None
                assert totals[source] == (Decimal(0) if unavailable else currents[source]), (label, source, currents[source], totals[source])
                checks.append({"scope": scope, "id": entity, "population": population, "start": start, "end": end, "source": source, "table_streams": currents[source], "daily_stream_sum": totals[source], "result": "table unavailable; chart explicitly zero" if unavailable else "match", "evidence": label})
        valid.append({"evidence": label, "scope": scope, "id": entity, "population": population, "start": start, "end": end, "metric": metric, "days": len(days)})
    assert set(period_seen) == set(period_after) and set(daily_seen) == set(daily_after)
    assert len(checks) == 297 and period_duplicates == 54 and daily_duplicates == 1516
    assert len(new_period_keys) == 765 and len(new_daily_keys) == 25633
    assert set(indexed(read_csv(continuation / "normalized/added_source_collection.csv"), PERIOD_KEY)) == new_period_keys
    assert set(indexed(read_csv(continuation / "normalized/added_source_daily_collection.csv"), DAILY_KEY)) == new_daily_keys
    stored = read_csv(continuation / "normalized/source_stream_reconciliation.csv")
    check_fields = ["scope", "id", "population", "start", "end", "source", "evidence"]
    saved_by_key = indexed(stored, check_fields)
    for check in checks:
        saved = saved_by_key[identity(check, check_fields)]
        assert number(saved["table_streams"]) == check["table_streams"]
        assert number(saved["daily_stream_sum"]) == check["daily_stream_sum"]
        assert saved["result"] == check["result"]
    assert len(saved_by_key) == len(checks)
    missing = [check for check in checks if check["table_streams"] is None]
    assert all(period_after[(check["scope"], check["id"], check["population"], check["start"], check["end"], "streams", check["source"])]["Current value"] == "" for check in missing)
    return {"method": "Independently parsed saved raw chart labels with escaped literal source names; table current/previous columns selected by headings; no package builder executed", "raw_valid_source_captures": len(valid), "raw_excluded_source_captures": len(excluded), "prior_comparison_rows_unchanged": len(period_before), "prior_daily_rows_unchanged": len(daily_before), "comparison_duplicate_agreements": period_duplicates, "daily_row_duplicate_agreements": daily_duplicates, "source_comparison_additions": len(new_period_keys), "source_daily_row_additions": len(new_daily_keys), "cumulative_comparisons": len(period_after), "cumulative_daily_rows": len(daily_after), "independently_recomputed_stream_reconciliations": len(checks), "reconciliation_results": dict(Counter(check["result"] for check in checks)), "missing_table_values_preserved_as_missing": len(missing), "raw_reconciliations": checks, "valid_capture_scopes": valid, "excluded_capture_labels": excluded}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    base = project / "data/recovery/additional_20261023"
    recovery = base / "recovery/The_Stats_Collection_Recovery_2026-10-23"
    continuation = base / "continuation/The_Stats_Collection_Continuation_2026-10-23"
    source_hashes_before = {str(path): sha(path) for root in (recovery, continuation) for path in root.rglob("*") if path.is_file()}
    report = {"audit": "Independent additional Spotify input audit", "captured_utc": datetime.now(timezone.utc).isoformat(), "read_only_inputs": True, "implementation": "scripts/audit_additional_inputs.py", "implementation_sha256": sha(Path(__file__)), "archives": [], "sha256_manifests": [], "limitations": ["Raw captures establish the preserved source evidence, not a new live Spotify read.", "Row counts are not independent statistical sample sizes.", "Daily listeners, source listeners, ratios and overlapping source hierarchy levels are not added into period/artist audience metrics."]}
    for root, folder in ((recovery, "recovery"), (continuation, "continuation")):
        archive = project / "data/recovery" / (root.name + ".zip")
        report["archives"].append(zip_check(archive, base / folder))
        report["sha256_manifests"].extend(manifest_check(root))
    report["baseline"] = baseline_check(project, recovery)
    report["continuation_sources"] = source_check(recovery, continuation)
    report["inputs_unchanged_after_audit"] = all(sha(Path(path)) == digest for path, digest in source_hashes_before.items())
    assert report["inputs_unchanged_after_audit"]
    report["result"] = "PASS"
    target = args.output or project / "data/reconciliation/additional_20261023/independent_input_audit.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=lambda value: float(value) if isinstance(value, Decimal) else str(value)) + "\n", encoding="utf-8")
    print(json.dumps({"result": report["result"], "output": str(target), "baseline": report["baseline"], "sources": {key: value for key, value in report["continuation_sources"].items() if key not in {"raw_reconciliations", "valid_capture_scopes", "excluded_capture_labels"}}, "input_files_unchanged": len(source_hashes_before)}, ensure_ascii=False, default=lambda value: float(value) if isinstance(value, Decimal) else str(value)))


if __name__ == "__main__":
    main()
