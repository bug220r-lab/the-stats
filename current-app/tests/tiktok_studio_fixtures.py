"""Small synthetic Studio collection; no private account data."""
import hashlib
import json


def seal(package, manifest):
    manifest["assets"] = [{"path": path.relative_to(package).as_posix(), "bytes": path.stat().st_size,
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                          for path in sorted(package.rglob("*")) if path.is_file() and path.name != "manifest.json"]
    (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return package


def studio_package(tmp_path, *, key="tiktok-20261027-studio"):
    package = tmp_path / (key + "-source")
    (package / "raw").mkdir(parents=True)
    (package / "tables").mkdir()
    (package / "raw/native.txt").write_bytes(b"Original bytes: undefined, -3, 0\r\n")
    (package / "tables/account_daily.csv").write_bytes(
        b"date,video_views,comments,viewer_total,source_reference\n2026-10-24,12,-3,,raw/native.txt\n2026-10-25,0,0,undefined,raw/native.txt\n")
    (package / "tables/posts.csv").write_bytes(b"post_id,caption,views_raw\n001,=formula,1.2K\n002,,0\n")
    (package / "tables/empty.csv").write_bytes(b"post_id,value\n")
    manifest = {"schema_version": 1, "collection_key": key, "platform": "tiktok", "account": "@synthetic",
                "label": "TikTok Studio synthetic", "collected_at": "2026-10-27T03:00:00Z",
                "reporting_start": "2026-10-24", "reporting_end": "2026-10-25", "reporting_timezone": "unknown",
                "artists_status": "pending", "datasets": [
                    {"dataset_id": "account_daily", "path": "tables/account_daily.csv", "status": "collected", "row_count": 2,
                     "primary_key": ["date"], "source_paths": ["raw/native.txt"], "definition": "Source-label daily activity."},
                    {"dataset_id": "posts", "path": "tables/posts.csv", "status": "collected", "row_count": 2,
                     "primary_key": ["post_id"], "definition": "Lifetime captured totals, not publication-day activity."},
                    {"dataset_id": "empty", "path": "tables/empty.csv", "status": "verified_empty", "row_count": 0},
                    {"dataset_id": "artists", "status": "pending", "reason": "User deferred artist analytics."}]}
    return seal(package, manifest)
