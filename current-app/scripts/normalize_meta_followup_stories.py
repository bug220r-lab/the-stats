"""Normalize retained Story inspection and Ads coverage without filling gaps.

Only the six source IDs below are included. Visual annotations are evidence
judgments, not audio recognition or assignments inferred from date proximity.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "data/collection/meta-followup-20261023"
OUTPUT = COLLECTION / "normalized"
PRIOR = ROOT / "data/reconciliation/meta_spotify_crossref_20261023/events/recent_retained_posts.csv"

NOTES = {
    "18216593050358711": ("band_reference_no_identified_song", "Door text: The Machine Must Be, with a [REDACTED] sticker. The word Machine alone cannot identify THIS MACHINE.", "", ""),
    "18430983631182631": ("candidate_song_unverified", "Pumpkins, Redacted reference??, AND I CUT. Candidate is supported by partial phrase and existing song title only; no music label or lyric source confirms it.", "3HqynH6ObSuDPZM0RMnFxN", "The Cut (Starts Tomorrow)"),
    "18078399140713885": ("album_brand_artwork_reference", "Listen to [REDACTED] with me and we'll end up like this; artwork matches debut-album branding. The same artwork occurs on the Funny Guy embed, so it does not identify one recording or all album tracks.", "", ""),
    "18114350993331569": ("band_reference_no_identified_song", "Meme table of contents includes Obsession with [REDACTED]. No song title is visible; one source video was downloaded and retained, not audio-identified.", "", ""),
    "18117197771279451": ("unspecified_song_reference", "Meme says Listen to the new [REDACTED] song challenge, without a title. No release-date inference is used.", "", ""),
    "17965560240198897": ("band_reference_no_identified_song", "Meme says babe it's time to get [REDACTED] before something important. No song title is visible.", "", ""),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize():
    OUTPUT.mkdir(exist_ok=True, parents=True)
    prior = pd.read_csv(PRIOR, dtype=str, keep_default_na=False)
    mappings, metrics = [], []
    for post_id, (status, note, candidate_id, candidate_title) in NOTES.items():
        source = prior.loc[prior.post_id.eq(post_id)]
        if len(source) != 1:
            raise ValueError("Story must have one predecessor source row: " + post_id)
        row = source.iloc[0].to_dict()
        evidence = COLLECTION / "stories" / (post_id + ".txt")
        image = evidence.with_suffix(".png")
        dom = json.loads(evidence.with_name(post_id + "_dom.json").read_text(encoding="utf-8"))
        capture = dom.get("captured_at_utc", "")
        acquired = datetime.fromtimestamp(image.stat().st_mtime, timezone.utc).isoformat()
        text = evidence.read_text(encoding="utf-8")
        source_url = re.search(r'URL: "([^"]+)"', text).group(1)
        overview = text.split("Overview", 1)[1].split("tab group", 1)[0]
        match = re.search(r"text ((?:\d+|‑‑)(?: (?:\d+|‑‑)){5})", overview)
        if not match:
            raise ValueError("Cannot find six original Overview values: " + post_id)
        fields = match.group(1).split()
        common = {
            "platform_selected": "Instagram", "selected_account_id": row["selected_account_id"],
            "account_handle": row["account_handle"], "post_id": post_id, "post_key": row["post_key"],
            "published_local": row["published_local"], "publication_timezone": row["reporting_timezone"],
            "published_utc": row["published_utc"], "permalink": row["permalink"],
            "source_url": source_url, "captured_at_utc": capture, "acquired_at_utc": acquired,
            "capture_timestamp_status": "Recorded at capture" if capture else "Exact capture not persisted; acquired_at is screenshot write time, not publication time",
            "evidence_ref": evidence.relative_to(COLLECTION).as_posix(), "evidence_sha256": sha(evidence),
            "screenshot_ref": image.relative_to(COLLECTION).as_posix(), "screenshot_sha256": sha(image),
            "predecessor_source_file": row["source_file"], "predecessor_source_sha256": row["retained_source_sha256"],
        }
        mappings.append({**common, "mapping_status": status, "visual_evidence": note,
                         "assigned_song_ids": "[]", "candidate_song_ids": json.dumps([candidate_id] if candidate_id else []),
                         "candidate_song_title": candidate_title, "audio_use_verified": False,
                         "owner_confirmation_status": "User does not know; owner archive inspection pending access",
                         "audio_label_status": "Not exposed in retained Meta preview",
                         "outbound_destination": "", "destination_status": "No outbound link exposed in preview or rendered DOM; not proof none existed",
                         "observed_dom_links": len(dom["links"]), "stream_attribution_available": False,
                         "mapping_basis": "Human-readable visual inspection, exact source ID; candidate kept outside confirmed assignments"})
        for metric, raw_value in zip(("views", "reach", "interactions", "link_clicks", "sticker_taps", "instagram_follows"), fields):
            metrics.append({**common, "metric": metric, "raw_value": raw_value,
                            "value": "" if raw_value == "‑‑" else int(raw_value),
                            "value_status": "unavailable_native_dash" if raw_value == "‑‑" else "observed_zero" if raw_value == "0" else "observed",
                            "reporting_start": "", "reporting_end": "", "metric_basis": "Retained Story lifetime overview at later capture; not period activity"})
    pd.DataFrame(mappings).to_csv(OUTPUT / "story_song_map.csv", index=False)
    pd.DataFrame(metrics).to_csv(OUTPUT / "story_metrics.csv", index=False)
    checks = json.loads((COLLECTION / "ads/coverage_findings.json").read_text(encoding="utf-8"))["checks"]
    normalized_checks = []
    for check in checks:
        evidence = COLLECTION / "ads" / check["evidence_file"]
        if sha(evidence) != check["evidence_sha256"]:
            raise ValueError("Ads coverage evidence changed: " + str(evidence))
        normalized_checks.append({"check": check["check"], "status": check["status"], "source_result": check["value"],
                                  "limitation": check["limitation"], "ad_account_id": check["account_id"],
                                  "reporting_start": check["period_start"], "reporting_end": check["period_end"],
                                  "reporting_timezone": check["timezone"], "captured_at_utc": "",
                                  "source_recorded_at_utc": check["recorded_at_utc"],
                                  "timestamp_status": "Collector recorded time or export acquisition time; see acquisition_metadata.json",
                                  "evidence_ref": "ads/" + check["evidence_file"], "evidence_sha256": check["evidence_sha256"]})
    pd.DataFrame(normalized_checks).to_csv(OUTPUT / "ads_coverage.csv", index=False)
    return {"story_rows": len(mappings), "story_metric_rows": len(metrics), "confirmed_song_mappings": 0,
            "candidate_song_rows": 1, "ads_coverage_checks": len(normalized_checks),
            "missing_story_metric_cells": sum(r["value"] == "" for r in metrics)}


if __name__ == "__main__":
    print(json.dumps(normalize(), indent=2))
