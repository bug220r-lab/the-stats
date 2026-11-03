"""Reconcile historical Meta delivery to newly captured current ad identities.

No previous snapshot or analysis is changed. Exact native ad IDs bridge current
configuration to historical delivery; names alone remain unresolved candidates.
"""
from datetime import datetime, timezone
from decimal import Decimal
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from stats_app.analysis_repository import load_registered_analysis
from stats_app.config import load_settings
from stats_app.storage import StorageError


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def native_id(value, prefix):
    if not value:
        return ""
    if not value.startswith(prefix) or not value[len(prefix):].isdigit():
        raise StorageError("Unexpected native ID encoding in configuration.")
    return value[len(prefix):]


def rows(raw, *, encoding="utf-8-sig", delimiter=","):
    reader = csv.DictReader(io.StringIO(raw.decode(encoding), newline=""), delimiter=delimiter)
    values = list(reader)
    if any(None in row for row in values):
        raise StorageError("Nonrectangular source CSV.")
    return values


def total(group, column, places=None):
    values = [Decimal(item[column]) for item in group if item[column] != ""]
    if not values:
        return ""
    value = sum(values, Decimal(0))
    return format(value, ".2f" if places == 2 else "f")


def classify(config):
    if config is None:
        return "unknown", "not_in_current_configuration_export"
    triple = (config["Link Object ID"], config["Instagram Account ID"], config["Link"])
    if triple == ("o:118246571240106", "x:5324346047653591", "https://www.instagram.com/_u/redactedbandoh"):
        return "band", "exact_ad_id_current_configuration_band_identity"
    if triple == ("o:723656497712673", "x:935441079885561", "https://www.therialtotheatre.com/record-and-release-program"):
        return "nonband", "exact_ad_id_current_configuration_rialto_identity"
    return "unknown", "current_configuration_identity_unresolved"


def write_csv(path, values):
    if path.exists():
        raise FileExistsError("Preserving previous identity audit output: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)


def run(collection, data_dir):
    collection = Path(collection).resolve()
    repo = load_registered_analysis(data_dir)
    if repo is None or repo.metadata["analysis_version"] != "meta-collection-20261023":
        raise StorageError("Run this historical audit against the retained active Meta collection before follow-up promotion.")
    db_before = sha(repo.db_path.read_bytes())
    history_path = "social/meta_collection/ads_history.csv"
    campaigns_path = "social/meta_collection/ads_campaigns.csv"
    history_raw, campaign_raw = repo.original_bytes(history_path), repo.original_bytes(campaigns_path)
    history, campaigns = rows(history_raw), rows(campaign_raw)
    config_path = collection / "ads/ad_configuration_all.csv"
    config_raw = config_path.read_bytes()
    config_values = rows(config_raw, encoding="utf-16", delimiter="\t")
    acquisition = json.loads((collection / "ads/acquisition_metadata.json").read_text(encoding="utf-8"))
    config_metadata = next(item for item in acquisition["reports"] if item["file"] == config_path.name)
    if config_metadata["sha256"] != sha(config_raw):
        raise StorageError("Configuration acquisition hash mismatch.")
    config = {}
    for record, item in enumerate(config_values, 2):
        key = native_id(item["Ad ID"], "a:")
        if not key or key in config:
            raise StorageError("Configuration ad IDs must be present and unique.")
        config[key] = dict(item, source_record=record)
    now = datetime.now(timezone.utc).isoformat()
    groups = {}
    for item in history:
        key = (item["ad_account_id"], item["ad_id"], item["source_file"])
        groups.setdefault(key, []).append(item)
    if len(history) != 3161 or len(groups) != 9:
        raise StorageError("Unexpected historical delivery inventory; reassess audit scope.")
    keys = [(item["ad_account_id"], item["ad_id"], item["reporting_start"], item["reporting_end"], item["source_file"]) for item in history]
    if len(keys) != len(set(keys)):
        raise StorageError("Duplicate ad/day/source keys would overcount delivery.")
    output = []
    for (account, ad_id, source), group in sorted(groups.items()):
        cfg = config.get(ad_id)
        scope, status = classify(cfg)
        names = sorted({r["Ad name"] for r in group})
        campaign_ids = sorted({r["campaign_id"] for r in group})
        if cfg and campaign_ids != [native_id(cfg["Campaign ID"], "cg:")]:
            raise StorageError("Ad bridge has conflicting campaign IDs.")
        positive = [r for r in group if Decimal(r["Amount spent (USD)"]) > 0]
        hint = ("candidate_nonband_name_only" if any("Rialto" in name for name in names) else
                "candidate_band_name_only" if scope == "unknown" else "")
        output.append({
            "ad_account_id": account, "ad_id": ad_id, "campaign_id": " | ".join(campaign_ids),
            "ad_names_json": json.dumps(names, ensure_ascii=False), "identity_scope": scope,
            "identity_status": status, "unverified_name_hint": hint,
            "reporting_start": min(r["reporting_start"] for r in group), "reporting_end": max(r["reporting_end"] for r in group),
            "reporting_timezone": "Eastern Time", "currency": "USD", "delivery_rows": len(group),
            "positive_spend_start": min((r["reporting_start"] for r in positive), default=""),
            "positive_spend_end": max((r["reporting_end"] for r in positive), default=""),
            "positive_spend_days": len(positive), "spend_usd": total(group, "Amount spent (USD)", 2),
            "impressions": total(group, "Impressions"), "populated_link_clicks": total(group, "Link clicks"),
            "link_click_rows_observed": sum(r["Link clicks"] != "" for r in group),
            "link_click_rows_unavailable": sum(r["Link clicks"] == "" for r in group),
            "clicks_all": total(group, "Clicks (all)"), "source_file": source,
            "historical_table": history_path, "historical_table_sha256": sha(history_raw),
            "historical_source_sha256": group[0]["source_sha256"],
            "historical_source_records_json": json.dumps([r["source_record"] for r in group]),
            "configuration_source": "ads/ad_configuration_all.csv" if cfg else "",
            "configuration_source_sha256": sha(config_raw) if cfg else "", "configuration_source_record": cfg["source_record"] if cfg else "",
            "configuration_acquired_at_utc": config_metadata["acquired_at_utc"] if cfg else "",
            "configuration_metadata_ref": "ads/acquisition_metadata.json" if cfg else "",
            "link_object_id_raw": cfg["Link Object ID"] if cfg else "", "instagram_account_id_raw": cfg["Instagram Account ID"] if cfg else "",
            "destination_url": cfg["Link"] if cfg else "", "instagram_preview_url": cfg["Instagram Preview Link"] if cfg else "",
            "creative_body": cfg["Body"] if cfg else "", "url_tags_raw": cfg["URL Tags"] if cfg else "",
            "configuration_reporting_basis": "current_configuration_at_capture; historical revision history unavailable" if cfg else "configuration unavailable",
            "identity_evidence_ref": "ads/ad_120203882112190452_preview_ax.txt" if scope == "nonband" else "ads/ad_configuration_all.csv" if cfg else history_path,
            "captured_at_utc": "", "capture_status": "Native configuration has no embedded capture timestamp; acquisition time and analysis time are separate",
            "audited_at_utc": now, "join_rule": "Exact native ad ID and matching campaign ID; names do not establish identity",
        })
    totals = []
    for source in sorted({r["source_file"] for r in output}):
        for scope in ("band", "nonband", "unknown"):
            group = [r for r in output if r["source_file"] == source and r["identity_scope"] == scope]
            if not group:
                continue
            totals.append({"source_file": source, "identity_scope": scope, "ad_count": len(group),
                           "delivery_rows": sum(r["delivery_rows"] for r in group),
                           "spend_usd": total(group, "spend_usd", 2), "impressions": total(group, "impressions"),
                           "populated_link_clicks": total(group, "populated_link_clicks"),
                           "link_click_rows_observed": sum(r["link_click_rows_observed"] for r in group),
                           "link_click_rows_unavailable": sum(r["link_click_rows_unavailable"] for r in group),
                           "clicks_all": total(group, "clicks_all"), "currency": "USD", "reporting_timezone": "Eastern Time",
                           "basis": "Disjoint ad/day rows within one export; no campaign totals or unique audiences added",
                           "identity_basis": "Current exact-ad-ID configuration; deleted identities unresolved",
                           "captured_at_utc": "", "audited_at_utc": now})
    maximum = [r for r in output if r["source_file"] == "raw/ads_daily_maximum.csv"]
    if total(maximum, "spend_usd", 2) != "661.02" or total(maximum, "impressions") != "77954" or total(maximum, "populated_link_clicks") != "805":
        raise StorageError("Identity partition failed to reconcile original historical totals.")
    campaign_reviews = []
    for item in campaigns:
        if any(item[key] for key in ("ad_id", "campaign_id", "ad_set_id")):
            raise StorageError("Campaign export unexpectedly supplies a stable identity; reassess review.")
        candidates = [r for r in maximum if item["Campaign name"] in json.loads(r["ad_names_json"])
                      and Decimal(r["spend_usd"]) == Decimal(item["Amount spent (USD)"])
                      and Decimal(r["impressions"]) == Decimal(item["Impressions"])]
        campaign_reviews.append({"source_file": item["source_file"], "source_record": item["source_record"],
            "campaign_name": item["Campaign name"], "identity_scope": "unknown_native_campaign_id_absent",
            "spend_usd": item["Amount spent (USD)"], "impressions": item["Impressions"], "populated_link_clicks": item["Link clicks"],
            "reconciliation_candidate_ad_ids": " | ".join(r["ad_id"] for r in candidates),
            "reconciliation_status": "Name and additive totals match; not an independent identity bridge" if candidates else "No candidate match",
            "historical_table": campaigns_path, "historical_table_sha256": sha(campaign_raw), "captured_at_utc": "",
            "audited_at_utc": now, "aggregation_rule": "Campaign totals overlap daily ad totals; never add levels"})
    if sha(repo.db_path.read_bytes()) != db_before or config_path.read_bytes() != config_raw:
        raise StorageError("Audit inputs changed.")
    out = collection / "normalized"
    write_csv(out / "ad_identity_scope.csv", output)
    write_csv(out / "ad_identity_totals.csv", totals)
    write_csv(out / "ad_campaign_identity_review.csv", campaign_reviews)
    report = {"passed": True, "audited_at_utc": now, "source_database_sha256_before": db_before,
              "source_database_sha256_after": sha(repo.db_path.read_bytes()), "source_analysis_version": repo.metadata["analysis_version"],
              "source_assets_sha256": {history_path: sha(history_raw), campaigns_path: sha(campaign_raw)},
              "configuration_sha256": sha(config_raw), "configuration_rows": len(config_values),
              "configuration_acquired_at_utc": config_metadata["acquired_at_utc"],
              "historical_ad_rows": len(history), "historical_ad_ids": len({r["ad_id"] for r in history}),
              "historical_campaign_rows": len(campaigns), "configuration_ad_ids_not_in_history": sorted(set(config)-{r["ad_id"] for r in history}),
              "identity_totals": totals, "historical_total_spend_usd": "661.02", "historical_total_impressions": "77954",
              "historical_populated_link_clicks": "805", "missing_clicks_not_zero": True,
              "limitations": ["Current configuration is not historical creative revision history.",
                  "Three deleted/unexported historical identities remain unresolved; names are candidate clues only.",
                  "Campaign-native IDs are absent; campaign totals are reconciliation evidence, not an additional identity bridge.",
                  "Ad configuration links do not prove a click, landing-page visit, Spotify destination or streaming conversion."],
              "prior_conclusion_corrections": [
                  "$661.02 was mixed-account historical spend, not fully verified band spend; exact current configuration identifies $554.52 band, $99.79 nonband and $6.71 unresolved.",
                  "Withdraw February generic-band-promotion interpretation: $99.79 is Rialto and $0.15 remains unknown with a Rialto-only name clue.",
                  "June album timing window remains June 4-11, but the confirmed band-identified ad is $199.94/19,672 impressions/300 populated clicks; the $2.49/132/2 deleted duplicate remains unknown.",
                  "Funny Guy $149.96 and Crawl $99.64 retain exact-ID band configuration support; current destinations are Instagram profile, not Spotify.",
                  "December confirmed band-identified ad is $104.98/9,543/110, plus unresolved $4.07/133/3; Spotify history still begins January 2024.",
                  "2026 organic post/song comparisons and social/Spotify correlations did not use Ads rows and are unaffected by this identity correction."]}
    report_path = collection / "historical_ad_identity_audit.json"
    with report_path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.collection, load_settings().data_dir), ensure_ascii=False, indent=2))
