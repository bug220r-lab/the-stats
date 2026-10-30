"""Read-only content inventory across immutable capture vintages.

Publication identities and lifetime observations are different grains. Unknown
dates remain unknown, and later captures never add to earlier lifetime values.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re

import pandas as pd

PREFIX = "social/meta_content_20261023/"
CONTENT_PATH = PREFIX + "content_snapshots.csv"
BRIDGE_PATH = PREFIX + "identity_bridges.csv"
INHERITED_PATH = "social/posts_latest.csv"
MANUAL_PATH = "social/meta_collection/instagram_stories_manual.csv"
# Supplements are explicitly registered here; a similarly named arbitrary CSV
# in an analysis package does not establish a supported content source.
SUPPLEMENT_PREFIXES = ("social/meta_refresh_20261024/", "social/meta_story_backfill_20261024/")
IDENTITY = ["platform_selected", "identity_account_id_type", "identity_account_id", "post_id"]
NUMERIC_STATUSES = {"observed", "observed_zero", "zero", "reported", "supplied_numeric"}
METRICS = ["views", "reach", "impressions", "likes", "comments", "shares", "saves", "reactions", "follows", "interactions",
           "engagement_actions", "replies", "navigation", "sticker_taps", "link_clicks", "profile_visits",
           "total_clicks", "organic_views", "boosted_views"]


def _text(value):
    return "" if value is None or pd.isna(value) else str(value)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def account_type(value):
    normalized = re.sub(r"\s+", "_", _text(value).strip().casefold())
    if normalized in {"native_account", "native_platform_account", "native_instagram_account", "instagram_account",
                      "native_facebook_page", "facebook_page", "native_facebook_account"}:
        return "native_account"
    if normalized in {"meta_business_suite_asset", "mbs_asset"}:
        return "meta_business_suite_asset"
    return normalized or "unknown"


def _publication(value, published):
    raw = _text(value).strip()
    if not raw and re.match(r"^\d{4}-\d{2}-\d{2}(?:T|\s|$)", _text(published)):
        raw = _text(published)[:10]
    try:
        return date.fromisoformat(raw).isoformat() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) else ""
    except ValueError:
        return ""


def _capture(value):
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
        return pd.Timestamp(parsed).tz_convert("UTC") if parsed.utcoffset() is not None else pd.NaT
    except (ValueError, TypeError, OverflowError):
        return pd.NaT


def _content_count(value, status):
    """Validate normalized counts before exposing analytical quantities."""
    if not value.strip():
        return float("nan"), "invalid_count_status" if status in NUMERIC_STATUSES else status or "not_supplied"
    try:
        exact = Decimal(value.strip())
    except InvalidOperation:
        return float("nan"), "invalid_count_source_value" if status in NUMERIC_STATUSES else status or "unparsed_source_value"
    if not exact.is_finite() or exact < 0 or exact != exact.to_integral_value():
        return float("nan"), "invalid_count_source_value"
    number = float(exact)
    if not math.isfinite(number) or int(number) != exact:
        return float("nan"), "invalid_count_source_value"
    status = status or "supplied_numeric"
    if status not in NUMERIC_STATUSES or (status in {"observed_zero", "zero"} and exact != 0):
        return float("nan"), "invalid_count_status"
    return number, status


def normalize_content(frame, source_table, *, source_table_sha256=""):
    """Project source fields for browsing, retaining originals and raw values."""
    records = []
    for ordinal, raw_row in enumerate(frame.to_dict("records"), 2):
        raw = {key: _text(value) for key, value in raw_row.items()}
        row = dict(raw)
        inherited = source_table == INHERITED_PATH
        row["platform_selected"] = raw.get("platform_selected", "")
        row["selected_account_id"] = raw.get("selected_account_id", "")
        row["post_id"] = raw.get("post_id", "")
        raw_type = raw.get("account_id_type") or raw.get("selected_account_id_type") or ("native_account" if inherited else "")
        row["account_id_type_raw"] = raw_type
        row["account_id_type"] = account_type(raw_type)
        row["identity_account_id_type"] = row["account_id_type"]
        row["identity_account_id"] = row["selected_account_id"]
        row["identity_basis"] = "source_account_identity"
        row["source_table"] = source_table
        row["source_table_sha256"] = source_table_sha256
        row["table_record"] = ordinal
        row["source_record"] = raw.get("source_record", str(ordinal))
        row["source_kind"] = raw.get("source_kind") or ("inherited_export" if inherited else "manual_story_detail" if source_table == MANUAL_PATH else "native_export")
        row["publication_date_raw"] = raw.get("publication_date", "")
        row["published_local"] = raw.get("published_local", "")
        row["publication_date"] = _publication(raw.get("publication_date"), raw.get("published_local"))
        row["publication_timezone"] = raw.get("publication_timezone") or raw.get("reporting_timezone", "")
        row["snapshot_timestamp"] = raw.get("snapshot_timestamp") or raw.get("captured_at_utc", "")
        row["capture_time_utc"] = _capture(row["snapshot_timestamp"])
        row["capture_time_status"] = "known" if not pd.isna(row["capture_time_utc"]) else "unknown_or_invalid"
        row["measurement_type"] = raw.get("measurement_type") or "lifetime_content_snapshot"
        row["metric_platform_scope"] = raw.get("metric_platform_scope") or "unknown"
        row["author_scope"] = raw.get("author_scope") or "unknown"
        row["post_type"] = raw.get("post_type") or "unknown"
        row["description"] = raw.get("description") or raw.get("caption") or raw.get("title", "")
        row["permalink"] = raw.get("permalink", "")
        row["source_url"] = raw.get("source_url", "")
        row["source_file"] = raw.get("source_file", "")
        row["source_sha256"] = raw.get("source_sha256", "")
        for metric in METRICS:
            value = raw.get(metric, "")
            row[metric + "_raw"] = raw.get(metric + "_raw", value)
            status = raw.get(metric + "_status", "")
            row[metric + "_normalized_raw"] = value
            row[metric + "_status_raw"] = raw.get(metric + "_status_raw", status)
            row[metric], row[metric + "_status"] = _content_count(value, status)
        age = pd.to_numeric(raw.get("post_age_days", ""), errors="coerce")
        row["post_age_days"] = float(age) if not pd.isna(age) and math.isfinite(float(age)) and age >= 0 else float("nan")
        row["post_age_basis"] = "source_supplied" if not pd.isna(row["post_age_days"]) else "unknown"
        if pd.isna(row["post_age_days"]) and row["publication_date"] and not pd.isna(row["capture_time_utc"]):
            zone = {"Pacific Time": "America/Los_Angeles", "UTC": "UTC"}.get(row["publication_timezone"], row["publication_timezone"])
            if zone:
                try:
                    days = (row["capture_time_utc"].tz_convert(zone).date() - date.fromisoformat(row["publication_date"])).days
                    if days >= 0:
                        row["post_age_days"], row["post_age_basis"] = float(days), "calendar_day_difference_in_publication_timezone"
                except (ValueError, KeyError):
                    pass
        # A snapshot fingerprint ignores delivery-table location; identical
        # retained evidence is not made into another observation by copying it.
        row["observation_id"] = _digest(raw)
        row["identity_complete"] = bool(row["platform_selected"] and row["selected_account_id"] and row["post_id"] and row["account_id_type"] != "unknown")
        records.append(row)
    return pd.DataFrame(records)


def apply_identity_bridges(data, bridges):
    """Apply only explicit verified account bridges; never equate bare IDs."""
    data = data.copy()
    if bridges.empty:
        return data
    fields = {"platform_selected", "from_account_id_type", "from_account_id", "to_account_id_type", "to_account_id", "evidence_ref"}
    if not fields.issubset(bridges):
        raise ValueError("Content identity bridges require explicit platform, account types/IDs and evidence_ref.")
    mapping = {}
    for raw in bridges.to_dict("records"):
        row = {key: _text(value) for key, value in raw.items()}
        verified = row.get("verification_status", "").casefold() == "verified" or row.get("verified", "").casefold() == "true"
        if not verified or not row["evidence_ref"].strip():
            continue
        key = (row["platform_selected"], account_type(row["from_account_id_type"]), row["from_account_id"])
        target = (account_type(row["to_account_id_type"]), row["to_account_id"], row["evidence_ref"])
        if "unknown" in (key[1], target[0]) or not key[2] or not target[1]:
            raise ValueError("Verified content identity bridges require known account identities.")
        if key in mapping and mapping[key][:2] != target[:2]:
            raise ValueError("Conflicting verified content account identity bridges.")
        mapping[key] = target
    for index, row in data.iterrows():
        target = mapping.get((row.platform_selected, row.account_id_type, row.selected_account_id))
        if target:
            data.loc[index, "identity_account_id_type"] = target[0]
            data.loc[index, "identity_account_id"] = target[1]
            data.loc[index, "identity_basis"] = "verified_account_bridge: " + target[2]
            data.loc[index, "identity_complete"] = bool(row.platform_selected and row.post_id)
    return data


def content_table_paths(repo):
    """Return supported retained content tables in stable source order."""
    tables = set(repo.tables)
    candidates = (INHERITED_PATH, CONTENT_PATH, MANUAL_PATH,
                  *(prefix + "content_snapshots.csv" for prefix in SUPPLEMENT_PREFIXES))
    return [path for path in candidates if path in tables]


def identity_bridge_paths(repo):
    """Return explicit account-bridge tables for the supported captures."""
    tables = set(repo.tables)
    candidates = (BRIDGE_PATH, *(prefix + "identity_bridges.csv" for prefix in SUPPLEMENT_PREFIXES))
    return [path for path in candidates if path in tables]


def load_content_observations(repo):
    frames = []
    for path in content_table_paths(repo):
        frame = repo.table(path, raw=True)
        if frame.empty:
            continue
        frames.append(normalize_content(frame, path, source_table_sha256=frame.attrs.get("source_sha256", "")))
    if not frames:
        return pd.DataFrame()
    data = pd.concat(frames, ignore_index=True).drop_duplicates("observation_id").reset_index(drop=True)
    bridges = [repo.table(path, raw=True) for path in identity_bridge_paths(repo)]
    if bridges:
        # Validate the complete bridge set together: applying tables in order
        # could otherwise silently overwrite conflicting account evidence.
        data = apply_identity_bridges(data, pd.concat(bridges, ignore_index=True))
    data["identity_key"] = data.apply(lambda r: _digest([r[field] for field in IDENTITY]) if r.identity_complete
                                      else "unresolved:" + r.observation_id, axis=1)
    return data


def _comparison_signature(row):
    # Publication/caption differences and missing-vs-zero statuses are retained
    # as conflicts at the same capture time, never resolved by source order.
    fields = ["publication_date", "published_local", "post_type", "description", "permalink", "author_scope"]
    values = {field: _text(row.get(field)) for field in fields}
    for metric in METRICS:
        values[metric] = _text(row.get(metric))
        values[metric + "_status"] = _text(row.get(metric + "_status"))
    return _digest(values)


def select_content_observations(data, mode="latest"):
    """Return captures without summing; unresolved chronology stays visible."""
    if data.empty:
        return data.copy()
    if mode not in {"latest", "all", "unknown_capture"}:
        raise ValueError("Unknown content observation view.")
    result = data.copy()
    result["selection_status"] = "retained_capture"
    result["supporting_observation_count"] = 1
    if mode == "all":
        return result
    if mode == "unknown_capture":
        result = result.loc[result.capture_time_utc.isna()].copy()
        result["selection_status"] = "capture_time_unknown"
        return result
    # Select positions in bulk: copying a wide source frame once per identity
    # made an ordinary library rerun take many seconds. Only tied latest
    # captures need value comparisons; singleton groups cannot conflict.
    result = result.reset_index(drop=True)
    grouped = result.groupby(["identity_key", "metric_platform_scope", "measurement_type"], dropna=False, sort=False)
    groups = grouped.ngroup()
    known = result.capture_time_utc.notna()
    latest = known & result.capture_time_utc.eq(grouped.capture_time_utc.transform("max"))
    candidate_groups = groups.loc[latest]
    counts = candidate_groups.value_counts(sort=False)
    tied = candidate_groups.index[candidate_groups.map(counts).gt(1)]
    conflicting_groups = []
    if len(tied):
        signatures = result.loc[tied].apply(_comparison_signature, axis=1)
        distinct = signatures.groupby(groups.loc[tied], sort=False).nunique()
        conflicting_groups = distinct.index[distinct.gt(1)]
    conflicts = latest & groups.isin(conflicting_groups)
    compatible = result.loc[latest & ~conflicts, "observation_id"].sort_values(kind="stable").index
    # Equivalent evidence still chooses the smallest observation fingerprint,
    # retaining its full supporting count exactly as the per-group algorithm.
    compatible = groups.loc[compatible].drop_duplicates().index
    keep = ~known | conflicts
    keep.loc[compatible] = True
    result.loc[~known, "selection_status"] = "capture_time_unknown"
    result.loc[conflicts, "selection_status"] = "same_time_conflict"
    result.loc[compatible, "selection_status"] = "latest_compatible_capture"
    result.loc[compatible, "supporting_observation_count"] = groups.loc[compatible].map(counts)
    # Preserve first-seen group order, unknown captures before known captures,
    # and source order within each unresolved/conflicting group.
    order = pd.DataFrame({"group": groups, "known": known}).loc[keep].sort_values(["group", "known"], kind="stable").index
    return result.loc[order].reset_index(drop=True)


def search_content(data, query):
    query = query.strip()
    if not query or data.empty:
        return data.copy()
    found = pd.Series(False, index=data.index)
    for column in ("description", "post_id", "permalink", "source_url", "published_local", "selected_account_id"):
        found |= data[column].fillna("").astype(str).str.contains(query, case=False, regex=False)
    return data.loc[found].copy()


def publication_inventory(data):
    """One known publication date per identity; conflicting dates are excluded."""
    if data.empty:
        return pd.DataFrame(columns=["publication_date", "post_type", "retained_publications"])
    known = data.loc[data.publication_date.ne("") & data.identity_complete].copy()
    unambiguous = known.groupby("identity_key").publication_date.transform("nunique").eq(1)
    known = known.loc[unambiguous].drop_duplicates("identity_key")
    return known.groupby(["publication_date", "post_type"]).size().rename("retained_publications").reset_index()


def conflicting_publication_identities(data):
    """Identify inconsistent known dates across the full supplied evidence."""
    if data.empty:
        return set()
    known = data.loc[data.publication_date.ne("") & data.identity_complete]
    counts = known.groupby("identity_key").publication_date.nunique()
    return set(counts.loc[counts.gt(1)].index)


def content_identity_inventory(data, evidence=None):
    """One row per filtered identity, with no selected or combined metrics.

    Date evidence may include older captures hidden by a latest-capture view.
    The capture count describes only the observations supplied in ``data``.
    """
    columns = ["identity_key", "platform_selected", "identity_account_id_type", "identity_account_id",
               "post_id", "post_type", "description", "publication_dates", "publication_date_status",
               "publication_text", "capture_count", "permalink"]
    if data.empty:
        return pd.DataFrame(columns=columns)
    evidence = data if evidence is None else evidence
    histories = {}
    for identity, publication, published in evidence[["identity_key", "publication_date", "published_local"]].itertuples(index=False, name=None):
        dates, text = histories.setdefault(identity, (set(), set()))
        if publication != "":
            dates.add(publication)
        if published != "":
            text.add(published)
    missing = ~data.identity_key.isin(histories)
    for identity, publication, published in data.loc[missing, ["identity_key", "publication_date", "published_local"]].itertuples(index=False, name=None):
        dates, text = histories.setdefault(identity, (set(), set()))
        if publication != "":
            dates.add(publication)
        if published != "":
            text.add(published)
    # Sort only the inventory fields once, not the entire source table once
    # per identity. First-seen identity order keeps stable output ties intact.
    fields = ["identity_key", "platform_selected", "identity_account_id_type", "identity_account_id", "post_id",
              "post_type", "description", "permalink", "observation_id", "capture_time_utc"]
    ordered = data[fields].sort_values(["capture_time_utc", "observation_id"], ascending=[False, True], na_position="last")
    groups = dict.fromkeys(data.identity_key.unique())
    for record in ordered.itertuples(index=False):
        group = groups[record.identity_key]
        if group is None:
            group = groups[record.identity_key] = {"representative": record, "types": set(), "observations": set(), "description": "", "permalink": ""}
        group["types"].add(record.post_type)
        group["observations"].add(record.observation_id)
        if not group["description"] and record.description:
            group["description"] = record.description
        if not group["permalink"] and record.permalink:
            group["permalink"] = record.permalink
    rows = []
    for identity, group in groups.items():
        dates, published = histories[identity]
        dates = sorted(dates)
        representative = group["representative"]
        row = {field: getattr(representative, field) for field in ("platform_selected", "identity_account_id_type", "identity_account_id", "post_id")}
        row.update(identity_key=identity, post_type="; ".join(sorted(group["types"])),
                   description=group["description"],
                   publication_dates="; ".join(dates),
                   publication_date_status="Conflicting known dates" if len(dates) > 1 else "Known date" if dates else "Unknown date",
                   publication_text="; ".join(sorted(published)),
                   capture_count=len(group["observations"]),
                   permalink=group["permalink"])
        rows.append(row)
    return pd.DataFrame(rows, columns=columns).sort_values(["publication_dates", "platform_selected", "post_id"],
                                                        ascending=[False, True, True], kind="stable").reset_index(drop=True)
