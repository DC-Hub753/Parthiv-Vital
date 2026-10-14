# VitalGuard AI — Risk Engine API

> **Prototype only. Synthetic data. Not for clinical use.**

This FastAPI service loads a configured, trusted model artifact or lazily builds a synthetic logistic-regression fallback on first inference. Model training and benchmarking are offline commands under `ml/`; no training occurs during API import or server startup. It stores submitted demo predictions in the SQLAlchemy-backed `observations` table. No approved clinical dataset is included or presumed available.

## Run locally

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

- Health: http://127.0.0.1:8000/health
- API docs: http://127.0.0.1:8000/docs
- Model information: http://127.0.0.1:8000/api/v1/model/info
- Saved demo history: http://127.0.0.1:8000/api/v1/observations

## Endpoints

- `GET /health` — reports active backend, database configuration, migration version, and schema readiness. Returns 503 when persistence is not ready.
- `GET /api/v1/model/info` — actual active model version, algorithm, feature schema, artifact status, and clinical-validation status.\n- `GET /api/v1/model/evaluation` — configured benchmark manifest and limitations; no fabricated metrics are returned when a manifest is absent.
- `POST /api/v1/risk/predict` — scores and persists a synthetic observation before returning success.
- `GET /api/v1/observations?limit=10` — recent history, bounded to 1–100 records.
- `GET /api/v1/observations?patient_id=DEMO-001` — filter by demo patient.
- `GET /api/v1/observations?before_id=25&limit=10` — cursor-based older history.\n- `GET /api/v1/events?after_seq=0&limit=100` — durable, ascending event history for reconnect recovery.\n- `WS /api/v1/live/events?after_seq=123` — live observation event stream with durable replay.
- `POST /api/v1/demo/observations` — generate and persist a deterministic synthetic observation.

## Model artifact configuration\n\nWithout `VITALGUARD_MODEL_PATH`, the service explicitly runs in `synthetic_demo` mode. To load a trained research artifact, set `VITALGUARD_MODEL_PATH` to a trusted immutable `.joblib` file; keep its generated `manifest.json` beside it or set `VITALGUARD_MODEL_MANIFEST`. Optionally set `VITALGUARD_MODEL_VERSION` to an explicit release identifier. The loader checks probability support and feature count/order, and fails closed with HTTP 503 if a configured artifact is missing or incompatible; it does not silently switch to the synthetic fallback. Artifact deserialization is unsafe for untrusted files.\n\nSee [`../ml/README.md`](../ml/README.md) for the reproducible benchmark commands and [`../ml/artifacts/README.md`](../ml/artifacts/README.md) for immutable versioning and rollback. Logistic regression remains the baseline; Random Forest and optional XGBoost comparisons on synthetic labels are engineering smoke tests only. No algorithm is established as clinically superior until an approved dataset and intended outcome are evaluated.\n\n## Database configuration

The active API uses the SQLAlchemy repository in `backend/app/storage.py`. Hosted deployments must explicitly set `DATABASE_URL` in the backend's private hosting environment to a managed PostgreSQL database. The health endpoint identifies the backend actually selected by the configured URL; verify it reports `database_backend: postgresql`, `database_configured: true`, and `schema_ready: true`. Never infer database selection from an environment-variable name alone.

If `DATABASE_URL` is unset, local development uses file-backed SQLite at `backend/vitalguard_demo.sqlite3` by default, or the path set by `VITALGUARD_DB_PATH`. SQLite is a local/test fallback, not durable hosted storage. Hosted service filesystems can be ephemeral.

The SQLAlchemy engine is reused per process with bounded pool, connection, and statement timeouts. Startup runs an additive migration; requests do not create schema. Observation writes use transactions, non-finite JSON is rejected, history is bounded, and persistence errors return controlled HTTP 503 responses. The standalone `backend/app/store.py` SQLite helper is not used by active API routes; `backend/app/storage.py` is the single active repository.

Never commit database credentials or put them in frontend `VITE_*` variables. Configure `CORS_ORIGINS` to exact permitted browser origins.

## Migration and backup/restore

Read [Phase 1 persistence hardening](../docs/PHASE_1_PERSISTENCE.md) before changing a hosted schema or database. The migration verifies the expected demo `observations` schema and adds its history index. If the existing schema is incompatible, startup fails closed rather than dropping or rewriting data. The active simplified API persists predictions within observation rows; it does not currently integrate older alert, audit, patient, ingestion, or session service modules, so this phase does not claim those unavailable workflows are migrated or integrated.

The backup/restore procedure is documented but has **not** been executed against the hosted database. Rehearse it against a separate scratch database before treating it as verified. Never restore into production as a test.

## Tests

```bash
python -m pip install -r backend/requirements.txt
PYTHONPATH=backend pytest backend/tests -q
```

The repository includes isolated SQLite tests. A passing SQLite suite does not substitute for PostgreSQL integration, hosted restart testing, or a controlled backup/restore rehearsal.

## Important limitations

- All current demo records are synthetic; no real patient dataset is included.
- The classifier is trained on generated synthetic data, not real clinical records.
- Labels are generated from a heuristic and are not clinically validated risk estimates.
- Feature indicators are threshold flags, not causal explanations.
- Do not use this service for diagnosis, triage, treatment, or real patient monitoring.
