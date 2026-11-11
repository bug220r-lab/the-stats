"""Normalize captured link evidence without browsing or modifying source files.

One Linktree card/control observation remains one row, even when two controls
have the same href. URL identifiers, not labels, establish catalog matches.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
LINK_COLUMNS = [
    "observation_id", "platform", "source_kind", "source_url", "source_post_id",
    "card_label", "control_label", "source_record_number", "control_number",
    "href_raw", "embedded_destination_url", "resolved_url", "destination_url",
    "destination_resolution", "destination_host", "destination_kind",
    "spotify_entity_type", "spotify_entity_id", "catalog_match_status",
    "canonical_recording_id", "canonical_release_id", "canonical_title",
    "canonical_recording_label", "catalog_match_basis", "card_label_match_status",
    "captured_at_utc", "temporal_scope", "historical_validity", "link_status",
    "source_file", "source_json_pointer", "source_sha256", "evidence_file",
    "evidence_sha256", "reporting_start", "reporting_end", "limitation",
]
ISSUE_COLUMNS = ["issue_id", "issue", "severity", "source_file", "source_json_pointer",
                 "captured_at_utc", "card_label", "detail", "status"]
AD_NATIVE_FIELDS = ["Ad ID", "Ad Name", "Campaign ID", "Campaign Name", "Ad Set ID",
                    "Ad Set Time Start", "Ad Set Time Stop", "Link Object ID", "Instagram Account ID",
                    "Link", "Call to Action", "Call to Action Link", "Instagram Preview Link",
                    "Permalink", "URL Tags", "Mobile App Deep Link"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def id_for(*values: str) -> str:
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()[:24]


def validate_ad_observations(collection: Path, observations: list[dict]) -> int:
    """Reconcile every retained field to the native export, including blanks."""
    native_sources = {}
    checks = 0
    for row in observations:
        source_name = row["source_file"]
        if source_name != Path(source_name).name:
            raise ValueError("Ad source filename must be a filename within ads/")
        if source_name not in native_sources:
            content = (collection/"ads"/source_name).read_bytes()
            text = content.decode("utf-16" if content.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
            delimiter = "\t" if "\t" in text.splitlines()[0] else ","
            native_sources[source_name] = list(csv.DictReader(io.StringIO(text), delimiter=delimiter))
        source = native_sources[source_name][int(row["source_record_number"])-2]
        for field in AD_NATIVE_FIELDS:
            if source.get(field) != row[field]:
                raise ValueError(f"Ad field differs from native export: {row['Ad ID']} / {field}")
            checks += 1
    return checks


def embedded_url(href: str) -> str:
    """Decode only an observed Meta redirect parameter; this is not navigation."""
    parsed = urlparse(href)
    if parsed.hostname in {"l.facebook.com", "l.instagram.com"}:
        return parse_qs(parsed.query).get("u", [""])[0]
    return ""


def spotify_identity(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.hostname != "open.spotify.com":
        return "", ""
    match = re.fullmatch(r"/(track|album)/([A-Za-z0-9]{22})/?", parsed.path)
    return match.groups() if match else ("", "")


def catalog_match(url: str, tracks: dict, releases: dict, recordings: dict) -> dict:
    kind, identity = spotify_identity(url)
    result = dict(spotify_entity_type=kind, spotify_entity_id=identity,
                  catalog_match_status="not_spotify_entity", canonical_recording_id="",
                  canonical_release_id="", canonical_title="", canonical_recording_label="",
                  catalog_match_basis="")
    if kind == "track":
        result["catalog_match_status"] = "unmatched_exact_track_id"
        if identity in tracks:
            result.update(catalog_match_status="matched_exact_track_id",
                          canonical_recording_id=identity,
                          canonical_title=recordings.get(identity, {}).get("title", tracks[identity]["recording_label"]),
                          canonical_recording_label=tracks[identity]["recording_label"],
                          catalog_match_basis="Exact URL track ID in prior spotify/cleaned/track_coverage.csv; title from exact-ID recordings.csv")
    elif kind == "album":
        result["catalog_match_status"] = "unmatched_exact_release_id"
        if identity in releases:
            result.update(catalog_match_status="matched_exact_release_id",
                          canonical_release_id=identity, canonical_title=releases[identity]["release_title"],
                          catalog_match_basis="Exact URL album ID in prior spotify/cleaned/release_metadata.csv; no recording alias inferred")
    return result


def normalize(collection: Path, catalog_root: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    source_names = ["links/linktree-cards.json", "social_branding/instagram-profile.json",
                    "social_branding/facebook-profile.json", "links/facebook-998829296519708-destination.json",
                    "ads/ad_destination_observations.json", "ads/ad_configuration_all.csv"]
    source_names = [name for name in source_names if (collection / name).is_file()]
    required = {"links/linktree-cards.json", "social_branding/instagram-profile.json",
                "social_branding/facebook-profile.json", "links/facebook-998829296519708-destination.json"}
    if not required.issubset(source_names):
        raise ValueError(f"Missing required inputs: {sorted(required - set(source_names))}")
    source_hashes = {name: digest(collection / name) for name in source_names}
    catalogs = {name: catalog_root / "spotify" / "cleaned" / name
                for name in ("track_coverage.csv", "release_metadata.csv", "recordings.csv")}
    catalog_hashes = {name: digest(path) for name, path in catalogs.items()}
    tracks = {row["song_id"]: row for row in read_csv(catalogs["track_coverage.csv"])}
    releases = {row["release_id"]: row for row in read_csv(catalogs["release_metadata.csv"])}
    recordings = {row["song_id"]: row for row in read_csv(catalogs["recordings.csv"])}
    rows, issues = [], []

    def load(name):
        return json.loads((collection / name).read_text(encoding="utf-8-sig"))

    def issue(name, pointer, captured, card, code, detail, status="unresolved", severity="warning"):
        issues.append(dict(issue_id=id_for(name, pointer, code), issue=code, severity=severity,
                           source_file=name, source_json_pointer=pointer, captured_at_utc=captured,
                           card_label=card, detail=detail, status=status))

    def append(name, pointer, captured, href, *, platform, kind, source_url, card="", label="",
               record=1, control=1, post_id="", resolved="", evidence="", limitation=""):
        if not href:
            raise ValueError(f"Empty href must not become a link observation: {name} {pointer}")
        if datetime.fromisoformat(captured.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError("Capture timestamp must retain its timezone")
        embedded = embedded_url(href)
        target = resolved or embedded or href
        match = catalog_match(target, tracks, releases, recordings)
        host = urlparse(target).hostname or ""
        destination_kind = ("spotify_track" if match["spotify_entity_type"] == "track" else
                            "spotify_release" if match["spotify_entity_type"] == "album" else
                            "link_hub" if host == "linktr.ee" else "external_website")
        if host == "blimpcitybeats.org":
            destination_kind = "community_music_submission"
        label_match = "not_applicable"
        if card:
            label_match = ("unresolved_exact_id_not_in_catalog" if not match["canonical_title"] else
                           "matches_catalog_title" if card.casefold() == match["canonical_title"].casefold() else
                           "does_not_match_catalog_destination_title")
        row = dict.fromkeys(LINK_COLUMNS, "")
        row.update(observation_id=id_for(name, pointer, captured, href), platform=platform,
                   source_kind=kind, source_url=source_url, source_post_id=post_id, card_label=card,
                   control_label=label, source_record_number=record, control_number=control,
                   href_raw=href, embedded_destination_url=embedded, resolved_url=resolved,
                   destination_url=target,
                   destination_resolution="observed_browser_navigation" if resolved else "decoded_redirect_parameter_only" if embedded else "observed_direct_href",
                   destination_host=host, destination_kind=destination_kind, **match,
                   card_label_match_status=label_match, captured_at_utc=captured,
                   temporal_scope="current_destination_at_capture",
                   historical_validity="Earlier destinations and click-time routing not established",
                   link_status="observed", source_file=name, source_json_pointer=pointer,
                   source_sha256=source_hashes[name],
                   evidence_file=evidence if evidence and (collection/evidence).is_file() else "",
                   evidence_sha256=digest(collection/evidence) if evidence and (collection/evidence).is_file() else "",
                   limitation=limitation or "Observed link configuration is not a click, landing-page visit or Spotify stream; current destination cannot be projected backward.")
        rows.append(row)
        if match["catalog_match_status"].startswith("unmatched_"):
            issue(name, pointer, captured, card, "unmatched_spotify_id",
                  f"Observed {match['spotify_entity_type']} ID {match['spotify_entity_id']} is not in the prior catalog; label similarity is not an alias bridge.")
        if label_match == "does_not_match_catalog_destination_title":
            issue(name, pointer, captured, card, "card_label_destination_mismatch",
                  f"Card label is {card!r}; actual URL is a {match['spotify_entity_type']} for {match['canonical_title']!r} ({match['spotify_entity_id']}).")

    name = "links/linktree-cards.json"
    cards = load(name)
    for index, card in enumerate(cards):
        links = card["links"]
        if not links:
            later = any(other["card"] == card["card"] and other.get("links") for other in cards[index+1:])
            issue(name, f"/{index}", card["captured_at_utc"], card["card"], "empty_transient_capture",
                  "No link controls captured; omitted from link observations. Later nonempty capture exists." if later else "No link controls captured; cannot infer absence of destinations.",
                  "superseded_by_later_capture" if later else "unresolved", "info")
            continue
        for control, link in enumerate(links):
            append(name, f"/{index}/links/{control}", card["captured_at_utc"], link["href"],
                   platform="Linktree", kind="music_card_control", source_url=card["source_url"],
                   card=card["card"], label=link["label"], record=index+1, control=control+1)
    name = "social_branding/instagram-profile.json"
    data = load(name)
    append(name, "/link_href", data["captured_at_utc"], data["link_href"], platform="Instagram",
           kind="profile_link", source_url=data["source_url"], label=data["link_label"],
           evidence="social_branding/instagram-profile.png")
    name = "social_branding/facebook-profile.json"
    data = load(name)
    for index, link in enumerate(data["links"]):
        append(name, f"/links/{index}", data["captured_at_utc"], link["href"], platform="Facebook",
               kind="profile_link", source_url=data["source_url"], label=link["text"], control=index+1,
               evidence="social_branding/facebook-profile.png")
    name = "links/facebook-998829296519708-destination.json"
    data = load(name)
    append(name, "/link_href", data["captured_at_utc"], data["link_href"], platform="Facebook",
           kind="historical_post_link_at_current_capture", source_url=data["source_url"],
           label=data["destination_title"], post_id=data["post_id"], resolved=data["resolved_url"],
           evidence="links/facebook-998829296519708.png",
           limitation=data["scope"] + ". Current navigation does not establish historic clicks or routing.")

    ad_rows = []
    native_ad_field_checks = 0
    ad_name = "ads/ad_destination_observations.json"
    if ad_name in source_hashes:
        ad_observations = load(ad_name)
        native_ad_field_checks = validate_ad_observations(collection, ad_observations)
        for index, raw in enumerate(ad_observations):
            row = dict(raw)  # All original names, prefixed IDs and blank fields are retained.
            derived = dict(evidence_source_file=ad_name, evidence_json_pointer=f"/{index}",
                           evidence_source_sha256=source_hashes[ad_name],
                           configuration_file=f"ads/{raw['source_file']}",
                           configuration_sha256=source_hashes.get(f"ads/{raw['source_file']}", ""),
                           captured_at_utc="",
                           capture_timestamp_status="unavailable_in_native_export",
                           acquisition_timestamp_basis="acquired_at_utc is download/acquisition time only; not an embedded source capture timestamp",
                           historical_validity="Current configuration is not historical creative revision or delivery evidence",
                           destination_status="observed_configured_link" if raw["Link"] else "unavailable_blank_configuration_field",
                           attribution_limitation="No click, Spotify visit or stream established; unpublished drafts are not delivered ads")
            row.update(derived)
            ad_rows.append(row)

    outputs = {"link_destinations.csv": (rows, LINK_COLUMNS),
               "link_evidence_issues.csv": (issues, ISSUE_COLUMNS)}
    if ad_rows:
        outputs["ad_destinations.csv"] = (ad_rows, list(dict.fromkeys(key for row in ad_rows for key in row)))
    for name, (data, columns) in outputs.items():
        write_csv(output/name, data, columns)
    unchanged = all(digest(collection/name) == value for name, value in source_hashes.items())
    catalogs_unchanged = all(digest(catalogs[name]) == value for name, value in catalog_hashes.items())
    if not unchanged or not catalogs_unchanged:
        raise RuntimeError("A source changed during normalization; outputs require rerun")
    counts = {name: len(data) for name, (data, _) in outputs.items()}
    audit = dict(passed=True, normalized_at_utc=datetime.now(timezone.utc).isoformat(),
                 source_files_unchanged=unchanged, catalog_files_unchanged=catalogs_unchanged,
                 input_sha256=source_hashes, catalog_sha256=catalog_hashes,
                 script_sha256=digest(Path(__file__)), counts=counts,
                 native_ad_field_checks=native_ad_field_checks,
                 catalog_tables=[f"spotify/cleaned/{name}" for name in catalogs],
                 linktree_controls=sum(row["platform"] == "Linktree" for row in rows),
                 linktree_nonempty_cards=sum(bool(card["links"]) for card in cards),
                 linktree_unique_exact_hrefs=len({row["href_raw"] for row in rows if row["platform"] == "Linktree"}),
                 unmatched_track_ids=sorted({row["spotify_entity_id"] for row in rows if row["catalog_match_status"] == "unmatched_exact_track_id"}),
                 output_sha256={name: digest(output/name) for name in outputs},
                 grain="One captured source control per link row; repeated href controls are not click counts or extra audiences",
                 limitations=["Current link state cannot establish prior destinations or conversion attribution.",
                              "No recording equivalence inferred from card titles or release membership.",
                              "Album links remain release-level; not summed with recording-level activity.",
                              "All existing snapshots and raw sources remain unchanged."])
    (output/"link_normalization_audit.json").write_text(json.dumps(audit, indent=2)+"\n", encoding="utf-8")
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, default=ROOT/"data/collection/meta-followup-20261023")
    parser.add_argument("--catalog-root", type=Path, default=ROOT/"data/reconciliation/meta_20261023/package")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(normalize(args.collection, args.catalog_root, args.output or args.collection/"normalized"), indent=2))


if __name__ == "__main__":
    main()
