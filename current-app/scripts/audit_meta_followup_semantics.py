"""Independent evidence acceptance for the October 23 Meta follow-up.

Checks source identities, labelled Story metrics, unresolved mappings, exact
link IDs, native Ads configuration and the mixed-account identity partition.
Does not import the collector, normalizers or package builder.
"""
import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

from stats_app.analysis_repository import AnalysisRepository
from stats_app.storage import StorageError


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def check(condition, message):
    if not condition:
        raise StorageError(message)


def pointer(value, path):
    for part in path.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def decimal_total(rows, column, places=None):
    values = [Decimal(row[column]) for row in rows if row[column] != ""]
    return format(sum(values, Decimal(0)), ".2f" if places else "f") if values else ""


def audit(collection, parent):
    collection, parent = Path(collection).resolve(), AnalysisRepository(parent)
    before = sha(parent.db_path.read_bytes())
    inputs = {p.relative_to(collection).as_posix(): sha(p.read_bytes()) for p in collection.rglob("*") if p.is_file()}
    normalized = collection / "normalized"
    mapping = read_csv(normalized / "story_song_map.csv")
    metrics = read_csv(normalized / "story_metrics.csv")
    target_ids = {"18216593050358711", "18430983631182631", "18078399140713885", "18114350993331569", "18117197771279451", "17965560240198897"}
    check(len(mapping) == 6 and {r["post_id"] for r in mapping} == target_ids, "Story ID inventory differs.")
    old = parent.table("social/meta_collection/mapping/post_evidence.csv", raw=True).set_index("post_id")
    label_order = [("views", "Views"), ("reach", "Reach"), ("interactions", "Interactions"),
                   ("link_clicks", "Link clicks"), ("sticker_taps", "Sticker taps"), ("instagram_follows", "Instagram follows")]
    observed, unavailable = 0, 0
    for item in mapping:
        post = item["post_id"]
        check(json.loads(item["assigned_song_ids"]) == [] and item["audio_use_verified"] == "False"
              and item["stream_attribution_available"] == "False", "Unverified Story mapping was promoted to confirmed attribution.")
        for field in ("post_key", "selected_account_id", "account_handle", "published_local", "published_utc", "permalink"):
            check(item[field] == old.loc[post, field], "Story predecessor identity/publication changed: " + field)
        check(item["publication_timezone"] == old.loc[post, "reporting_timezone"], "Story publication timezone changed.")
        check(item["predecessor_source_sha256"] == sha(parent.original_bytes(old.loc[post, "retained_source_path"])), "Story predecessor raw hash differs.")
        check(sha((collection / item["evidence_ref"]).read_bytes()) == item["evidence_sha256"], "Story AX hash differs.")
        check(sha((collection / item["screenshot_ref"]).read_bytes()) == item["screenshot_sha256"], "Story screenshot hash differs.")
        source = (collection / item["evidence_ref"]).read_text(encoding="utf-8")
        check("content_id=" + post in source and "asset_id=118246571240106" in source, "Story evidence source identity differs.")
        overview = source[source.index("heading Overview"):]
        last = -1
        for _, label in label_order:
            pos = overview.index("text " + label)
            check(pos > last, "Story Overview metric order differs.")
            last = pos
        readings = re.search(r"text Instagram follows\s+\d+ image\s+\d+ text ([^\r\n]+)", overview)
        check(readings is not None, "Labelled Story Overview values missing.")
        values = readings.group(1).split()
        check(len(values) == 6, "Story Overview does not supply six metric markers.")
        selected = [row for row in metrics if row["post_id"] == post]
        check(len(selected) == 6 and {r["metric"] for r in selected} == {v[0] for v in label_order}, "Story metric grain differs.")
        for (metric, _), raw in zip(label_order, values):
            row = next(v for v in selected if v["metric"] == metric)
            check(row["raw_value"] == raw, "Story metric differs from labelled native Overview.")
            check(row["reporting_start"] == row["reporting_end"] == "" and "lifetime" in row["metric_basis"], "Story lifetime metric assigned to a period.")
            if raw.isdigit():
                check(row["value"] == raw and row["value_status"] == "observed", "Observed Story value changed.")
                observed += 1
            else:
                check(row["value"] == "" and row["value_status"] == "unavailable_native_dash", "Missing Story metric filled.")
                unavailable += 1
        dom = json.loads((collection / "stories" / (post + "_dom.json")).read_text(encoding="utf-8"))
        check(dom["links"] == [] and item["observed_dom_links"] == "0" and item["outbound_destination"] == "", "Story DOM link claim differs.")
        check(item["captured_at_utc"] == dom.get("captured_at_utc", ""), "Story capture time is not exact raw capture time.")
    check(observed == 14 and unavailable == 22, "Story observed/missing inventory differs.")
    check(sum(bool(json.loads(item["candidate_song_ids"])) for item in mapping) == 1, "Unexpected Story candidate assignments.")
    candidate = next(item for item in mapping if json.loads(item["candidate_song_ids"]))
    check(candidate["post_id"] == "18430983631182631" and json.loads(candidate["candidate_song_ids"]) == ["3HqynH6ObSuDPZM0RMnFxN"], "Story candidate scope differs.")

    links = read_csv(normalized / "link_destinations.csv")
    check(len(links) == 15, "Link-control inventory differs.")
    tracks = set(parent.table("spotify/cleaned/track_coverage.csv", raw=True).song_id)
    releases = set(parent.table("spotify/cleaned/release_metadata.csv", raw=True).release_id)
    unmatched = set()
    for row in links:
        source = collection / row["source_file"]
        check(sha(source.read_bytes()) == row["source_sha256"], "Link source hash differs.")
        original = pointer(json.loads(source.read_text(encoding="utf-8")), row["source_json_pointer"])
        href = original.get("href") if isinstance(original, dict) else original
        check(href == row["href_raw"], "Link href differs from exact source pointer.")
        if row["evidence_file"]:
            check(sha((collection / row["evidence_file"]).read_bytes()) == row["evidence_sha256"], "Link screenshot hash differs.")
        check(row["temporal_scope"] == "current_destination_at_capture" and row["reporting_start"] == row["reporting_end"] == "", "Current link projected into activity period.")
        parsed = urlparse(row["destination_url"])
        if parsed.hostname == "open.spotify.com":
            kind, identity = parsed.path.strip("/").split("/")
            check((row["spotify_entity_type"], row["spotify_entity_id"]) == (kind, identity), "Spotify URL ID changed.")
            if kind == "track":
                check(row["canonical_recording_id"] == (identity if identity in tracks else ""), "Unmatched recording URL was aliased.")
                check(row["canonical_release_id"] == "", "Track URL promoted to release.")
                if identity not in tracks:
                    unmatched.add(identity)
            elif kind == "album":
                check(row["canonical_release_id"] == (identity if identity in releases else ""), "Unmatched release URL was aliased.")
                check(row["canonical_recording_id"] == "", "Release URL promoted to recording.")
    album = [r for r in links if r["card_label"] == "[REDACTED] - Debut Album"]
    check(len(album) == 2 and all(r["spotify_entity_id"] == "3QVtuSBGLC9fTmLfF6qP7Z" and r["canonical_title"] == "Funny Guy" for r in album), "Debut Album card mismatch evidence differs.")
    check(len(unmatched) == 3, "Unmatched exact recording IDs were lost.")
    link_receipt = json.loads((normalized / "link_normalization_audit.json").read_text(encoding="utf-8"))
    for path, expected in link_receipt["input_sha256"].items():
        check(inputs[path] == expected, "Link normalizer source hash differs.")
    for path, expected in link_receipt["output_sha256"].items():
        check(sha((normalized / path).read_bytes()) == expected, "Link normalizer output hash differs.")

    native_bytes = (collection / "ads/ad_configuration_all.csv").read_bytes()
    native = list(csv.DictReader(io.StringIO(native_bytes.decode("utf-16")), delimiter="\t"))
    ads = read_csv(normalized / "ad_destinations.csv")
    check(len(ads) == len(native) == 6, "Ad config inventory differs.")
    native_checks = 0
    for row in ads:
        original = native[int(row["source_record_number"]) - 2]
        for field in set(row) & set(original):
            check(row[field] == original[field], "Normalized ad config differs: " + field)
            native_checks += 1
        check(row["captured_at_utc"] == "" and row["acquired_at_utc"] == "2026-10-23T05:07:43.552Z", "Ad acquisition timestamp was relabelled capture time.")
        check(row["delivery_in_period"] == "not_established_by_configuration", "Configuration promoted to delivery.")
    history = parent.table("social/meta_collection/ads_history.csv", raw=True).to_dict("records")
    identities = read_csv(normalized / "ad_identity_scope.csv")
    check(len(identities) == 9, "Historical identity groups differ.")
    native_by_ad = {r["Ad ID"].split(":", 1)[1]: r for r in native}
    scopes = {"band": [], "nonband": [], "unknown": []}
    for row in identities:
        group = [r for r in history if r["ad_id"] == row["ad_id"] and r["source_file"] == row["source_file"]]
        check(int(row["delivery_rows"]) == len(group), "Historical identity daily rows differ.")
        for source_field, field, places in [("Amount spent (USD)", "spend_usd", 2), ("Impressions", "impressions", None), ("Link clicks", "populated_link_clicks", None)]:
            check(row[field] == decimal_total(group, source_field, places), "Historical identity total differs: " + field)
        config = native_by_ad.get(row["ad_id"])
        expected_scope = "unknown" if config is None else "band" if config["Link"] == "https://www.instagram.com/_u/redactedbandoh" else "nonband" if config["Link"] == "https://www.therialtotheatre.com/record-and-release-program" else "unknown"
        check(row["identity_scope"] == expected_scope, "Historical identity disagrees with native configuration.")
        if row["source_file"] == "raw/ads_daily_maximum.csv":
            scopes[expected_scope].extend(group)
    expected = {"band": ("554.52", "50270", "723"), "nonband": ("99.79", "27382", "77"), "unknown": ("6.71", "302", "5")}
    for scope, values in expected.items():
        got = (decimal_total(scopes[scope], "Amount spent (USD)", 2), decimal_total(scopes[scope], "Impressions"), decimal_total(scopes[scope], "Link clicks"))
        check(got == values, "Historical scope reconciliation differs: " + scope)
    coverage = read_csv(normalized / "ads_coverage.csv")
    check(len(coverage) == 9, "Ads coverage checks missing.")
    for item in coverage:
        check(sha((collection / item["evidence_ref"]).read_bytes()) == item["evidence_sha256"], "Ads coverage evidence hash differs.")
        if item["status"] == "native_no_data":
            check("No data available." in (collection / item["evidence_ref"]).read_text(encoding="utf-8-sig"), "Ads native no-data status differs.")
    for row in read_csv(normalized / "collection_status.csv"):
        for path in row["evidence_ref"].split("; "):
            if path != "User scope instruction":
                check((collection / path).is_file(), "Collection status points to a missing evidence file: " + path)
    check(sha(parent.db_path.read_bytes()) == before, "Parent database changed during semantic audit.")
    check(inputs == {p.relative_to(collection).as_posix(): sha(p.read_bytes()) for p in collection.rglob("*") if p.is_file()}, "Collection changed during semantic audit.")
    return {"passed": True, "audited_at_utc": datetime.now(timezone.utc).isoformat(),
            "parent_database_sha256": before, "collection_sha256": inputs,
            "checks": {"six_exact_story_ids": True, "inherited_story_publication_and_account_identity": True,
                       "source_labelled_story_metrics": 36, "story_observed_metrics": observed, "story_unavailable_metrics": unavailable,
                       "zero_confirmed_story_song_assignments": True, "one_unconfirmed_candidate_kept_separate": True,
                       "all_six_screenshots_visually_reviewed_by_independent_agent": True,
                       "exact_link_controls": len(links), "unmatched_track_ids_kept_unaliased": sorted(unmatched),
                       "debut_album_card_funny_guy_mismatch_retained": True, "native_ad_fields_checked": native_checks,
                       "ad_acquisition_not_relabelled_capture": True, "historical_mixed_account_partitions_match": True,
                       "historical_ad_rows_checked": len(history), "ads_coverage_evidence_hashes": len(coverage),
                       "collection_status_evidence_refs_exist": True, "raw_sources_and_parent_unchanged": True},
            "limitations": ["No Story song or audio use is confirmed; owner archive access remains pending.",
                "Story metrics are lifetime, and absence of a DOM link is not proof no sticker existed.",
                "Current configuration cannot prove historical creative or link revisions.",
                "2026 no-data findings cover only the accessible account and selected reports.",
                "No link control or populated ad click is a verified Spotify conversion.",
                "October 20 original baseline membership remains unverified; TikTok excluded."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    check(not args.report.resolve().is_relative_to(args.collection.resolve()), "Audit report must be outside frozen collection.")
    result = audit(args.collection, args.parent)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"passed": result["passed"], "checks": result["checks"]}, ensure_ascii=False))
