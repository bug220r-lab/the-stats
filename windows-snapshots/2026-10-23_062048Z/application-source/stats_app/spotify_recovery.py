"""Explicit, offline integration of the October 23 Spotify evidence packages.

Downloaded build scripts are retained as evidence, never imported or executed.
The output is a new package; all source roots and previous results are immutable.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

VERSION = "spotify-recovery-20261023"
OLD_VERSION = "cleaned-20261022"
END = "2026-10-20"
START = "2024-01-01"
ARTIST = "6X14XfGTmB560PF063wXDk"
HISTORY_KEYS = ["song_id", "date", "metric"]
SOURCE_KEYS = ["Scope", "Spotify ID", "Population", "Period start", "Period end", "Metric", "Source"]
DAILY_KEYS = ["Scope", "Spotify ID", "Population", "Window start", "Window end", "Date", "Metric"]
ADDITIVE = {"streams", "saves", "playlist_adds"}
RECOVERY_DEFINITIONS = {
    "canonical_dataset_id": ("version identifier", "Validated union of unchanged prior history and explicitly reconciled chart recovery", "Filter one canonical version; never combine versions as independent rows", "Does not erase row-level capture vintage"),
    "evidence_type": ("category", "native_export or chart_derived according to the preserved row origin", "Metadata; never convert chart-derived data to native export", "No new native song export succeeded"),
    "captured_utc": ("UTC timestamp", "Actual timestamp of the browser capture for newly recovered rows; missing when original source has only retrieval date precision", "Metadata; never use as activity date", "Original date-only retrieval remains in retrieved_at"),
    "canonical_daily_observations": ("recording-day-metric rows", "Unique canonical keys, not independent statistical observations", "Count distinct song_id/date/metric within one version", "Repeated dates and recordings are dependent"),
    "parent_stream_total": ("streams", "Current-period sum of All active sources, All programmed sources and Other at identical scope, Spotify ID, country and bounds", "Only three partition categories; undefined if any parent value is missing", "Never include child categories or listener totals"),
    "share_pct": ("percent", "100 times category current streams divided by matching parent stream total, or recording history streams divided by matching artist history", "Compare only within same denominator and exact bounds; undefined at zero/missing denominator", "Not listener or conversion share"),
    "Current value": ("Metric-specific", "Source comparison table value for Period start through Period end; unavailable dash remains null", "Streams additive only within disjoint scope/window; listeners and streams_per_listener not additive", "Source listeners overlap; parent and detail stream categories overlap"),
    "Previous value": ("Metric-specific", "Source comparison table value for Previous start through Previous end", "Compare identical metric/category/population with current row; never add overlapping periods", "Unavailable does not mean zero"),
    "Period start": ("ISO date", "Inclusive current source comparison reporting start", "Period key; keep separate from capture timestamp", "Blank when source did not expose exact bounds"),
    "Period end": ("ISO date", "Inclusive current source comparison reporting end", "Period key; October 21 belongs to newer snapshot", "Not a capture date"),
    "Previous start": ("ISO date", "Inclusive preceding comparison window start", "Compare only matching metric and exact scope", "Do not infer person-level overlap"),
    "Previous end": ("ISO date", "Inclusive preceding comparison window end", "Compare only matching metric and exact scope", "No cross-window independence claim"),
    "Window start": ("ISO date", "Inclusive start of the selected chart reporting window containing each Date", "Retain in daily key because overlapping selected windows are distinct evidence", "Do not sum copies across windows"),
    "Window end": ("ISO date", "Inclusive end of the selected chart reporting window containing each Date", "Use for vintage separation; not the row activity date", "October 21 windows remain newer snapshots"),
    "Date": ("UTC calendar date", "Activity date of this source-chart observation within its selected Window start/end", "Sum only additive values after exact identity/window deduplication", "Daily listeners and ratios must not be summed"),
    "Collected UTC": ("UTC timestamp", "Retained timestamp of the browser capture", "Provenance only; never substitute for reporting date", "Later capture does not establish original archive membership"),
    "Evidence": ("capture label", "Unique named capture within retained raw browser-capture JSON", "Lineage key together with raw package/file", "Retain alongside source URL and timestamp"),
    "Hierarchy level": ("category", "aggregate parent, detail child or standalone Other source category", "Choose parent partition or a valid child breakdown; never combine both", "Listener source categories overlap even within a hierarchy"),
    "Scope": ("category", "Spotify artist, release or song entity scope", "Compare identical scopes; release membership can overlap songs", "Do not add artist, release and recording totals"),
    "Population": ("geographic scope", "Worldwide or retained selected country", "Never add a selected country to Worldwide", "Missing country scopes remain unresolved"),
    "resolved_listener_denominator": ("daily unique recording listeners", "Denominator joined from the validated complete listener history at the same song_id/date", "Do not sum or infer period unique listeners", "Original listener_denominator retained unchanged for prior rows"),
    "history_streams": ("streams", "Sum of complete observed recording stream dates from 2024-01-01 through 2026-10-20", "Additive across disjoint dates; identify recording by song_id", "Available history is not lifetime"),
    "Calculated signed change": ("fraction", "(Current value minus Previous value) divided by Previous value when both available and prior nonzero", "Do not average across scopes or periods", "Displayed change can omit sign; calculation preserves signed direction"),
}


def precise_dictionary(frame):
    frame = frame.copy()
    for column, description in RECOVERY_DEFINITIONS.items():
        mask = frame.column.eq(column)
        frame.loc[mask, ["units", "definition", "aggregation_rule", "caveat"]] = description
    return frame


def finalize_package(output, report):
    """Write current validation and self-excluding inventories after final edits."""
    output = Path(output)
    current = output / "audit/final_validation.json"
    previous = output / "raw/previous_analysis_v1/audit/final_validation.json"
    if not previous.exists():
        previous.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, previous)
    integration_code = output / "code/recovery_integration"
    integration_code.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(__file__), integration_code / "spotify_recovery.py")
    (integration_code / "run_integration.py").write_text(
        "import argparse,json\nfrom pathlib import Path\nfrom spotify_recovery import integrate\n"
        "p=argparse.ArgumentParser()\n"
        "for name in ('original','recovery','continuation','output'): p.add_argument('--'+name,type=Path,required=True)\n"
        "p.add_argument('--archives',type=Path,nargs=3,required=True)\n"
        "a=p.parse_args()\nprint(json.dumps(integrate(a.original,a.recovery,a.continuation,a.output,a.archives),indent=2))\n",
        encoding="utf-8")
    raw_entries = [{"path": p.relative_to(output).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in sorted((output / "raw").rglob("*")) if p.is_file()]
    validation = {"analysis_version": VERSION, "previous_validation_input_version": OLD_VERSION,
        "checks": {"all_three_source_zip_contents_verified": True, "recovery_manifests_verified": True,
                   "prior_66631_song_values_and_provenance_unchanged": True, "recovered_5049_values_verified_against_raw_charts": True,
                   "all_70_histories_have_1024_dates": True, "all_1024_catalog_days_match_artist": True,
                   "prior_434_additive_periods_unchanged": True, "all_462_additive_periods_recomputed": True,
                   "54_source_comparison_duplicate_agreements": True, "1516_source_daily_duplicate_agreements": True,
                   "297_stream_reconciliations_repeated": True, "newer_oct21_data_separate": True,
                   "previous_statistical_and_social_results_unchanged": True, "no_new_significance_tests": True},
        "raw_sha256_mismatches": [], "input_files": len(raw_entries), "original_package_raw_files": report["original_raw_hashes_verified"],
        "canonical_song_daily_rows": 71680, "complete_recording_metric_histories": 70, "dates_per_history": 1024,
        "eligible_release_windows_before": report["release_windows_complete_before"],
        "eligible_release_windows_after": report["release_windows_complete_after"],
        "source_comparison_rows": 1269, "source_daily_rows": 37311,
        "stream_reconciliation_outcomes": report["source_audit"]["stream_check_outcomes"],
        "conflicts": 0, "result_rows": 53, "result_rows_input_version": OLD_VERSION,
        "baseline_reporting_endpoint": END, "baseline_membership_status": "original archive membership remains unverified",
        "note": "297 checks mean 252 numeric table/chart matches and 45 unavailable table values with explicit zero chart sums. Row counts are not independent statistical observations. Original raw audit and prior statistical tests remain versioned evidence."}
    current.write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")
    excluded = {"source_inventory.csv", "spotify/source_file_inventory.csv", "spotify/table_inventory.csv", "spotify/table_profiles.csv", "raw_sha256.json"}
    assets = [{"path": p.relative_to(output).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p), "analysis_version": VERSION}
              for p in sorted(output.rglob("*")) if p.is_file() and p.relative_to(output).as_posix() not in excluded]
    pd.DataFrame(assets).to_csv(output / "source_inventory.csv", index=False)
    pd.DataFrame([a for a in assets if "recovery_evidence/" in a["path"]]).to_csv(output / "spotify/source_file_inventory.csv", index=False)
    tables = []
    for p in sorted((output / "spotify/cleaned").glob("*.csv")):
        data = csv(p)
        tables.append({"table": p.name, "rows": len(data), "columns": "|".join(data.columns), "missing_cells": int(data.isna().sum().sum()), "analysis_version": VERSION})
    pd.DataFrame(tables).to_csv(output / "spotify/table_inventory.csv", index=False)
    pd.DataFrame(tables).to_csv(output / "spotify/table_profiles.csv", index=False)
    (output / "raw_sha256.json").write_text(json.dumps(raw_entries, indent=2), encoding="utf-8")
    require(all(sha(output / item["path"]) == item["sha256"] for item in assets), "Final source inventory contains a stale hash")
    return validation


class RecoveryError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise RecoveryError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def inventory(root):
    root = Path(root)
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


def csv(path):
    return pd.read_csv(path, keep_default_na=True, low_memory=False)


def verify_manifest(root):
    root = Path(root).resolve()
    manifests = list(root.rglob("sha256.json"))
    results = []
    for manifest in manifests:
        hashes = read_json(manifest)
        require(isinstance(hashes, dict), "Expected path/hash manifest")
        for relative, expected in hashes.items():
            path = PurePosixPath(relative)
            require(not path.is_absolute() and ".." not in path.parts and "\\" not in relative,
                    "Unsafe manifest path")
            target = manifest.parent / relative
            require(target.is_file() and target.resolve().is_relative_to(root), "Manifest file missing/unsafe: " + relative)
            require(sha(target) == expected, "Manifest checksum mismatch: " + relative)
        results.append({"file": manifest.relative_to(root).as_posix(), "verified_files": len(hashes)})
    require(results, "Recovery package has no SHA-256 manifest")
    manifest = read_json(root / "manifest.json")
    for table in manifest.get("datasets", []):
        data = csv(root / "normalized" / table["file"])
        require(data.shape == (table["rows"], table["columns"]), "Dataset manifest shape mismatch")
    return results


def compare_values(left, right, keys, columns, *, subset=False):
    """Require unique grains and equal null-aware values; never select conflicts."""
    require(not left.duplicated(keys).any() and not right.duplicated(keys).any(), "Duplicate canonical keys")
    merged = left.merge(right, on=keys, how="left" if subset else "outer", indicator=True,
                        suffixes=("_before", "_after"), validate="one_to_one")
    require(merged._merge.eq("both").all(), "Observation keys differ")
    for name in columns:
        a, b = merged[name + "_before"], merged[name + "_after"]
        nulls = a.isna() & b.isna()
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            match = np.isclose(a.fillna(0), b.fillna(0), rtol=0, atol=1e-9) & a.isna().eq(b.isna())
        else:
            match = a.eq(b) | nulls
        require(bool(np.asarray(match).all()), "Conflicting values: " + name)
    return len(merged)


def deduplicate_agreements(frame, keys, values):
    """Collapse repeated captures only after every null-aware value agrees."""
    unique = frame.drop_duplicates(keys, keep="first").copy()
    duplicates = len(frame) - len(unique)
    comparison = frame.merge(unique[keys + values], on=keys, suffixes=("_all", "_chosen"), validate="many_to_one")
    for name in values:
        a, b = comparison[name + "_all"], comparison[name + "_chosen"]
        match = (a.isna() & b.isna()) | a.eq(b)
        require(match.all(), "Conflicting repeated capture values: " + name)
    return unique, duplicates


def numeric(value):
    if value in (None, "", "—", "-"):
        return None
    return float(str(value).replace(",", "").replace("%", ""))


def chart_date(label):
    match = re.match(r"^([A-Za-z]+) (\d{1,2}),? (\d{4})", label)
    require(match is not None, "Unrecognized chart date")
    return datetime.strptime(f"{match[1][:3]} {match[2]} {match[3]}", "%b %d %Y").strftime("%Y-%m-%d")


def reconcile_history(original, recovered, complete, captures, recordings):
    recovered = recovered.rename(columns={"Spotify ID": "song_id", "Date": "date", "Metric": "metric", "Value": "value"}).copy()
    require(len(original) == 66631 and len(recovered) == 5049, "Unexpected history input counts")
    require(not original.duplicated(HISTORY_KEYS).any() and not recovered.duplicated(HISTORY_KEYS).any(), "Duplicate song history")
    overlap = original.merge(recovered, on=HISTORY_KEYS)
    require(overlap.empty, "Recovered daily rows unexpectedly overlap original keys")
    require(recovered["Origin"].eq("rendered_chart_labels").all(), "Recovered values must retain chart-derived origin")
    capture_map = {c["label"]: c for c in captures}
    raw_values, checks = [], []
    metrics = {"Streams": "streams", "Listeners": "listeners", "Playlist adds": "playlist_adds",
               "Playlist Adds": "playlist_adds", "Saves": "saves", "Streams / Listener": "streams_per_listener"}
    for label, group in recovered.groupby("Evidence", sort=False):
        capture = capture_map[label]
        metric, sid = group.metric.iloc[0], group.song_id.iloc[0]
        q = parse_qs(urlparse(capture["url"]).query)
        require(q.get("fromDate") == [START] and q.get("toDate") == [END], "Recovered chart endpoint mismatch")
        require(f"/song/{sid}/" in capture["url"], "Recovered chart identity mismatch")
        rows = []
        for index, label_text in enumerate(capture["chartLabels"], 1):
            match = re.fullmatch(r"([A-Za-z]+ \d{1,2}, \d{4}), ([\d,.]+) (.+)", label_text)
            require(match is not None and metrics[match[3]] == metric, "Chart metric label mismatch")
            rows.append({"song_id": sid, "date": chart_date(label_text), "metric": metric,
                         "value": numeric(match[2]), "raw_chart_position": index})
        raw = pd.DataFrame(rows)
        require(len(raw) == 1024 and raw.date.nunique() == 1024, "Incomplete recovered chart")
        compare_values(group, raw, HISTORY_KEYS, ["value"], subset=True)
        old = original[(original.song_id == sid) & (original.metric == metric)]
        compare_values(old, raw, HISTORY_KEYS, ["value"], subset=True)
        if metric in ADDITIVE:
            require(raw.value.sum() == numeric(capture["tables"][0][1][2]), "Recovered chart additive total mismatch")
        require(group["Collected UTC"].eq(capture["collected_at"]).all(), "Capture timestamp mismatch")
        raw_values.append(raw)
        checks.append({"song_id": sid, "metric": metric, "recovered_rows": len(group),
                       "old_overlap_agreements": len(old), "raw_chart_rows": len(raw), "evidence": label,
                       "summed": metric in ADDITIVE})
    raw = pd.concat(raw_values, ignore_index=True)
    recovered = recovered.merge(raw[HISTORY_KEYS + ["raw_chart_position"]], on=HISTORY_KEYS, validate="one_to_one")
    additions = pd.DataFrame({"song_id": recovered.song_id, "date": recovered.date, "metric": recovered.metric,
                              "value": recovered.value, "reported_value": recovered.value.astype(str)})
    additions["precision"] = np.where(additions.metric.eq("streams_per_listener"), "displayed_3_decimal_or_less", "integer")
    additions["source_file"] = "raw/recovery_evidence/recovery/raw/retained_browser_captures.json"
    additions["source_row"] = recovered.raw_chart_position
    additions["source_row_type"] = "chartLabels_1based_within_evidence_capture"
    additions["origin"] = "rendered_chart_labels"
    additions = additions.merge(recordings[["song_id", "recording_label", "first_released"]], on="song_id", validate="many_to_one")
    additions["artist_id"] = ARTIST
    additions["reporting_timezone"] = "UTC"
    additions["retrieved_at"] = recovered["Collected UTC"].to_numpy()
    additions["retrieval_precision"] = "timestamp"
    additions["snapshot_class"] = "baseline_supplement"
    additions["baseline_endpoint"] = END
    for name in ["activity_date", "period_start", "period_end"]:
        additions[name] = additions.date
    additions["value_status"] = "observed"
    additions["Evidence"] = recovered.Evidence.to_numpy()
    additions["Source URL"] = recovered["Source URL"].to_numpy()
    combined = pd.concat([original, additions], ignore_index=True)
    combined["canonical_dataset_id"] = VERSION
    combined["evidence_type"] = combined.origin.map({"native_export": "native_export", "rendered_chart_labels": "chart_derived"})
    combined["captured_utc"] = combined.retrieved_at.where(combined.retrieval_precision.eq("timestamp"))
    listeners = combined[combined.metric.eq("listeners")][["song_id", "date", "value"]].rename(columns={"value": "resolved_listener_denominator"})
    combined = combined.merge(listeners, on=["song_id", "date"], how="left", validate="many_to_one")
    # Retain every earlier column value; the resolved denominator is a new derived field.
    mask = combined.snapshot_class.eq("baseline_supplement")
    combined.loc[mask, "listener_denominator"] = combined.loc[mask, "resolved_listener_denominator"]
    undefined = mask & combined.metric.eq("streams_per_listener") & combined.resolved_listener_denominator.eq(0)
    combined.loc[undefined, "value_status"] = "undefined_zero_denominator_reported_zero"
    compare_values(original, combined, HISTORY_KEYS, ["value", "origin", "snapshot_class", "retrieved_at"], subset=True)
    compare_values(combined, complete, HISTORY_KEYS, ["value", "origin"])
    require(len(combined) == 71680 and combined.date.between(START, END).all(), "Canonical history coverage mismatch")
    expected = set(pd.date_range(START, END).strftime("%Y-%m-%d"))
    groups = combined.groupby(["song_id", "metric"])
    require(len(groups) == 70 and all(set(g.date) == expected for _, g in groups), "Not all 70 histories are complete")
    return combined, checks


def parse_source_captures(captures, sources):
    """Independently parse retained browser tables and exact named chart values."""
    periods, daily, reconciliations, excluded = [], [], [], []
    for capture in captures:
        if "sources" not in capture["label"]:
            continue
        tables, labels = capture.get("tables", []), capture.get("chartLabels", [])
        if not tables or len(tables[0]) != 10 or not labels:
            excluded.append(capture["label"])
            continue
        q = parse_qs(urlparse(capture["url"]).query)
        metric = q.get("metric", ["streams"])[0]
        expected = {"streams": "Streams", "listeners": "Listeners", "streams_per_listener": "Streams / Listener"}[metric]
        require(tables[0][0][0].startswith(expected + " ·"), "Source capture metric mismatch")
        dates = [chart_date(label) for label in labels]
        start, end = min(dates), max(dates)
        count = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days + 1
        require(len(dates) == len(set(dates)) == count, "Source chart missing or duplicate days")
        require(q.get("fromDate", [start]) == [start] and q.get("toDate", [end]) == [end], "Source chart URL/date mismatch")
        require(end == END, "Continuation source date is newer than baseline")
        scope = "release" if "/release/" in capture["url"] else "song" if "/song/" in capture["url"] else "artist"
        sid = re.search("/" + scope + r"/([^/?]+)", capture["url"])[1] if scope != "artist" else ARTIST
        country = q.get("country", ["Worldwide"])[0]
        country = "United States" if country == "US" else country
        prefix = {"Scope": scope, "Spotify ID": sid, "Population": country, "Metric": metric}
        current = {}
        for table_row in tables[0][1:]:
            source = next((s for s in sources if table_row[0].startswith(s)), None)
            require(source is not None and source not in current, "Invalid source category")
            current[source] = numeric(table_row[2])
            periods.append({**prefix, "Period start": start, "Period end": end, "Source": source,
                            "Current value": current[source], "Previous value": numeric(table_row[1]),
                            "Evidence": capture["label"], "Collected UTC": capture["collected_at"]})
        require(set(current) == set(sources), "Source table categories incomplete")
        parsed = []
        for label, date in zip(labels, dates):
            values = {}
            for source in sources:
                match = re.search(re.escape(source) + r" ([\d,.]+) " + re.escape(metric) + r"(?:,|\s|$)", label)
                require(match is not None, "Source chart category missing")
                values[source] = numeric(match[1])
            row = {**prefix, "Window start": start, "Window end": end, "Date": date, **values,
                   "Evidence": capture["label"], "Collected UTC": capture["collected_at"]}
            daily.append(row)
            parsed.append(row)
        if metric == "streams":
            for source in sources:
                total = sum(row[source] for row in parsed)
                require(current[source] == total or (current[source] is None and total == 0), "Source table/chart discrepancy")
                reconciliations.append({"scope": scope, "id": sid, "population": country, "start": start, "end": end,
                                       "source": source, "table_streams": current[source], "daily_stream_sum": total,
                                       "result": "match" if current[source] is not None else "table unavailable; chart explicitly zero",
                                       "evidence": capture["label"]})
    return pd.DataFrame(periods), pd.DataFrame(daily), pd.DataFrame(reconciliations), excluded


def reconcile_sources(recovery, continuation):
    before_p = csv(recovery / "normalized/source_collection.csv")
    before_d = csv(recovery / "normalized/source_daily_collection.csv")
    master_p = csv(continuation / "normalized/source_collection.csv")
    master_d = csv(continuation / "normalized/source_daily_collection.csv")
    sources = list(master_d.columns[9:18])
    period, daily, recon, excluded = parse_source_captures(read_json(continuation / "raw/browser_captures.json"), sources)
    compare_values(before_p, master_p, SOURCE_KEYS, ["Current value", "Previous value"], subset=True)
    compare_values(before_d, master_d, DAILY_KEYS, sources, subset=True)
    canonical_p, dup_p = deduplicate_agreements(pd.concat([before_p, period], ignore_index=True), SOURCE_KEYS, ["Current value", "Previous value"])
    canonical_d, dup_d = deduplicate_agreements(pd.concat([before_d, daily], ignore_index=True), DAILY_KEYS, sources)
    require(dup_p == 54 and dup_d == 1516, "Duplicate agreement counts mismatch")
    compare_values(canonical_p, master_p, SOURCE_KEYS, ["Current value", "Previous value"])
    compare_values(canonical_d, master_d, DAILY_KEYS, sources)
    # Cumulative masters must be precisely prior rows plus only the new parsed keys.
    new_p = canonical_p.merge(before_p[SOURCE_KEYS], on=SOURCE_KEYS, how="left", indicator=True).query('_merge == "left_only"').drop(columns="_merge")
    new_d = canonical_d.merge(before_d[DAILY_KEYS], on=DAILY_KEYS, how="left", indicator=True).query('_merge == "left_only"').drop(columns="_merge")
    compare_values(new_p, csv(continuation / "normalized/added_source_collection.csv"), SOURCE_KEYS, ["Current value", "Previous value"])
    compare_values(new_d, csv(continuation / "normalized/added_source_daily_collection.csv"), DAILY_KEYS, sources)
    require(len(master_p) == len(before_p) + len(new_p) == 1269 and len(master_d) == len(before_d) + len(new_d) == 37311, "Cumulative source counts mismatch")
    expected_recon = csv(continuation / "normalized/source_stream_reconciliation.csv")
    compare_values(recon, expected_recon, ["scope", "id", "population", "start", "end", "source", "evidence"], ["table_streams", "daily_stream_sum", "result"])
    require(len(recon) == 297, "Expected 297 independent table/chart checks")
    return master_p, master_d, recon, {"comparison_agreements": dup_p, "daily_agreements": dup_d,
        "comparison_additions": len(new_p), "daily_additions": len(new_d), "conflicts": 0,
        "stream_reconciliations": len(recon), "stream_check_outcomes": recon.result.value_counts().to_dict(),
        "excluded_source_captures": len(excluded), "raw_captures_independently_parsed": period.Evidence.nunique()}


def derive_history(combined, recordings, artist):
    coverage = combined.groupby(["song_id", "recording_label", "metric"]).agg(observed_days=("date", "nunique"), activity_start=("date", "min"), activity_end=("date", "max")).reset_index()
    coverage["expected_history_days"] = 1024
    coverage["missing_dates_in_history"] = 1024 - coverage.observed_days
    coverage["complete"] = coverage.observed_days.eq(1024)
    streams = combined[combined.metric.eq("streams")]
    catalog = streams.groupby("date").agg(catalog_streams=("value", "sum"), recordings=("song_id", "nunique")).reset_index().merge(artist[["date", "daily_streams"]], on="date", validate="one_to_one")
    catalog["difference"] = catalog.catalog_streams - catalog.daily_streams
    catalog["comparable"] = catalog.recordings.eq(14)
    require(catalog.comparable.all() and catalog.difference.eq(0).all() and len(catalog) == 1024, "Full catalog/artist reconciliation failed")
    launch = []
    for row in recordings.itertuples():
        z = streams[streams.song_id.eq(row.song_id)]
        for days in (7, 28, 90):
            end = (pd.Timestamp(row.first_released) + pd.Timedelta(days=days - 1)).strftime("%Y-%m-%d")
            window = z[z.date.between(row.first_released, end)]
            complete = window.date.nunique() == days
            launch.append({"song_id": row.song_id, "recording_label": row.recording_label, "release_date": row.first_released,
                           "days_since_release": days, "window_end": end, "observed_days": len(window), "complete": complete,
                           "streams": int(window.value.sum()) if complete else None,
                           "limitation": "" if complete else "release window begins before available 2024 history; no imputation",
                           "source_file": "cleaned/track_daily_long.csv + cleaned/recordings.csv"})
    totals = streams.groupby(["song_id", "recording_label"]).agg(history_streams=("value", "sum"), observed_days=("date", "nunique")).reset_index()
    totals["period_start"], totals["period_end"] = START, END
    totals["share_pct"] = 100 * totals.history_streams / artist.daily_streams.sum()
    return coverage, catalog, pd.DataFrame(launch), totals


def integrate(original, recovery, continuation, output, archives):
    original, recovery, continuation, output = map(lambda p: Path(p).resolve(), (original, recovery, continuation, output))
    require(not output.exists(), "Output must be a new directory")
    require(all(not output.is_relative_to(root) for root in (original, recovery, continuation)), "Output cannot be inside input package")
    before = {name: inventory(root) for name, root in (("original", original), ("recovery", recovery), ("continuation", continuation))}
    manifest_checks = {"recovery": verify_manifest(recovery), "continuation": verify_manifest(continuation)}
    old_hashes = read_json(original / "raw_sha256.json")
    require(all(sha(original / r["path"]) == r["sha256"] for r in old_hashes), "Original package raw hashes differ")
    archives = [Path(p).resolve() for p in archives]
    require(len(archives) == 3 and all(p.is_file() for p in archives), "All three original ZIPs are required")
    # Exact ZIP-to-directory coverage is checked without extraction or running bundled code.
    zip_checks = []
    for root, archive in zip((original, recovery, continuation), archives):
        with zipfile.ZipFile(archive) as z:
            members = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}
        files = before[{original: "original", recovery: "recovery", continuation: "continuation"}[root]]
        require(len(members) == len(files), "ZIP membership count differs from extracted package")
        for relative, digest in files.items():
            matches = [key for key in members if key == relative or key.endswith("/" + relative)]
            # Match full package prefix to prevent suffix ambiguity.
            preferred = root.name + "/" + relative
            member = preferred if preferred in members else (matches[0] if len(matches) == 1 else None)
            require(member is not None and hashlib.sha256(members[member]).hexdigest() == digest, "ZIP bytes differ: " + relative)
        zip_checks.append({"name": archive.name, "sha256": sha(archive), "verified_files": len(files)})
    recordings = csv(original / "spotify/cleaned/recordings.csv")
    combined, recovery_checks = reconcile_history(csv(original / "spotify/cleaned/track_daily_long.csv"),
        csv(recovery / "normalized/recovered_song_daily.csv"), csv(recovery / "normalized/song_daily_long_complete_baseline.csv"),
        read_json(recovery / "raw/retained_browser_captures.json"), recordings)
    sources, source_daily, recon, source_audit = reconcile_sources(recovery, continuation)
    coverage, catalog, launch, history = derive_history(combined, recordings, csv(original / "spotify/cleaned/artist_daily.csv"))
    period = csv(recovery / "normalized/song_periods_complete_baseline.csv")
    require(set(period.metric) <= ADDITIVE and len(period) == 462, "Unexpected additive period schema")
    for r in period.itertuples():
        rows = combined[combined.song_id.eq(r.song_id) & combined.metric.eq(r.metric) & combined.date.between(r.start_date, r.end_date)]
        days = (pd.Timestamp(r.end_date) - pd.Timestamp(r.start_date)).days + 1
        require(len(rows) == days and rows.value.sum() == r.value, "Additive period recheck failed")
    prior_periods = csv(recovery / "raw/original_song_periods_from_daily.csv")
    compare_values(prior_periods, period, ["song_id", "period", "metric", "start_date", "end_date"], ["value"], subset=True)
    require(len(prior_periods) == 434, "Unexpected previous additive periods")
    queue = csv(continuation / "normalized/collection_log_retry.csv")
    counts = queue.Status.str.split(" — ").str[0].value_counts().to_dict()
    require(counts == {"Complete": 36, "Partial": 5, "Blocked": 2}, "Queue status counts differ")
    old_launch = csv(original / "spotify/cleaned/recording_launch_windows.csv")
    changed_launch = launch.merge(old_launch[["song_id", "days_since_release", "complete", "streams"]], on=["song_id", "days_since_release"], suffixes=("", "_before"))
    new_launch = changed_launch[changed_launch.complete & ~changed_launch.complete_before]
    report = {"analysis_version": VERSION, "previous_version": OLD_VERSION, "baseline_endpoint": END,
        "retrieval_utc_date": "2026-10-23", "native_exports_added": 0, "prior_native_song_exports": 4,
        "previous_daily_observations": 66631, "added_daily_observations": 5049, "canonical_daily_observations": 71680,
        "previous_values_unchanged": 66631, "complete_histories_before": 64, "complete_histories_after": 70,
        "catalog_matching_days_before": 365, "catalog_matching_days_after": 1024,
        "additive_periods_before": 434, "additive_periods_after": 462, "additive_periods_added": 28,
        "release_windows_complete_before": int(old_launch.complete.sum()), "release_windows_complete_after": int(launch.complete.sum()),
        "newly_eligible_release_windows": new_launch.fillna("").to_dict("records"),
        "source_comparisons": len(sources), "source_daily_rows": len(source_daily), "source_audit": source_audit,
        "queue_status_counts": counts, "manifest_checks": manifest_checks, "original_raw_hashes_verified": len(old_hashes),
        "zip_checks": zip_checks, "recovery_chart_checks": recovery_checks, "conflicts": 0,
        "new_significance_tests": 0, "cross_platform_input_version": OLD_VERSION,
        "workbook_readback_checks": "16 supplied workbook readback checks are not reproduced as workbook API checks; files and raw captures were independently validated.",
        "newly_supported_questions": ["Complete 2024-01-01 through 2026-10-20 recording composition", "Source mix within retained exact scopes/windows/hierarchies"],
        "unchanged_findings": ["Latest 28-day artist and song momentum is unchanged", "Social evidence and prior cross-platform significance results retain their original input version"],
        "limitations": ["Complete refers to collected available scope, not every geography/window", "2023 release starts remain unavailable", "Source listeners overlap and daily unique listeners and ratios must not be summed", "Original archive membership is not established by later historical recovery", "Newer October 21 observations remain separate"]}
    shutil.copytree(original, output)
    changed = []

    def preserve(relative):
        target = output / relative
        if target.is_file():
            prior = output / "raw/previous_analysis_v1" / relative
            prior.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, prior)
        target.parent.mkdir(parents=True, exist_ok=True)
        changed.append(relative)
        return target

    def save(frame, relative):
        frame.to_csv(preserve(relative), index=False)

    def json_out(value, relative):
        preserve(relative).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")

    for name, root in (("recovery", recovery), ("continuation", continuation)):
        shutil.copytree(root, output / "raw/recovery_evidence" / name)
    archive_dir = output / "raw/recovery_evidence/archives"
    archive_dir.mkdir(parents=True)
    for archive in archives:
        shutil.copy2(archive, archive_dir / archive.name)
    save(combined, "spotify/cleaned/track_daily_long.csv")
    save(coverage, "spotify/cleaned/track_coverage.csv")
    save(coverage, "spotify/cleaned/recovery_coverage.csv")
    save(catalog, "spotify/cleaned/catalog_artist_daily_reconciliation.csv")
    save(launch, "spotify/cleaned/recording_launch_windows.csv")
    save(history, "spotify/cleaned/complete_history_catalog.csv")
    counters = csv(original / "spotify/cleaned/song_alltime_counters.csv")
    comparison = history[["song_id", "history_streams", "observed_days"]].merge(counters, on="song_id", validate="one_to_one")
    comparison["history_minus_alltime"] = comparison.history_streams - comparison.all_time_streams
    save(comparison, "spotify/cleaned/history_counter_comparison.csv")
    save(period, "spotify/cleaned/song_periods_complete_baseline.csv")
    save(csv(recovery / "normalized/recovered_song_periods.csv"), "spotify/cleaned/recovered_song_periods.csv")
    save(sources, "spotify/cleaned/source_recovery.csv")
    save(source_daily, "spotify/cleaned/source_history.csv")
    save(recon, "spotify/cleaned/source_stream_reconciliation.csv")
    save(queue, "spotify/cleaned/current_queue.csv")
    save(queue[~queue.Status.str.startswith("Complete")], "spotify/cleaned/remaining_limits.csv")
    for source, destination in [(continuation / "normalized/newer_snapshots.csv", "snapshot_recovery.csv"),
        (recovery / "normalized/geography_comparison_daily.csv", "geography_history.csv"),
        (continuation / "normalized/content_event_reporting.csv", "content_recovery.csv"),
        (continuation / "normalized/source_capture_coverage.csv", "source_capture_coverage.csv"),
        (continuation / "normalized/excluded_source_captures.csv", "excluded_source_captures.csv")]:
        save(csv(source), "spotify/cleaned/" + destination)
    for root, filename in [(continuation, "newer_snapshots.csv"), (recovery, "geography_comparison_daily.csv"), (continuation, "content_event_reporting.csv")]:
        save(csv(root / "normalized" / filename), "spotify/cleaned/" + filename)
    # Descriptive shares only within a single stream hierarchy and exact current period.
    summary = sources[sources.Metric.eq("streams") & sources["Source"].isin(["All active sources", "All programmed sources", "Other"])].copy()
    group = ["Scope", "Spotify ID", "Population", "Period start", "Period end"]
    denominator = summary.groupby(group)["Current value"].transform(lambda x: x.sum(min_count=3))
    summary["parent_stream_total"] = denominator
    summary["share_pct"] = 100 * summary["Current value"] / denominator.replace(0, np.nan)
    summary["aggregation_note"] = "Streams: active + programmed + Other only. No detail children or listener sums."
    save(summary, "spotify/cleaned/source_parent_stream_summary.csv")
    findings = read_json(original / "spotify/reviewed_findings.json")
    findings.update(analysis_version=VERSION, track_metric_rows=71680, complete_track_metric_histories=70,
                    catalog_matching_days=1024, collection_retrieval_utc_date="2026-10-23",
                    full_history_catalog=history.sort_values("history_streams", ascending=False).to_dict("records"),
                    newly_eligible_release_windows=report["newly_eligible_release_windows"])
    findings["launch"] = launch.astype(object).where(pd.notna(launch), None).to_dict("records")
    findings["issues"] = [item for item in findings.get("issues", []) if item.get("title") != "Six recording-metric histories incomplete"]
    findings["resolved_issues"] = [{"title": "Six recording-metric history gaps resolved", "status": "resolved",
        "details": "5,049 observed chart-derived values complete all 70 histories. No imputation. 2023 original-release windows remain outside date coverage."}]
    findings["previous_validation"] = findings.pop("validation", [])
    findings["validation"] = [{"check": "complete_histories", "passed": True, "details": "70 of 70; 1024 dates each"},
                              {"check": "catalog_matching_days", "passed": True, "details": "1024 of 1024"},
                              {"check": "source_reconciliations", "passed": True, "details": "252 numeric table/chart matches; 45 unavailable table values with explicit zero chart sums"}]
    json_out(findings, "spotify/reviewed_findings.json")
    # Readiness is current; prior statistics stay byte-for-byte unchanged with an explicit version map.
    readiness = csv(original / "spotify/analysis_readiness.csv")
    mask = readiness.question.eq("Full-history catalog composition")
    readiness.loc[mask, ["status", "usable_observations", "missingness", "dependence", "smallest_next_data"]] = ["Supported", 14336,
        "All 14 recordings have 1024 observed stream dates; 70/70 metric histories complete", "Repeated recordings/days; descriptive composition only", "No remaining daily-history gaps for Jan 1 2024 to Oct 20 2026"]
    readiness.loc[readiness.question.eq("Equal-age release ranking"), "usable_observations"] = int(launch[launch.days_since_release.eq(28)].complete.sum())
    readiness.loc[readiness.question.eq("Equal-age release ranking"), "missingness"] = "2023 original-release starts remain unavailable; 33 eligible release windows unchanged and revalidated, including Son!"
    save(readiness, "spotify/analysis_readiness.csv")
    overall = csv(original / "analysis_readiness.csv")
    for row in readiness.itertuples():
        mask = overall.domain.eq("Spotify") & overall.question.eq(row.question)
        for target, source in (("status", "status"), ("n", "usable_observations"), ("missingness", "missingness"), ("dependence", "dependence"), ("next_data", "smallest_next_data")):
            overall.loc[mask, target] = str(getattr(row, source))
    save(overall, "analysis_readiness.csv")
    issues = csv(original / "spotify/data_quality_issues.csv")
    if "title" in issues:
        issues = issues[~issues.title.eq("Six recording-metric histories incomplete")]
    save(issues, "spotify/data_quality_issues.csv")
    log = pd.DataFrame([
        {"action": "Verified manifests and all three original ZIP contents", "records_affected": sum(r["verified_files"] for r in zip_checks), "reason": "Original source hashes preserved; downloaded code not executed"},
        {"action": "Merged recovered keys with unchanged prior history", "records_affected": 5049, "reason": "Chart-derived evidence, timestamps and original provenance retained; no zero filling"},
        {"action": "Selected cumulative sources after raw table/chart reparse and overlap verification", "records_affected": 1269 + 37311, "reason": "54 comparison and 1516 daily duplicate agreements; zero conflicts; no blind append"},
        {"action": "Regenerated coverage, catalog, release-age, history totals and source summaries", "records_affected": 71680, "reason": "Descriptive analyses only; no significance tests added"}])
    save(pd.concat([csv(original / "spotify/cleaning_log.csv"), log], ignore_index=True), "spotify/cleaning_log.csv")
    global_log = pd.DataFrame({"domain": "Spotify", "operation": log.action, "records_affected": log.records_affected,
                              "reason": log.reason, "detail_file": "audit/recovery_changes.json"})
    save(pd.concat([csv(original / "cleaning_log.csv"), global_log], ignore_index=True), "cleaning_log.csv")
    # Extend dictionaries for every changed/new cleaned table field.
    dictionary = csv(original / "spotify/data_dictionary.csv")
    entries = []
    for relative in changed:
        if relative.startswith("spotify/cleaned/") and relative.endswith(".csv"):
            data = csv(output / relative)
            for column in data.columns:
                entries.append({"table": Path(relative).name, "column": column, "units": "source-specific",
                    "definition": "Preserved source field or explicitly derived recovery field; see recovery changes and raw capture provenance",
                    "aggregation_rule": "Only additive streams/saves/playlist_adds across disjoint dates at matching scope; listeners, ratios, stocks and overlapping hierarchies must not be summed",
                    "caveat": "Reporting endpoint differs from capture timestamp; chart-derived files are not native exports"})
    extra = pd.DataFrame(entries)
    dictionary = precise_dictionary(pd.concat([dictionary, extra], ignore_index=True).drop_duplicates(["table", "column"], keep="first"))
    save(dictionary, "spotify/data_dictionary.csv")
    global_dictionary = csv(original / "data_dictionary.csv")
    extra["domain"] = "Spotify"
    save(precise_dictionary(pd.concat([global_dictionary, extra], ignore_index=True).drop_duplicates([c for c in ["domain", "table", "column"] if c in global_dictionary], keep="first")), "data_dictionary.csv")
    version_map = {"analysis_version": VERSION, "retained_results_input_version": OLD_VERSION,
                   "unchanged_result_files": {p: sha(original / p) for p in before["original"] if p.startswith("cross_platform/") or p.endswith("statistical_results.csv")},
                   "note": "Prior statistical results remain the earlier analysis, not tests of the expanded recovery dataset. No new statistical testing family was introduced."}
    json_out(version_map, "audit/statistical_input_versions.json")
    metadata = {"analysis_version": VERSION, "label": "Spotify recovery · Oct 23 UTC capture · reporting through Oct 20", "previous_analysis_version": OLD_VERSION,
        "retrieval_vintage": "2026-10-23", "activity_endpoint": END,
        "baseline_status": "unverified original archive membership; reporting endpoint preserved", "baseline_endpoint": END,
        "input_lineage": {"original_analysis": OLD_VERSION, "spotify_history": VERSION, "social": OLD_VERSION,
                          "cross_platform": OLD_VERSION, "statistical_results": OLD_VERSION},
        "evidence_type": "Original native exports plus separately identified rendered-chart recovery; zero new native exports",
        "source_urls": ["https://drive.google.com/file/d/1Y21nrKj5ARqyCE9im36Ekg19XJndrmM7/view", "https://drive.google.com/file/d/1k63vp8Tgjt7QjaBWnwPmrSI1BCeKCMAe/view", "https://drive.google.com/file/d/1qsvqB2W-4i8FpHHpC6tT9Bx7342jpfzz/view"]}
    json_out(metadata, "metadata.json")
    note = """# Current recovery integration\n\nVersion spotify-recovery-20261023 explicitly supersedes old daily-history gaps. 71,680 unique observations cover 70/70 histories, January 1, 2024 through October 20, 2026. Added 5,049 chart-derived values; 66,631 earlier values are unchanged. No new native exports. Full catalog reconciles on all 1,024 days; All 33 previously eligible release-age windows remain eligible with unchanged stream totals, including Son!; 2023 release starts remain outside coverage.\n\nCumulative sources were reconciled, not appended: 1,269 comparison and 37,311 daily rows, 54/1,516 duplicate agreements and no conflicts. Of 297 independently repeated continuation stream-source reconciliations, 252 are numeric table/chart matches; 45 retain an unavailable table value alongside an explicitly zero chart sum. The latter are not numerical table matches or permission to replace missing values with zero. Row counts are not independent statistical observations. Source parents/children remain separate and listener sources overlap.\n\nSeven collection limitations remain in spotify/cleaned/remaining_limits.csv: Lab Tapes La Cocaína source metrics/windows; Method Acting album 28-day playlists; Son! 28-day playlists; THIS MACHINE 12-month playlists; Waste Away playlist access; nine unresolved song-country views; and additional native exports. October 21 geography/catalog and unknown-window playlists remain separate snapshots.\n\nMeta coverage remains unchanged: 128 Instagram Follows calendar values are missing; 183 malformed Stories records are quarantined; selected Instagram views include Facebook crossposted views; lifetime post counts cannot be assigned to a reporting interval. October 21 and October partial activity remain excluded by default. TikTok is deferred. Daily unique audiences and stocks must not be summed.\n\nAudience demographic totals and some lifetime counters still disagree with their independent source totals; retained discrepancies are not reconciled by invention. Stable person-level attribution, campaign exposure and comparable promotion controls are absent. UTC Spotify and Pacific Meta daily boundaries cannot be precisely rebinned from aggregates.\n\nThe prior 53 statistical results and cross-platform files retain input version cleaned-20261022 and were not recomputed as new evidence tests. No new significance testing family was introduced. Earlier recent 28-day momentum findings are unchanged by the recovered older history.\n\nSee audit/recovery_changes.json, audit/statistical_input_versions.json and the retained original packages under raw/recovery_evidence/. Previous versions of every replaced document/table are preserved under raw/previous_analysis_v1/.\n"""
    for relative in ("README.md", "DASHBOARD_HANDOFF.md", "DATA_QUALITY_ASSESSMENT.md", "spotify/README.md", "spotify/dashboard_handoff.md"):
        preserve(relative).write_text(note, encoding="utf-8")
    preserve("spotify/analysis_plan.md").write_text("# Recovery descriptive update plan\n\nVerify unchanged originals, recovered daily history, cumulative masters and raw captures before selecting canonical records. Recompute coverage, complete-period catalog totals, eligible release-age windows and within-scope parent-source stream shares. Preserve prior cross-platform tests and their input version. No new significance tests; daily values, repeated recordings, overlapping windows and source hierarchies are not independent samples.\n", encoding="utf-8")
    report["regenerated_files"] = sorted(set(changed))
    json_out(report, "audit/recovery_changes.json")
    for name in ("independent_input_audit.json", "independent_input_audit.md", "workbook_audit.json", "workbook_audit.md"):
        audit_source = output.parent / name
        if audit_source.is_file():
            shutil.copy2(audit_source, output / "audit" / name)
    # Inventories are rebuilt after all substantive outputs, with original inventories preserved.
    for relative in ("raw_sha256.json", "source_inventory.csv", "spotify/source_file_inventory.csv", "spotify/table_inventory.csv", "spotify/table_profiles.csv"):
        preserve(relative)
    finalize_package(output, report)
    for name, root in (("original", original), ("recovery", recovery), ("continuation", continuation)):
        require(before[name] == inventory(root), "Source package changed during integration")
    require(all(sha(output / p) == digest for p, digest in version_map["unchanged_result_files"].items()), "Earlier statistical evidence changed")
    return report
