"""Synthetic end-to-end TikTok preparation checks; no native schema assumed."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.prepare_tiktok import main
from stats_app.validation import validate_records


@pytest.fixture
def tiktok_files(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path / "synthetic-local-appdata"))
    monkeypatch.setenv("APPDATA",str(tmp_path / "synthetic-roaming-appdata"))
    monkeypatch.setenv("STATS_DATA_DIR",str(tmp_path / "synthetic-live-library"))
    source = tmp_path / "synthetic-tiktok.csv"
    raw = b"ExportDay,DailyViews,NetChange,DailyViewers\n2026-10-01,0,-2,5\n2026-10-02,,0,*\n"
    source.write_bytes(raw)
    mapping = dict(schema_version=1, encoding="utf-8-sig", delimiter=",", header_row=1,
        date_format="%Y-%m-%d", time_grain="daily", number_format="plain", columns={"date":"ExportDay"},
        dimensions={}, metrics=[
            dict(metric="video_views",column="DailyViews",unit="count",measurement_basis="period_count",
                 definition="Synthetic TikTok account view activity.",value_tokens={"":"missing"}),
            dict(metric="net_followers",column="NetChange",unit="count",measurement_basis="period_count",
                 definition="Synthetic TikTok signed net follower change.",value_tokens={"":"missing"}),
            dict(metric="unique_viewers",column="DailyViewers",unit="count",measurement_basis="distinct_count",
                 definition="Synthetic TikTok unique viewers per source day.",value_tokens={"":"missing","*":"suppressed"})])
    metadata = dict(source_family="studio_csv",account="synthetic-tiktok-account",entity_type="account",
        entity_id="synthetic-tiktok-account",entity_name="Synthetic fixture only",content_scope="band_owned",
        source_timezone="UTC",captured_at="2026-10-25T12:00:00Z",report_scope="Synthetic account daily test",filters={})
    mapping_file, metadata_file = tmp_path / "mapping.json", tmp_path / "metadata.json"
    mapping_file.write_text(json.dumps(mapping),encoding="utf-8")
    metadata_file.write_text(json.dumps(metadata),encoding="utf-8")
    return source,mapping_file,metadata_file,raw


def args(mode,files,output):
    return [mode,"--input",str(files[0]),"--mapping",str(files[1]),"--metadata",str(files[2]),"--output",str(output)]


def test_inspect_and_stage_keep_exact_bytes_and_signed_missing_values(tmp_path,tiktok_files):
    source,_,_,raw=tiktok_files
    inspection=tmp_path / "schema.json"
    assert main(["inspect","--input",str(source),"--output",str(inspection)]) == 0
    assert "DailyViews" in inspection.read_text(encoding="utf-8")
    output=tmp_path / "stage"
    assert main(args("stage",tiktok_files,output)) == 0
    receipt=json.loads((output / "stage_receipt.json").read_text(encoding="utf-8"))
    assert receipt["accepted"] is True and receipt["library_modified"] is False
    assert receipt["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert (output / "raw" / source.name).read_bytes() == source.read_bytes() == raw
    result=json.loads((output / "preview.json").read_text(encoding="utf-8"))
    assert len(result["records"]) == 6 and validate_records(result["records"]) == []
    assert {row["status"] for row in result["records"]} == {"observed","missing","suppressed"}
    assert any(row["metric"] == "net_followers" and row["value"] == -2 for row in result["records"])
    assert result["summary"]["observed_zero_count"] == 2


def test_rejected_mapping_and_existing_outputs_preserve_evidence(tmp_path,tiktok_files,capsys):
    mapping=json.loads(tiktok_files[1].read_text(encoding="utf-8"))
    mapping["metrics"][0]["column"]="Not an actual source column"
    tiktok_files[1].write_text(json.dumps(mapping),encoding="utf-8")
    stage=tmp_path / "rejected"
    assert main(args("stage",tiktok_files,stage)) == 2
    receipt=json.loads((stage / "stage_receipt.json").read_text(encoding="utf-8"))
    assert not receipt["accepted"] and receipt["summary"]["error_count"] > 0
    raw_hash=hashlib.sha256((stage / "raw" / tiktok_files[0].name).read_bytes()).hexdigest()
    assert main(args("stage",tiktok_files,stage)) == 2
    assert hashlib.sha256((stage / "raw" / tiktok_files[0].name).read_bytes()).hexdigest() == raw_hash
    assert "Output already exists" in capsys.readouterr().err


def test_prior_capture_comparison_does_not_append_old_rows(tmp_path,tiktok_files):
    stage=tmp_path / "prior"
    assert main(args("stage",tiktok_files,stage)) == 0
    metadata=json.loads(tiktok_files[2].read_text(encoding="utf-8"))
    metadata["captured_at"]="2026-10-26T12:00:00Z"
    tiktok_files[2].write_text(json.dumps(metadata),encoding="utf-8")
    preview=tmp_path / "later.json"
    assert main(args("preview",tiktok_files,preview)+["--compare-observations",str(stage / "normalized/observations.csv")]) == 0
    result=json.loads(preview.read_text(encoding="utf-8"))
    assert len(result["records"]) == 6
    assert result["summary"]["overlap_pairs"] > 0


def test_ambiguous_prior_csv_headers_and_duplicate_mapping_keys_reject(tmp_path,tiktok_files,capsys):
    comparison=tmp_path / "ambiguous.csv"
    comparison.write_text("value, Value \n1,2\n",encoding="utf-8")
    output=tmp_path / "no-preview.json"
    assert main(args("preview",tiktok_files,output)+["--compare-observations",str(comparison)]) == 2
    assert not output.exists()
    tiktok_files[1].write_text('{"schema_version":1,"schema_version":2}',encoding="utf-8")
    assert main(args("stage",tiktok_files,tmp_path / "no-stage")) == 2
    assert "Repeated JSON key" in capsys.readouterr().err
    assert not (tmp_path / "no-stage").exists()


def test_snapshot_keeps_caption_and_publication_separate_from_unknown_activity_bounds(tmp_path,tiktok_files):
    source,mapping_file,metadata_file,_=tiktok_files
    source.write_text("VideoKey,NativeCaption,Published,ViewTotal,Completion\n000987,New song soon,2025-08-01,123,87.5%\n",encoding="utf-8")
    mapping=json.loads(mapping_file.read_text(encoding="utf-8"))
    mapping.update(time_grain="snapshot",publication_date_format="%Y-%m-%d",columns={"entity_id":"VideoKey","caption":"NativeCaption","publication_date":"Published"})
    mapping["metrics"]=[
        dict(metric="video_views",column="ViewTotal",unit="count",measurement_basis="cumulative_count",definition="Synthetic lifetime video views."),
        dict(metric="completion_rate",column="Completion",unit="percent",measurement_basis="rate",allow_percent_suffix=True,definition="Synthetic completion percentage points.")]
    metadata=json.loads(metadata_file.read_text(encoding="utf-8"))
    metadata.update(entity_type="video",entity_id="",report_scope="Synthetic lifetime video snapshot")
    mapping_file.write_text(json.dumps(mapping),encoding="utf-8")
    metadata_file.write_text(json.dumps(metadata),encoding="utf-8")
    output=tmp_path / "snapshot.json"
    assert main(args("preview",tiktok_files,output)) == 0
    result=json.loads(output.read_text(encoding="utf-8"))
    assert result["summary"]["canonical_import_eligible"] is False
    for row in result["records"]:
        assert row["entity_id"] == "000987"
        assert row["period_start"] in {"",None} and row["period_end"] in {"",None}
        assert row["caption"] == "New song soon" and row["publication_date"] == "2025-08-01"
    rate=next(row for row in result["records"] if row["metric"] == "completion_rate")
    assert rate["value"] == 87.5 and rate["unit"] == "percent"


def test_real_cli_runs_outside_project_directory(tmp_path,tiktok_files):
    script=Path(__file__).resolve().parents[1] / "scripts/prepare_tiktok.py"
    output=tmp_path / "subprocess-stage"
    process=subprocess.run([sys.executable,"-X","utf8",str(script),*args("stage",tiktok_files,output)],
        cwd=tmp_path,capture_output=True,text=True,encoding="utf-8",check=False)
    assert process.returncode == 0,process.stderr
    result=json.loads(process.stdout)
    assert result["accepted"] is True and result["summary"]["record_count"] == 6
    assert result["library_modified"] is False
