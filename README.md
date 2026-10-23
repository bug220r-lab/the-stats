# The Stats™️ — project backup, October 23, 2026

This dated backup preserves the project files accessible from the existing Google Drive project and saved project artifacts at collection time. Original source bytes are unchanged. It is a recovery snapshot, not a claim that every conversation or the latest computer-only edit has been exported.

## Contents

- **133 source records:** 114 Drive files and 19 saved project artifacts, including byte-identical copies from different origins. There are **118 unique source contents**, totaling **227,926,086 bytes** before ZIP compression and counting duplicated source records.
- Spotify workbooks, original source data, collection supplements, recovery and continuation packages.
- Facebook and Instagram capture evidence, the Meta/TikTok status package, and the saved application database. An archived package name is not evidence that blocked TikTok analytics were collected.
- YouTube collection package, current workbook export, 26 organized CSVs, and all 67 original export ZIPs.
- Analysis reports, data-quality assessment, statistical results, measurement plan, dashboard handoffs, and pasted project text.
- Three original logo assets and two flyer references within the preserved branding bundle.
- The complete saved October 22 dashboard recovery ZIP, plus **29 extracted application-source files** for browsing and version control.
- Source identities, file paths, SHA-256 hashes, verification reports, and restore instructions.

## Where to start

| Location | Purpose |
| --- | --- |
| `RESTORE.md` | Restore and verify on Windows or another computer |
| `SOURCE_MANIFEST.csv` / `.json` | Map each source file to its backup path and checksum |
| `sources/drive/Project/` | Portable copies of the complete discovered Drive project tree |
| `sources/library/` | Saved project artifacts from prior work |
| `application-source/` | Unchanged source, tests, docs, templates, and locks recovered from the October 22 application ZIP |
| `verification/` | Download, native-copy, archive, and database verification evidence |
| `docs/SCOPE_AND_LIMITS.md` | Exact coverage and limitations |
| `SHA256SUMS.txt` / `verify_backup.py` | Verify the extracted backup files |

## Remote destinations

- [Dated Google Drive backup folder](https://drive.google.com/drive/folders/122KQIiOGFl_h0ZpthM-333__r1bVd2_N). It also contains native editable copies of the two Google Sheets and project-index document.
- [Original Drive project](https://drive.google.com/drive/folders/1sE3oczZadl04Ro2HDf0GQ51oxuNxiLdR). Its existing files and sharing were preserved.
- **GitHub: prepared, awaiting repository creation/sign-in.** The connected account is `bug220r-lab`. No remote GitHub backup existed at this package's assembly. The accompanying Git bundle contains a local recovery commit; it is not proof of a successful push.

## Verification completed

All 133 source records were copied and locally hashed. Every downloaded stored-file size matches its declared source size; native Google exports have their own exported sizes. ZIP/container checks passed. The complete dashboard ZIP has **741 members**, and **740 of 740** original manifest entries match. Its SQLite backup passed a read-only integrity check. The extracted 15 Python files parse successfully; the application and historical 127-test suite were not run during backup.

The native workbook copies retain the original 36-sheet and 5-sheet structures, locale, and reporting timezone. This is a current-content snapshot, not an export of every past revision or comment.

## Material limits

The saved application package is dated October 22 and refers to an earlier macOS workspace. **Newer Windows/Codex edits and an active local database were not accessible and are not verified as included.** Restore the populated application from the full recovery ZIP; the extracted code directory intentionally has no database or raw data.

The archived application handoff explicitly describes the original October 20 baseline as **unavailable/unverified**. An October 20 reporting endpoint is not proof of original baseline provenance. All source labels and qualifications are preserved. Later Spotify and YouTube packages remain separate inputs; this backup does not import them into the October 22 application database.

Available handoff files and pasted text are included. **Full ChatGPT/Codex conversation histories and unsaved drafts are not included.** The original branding prompt is retained as historical material because it was rejected as a current Codex specification. Credentials, browser sessions, and virtual environments are not backup targets.
