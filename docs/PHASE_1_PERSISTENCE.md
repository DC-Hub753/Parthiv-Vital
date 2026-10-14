# Phase 1 — Persistence hardening

> Scope: synthetic demo records only. This is not a production clinical record system.

## Changes in this phase

- Reuse a process-wide SQLAlchemy engine instead of creating and disposing an engine for every request.
- Configure bounded PostgreSQL connection, pool, recycle, pre-ping, and statement timeouts. SQLite remains the local/test fallback.
- Use a versioned, additive storage migration. It verifies the existing observation table before proceeding and fails closed if the schema is incompatible; it never drops or rewrites rows.
- Run schema setup at application startup, not on each history read/write.
- Reject non-finite JSON values and keep each observation write in a transaction.
- Bound history page sizes at both API and storage boundaries.
- Return a controlled HTTP 503 for persistence failures, without exposing DSNs or database exception details.
- Make `GET /health` report the active backend, whether PostgreSQL was configured, the schema version, and whether the schema is ready. Health inspection itself does not create or repair schema.

## Environment settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | unset | Private PostgreSQL URL for hosted persistence. Never commit this value. |
| `DB_CONNECT_TIMEOUT_SECONDS` | `5` | PostgreSQL connection timeout. |
| `DB_STATEMENT_TIMEOUT_MS` | `10000` | PostgreSQL statement timeout. |
| `DB_POOL_SIZE` | `5` | SQLAlchemy base pool size. |
| `DB_MAX_OVERFLOW` | `5` | Temporary connections above pool size. |
| `DB_POOL_TIMEOUT_SECONDS` | `10` | Maximum wait for a pooled connection. |
| `VITALGUARD_DB_PATH` | local SQLite file | Local/test SQLite path; not a substitute for hosted durable storage. |

A healthy hosted health response must show `database_backend: "postgresql"`, `database_configured: true`, and `schema_ready: true`. A successful HTTP response alone is not proof of durable hosted persistence.

## Migration safety

The migration is additive and only manages the demo `observations` table and its index. If an existing table does not match the columns expected by this source, startup fails closed and logs the failure; it does not rename, drop, truncate, or automatically alter the table. Review the live schema and prepare a separate migration plus rollback before changing a production schema.

The current `main` application stores each prediction JSON inside an observation. It does not currently expose the previous alert/audit/session service modules that existed in the older backend architecture. This phase does not fabricate replacement schemas or claim those missing modules are integrated; restoring those workflows requires a separate reviewed integration before their migrations can be safely managed by this code.

## Backup and restore rehearsal (operator-run)

Do not run these commands against production without choosing a secure destination and confirming the available database plan/backup options. Keep dump files encrypted and access-restricted; they can contain sensitive records if the dataset changes in the future.

1. Obtain the PostgreSQL connection string from the hosting provider's private database settings. Do not paste it into chat or commit it.
2. Create a custom-format backup to a secure local path:

   ```bash
   pg_dump --format=custom --no-owner --file=vitalguard-phase1.dump "$DATABASE_URL"
   ```

3. Verify the archive is readable:

   ```bash
   pg_restore --list vitalguard-phase1.dump
   ```

4. Restore into a separate, empty scratch database (never the production database):

   ```bash
   pg_restore --no-owner --exit-on-error --dbname="$RESTORE_DATABASE_URL" vitalguard-phase1.dump
   ```

5. Compare table names, migration versions, and row counts for `observations`, `alerts`, `audit_events`, `ingestion_records`, `patients`, and `users`; then run the app's read-only health check and synthetic smoke tests against the scratch database.
6. Record the backup timestamp, dump size, restore result, row-count comparison, and operator. Protect the dump and delete it according to the project's retention policy.

This repository change does not create a backup, execute a restore, change Render environment variables, or run migrations against the hosted database. Those actions need a separate controlled release with a reviewed rollback plan.

## Verification

Run from the repository root:

```bash
python -m pip install -r backend/requirements.txt
PYTHONPATH=backend pytest backend/tests -q
```

Tests should cover the existing API contract plus migration idempotency, persistence after engine reconnect, incompatible-schema fail-closed behavior, finite JSON, bounded pagination, and read-only health inspection. A passing local SQLite suite does not substitute for PostgreSQL integration and hosted restart/restore verification.
