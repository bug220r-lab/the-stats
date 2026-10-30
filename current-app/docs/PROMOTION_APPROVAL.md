# Approval of immutable analysis versions

`scripts/promote_analysis.py` accepts a new version only with a candidate-bound independent semantic acceptance receipt. An existing file, a storage-only PASS, or a generic `passed`/hash pair cannot authorize activation. This gate validates the receipt contract and exact bytes; it does not authenticate the reviewer or perform the independent semantic review itself.

Both retained acceptance formats require:

- A JSON object with `passed: true` (the JSON boolean), no duplicate keys or non-finite JSON values, and `status: "PASS"` if status is present.
- `candidate_database_sha256`: the lowercase SHA-256 of the exact staged `analysis.sqlite3` bytes.
- The requested version key in `analysis_version` or `analysis_key`, as required by the format. If both appear, both must match.
- `audited_at_utc`: an ISO timestamp with an explicit UTC offset.
- `all_prior_database_hashes`: a map of relative database paths to lowercase SHA-256 values. It must exactly match the registered predecessor databases and writable database immediately before copying. A changed library needs a new review receipt.
- No outstanding semantic-review-required flag. Optional `schema_version`, if supplied, must be integer `1`.

## Retained Meta follow-up acceptance format

This format has `audit_scope: "independent_semantic_evidence_and_storage_acceptance"`, a matching `analysis_version`, a nonempty `semantic_checks` object, and a nonempty `storage_checks` object. Boolean check results cannot be false; counts and lists remain findings rather than inferred pass flags. The storage checks `all_candidate_table_rows_match_csv` and `all_zip_assets_match_database`, and `registry_unchanged_before_activation`, must each be true.

`supporting_receipts` is a hash map with exactly `semantic_acceptance_audit.json` and `independent_storage_audit.json`.

## Retained Instagram acceptance format

This format has a matching `analysis_key`, `status: "PASS"`, nonempty `approval_scope` text and `summary` object, and a `normalization_receipt_sha256`. It has no `audit_scope` field. Its `supporting_receipts` list has two objects, each with a relative forward-slash `path` and `sha256`: one `semantic_acceptance_audit.json` and one `direct_sql_storage_audit.json`.

Supporting receipt paths and digests are checked for the required structure and retained as provenance. The gate does not resolve those external paths or claim their bytes were re-audited. The independent acceptance receipt must be produced by an actual semantic and storage review; populating a shape alone is not such a review.

## Copy and replay behavior

The gate pins the candidate and acceptance bytes before activation. It checks the complete stage file inventory, copied files, audit bytes, and prior database hashes before the atomic registry replacement. The final prior-state check re-enumerates which registered database paths and optional writable database exist, so a newly created or removed database also invalidates acceptance. Changes during validation or copying leave the previous registry active; any copied candidate remains unregistered for inspection. The activation receipt records the accepted database hash, audit hash and recognized acceptance format. No pre-existing evidence is deleted or overwritten.

The writable `stats.sqlite3` must be checkpointed and quiescent. A nonempty `stats.sqlite3-wal` or `stats.sqlite3-journal` causes refusal before acceptance/copy and immediately before registry replacement, even if the main database hash still matches. Committed WAL pages can change logical data without changing that main-file hash. The gate only reads sidecar metadata and main-file bytes; it never opens a writable SQLite connection, checkpoints, deletes sidecars or attempts recovery. It also verifies that the writable main-file hash remains stable. A successful sidecar check is a point-in-time observation, not a lock against an unrelated writer; the library owner must keep writes stopped through promotion.

Earlier receipts lacking this contract cannot approve a new version. An exact already-registered key, label, database and evidence replay may return its current status without creating a lock, changing files, or switching the active pointer. This preserves historical compatibility without granting a new approval.

Read-only replays apply the same sidecar refusal at entry and before returning, and check the writable main-file hash for changes. They cannot report unchanged data while observed committed changes are held only in a WAL.

Approval does not establish original October 20 baseline membership, resolve deferred Story audio mappings, or authorize inferred causal or conversion claims. Those limitations remain attached to the retained evidence.
