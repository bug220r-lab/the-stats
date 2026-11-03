# Apple Music preparation handoff — October 25, 2026

Preparation is complete. Genuine Apple data collection, native-schema verification, persistent collection registration, dashboard views and Apple/social/Spotify comparisons remain future integration work. No Apple account or API credentials were accessed, and no genuine Apple observations were imported by this pass.

## Added groundwork

- `stats_app/apple_music.py`: explicit-mapping artist-CSV inspection, validation, optional comparison with prior staged rows, and new-directory-only review staging.
- `scripts/prepare_apple_music.py`: `inspect`, `preview` and `stage` CLI commands, strict JSON inputs, exclusive output creation, and rejected-preview exit code 2.
- `templates/apple_music.daily.mapping.template.json`, `apple_music.period.mapping.template.json`, and `apple_music.metadata.template.json`: project mapping contracts with deliberately incomplete identity/header values. They are not native Apple export schemas.
- `templates/apple_music.recording_crosswalk.template.csv`: an empty future identity-review worksheet, not an active cross-platform mapping.
- `docs/APPLE_MUSIC_INTEGRATION_20261025.md`: current primary Apple source review, collection checklist, metric definitions and unresolved native-export questions.
- `docs/APPLE_MUSIC_PREPARATION.md`: local commands and interpretation rules. README links to both guides.

The adapter keeps plays, daily uniques, period uniques, period listener averages, Shazams, radio spins, iTunes song/album purchases and music-video views distinct. It rejects unqualified listeners, Spotify streams aliases, unsupported source families, conflicting metric bases and invalid count formats. Listening Now is outside this historical adapter.

Raw bytes, hashes, literal headers/cells, line/record references, metric definitions, scope/filters, capture evidence and native status tokens remain inspectable. Canonical dimensions also include the reserved `_apple_music_scope` object so fixed filters and report scope survive a standard 20-column projection. Blank mapped fields do not fall back to metadata; a known period may come from explicit metadata only when no corresponding source column is mapped.

Duplicate and overlap checks compare compatible typed entities, metrics, periods, definitions, scope, dimensions and filters. Equal numeric representations such as 1 and 1.0 are equivalent while their raw strings remain retained. Same-delivery conflicts reject even when capture time is unknown; newer or unknown captures remain separate review observations. No aggregation, revision selection, zero filling, or cross-platform audience merging occurs.

Staging creates raw/config/normalized/review evidence and hashed receipts. Rejected packages are marked `accepted: false`, and any partial normalized rows are review evidence only. Existing destinations and AppData/live data directories are refused. The command never calls a production importer or changes an analysis registry.

## Verification performed

- **37 Apple core and CLI tests passed** on the frozen module, including a subprocess launched outside the project directory, canonical validation, source-byte preservation, rejected-stage retention, prior-capture comparison, output refusal, missingness, explicit date parsing, fixed-filter portability, count overflow and nonzero-average underflow.
- **110 existing ingestion, calculations, import-preview and storage tests passed.** These are separate test files from the 37 above, for 147 tests total. No full dashboard/UI regression suite was needed because existing runtime/UI files were unchanged.
- **33 independent synthetic checks passed** against final module SHA-256 `fa31523614a1f59d516380ccaf62a2c19c3c418a4f70f59a5e61e9fe026e8af9`. Earlier review receipts remain retained.
- All three JSON templates parse successfully; the crosswalk is header-only.
- Before/after hashes confirm all **109 tracked existing application/dependency/library files**, including **55 live-library SQLite/JSON files**, unchanged. No added library file was found. Existing analysis versions, registries and source collections remain separate.

Receipts:

- `outputs/apple_music_preparation_20261025/apple-preparation-frozen-tests.xml`
- `outputs/apple_music_preparation_20261025/existing-import-regression.xml`
- `test-results/apple-music-preparation-20261025-review/independent_review_final_v3.json`
- `outputs/apple_music_preparation_20261025/preservation_before.json`
- `outputs/apple_music_preparation_20261025/preservation_after.json`
- `outputs/apple_music_preparation_20261025/completion.json`

All executed import examples were clearly synthetic fixtures. These tests establish local preparation behavior, not the shape or meaning of a genuine Apple export. No dashboard layout, navigation or source binding changed, so the running dashboard did not need a restart or browser verification.

## Next required input

Obtain an untouched Apple Music for Artists catalog CSV with the selected artist, dates, metric labels and filters recorded. Apple's documented path is Music → See All with the requested date range selected before CSV download. Obtain genuine dated artist Plays and daily Listeners evidence if the actual account exposes it; a catalog-period CSV is not guaranteed to contain daily rows.

Inspect that file, map its literal schema, reconcile an appropriate native total and review identity/overlap findings before implementing immutable-library activation. Apple Music for Artists uses UTC and daily refresh with a documented display delay; provider Sales and Trends/API data must retain their own contracts. A Music Analytics API exists for eligible label partners, but this account's access is unverified and no setup was performed. See the primary-source guide for exact official links.
