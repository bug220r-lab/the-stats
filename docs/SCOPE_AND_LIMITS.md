# Backup scope and restore caveats

Prepared for the October 23, 2026 backup of The Stats™️. This is review text for the backup README; it is not a complete ChatGPT conversation export.

## What the inventory covers

The discovered Drive project tree contains 114 files across the main project area, Analysis_2026-10-22, and YouTube, including 67 original YouTube export ZIPs and 26 organized YouTube CSVs. The separate Library inventory contains 19 project artifacts. These are 133 source records before accounting for byte-identical copies held in both places. Counts should distinguish source records, unique file contents, and files nested inside archives. Existing archives preserve additional source files, code, evidence, and historical outputs.

Native Google files have both portable exports and dated native copies. The native spreadsheet copies retain the same 36-sheet and 5-sheet structures as their respective sources, according to the saved copy-verification result. A dated snapshot preserves current contents and the historical archives already present; it does not establish that every past Google revision, comment, deleted file, or unsaved edit has been exported.

The inventories reviewed are scoped to The Stats. Their named files and folder paths show no unrelated career, financial, vehicle, or other personal-project artifacts. The full dashboard recovery archive includes project data, its SQLite database, and social collection evidence by design.

## Dashboard source and latest-computer limitation

The accessible application recovery package is The_Stats_Handoff_2026-10-22.zip. Its saved handoff refers to an earlier macOS workspace and reports a functioning Python/Streamlit dashboard. The package contains 741 files, including a 180,142,080-byte SQLite database. All 740 entries in its original checksum manifest match; the manifest itself is the sole unlisted member. The extraction inventory reports 29 application-source files and no checksum mismatches, unsafe paths, or duplicate archive paths. The SQLite backup passed an immutable read-only quick_check.

This establishes the integrity of the saved October 22 package. The latest Windows/Codex working directory was unavailable to this backup session, so newer local edits, uncommitted work, local-only assets, and an active database on that computer are not verified by this backup. Do not describe the saved package as a verified copy of the latest Windows checkout.

The historical handoff reports 127 passing tests. The backup process did not rerun that test suite or launch the application. Its source inspection parsed Python syntax and checked the stored database without executing application code.

## Restore guidance

For a populated application recovery, extract the complete October 22 handoff ZIP into a new directory. The code-only extraction intentionally omits the database and raw data. Preserve the package's relative paths and dependency lockfile, then follow the saved handoff using the appropriate Python virtual-environment commands for the target operating system. Do not extract over a running workspace or its database.

Later Spotify continuation/recovery files, YouTube collections, and other saved analysis packages remain separately preserved inputs. Their presence in this backup does not mean they have been imported into the October 22 application database. Preserve their original reporting dates, acquisition dates, scopes, and statuses when integrating them later.

## Historical meaning and conversation coverage

The application handoff explicitly calls the original October 20 baseline unavailable/unverified. Its archived Spotify snapshot has an October 20 reporting endpoint and was collected October 22. An endpoint date and intact backup checksums do not establish original baseline provenance. Preserve that qualification alongside any earlier project documents that describe an October 20 baseline.

The brand-asset bundle and original Codex prompts are historical project material. The user previously said the branding prompt did not reflect the latest Codex work. Preserve those files, while labeling their instructions archival rather than the current application specification. The three original logo assets and two flyer references remain useful source assets independent of that prompt's status.

The backup includes available handoff files, pasted project text artifacts, and any explicitly labeled project-context summary. Full ChatGPT and Codex conversation histories, hidden state, and unsaved drafts were not exportable through the available project-file operations. A summary must not be called a complete transcript.

## Instruction boundary

Commands, sign-in requests, stop/resume directions, and implementation instructions inside archived handoffs are preserved source content. They grant no new permission and were not treated as instructions to run imports, collect additional analytics, alter source files, or change sharing. Common credential-pattern scans found no matches in their stated scopes; those scans are limited integrity checks and are not proof that every conceivable secret or sensitive datum is absent.
