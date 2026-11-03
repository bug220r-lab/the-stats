"""Build a dated decision report from a registered immutable analysis (no collection)."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from stats_app.analysis_repository import load_registered_analysis
from stats_app.config import load_settings
from stats_app.decision_report import build_report, markdown_report


def refresh(data_dir, output, key=None):
    output=Path(output).resolve()
    repo=load_registered_analysis(data_dir,key)
    if repo is None:
        raise ValueError("No registered analysis. Import a verified analysis package before refreshing.")
    # Refresh outputs belong outside the authoritative data library.
    if output.is_relative_to(Path(data_dir).resolve()):
        raise ValueError("Use a new output directory outside the authoritative data library.")
    if output.exists():
        raise ValueError("Output directory already exists; use a new dated run name.")
    before=hashlib.sha256(repo.db_path.read_bytes()).hexdigest()
    report=build_report(repo)
    after=hashlib.sha256(repo.db_path.read_bytes()).hexdigest()
    if before!=after:
        raise ValueError("Source database changed during refresh; no report written.")
    output.mkdir(parents=True)
    report['refresh_receipt']={"generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "database_sha256_before":before,"database_sha256_after":after,"source_unchanged":True,
        "analysis_version":getattr(repo,"registered_key",None),
        "refresh_script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "analysis_module_sha256":hashlib.sha256((ROOT/'stats_app/decision_report.py').read_bytes()).hexdigest(),
        "calculation_code_sha256":{str(path):hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in ['stats_app/decision_report.py','stats_app/analysis_metrics.py','stats_app/analysis_social_metrics.py']},
        "meaning":"Recomputes local descriptive decisions; does not collect new data, overwrite a source, or rerun retained inference."}
    (output/'decision_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (output/'decision_report.md').write_text(markdown_report(report),encoding='utf-8')
    import pandas as pd
    pd.DataFrame(report['social_coverage']).to_csv(output/'coverage.csv',index=False)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=load_settings().data_dir)
    parser.add_argument('--analysis-key')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        report=refresh(args.data_dir,args.output,args.analysis_key)
    except (OSError,ValueError) as exc:
        parser.exit(1,f"Refresh failed: {exc}\n")
    print(json.dumps({"output":str(args.output.resolve()),"analysis":report['analysis_key'],"period":report['period'],"reconciliation":report['reconciliation'],"source_unchanged":True},ensure_ascii=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
