"""Create an independently validated new analysis package; never touch live databases."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stats_app.spotify_recovery import integrate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("original", "recovery", "continuation", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--archives", type=Path, nargs=3, required=True,
                   metavar=("ORIGINAL_ZIP", "RECOVERY_ZIP", "CONTINUATION_ZIP"))
    args = p.parse_args()
    result = integrate(args.original, args.recovery, args.continuation, args.output, args.archives)
    print(json.dumps({k: result[k] for k in ("analysis_version", "canonical_daily_observations", "added_daily_observations", "source_audit", "queue_status_counts")}, indent=2))


if __name__ == "__main__":
    main()
