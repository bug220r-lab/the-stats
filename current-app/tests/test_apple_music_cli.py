"""CLI acceptance boundaries for Apple staging, using synthetic source data only."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.prepare_apple_music import main
from stats_app.validation import validate_records


@pytest.fixture
def apple_files(tmp_path, monkeypatch):
    # The stage guard must never point at a developer's real library in tests.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "synthetic-local-appdata"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "synthetic-roaming-appdata"))
    monkeypatch.setenv("STATS_DATA_DIR", str(tmp_path / "synthetic-live-library"))
    raw = b"ReportDay,NativePlayCount,NativeDailyAudience\n2026-10-01,0,5\n2026-10-02,,*\n"
    source = tmp_path / "synthetic-export.csv"
    source.write_bytes(raw)
    mapping = dict(schema_version=1, encoding="utf-8-sig", delimiter=",", header_row=1,
        date_format="%Y-%m-%d", time_grain="daily", number_format="plain",
        columns={"date":"ReportDay"}, dimensions={}, metrics=[
            dict(metric="plays", column="NativePlayCount", unit="count", measurement_basis="period_count",
                 definition="Synthetic Apple plays test fixture only.", value_tokens={"":"missing"}),
            dict(metric="daily_unique_listeners", column="NativeDailyAudience", unit="count", measurement_basis="distinct_count",
                 definition="Synthetic daily unique listeners test fixture only.", value_tokens={"":"missing", "*":"suppressed"})])
    metadata = dict(account="synthetic-apple-artist", entity_type="artist", entity_id="synthetic-apple-artist",
        entity_name="Synthetic fixture only", source_kind="artists_csv", source_timezone="UTC",
        captured_at="2026-10-25T12:00:00+00:00", report_scope="Synthetic CLI test; not actual Apple data", filters={})
    mapping_file, metadata_file = tmp_path / "mapping.json", tmp_path / "metadata.json"
    mapping_file.write_text(json.dumps(mapping), encoding="utf-8")
    metadata_file.write_text(json.dumps(metadata), encoding="utf-8")
    return source, mapping_file, metadata_file, raw


def command_args(mode, files, output):
    source, mapping, metadata, _ = files
    return [mode, "--input", str(source), "--mapping", str(mapping), "--metadata", str(metadata), "--output", str(output)]


def test_inspection_and_staging_preserve_source_bytes_and_missingness(tmp_path, apple_files, capsys):
    source, _, _, raw = apple_files
    inspection = tmp_path / "inspection.json"
    assert main(["inspect", "--input", str(source), "--output", str(inspection)]) == 0
    assert "NativePlayCount" in inspection.read_text(encoding="utf-8")
    stage = tmp_path / "new-stage"
    assert main(command_args("stage", apple_files, stage)) == 0
    receipt = json.loads((stage / "stage_receipt.json").read_text(encoding="utf-8"))
    assert receipt["accepted"] is True
    assert receipt["library_modified"] is False
    assert receipt["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert (stage / "raw" / source.name).read_bytes() == source.read_bytes() == raw
    preview = json.loads((stage / "preview.json").read_text(encoding="utf-8"))
    assert len(preview["records"]) == 4
    assert validate_records(preview["records"]) == []
    assert {row["status"] for row in preview["records"]} == {"observed", "missing", "suppressed"}
    zeros = [row for row in preview["records"] if row["value_status"] == "observed_zero"]
    assert len(zeros) == 1 and zeros[0]["value"] == 0


def test_existing_output_rejected_without_overwriting(tmp_path, apple_files, capsys):
    output = tmp_path / "preserved.json"
    output.write_bytes(b"preserve this earlier receipt")
    assert main(command_args("preview", apple_files, output)) == 2
    assert output.read_bytes() == b"preserve this earlier receipt"
    assert "Output already exists" in capsys.readouterr().err


def test_duplicate_json_keys_rejected_before_staging(tmp_path, apple_files, capsys):
    apple_files[1].write_text('{"schema_version":1,"schema_version":2}',encoding="utf-8")
    output = tmp_path / "no-stage"
    assert main(command_args("stage", apple_files, output)) == 2
    assert not output.exists()
    assert "Repeated JSON key" in capsys.readouterr().err


def test_rejected_mapping_is_review_evidence_not_accepted_data(tmp_path, apple_files):
    mapping = json.loads(apple_files[1].read_text(encoding="utf-8"))
    mapping["metrics"][0]["column"] = "Not a real header"
    apple_files[1].write_text(json.dumps(mapping),encoding="utf-8")
    output = tmp_path / "rejected-stage"
    assert main(command_args("stage", apple_files, output)) == 2
    receipt = json.loads((output / "stage_receipt.json").read_text(encoding="utf-8"))
    assert receipt["accepted"] is False
    assert receipt["summary"]["error_count"] > 0
    assert (output / "raw" / apple_files[0].name).read_bytes() == apple_files[3]


def test_prior_staged_csv_reports_overlaps_without_merging(tmp_path, apple_files):
    prior = tmp_path / "prior-stage"
    assert main(command_args("stage", apple_files, prior)) == 0
    metadata = json.loads(apple_files[2].read_text(encoding="utf-8"))
    metadata["captured_at"] = "2026-10-26T12:00:00+00:00"
    apple_files[2].write_text(json.dumps(metadata),encoding="utf-8")
    output = tmp_path / "later-preview.json"
    assert main(command_args("preview", apple_files, output) + ["--compare-observations", str(prior / "normalized/observations.csv")]) == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert len(result["records"]) == result["summary"]["record_count"] == 4
    assert result["summary"]["overlap_pairs"] > 0 or result["summary"]["duplicate_record_groups"] > 0


def test_ambiguous_prior_csv_headers_rejected(tmp_path, apple_files, capsys):
    prior = tmp_path / "ambiguous.csv"
    prior.write_text("value, Value \n1,2\n", encoding="utf-8")
    output = tmp_path / "no-preview.json"
    assert main(command_args("preview", apple_files, output) + ["--compare-observations", str(prior)]) == 2
    assert not output.exists()
    assert "unambiguous CSV headers" in capsys.readouterr().err


def test_real_cli_runs_from_another_directory(tmp_path, apple_files):
    script = Path(__file__).resolve().parents[1] / "scripts/prepare_apple_music.py"
    stage = tmp_path / "subprocess-stage"
    process = subprocess.run([sys.executable, "-X", "utf8", str(script),
                              *command_args("stage", apple_files, stage)],
                             cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", check=False)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result["accepted"] is True and result["library_modified"] is False
    assert result["summary"]["record_count"] == 4
    assert (stage / "raw" / apple_files[0].name).read_bytes() == apple_files[3]
