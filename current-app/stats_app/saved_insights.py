"""Verified, dated analytical readouts, independent of optional report plugins.

The package is a saved analysis, never a live aggregate of whichever source is
selected in the dashboard. Original collection and analysis versions stay intact.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path, PurePosixPath

import pandas as pd

from stats_app.config import PROJECT_ROOT
from stats_app.storage import StorageError

REPORT_KEY = "tiktok-cross-platform-20261027"
REPORT_MANIFEST_SHA256 = "97e61defd3e6d73c88fe1dac3f20d5a8a2b0a1a7f37f46a4905d5defe79416d7"
SCHEMA_VERSION = 1
REQUIRED_ASSETS = {"report.json", "report.md", "report.html", "sources.json",
                   "monthly_trends.png", "song_candidates.png"}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe_path(root, name):
    path = PurePosixPath(name)
    if not isinstance(name, str) or not name or "\\" in name or path.is_absolute() or ":" in name or ".." in path.parts or str(path) != name:
        raise StorageError("Unsafe saved-insights asset path.")
    result = root.joinpath(*path.parts)
    # Reject links at every component, including a redirected package root.
    for part in (result, *result.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise StorageError("Saved-insights packages cannot contain symbolic links or junctions.")
        if part == root:
            break
    if not result.is_file():
        raise StorageError("Saved-insights asset is missing: " + name)
    return result


def _json(raw, label):
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise StorageError("Invalid saved-insights " + label + ".") from exc


class SavedInsights:
    def __init__(self, root: Path, *, manifest_sha256: str = REPORT_MANIFEST_SHA256):
        self.root = Path(root).absolute()
        manifest_raw = _safe_path(self.root, "manifest.json").read_bytes()
        if _sha(manifest_raw) != manifest_sha256:
            raise StorageError("Saved-insights manifest does not match its pinned version.")
        manifest = _json(manifest_raw, "manifest")
        if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("key") != REPORT_KEY:
            raise StorageError("Unsupported saved-insights schema or report identity.")
        assets = manifest.get("assets")
        if not isinstance(assets, dict) or not REQUIRED_ASSETS.issubset(assets):
            raise StorageError("Saved-insights asset catalog is incomplete.")
        self._manifest = manifest
        self._assets = {}
        for name, record in assets.items():
            if not isinstance(record, dict) or not isinstance(record.get("bytes"), int) or record["bytes"] < 0 or not isinstance(record.get("sha256"), str):
                raise StorageError("Invalid saved-insights asset metadata.")
            raw = _safe_path(self.root, name).read_bytes()
            if len(raw) != record["bytes"] or _sha(raw) != record["sha256"]:
                raise StorageError("Saved-insights asset hash mismatch: " + name)
            self._assets[name] = raw
        report = _json(self._assets["report.json"], "report")
        if not isinstance(report, dict) or report.get("schema_version") != SCHEMA_VERSION or report.get("key") != REPORT_KEY:
            raise StorageError("Unsupported saved-insights report schema.")
        if report.get("artists_status") != "pending" or not isinstance(report.get("title"), str):
            raise StorageError("Saved-insights scope is incomplete.")
        queries, sections = report.get("queries"), report.get("sections")
        if not isinstance(queries, dict) or not queries or not isinstance(sections, list) or not sections:
            raise StorageError("Saved-insights report has no reviewed evidence.")
        for key, query in queries.items():
            if not isinstance(query, dict) or not isinstance(query.get("rows"), list) or any(not isinstance(row, dict) for row in query["rows"]) or not isinstance(query.get("source"), dict):
                raise StorageError("Invalid saved-insights query: " + str(key))
        seen = set()
        for section in sections:
            if not isinstance(section, dict) or not isinstance(section.get("id"), str) or section["id"] in seen or not isinstance(section.get("markdown"), str):
                raise StorageError("Invalid or duplicate saved-insights section.")
            seen.add(section["id"])
            if not section.get("queryIds") or any(q not in queries for q in section["queryIds"]):
                raise StorageError("Saved-insights section references unavailable evidence.")
            for chart in section.get("charts", []):
                if chart.get("queryId") not in queries:
                    raise StorageError("Saved-insights chart references unavailable evidence.")
        self._report = report

    @property
    def metadata(self):
        return copy.deepcopy(self._manifest)

    @property
    def report(self):
        return copy.deepcopy(self._report)

    @property
    def key(self):
        return self._manifest["key"]

    @property
    def title(self):
        return self._report["title"]

    @property
    def sections(self):
        return copy.deepcopy(self._report["sections"])

    @property
    def queries(self):
        return copy.deepcopy(self._report["queries"])

    def table(self, query_id):
        if query_id not in self._report["queries"]:
            raise StorageError("No saved-insights query: " + str(query_id))
        return pd.DataFrame(copy.deepcopy(self._report["queries"][query_id]["rows"]))

    def asset_bytes(self, name):
        if name not in self._assets:
            raise StorageError("No saved-insights asset: " + str(name))
        return self._assets[name]

    def markdown(self):
        return self.asset_bytes("report.md").decode("utf-8")

    def html(self):
        return self.asset_bytes("report.html").decode("utf-8")


def load_saved_insights(root: Path | None = None):
    """Return the fixed report or an honest empty state; never trust altered bytes."""
    folder = Path(root) if root is not None else PROJECT_ROOT / "data" / "reports" / REPORT_KEY
    if not folder.exists():
        return None
    return SavedInsights(folder)
