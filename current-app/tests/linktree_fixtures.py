"""Small synthetic Linktree packages; never used as native collection evidence."""
import csv
import hashlib
import io
import json


def write_csv(path, rows):
    header = list(dict.fromkeys(field for row in rows for field in row))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(stream.getvalue().encode("utf-8-sig"))


def reseal(source):
    manifest_path = source / "collection_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = []
    for path in sorted(source.rglob("*")):
        if path.is_file() and path.name not in {"collection_manifest.json", "FILES_SHA256.json"}:
            raw = path.read_bytes()
            entries.append({"path": path.relative_to(source).as_posix(), "bytes": len(raw),
                            "sha256": hashlib.sha256(raw).hexdigest(), "kind": "synthetic_fixture"})
    inventory = {"algorithm": "SHA-256", "excludes": ["FILES_SHA256.json", "collection_manifest.json", "__pycache__/"], "files": entries}
    inventory_raw = json.dumps(inventory).encode("utf-8")
    (source / "FILES_SHA256.json").write_bytes(inventory_raw)
    manifest.update(file_inventory=entries, checksums_file="FILES_SHA256.json",
                    checksums_file_sha256=hashlib.sha256(inventory_raw).hexdigest())
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def synthetic_package(tmp_path):
    source = tmp_path / "synthetic-linktree-source"
    source.mkdir()
    identity = {"collection_id": "linktree-20261025", "platform": "Linktree", "account": "fixture-account",
                "profile_display_name": "Synthetic fixture", "public_url": "https://example.invalid/fixture",
                "reporting_timezone": None, "reporting_timezone_status": "not_stated",
                "collection_ended_at_utc": "2026-10-25T05:30:00Z"}
    (source / "collection_identity.json").write_text(json.dumps(identity), encoding="utf-8")
    (source / "VALIDATION_AND_GAPS.md").write_bytes(b"Synthetic discrepancy: source totals and breakdowns differ.\r\n")
    (source / "captures").mkdir()
    (source / "captures/native.txt").write_bytes(b"Synthetic only\r\nsource counts: 0, 13, 162.5%\r\n")
    base = dict(platform="linktree", account="fixture-account", period_start="2026-10-19", period_end="2026-10-25",
                granularity="period", reporting_timezone="unknown", metric="total_clicks", value="13", unit="count",
                link_id="00001", dimension_value="last_7_days", source_reference="captures/native.txt",
                availability_status="observed", original_value_label="13", date_completeness="current_day_incomplete",
                aggregation_caution="Not confirmed music listening", precision="exact_displayed_integer")
    tables = {
        "period_summaries": [{**base, "metric": "total_views", "value": "8", "original_value_label": "8"},
                             {**base}, {**base, "metric": "reported_click_rate_percent", "value": "162.5", "unit": "percent", "original_value_label": "162.5%"}],
        "activity_daily": [{**base, "granularity": "daily", "period_start": "2026-10-24", "period_end": "2026-10-24", "value": "0", "original_value_label": "0"},
                           {**base, "granularity": "daily", "period_start": "2026-10-25", "period_end": "2026-10-25"}],
        "activity_daily_reported_rates": [{**base, "metric": "reported_click_rate_percent", "unit": "percent", "value": "162.5", "granularity": "daily"}],
        "traffic_sources_daily": [{**base, "metric": "referrer_clicks", "value": "", "availability_status": "unavailable", "availability_reason": "Tooltip not exposed", "dimension_value": "Facebook", "granularity": "daily"}],
        "link_inventory": [{**base, "metric": "link_configuration", "value": "", "title": "=UNTRUSTED()", "destination_url": "https://example.invalid/song", "current_status": "active"}],
        "music_service_metrics": [{**base, "metric": "music_service_outbound_clicks", "value": "", "availability_status": "unavailable", "availability_reason": "Service-level counts not exposed", "title": "Synthetic song", "service_label": "Spotify"}],
    }
    datasets = []
    for name, rows in tables.items():
        path = source / "normalized" / (name + ".csv")
        write_csv(path, rows)
        datasets.append({"file": "normalized\\" + name + ".csv", "row_count": len(rows)})
    manifest = {"schema_version": 1, "collection_id": identity["collection_id"], "identity": identity,
                "coverage": {"earliest_accessible_date": "2026-10-19", "latest_accessible_date": "2026-10-25", "current_day_incomplete": "2026-10-25"},
                "collection_status": "synthetic_fixture", "dataset_tables": datasets, "remaining_blockers": ["Synthetic fixture"]}
    (source / "collection_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    reseal(source)
    return source
