"""Exercise isolated reproduction and refusal paths without rerunning analytics."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def wrapper():
    path = Path(__file__).resolve().parents[1] / "scripts/reproduce_analysis.py"
    spec = importlib.util.spec_from_file_location("stats_reproduction_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def package(tmp_path):
    root = tmp_path / "source"
    (root / "code").mkdir(parents=True)
    (root / "raw").mkdir()
    (root / "raw/export.csv").write_bytes(b"date,value\n2026-10-20,5\n")
    (root / "raw_sha256.json").write_text(json.dumps([{
        "path": "raw/export.csv", "sha256": hashlib.sha256((root / "raw/export.csv").read_bytes()).hexdigest()
    }]), encoding="utf-8")
    (root / "code/audit_inputs.py").write_text("rel=str(p.relative_to(ROOT))\n", encoding="utf-8")
    (root / "code/spotify_pipeline.py").write_text("file=str(f.relative_to(root))\n", encoding="utf-8")
    (root / "code/run_all.py").write_text(
        "from pathlib import Path\nimport json, os\n"
        "assert os.environ['PYTHONUTF8'] == '1'\n"
        "assert '.as_posix()' in Path('code/audit_inputs.py').read_text()\n"
        "assert '.as_posix()' in Path('code/spotify_pipeline.py').read_text()\n"
        "Path('generated.txt').write_text('Reproduced \\u2122', encoding='utf-8')\n"
        "Path('audit/final_validation.json').write_text(json.dumps({'checks': {'sample': True}}))\n"
        "print('isolated pipeline completed')\n", encoding="utf-8")
    return root


def test_copy_pipeline_preserves_inputs_and_records_evidence(wrapper, package, tmp_path):
    before = wrapper.tree_hashes(package)
    output = tmp_path / "reproduced"
    report = wrapper.reproduce(package, output)
    assert report["status"] == "passed"
    assert report["pipeline_exit_code"] == 0
    assert report["original_package_unchanged"]
    assert wrapper.tree_hashes(package) == before
    assert (output / "generated.txt").read_text(encoding="utf-8") == "Reproduced ™"
    assert "isolated pipeline completed" in (output / "audit/windows_reproduction_run.log").read_text()
    saved = json.loads((output / "audit/windows_reproduction_manifest.json").read_text(encoding="utf-8"))
    assert saved["copy_raw_files_verified_after_run"] == 1
    assert len(saved["path_fixes"]) == 2


def test_existing_output_is_never_overwritten(wrapper, package, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="already exists"):
        wrapper.reproduce(package, output)
    assert (output / "keep.txt").read_text() == "keep"


def test_raw_mismatch_refuses_before_output_creation(wrapper, package, tmp_path):
    (package / "raw/export.csv").write_bytes(b"changed")
    output = tmp_path / "new"
    with pytest.raises(ValueError, match="checksum mismatch"):
        wrapper.reproduce(package, output)
    assert not output.exists()


def test_output_inside_source_is_refused(wrapper, package):
    with pytest.raises(ValueError, match="separate"):
        wrapper.reproduce(package, package / "nested")
    assert not (package / "nested").exists()


def test_failed_pipeline_retains_log_and_source_preservation_report(wrapper, package, tmp_path):
    (package / "code/run_all.py").write_text("raise RuntimeError('known failure')\n", encoding="utf-8")
    output = tmp_path / "failed"
    report = wrapper.reproduce(package, output)
    assert report["status"] == "failed"
    assert report["pipeline_exit_code"] != 0
    assert report["original_package_unchanged"]
    assert "known failure" in (output / "audit/windows_reproduction_run.log").read_text(encoding="utf-8")


def test_manifest_escape_is_rejected(wrapper, package, tmp_path):
    (package / "raw_sha256.json").write_text(json.dumps([{
        "path": "../outside.csv", "sha256": "0" * 64
    }]), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid source manifest"):
        wrapper.reproduce(package, tmp_path / "reproduced")


def test_copied_validation_cannot_masquerade_as_fresh_run(wrapper, package, tmp_path):
    (package / "audit").mkdir()
    (package / "audit/final_validation.json").write_text(json.dumps({"checks": {"old": True}}))
    (package / "code/run_all.py").write_text("print('No regenerated validation')\n", encoding="utf-8")
    report = wrapper.reproduce(package, tmp_path / "not-regenerated")
    assert report["status"] == "failed"
    assert "did not regenerate" in report["error"]
    assert report["original_package_unchanged"]
