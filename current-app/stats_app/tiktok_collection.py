"""Prepare and inspect local TikTok collection workspaces without activation.

This manifest tracks acquisition work, not verified analytics. Native sources,
identity, metric definitions and reconciliation still need review before import.
"""
from __future__ import annotations

import csv
from datetime import date
import hashlib
import io
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from stats_app.config import _path as _configured_path


SCHEMA_VERSION = 1
COLLECTION_TYPE = "tiktok_preparation"
QUEUE_STATUSES = {"not_collected", "collected", "partial", "verified_empty", "unavailable", "blocked", "not_applicable"}
QUEUE_COLUMNS = ["item_id", "label", "required", "status", "evidence_ref", "notes"]
QUEUE_ITEMS = [
    ("account_identity", "Account identity and access", True, "Verify the supplied profile, stable account ID and analytics access."),
    ("account_daily", "Account activity by reporting date", True, "Preserve actual date coverage, report clock, filters, units and native definitions."),
    ("owned_posts", "Owned post inventory and performance", True, "Retain IDs, captions, publication evidence, links and actual capture time; lifetime metrics stay snapshots."),
    ("song_activity", "Artist song and community activity", False, "If accessible, collect TikTok for Artists separately from the account's own posts."),
    ("audience", "Viewer and follower audience reports", False, "Keep viewer/follower populations, suppression and period definitions separate."),
    ("sound_mapping", "Post, sound and recording identity review", True, "Use documented mappings; keep unresolved songs and recordings unassigned."),
    ("reconciliation", "Native report reconciliation", True, "Compare compatible source totals, missingness, dates and scopes before any library activation."),
]
POST_COLUMNS = ["account", "post_id", "post_url", "published_at", "publication_timezone", "caption",
                "caption_status", "sound_id", "sound_title", "song_id", "song_title", "recording_version",
                "campaign_id", "creative_format", "hook", "call_to_action", "destination_url",
                "paid_organic_status", "mapping_status", "evidence_ref", "notes"]
SNAPSHOT_COLUMNS = ["account", "post_id", "post_url", "published_at", "publication_timezone", "target_age_hours",
                    "target_capture_at", "actual_captured_at", "actual_age_hours", "status", "evidence_ref", "notes"]


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _csv_bytes(columns, rows=()):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def _profile_handle(profile_url):
    if not isinstance(profile_url, str) or profile_url != profile_url.strip():
        raise ValueError("profile_url must be an exact HTTPS TikTok profile URL.")
    parsed = urlsplit(profile_url)
    if (parsed.scheme != "https" or parsed.netloc not in {"tiktok.com", "www.tiktok.com"}
            or parsed.query or parsed.fragment or not re.fullmatch(r"/@[A-Za-z0-9._]+/?", parsed.path)):
        raise ValueError("Use an HTTPS tiktok.com/@handle profile URL without a query, fragment, credentials or port.")
    return parsed.path.rstrip("/")[1:]


def _prepared_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("prepared_on must be an ISO calendar date (YYYY-MM-DD).")
    date.fromisoformat(value)
    return value


def _new_destination(output):
    destination = Path(output).expanduser().resolve()
    if destination.exists():
        raise FileExistsError("Choose a new collection directory; existing files and collections are never overwritten.")
    for variable in ("LOCALAPPDATA", "APPDATA", "STATS_DATA_DIR"):
        value = os.environ.get(variable)
        if not value:
            continue
        protected = _configured_path(value) if variable == "STATS_DATA_DIR" else Path(value).expanduser().resolve()
        if destination.is_relative_to(protected):
            raise ValueError("Create the preparation workspace outside AppData and the configured live library.")
    return destination


def create_collection(output: Path, *, profile_url: str, prepared_on: str = "2026-10-26") -> dict:
    """Create empty acquisition worksheets and mapping contracts in a fresh folder."""
    handle = _profile_handle(profile_url)
    prepared_on = _prepared_date(prepared_on)
    destination = _new_destination(output)
    template_root = Path(__file__).resolve().parents[1] / "templates"
    manifest = dict(schema_version=SCHEMA_VERSION, collection_type=COLLECTION_TYPE,
                    collection_id=destination.name, profile_url=profile_url, handle=handle,
                    identity_status="user_supplied_unverified", prepared_on=prepared_on,
                    status="preparation_only", integration_ready=False,
                    snapshot_target_ages_hours=[24, 72, 168, 672],
                    integration_gate="Review native identity, schemas, scope, dates, units, missingness and reconciliation before library activation.")
    queue = [dict(item_id=item, label=label, required="true" if required else "false",
                  status="not_collected", evidence_ref="", notes=notes)
             for item, label, required, notes in QUEUE_ITEMS]
    payloads = {"collection.json": _json_bytes(manifest),
                "collection_queue.csv": _csv_bytes(QUEUE_COLUMNS, queue),
                "post_log.csv": _csv_bytes(POST_COLUMNS),
                "snapshot_schedule.csv": _csv_bytes(SNAPSHOT_COLUMNS)}
    for name in ("account_daily", "video_snapshot", "song_daily"):
        payloads[f"config/{name}.mapping.json"] = (template_root / f"tiktok.{name}.mapping.template.json").read_bytes()
        metadata = json.loads((template_root / "tiktok.metadata.template.json").read_text(encoding="utf-8-sig"))
        metadata.update(account=handle, source_url=profile_url, identity_status="user_supplied_unverified")
        if name == "video_snapshot":
            metadata.update(entity_type="video")
        elif name == "song_daily":
            metadata.update(source_family="artists_csv", entity_type="song", content_scope="all_creators")
        payloads[f"config/{name}.metadata.json"] = _json_bytes(metadata)
    payloads["config/sound_recording_crosswalk.csv"] = (template_root / "tiktok.sound_recording_crosswalk.template.csv").read_bytes()
    destination.mkdir(parents=True, exist_ok=False)
    for folder in ("raw", "evidence", "stages", "config"):
        (destination / folder).mkdir(exist_ok=False)
    for relative, content in payloads.items():
        with (destination / relative).open("xb") as stream:
            stream.write(content)
        if (destination / relative).read_bytes() != content:
            raise OSError(f"Collection file readback differs: {relative}")
    return assess_collection(destination)


def _issue(issues, severity, code, message):
    issues.append(dict(severity=severity, code=code, message=message))


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate manifest key: {key}")
        result[key] = value
    return result


def _read_manifest(root):
    manifest_path = _evidence_path(root.resolve(), "collection.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_json)
    if not isinstance(manifest, dict) or manifest.get("collection_type") != COLLECTION_TYPE:
        raise ValueError("This is not a TikTok preparation collection manifest.")
    return manifest


def _evidence_path(root, reference):
    if not isinstance(reference, str) or not reference or reference != reference.strip():
        raise ValueError("An evidence reference must be a nonempty package-relative file path.")
    candidate = Path(reference)
    if candidate.is_absolute() or candidate.drive or any(part == ".." for part in candidate.parts):
        raise ValueError("Evidence references must stay within this collection package.")
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("Evidence reference is missing, is not a file, or leaves this collection package.")
    return resolved


def _read_queue(root, issues):
    rows = []
    try:
        with _evidence_path(root, "collection_queue.csv").open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != QUEUE_COLUMNS:
                raise ValueError("Collection queue headers must match the supplied worksheet exactly.")
            seen = set()
            required_by_id = {item: required for item, _, required, _ in QUEUE_ITEMS}
            for number, row in enumerate(reader, start=2):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"Collection queue row {number} has an inconsistent field count.")
                rows.append(row)
                item = row["item_id"]
                if item not in required_by_id or item in seen:
                    _issue(issues, "error", "queue_identity", f"Queue row {number} has an unknown or duplicate item_id.")
                seen.add(item)
                expected = "true" if required_by_id.get(item) else "false"
                if row["required"] != expected:
                    _issue(issues, "error", "queue_required", f"Queue item {item!r} has an invalid required flag.")
                if row["status"] not in QUEUE_STATUSES:
                    _issue(issues, "error", "queue_status", f"Queue item {item!r} has an unsupported or blank status.")
                if row["status"] == "not_applicable" and required_by_id.get(item):
                    _issue(issues, "error", "required_not_applicable", f"Required item {item!r} cannot be marked not_applicable.")
                if row["status"] in {"blocked", "unavailable", "not_applicable"} and not row["notes"].strip():
                    _issue(issues, "warning", "outcome_explanation_missing", f"Queue item {item!r} needs notes explaining its {row['status']} outcome.")
                if row["evidence_ref"]:
                    try:
                        resolved = _evidence_path(root, row["evidence_ref"])
                        if row["status"] in {"collected", "partial", "verified_empty"} and not any(
                                resolved.is_relative_to(root / folder) for folder in ("raw", "evidence", "stages")):
                            _issue(issues, "warning", "non_source_evidence", f"Queue item {item!r} refers to preparation configuration or a worksheet; this alone does not establish collected native evidence.")
                    except (OSError, ValueError) as exc:
                        _issue(issues, "error", "invalid_evidence_reference", f"Queue item {item!r}: {exc}")
                elif row["status"] in {"collected", "partial", "verified_empty"}:
                    _issue(issues, "error", "evidence_required", f"Queue item {item!r} needs an evidence_ref for its stated status.")
            missing = set(required_by_id) - seen
            if missing:
                _issue(issues, "error", "queue_items_missing", "Missing queue items: " + ", ".join(sorted(missing)))
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        _issue(issues, "error", "invalid_queue", str(exc))
    return rows


def _inventory(root, issues):
    records = []
    for category in ("raw", "evidence"):
        folder = root / category
        if not folder.is_dir():
            _issue(issues, "error", "missing_directory", f"Missing {category}/ directory.")
            continue
        if not folder.resolve().is_relative_to(root):
            _issue(issues, "error", "inventory_outside_package", f"The {category}/ directory resolves outside this collection.")
            continue
        try:
            for path in sorted(folder.rglob("*")):
                if not path.is_file():
                    continue
                if not path.resolve().is_relative_to(root):
                    _issue(issues, "error", "inventory_outside_package", f"An item under {category}/ resolves outside the collection.")
                    continue
                digest = hashlib.sha256()
                size = 0
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                        size += len(chunk)
                records.append(dict(path=path.relative_to(root).as_posix(), category=category, sha256=digest.hexdigest(), bytes=size))
        except OSError as exc:
            _issue(issues, "error", "inventory_unreadable", f"Could not inventory {category}/: {exc}")
    return records


def assess_collection(path: Path) -> dict:
    """Read the workspace and hash its sources; never import or modify it."""
    root = Path(path).expanduser().resolve()
    manifest = _read_manifest(root)
    issues = []
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != SCHEMA_VERSION:
        _issue(issues, "error", "manifest_schema", "Unsupported collection manifest schema_version.")
    try:
        handle = _profile_handle(manifest.get("profile_url"))
        if manifest.get("handle") != handle:
            raise ValueError("Manifest handle does not match its supplied profile URL.")
        _prepared_date(manifest.get("prepared_on"))
    except (TypeError, ValueError) as exc:
        _issue(issues, "error", "manifest_identity", str(exc))
    if manifest.get("identity_status") != "user_supplied_unverified":
        _issue(issues, "error", "identity_review_required", "The preparation manifest cannot certify account identity; retain user_supplied_unverified.")
    if manifest.get("status") != "preparation_only" or manifest.get("integration_ready") is not False:
        _issue(issues, "error", "activation_not_supported", "This preparation manifest cannot claim library activation or integration readiness.")
    queue = _read_queue(root, issues)
    inventory = _inventory(root, issues)
    progressed = bool(inventory) or any(row.get("status") != "not_collected" for row in queue)
    status = "needs_review" if any(item["severity"] == "error" for item in issues) else "collection_in_progress" if progressed else "preparation_only"
    return dict(schema_version=SCHEMA_VERSION, collection_type=COLLECTION_TYPE, path=str(root), collection_id=root.name,
                profile_url=manifest.get("profile_url", ""), handle=manifest.get("handle", ""),
                identity_status="user_supplied_unverified", manifest_identity_status=manifest.get("identity_status", ""),
                prepared_on=manifest.get("prepared_on", ""),
                status=status, integration_ready=False, library_modified=False,
                raw_file_count=sum(item["category"] == "raw" for item in inventory),
                evidence_file_count=sum(item["category"] == "evidence" for item in inventory),
                queue=queue, inventory=inventory, issues=issues,
                snapshot_target_ages_hours=[24, 72, 168, 672],
                integration_gate="Native identity, export semantics and reconciliation review, followed by a separate immutable-library activation, remain pending.")


def list_collections(root: Path) -> list[dict]:
    """List matching direct child collections; ignore unrelated source packages."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        return []
    collections = []
    for candidate in sorted(root.iterdir()):
        if not candidate.is_dir() or not candidate.resolve().is_relative_to(root):
            continue
        try:
            _read_manifest(candidate)
            collections.append(assess_collection(candidate))
        except (OSError, UnicodeError, ValueError):
            continue
    return collections
