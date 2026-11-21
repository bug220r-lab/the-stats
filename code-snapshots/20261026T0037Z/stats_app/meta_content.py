"""Normalize native Meta exports into separately retained content observations.

This module never updates a predecessor asset, fills missing metrics, sums
snapshots, or infers that a requested export window is a complete history.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from stats_app.meta_followup import SupplementSpec, build_evidence_supplement

NAMESPACE = "meta_content_20261023"
PREFIX = f"social/{NAMESPACE}/"
VERSION = "meta-content-20261023"
SPEC = SupplementSpec(
    namespace=NAMESPACE, lineage_key=NAMESPACE, title="Meta content history collection",
    handoff_filename="META_CONTENT_HANDOFF.md",
    evidence_type="Separate native content snapshots; inherited captures and statistics unchanged",
    limitations=("Requested dates do not establish complete account history.",
                 "Lifetime outcomes describe their capture and are not publication-day activity.",
                 "Missing metrics, publication timezones and capture times remain unknown.",
                 "Different platform/account identities and capture vintages are not summed."),
)

# Only explicit native labels are mapped. All other fields remain in native_record_json.
METRIC_COLUMNS = {
    "views": "Views", "reach": "Reach", "likes": "Likes", "comments": "Comments",
    "shares": "Shares", "saves": "Saves", "reactions": "Reactions", "follows": "Follows",
    "interactions": "Interactions", "engagement_actions": "Reactions, Comments and Shares",
    "replies": "Replies", "navigation": "Navigation", "sticker_taps": "Sticker taps",
    "link_clicks": "Link Clicks", "profile_visits": "Profile visits", "total_clicks": "Total clicks",
    "organic_views": "Views from Organic posts", "boosted_views": "Views from Boosted posts", "impressions": "Impressions",
    "viewers": "Viewers", "likes_and_reactions": "Likes and reactions",
}
BASE_FIELDS = [
    "platform_selected", "selected_account_id", "account_id_type", "selected_asset_id", "account_handle",
    "post_id", "author_account_id", "author_name", "author_username", "author_scope", "post_type",
    "description", "title", "permalink", "publication_date", "published_local", "published_local_raw",
    "publication_date_status", "publication_timezone", "publication_timezone_status", "timezone_evidence_ref",
    "published_utc", "published_utc_status", "snapshot_timestamp", "captured_at_utc", "acquired_at_utc",
    "capture_timestamp_status", "source_file", "source_sha256", "source_record", "source_url", "source_kind",
    "metadata_file", "metadata_sha256", "metric_platform_scope", "metric_scope_evidence_ref", "measurement_type",
    "reporting_basis_raw", "requested_start", "requested_end", "publication_filter", "publication_status",
    "is_crosspost_raw", "is_share_raw", "native_record_json", "native_row_status", "native_row_reason", "observation_id", "evidence_refs_json",
]
CONTENT_FIELDS = BASE_FIELDS + [f for metric in METRIC_COLUMNS for f in (metric, metric + "_status", metric + "_raw", metric + "_native_label")]
QUARANTINE_FIELDS = ["source_file", "source_sha256", "source_record", "reason", "recovery_status", "expected_fields", "actual_fields", "raw_record_json"]
STATUS_FIELDS = ["dataset", "status", "detail", "evidence_ref", "captured_at_utc"]


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _stamp(value):
    if not value:
        return ""
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Capture timestamps require an explicit UTC offset.")
    return parsed.astimezone(timezone.utc).isoformat()


def _identifier(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value):
        raise ValueError(f"{field} must be an exact string of native ID digits.")
    return value


def parse_count(raw, *, present=True):
    """Return exact decimal strings, never float-round IDs or impute counts."""
    if not present:
        return "", "metric_not_in_export"
    value = raw.strip()
    if not value:
        return "", "missing_source_blank"
    if value.casefold() in {"n/a", "na", "null", "none"} or all(c in "-—–‐‑‒−" for c in value):
        return "", "unavailable_source_marker"
    # Reject rounded/ambiguous displays rather than treating 1.2K as exact.
    if re.fullmatch(r"[\d,.]+\s*[KMBkmb]", value):
        return "", "rounded_display_not_exact"
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", value):
        return "", "invalid_numeric_source_value"
    try:
        number = Decimal(value.replace(",", ""))
    except InvalidOperation:
        return "", "invalid_numeric_source_value"
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        return "", "invalid_count_source_value"
    return str(int(number)), "observed_zero" if number == 0 else "observed"


def _publication(raw, zone):
    result = dict(published_local_raw=raw, published_local=raw, publication_date="",
                  publication_date_status="missing_source_blank" if not raw else "unparsed_source_value",
                  published_utc="", published_utc_status="publication_time_unknown")
    parsed = None
    for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(raw, fmt)
            break
        except ValueError:
            pass
    if parsed is None:
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                result.update(publication_date=date.fromisoformat(raw).isoformat(), publication_date_status="observed_date_only")
            elif re.fullmatch(r"[A-Za-z]+ \d{1,2}, \d{4}", raw):
                for fmt in ("%b %d, %Y", "%B %d, %Y"):
                    try:
                        result.update(publication_date=datetime.strptime(raw, fmt).date().isoformat(), publication_date_status="observed_date_only")
                        break
                    except ValueError:
                        pass
        except ValueError:
            pass
        return result
    result.update(published_local=parsed.isoformat(), publication_date=parsed.date().isoformat(), publication_date_status="observed")
    if not zone:
        result["published_utc_status"] = "publication_timezone_unknown"
        return result
    zone_name = {"Pacific Time": "America/Los_Angeles", "Pacific time": "America/Los_Angeles"}.get(zone, zone)
    try:
        tz = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        result["published_utc_status"] = "unsupported_publication_timezone"
        return result
    first, second = parsed.replace(tzinfo=tz, fold=0), parsed.replace(tzinfo=tz, fold=1)
    if first.utcoffset() != second.utcoffset():
        result["published_utc_status"] = "ambiguous_or_nonexistent_local_time"
        return result
    result.update(published_utc=first.astimezone(timezone.utc).isoformat(), published_utc_status="derived_from_explicit_publication_timezone")
    return result


def _recover_identity_prefix(header, values, platform, selected_account):
    """Recover only an anchored native prefix, never align a metric suffix."""
    facebook = ["Post ID", "Page ID", "Page name", "Title", "Description", "Duration (sec)", "Publish time",
                "Caption type", "Permalink", "Is crosspost", "Is share", "Post type", "Languages", "Custom labels",
                "Funded content status", "Data comment", "Date"]
    instagram = ["Post ID", "Account ID", "Account username", "Account name", "Description", "Duration (sec)",
                 "Publish time", "Permalink", "Post type", "Data comment", "Date"]
    prefix = facebook if platform == "Facebook" else instagram
    if not len(prefix) <= len(values) < len(header) or header[:len(prefix)] != prefix:
        return None
    native = dict(zip(prefix, values[:len(prefix)]))
    account_column = "Page ID" if platform == "Facebook" else "Account ID"
    try:
        _identifier(native["Post ID"], "Post ID")
        if _identifier(native[account_column], account_column) != selected_account:
            return None
    except ValueError:
        return None
    if _publication(native["Publish time"], "")["publication_date_status"] != "observed":
        return None
    if not re.fullmatch(r"\d+(?:\.\d+)?", native["Duration (sec)"]) or native["Date"].casefold() != "lifetime":
        return None
    try:
        url = urlsplit(native["Permalink"])
        valid_url = url.scheme == "https" and not url.username and not url.password and url.port in {None, 443}
    except ValueError:
        return None
    if platform == "Facebook":
        valid_url = valid_url and url.hostname in {"facebook.com", "www.facebook.com", "m.facebook.com"}
        valid_url = valid_url and (any(part in url.path for part in ("/posts/", "/reel/", "/videos/", "/photos/"))
                                   or url.path in {"/photo.php", "/photo", "/permalink.php", "/story.php"})
        valid_type = native["Post type"] in {"Photos", "Videos", "Reels", "Links", "Status", "Text", "Live videos"}
        valid_flags = all(native[key] in {"0", "1", "true", "false", "True", "False"} for key in ("Is crosspost", "Is share"))
        if not valid_flags:
            return None
    else:
        valid_url = valid_url and url.hostname in {"instagram.com", "www.instagram.com"}
        valid_url = valid_url and any(url.path.startswith(part) for part in ("/p/", "/reel/", "/stories/", "/tv/"))
        valid_type = native["Post type"] in {"IG carousel", "IG image", "IG reel", "IG story"}
    return native if valid_url and valid_type else None


def normalize_content_file(path, metadata, *, collection_root=None):
    """Return (snapshots, quarantine, coverage) without writing any files."""
    path = Path(path).resolve()
    root = Path(collection_root).resolve() if collection_root is not None else path.parent
    if not path.is_relative_to(root):
        raise ValueError("Native source must be within its collection root.")
    raw = path.read_bytes()
    sha = _hash(raw)
    if metadata.get("source_sha256") and metadata["source_sha256"] != sha:
        raise ValueError("Native source hash differs from collector metadata.")
    platform = metadata.get("platform_selected", "")
    if platform not in {"Facebook", "Instagram"}:
        raise ValueError("An explicit Facebook or Instagram platform is required.")
    account = _identifier(metadata.get("selected_account_id"), "selected_account_id")
    id_type = metadata.get("account_id_type", "")
    if id_type not in {"native_account", "native_facebook_page", "native_instagram_account"}:
        raise ValueError("Native export selection requires an explicitly native account ID type.")
    requested = [str(metadata.get(key, "")) for key in ("requested_start", "requested_end")]
    for value in requested:
        if value:
            date.fromisoformat(value)
    if all(requested) and requested[0] > requested[1]:
        raise ValueError("Requested start follows end.")
    text = raw.decode("utf-16") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("utf-8-sig")
    records = list(csv.reader(io.StringIO(text, newline="")))
    header_index = next((i for i, row in enumerate(records) if "Post ID" in row), None)
    if header_index is None:
        raise ValueError("No native Post ID header found.")
    header = records[header_index]
    if len(set(header)) != len(header) or any(not field for field in header):
        raise ValueError("Duplicate or empty native CSV header.")
    account_column = "Page ID" if platform == "Facebook" else "Account ID"
    if not {account_column, "Publish time", "Post type"}.issubset(header):
        raise ValueError("Native content header does not match its selected platform.")
    fields = {name.casefold(): name for name in header}
    if len(fields) != len(header):
        raise ValueError("Case-insensitive native headers are ambiguous.")
    capture, acquired = _stamp(metadata.get("captured_at_utc", "")), _stamp(metadata.get("acquired_at_utc", ""))
    relative = path.relative_to(root).as_posix()
    zone = metadata.get("publication_timezone", "")
    # A reporting/account timezone alone is not proof of publication timestamp semantics.
    zone_evidence = metadata.get("timezone_evidence_ref", "")
    verified_zone = zone if zone and zone_evidence else ""
    common = dict(platform_selected=platform, selected_account_id=account, account_id_type=id_type,
                  selected_asset_id=metadata.get("selected_asset_id", ""), account_handle=metadata.get("account_handle", ""),
                  source_file=relative, source_sha256=sha, source_url=metadata.get("source_url", ""), source_kind="native_export",
                  metadata_file=metadata.get("metadata_file", ""), metadata_sha256=metadata.get("metadata_sha256", ""),
                  captured_at_utc=capture, acquired_at_utc=acquired, snapshot_timestamp=capture,
                  capture_timestamp_status="explicit_collector_timestamp" if capture else "exact_capture_unknown",
                  publication_timezone=verified_zone, timezone_evidence_ref=zone_evidence,
                  publication_timezone_status="explicit_source_evidence" if verified_zone else "unverified_metadata_timezone" if zone else "unknown",
                  metric_platform_scope=metadata.get("metric_platform_scope", "unknown"),
                  metric_scope_evidence_ref=metadata.get("metric_scope_evidence_ref", ""),
                  requested_start=requested[0], requested_end=requested[1], publication_filter=metadata.get("publication_filter", ""),
                  publication_status=metadata.get("publication_status", ""), measurement_type="lifetime_content_snapshot")
    snapshots, quarantine, seen = [], [], set()
    duplicate_count = 0
    native_data_rows = 0
    for record_no, values in enumerate(records[header_index + 1:], header_index + 2):
        if not values or not any(values):
            continue
        native_data_rows += 1
        bad = dict(source_file=relative, source_sha256=sha, source_record=record_no,
                   expected_fields=len(header), actual_fields=len(values), raw_record_json=json.dumps(values, ensure_ascii=False), recovery_status="not_recovered")
        identity_only = len(values) != len(header)
        if identity_only:
            bad["reason"] = "native_field_count_mismatch_no_alignment_guess"
            quarantine.append(bad)
            native = _recover_identity_prefix(header, values, platform, account)
            if native is None:
                continue
            bad["recovery_status"] = "identity_only_prefix_verified_metrics_unavailable"
        else:
            native = dict(zip(header, values))
        try:
            post_id = _identifier(native["Post ID"], "Post ID")
            author_id = _identifier(native[account_column], account_column)
        except ValueError:
            quarantine.append({**bad, "reason": "missing_or_nonexact_native_identity"})
            continue
        basis = native.get("Date", "") or metadata.get("reporting_basis", "")
        if basis.casefold() != "lifetime":
            quarantine.append({**bad, "reason": "non_lifetime_or_unknown_measurement_basis"})
            continue
        fingerprint = _hash(json.dumps(values, ensure_ascii=False).encode())
        if fingerprint in seen:
            duplicate_count += 1
            if identity_only:
                bad["recovery_status"] = "exact_duplicate_identity_only_record_omitted"
            else:
                quarantine.append({**bad, "reason": "exact_duplicate_native_record_retained_raw"})
            continue
        seen.add(fingerprint)
        row = {**common, "source_record": record_no, "post_id": post_id, "author_account_id": author_id,
               "author_name": native.get("Page name", native.get("Account name", "")), "author_username": native.get("Account username", ""),
               "author_scope": "band_authored" if author_id == account else "associated_account_authorship_unverified",
               "post_type": native["Post type"], "description": native.get("Description", ""), "title": native.get("Title", ""),
               "permalink": native.get("Permalink", ""), "is_crosspost_raw": native.get("Is crosspost", ""), "is_share_raw": native.get("Is share", ""),
               "reporting_basis_raw": basis, "native_record_json": json.dumps(values if identity_only else native, ensure_ascii=False),
               "native_row_status": "identity_only_prefix_verified" if identity_only else "complete_native_record",
               "native_row_reason": "native_field_count_mismatch_no_alignment_guess" if identity_only else "",
               **_publication(native["Publish time"], verified_zone)}
        if identity_only:
            row.update(source_kind="native_export_identity_only", measurement_type="content_identity_only")
        for metric, label in METRIC_COLUMNS.items():
            source_label = fields.get(label.casefold())
            value = native.get(source_label, "") if source_label else ""
            row[metric], row[metric + "_status"] = ("", "unavailable_malformed_source_row") if identity_only else parse_count(value, present=source_label is not None)
            row[metric + "_raw"], row[metric + "_native_label"] = value, source_label or ""
        row["observation_id"] = _hash(json.dumps([platform, account, post_id, capture, sha, fingerprint], ensure_ascii=False).encode())
        snapshots.append(row)
    dates = sorted(row["publication_date"] for row in snapshots if row["publication_date"])
    coverage = dict(source_file=relative, source_sha256=sha, platform_selected=platform, selected_account_id=account,
                    captured_at_utc=capture, requested_start=requested[0], requested_end=requested[1],
                    actual_publication_start=dates[0] if dates else "", actual_publication_end=dates[-1] if dates else "",
                    native_data_rows=native_data_rows, retained_snapshots=len(snapshots),
                    unique_post_ids=len({row["post_id"] for row in snapshots}), quarantined_rows=len(quarantine),
                    identity_only_rows=sum(row["source_kind"] == "native_export_identity_only" for row in snapshots),
                    metric_eligible_rows=sum(row["source_kind"] == "native_export" for row in snapshots),
                    exact_duplicate_rows=duplicate_count, unknown_publication_dates=sum(not row["publication_date"] for row in snapshots),
                    outside_requested_window=sum(bool(row["publication_date"]) and ((bool(requested[0]) and row["publication_date"] < requested[0]) or (bool(requested[1]) and row["publication_date"] > requested[1])) for row in snapshots),
                    completeness_status="not_established", header=header,
                    scope_note="Requested filters and observed row dates are separate; no complete or all-ever history claim.")
    return snapshots, quarantine, coverage


def normalize_story_observations(path, *, collection_root=None):
    """Retain manually captured native detail panels without inventing metric labels."""
    path = Path(path).resolve()
    root = Path(collection_root).resolve() if collection_root is not None else path.parent
    if not path.is_relative_to(root):
        raise ValueError("Story source must be within its collection root.")
    raw = path.read_bytes()
    sha, relative = _hash(raw), path.relative_to(root).as_posix()
    observations = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(observations, list):
        raise ValueError("Manual Story source must contain an observation list.")
    snapshots, quarantine, seen = [], [], set()
    for number, native in enumerate(observations, 1):
        bad = dict(source_file=relative, source_sha256=sha, source_record=number, recovery_status="not_recovered",
                   expected_fields="keyed_story_detail", actual_fields="keyed_story_detail", raw_record_json=json.dumps(native, ensure_ascii=False))
        try:
            if not isinstance(native, dict) or native.get("platform_selected") != "Instagram":
                raise ValueError("invalid_manual_story_platform")
            post_id = _identifier(native.get("post_id"), "post_id")
            account = _identifier(native.get("selected_account_id"), "selected_account_id")
            if native.get("account_id_type") != "meta_business_suite_asset":
                raise ValueError("unverified_manual_story_account_type")
            url = urlsplit(native.get("source_url", ""))
            query = parse_qs(url.query)
            if (url.scheme != "https" or url.hostname != "business.facebook.com" or url.username or url.password
                    or url.path != "/latest/insights/object_insights/" or query.get("content_id") != [post_id]
                    or query.get("asset_id") != [account]):
                raise ValueError("manual_story_url_identity_mismatch")
            capture = _stamp(native.get("captured_at_utc", ""))
            if not capture:
                raise ValueError("manual_story_capture_missing")
            # Optional collector-transcribed content must be explicit strings.
            # A Story destination/source URL is not a permalink, and an MBS ID
            # cannot manufacture a public Instagram Story URL.
            if any(key in native and not isinstance(native[key], str)
                   for key in ("description", "caption", "permalink")):
                raise ValueError("manual_story_content_fields_not_explicit_strings")
            metrics = native.get("metrics_raw")
            if not isinstance(metrics, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in metrics.items()):
                raise ValueError("manual_story_metrics_not_explicit_label_strings")
            if len({label.casefold() for label in metrics}) != len(metrics):
                raise ValueError("manual_story_metric_labels_ambiguous")
            refs = []
            for key in ("ax_path", "dom_path"):
                ref = native.get(key, "")
                evidence = (root / ref).resolve()
                if not ref or not evidence.is_relative_to(root) or not evidence.is_file():
                    raise ValueError("manual_story_evidence_missing_or_outside_collection")
                refs.append(dict(kind=key, file=evidence.relative_to(root).as_posix(), sha256=_hash(evidence.read_bytes())))
            publication = _publication(native.get("published_local", ""), "")
            for key in ("archive_requested_start", "archive_requested_end"):
                if native.get(key):
                    date.fromisoformat(native[key])
            if native.get("measurement_type") != "lifetime_content_snapshot":
                raise ValueError("manual_story_measurement_basis_unknown")
        except (ValueError, TypeError) as exc:
            quarantine.append({**bad, "reason": str(exc)})
            continue
        fingerprint = _hash(json.dumps(native, ensure_ascii=False, sort_keys=True).encode())
        if fingerprint in seen:
            quarantine.append({**bad, "reason": "exact_duplicate_manual_observation_retained_raw"})
            continue
        seen.add(fingerprint)
        row = dict(platform_selected="Instagram", selected_account_id=account, account_id_type="meta_business_suite_asset",
                   selected_asset_id=account, post_id=post_id, post_type="IG story", author_scope="selected_account_detail_authorship_unverified",
                   account_handle="redactedbandoh" if native.get("account_handle") == "redactedbandoh" else "",
                   description=native.get("description", native.get("caption", "")), permalink=native.get("permalink", ""),
                   source_file=relative, source_sha256=sha, source_record=number, source_url=native["source_url"], source_kind="manual_story_detail",
                   snapshot_timestamp=capture, captured_at_utc=capture, capture_timestamp_status="explicit_collector_timestamp",
                   publication_timezone="", publication_timezone_status="unknown", metric_platform_scope=native.get("metric_platform_scope", "unknown"),
                   measurement_type="lifetime_content_snapshot", reporting_basis_raw="Native Story detail lifetime snapshot",
                   requested_start=native.get("archive_requested_start", ""), requested_end=native.get("archive_requested_end", ""),
                   publication_filter=("Archive requested dates; panel publication date retained separately"
                                       if native.get("archive_requested_start") or native.get("archive_requested_end")
                                       else "Direct native Story detail; no archive date filter applied"),
                   publication_status="Archived Story",
                   native_record_json=json.dumps(native, ensure_ascii=False), native_row_status="manual_native_detail_observation",
                   evidence_refs_json=json.dumps(refs, ensure_ascii=False), **publication)
        labels = {label.casefold(): label for label in metrics}
        for metric, label in METRIC_COLUMNS.items():
            source_label = labels.get(("Instagram follows" if metric == "follows" else label).casefold())
            value = metrics.get(source_label, "") if source_label else ""
            row[metric], row[metric + "_status"] = parse_count(value, present=source_label is not None)
            row[metric + "_raw"], row[metric + "_native_label"] = value, source_label or ""
        row["observation_id"] = _hash(json.dumps(["Instagram", account, post_id, capture, sha, fingerprint]).encode())
        snapshots.append(row)
    dates = sorted(row["publication_date"] for row in snapshots if row["publication_date"])
    captures = sorted(row["snapshot_timestamp"] for row in snapshots)
    requested_starts = sorted({str(item.get("archive_requested_start", "")) for item in observations if isinstance(item, dict)} - {""})
    requested_ends = sorted({str(item.get("archive_requested_end", "")) for item in observations if isinstance(item, dict)} - {""})
    coverage = dict(source_file=relative, source_sha256=sha, platform_selected="Instagram", captured_at_utc=captures[-1] if captures else "",
                    requested_start=requested_starts[0] if requested_starts else "", requested_end=requested_ends[-1] if requested_ends else "",
                    actual_publication_start=dates[0] if dates else "", actual_publication_end=dates[-1] if dates else "",
                    native_data_rows=len(observations), retained_snapshots=len(snapshots), unique_post_ids=len({row["post_id"] for row in snapshots}),
                    quarantined_rows=len(quarantine), identity_only_rows=0, metric_eligible_rows=len(snapshots), completeness_status="not_established",
                    scope_note="Individually observed native Story panels; archive requested dates do not establish complete history.")
    return snapshots, quarantine, coverage


def normalize_content_grid(path, *, collection_root=None):
    """Parse retained page rows by explicit column indices and labels, never by guessed position."""
    path = Path(path).resolve()
    root = Path(collection_root).resolve() if collection_root is not None else path.parent
    if not path.is_relative_to(root):
        raise ValueError("Grid source must be within its collection root.")
    raw = path.read_bytes()
    sha, relative = _hash(raw), path.relative_to(root).as_posix()
    pages = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(pages, list):
        raise ValueError("Content grid source must contain a page list.")
    snapshots, quarantine, seen = [], [], set()
    duplicate_count, source_count = 0, 0
    clean = lambda text: str(text).replace("\u200b", "").strip()
    for page_number, page in enumerate(pages, 1):
        if not isinstance(page, dict) or page.get("platform_selected") != "Instagram" or page.get("placement_filter") != "Instagram Feed":
            raise ValueError("Grid requires explicit Instagram Feed selection evidence.")
        account = _identifier(page.get("selected_account_id"), "selected_account_id")
        if page.get("account_id_type") != "meta_business_suite_asset" or page.get("measurement_type") != "native_content_grid_snapshot":
            raise ValueError("Unknown grid account or measurement type.")
        url = urlsplit(page.get("source_url", ""))
        if (url.scheme != "https" or url.hostname != "business.facebook.com" or url.username or url.password
                or url.path != "/latest/posts/published_posts" or parse_qs(url.query).get("asset_id") != [account]):
            raise ValueError("Grid source URL does not identify the selected asset.")
        capture = _stamp(page.get("captured_at_utc", ""))
        if not capture:
            raise ValueError("Grid capture timestamp required.")
        headers = page.get("headers", [])
        labels = {str(item["index"]): clean(item["text"]) for item in headers}
        if len(labels) != len(headers) or len(set(labels.values())) != len(labels) or not {"Title", "Date published"} <= set(labels.values()):
            raise ValueError("Grid header indices or labels ambiguous.")
        refs = []
        for key in ("ax_path", "dom_path", "screenshot_path"):
            ref = page.get(key, "")
            evidence = (root / ref).resolve()
            if not ref or not evidence.is_relative_to(root) or not evidence.is_file():
                raise ValueError("Grid evidence missing or outside collection.")
            refs.append(dict(kind=key, file=evidence.relative_to(root).as_posix(), sha256=_hash(evidence.read_bytes())))
        for key in ("requested_start", "requested_end"):
            if page.get(key):
                date.fromisoformat(page[key])
        for row_number, native in enumerate(page.get("rows", []), 1):
            source_count += 1
            source_record = f"page:{page_number}/row:{row_number}"
            bad = dict(source_file=relative, source_sha256=sha, source_record=source_record, recovery_status="not_recovered",
                       expected_fields=len(headers), actual_fields=len(native.get("cells", [])), raw_record_json=json.dumps(native, ensure_ascii=False))
            match = re.fullmatch(r"Select item with id ([0-9]+)", native.get("row_label", ""))
            cells = {str(item["index"]): item["text"] for item in native.get("cells", [])}
            if not match or "Instagram" not in native.get("platform_alts", []):
                quarantine.append({**bad, "reason": "grid_identity_or_platform_unverified"})
                continue
            if len(cells) != len(native.get("cells", [])) or set(cells) != set(labels) or any("Loading..." in str(value) for value in cells.values()):
                quarantine.append({**bad, "reason": "grid_incomplete_or_ambiguous_cells"})
                continue
            post_id = match[1]
            native_labels = {labels[index]: value for index, value in cells.items()}
            # Overlapping scroll pages are retained raw but not repeated as new observations.
            fingerprint = _hash(json.dumps([account, post_id, native_labels], sort_keys=True, ensure_ascii=False).encode())
            if fingerprint in seen:
                duplicate_count += 1
                continue
            seen.add(fingerprint)
            title_lines = [clean(line) for line in native_labels["Title"].splitlines() if clean(line)]
            formats = {"Photo": "IG image", "Reel": "IG reel", "Carousel": "IG carousel", "Video": "IG video"}
            format_positions = [i for i, line in enumerate(title_lines) if line in formats]
            format_index = format_positions[-1] if format_positions else None
            post_type, author_username = "Instagram feed (native grid)", ""
            if format_index is not None:
                post_type = formats[title_lines[format_index]]
                tail = title_lines[format_index + 1:]
                if tail and re.fullmatch(r"[A-Za-z0-9_.]+", tail[0]) and tail[0] not in {"Crossposted", "Boost"}:
                    author_username = tail[0]
            author_scope = "associated_account_authorship_unverified" if author_username and author_username != "redactedbandoh" else "selected_account_grid_authorship_unverified"
            row = dict(platform_selected="Instagram", selected_account_id=account, account_id_type="meta_business_suite_asset",
                       selected_asset_id=account, post_id=post_id, post_type=post_type, author_scope=author_scope, author_username=author_username,
                       description=native_labels["Title"], title=native_labels["Title"], source_file=relative, source_sha256=sha,
                       source_record=source_record, source_url=page["source_url"], source_kind="content_grid_observation",
                       snapshot_timestamp=capture, captured_at_utc=capture, capture_timestamp_status="explicit_collector_timestamp",
                       publication_timezone="", publication_timezone_status="unknown", metric_platform_scope=page.get("metric_platform_scope", "unknown"),
                       measurement_type="native_content_grid_snapshot", reporting_basis_raw="Native content grid snapshot",
                       requested_start=page.get("requested_start", ""), requested_end=page.get("requested_end", ""),
                       publication_filter="Instagram Feed; requested dates retained separately", publication_status="Published",
                       native_record_json=json.dumps({"headers": headers, "row": native}, ensure_ascii=False), native_row_status="native_grid_observation",
                       evidence_refs_json=json.dumps(refs, ensure_ascii=False), **_publication(native_labels["Date published"], ""))
            fields = {label.casefold(): label for label in native_labels}
            for metric, label in METRIC_COLUMNS.items():
                source_label = fields.get(label.casefold())
                value = native_labels.get(source_label, "") if source_label else ""
                row[metric], row[metric + "_status"] = parse_count(value, present=source_label is not None)
                row[metric + "_raw"], row[metric + "_native_label"] = value, source_label or ""
            row["observation_id"] = _hash(json.dumps([account, post_id, capture, sha, fingerprint]).encode())
            snapshots.append(row)
    dates = sorted(row["publication_date"] for row in snapshots if row["publication_date"])
    captures = sorted(row["snapshot_timestamp"] for row in snapshots)
    requested_starts = sorted({page.get("requested_start", "") for page in pages} - {""})
    requested_ends = sorted({page.get("requested_end", "") for page in pages} - {""})
    coverage = dict(source_file=relative, source_sha256=sha, platform_selected="Instagram", captured_at_utc=captures[-1] if captures else "",
                    requested_start=requested_starts[0] if requested_starts else "", requested_end=requested_ends[-1] if requested_ends else "",
                    actual_publication_start=dates[0] if dates else "", actual_publication_end=dates[-1] if dates else "",
                    native_data_rows=source_count, retained_snapshots=len(snapshots), unique_post_ids=len({row["post_id"] for row in snapshots}),
                    quarantined_rows=len(quarantine), identity_only_rows=0, metric_eligible_rows=len(snapshots), exact_duplicate_rows=duplicate_count,
                    completeness_status="not_established", scope_note="Native grid rows; repeated identical scroll observations deduplicated, changed captures separate. No complete account-history claim.")
    return snapshots, quarantine, coverage


def _metadata_for(root, path):
    relative = path.relative_to(root).as_posix()
    result = {}
    manifests = [root / "collection_manifest.json", root / "observation_manifest.json"]
    sidecars = [path.with_suffix(".metadata.json"), path.with_suffix(path.suffix + ".metadata.json")]
    refs = []
    for source in manifests + sidecars:
        if not source.is_file():
            continue
        raw = source.read_bytes()
        content = json.loads(raw.decode("utf-8-sig"))
        items = content.get("files", []) if source in manifests else [content]
        for item in items:
            if source in manifests and item.get("source_file", item.get("file")) != relative:
                continue
            result.update(item)
            refs.append({"file": source.relative_to(root).as_posix(), "sha256": _hash(raw)})
    result["metadata_file"] = " | ".join(item["file"] for item in refs)
    result["metadata_sha256"] = " | ".join(item["sha256"] for item in refs)
    return result


def _write_csv(path, rows, fields):
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def normalize_collection(collection_root, output_dir=None):
    """Normalize explicit native source files into a new output directory."""
    root = Path(collection_root).resolve()
    output = Path(output_dir).resolve() if output_dir is not None else root / "normalized"
    if output.exists():
        raise FileExistsError("Preserving existing normalized outputs; choose a new output directory.")
    paths = sorted((root / "raw").rglob("*.csv"))
    manual_paths = sorted((root / "raw").glob("story_detail_observations*.json"))
    grid_paths = sorted((root / "raw").glob("instagram_*grid_pages.json"))
    if not paths and not manual_paths and not grid_paths:
        raise ValueError("No native exports or retained Story panels found under raw/.")
    snapshots, quarantine, coverage = [], [], []
    for path in paths:
        rows, excluded, report = normalize_content_file(path, _metadata_for(root, path), collection_root=root)
        snapshots.extend(rows)
        quarantine.extend(excluded)
        coverage.append(report)
    for path in manual_paths:
        rows, excluded, report = normalize_story_observations(path, collection_root=root)
        snapshots.extend(rows)
        quarantine.extend(excluded)
        coverage.append(report)
    for path in grid_paths:
        rows, excluded, report = normalize_content_grid(path, collection_root=root)
        snapshots.extend(rows)
        quarantine.extend(excluded)
        coverage.append(report)
    statuses = [dict(dataset=f"content_source_{i:03d}", status="partial_history_native_rows" if report["retained_snapshots"] else "no_valid_native_snapshots",
                     detail=f"{report['retained_snapshots']} retained records, including {report['identity_only_rows']} identity-only records with every metric unavailable; {report['quarantined_rows']} original records quarantined (including recovered identity-only records). Requested {report['requested_start'] or 'unknown'} to {report['requested_end'] or 'unknown'}; observed publication dates {report['actual_publication_start'] or 'unknown'} to {report['actual_publication_end'] or 'unknown'}. Complete account history is not established.",
                     evidence_ref=report["source_file"], captured_at_utc=report["captured_at_utc"])
                for i, report in enumerate(coverage, 1)]
    additions_path = root / "collection_status_additions.json"
    if additions_path.is_file():
        additions = json.loads(additions_path.read_text(encoding="utf-8-sig"))
        if not isinstance(additions, list) or any(not isinstance(item, dict) or set(item) != set(STATUS_FIELDS) for item in additions):
            raise ValueError("Explicit collection statuses must use the status CSV schema.")
        statuses.extend(additions)
    output.mkdir(parents=True, exist_ok=False)
    _write_csv(output / "content_snapshots.csv", snapshots, CONTENT_FIELDS)
    _write_csv(output / "quarantined_records.csv", quarantine, QUARANTINE_FIELDS)
    _write_csv(output / "collection_status.csv", statuses, STATUS_FIELDS)
    result = dict(normalizer_version="1.2.0", source_exports=coverage, retained_snapshots=len(snapshots),
                  quarantined_rows=len(quarantine), complete_history_claim=False, inherited_assets_modified=False)
    (output / "normalization_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def build_meta_content(parent, collection_root, output_dir, zip_path, *, version_key=VERSION,
                       label="Meta content history · October 23, 2026 · source-qualified snapshots"):
    return build_evidence_supplement(parent, collection_root, output_dir, zip_path,
                                    version_key=version_key, label=label, spec=SPEC)
