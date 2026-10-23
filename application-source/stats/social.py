"""Explicit parsers for observed native Meta export schemas.

Only registered column sets are accepted. Account IDs come from the export;
capture times and timezones come from supplied acquisition evidence. Neither is
guessed from filenames or filesystem timestamps.
"""
from __future__ import annotations

from datetime import datetime
import csv
import hashlib
import io
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from stats.ingestion import FIELDS, clean, parse_date, parse_number, read_table
from stats.metrics import METRICS


FACEBOOK_AUDIENCE_METRICS = {
    "Unique user engagements": "unique_user_engagements",
    "Overall negative feedback": "negative_feedback_total",
    "Overall negative feedback: Hide all": "negative_feedback_hide_all",
    "Overall negative feedback: Hide": "negative_feedback_hide",
    "Overall negative feedback: Report as spam": "negative_feedback_report_spam",
    "Overall negative feedback: Unlike Page": "negative_feedback_unlike_page",
    "Overall negative feedback: Click X button": "negative_feedback_click_x",
    "Unique negative feedback from users": "unique_negative_feedback_users",
}
INSTAGRAM_CONTENT_METRICS = {
    "Views": "views", "Reach": "reach", "Likes": "likes", "Shares": "shares",
    "Follows": "content_follows", "Comments": "comments", "Saves": "saves",
}
FACEBOOK_POST_METRICS = {
    "3-second video views": "video_views_3s", "1-minute video views": "video_views_1m",
    "3-Second viewers": "video_viewers_3s", "1-minute viewers": "video_viewers_1m",
    "3-second video views from Boosted posts": "video_views_3s_boosted",
    "3-second video views from Organic posts": "video_views_3s_organic",
}
FACEBOOK_RESULT_LABELS = {
    "Views": "views", "Viewers": "viewers", "Content interactions": "content_interactions",
    "Facebook link clicks": "link_clicks", "Facebook visits": "profile_visits", "Facebook follows": "new_followers",
}
INSTAGRAM_RESULT_LABELS = {
    "Views": "views", "Reach": "reach", "Content interactions": "content_interactions",
    "Instagram link clicks": "link_clicks", "Instagram profile visits": "profile_visits", "Instagram follows": "new_followers",
}

PARSERS = {
    "facebook_page_audience_daily_v1": {
        "platform": "facebook", "entity_type": "account", "time_grain": "daily",
        "account_id_column": "Page ID", "account_name_column": "Page name",
        "date_column": "Date", "date_format": "MDY", "metadata_columns": {"Data comment"},
        "metric_columns": FACEBOOK_AUDIENCE_METRICS,
    },
    "instagram_post_lifetime_v1": {
        "platform": "instagram", "entity_type": "post", "time_grain": "lifetime",
        "required_columns": {"Post ID", "Account ID", "Account username", "Account name",
                             "Description", "Duration (sec)", "Publish time", "Permalink", "Post type", "Date"},
        "metadata_columns": {"Data comment"}, "metric_columns": INSTAGRAM_CONTENT_METRICS,
    },
    "facebook_post_daily_v1": {
        "platform": "facebook", "entity_type": "post", "time_grain": "daily", "kind": "post_daily",
        "required_columns": {"Post ID", "Page ID", "Page name", "Title", "Description", "Duration (sec)",
                             "Publish time", "Caption type", "Permalink", "Is crosspost", "Is share", "Post type",
                             "Languages", "Custom labels", "Funded content status", "Date"},
        "metadata_columns": {"Data comment"}, "metric_columns": FACEBOOK_POST_METRICS,
    },
    "facebook_account_results_daily_v1": {
        "platform": "facebook", "entity_type": "account", "time_grain": "daily", "kind": "account_results",
        "labels": FACEBOOK_RESULT_LABELS,
    },
    "instagram_account_results_daily_v1": {
        "platform": "instagram", "entity_type": "account", "time_grain": "daily", "kind": "account_results",
        "labels": INSTAGRAM_RESULT_LABELS,
    },
    "meta_ui_readings_v1": {"platform": None, "time_grain": "mixed", "kind": "ui_readings"},
}


def _metadata(metadata: dict, schema: dict) -> dict:
    result = dict(metadata)
    if result.get("platform") and result["platform"] != schema["platform"]:
        raise ValueError("Manifest platform disagrees with the selected native parser.")
    for key in ("captured_at", "published_at"):
        if result.get(key):
            datetime.fromisoformat(str(result[key]).replace("Z", "+00:00"))
    timezone = clean(result.get("source_timezone"))
    if timezone:
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("source_timezone must be an explicitly evidenced IANA timezone.") from exc
        if not clean(result.get("timezone_evidence")):
            raise ValueError("A known source timezone requires timezone_evidence from the export settings or documentation.")
    result["source_timezone"] = timezone or None
    for key in ("period_start", "period_end", "publication_selection_start", "publication_selection_end"):
        if result.get(key):
            result[key] = parse_date(result[key])
    if schema["time_grain"] == "lifetime" and (result.get("period_start") or result.get("period_end")):
        raise ValueError("Lifetime content exports require publication_selection_start/end, not invented metric period_start/end.")
    return result


def _content_lifetime(frame, filename, schema, metadata):
    observations, issues = [], []
    for position, (_, row) in enumerate(frame.iterrows(), start=2):
        if all(not clean(value) for value in row):
            continue
        try:
            account_id, post_id = clean(row["Account ID"]), clean(row["Post ID"])
            if not account_id or not post_id:
                raise ValueError("Native account and post IDs are required; names cannot replace stable IDs.")
            if clean(row["Date"]).lower() != "lifetime":
                raise ValueError("This parser supports only explicitly labeled Lifetime content metrics.")
            published = datetime.strptime(clean(row["Publish time"]), "%m/%d/%Y %H:%M").isoformat(timespec="minutes")
            duration, duration_status, duration_percent = parse_number(row["Duration (sec)"])
            if duration_percent or (duration is not None and duration < 0):
                raise ValueError("Content duration must be nonnegative seconds or missing.")
            relationship = "target_account" if not metadata.get("account_id") or account_id == str(metadata["account_id"]) else "other_exported_account"
            if relationship == "other_exported_account":
                issues.append({"severity": "warning", "code": "other_exported_account", "source_row": position,
                               "account_id": account_id, "account_username": clean(row["Account username"]),
                               "message": "This exported post belongs to another account (possibly collaborative content). Its native account identity is preserved; it is not relabeled as the target account."})
            elif metadata.get("account_username") and clean(row["Account username"]) != metadata["account_username"]:
                raise ValueError("Target account username differs from the manifest; verify the source identity.")
        except (ValueError, TypeError) as exc:
            issues.append({"severity": "error", "code": "native_metadata_error", "source_row": position,
                           "message": str(exc), "source_record": row.to_dict()})
            continue
        dimensions = {"source_report": "instagram_post_lifetime", "measurement_window": "lifetime",
                      "post_type": clean(row["Post type"]), "duration_seconds": duration,
                      "account_username": clean(row["Account username"]), "source_account_relationship": relationship,
                      **_provenance_dimensions(metadata)}
        for key in ("publication_selection_start", "publication_selection_end"):
            if metadata.get(key):
                dimensions[key] = metadata[key]
        comment = clean(row.get("Data comment"))
        if comment:
            dimensions["data_comment"] = comment
            issues.append({"severity": "warning", "code": "source_data_comment", "source_row": position, "message": comment})
        for source_column, metric in schema["metric_columns"].items():
            try:
                value, status, was_percent = parse_number(row[source_column])
                if was_percent or (value is not None and (value < 0 or not value.is_integer())):
                    raise ValueError("A lifetime content count must be a nonnegative whole number or missing.")
                measurement_type = "distinct_audience_count" if metric == "reach" else "cumulative_total"
                definition = (f"Instagram source-reported lifetime {source_column.lower()} for this post as provided in the export; "
                              "the measurement cutoff is not supplied. " +
                              ("Distinct accounts reached; never sum posts or snapshots." if metric == "reach" else
                               "Do not add snapshots or compare posts as equal exposure ages."))
                observation = {field: None for field in FIELDS}
                observation.update(platform="instagram", account_id=account_id, account_name=clean(row["Account name"]),
                                   entity_type="post", entity_id=post_id, entity_name=clean(row["Description"])[:240],
                                   metric=metric, value=value, unit="count", definition=definition,
                                   dimensions=json.dumps(dimensions, sort_keys=True), time_grain="lifetime",
                                   captured_at=metadata.get("captured_at") or None, source_timezone=metadata["source_timezone"],
                                   measurement_type=measurement_type, status=status, source_row=position,
                                   published_at=published, source_url=clean(row["Permalink"]) or None,
                                   evidence_ref=f"{filename}#row={position}; column={source_column}")
                observations.append(observation)
            except (ValueError, TypeError) as exc:
                issues.append({"severity": "error", "code": "native_value_error", "source_row": position,
                               "metric": metric, "source_column": source_column,
                               "raw_value": clean(row[source_column]), "message": str(exc)})
    return observations, issues


def _provenance_dimensions(metadata):
    return {key: metadata[key] for key in ("selected_meta_asset_id", "account_identity_basis") if metadata.get(key)}


def _facebook_post_daily(frame, filename, schema, metadata):
    observations, issues = [], []
    for position, (_, row) in enumerate(frame.iterrows(), start=2):
        try:
            account_id, post_id = clean(row["Page ID"]), clean(row["Post ID"])
            if not account_id or not post_id:
                raise ValueError("Native Page ID and Post ID are required.")
            if metadata.get("account_id") and account_id != str(metadata["account_id"]):
                raise ValueError("Native Page ID differs from expected manifest account_id. Put the UI asset ID in selected_meta_asset_id instead.")
            published = datetime.strptime(clean(row["Publish time"]), "%m/%d/%Y %H:%M").isoformat(timespec="minutes")
            day = parse_date(row["Date"], "MDY")
            if not day:
                raise ValueError("Source daily date is missing.")
            if (metadata.get("period_start") and day < metadata["period_start"]) or (metadata.get("period_end") and day > metadata["period_end"]):
                raise ValueError("Source daily date is outside the manifest selection.")
            duration, _, percent = parse_number(row["Duration (sec)"])
            if percent or (duration is not None and duration < 0):
                raise ValueError("Duration must be nonnegative seconds.")
        except (ValueError, TypeError) as exc:
            issues.append({"severity": "error", "code": "native_metadata_error", "source_row": position,
                           "message": str(exc), "source_record": row.to_dict()})
            continue
        dimensions = {"source_report": "facebook_post_daily", "post_type": clean(row["Post type"]),
                      "duration_seconds": duration, "is_crosspost": clean(row["Is crosspost"]),
                      "is_share": clean(row["Is share"]), "caption_type": clean(row["Caption type"]),
                      "languages": clean(row["Languages"]), "custom_labels": clean(row["Custom labels"]),
                      "funded_content_status": clean(row["Funded content status"]), **_provenance_dimensions(metadata)}
        for column, metric in schema["metric_columns"].items():
            try:
                value, status, percent = parse_number(row[column])
                if percent or (value is not None and (value < 0 or not value.is_integer())):
                    raise ValueError("A native count must be a nonnegative whole number or missing.")
                if day < published[:10]:
                    if value not in (None, 0):
                        raise ValueError("The export reports positive activity before publication; verify source dates.")
                    status = "unavailable"
                spec = METRICS[metric]
                observation = {field: None for field in FIELDS}
                observation.update(platform="facebook", account_id=account_id, account_name=clean(row["Page name"]),
                                   entity_type="post", entity_id=post_id, entity_name=(clean(row["Title"]) or clean(row["Description"]))[:240],
                                   metric=metric, value=value, unit="count", definition=spec["definition"],
                                   dimensions=json.dumps(dimensions, sort_keys=True), period_start=day, period_end=day,
                                   time_grain="daily", captured_at=metadata.get("captured_at") or None,
                                   source_timezone=metadata["source_timezone"], measurement_type=spec["measurement_type"],
                                   status=status, source_row=position, published_at=published,
                                   source_url=clean(row["Permalink"]) or None,
                                   evidence_ref=f"{filename}#row={position}; column={column}")
                observations.append(observation)
            except (ValueError, TypeError) as exc:
                issues.append({"severity": "error", "code": "native_value_error", "source_row": position,
                               "metric": metric, "message": str(exc), "raw_value": clean(row[column])})
        if day < published[:10]:
            issues.append({"severity": "warning", "code": "prepublication_export_row", "source_row": position,
                           "message": "The native export emits zeros before this post was published. Values are retained as source evidence with unavailable status and excluded from activity calculations."})
    if observations and all(row["value"] in (None, 0) for row in observations):
        issues.append({"severity": "warning", "code": "zero_limited_content_export",
                       "message": "This export contains only zero/missing values for its selected content and video thresholds. It is not evidence of zero activity across the Facebook account."})
    return observations, issues


def _account_result_table(raw, schema):
    if not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ValueError("The observed account-results schema requires its native UTF-16 BOM export.")
    rows = list(csv.reader(io.StringIO(raw.decode("utf-16"))))
    if len(rows) < 4 or rows[0] != ["sep=", ""] or len(rows[1]) != 1 or rows[2] != ["Date", "Primary"]:
        raise ValueError("Unknown account-results header; expected sep=, then one metric label and Date/Primary.")
    label = rows[1][0]
    if label not in schema["labels"]:
        raise ValueError(f"Unregistered account-results metric {label!r}; no generic Primary column guessing is allowed.")
    if any(len(row) != 2 for row in rows[3:] if row):
        raise ValueError("Account-results data row does not match its exact Date/Primary schema.")
    return pd.DataFrame([row for row in rows[3:] if row], columns=rows[2]), label


def _account_metric_dimensions(metric, platform, metadata):
    dimensions = {"source_report": "meta_account_results", **_provenance_dimensions(metadata)}
    if metric == "views" and platform == "instagram":
        if metadata.get("reported_scope") not in {"instagram_and_facebook", "instagram_only", "facebook_only"}:
            raise ValueError("Instagram Results Views requires an explicitly evidenced reported_scope; its export can include Facebook crossposted views.")
        dimensions["reported_scope"] = metadata["reported_scope"]
    elif metadata.get("reported_scope"):
        dimensions["reported_scope"] = metadata["reported_scope"]
    return dimensions


def _account_metric_definition(metric, platform, metadata):
    scope = ""
    if metric == "views" and platform == "instagram":
        scope = {"instagram_and_facebook": " Includes both Instagram and Facebook views as explicitly shown by the source.",
                 "instagram_only": " Instagram component only, explicitly separated by the source.",
                 "facebook_only": " Facebook component only, explicitly separated by the source."}[metadata["reported_scope"]]
    return f"{platform.title()} native account Results export: {metric}; source-defined measurement in the reported window.{scope} {METRICS[metric]['definition']}"


def _account_results(frame, label, filename, schema, metadata):
    if not metadata.get("account_id") or not metadata.get("account_identity_basis"):
        raise ValueError("Account-results files lack account IDs; supply an explicit account_id and account_identity_basis from the source UI.")
    metric = schema["labels"][label]
    spec = METRICS[metric]
    observations, issues = [], []
    dimensions = _account_metric_dimensions(metric, schema["platform"], metadata)
    for position, (_, row) in enumerate(frame.iterrows(), start=4):
        try:
            stamp = datetime.strptime(clean(row["Date"]), "%Y-%m-%dT%H:%M:%S")
            if (stamp.hour, stamp.minute, stamp.second) != (0, 0, 0):
                raise ValueError("Expected a source daily midnight bucket; do not shift a timestamp into a different date.")
            day = stamp.date().isoformat()
            if (metadata.get("period_start") and day < metadata["period_start"]) or (metadata.get("period_end") and day > metadata["period_end"]):
                raise ValueError("Source date is outside the manifest reporting window.")
            value, status, percent = parse_number(row["Primary"])
            if percent or (value is not None and (value < 0 or not value.is_integer())):
                raise ValueError("Account-results count must be a nonnegative whole number or missing.")
            definition = _account_metric_definition(metric, schema["platform"], metadata)
            observation = {field: None for field in FIELDS}
            observation.update(platform=schema["platform"], account_id=str(metadata["account_id"]), account_name=metadata.get("account_name"),
                               entity_type="account", entity_id=str(metadata["account_id"]), entity_name=metadata.get("account_name"),
                               metric=metric, value=value, unit="count", definition=definition,
                               dimensions=json.dumps(dimensions, sort_keys=True), period_start=day, period_end=day, time_grain="daily",
                               captured_at=metadata.get("captured_at") or None, source_timezone=metadata["source_timezone"],
                               measurement_type=spec["measurement_type"], status=status, source_row=position,
                               source_url=metadata.get("source_url"), evidence_ref=f"{filename}#row={position}; metric={label}; column=Primary")
            observations.append(observation)
        except (ValueError, TypeError) as exc:
            issues.append({"severity": "error", "code": "native_value_error", "source_row": position,
                           "metric": metric, "message": str(exc), "source_record": row.to_dict()})
    return observations, issues


def _ui_readings(raw, filename):
    document = json.loads(raw.decode("utf-8-sig"))
    if document.get("schema_version") != 1 or not isinstance(document.get("readings"), list):
        raise ValueError("Expected version1 Meta UI readings with a readings list.")
    observations, issues = [], []
    for index, row in enumerate(document["readings"]):
        source_row = index + 1
        try:
            if row.get("exactness") == "rounded":
                issues.append({"severity": "warning", "code": "rounded_ui_value_not_imported", "source_row": source_row,
                               "metric": row.get("metric"), "display_value": row.get("display_value"),
                               "message": "Rounded UI text is retained in the archived source and is not converted into an exact observation."})
                continue
            if row.get("exactness") != "exact":
                raise ValueError("A UI reading requires explicit exactness='exact' or 'rounded'.")
            platform, metric = row.get("platform"), row.get("metric")
            if platform not in {"facebook", "instagram"} or metric not in METRICS:
                raise ValueError("UI reading platform/metric is not registered.")
            if not row.get("account_id") or not row.get("evidence_ref") or not row.get("captured_at"):
                raise ValueError("Exact UI readings require explicit account identity, evidence reference and capture timestamp.")
            datetime.fromisoformat(row["captured_at"].replace("Z", "+00:00"))
            dimensions = row.get("dimensions")
            if not isinstance(dimensions, dict) or not dimensions.get("account_identity_basis") or not dimensions.get("selected_meta_asset_id"):
                raise ValueError("UI reading dimensions must retain its explicit selected Meta asset identity.")
            source_meta = {**dimensions, "source_timezone": row.get("source_timezone"), "timezone_evidence": row["evidence_ref"]}
            _metadata(source_meta, {"platform": platform, "time_grain": row.get("time_grain")})
            expected = _account_metric_dimensions(metric, platform, source_meta)
            if dimensions.get("source_report") == "meta_account_results" and dimensions != expected:
                raise ValueError("UI Results dimensions differ from the corresponding native daily scope.")
            value, status, percent = parse_number(row.get("value"))
            if value is None or percent or value < 0 or not value.is_integer():
                raise ValueError("An exact source count must be a nonnegative whole number.")
            start, end = parse_date(row.get("period_start")), parse_date(row.get("period_end"))
            if not start or not end or start > end:
                raise ValueError("An exact UI reading needs its actual reporting/as-of dates.")
            spec = METRICS[metric]
            measurement_type = {"additive_count": "period_count"}.get(row.get("measurement_type"), row.get("measurement_type"))
            if measurement_type != spec["measurement_type"] or row.get("unit") != "count":
                raise ValueError("UI measurement type/unit disagrees with the registered native metric.")
            time_grain = {"point_in_time": "point"}.get(row.get("time_grain"), row.get("time_grain"))
            if time_grain not in {"period", "point"}:
                raise ValueError("UI reading time_grain must explicitly identify its period or point-in-time measurement.")
            if measurement_type == "point_in_time_count":
                if time_grain != "point" or start != end:
                    raise ValueError("A follower balance needs a single source as-of date and point time grain.")
            elif time_grain != "period":
                raise ValueError("An activity or distinct-audience reading needs its actual period time grain.")
            definition = _account_metric_definition(metric, platform, source_meta)
            if dimensions.get("source_report") == "meta_account_audience":
                if metric != "followers":
                    raise ValueError("The registered Audience UI schema currently supports follower balances only.")
                definition = f"{platform.title()} native account Audience UI: {METRICS[metric]['definition']}"
            observation = {field: None for field in FIELDS}
            observation.update(platform=platform, account_id=str(row["account_id"]), account_name=row.get("account_name"),
                               entity_type="account", entity_id=str(row["account_id"]), entity_name=row.get("account_name"),
                               metric=metric, value=value, unit="count", definition=definition,
                               dimensions=json.dumps(dimensions, sort_keys=True), period_start=start, period_end=end,
                               time_grain=time_grain, captured_at=row["captured_at"], source_timezone=row.get("source_timezone"),
                               measurement_type=measurement_type, status="available", source_row=source_row,
                               evidence_ref=f"{filename}#readings[{index}]; {row['evidence_ref']}; capture_basis={row.get('captured_at_basis', 'recorded_UI_capture')}",
                               source_url=row.get("source_url"))
            observations.append(observation)
        except (ValueError, TypeError, KeyError) as exc:
            issues.append({"severity": "error", "code": "ui_reading_error", "source_row": source_row,
                           "metric": row.get("metric"), "message": str(exc), "source_record": row})
    return {"parser": "meta_ui_readings_v1", "observations": observations, "issues": issues,
            "source_rows": len(document["readings"]), "file_hash": hashlib.sha256(raw).hexdigest(),
            "accounts": sorted({row["account_id"] for row in observations}),
            "period_start": min((row["period_start"] for row in observations), default=None),
            "period_end": max((row["period_end"] for row in observations), default=None),
            "coverage": [], "reconciliation": {"exact_readings": len(observations),
                                                   "rounded_readings_excluded": sum(issue["code"] == "rounded_ui_value_not_imported" for issue in issues)}}


def parse_social_export(raw: bytes, filename: str, parser: str, metadata: dict | None = None) -> dict:
    """Preview a registered export without writing files or a database."""
    if parser not in PARSERS:
        raise ValueError(f"Unsupported native export parser {parser!r}. Register the observed schema before importing it.")
    schema = PARSERS[parser]
    if schema.get("kind") == "ui_readings":
        return _ui_readings(raw, filename)
    metadata = _metadata(metadata or {}, schema)
    if schema.get("kind") == "account_results":
        frame, label = _account_result_table(raw, schema)
        observations, issues = _account_results(frame, label, filename, schema, metadata)
        schema = {**schema, "required_columns": {"Date"}, "metadata_columns": set(),
                  "metric_columns": {"Primary": schema["labels"][label]}}
    else:
        frame = read_table(raw, filename)
        observations, issues = [], []
    required = (schema["required_columns"] if "required_columns" in schema else
                {schema["account_id_column"], schema["account_name_column"], schema["date_column"]}) | set(schema["metric_columns"])
    allowed = required | schema["metadata_columns"]
    unknown, missing = set(frame.columns) - allowed, required - set(frame.columns)
    if unknown or missing:
        raise ValueError(f"Unrecognized native schema. Unknown columns: {sorted(unknown)}; missing columns: {sorted(missing)}. No columns were guessed or discarded.")
    if schema["time_grain"] == "lifetime":
        observations, issues = _content_lifetime(frame, filename, schema, metadata)
    elif schema.get("kind") == "post_daily":
        observations, issues = _facebook_post_daily(frame, filename, schema, metadata)
    daily_rows = frame.iterrows() if schema["time_grain"] == "daily" and not schema.get("kind") else []
    for position, (_, row) in enumerate(daily_rows, start=2):
        if all(not clean(value) for value in row):
            continue
        try:
            account_id = clean(row[schema["account_id_column"]])
            account_name = clean(row[schema["account_name_column"]])
            if not account_id:
                raise ValueError("Native account ID is missing; account names cannot replace IDs.")
            if metadata.get("account_id") and account_id != str(metadata["account_id"]):
                raise ValueError("Native account ID differs from the manifest account ID.")
            if metadata.get("account_name") and account_name != metadata["account_name"]:
                raise ValueError("Native account name differs from the manifest; verify the source account.")
            day = parse_date(row[schema["date_column"]], schema["date_format"])
            if day is None:
                raise ValueError("Source daily date is missing.")
            if metadata.get("period_start") and day < metadata["period_start"]:
                raise ValueError("A source date falls before the manifest reporting window.")
            if metadata.get("period_end") and day > metadata["period_end"]:
                raise ValueError("A source date falls after the manifest reporting window.")
        except (ValueError, TypeError) as exc:
            issues.append({"severity": "error", "code": "native_metadata_error", "source_row": position,
                           "message": str(exc), "source_record": row.to_dict()})
            continue
        comment = clean(row.get("Data comment"))
        if comment:
            issues.append({"severity": "warning", "code": "source_data_comment", "source_row": position,
                           "message": comment})
        dimensions = {"source_report": parser.removesuffix("_v1"), **_provenance_dimensions(metadata)}
        if comment:
            dimensions["data_comment"] = comment
        for source_column, metric in schema["metric_columns"].items():
            try:
                value, status, was_percent = parse_number(row[source_column], "en_US")
                if was_percent:
                    raise ValueError("This source column records a count, not a percentage.")
                if value is not None and (value < 0 or not value.is_integer()):
                    raise ValueError("A native count must be a nonnegative whole number.")
                spec = METRICS[metric]
                observation = {field: None for field in FIELDS}
                observation.update(platform=schema["platform"], account_id=account_id, account_name=account_name,
                                   entity_type=schema["entity_type"], entity_id=account_id, entity_name=account_name,
                                   metric=metric, value=value, unit=spec["unit"], definition=spec["definition"],
                                   dimensions=json.dumps(dimensions, sort_keys=True), period_start=day, period_end=day,
                                   time_grain=schema["time_grain"], captured_at=metadata.get("captured_at") or None,
                                   source_timezone=metadata["source_timezone"], measurement_type=spec["measurement_type"],
                                   status=status, source_row=position,
                                   evidence_ref=f"{filename}#row={position}; column={source_column}",
                                   source_url=metadata.get("source_url") or None)
                observations.append(observation)
            except (ValueError, TypeError) as exc:
                issues.append({"severity": "error", "code": "native_value_error", "source_row": position,
                               "metric": metric, "source_column": source_column,
                               "raw_value": clean(row[source_column]), "message": str(exc)})
    if not metadata.get("captured_at"):
        issues.append({"severity": "warning", "code": "unknown_capture", "message": "Capture time is unknown; file timestamps are not used as capture evidence."})
    if not metadata["source_timezone"]:
        issues.append({"severity": "warning", "code": "unknown_timezone", "message": "Source timezone is unknown; source date buckets remain unchanged."})
    if metadata.get("capture_time_basis"):
        for observation in observations:
            observation["evidence_ref"] += "; capture_time_basis=" + str(metadata["capture_time_basis"])
    # Daily repeated records are an ambiguity, even if an export happens to
    # duplicate the same count. The file can be corrected/re-exported first.
    seen = set()
    for observation in observations:
        key = (observation["account_id"], observation["entity_id"], observation["period_start"], observation["metric"], observation["dimensions"])
        if key in seen:
            issues.append({"severity": "error", "code": "duplicate_native_row", "source_row": observation["source_row"],
                           "message": "Native export contains repeated account/content observation rows; resolve before committing."})
        seen.add(key)
    coverage = []
    if schema["time_grain"] == "daily" and observations:
        expected_start = metadata.get("period_start") or min(row["period_start"] for row in observations)
        expected_end = metadata.get("period_end") or max(row["period_end"] for row in observations)
        expected_dates = set(pd.date_range(expected_start, expected_end).strftime("%Y-%m-%d"))
        groups = {}
        for observation in observations:
            key = (observation["account_id"], observation["entity_id"], observation["metric"])
            groups.setdefault(key, set()).add(observation["period_start"])
        for (account_id, entity_id, metric), dates in groups.items():
            missing_dates = sorted(expected_dates - dates)
            coverage.append({"account_id": account_id, "entity_id": entity_id, "metric": metric,
                             "expected_start": expected_start, "expected_end": expected_end,
                             "expected_days": len(expected_dates), "observed_days": len(dates),
                             "missing_dates": missing_dates})
            if missing_dates:
                issues.append({"severity": "warning", "code": "incomplete_daily_coverage", "metric": metric,
                               "account_id": account_id, "entity_id": entity_id, "missing_dates": missing_dates,
                               "message": f"The export contains {len(dates)} of {len(expected_dates)} expected date buckets. Absent dates remain missing and are not filled with zero."})
    reconciliation = {}
    for source_column, metric in schema["metric_columns"].items():
        selected = [row for row in observations if row["metric"] == metric]
        values = [row["value"] for row in selected]
        reconciliation[metric] = {
            "source_column": source_column, "observations": len(selected),
            "missing_or_suppressed": sum(value is None for value in values),
            "zero_values": sum(value == 0 for value in values),
            "unavailable_status_values": sum(row["status"] == "unavailable" for row in selected),
            "measurement_type": selected[0]["measurement_type"] if selected else METRICS.get(metric, {}).get("measurement_type"),
            "ordered_values_sha256": hashlib.sha256(json.dumps(values).encode()).hexdigest(),
        }
        if selected and selected[0]["measurement_type"] == "period_count" and all(value is not None for value in values) and all(row["status"] == "available" for row in selected):
            scopes = [group for group in coverage if group["metric"] == metric]
            reconciliation[metric]["observed_additive_value_sum"] = sum(values)
            if len(scopes) == 1 and not scopes[0]["missing_dates"]:
                reconciliation[metric]["additive_period_total"] = sum(values)
    return {"parser": parser, "observations": observations, "issues": issues,
            "source_rows": len(frame), "file_hash": hashlib.sha256(raw).hexdigest(),
            "accounts": sorted({row["account_id"] for row in observations}),
            "period_start": min((row["period_start"] for row in observations if row["period_start"]), default=None),
            "period_end": max((row["period_end"] for row in observations if row["period_end"]), default=None),
            "coverage": coverage, "reconciliation": reconciliation}
