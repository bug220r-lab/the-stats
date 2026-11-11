"""Build an immutable Studio integration package from the sealed acquisition.

No network access, date correction, library writes, or source modification.
Native reporting labels are selected by corroboration, never by capture date.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("data/collection/tiktok-20261026")
EVIDENCE = SOURCE / "evidence/studio-20261027T003214Z"
RAW = SOURCE / "raw/studio-20261027T003214Z"
DERIVED = Path("outputs/tiktok_collection_20261026")
AUDIT = Path("outputs/tiktok_integration_20261027/date_audit")
SEALED_SHA = "dc3b3ceb774fe6910dd1bb2c8fe6ec9d231a56c66ed46987ce4818789c72f0b1"
END = date(2026, 10, 25)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(dict.fromkeys(key for row in rows for key in row))
    if not fields:
        raise ValueError("A table must have a known schema")
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def native(zip_path, member):
    with zipfile.ZipFile(ROOT / zip_path) as archive:
        raw = archive.read(member)
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")))


def label_calendar(rows, end=END, field="Date", repeats=1):
    """Assign only the year from established bounds; reject mismatched labels."""
    if len(rows) % repeats:
        raise ValueError("Incomplete reporting-day groups")
    start = end - timedelta(days=len(rows) // repeats - 1)
    result = []
    for index, row in enumerate(rows):
        day = start + timedelta(days=index // repeats)
        expected = day.strftime("%B ") + str(day.day)
        if row[field] != expected:
            raise ValueError(f"Native calendar mismatch at {index + 2}: {row[field]} != {expected}")
        result.append(day.isoformat())
    return result


def integer(value, *, signed=False):
    if not re.fullmatch(r"-?\d+" if signed else r"\d+", value):
        raise ValueError("Unexpected numeric source token: " + repr(value))
    return int(value)


def exact_display(value):
    clean = value.replace(",", "")
    return int(clean) if re.fullmatch(r"-?\d+", clean) else ""


def daily_tables():
    configs = [
        ("account_daily", RAW / "Overview_2025-10-26_1792974780_funnyguycrawl.zip", "Overview.csv"),
        ("viewer_daily", RAW / "Viewers_funnyguycrawl.zip", "Viewers.csv"),
        ("follower_daily", RAW / "followers-365/Followers_funnyguycrawl.zip", "FollowerHistory.csv"),
        ("follower_activity", RAW / "followers-365/Followers_funnyguycrawl.zip", "FollowerActivity.csv"),
    ]
    results = {}
    for key, source, member in configs:
        rows = native(source, member)
        dates = label_calendar(rows, repeats=24 if key == "follower_activity" else 1)
        output = []
        for record, (row, day) in enumerate(zip(rows, dates), 2):
            new = {"date": day, "date_raw": row["Date"], "reporting_timezone": "unknown",
                   "date_status": "preferred_initial_native_calendar", "source_zip": source.as_posix(),
                   "source_member": member, "source_record": record}
            if key == "account_daily":
                for name, column in {"video_views": "Video Views", "profile_views": "Profile Views",
                                     "likes": "Likes", "shares": "Shares"}.items():
                    new[name] = integer(row[column])
                new.update(comments_raw=row["Comments"], comments_signed_native=integer(row["Comments"], signed=True),
                           comments_status="source_signed_net_semantics_unverified")
            elif key == "viewer_daily":
                raw = row["Total Viewers"]
                new.update(total_viewers_raw=raw, total_viewers="" if raw == "undefined" else integer(raw),
                           total_viewers_status="unavailable_native_undefined" if raw == "undefined" else "observed_exact",
                           new_viewers=integer(row["New Viewers"]), returning_viewers=integer(row["Returning Viewers"]),
                           aggregation="Daily unique audiences; never sum to period unique audience")
            elif key == "follower_daily":
                new.update(followers=integer(row["Followers"]),
                           net_followers=integer(row["Difference in followers from previous day"], signed=True))
            else:
                new.update(hour=integer(row["Hour"]), active_followers=integer(row["Active followers"]),
                           aggregation="Hourly active audience; not additive across hours or days")
            output.append(new)
        results[key] = (output, source)
    followers = results["follower_daily"][0]
    assert all(b["followers"] - a["followers"] == b["net_followers"] for a, b in zip(followers, followers[1:]))
    assert sum(r["video_views"] for r in results["account_daily"][0]) == 514995
    return results


def account_panels():
    captures = [
        ("004-overview-365", "overview", 365), ("017-overview-7", "overview", 7),
        ("007-viewers-365", "viewers", 365), ("008-viewers-60", "viewers", 60),
        ("009-viewers-28", "viewers", 28), ("010-viewers-7", "viewers", 7),
        ("012b-followers-365-loaded", "followers", 365), ("013-followers-60", "followers", 60),
        ("014-followers-28", "followers", 28), ("015-followers-7", "followers", 7),
        ("030-monetization-7", "monetization", 7), ("031-monetization-30", "monetization", 30),
        ("032-monetization-60", "monetization", 60),
    ]
    metrics, breakdowns, notes = [], [], []
    headings = {"Traffic source", "Search queries", "Gender", "Age", "Locations", "Most active times",
                "Posts your viewers also viewed", "Creators your viewers also watched"}
    numeric_metrics = ["Video views", "Profile views", "Likes", "Comments", "Shares", "Est. rewards",
                       "Total viewers", "New viewers", "Total followers", "Net followers"]
    for stem, family, window in captures:
        path = EVIDENCE / (stem + ".txt")
        text = (ROOT / path).read_text(encoding="utf-8")
        metadata = json.loads((ROOT / EVIDENCE / (stem + ".json")).read_text(encoding="utf-8"))
        context = {"panel_id": stem, "family": family, "window_days": window,
                   "captured_at": metadata["captured_at"], "source_file": path.as_posix(),
                   "source_url": metadata["source_url"], "reporting_timezone": "unknown",
                   "reporting_start": (END-timedelta(days=window-1)).isoformat() if family != "monetization" else "",
                   "reporting_end": END.isoformat() if family != "monetization" else ""}
        for metric in numeric_metrics:
            match = re.search(r'- button "' + re.escape(metric) + r' ([^"\n]+)"', text)
            if not match:
                continue
            display = match.group(1).split(" ")[0]
            exact = exact_display(display)
            metrics.append({**context, "metric": metric, "value_raw": display, "value_exact": exact,
                            "button_display_raw": match.group(1), "comparison_raw": match.group(1)[len(display):].strip(),
                            "value_status": "exact_displayed" if exact != "" else "rounded_or_unavailable",
                            "scope": "all-time follower stock" if metric == "Total followers" else "native selected-period summary"})
        if family == "monetization":
            for metric, amount in re.findall(r'- button "(Total|LIVE rewards|TikTok Shop for Seller) \$(\d+\.\d{2}) ', text):
                metrics.append({**context, "metric": metric, "value_raw": "$"+amount, "value_exact": amount,
                                "button_display_raw": next((m for m in re.findall(r'- button "([^"\n]+)"', text) if m.startswith(metric+' $')), ""),
                                "comparison_raw": "",
                                "value_status": "displayed_currency", "scope": "selected-period USD reward snapshot; dates not exposed"})
        tokens = []
        for line in text.splitlines():
            match = re.match(r"\s*- generic: (.*)", line)
            if match:
                tokens.append(match.group(1).strip().strip('"'))
        dimension = None
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token in headings:
                dimension = token
            elif dimension in {"Traffic source", "Gender", "Age", "Locations"} and index+1 < len(tokens) and re.fullmatch(r"<?\d+(?:\.\d+)?%", tokens[index+1]):
                value = tokens[index+1]
                breakdowns.append({**context, "dimension": dimension, "label": token, "value_raw": value,
                                   "value_status": "bounded_percentage" if value.startswith("<") else "displayed_rounded_percentage",
                                   "scope": "native panel population; separate viewers and followers"})
                index += 1
            elif "most active" in token or "were active" in token or "Information will be available" in token:
                note_context = dict(context, panel_window_days=window)
                if "7 days" in token:
                    note_context.update(window_days=7, reporting_start=(END-timedelta(days=6)).isoformat(),
                                        reporting_end=END.isoformat())
                notes.append({**note_context, "note_raw": token})
            index += 1
    return metrics, breakdowns, notes


def account_affinity():
    """Retain viewer affinity lists as displayed; these are not owned posts."""
    rows = []
    for stem, window in [("007-viewers-365", 365), ("008-viewers-60", 60),
                         ("009-viewers-28", 28), ("010-viewers-7", 7)]:
        path = EVIDENCE / (stem + ".txt")
        metadata = json.loads((ROOT/EVIDENCE/(stem+".json")).read_text(encoding="utf-8"))
        section = None
        display = None
        for line in (ROOT/path).read_text(encoding="utf-8").splitlines():
            if line == "- generic: Posts your viewers also viewed":
                section = "Posts your viewers also viewed"
            elif line == "- generic: Creators your viewers also watched":
                section = "Creators your viewers also watched"
            elif section and line == "- generic: Gender":
                section = None
            if section:
                match = re.match(r"^- '?link (.+):$", line)
                if match:
                    display = match.group(1)
                url_match = re.match(r"\s+- /url: (.+)$", line)
                if url_match and display:
                    rows.append({"panel_id": stem, "window_days": window, "section": section,
                                 "link_display_raw": display, "observed_url": url_match.group(1),
                                 "captured_at": metadata["captured_at"], "source_file": path.as_posix(),
                                 "scope": "Viewer affinity display; third-party accounts/content, not owned-post activity"})
                    display = None
    return rows


def build(destination):
    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError("Use a new output directory; sealed packages are never overwritten")
    seal = SOURCE / "evidence/collection-file-manifest.json"
    if sha(ROOT / seal) != SEALED_SHA:
        raise ValueError("Original acquisition manifest changed")
    acquisition = json.loads((ROOT / seal).read_text(encoding="utf-8"))
    for item in acquisition["files"]:
        path = ROOT / item["path"]
        if path.stat().st_size != item["bytes"] or sha(path) != item["sha256"]:
            raise ValueError("Acquisition bytes changed: " + item["path"])
    disposition_path = ROOT / AUDIT / "source_dispositions.csv"
    dispositions = read_csv(disposition_path)
    if len(dispositions) != 33:
        raise ValueError("Require the completed 33-member independent date disposition")
    destination.mkdir(parents=True)
    datasets = []

    def copy(relative):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)

    def table(key, rows, definition, status="collected", reason="", primary_key=None, source_paths=None, **extra):
        path = "tables/"+key+".csv"
        write_csv(destination / path, rows)
        datasets.append({"dataset_id": key, "path": path, "status": status, "row_count": len(rows),
                         "definition": definition, "reason": reason, "primary_key": primary_key or [],
                         "source_paths": [str(p).replace("\\", "/") for p in source_paths or []], **extra})

    for item in acquisition["files"]:
        copy(Path(item["path"]))
    copy(seal)
    for p in sorted((ROOT / AUDIT).glob("*")):
        if p.is_file():
            copy(p.relative_to(ROOT))
    copy(Path(__file__).relative_to(ROOT))
    for key, (rows, source) in daily_tables().items():
        table(key, rows, {"account_daily": "Native account activity; signed comments kept out of default activity KPIs",
                         "viewer_daily": "Daily unique viewers; not period-unique and not additive",
                         "follower_daily": "Daily follower stock and native signed net change",
                         "follower_activity": "Hourly active followers; seven source-labeled days only"}[key],
              primary_key=["date", "hour"] if key == "follower_activity" else ["date"], source_paths=[source],
              reporting_start=rows[0]["date"], reporting_end=rows[-1]["date"], reporting_timezone="unknown",
              date_disposition="preferred_initial_source_labels; absolute reporting timezone unknown")
    copies = [
        ("post_inventory", DERIVED/"posts-inventory-observed-615.csv", "615 owned posts; native publication text and unknown timezone", ["post_id"]),
        ("post_summary", DERIVED/"audit-final/post-summary-snapshots.csv", "Post lifetime/stated-scope snapshots; never reporting-day activity", ["post_id"]),
        ("post_viewers", DERIVED/"audit-final/post-viewer-summary.csv", "Post viewer snapshot; not additive across posts", ["post_id"]),
        ("post_breakdowns", DERIVED/"audit-final/post-displayed-breakdowns.csv", "Displayed percentages and bounds for native post panel populations", []),
        ("post_panels", DERIVED/"audit-final/post-panel-captures.csv", "All panel receipts; readiness and superseded captures explicit", ["metadata_file", "section"]),
        ("post_coverage", DERIVED/"audit-final/post-panel-coverage.csv", "Distinct post and panel coverage", ["canonical_index"]),
        ("recent_comments", DERIVED/"supporting-index-01/comment-observations.csv", "Recent visible comment observations; fingerprints are not comment IDs", []),
        ("sound_labels", DERIVED/"supporting-index-01/public-sound-label-observations.csv", "Partial public sound labels; recording identity unverified", []),
        ("source_dispositions", AUDIT/"source_dispositions.csv", "Explicit precedence/exclusion decision for each native CSV export", []),
    ]
    for key, source, definition, pk in copies:
        rows = read_csv(ROOT / source)
        if key in {"post_inventory", "post_summary", "post_viewers", "post_coverage"} and len(rows) != 615:
            raise ValueError("Incomplete owned-post coverage: " + key)
        partial = key in {"recent_comments", "sound_labels", "post_breakdowns"}
        table(key, rows, definition, "partial" if partial else "collected",
              "Accessible observed subset; missing/suppressed values remain unknown" if partial else "",
              primary_key=pk, source_paths=[source])
    ranking_source = DERIVED/"supporting-index-01/content-ranking-observations.csv"
    ranks = []
    for row in read_csv(ROOT/ranking_source):
        if not row["rank"]:
            continue
        match = re.fullmatch(r"content-(.+)-(\d+)-rows.json", row["source_file"])
        cells = json.loads(row["cells_json"])
        ranks.append({**row, "source_file": (EVIDENCE/row["source_file"]).as_posix(),
                      "ranking_metric": match.group(1), "window_days": match.group(2),
                      "post_display": cells[1], "ranking_value_raw": cells[2], "all_views_raw": cells[3],
                      "posted_on_raw": cells[4]})
    table("content_rankings", ranks, "16 ranking views; ranking period metrics separate from All views",
          status="partial", reason="Native top-ranking subsets, not complete account activity", source_paths=[ranking_source])
    metrics, breakdowns, notes = account_panels()
    table("account_panel_metrics", metrics, "Native selected-window UI summary displays; precision retained")
    table("account_breakdowns", breakdowns, "Account audience and traffic displays; viewers and followers separate")
    table("account_panel_notes", notes, "Native activity/suppression notices; no chart point series inferred", family="audience")
    table("account_affinity", account_affinity(), "Native viewer affinity links; third-party content is not owned-post activity", family="audience")
    # Every original native member remains available as its own unmerged table.
    exports = json.loads((ROOT/DERIVED/"audit-final/native-exports.json").read_text(encoding="utf-8"))["archives"]
    number = 0
    for archive in exports:
        with zipfile.ZipFile(ROOT/archive["path"]) as zf:
            for member in zf.namelist():
                number += 1
                raw = zf.read(member)
                path = f"native/{number:02d}-{Path(member).name}"
                (destination/path).parent.mkdir(exist_ok=True)
                (destination/path).write_bytes(raw)
                rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
                decision = next((d for d in dispositions if d["source_zip"] == archive["path"] and d["source_member"] == member), None)
                if decision is None:
                    raise ValueError("Missing native-member decision: "+archive["path"]+":"+member)
                datasets.append({"dataset_id": f"native_{number:02d}_{Path(member).stem.lower()}", "path": path,
                                 "status": "collected", "row_count": len(rows), "primary_key": [],
                                 "label": f"{Path(member).stem} · {decision['window_days']} day filter · {decision['date_disposition']} · capture {number:02d}",
                                 "definition": "Original CSV member; separate source snapshot, never added to overlapping exports",
                                 "source_paths": [archive["path"]], **decision})
    assert number == 33
    for key, reason in {
        "tiktok_for_artists": "Pending by explicit user instruction; no Business account created or linked",
        "interactive_chart_series": "Raw hover/chart point series were not exported; saved panels are retained",
        "live_mobile_details": "Desktop Studio led to a mobile QR handoff; details unavailable",
        "recording_crosswalk": "Sound labels do not establish sound IDs or recording identities",
    }.items():
        datasets.append({"dataset_id": key, "status": "pending" if key == "tiktok_for_artists" else "unavailable",
                         "row_count": 0, "reason": reason, "definition": reason})
    manifest = {
        "schema_version": 1, "collection_key": "tiktok-20261027-studio", "platform": "tiktok",
        "account": "@funnyguycrawl", "account_display_name": "@funnyguycrawl",
        "label": "TikTok Studio · @funnyguycrawl · collected October 26–27, 2026",
        "collected_at": "2026-10-27T04:33:24.539557+00:00", "integrated_package_at": datetime.now(timezone.utc).isoformat(),
        "reporting_start": "2025-10-26", "reporting_end": "2026-10-25", "reporting_timezone": "unknown",
        "artists_status": "pending", "baseline_status": "separate_retrospective_collection_not_original_baseline",
        "identity_status": "authenticated_handle_and_profile_verified; stable numeric account ID not exposed",
        "date_resolution": "Prefer initial native reporting labels supported by shorter-window overlap; exclude later relabelings. No timezone or platform root cause inferred; no October26 activity appended.",
        "date_resolution_summary": "The initial exports control this view: all 197 shorter-window rows agree with their annual histories. Later relabelings are retained as excluded evidence and add no new reporting day. Dates are TikTok source labels; the reporting timezone remains unknown.",
        "date_limit": "Absolute reporting-day timezone is unknown; saved UI calendar boundaries are not independent certification of the native source labels.",
        "limitations": ["TikTok for Artists remains pending by user instruction.",
                        "Reporting timezone and absolute event-day boundaries remain unknown; source precedence resolves the conflicting exports without rewriting native dates.",
                        "Signed daily comments are preserved separately; their interpretation as new comment events remains unverified.",
                        "The final total-viewer value is native undefined, not zero. Daily unique audiences cannot be summed into a period-unique audience.",
                        "Post counters are lifetime/stated-scope snapshots at different post ages. Abbreviated counts are not exact.",
                        "Comments cover the accessible recent list; fingerprints are not unique native comment IDs.",
                        "Raw interactive chart point series and mobile-only LIVE details are unavailable. Sound-to-recording mappings remain unresolved."],
        "collection_counts": {"posts": 615, "distinct_post_panels": 1845, "panel_receipts": 1846,
                              "native_zip_exports": 18, "native_csv_members": 33, "verified_images": 945},
        "acquisition_manifest": seal.as_posix(), "acquisition_manifest_sha256": SEALED_SHA,
        "datasets": datasets,
        "assets": [{"path": p.relative_to(destination).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)}
                   for p in sorted(destination.rglob("*")) if p.is_file()],
    }
    (destination/"manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return {"package": str(destination), "datasets": len(datasets), "assets": len(manifest["assets"]),
            "rows": sum(d["row_count"] for d in datasets), "manifest_sha256": sha(destination/"manifest.json")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(build(args.output), ensure_ascii=False, indent=2))
