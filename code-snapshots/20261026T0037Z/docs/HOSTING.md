# Future private hosting requirements

This document is a deployment plan. No host, paid service, domain, account, firewall rule, or cloud database is created by the local milestone. Local mode is bound to `127.0.0.1` and can run without authentication. Do not publish, proxy, or tunnel that unauthenticated mode.

## Linux runtime and service

Use Python 3.12, install the pinned `requirements.lock.txt` into a new Linux virtual environment, and run the same `app.py`. Windows batch files are conveniences; Python uses `pathlib` and operating-system-aware data defaults. Verify dependency installation and tests on the actual target Linux distribution before deployment; Windows execution alone is not Linux validation.

Provision a non-root service user, an HTTPS reverse proxy with WebSocket support, process supervision, application logs with retention, and a private writable data directory. Keep secrets outside source control. Choose a hosting plan with durable storage; ephemeral container/application filesystems are unsuitable for the database. No container is required.

Set `STATS_MODE=hosted` explicitly. Set `STATS_DATA_DIR` to the mounted persistent local disk directory, `STATS_APPROVED_USERS_FILE` to the protected approved-user JSON file, and `STATS_EXPECTED_ISSUER` to the exact issuer returned by the chosen OIDC provider. Bind the Streamlit service to loopback behind the proxy unless the selected platform supplies an equivalent restricted internal network. Hosted mode must remain active even when its internal service binds to loopback.

Do not use the Windows local launcher for hosting: it intentionally accepts local mode only. Before enabling access, verify the hosted entry point refuses data and import access for missing configuration, missing sign-in, an unapproved identity, a mismatched issuer, and an expired identity.

## Provider sign-in and approved users

Use an OpenID Connect identity provider supported by Streamlit, such as an existing organizational provider or a suitable managed identity provider. Streamlit's provider sign-in identifies the person; the application's approved-user list separately authorizes access. No password database or homemade password flow is included. See [Streamlit authentication documentation](https://docs.streamlit.io/develop/concepts/connections/authentication).

Register the actual private HTTPS application URL and its `/oauth2callback` URL with the selected provider. Configure the provider-issued client ID, client secret, metadata URL, and a strong random cookie secret in the ignored `.streamlit/secrets.toml` or the host's protected secrets mechanism. `.streamlit/secrets.example.toml` contains placeholders only. Never commit real credentials.

Obtain each approved user's verified provider issuer and stable subject identifier, then create the private approved-user JSON outside source control. Do not infer an email address, authorize by display name, or automatically admit every member of a provider/tenant. Confirm the intended roles before hosting; the example suggests one administrator and two viewers, not an established production authorization decision.

| Role | Application permission |
| --- | --- |
| Viewer | Read dashboards and provenance for approved data. No import/commit permission. |
| Admin | Viewer access plus validated data import. No permission to overwrite a sealed baseline. |

The gate runs before database initialization or reporting queries. Hosted access requires complete provider configuration, an explicit nonempty approved list, exact issuer/subject matching, a recognized role, and an unexpired identity. Missing or placeholder configuration fails closed. Test login, logout, expiration, unauthorized-user denial, and both roles with real provider accounts before any production release. Actual provider sign-in is not exercised by a local unauthenticated test.

## Durable storage and simultaneous users

For the approved team on one application instance, SQLite on a durable **local attached disk** is an initial option. The repository opens per-operation connections and uses transactions and a busy timeout; WAL permits concurrent reads while writes remain serialized. Keep transactions short. Do not put the active database on OneDrive, Dropbox, SMB/NFS, or another syncing/network filesystem. Do not run multiple replicas against one shared SQLite file.

Snapshot and duplicate checks are enforced by the storage layer, so a second session cannot silently replace previously imported observations. Test two simultaneous admin imports on the intended host, including duplicate and conflicting submissions, before enabling concurrent administrative use. UI session state contains only temporary choices/previews; SQLite remains authoritative.

If independent replicas, more write traffic, or host-managed relational storage become necessary, implement the repository interface in `stats_app/storage.py` with PostgreSQL (or another justified durable store). Preserve snapshot identities, source hashes/bytes, provenance, missing statuses, transactions, and uniqueness constraints during migration. Plan and test schema migration and rollback; do not rewrite dashboard calculations to talk directly to a new database. A cloud database is not required for local operation.

## Backup and restore

Schedule consistent complete-library backups through the application's `python -m stats_app.backup --bundle-dir <new-backup-directory>` command or an equivalent database-aware snapshot. This includes the writable database, registered archives, every analysis version and the active-version pointer. The `--output` command backs up only local uploads. Do not copy only `stats.sqlite3` while WAL writes may still be active. Encrypt off-host backups, restrict access, define retention and recovery targets, and verify restore on a separate data directory regularly. Include configuration needed for recovery and the exact dependency lock file. Back up credentials separately using the host's approved secret-management process.

On restore, stop writes, preserve the old directory, initialize a fresh data directory from a verified complete library backup, restore protected configuration, then validate integrity, observation counts, source hashes, snapshot protection, and known reporting values. Include `archive_registry.json` and all registered archive databases, raw sources and evidence in durable storage/backups; a local-only SQLite backup omits those archives. Never combine an old WAL file with a restored database. Reopen access only after validation succeeds.

## Deployment acceptance still required

Before a later deployment, verify a fresh Linux install, private HTTPS routing and WebSockets, authentication and role enforcement with the chosen provider, persistent storage across service/host replacement, simultaneous read/import behavior, encrypted backups and a complete restore, dependency vulnerability review, and log redaction. Confirm which of the approved team may administer imports. These are future acceptance tasks; this document is not evidence that they have been performed.
