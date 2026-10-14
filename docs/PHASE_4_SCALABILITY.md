# Phase 4 — Scaling and event delivery

## Current architecture

Each observation request commits the observation and an `observation.created` event to PostgreSQL in the same transaction. The database event log is the durable source of truth; Redis Pub/Sub is only a cross-instance notification transport. Event records include a stable UUID `event_id`, monotonically allocated `event_seq`, `event_type`, `schema_version`, UTC timestamp, optional session ID, observation ID, payload, publish state, and retry count.

- `GET /api/v1/events?after_seq=0&limit=100` returns durable, ascending event history (maximum 500 per page).
- `WS /api/v1/live/events?after_seq=123` streams notifications and replays events after the supplied cursor.
- Clients must deduplicate by `event_id` and use `event_seq` as the durable cursor. Reconnect with the last processed sequence; query HTTP history if any sequence gap is detected.
- Redis Pub/Sub is at-least-once best-effort fan-out, not a durable queue. The database outbox retries events when Redis is unavailable; duplicates can occur when publish succeeds but its database acknowledgement fails. This is intentional and is why client deduplication is mandatory.
- PostgreSQL event allocation takes a short transaction-scoped advisory lock immediately before inserting the outbox row. This serializes event-sequence allocation through commit, preventing a lower sequence from committing after a higher sequence. SQLite serializes its writers. Redis notifications can still arrive out of order across publishers; clients reconcile gaps from durable history and deduplicate by `event_id`/sequence.

## Deployment configuration

For cross-instance delivery, configure a managed Redis-compatible service and set `REDIS_URL` as a private backend environment variable on **every** backend instance. Prefer TLS (`rediss://`) and a least-privilege credential. Optional variables: `EVENT_BROKER_CHANNEL` and `EVENT_OUTBOX_POLL_SECONDS`. Do not put Redis credentials in `VITE_*`, source control, logs, or client code.

If `REDIS_URL` is absent, the process uses `local_single_instance` mode. WebSocket fan-out then reaches only clients connected to the same process; `/health` explicitly reports `cross_instance_delivery: false`. Local fallback is suitable for development, not multi-instance production. If Redis is configured but unhealthy, health reports degraded broker status, event rows remain recoverable, and the outbox worker retries.

The current repository branch does not include the older alert, timeline, or trend route modules referenced in the original gap statement. The implemented event lifecycle currently covers prediction and synthetic-simulator observations; alert-created events must be added when those modules are restored/integrated.

## Resource and failure semantics

- Database connection pools remain bounded by `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, and `DB_POOL_TIMEOUT_SECONDS`; connection and statement timeouts are configured through `DB_CONNECT_TIMEOUT_SECONDS` and `DB_STATEMENT_TIMEOUT_MS`.
- Event-history pages are bounded to 500 events. Observation pages are bounded to 100.
- The outbox is at-least-once; it does not guarantee exactly-once delivery. Do not delete old event history until retention and replay policy are approved.
- Redis Pub/Sub itself does not persist messages. PostgreSQL event history is required for recovery.
- Health separates API, database, and broker status. A healthy API/database with a down configured broker is degraded, not proof of cross-instance delivery.

## Tests and load measurement

Run backend tests:

```bash
python -m pip install -r backend/requirements.txt
PYTHONPATH=backend pytest backend/tests -q
```

Run a synthetic HTTP probe only against a test instance:

```bash
python scripts/load_test.py --base-url http://127.0.0.1:8000 --requests 500 --concurrency 25 --output load-test-results.json
```

The script reports measured throughput, success/error rate, and p50/p95/max latency. For a real cross-instance check, start two already-configured test instances and run `python scripts/multi_instance_smoke.py --instance-a https://test-a.example --instance-b https://test-b.example`. This connects to both WebSockets, writes through instance A, and verifies both receive the same event ID. Replace example URLs with actual test endpoints. Commit or report results only after running the scripts; results depend on instance size, network, database, and broker.

## Multi-instance acceptance test

1. Provision managed PostgreSQL and Redis in a non-production environment.
2. Start two API processes with identical `DATABASE_URL` and `REDIS_URL`, but distinct instance IDs/log streams.
3. Open a WebSocket to each process and submit an observation to instance A.
4. Verify both sockets receive the same `event_id`; duplicates are allowed, missing durable history is not.
5. Stop Redis, submit observations, restore Redis, and verify pending outbox events are replayed. Then reconnect a client with an old `after_seq` and verify durable history catches it up.
6. Run concurrency tests and `scripts/load_test.py`; record the environment and output values. Do not infer production capacity from local tests.

No cross-instance integration or load test is claimed until this procedure has been run with a shared database and broker.
