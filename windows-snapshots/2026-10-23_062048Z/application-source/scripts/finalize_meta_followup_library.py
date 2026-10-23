"""Verify this dated promotion and create a portable backup without replacing data."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from scripts.promote_analysis import promote
from stats_app.analysis_repository import list_registered_analyses, load_registered_analysis
from stats_app.backup import backup_library, verify_bundle
from stats_app.config import load_settings


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key', default='meta-followup-20261023')
    parser.add_argument('--reconciliation-dir', type=Path, default=Path('data/reconciliation/meta_followup_20261023'))
    parser.add_argument('--bundle-dir', type=Path, default=Path('backups/library-meta-followup-2026-10-23'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = (root / args.reconciliation_dir).resolve()
    data = load_settings().data_dir
    audit_path = output / 'independent_acceptance_audit.json'
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    assert audit['passed'] is True
    registry = data / 'archive_registry.json'
    before_replay = digest(registry)
    replay = promote(output / 'staged_analysis', audit_path, data, key=args.key)
    assert replay['idempotent'] and replay['active']
    assert digest(registry) == before_replay
    earlier = {relative: digest(data / relative) for relative in audit['all_prior_database_hashes']}
    assert earlier == audit['all_prior_database_hashes']
    active = load_registered_analysis(data)
    assert active.registered_key == args.key
    assert digest(active.db_path) == audit['candidate_database_sha256']
    checks = {}
    for path in [data / relative for relative in earlier] + [active.db_path]:
        with sqlite3.connect(Path(path).as_uri() + '?mode=ro&immutable=1', uri=True) as conn:
            checks[Path(path).relative_to(data).as_posix()] = conn.execute('PRAGMA quick_check').fetchone()[0]
    assert set(checks.values()) == {'ok'}
    bundle = (root / args.bundle_dir).resolve()
    backup_library(data, bundle)
    manifest = verify_bundle(bundle)
    live_versions = list_registered_analyses(data)
    assert live_versions == list_registered_analyses(bundle)
    readback = {}
    for version in live_versions:
        live = load_registered_analysis(data, version['key'])
        copied = load_registered_analysis(bundle, version['key'])
        assert digest(live.db_path) == digest(copied.db_path)
        for table in copied.tables:
            assert live.table(table).equals(copied.table(table))
        assert live.original_zip() == copied.original_zip()
        readback[version['key']] = {'tables': len(copied.tables), 'database_sha256': digest(copied.db_path), 'all_tables_and_zip_equal': True}
    assert {relative: digest(data / relative) for relative in earlier} == earlier
    report = {
        'verified_at_utc': datetime.now(timezone.utc).isoformat(),
        'active_version': active.registered_key,
        'duplicate_promotion': replay,
        'duplicate_replay_registry_unchanged': True,
        'earlier_database_hashes': earlier,
        'all_earlier_databases_unchanged': True,
        'earlier_database_count': len(earlier),
        'database_quick_checks': checks,
        'backup': str(bundle.relative_to(root)),
        'backup_files': len(manifest['files']),
        'backup_analysis_versions': manifest['analysis_versions_included'],
        'backup_verification': 'all manifest paths, sizes and SHA-256 hashes match',
        'relocated_readback': readback,
        'restore_limit': 'Readback from relocated backup verified; no live database replacement performed.'
    }
    (output / 'final_preservation_and_backup.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('active_version', 'all_earlier_databases_unchanged', 'earlier_database_count', 'backup_files', 'backup_analysis_versions')}))
