# Decision workflow verification — October 23, 2026

**339 tests passed**, zero failures/errors, in 342.61 seconds using the full existing suite plus new tests. A subsequent focused pass covering the final report changes passed **11 tests** in 26.66 seconds. `pip check` reports **No broken requirements found**. Logs are `logs/decision-workflow-tests-20261023.log` and `logs/decision-report-post-review-20261023.log`; the structured receipt is `data/reconciliation/decision-workflow-verification-20261023.json`.

## What was verified

- Existing import/repository/versioning, archive and backup behavior, access controls, original input preservation, overlapping observation handling and application views passed the full suite.
- Campaign imports validate timezone offsets, exact identity, required provenance, missing numeric values and tag status; repeat imports/overlaps are idempotent. Newer explicit revision times win independently of arrival order; conflicting equal-time rows reject atomically. Original bytes are hash checked, editable exports round trip, and viewers cannot commit. UI tests verified preview/save/refresh/replay with isolated fixtures.
- Real Spotify native rows reconcile to 4,246/4,011 streams, 217/129 saves and 362/366 playlist additions in matched 28-day windows. All 14 recording stream totals reconcile to the artist totals. Direct period listeners remain 1,062/1,121; no daily distinct sum is used. Follower endpoints reconcile to 1,616→1,644, net +28. Latest complete week October 12–18 has 1,224 streams; the trailing 2/7-day week remains unavailable.
- The Instagram follows repair is one canonical descriptive series with its row vintages preserved, 293 dates and 15/15 follow events. All 12 social scope/metric comparisons remain separate. Old source tables and original cross-platform results remain unchanged.
- Source ratios reject missing/nonfinite/nonpositive denominators. Period summaries reject missing, failed and partial observations. Joins enforce unique keys. Unsupported attribution, equal-age content and retention analyses identify their missing evidence.
- All six Decision report views render in Streamlit AppTest. The normal Windows batch launcher was then run on loopback port 8513 against a separate hash-verified copy of the active analysis and verified YouTube ZIP. Browser readback confirmed Overview, the new report cards and weekly chart, Campaigns template/import controls, and all 27 YouTube video identities. The test preview was closed after verification. Physical double-click and manual console Ctrl+C were not tested.
- The refreshed report used active version `instagram-story-owner-20261023`. Its source database SHA-256 before/after and the final preservation check match `5aa85bb3efa84a8a759ecf544414a5c067b9f25b9cf4a886a45d3385b0e344ef`. Each consumed source table is hash checked by the immutable repository. Report/source metadata remain separate from originals.

## Concrete failures resolved

The first suite exposed a Windows test decoding failure: a UTF-8 traceback with the project's Unicode path was read using the default code page. The test now explicitly reads UTF-8. YouTube fixtures previously stopped at an inaccessible live-file candidate; discovery now continues to the accessible original ZIP and validates it. Optional inaccessible YouTube files no longer hide unrelated dashboard pages.

Independent review caught the first draft report grouping the repaired Instagram series by historical row vintages, splitting the completed series. The new view now selects the documented canonical repair, retaining source vintages separately. Missing source timezone labels use the existing canonical Pacific calendar contract, without converting daily dates. Tests verify 12 compatible series and the corrected 15/15 result. The provisional run is marked superseded; use `data/reconciliation/decision-report-20261023-final`.

## Remaining limits

The registered live YouTube database could not be read by this tool session. Its original ZIP, source hashes, importer, backup relocation, all YouTube tests and staged browser view passed; this is not proof of access to that live file. No source permissions were changed or live database replaced. No production campaign rows were imported, and no deployment or external sharing changed.

Original October 20 baseline membership remains unverified. The prior 16 workbook checks were retained evidence; the fresh connected workbook read checked bounded queue/reconciliation ranges, not all 16 checks again. TikTok, six Story song mappings, equal-age content histories, measured post-to-stream conversion and person-level retention remain unsupported. Existing observational results establish no causal effect.

Other ongoing work updated the owner-Story handoff during this task. That update was preserved; this implementation's separate handoff is `handoff/DECISION_WORKFLOW_20261023.md`.
