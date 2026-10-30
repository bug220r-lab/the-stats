"""Validate a new Meta export collection without changing raw files or databases.

Write a new output directory. Campaign summaries, daily ads, sparse Follows and
lifetime Stories remain separate grains. Missing dates/values never become zero.
Manual Follows probes require explicit structured daily observations and evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stats_app.analysis_repository import AnalysisRepository, load_registered_analysis

VERSION = "1.0.0"
STATUS_FIELDS = ["dataset", "status", "detail", "evidence_ref", "captured_at_utc"]
KNOWN_ACCOUNT = "17841454335424545"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_rows(frame):
    return json.loads(frame.to_json(orient="records", force_ascii=False))


def decode(raw):
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def native_csv(path, header_predicate=None):
    """Keep ragged records quarantined; never pad or shift native columns."""
    records = list(csv.reader(io.StringIO(decode(Path(path).read_bytes()), newline="")))
    header_index = next((i for i, row in enumerate(records) if row and (header_predicate(row) if header_predicate else len(row) > 2)), None)
    if header_index is None:
        raise ValueError(f"No recognized CSV header: {path}")
    header = records[header_index]
    if len(header) != len(set(header)) or any(not x for x in header):
        raise ValueError(f"Duplicate or empty native column: {path}")
    valid, bad = [], []
    for record_no, values in enumerate(records[header_index + 1:], header_index + 2):
        if not values or not any(values):
            continue
        if len(values) != len(header):
            bad.append(dict(source_record=record_no, expected_fields=len(header), actual_fields=len(values), raw_record_json=json.dumps(values, ensure_ascii=False), reason="native_field_count_mismatch_no_alignment_guess"))
        else:
            valid.append((record_no, dict(zip(header, values))))
    return header, valid, bad


def number(raw):
    """An empty native numeric field is unavailable, while explicit zero is observed."""
    value = "" if raw is None else str(raw).strip()
    if value == "":
        return "", "missing_source_blank"
    if value in {"N/A", "n/a"} or (value and all(c in "-—–‐‑‒−" for c in value)):
        return "", "unavailable_source_marker"
    try:
        parsed = Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("Invalid exact numeric value: " + value) from exc
    if not parsed.is_finite():
        raise ValueError("Non-finite native numeric value")
    return format(parsed, "f"), "observed_zero" if parsed == 0 else "observed"


def calendar_date(raw):
    value = str(raw).strip()[:10]
    return date.fromisoformat(value).isoformat()


def utc_stamp(value):
    if not value:
        return ""
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Capture/acquisition timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def metadata_for(root, path):
    """Read explicit collector metadata; filesystem mtimes are bounds, not captures."""
    relative = path.relative_to(root).as_posix()
    result = {}
    for manifest_name in ["collection_manifest.json", "observation_manifest.json"]:
        manifest = root / manifest_name
        if manifest.is_file():
            value = json.loads(manifest.read_text(encoding="utf-8-sig"))
            for item in value.get("files", []):
                if item.get("file", item.get("source_file")) in {relative, path.name}:
                    result.update(item)
    for sidecar in [path.with_suffix(".metadata.json"), path.with_suffix(path.suffix + ".metadata.json")]:
        if sidecar.is_file():
            result.update(json.loads(sidecar.read_text(encoding="utf-8-sig")))
    result["captured_at_utc"] = utc_stamp(result.get("captured_at_utc", ""))
    result["acquired_at_utc"] = utc_stamp(result.get("acquired_at_utc", ""))
    result["filesystem_modified_at_utc"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    result["capture_precision"] = result.get("capture_precision") or ("explicit_collector_timestamp" if result["captured_at_utc"] else "exact_capture_unknown")
    result["reporting_start"] = result.get("reporting_start", result.get("requested_window_start", ""))
    result["reporting_end"] = result.get("reporting_end", result.get("requested_window_end", ""))
    result["source_sha256"] = sha(path)
    if not result.get("ad_account_id") and result.get("source_url"):
        result["ad_account_id"] = parse_qs(urlsplit(result["source_url"]).query).get("act", [""])[0]
    return result


def base_meta(root, path, metadata, record_no):
    return dict(source_file=path.relative_to(root).as_posix(), source_sha256=metadata.get("source_sha256") or sha(path), source_record=record_no,
                captured_at_utc=metadata["captured_at_utc"], acquired_at_utc=metadata["acquired_at_utc"],
                capture_precision=metadata["capture_precision"], source_url=metadata.get("source_url", ""),
                source_identity_evidence=metadata.get("identity_evidence_ref", metadata.get("evidence_ref", "")),
                filesystem_modified_at_utc=metadata["filesystem_modified_at_utc"])


def find_column(header, *aliases):
    lower = {x.casefold(): x for x in header}
    return next((lower[a.casefold()] for a in aliases if a.casefold() in lower), None)


def exact_values(rows, column):
    values = []
    for row in rows:
        value, status = number(row.get(column, ""))
        if status in {"observed", "observed_zero"}:
            values.append(Decimal(value))
    return values


def ads_rows(root, path, metadata):
    header, records, bad = native_csv(path, lambda row: "Reporting starts" in row and "Reporting ends" in row)
    no_data_notice = bool(not records and len(bad) == 1 and json.loads(bad[0]["raw_record_json"]) == ["No data available."])
    if bad and not no_data_notice:
        raise ValueError("Ads export has ragged rows; requires review before normalization: " + path.name)
    level = "ad" if find_column(header, "Ad ID", "Ad name") else "ad_set" if find_column(header, "Ad set ID", "Ad set name") else "campaign"
    id_column = find_column(header, {"ad": "Ad ID", "ad_set": "Ad set ID", "campaign": "Campaign ID"}[level])
    money = [m.group(1) for column in header if (m := re.search(r"Amount spent \(([A-Z]{3})\)", column))]
    if len(set(money)) > 1:
        raise ValueError("Mixed spend currencies in one native export")
    currency = money[0] if money else metadata.get("currency", "")
    count_columns = {"Results", "Reach", "Impressions", "Link clicks", "Clicks (all)", "Landing page views", "Results (initial)", "shop_clicks"}
    numeric_columns = [h for h in header if h in count_columns or h == "Frequency" or h.startswith(("Amount spent (", "Cost per ", "CPM (", "CPC (", "CTR ("))]
    rows, keys = [], []
    for record_no, native in records:
        start, end = calendar_date(native["Reporting starts"]), calendar_date(native["Reporting ends"])
        if start > end:
            raise ValueError("Ads reporting starts after it ends")
        statuses = {}
        for name in numeric_columns:
            value, status = number(native[name]); statuses[name] = status
            if value != "" and Decimal(value) < 0:
                raise ValueError("Negative native ad metric requires review")
        ad_id = native.get(find_column(header, "Ad ID"), "")
        campaign_id = native.get(find_column(header, "Campaign ID"), "")
        ad_set_id = native.get(find_column(header, "Ad set ID"), "")
        account_id = native.get(find_column(header, "Account ID"), "") or str(metadata.get("ad_account_id", ""))
        row = {**native, **base_meta(root, path, metadata, record_no), "ad_account_id": account_id,
               "campaign_id": campaign_id, "ad_set_id": ad_set_id, "ad_id": ad_id,
               "reporting_level": level, "reporting_start": start, "reporting_end": end,
               "reporting_timezone": metadata.get("reporting_timezone", ""), "currency": currency,
               "attribution_setting": native.get("Attribution setting", metadata.get("attribution_setting", "")),
               "metric_platform_scope": metadata.get("metric_platform_scope", "Meta ads; publisher platform/placement not supplied"),
               "breakdowns_json": json.dumps(metadata.get("breakdowns", {}), ensure_ascii=False),
               "time_grain": "day" if start == end else "native_reporting_window",
               "selected_ui_start": metadata.get("reporting_start", ""), "selected_ui_end": metadata.get("reporting_end", ""),
               "native_window_vs_ui": "differs" if metadata.get("reporting_end") and end != metadata["reporting_end"] and start != end else "daily_breakdown_or_not_verified",
               "metric_value_status_json": json.dumps(statuses, ensure_ascii=False),
               "native_identity_status": "stable_native_id" if id_column and native[id_column] else "source_row_identity_only_native_id_absent",
               "observation_id": hashlib.sha256(((metadata.get("source_sha256") or sha(path)) + ":" + str(record_no)).encode()).hexdigest()[:24],
               "measurement_type": "paid_delivery_daily" if start == end else "paid_delivery_native_window",
               "aggregation_rule": "Keep one delivery level/export/breakdown/window. Never add campaign summaries to ad daily rows; reach and ratios are nonadditive.",
               "destination_status": "not_identified_by_link_click_metric"}
        rows.append(row)
        if id_column and native[id_column]:
            keys.append((account_id, native[id_column], start, end, row["breakdowns_json"]))
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate stable ad/campaign/date grain in a single export")
    actual_start = min((r["reporting_start"] for r in rows), default="")
    actual_end = max((r["reporting_end"] for r in rows), default="")
    spend_values = exact_values(rows, "Amount spent (" + currency + ")")
    metric_coverage = {}
    for name in numeric_columns:
        values = exact_values(rows, name)
        additive = name in {"Impressions", "Link clicks", "Clicks (all)", "Landing page views", "Amount spent (" + currency + ")"}
        metric_coverage[name] = dict(observed_rows=len(values), unavailable_rows=len(rows) - len(values), observed_sum=str(sum(values)) if values and additive else "",
                                     sum_is_additive=additive)
    entity_dates = {}
    for entity in sorted({r["ad_id"] for r in rows if r["ad_id"]}):
        dates = sorted({r["reporting_start"] for r in rows if r["ad_id"] == entity and r["time_grain"] == "day"})
        if dates:
            expected = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days + 1
            entity_dates[entity] = dict(start=dates[0], end=dates[-1], observed_dates=len(dates), calendar_days=expected, explicit_daily_calendar_complete=len(dates) == expected)
    return rows, {"file": path.relative_to(root).as_posix(), "rows": len(rows), "reporting_level": level,
                  "export_status": "native_no_data_available_notice" if no_data_notice else "native_rows_available" if rows else "header_only_no_rows",
                  "requested_start": metadata.get("reporting_start", ""), "requested_end": metadata.get("reporting_end", ""),
                  "ad_account_id": str(metadata.get("ad_account_id", "")), "source_sha256": metadata.get("source_sha256", sha(path)),
                  "captured_at_utc": metadata["captured_at_utc"], "acquired_at_utc": metadata["acquired_at_utc"],
                  "native_start": actual_start, "native_end": actual_end,
                  "requested_window_vs_native": "no_native_rows" if not rows else "matches" if (actual_start, actual_end) == (metadata.get("reporting_start"), metadata.get("reporting_end")) else "differs_or_requested_unknown",
                  "native_id_missing_rows": sum(r["native_identity_status"] != "stable_native_id" for r in rows),
                  "unique_ad_ids": len({r["ad_id"] for r in rows if r["ad_id"]}), "unique_campaign_ids": len({r["campaign_id"] for r in rows if r["campaign_id"]}),
                  "entity_date_coverage_json": json.dumps(entity_dates), "metric_coverage_json": json.dumps(metric_coverage),
                  "currency": currency, "reporting_timezone": metadata.get("reporting_timezone", ""),
                  "spend_total_native_rows": str(sum(spend_values)) if spend_values else "",
                  "daily_rows": sum(r["time_grain"] == "day" for r in rows)}


def follow_rows(root, path, metadata):
    header, records, bad = native_csv(path, lambda row: "Date" in row and "Primary" in row)
    if bad:
        raise ValueError("Follows export has malformed rows")
    title = decode(path.read_bytes()).splitlines()[:3]
    if not any("follows" in line.casefold() for line in title):
        raise ValueError("The export title does not identify Follows")
    if str(metadata.get("selected_account_id", KNOWN_ACCOUNT)) != KNOWN_ACCOUNT:
        raise ValueError("Follows account differs from the retained band account")
    rows, days = [], set()
    for record_no, native in records:
        day = calendar_date(native["Date"])
        if day in days:
            raise ValueError("Duplicate date in native Follows export")
        days.add(day)
        value, status = number(native["Primary"])
        if value != "" and (Decimal(value) < 0 or Decimal(value) != int(Decimal(value))):
            raise ValueError("Follows event count must be a nonnegative integer")
        rows.append(dict(**base_meta(root, path, metadata, record_no), platform_selected="Instagram", selected_account_id=metadata.get("selected_account_id", KNOWN_ACCOUNT),
                         metric_platform_scope="Instagram", metric="follows", date=day, value=value, value_status=status,
                         value_raw=native["Primary"], date_raw=native["Date"], reporting_timezone=metadata.get("reporting_timezone", ""),
                         reporting_start=metadata.get("reporting_start", ""), reporting_end=metadata.get("reporting_end", ""),
                         measurement_type="daily_follows_event_count", source_kind="native_export", absent_dates_treatment="unavailable_not_zero"))
    return rows


def manual_follows(root):
    path = next((p for p in [root / "manual_follows_observations.json", root / "raw/follows_daily_observations.json"] if p.is_file()), None)
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = payload if isinstance(payload, list) else payload.get("observations", [])
    result = []
    for no, item in enumerate(rows, 1):
        if item.get("metric", "follows") != "follows" or item.get("grain", "day") != "day":
            raise ValueError("Manual Follows requires explicit daily grain")
        start = calendar_date(item.get("reporting_start", item["date"]))
        end = calendar_date(item.get("reporting_end", item["date"]))
        day = calendar_date(item["date"])
        if start != day or end != day or not item.get("evidence_ref"):
            raise ValueError("Manual Follows must cite a single-day observation and saved evidence")
        evidence = (root / item["evidence_ref"]).resolve()
        if not evidence.is_relative_to(root.resolve()) or not evidence.is_file():
            raise ValueError("Manual Follows evidence path is absent or unsafe")
        value, status = number(item.get("value", ""))
        if status not in {"observed", "observed_zero"} or not item.get("captured_at_utc"):
            raise ValueError("Manual Follows requires an explicit numeric daily value and capture timestamp")
        if Decimal(value) < 0 or Decimal(value) != int(Decimal(value)):
            raise ValueError("Manual Follows must be a nonnegative integer")
        source_url_raw = item.get("source_url", "")
        found_url = re.search(r'URL: "([^"]+)"', source_url_raw)
        source_url = found_url.group(1) if found_url else source_url_raw
        query = parse_qs(urlsplit(source_url).query)
        if query.get("asset_id") != ["118246571240106"] or str(item.get("selected_account_id", KNOWN_ACCOUNT)) != KNOWN_ACCOUNT:
            raise ValueError("Manual Follows selected asset/account differs from retained band identity")
        encoded = query.get("time_range", [""])[0]
        for _ in range(4):
            if encoded.startswith("{"):
                break
            encoded = unquote(encoded)
        try:
            bounds = json.loads(encoded)
        except ValueError as exc:
            raise ValueError("Manual daily probe URL does not preserve exact selected dates") from exc
        if bounds.get("start") != day or bounds.get("end") != day or query.get("platform") != ["Instagram"]:
            raise ValueError("Manual probe date/platform differs from its URL evidence")
        evidence_text = evidence.read_text(encoding="utf-8-sig")
        follows_section = evidence_text.split("heading Follows", 1)[-1] if "heading Follows" in evidence_text else ""
        if source_url not in evidence_text or not follows_section:
            raise ValueError("Manual Follows must match the retained browser URL and Follows panel")
        if Decimal(value) == 0 and not (re.search(r"\btext 0\s*$", follows_section, re.M) and "No activity during selected date range" in follows_section):
            raise ValueError("A manual zero requires explicit zero and no-activity evidence in the daily Follows panel")
        if Decimal(value) > 0 and not re.search(r"\btext " + re.escape(str(int(Decimal(value)))) + r"\s*$", follows_section, re.M):
            raise ValueError("Manual Follows positive count requires exact displayed numeric evidence")
        result.append(dict(platform_selected="Instagram", selected_account_id=str(item.get("selected_account_id", KNOWN_ACCOUNT)),
                           metric_platform_scope="Instagram", metric="follows", date=day, value=value, value_status=status,
                           value_raw=str(item["value"]), reporting_start=start, reporting_end=end, reporting_timezone=item.get("reporting_timezone", ""),
                           measurement_type="daily_follows_event_count", source_kind="manual_daily_ui_observation", source_file=path.relative_to(root).as_posix(),
                           source_sha256=sha(path), source_record=no, captured_at_utc=utc_stamp(item["captured_at_utc"]),
                           source_url=source_url, source_url_raw=source_url_raw, source_value_status=item.get("value_status", ""),
                           evidence_ref=item["evidence_ref"], evidence_sha256=sha(evidence),
                           absent_dates_treatment="unavailable_not_zero"))
    return result


def compare_follows(new, prior):
    old = {(str(r["selected_account_id"]), r["date"]): r for r in prior if r["platform_selected"] == "Instagram" and r["metric"] == "follows"}
    rows = []
    for item in new:
        previous = old.get((str(item["selected_account_id"]), item["date"]))
        value = Decimal(item["value"]) if item["value"] != "" else None
        before = Decimal(str(previous["value"])) if previous and previous["value"] is not None else None
        status = "new_date_outside_prior" if previous is None else "prior_missing_resolved_by_explicit_daily_evidence" if before is None and value is not None else "both_missing" if before is None else "matches_prior_observation" if before == value else "conflicts_with_prior_observation"
        if previous is not None and item.get("reporting_timezone") != "Pacific Time":
            status = "comparison_requires_verified_matching_timezone"
        rows.append({**item, "prior_value": "" if before is None else str(before), "prior_value_status": previous.get("value_status", "") if previous else "date_absent",
                     "comparison_status": status, "canonical_update_applied": False})
    by_day = {}
    for row in rows:
        if row["value"] == "":
            continue
        key = (row["selected_account_id"], row["date"])
        if key in by_day and Decimal(by_day[key]) != Decimal(row["value"]):
            raise ValueError("New native/manual Follows evidence disagrees for one date")
        by_day[key] = row["value"]
    return rows


def resolved_follows(prior, comparisons, database_sha256, asset_sha256, catalog_hashes=None):
    """Build a new daily view, retaining old observations and explicit repair lineage."""
    catalog_hashes = catalog_hashes or {}
    rows, partial = [], []
    keys = set()
    for record_no, old in enumerate(prior, 2):
        if old["platform_selected"] != "Instagram" or old["metric"] != "follows":
            continue
        key = (str(old["selected_account_id"]), old["date"])
        if key in keys:
            raise ValueError("Predecessor Follows contains duplicate daily grain")
        keys.add(key)
        evidence = [r for r in comparisons if (str(r["selected_account_id"]), r["date"]) == key]
        conflicts = [r for r in evidence if r["comparison_status"] == "conflicts_with_prior_observation"]
        repairs = [r for r in evidence if r["comparison_status"] == "prior_missing_resolved_by_explicit_daily_evidence"]
        inherited = old["value"] is not None
        chosen = repairs[0] if not inherited and repairs else None
        value, value_status = number(old["value"]) if inherited else (chosen["value"], chosen["value_status"]) if chosen else ("", old["value_status"])
        old_source = "raw/meta/" + old["source_file"]
        row = {**old, "value": value, "value_status": value_status,
               "source_kind": "inherited_observed_daily_value" if inherited else "verified_daily_repair" if chosen else "unresolved_predecessor_gap",
               "resolution_status": "prior_observation_retained_conflicting_new_evidence" if conflicts else "inherited_observation" if inherited else "explicit_daily_evidence_resolved" if chosen else "unresolved",
               "prior_value": old["value"], "prior_value_status": old["value_status"],
               "predecessor_database_sha256": database_sha256, "predecessor_asset": "social/account_daily.csv",
               "predecessor_asset_sha256": asset_sha256, "predecessor_csv_record": record_no,
               "predecessor_snapshot_timestamp": old.get("snapshot_timestamp", ""),
               "snapshot_timestamp": chosen.get("captured_at_utc", "") if chosen else old.get("snapshot_timestamp", ""),
               "snapshot_class": "collected_2026-10-23_daily_repair_not_original_baseline" if chosen else old.get("snapshot_class", ""),
               "reporting_window_start": chosen.get("reporting_start", old["date"]) if chosen else old.get("reporting_window_start", ""),
               "reporting_window_end": chosen.get("reporting_end", old["date"]) if chosen else old.get("reporting_window_end", ""),
               "value_raw": chosen.get("value_raw", chosen["value"]) if chosen else old.get("value_raw", ""),
               "predecessor_raw_file": old_source, "predecessor_raw_sha256": catalog_hashes.get(old_source, ""),
               "source_file": chosen["source_file"] if chosen else old_source,
               "source_sha256": chosen["source_sha256"] if chosen else catalog_hashes.get(old_source, ""),
               "source_record": chosen["source_record"] if chosen else old.get("source_record"),
               "captured_at_utc": chosen.get("captured_at_utc", "") if chosen else old.get("snapshot_timestamp", ""),
               "evidence_ref": chosen.get("evidence_ref", "") if chosen else "",
               "evidence_sha256": chosen.get("evidence_sha256", "") if chosen else "",
               "source_url": chosen.get("source_url", "") if chosen else old.get("source_url", ""),
               "supporting_new_observations_json": json.dumps([{k: r.get(k, "") for k in ["source_file", "source_sha256", "source_record", "evidence_ref", "evidence_sha256", "captured_at_utc", "comparison_status", "value"]} for r in evidence]),
               "canonical_update_applied": False, "aggregation_rule": "Daily follows events only; not a net follower-stock change. No absent date inferred as zero."}
        (partial if old.get("partial_day") else rows).append(row)
    return sorted(rows, key=lambda r: r["date"]), sorted(partial, key=lambda r: r["date"])


def facebook_recheck(root, prior):
    """Fresh native account daily evidence; compare only matching asset and timezone."""
    folder = root / "raw/facebook_recheck"
    manifest_path = folder / "acquisition_metadata.json"
    if not manifest_path.is_file():
        return [], {}, []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("selected_entity") != "Facebook" or manifest.get("selected_asset_id") != "118246571240106":
        raise ValueError("Facebook recheck identity differs from retained selected asset")
    old = {(r["metric"], r["date"]): r for r in prior if r["platform_selected"] == "Facebook"}
    rows, hashes = [], {manifest_path.relative_to(root).as_posix(): sha(manifest_path)}
    comparison_audit = folder / "comparison_audit.json"
    if comparison_audit.is_file():
        hashes[comparison_audit.relative_to(root).as_posix()] = sha(comparison_audit)
    for filename in manifest.get("evidence_files", []):
        p = (folder / filename).resolve()
        if not p.is_relative_to(folder.resolve()):
            raise ValueError("Unsafe Facebook evidence path")
        hashes[p.relative_to(root).as_posix()] = sha(p)
    metadata_inventory = []
    for item in manifest.get("files", []):
        path = (folder / item["path"]).resolve()
        if not path.is_relative_to(folder.resolve()) or sha(path) != item["sha256"]:
            raise ValueError("Facebook native file hash differs from acquisition manifest")
        relative = path.relative_to(root).as_posix(); hashes[relative] = sha(path)
        header, records, bad = native_csv(path, lambda row: "Date" in row and "Primary" in row)
        if bad:
            raise ValueError("Facebook recheck has malformed native rows")
        title = decode(path.read_bytes()).splitlines()[1].strip('"')
        metric = {"Content interactions": "interactions", "Facebook visits": "visits"}.get(title)
        if not metric or item["metric_title"] != title:
            raise ValueError("Facebook recheck metric title differs from manifest")
        metadata = metadata_for(root, path)
        metadata.update(captured_at_utc="", acquired_at_utc=utc_stamp(manifest["completed_at_utc"]), capture_precision="acquisition_completed_bound_exact_capture_unknown",
                        source_url=manifest["source_url"], reporting_start=manifest["reporting_start"], reporting_end=manifest["reporting_end"],
                        reporting_timezone=manifest["reporting_timezone"], evidence_ref=manifest_path.relative_to(root).as_posix())
        metadata_inventory.append({**metadata, "file": relative})
        seen = set()
        for no, native in records:
            day = calendar_date(native["Date"])
            if day in seen or not manifest["reporting_start"] <= day <= manifest["reporting_end"]:
                raise ValueError("Facebook recheck duplicate date or date outside selected bounds")
            seen.add(day)
            value, status = number(native["Primary"])
            if value != "" and (Decimal(value) < 0 or Decimal(value) != int(Decimal(value))):
                raise ValueError("Facebook count must be a nonnegative integer")
            previous = old.get((metric, day))
            previous_asset = parse_qs(urlsplit(previous.get("source_url", "")).query).get("asset_id", [""])[0] if previous else ""
            compatible = previous is not None and previous_asset == manifest["selected_asset_id"] and previous.get("reporting_timezone") == "Pacific Time" and manifest["reporting_timezone"] == "America/Los_Angeles"
            before = number(previous["value"])[0] if previous and previous["value"] is not None else ""
            comparison = "matches_prior_observation" if compatible and value != "" and before != "" and Decimal(value) == Decimal(before) else "conflicts_with_prior_observation" if compatible and value != "" and before != "" else "not_comparable_or_missing"
            rows.append(dict(**base_meta(root, path, metadata, no), platform_selected="Facebook", selected_account_id=manifest["selected_asset_id"],
                             selected_account_id_type="Meta Business Suite asset", predecessor_native_account_id=previous.get("selected_account_id", "") if previous else "",
                             metric_platform_scope="Facebook; includes ads" if metric == "interactions" else "Facebook Page/profile visits",
                             metric=metric, metric_native_title=title, metric_definition=manifest["definitions"]["content_interactions" if metric == "interactions" else metric],
                             date=day, value=value, value_status=status, value_raw=native["Primary"], date_raw=native["Date"],
                             reporting_timezone=manifest["reporting_timezone"], reporting_start=manifest["reporting_start"], reporting_end=manifest["reporting_end"],
                             measurement_type="daily_interval_count", download_clicked_at_utc=utc_stamp(item["download_clicked_at_utc"]),
                             prior_value=before, comparison_status=comparison, canonical_update_applied=False,
                             interpretation_limit="Recheck can confirm values, not the cause of the June interaction change."))
    return rows, hashes, metadata_inventory


def story_rows(root, path, metadata):
    header, valid, bad = native_csv(path, lambda row: any(x.casefold() == "post id" for x in row))
    id_col, account_col = find_column(header, "Post ID"), find_column(header, "Account ID", "Instagram account ID")
    rows = []
    for no, native in valid:
        if not native[id_col]:
            raise ValueError("Story native post ID is blank")
        if account_col and native[account_col] != KNOWN_ACCOUNT:
            raise ValueError("Story export account differs from the retained band account")
        rows.append({**native, **base_meta(root, path, metadata, no), "post_id": native[id_col], "selected_account_id": native.get(account_col, metadata.get("selected_account_id", KNOWN_ACCOUNT)),
                     "platform_selected": "Instagram", "metric_platform_scope": "Instagram", "measurement_type": "lifetime_content_snapshot",
                     "reporting_timezone": metadata.get("reporting_timezone", ""), "reporting_start": metadata.get("reporting_start", ""),
                     "reporting_end": metadata.get("reporting_end", ""), "canonical_update_applied": False,
                     "aggregation_rule": "Lifetime content snapshot; no allocation to publication date and no sum across snapshots."})
    return rows, [{**row, **base_meta(root, path, metadata, row["source_record"])} for row in bad]


def manual_story_rows(root):
    path = root / "raw/story_manual_observations.json"
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    items = payload if isinstance(payload, list) else payload.get("observations", [])
    rows = []
    for no, item in enumerate(items, 1):
        selected_id = str(item.get("selected_account_id", KNOWN_ACCOUNT))
        if not str(item.get("post_id", "")).isdigit() or selected_id not in {KNOWN_ACCOUNT, "118246571240106"}:
            raise ValueError("Manual Story identity must match the retained Instagram account or explicitly identified MBS asset and post ID")
        if selected_id == "118246571240106" and item.get("selected_account_id_type") != "Meta Business Suite asset":
            raise ValueError("MBS asset ID must not be relabelled as a native Instagram account ID")
        evidence = (root / item["evidence_ref"]).resolve()
        if not evidence.is_relative_to(root.resolve()) or not evidence.is_file() or not item.get("captured_at_utc"):
            raise ValueError("Manual Story requires saved evidence and an explicit capture timestamp")
        source_query = parse_qs(urlsplit(item.get("source_url", "")).query)
        if source_query.get("content_id") != [str(item["post_id"])] or source_query.get("asset_id") != ["118246571240106"]:
            raise ValueError("Manual Story URL identity differs from retained band asset/post")
        if evidence.suffix.lower() == ".txt" and item["source_url"] not in evidence.read_text(encoding="utf-8-sig"):
            raise ValueError("Manual Story exact URL does not occur in saved detail evidence")
        metrics = {}
        for label, observation in item.get("metrics", {}).items():
            metric = re.sub(r"\s+", "_", label.strip().lower())
            if metric not in {"views", "reach", "interactions", "likes", "replies", "navigation", "sticker_taps", "shares", "follows", "profile_visits", "link_clicks"}:
                raise ValueError("Manual Story metric needs a known explicit definition: " + metric)
            raw_value = observation.get("raw", observation.get("raw_value", observation.get("display_value", observation.get("value", ""))))
            if re.fullmatch(r"[\d,.]+\s*[KMBkmb]", str(raw_value)):
                value, status = "", "rounded_display_not_exact"
            else:
                value, status = number(raw_value)
            if value != "" and (Decimal(value) < 0 or Decimal(value) != int(Decimal(value))):
                raise ValueError("Story count must be a nonnegative integer")
            metrics[metric], metrics[metric + "_status"] = value, status
            metrics[metric + "_source_status"] = observation.get("status", "")
            metrics[metric + "_raw"] = raw_value
            metrics[metric + "_collector_label"] = label
            metrics[metric + "_source_label"] = "Instagram follows" if metric == "follows" else metric.replace("_", " ").capitalize()
        if not metrics:
            raise ValueError("Manual Story record has no explicit metrics")
        rows.append(dict(platform_selected="Instagram", selected_account_id=selected_id,
                         selected_account_id_type=item.get("selected_account_id_type", "native Instagram account"), account_handle=item.get("account_handle", ""),
                         post_id=str(item["post_id"]), post_type="IG story", source_kind="manual_story_detail", measurement_type="lifetime_content_snapshot",
                         metric_platform_scope=item.get("metric_platform_scope", "Selected Instagram Story detail; per-metric crossposting scope not independently labelled"), published_local=item.get("published_local", ""),
                         reporting_timezone=item.get("reporting_timezone", ""), source_file=path.relative_to(root).as_posix(), source_record=no,
                         source_sha256=sha(path), evidence_ref=item["evidence_ref"], evidence_sha256=sha(evidence), source_url=item.get("source_url", ""),
                         captured_at_utc=utc_stamp(item["captured_at_utc"]), canonical_update_applied=False,
                         repair_scope="Only separately observed metrics; original malformed record remains quarantined.", **metrics))
    return rows


def story_metric_rows(stories):
    """One separately observed field per post/capture/metric, including unavailable."""
    result = []
    metric_names = ["views", "reach", "interactions", "likes", "replies", "navigation", "sticker_taps", "shares", "follows", "profile_visits", "link_clicks"]
    for story in stories:
        metadata = {k: v for k, v in story.items() if not any(k == metric or k.startswith(metric + "_") for metric in metric_names)}
        for metric in metric_names:
            if metric + "_status" not in story:
                continue
            result.append({**metadata, "metric": metric, "metric_native_label": story[metric + "_source_label"],
                           "value": story[metric], "value_status": story[metric + "_status"], "value_raw": story[metric + "_raw"],
                           "source_value_status": story[metric + "_source_status"],
                           "aggregation_rule": "Lifetime per-content field at capture. Do not assign to publication date or add repeated captures."})
    return result


def reconcile_ad_levels(campaigns, ads):
    """Compare matching exports, without summing their parent and child totals."""
    rows = []
    for campaign_file in sorted({r["source_file"] for r in campaigns}):
        parent = [r for r in campaigns if r["source_file"] == campaign_file]
        for ad_file in sorted({r["source_file"] for r in ads}):
            child = [r for r in ads if r["source_file"] == ad_file]
            fields = ["ad_account_id", "currency", "reporting_timezone", "attribution_setting", "metric_platform_scope", "breakdowns_json"]
            compatible = all(len({r[k] for r in parent}) == len({r[k] for r in child}) == 1 and parent[0][k] == child[0][k] for k in fields)
            compatible &= bool(parent[0]["ad_account_id"] and parent[0]["reporting_timezone"])
            start, end = min(r["reporting_start"] for r in parent), max(r["reporting_end"] for r in parent)
            compatible &= start == min(r["reporting_start"] for r in child) and end == max(r["reporting_end"] for r in child)
            if not compatible:
                continue
            for metric in [f"Amount spent ({parent[0]['currency']})", "Impressions", "Link clicks"]:
                pvalues = exact_values(parent, metric)
                cvalues = exact_values(child, metric)
                rows.append(dict(campaign_source_file=campaign_file, ad_source_file=ad_file, metric=metric,
                                 ad_account_id=parent[0]["ad_account_id"], currency=parent[0]["currency"], reporting_timezone=parent[0]["reporting_timezone"],
                                 reporting_start=start, reporting_end=end, campaign_known_sum=str(sum(pvalues)), ad_known_sum=str(sum(cvalues)),
                                 known_sums_match=sum(pvalues) == sum(cvalues), campaign_observed_rows=len(pvalues), campaign_rows=len(parent),
                                 ad_observed_rows=len(cvalues), ad_rows=len(child), all_metric_rows_observed=len(pvalues) == len(parent) and len(cvalues) == len(child),
                                 caveat="Comparison only; never add these two totals. Blank metric cells remain unavailable even when known sums match."))
    return rows


def write_csv(path, rows, empty_fields=None):
    fields = list(dict.fromkeys(k for row in rows for k in row)) or (empty_fields or ["no_records"])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else "" if v is None else v for k, v in row.items()} for row in rows)


def normalize(root, output, repo, collection_complete=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("Use a new normalization output directory")
    before = sha(repo.db_path)
    sources = sorted([p for directory in [root, root / "raw"] if directory.is_dir() for p in directory.glob("*.csv")])
    source_hashes = {p.relative_to(root).as_posix(): sha(p) for p in sources}
    # Include capture receipts, blocked-export evidence and supplemental proofs,
    # even when they do not contribute a numeric row.
    evidence_files = [p for p in (root / "raw").rglob("*") if p.is_file()] if (root / "raw").is_dir() else []
    evidence_files.extend(p for p in root.iterdir() if p.is_file() and (p.suffix.lower() in {".txt", ".png"} or p.name == "preflight_preservation.json"))
    source_hashes.update({p.relative_to(root).as_posix(): sha(p) for p in evidence_files})
    campaigns, ads, follows, stories, quarantine, summaries = [], [], [], [], [], []
    metadata_inventory = []
    for path in sources:
        metadata = metadata_for(root, path)
        metadata_inventory.append({**metadata, "file": path.relative_to(root).as_posix()})
        if path.name.startswith("ads_"):
            rows, summary = ads_rows(root, path, metadata); summaries.append(summary)
            (campaigns if summary["reporting_level"] == "campaign" else ads).extend(rows)
        elif path.name.startswith("instagram_follows_"):
            follows.extend(follow_rows(root, path, metadata))
        elif path.name.startswith("instagram_stories_"):
            valid, bad = story_rows(root, path, metadata); stories.extend(valid); quarantine.extend(bad)
    follows.extend(manual_follows(root))
    manual_stories = manual_story_rows(root)
    for extra in [root / "collection_manifest.json", root / "observation_manifest.json", *root.glob("*.metadata.json"), *(root / "raw").glob("*.metadata.json")]:
        if extra.is_file():
            source_hashes[extra.relative_to(root).as_posix()] = sha(extra)
    for row in follows + manual_stories:
        for name in [row.get("source_file"), row.get("evidence_ref")]:
            if name:
                source_hashes[name] = sha(root / name)
    old_daily = json_rows(repo.table("social/account_daily.csv"))
    facebook, facebook_hashes, facebook_metadata = facebook_recheck(root, old_daily)
    source_hashes.update(facebook_hashes); metadata_inventory.extend(facebook_metadata)
    follow_comparisons = compare_follows(follows, old_daily)
    catalog_hashes = {r["path"]: r["sha256"] for r in json_rows(repo.file_catalog())}
    daily_resolved, daily_partial = resolved_follows(old_daily, follow_comparisons, before, catalog_hashes["social/account_daily.csv"], catalog_hashes)
    old_excluded = {str(r["post_id"]) for r in json_rows(repo.table("social/excluded_records.csv"))}
    recovered_story_ids = sorted({r["post_id"] for r in stories} & old_excluded)
    manual_story_ids = sorted({r["post_id"] for r in manual_stories} & old_excluded)
    prior_missing_resolved = sorted({r["date"] for r in follow_comparisons if r["comparison_status"] == "prior_missing_resolved_by_explicit_daily_evidence"})
    missing_date_status = []
    for old in old_daily:
        if old["platform_selected"] != "Instagram" or old["metric"] != "follows" or old["value"] is not None:
            continue
        evidence = [r for r in follow_comparisons if r["date"] == old["date"] and r["comparison_status"] == "prior_missing_resolved_by_explicit_daily_evidence"]
        missing_date_status.append(dict(date=old["date"], prior_value_status=old["value_status"], prior_partial_day=old["partial_day"],
                                        new_value=evidence[0]["value"] if evidence else "", new_value_status=evidence[0]["value_status"] if evidence else "missing_source",
                                        evidence_rows=len(evidence), resolution_status="separately_observed_daily_evidence" if evidence else "unresolved",
                                        evidence_refs=json.dumps([r.get("evidence_ref", r["source_file"]) for r in evidence]), canonical_update_applied=False))
    pending = "not_collected_in_this_pass" if collection_complete else "collection_in_progress"
    statuses = [dict(dataset="ads_manager", status="new_native_evidence_separate_grains" if ads or campaigns else pending,
                     detail=f"{len(ads)} non-campaign native rows; {len(campaigns)} campaign rows. Native CSV windows control; no parent/child addition or inferred zero-spend coverage.", evidence_ref="ads_history.csv;ads_campaigns.csv", captured_at_utc=""),
                dict(dataset="instagram_follows", status="explicit_daily_evidence_acquired" if follows else pending,
                     detail=f"{len(follows)} evidence rows; {len(prior_missing_resolved)} previously missing dates explicitly observed. New resolved daily view has {sum(r['value'] != '' for r in daily_resolved)}/{len(daily_resolved)} observed complete dates; old canonical table unchanged.", evidence_ref="follows_daily_resolved.csv;instagram_follows_comparison.csv", captured_at_utc=""),
                dict(dataset="instagram_stories", status="new_native_evidence_acquired" if stories or quarantine else "manual_lifetime_metrics_acquired" if manual_stories else pending,
                     detail=f"{len(stories)} structurally valid native rows, {len(quarantine)} malformed rows, {len(manual_stories)} manual detail observations; {len(recovered_story_ids)} old IDs have valid new native rows and {len(manual_story_ids)} have separate manual metrics. Lifetime snapshots remain separate.", evidence_ref="instagram_stories.csv;instagram_stories_manual.csv;instagram_stories_quarantine.csv", captured_at_utc="")]
    if facebook:
        statuses.append(dict(dataset="facebook_historical_recheck", status="fresh_native_daily_recheck", detail=f"{len(facebook)} daily metric rows; {sum(r['comparison_status'] == 'matches_prior_observation' for r in facebook)} agree with prior values. Metric definition includes ads for interactions; cause of June shift remains unknown.", evidence_ref="facebook_daily_recheck.csv", captured_at_utc=""))
    repair = [dict(dataset="instagram_follows", status="resolved_new_daily_view" if daily_resolved and all(r["value"] != "" for r in daily_resolved) else "partially_resolved_new_daily_view" if prior_missing_resolved else "no_missing_dates_resolved_yet",
                   detail=json.dumps({"previously_missing_dates_observed": prior_missing_resolved, "no_zero_filling": True, "old_canonical_unchanged": True}),
                   evidence_ref="follows_daily_resolved.csv;instagram_follows_comparison.csv", captured_at_utc=""),
              dict(dataset="instagram_stories", status="valid_reexport_matches_pending_review" if recovered_story_ids else "manual_metric_recovery_pending_review" if manual_story_ids else "no_previously_quarantined_ids_resolved_yet",
                   detail=json.dumps({"previously_quarantined_ids_with_valid_new_rows": recovered_story_ids, "previously_quarantined_ids_with_manual_metrics": manual_story_ids, "new_malformed_rows": len(quarantine), "old_quarantine_unchanged": True}),
                   evidence_ref="instagram_stories.csv;instagram_stories_quarantine.csv", captured_at_utc="")]
    if any(sha(root / name) != value for name, value in source_hashes.items()) or sha(repo.db_path) != before:
        raise ValueError("An input changed during validation; output refused")
    output.mkdir(parents=True)
    tables = {"ads_campaigns": campaigns, "ads_history": ads, "ads_export_coverage": summaries, "ads_level_reconciliation": reconcile_ad_levels(campaigns, ads),
              "instagram_follows": follows, "instagram_follows_comparison": follow_comparisons, "instagram_follows_missing_date_status": missing_date_status,
              "follows_daily_resolved": daily_resolved, "follows_daily_partial": daily_partial,
              "facebook_daily_recheck": facebook,
              "instagram_stories": stories, "instagram_stories_manual": manual_stories, "instagram_story_metrics": story_metric_rows(manual_stories), "instagram_stories_quarantine": quarantine, "repair_status": repair, "collection_status": statuses}
    for name, rows in tables.items():
        write_csv(output / (name + ".csv"), rows, STATUS_FIELDS if name.endswith("status") else None)
    report = dict(version=VERSION, generated_at_utc=datetime.now(timezone.utc).isoformat(), collection_complete=collection_complete,
                  source_database=str(repo.db_path), source_database_sha256_before=before, source_database_sha256_after=sha(repo.db_path),
                  input_files_sha256=source_hashes, source_metadata=metadata_inventory, ads_exports=summaries,
                  predecessor_asset_hashes={name: catalog_hashes[name] for name in ["social/account_daily.csv", "social/excluded_records.csv"]},
                  table_rows={k: len(v) for k, v in tables.items()}, follows_comparison_counts=dict(Counter(r["comparison_status"] for r in follow_comparisons)),
                  missing_follows_dates_explicitly_observed=prior_missing_resolved, previously_quarantined_story_ids_with_valid_new_rows=recovered_story_ids,
                  previously_quarantined_story_ids_with_manual_metrics=manual_story_ids, prior_missing_follows_dates_still_unresolved=sum(r["resolution_status"] == "unresolved" for r in missing_date_status),
                  limitations=["New evidence is not applied to inherited canonical tables.", "CSV native reporting dates override selected UI range; missing windows never imply zero spend.",
                               "Campaign, ad-set and ad levels must not be summed together; reach, frequency and ratios are nonadditive.",
                               "Native link clicks do not identify Spotify destinations or prove listening.", "Capture timestamps are not inferred from filesystem times.",
                               "No malformed Story field alignment or omitted Follows zero is inferred."])
    (output / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "output_manifest.json").write_text(json.dumps({p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--data-dir", type=Path)
    source.add_argument("--database", type=Path)
    parser.add_argument("--collection-complete", action="store_true")
    args = parser.parse_args()
    repository = AnalysisRepository(args.database) if args.database else load_registered_analysis(args.data_dir)
    if repository is None:
        parser.error("No registered analysis package")
    result = normalize(args.collection, args.output, repository, args.collection_complete)
    print(json.dumps({k: result[k] for k in ["table_rows", "ads_exports", "follows_comparison_counts", "missing_follows_dates_explicitly_observed", "previously_quarantined_story_ids_with_valid_new_rows"]}, ensure_ascii=False, indent=2))
