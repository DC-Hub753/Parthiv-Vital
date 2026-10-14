# VitalGuard AI — Risk Engine API

> **Prototype only. Synthetic data. Not for clinical use.**

This FastAPI service trains a small scikit-learn logistic-regression pipeline at process startup using generated synthetic observations and heuristic-generated labels. It stores submitted demo predictions in SQLite. No real patient dataset is included or loaded.

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

## Example prediction

```bash
curl -X POST http://127.0.0.1:8000/api/v1/risk/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "patient_id": "DEMO-001",
    "age": 58,
    "heart_rate": 82,
    "spo2": 98,
    "systolic_bp": 122,
    "diastolic_bp": 78,
    "temperature": 37.0,
    "respiratory_rate": 16
  }'
```

## Endpoints

- `GET /health` — service health and model version.
- `GET /api/v1/model/info` — algorithm, features and limitations.
- `POST /api/v1/risk/predict` — validates vital observations, predicts a demo risk band, and persists the record.
- `GET /api/v1/observations?limit=10` — list recent demo predictions (limit 1–100).
- `GET /api/v1/observations?patient_id=DEMO-001` — filter by demo patient ID.
- `GET /api/v1/observations?before_id=25&limit=10` — page toward older records using the returned `next_before_id` cursor.

## Storage and deployment

Local development/tests use SQLite. Hosted persistence requires a private `DATABASE_URL` pointing to PostgreSQL. Do not assume PostgreSQL is active just because the API responds: check `GET /health` for `database_backend`, `database_configured`, `schema_version`, and `schema_ready`. A healthy hosted deployment should report PostgreSQL and a ready schema.

The SQLAlchemy engine is reused for the process lifetime and uses bounded pool/connection/statement timeouts. Schema setup runs at startup through an additive versioned migration; request handlers do not create tables. Incompatible existing schemas fail closed instead of being automatically altered. Local SQLite is for development/tests, not a production patient-record store.

See [Phase 1 persistence hardening](../docs/PHASE_1_PERSISTENCE.md) for configuration, migration safety, and an operator-run backup/restore rehearsal. No hosted migration or backup/restore is performed automatically by this code.

Set `CORS_ORIGINS` to a comma-separated list of exact permitted browser origins. The deployed frontend origin is allowed by default.

## Tests

```bash
python -m pip install -r backend/requirements.txt
PYTHONPATH=backend pytest backend/tests -q
```

The tests isolate SQLite in temporary directories. Tests have been added to the repository but must be run in a configured Python environment before claiming they pass.

## Important limitations

- The classifier is trained on generated synthetic data, not real clinical records.
- Labels are generated from a transparent heuristic. Outputs demonstrate software integration; they are not validated estimates of deterioration probability.
- Feature indicators are threshold flags, not causal explanations.
- Do not use this service for diagnosis, triage, treatment, or real patient monitoring.
