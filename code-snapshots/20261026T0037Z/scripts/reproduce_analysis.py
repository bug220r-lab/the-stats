"""Reproduce a retained analysis package in a new, independent output directory.

The package's Python pipeline executes with this interpreter. Input checksums
are verified before copying, and all input files are checked again afterward.
Only the copy receives two documented Windows path-normalization fixes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import time


PATH_FIXES = (
    ("code/audit_inputs.py", "rel=str(p.relative_to(ROOT))", "rel=p.relative_to(ROOT).as_posix()"),
    ("code/spotify_pipeline.py", "file=str(f.relative_to(root))", "file=f.relative_to(root).as_posix()"),
)


def file_hash(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def tree_hashes(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"The package must contain ordinary files, not symbolic links: {path}")
        if path.is_file():
            if not path.resolve().is_relative_to(root):
                raise ValueError(f"Package file resolves outside its directory: {path}")
            result[path.relative_to(root).as_posix()] = file_hash(path)
    return result


def verify_raw_manifest(root: Path) -> int:
    entries = json.loads((root / "raw_sha256.json").read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not entries:
        raise ValueError("raw_sha256.json must contain a nonempty list of source files.")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Every source manifest entry must be an object.")
        relative, expected = entry.get("path"), entry.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError("Every source manifest entry requires a path and SHA-256.")
        parts = PurePosixPath(relative)
        if (parts.is_absolute() or ".." in parts.parts or "\\" in relative
                or not parts.parts or parts.parts[0] != "raw"
                or relative in seen or not re.fullmatch(r"[0-9a-f]{64}", expected)):
            raise ValueError(f"Unsafe, repeated, or invalid source manifest entry: {relative}")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Missing or invalid source file: {relative}")
        if file_hash(path) != expected:
            raise ValueError(f"Source checksum mismatch: {relative}; reproduction cancelled.")
        seen.add(relative)
    return len(seen)


def apply_path_fixes(output: Path) -> list[dict]:
    fixes = []
    for relative, before, after in PATH_FIXES:
        path = output / relative
        text = path.read_text(encoding="utf-8")
        original_hash = file_hash(path)
        if text.count(before) == 1 and after not in text:
            path.write_text(text.replace(before, after), encoding="utf-8")
            changed = True
        elif text.count(after) == 1 and before not in text:
            changed = False
        else:
            raise ValueError(f"Unrecognized pipeline version in {relative}; inspect before adapting it.")
        fixes.append({"path": relative, "changed": changed, "before_sha256": original_hash,
                      "after_sha256": file_hash(path), "old": before, "new": after})
    return fixes


def reproduce(package: Path, output: Path) -> dict:
    package, output = package.expanduser().resolve(), output.expanduser().resolve()
    if not package.is_dir() or not (package / "code/run_all.py").is_file():
        raise ValueError("Choose the extracted analysis directory containing code/run_all.py.")
    if output.exists():
        raise ValueError("The output directory already exists. Choose a NEW directory; nothing was overwritten.")
    if output.is_relative_to(package) or package.is_relative_to(output):
        raise ValueError("The output must be separate from the source package directory.")
    originals = tree_hashes(package)
    raw_count = verify_raw_manifest(package)
    shutil.copytree(package, output)
    audit_dir = output / "audit"
    audit_dir.mkdir(exist_ok=True)
    log_path = audit_dir / "windows_reproduction_run.log"
    report_path = audit_dir / "windows_reproduction_manifest.json"
    report = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "package": str(package), "output": str(output), "python": sys.executable,
        "python_version": sys.version, "raw_manifest_files": raw_count,
        "original_file_sha256": originals, "log": str(log_path), "status": "running",
        "dependency_versions": {},
    }
    for name in ("pandas", "numpy", "scipy", "matplotlib", "openpyxl"):
        try:
            report["dependency_versions"][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            report["dependency_versions"][name] = None
    started = time.monotonic()
    try:
        if tree_hashes(output) != originals:
            raise ValueError("Copied package does not match the source tree.")
        report["path_fixes"] = apply_path_fixes(output)
        environment = dict(os.environ)
        environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
                           MPLCONFIGDIR=str(audit_dir / "matplotlib-cache"))
        command = [sys.executable, str(output / "code/run_all.py")]
        report["command"] = command
        report["environment_overrides"] = {name: environment[name] for name in
                                           ("PYTHONUTF8", "PYTHONIOENCODING", "MPLCONFIGDIR")}
        validation_path = audit_dir / "final_validation.json"
        prior_validation_mtime = validation_path.stat().st_mtime_ns if validation_path.exists() else None
        with log_path.open("w", encoding="utf-8") as log:
            completed = subprocess.run(command, cwd=output, env=environment,
                                       stdout=log, stderr=subprocess.STDOUT, check=False)
        report["pipeline_exit_code"] = completed.returncode
        if completed.returncode:
            raise ValueError(f"Analysis pipeline exited with code {completed.returncode}; see {log_path}")
        if (prior_validation_mtime is not None and validation_path.exists()
                and validation_path.stat().st_mtime_ns == prior_validation_mtime):
            raise ValueError("The pipeline did not regenerate final_validation.json; copied checks are not a new run.")
        final = json.loads(validation_path.read_text(encoding="utf-8"))
        report["final_validation"] = final
        if not final.get("checks") or not all(value is True for value in final["checks"].values()):
            raise ValueError("The pipeline's final validation did not pass every check.")
        report["copy_raw_files_verified_after_run"] = verify_raw_manifest(output)
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        current = tree_hashes(package)
        changed = sorted(name for name in originals.keys() | current.keys()
                         if originals.get(name) != current.get(name))
        report.update(original_package_unchanged=not changed, changed_source_files=changed,
                      elapsed_seconds=round(time.monotonic() - started, 3),
                      finished_at_utc=datetime.now(timezone.utc).isoformat())
        if changed:
            report.update(status="failed", error="Original package files changed during reproduction.")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True,
                        help="Extracted directory containing raw_sha256.json and code/run_all.py")
    parser.add_argument("--output", type=Path, required=True,
                        help="New directory outside the source package; existing paths are refused")
    args = parser.parse_args()
    try:
        report = reproduce(args.package, args.output)
    except (OSError, ValueError) as exc:
        print(f"Reproduction refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({key: report.get(key) for key in
                      ("status", "output", "pipeline_exit_code", "original_package_unchanged", "log", "error")},
                     ensure_ascii=True, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
