"""Durable SQLAlchemy repository for synthetic demo predictions.

Hosted deployments must explicitly configure DATABASE_URL to use PostgreSQL.
SQLite is retained for local development and tests only. Schema changes are
handled by versioned, additive migrations; request handlers never create schema.
This prototype must not be used with real patient data.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    insert,
    inspect,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

_DEFAULT_DB = Path(__file__).resolve().parents[1] / "vitalguard_demo.sqlite3"
_METADATA = MetaData()
_OBSERVATIONS = Table(
    "observations",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("patient_id", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("input_json", Text, nullable=False),
    Column("prediction_json", Text, nullable=False),
    Column("model_version", String(128), nullable=False),
)
Index(
    "idx_observations_patient_created",
    _OBSERVATIONS.c.patient_id,
    _OBSERVATIONS.c.created_at.desc(),
    _OBSERVATIONS.c.id.desc(),
)

class StorageError(RuntimeError):
    """Safe-to-report storage failure; original details stay in server logs."""


_ENGINE_LOCK = threading.RLock()
_ENGINES: dict[str, Engine] = {}
_INITIALIZED_URLS: set[str] = set()


def _database_url() -> str:
    """Prefer hosted DATABASE_URL; use a file-backed SQLite DB for local work."""
    configured = os.getenv("DATABASE_URL", "").strip()
    if configured:
        if configured.startswith("postgres://"):
            return "postgresql+psycopg://" + configured[len("postgres://") :]
        if configured.startswith("postgresql://"):
            return "postgresql+psycopg://" + configured[len("postgresql://") :]
        return configured

    path = os.getenv("VITALGUARD_DB_PATH", str(_DEFAULT_DB))
    if path == ":memory:":
        return "sqlite+pysqlite:///:memory:"
    absolute_path = Path(path).expanduser().resolve()
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+pysqlite:///{absolute_path.as_posix()}"


def _engine() -> Engine:
    """Return a process-reused engine with bounded pool and connection timeouts."""
    url = _database_url()
    with _ENGINE_LOCK:
        if url in _ENGINES:
            return _ENGINES[url]

        connect_args: dict[str, Any]
        options: dict[str, Any] = {"pool_pre_ping": True, "pool_recycle": 1800}
        if url.startswith("sqlite"):
            connect_args = {"check_same_thread": False, "timeout": 10}
            if url.endswith(":memory:"):
                options["poolclass"] = StaticPool
        else:
            connect_args = {
                "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "5")),
                "options": f"-c statement_timeout={int(os.getenv('DB_STATEMENT_TIMEOUT_MS', '10000'))}",
            }
            options.update(
                pool_size=max(1, int(os.getenv("DB_POOL_SIZE", "5"))),
                max_overflow=max(0, int(os.getenv("DB_MAX_OVERFLOW", "5"))),
                pool_timeout=max(1, int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "10"))),
            )

        try:
            engine = create_engine(url, connect_args=connect_args, **options)
            if url.startswith("sqlite"):
                from sqlalchemy import event

                @event.listens_for(engine, "connect")
                def _sqlite_pragmas(dbapi_connection, _connection_record):
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA busy_timeout=10000")
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.close()

            _ENGINES[url] = engine
            return engine
        except (SQLAlchemyError, ValueError) as exc:
            raise StorageError("Database engine configuration failed.") from exc


def initialize_storage() -> None:
    """Apply additive migrations once per configured URL, not on each request."""
    url = _database_url()
    with _ENGINE_LOCK:
        if url in _INITIALIZED_URLS:
            return
        engine = _engine()
        try:
            # Import lazily to avoid a module cycle: migrations share this module's table.
            from .migrations import migrate

            with engine.begin() as connection:
                migrate(connection)
            _INITIALIZED_URLS.add(url)
        except Exception as exc:
            raise StorageError("Database schema initialization failed; see server logs.") from exc


def storage_status() -> dict[str, Any]:
    """Inspect active backend/schema without creating or repairing anything."""
    url = _database_url()
    parsed = urlsplit(url)
    backend = "postgresql" if parsed.scheme.startswith("postgres") else (
        "sqlite" if parsed.scheme.startswith("sqlite") else "unknown"
    )
    status: dict[str, Any] = {
        "backend": backend,
        "configured": bool(os.getenv("DATABASE_URL", "").strip()) if backend == "postgresql" else True,
        "schema_version": None,
        "schema_ready": False,
    }
    try:
        engine = _engine()
        with engine.connect() as connection:
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
            if "observations" not in tables or "vitalguard_storage_migrations" not in tables:
                status["reason"] = "required schema or migration ledger is missing"
                return status
            columns = {column["name"] for column in inspector.get_columns("observations")}
            required = {"id", "patient_id", "created_at", "input_json", "prediction_json", "model_version"}
            if not required.issubset(columns):
                status["reason"] = "observations schema is incompatible"
                return status
            from .migrations import _MIGRATIONS, SCHEMA_VERSION

            version = connection.execute(
                select(_MIGRATIONS.c.version).order_by(_MIGRATIONS.c.version.desc()).limit(1)
            ).scalar_one_or_none()
            status["schema_version"] = version
            status["schema_ready"] = version == SCHEMA_VERSION
            if not status["schema_ready"]:
                status["reason"] = "database migration version is incomplete or unsupported"
    except Exception:
        # Never return DSNs, credentials, hostnames, or driver exception text to clients.
        status["reason"] = "database connection or schema inspection failed"
    return status


def save_observation(
    patient_id: str,
    inputs: dict[str, Any],
    prediction: dict[str, Any],
) -> dict[str, Any]:
    initialize_storage()
    engine = _engine()
    try:
        with engine.begin() as connection:
            observation_id = connection.execute(
                insert(_OBSERVATIONS)
                .values(
                    patient_id=patient_id,
                    input_json=json.dumps(inputs, separators=(",", ":"), allow_nan=False),
                    prediction_json=json.dumps(prediction, separators=(",", ":"), allow_nan=False),
                    model_version=prediction["model_version"],
                )
                .returning(_OBSERVATIONS.c.id)
            ).scalar_one()
            row = connection.execute(
                select(_OBSERVATIONS).where(_OBSERVATIONS.c.id == observation_id)
            ).mappings().one()
        return _serialize(row)
    except (SQLAlchemyError, ValueError, KeyError, TypeError) as exc:
        raise StorageError("Observation could not be persisted.") from exc


def list_observations(
    patient_id: str | None = None,
    limit: int = 50,
    before_id: int | None = None,
) -> list[dict[str, Any]]:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    initialize_storage()
    engine = _engine()
    try:
        query = select(_OBSERVATIONS)
        if patient_id is not None:
            query = query.where(_OBSERVATIONS.c.patient_id == patient_id)
        if before_id is not None:
            query = query.where(_OBSERVATIONS.c.id < before_id)
        query = query.order_by(_OBSERVATIONS.c.id.desc()).limit(limit)
        with engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
        return [_serialize(row) for row in rows]
    except SQLAlchemyError as exc:
        raise StorageError("Observation history could not be read.") from exc


def _serialize(row: Any) -> dict[str, Any]:
    created_at = row["created_at"]
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()
    return {
        "id": row["id"],
        "patient_id": row["patient_id"],
        "created_at": created_at,
        "inputs": json.loads(row["input_json"]),
        "prediction": json.loads(row["prediction_json"]),
        "model_version": row["model_version"],
    }
