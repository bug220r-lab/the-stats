"""Optional private-source reconciliation; the exports stay outside Git."""
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

from stats_app.access import Principal
from stats_app.service import load_collected_baseline
from stats_app.storage import SQLiteRepository


MANIFEST = Path(__file__).resolve().parents[1] / "data" / "source" / "baseline_import_manifest.json"


@pytest.mark.skipif(not MANIFEST.exists(), reason="Private original source package is not included in source control.")
def test_real_native_source_reconciliation_and_fresh_process(tmp_path):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 5
    originals = {}
    expected_streams = {}
    for item in manifest["files"]:
        path = MANIFEST.parent / item["path"]
        raw = path.read_bytes()
        originals[path] = raw
        assert sha256(raw).hexdigest() == item["sha256"]
        # Independent standard-library read checks sums against raw CSV cells,
        # avoiding a reconciliation which repeats the app's pandas parser.
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        assert len(rows) == item["native_row_count"] == 1024
        expected_streams[item["metadata"]["entity_id"]] = sum(int(row["streams"]) for row in rows)
    db = tmp_path / "real-source-check.sqlite3"
    repo = SQLiteRepository(db)
    principal = Principal("Real source test", "admin")
    first = load_collected_baseline(repo, principal, MANIFEST)
    assert sum(item.imported_rows for item in first) == 12288
    second = load_collected_baseline(repo, principal, MANIFEST)
    assert all(item.duplicate_import for item in second)
    assert sum(item.imported_rows for item in second) == 0
    # A fresh Python process represents a complete application-memory restart.
    code = """
import json, sys
from stats_app.storage import SQLiteRepository
r = SQLiteRepository(sys.argv[1])
d = r.observations(sys.argv[2])
s = d[d.metric.eq('streams')].groupby('entity_id').value.sum().to_dict()
print(json.dumps({'rows': len(d), 'streams': s, 'sealed': int(r.list_snapshots().iloc[0].sealed)}))
"""
    assert repo.list_snapshots().iloc[0].is_baseline == 0
    readback = json.loads(subprocess.check_output([sys.executable, "-c", code, str(db), first[0].snapshot_label], text=True, encoding="utf-8"))
    assert readback["rows"] == 12288
    assert readback["sealed"] == 1
    assert readback["streams"] == expected_streams
    for path, raw in originals.items():
        assert path.read_bytes() == raw
        assert repo.original_source(sha256(raw).hexdigest()) == raw
