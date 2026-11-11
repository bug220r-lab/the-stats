"""The native report is immutable, portable and honest about analytical scope."""
import hashlib
import json
from pathlib import Path
import shutil
import importlib.util
from html.parser import HTMLParser

import pytest

from stats_app.config import PROJECT_ROOT
from stats_app.saved_insights import (
    REPORT_KEY, REPORT_MANIFEST_SHA256, SavedInsights, load_saved_insights,
)
from stats_app.storage import StorageError


PACKAGE = PROJECT_ROOT / "data" / "reports" / REPORT_KEY


def copied(tmp_path):
    target = tmp_path / "package"
    shutil.copytree(PACKAGE, target)
    return target


def reseal(root, *, report_change=None, manifest_change=None):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if report_change:
        path = root / "report.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        report_change(report)
        raw = json.dumps(report).encode()
        path.write_bytes(raw)
        manifest["assets"]["report.json"] = {"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
    if manifest_change:
        manifest_change(manifest)
    raw = json.dumps(manifest).encode()
    (root / "manifest.json").write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_saved_values_identity_scope_and_copy_isolation():
    report = load_saved_insights()
    assert report.key == REPORT_KEY
    assert report.metadata["fixed_report"] is True
    assert report.metadata["artists_status"] == "pending"
    assert report.metadata["analysis_key"] == "meta-story-backfill-20261024"
    assert len(report.sections) == 8 and len(report.queries) == 16
    assert report.table("matched_periods").set_index("period").loc["latest28", "spotify_daily_streams"] == 4246
    assert report.table("songs").iloc[0]["streams"] == 1488
    assert report.table("songs").iloc[0]["listeners"] == 624
    assert report.table("songs").iloc[0]["saves"] == 70
    assert report.table("post_examples").iloc[0]["post_id"] == "7572408030201941279"
    assert all(isinstance(row['post_id'],str) for row in report.queries['post_examples']['rows'])
    assert report.table("post_examples").snapshot_followers_exact.isna().any()
    query = report.queries
    query["songs"]["rows"][0]["streams"] = 0
    assert report.table("songs").iloc[0]["streams"] == 1488
    metadata = report.metadata
    metadata["artists_status"] = "connected"
    assert report.metadata["artists_status"] == "pending"


def test_package_is_pinned_and_absent_package_is_explicit(tmp_path):
    assert load_saved_insights(tmp_path / "missing") is None
    target = copied(tmp_path)
    manifest = target / "manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b" ")
    with pytest.raises(StorageError, match="pinned"):
        load_saved_insights(target)


@pytest.mark.parametrize("name", ["report.json", "report.md", "report.html", "sources.json", "monthly_trends.png", "song_candidates.png"])
def test_any_changed_asset_fails_before_display(tmp_path, name):
    target = copied(tmp_path)
    asset = target / name
    asset.write_bytes(asset.read_bytes() + b" changed")
    with pytest.raises(StorageError, match="hash mismatch"):
        load_saved_insights(target)


def test_missing_asset_and_unknown_query_are_not_zero(tmp_path):
    target = copied(tmp_path)
    (target / "report.html").unlink()
    with pytest.raises(StorageError, match="missing"):
        load_saved_insights(target)
    report = load_saved_insights()
    with pytest.raises(StorageError, match="No saved-insights query"):
        report.table("artists")
    with pytest.raises(StorageError, match="No saved-insights asset"):
        report.asset_bytes("../../secrets.txt")


@pytest.mark.parametrize("mutation,match", [
    (lambda x:x.update(schema_version=999), "schema"),
    (lambda x:x.update(artists_status="connected"), "scope"),
    (lambda x:x["sections"][0].update(queryIds=["missing"]), "unavailable evidence"),
    (lambda x:x["queries"]["songs"].update(rows=[None]), "Invalid saved-insights query"),
])
def test_structural_validation_after_explicit_integrity_check(tmp_path, mutation, match):
    target = copied(tmp_path)
    pin = reseal(target, report_change=mutation)
    with pytest.raises(StorageError, match=match):
        SavedInsights(target, manifest_sha256=pin)


def test_unsafe_asset_path_fails_even_with_matching_manifest(tmp_path):
    target = copied(tmp_path)
    pin = reseal(target,manifest_change=lambda x:x["assets"].update({"../escape": {"bytes":0,"sha256":hashlib.sha256(b"").hexdigest()}}))
    with pytest.raises(StorageError, match="Unsafe"):
        SavedInsights(target,manifest_sha256=pin)


class InspectHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables=0; self.images=[]; self.scripts=0; self.links=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=="table": self.tables+=1
        if tag=="script": self.scripts+=1
        if tag=="img": self.images.append(attrs['src'])
        if tag=="a": self.links.append(attrs['href'])


def test_portable_html_and_markdown_retain_findings_and_source_windows():
    report = load_saved_insights()
    content = report.html()
    parser = InspectHTML(); parser.feed(content)
    assert parser.tables >= 4
    assert parser.scripts == 0
    assert len(parser.images) == 2 and all(v.startswith("data:image/png;base64,") for v in parser.images)
    assert all(v.startswith(("https://", "http://", "#")) for v in parser.links)
    assert "C:\\Users" not in content and "C:/Users" not in content
    assert "runtime became unavailable" not in content and "buildStatus" not in content
    assert "September 23–October 20" in content
    assert "including partial" in content and "TikTok for Artists remains pending" in content
    assert "1,181" in content and "1,379" in content and "3.8K recent views" in content
    assert "No click-to-stream conversion rate is available" in report.markdown()
    sources=json.loads(report.asset_bytes('sources.json'))
    assert len(sources['other_platform_tables']) == 15
    assert sources['analysis_database_sha256'] == 'f013434eb7f24abc6ff138d9c9e0d02c6f42cec8df52530e8e325513a10f9b2b'
    assert sources['analysis_database_sha256'] in content
    assert 'Complete source receipts and fingerprints' in content
    assert 'outputs/tiktok_cross_platform_analysis_20261027/analysis.ipynb' in content
    assert 'scripts in this folder' not in content
    assert 'Apple reinforces that choice: 176' in content


def test_builder_replay_preserves_every_existing_byte(tmp_path):
    spec=importlib.util.spec_from_file_location('report_builder',PROJECT_ROOT/'scripts/build_tiktok_insights_report.py')
    builder=importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    target=copied(tmp_path)
    before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in target.iterdir() if p.is_file()}
    result=builder.build(PROJECT_ROOT/'outputs/tiktok_cross_platform_analysis_20261027',target)
    assert result['idempotent'] is True and result['manifest_sha256'] == REPORT_MANIFEST_SHA256
    after={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in target.iterdir() if p.is_file()}
    assert after==before
