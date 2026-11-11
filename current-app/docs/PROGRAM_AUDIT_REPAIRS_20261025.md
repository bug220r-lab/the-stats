# Program audit repairs — October 25, 2026

This implements the eleven confirmed items from the [program audit](../outputs/dashboard_program_audit_20261025/AUDIT.md). **Ready within the reviewed repair scope.** Repairs change application behavior and tests; existing source exports, saved analysis databases and registrations are preserved. The original audit remains a historical receipt.

## Implemented decisions

| Audit item | Repair | Regression evidence |
|---|---|---|
| F01: CSV header detection drops rows | The first rectangular header is authoritative. Ordinary `Day` and `Date` values stay in the body. The supported single-title Meta preamble retains source lines; ambiguous prefixes reject. | CSV/TSV/UTF-16 cases, valid Meta title, ambiguous prefixes, and actual UI preview/save/replay of four IDs. |
| F02: definitions collapse across scopes | Definition mismatches reject the complete file transaction. Existing observation keys/schema remain intact; verified distinct scopes can be represented in dimensions. | Preview and save refuse both cross-file and within-file conflicts; prior data/provenance remain unchanged. Equal definitions still replay and overlap idempotently. |
| F03: failed promotion blocks later attempts | Registry preparation uses a unique operation-owned file in the same directory. Failure cleans up only that file and releases locks. | A concurrent-change refusal and a replace failure both allow fresh-key retries. Legacy and other-attempt diagnostics remain unchanged. |
| F04: immutable archive reader ignores rollback journals | Both nonempty WAL and rollback journals are refused at connection use, including existing repository instances. | A real 1,500-row uncommitted cache spill is rejected without modifying the source database or journal. |
| F05: local original-source bytes are unchecked on read | Readback verifies SHA-256 and recorded byte count before returning bytes. A mismatch is an error, not an automatic repair. | Corrupted bytes and incorrect byte counts refuse downloads without changing the stored evidence. |
| F06: incomplete extraction can stage | The complete intended ZIP file inventory must match the extracted inventory in both directions. Duplicate, ambiguous, unsafe and conflicting paths reject before output creation. | Complete flat/prefixed layouts pass exact-byte checks; missing/extra tables, unsafe members and aliases refuse staging. |
| F07: exact values lose precision | Text/integer/Decimal inputs must survive the numeric storage boundary. Inexact large integers, overprecise decimals, nonfinite numbers and nonzero underflow reject. Existing finite binary64 inputs retain their supplied value. | Adjacent large counts cannot become duplicates; ordinary decimals and already-float values remain supported; list validation preserves integer evidence. |
| F08: invalid Apple prior statuses pass | Prior comparison records require a canonical status and a valid numeric/blank relationship. | Invalid statuses and contradictory missing/observed values reject; valid missing states remain distinct from observed zero. |
| F09: new generic packages inherit old dates | New generic stages use a neutral label and null unknown activity/retrieval dates. Explicit metadata and existing immutable replay retain their values. | Unknown dates, explicit provenance and existing replay are verified separately. |
| F10: malformed normalized content counts enter summaries | Negative, fractional, nonfinite, inexact or status-conflicting counts retain raw evidence, receive an explicit invalid status and have no analytical quantity. | Distributions and Spotify capture context exclude invalid quantities while retaining genuine zeros and raw tokens. |
| F11: coverage test expects obsolete wording | Assertions now check current coverage meaning: retained TikTok evidence is uncollected, access has not been rechecked, and earlier Story notices describe historical acquisition state. | Existing coverage AppTest verifies the current page instead of restoring superseded copy. |

The Story comparison audit helper also uses calendar-date subtraction to avoid the observed NumPy timedelta deprecation warning, with unchanged week boundaries.

Concurrent work added Shopify integration during the regression run. That work was preserved. The promotion safeguard was extended to include Shopify's separate registry, database, retained sources and import lock, alongside YouTube. Complete prior-database acceptance inventory, byte-preserving activation/replay, concurrent-change refusals and lock ownership have dedicated regressions. A read-only check also verified the actually registered Shopify collection without performing a promotion.

Two preliminary wrapper-composition hypotheses were excluded by the original audit and were not implemented as fixes. The Import data page continues to use its actual local SQLite repository. No database migration, source-system setting change or new platform collection is part of these repairs.

## Validation and preservation

The final machine-readable outcome, complete suite log, source diff and file inventories are retained in [the repair evidence folder](../outputs/dashboard_program_repairs_20261025/). In particular:

The full run passed **788 tests**, with **30 skipped**, zero failures and no warnings. It added 99 cases over the audit's full run and removed none. After concurrent Shopify edits, focused checks on the final files passed **66 UI/backup/Shopify checks**, **141 promotion/staging checks**, and **25 latest repository checks**. These runs overlap; their counts must not be added into a single suite total. The later promotion safeguard adds 24 dedicated regression cases beyond the full-run snapshot. Twenty-nine skipped checks lack private fixtures; one historical version predates the follows repair.

- `completion.json` and `test_summary.json` record the final full-suite result, skipped-test reasons, source stability and finding-to-regression mapping.
- `pytest.log` and `pytest.xml` retain the complete regression run. Focused test receipts under `inputs/`, `runtime/` and `staging/` are additional checks, not added to the full-suite pass count.
- `metrics/verification.json` independently reconciles the accepted 12 Spotify presets, all 146 complete weeks, spike rankings, audience values and the 75 backfilled Stories after the code changes. `metrics/missingness_verification.json` checks 24 social windows and malformed-count exclusion.
- `browser/` records actual restarted-launcher checks on an isolated byte-verified library copy: four source rows reach preview, scope conflict removes the save path, and existing Spotify spike/Story evidence remains available. Browser verification did not save records. A separate AppTest exercised save and replay only in a synthetic temporary library.
- `final_preservation.json` records all 55 preexisting live-library SQLite/JSON files remaining unchanged. It separately lists 48 added Shopify collection/registry files without attributing their creation to this repair pass. Both registered YouTube ZIP hashes also match. The accepted analysis remains SHA-256 `f013434eb7f24abc6ff138d9c9e0d02c6f42cec8df52530e8e325513a10f9b2b`.
- `before/` preserves the pre-repair source/test/configuration files, with the edited README/import documentation also copied before changes. `source_diff.patch` supports review without a Git checkout.

`concurrent_before/` and phase-specific hash inventories distinguish preserved concurrent work from this pass's edits. The completed full-suite result applies to its recorded source snapshot; final affected paths were rechecked separately after concurrent edits. The repair diff excludes those external implementation files, while retaining the compatibility safeguard in promotion and the shared README's documentation changes.

## Operational meaning

New imports may now refuse ambiguous prefixes, definition mismatches, excessive numeric precision or malformed prior evidence that previously passed silently. Keep originals intact and review explicit scope or a separate documented working copy. Do not round values, invent dates or reinterpret a different definition solely to make a rejected import pass.

Existing analytical limitations still apply: source coverage is not guaranteed complete, unavailable values are not zero, daily listener means are not period-unique audiences, and associations with social posts do not establish causal streaming lift. Real Apple/TikTok native export verification, live-account completeness, hosted authentication and security penetration testing were not part of this implementation.
