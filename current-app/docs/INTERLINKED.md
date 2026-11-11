# INTERLINKED on THIS-MACHINE

INTERLINKED runs this checkout with its `.venv` and an explicit local
`STATS_DATA_DIR` resolved from the fetched `stats-active` catalog entry.
Code and the managed data library have separate ownership and save routes.
MSI saves include managed files; they do not include this development checkout.
Use Git commit/push for code. Leave dated recovery snapshots unchanged.

The reviewed launcher supports `--managed --no-browser --port 8501` for its
private parent process. Stdout contains newline-delimited `stats-managed-v1`
events: `ready` with its exact loopback URL, `error`, and `exit` with `clean`.
Stderr carries application logs. Stdin accepts only `{"action":"stop"}`;
pipe EOF also requests stop. Managed launch refuses a missing explicit local
database, an occupied port, hosted mode, or the wrong Python environment.

INTERLINKED contains the process tree in an owned Windows Job Object and holds
the original Stats cache lock until every descendant exits. A hidden console
enables graceful CTRL_BREAK shutdown. A forced or uncertain exit requires
explicit recovery and a local database integrity check. Browser closure does
not stop Streamlit. No source account synchronization or data promotion occurs.

Stop Stats before Save library to MSI + verify, verification, or release.
Release requires the exact project ID and current saved-content verification;
the separate checkout remains outside its scope. Stats can run alongside the
other project session, and actual library transfers are serialized.
