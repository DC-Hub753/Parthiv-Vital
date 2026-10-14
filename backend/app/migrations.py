"""Explicit, additive migrations for the demo observation store.

These migrations never drop or rewrite existing data. If an existing observations
table has an incompatible schema, startup fails closed and requires a reviewed
migration rather than silently altering the table.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, inspect, select
from sqlalchemy.engine import Connection

from .storage import _OBSERVATIONS

SCHEMA_VERSION = 1
_MIGRATION_METADATA = MetaData()
_MIGRATIONS = Table(
    "vitalguard_storage_migrations",
    _MIGRATION_METADATA,
    Column("version", Integer, primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False),
    Column("description", String(200), nullable=False),
)

_REQUIRED_OBSERVATION_COLUMNS = {
    "id",
    "patient_id",
    "created_at",
    "input_json",
    "prediction_json",
    "model_version",
}


def migrate(connection: Connection) -> int:
    """Apply safe, additive schema setup and return the current schema version."""
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())

    if "observations" in tables:
        existing = {column["name"] for column in inspector.get_columns("observations")}
        missing = _REQUIRED_OBSERVATION_COLUMNS - existing
        if missing:
            raise RuntimeError(
                "Existing observations table is incompatible with this code; "
                f"missing columns: {', '.join(sorted(missing))}. "
                "No automatic schema alteration was attempted."
            )
    else:
        _OBSERVATIONS.create(connection, checkfirst=False)

    # Index creation is additive and guarded by inspection.
    inspector = inspect(connection)
    indexes = {index["name"] for index in inspector.get_indexes("observations")}
    for index in _OBSERVATIONS.indexes:
        if index.name not in indexes:
            index.create(connection, checkfirst=False)

    _MIGRATIONS.create(connection, checkfirst=True)
    current = connection.execute(
        select(_MIGRATIONS.c.version).order_by(_MIGRATIONS.c.version.desc()).limit(1)
    ).scalar_one_or_none()

    if current is None:
        connection.execute(
            _MIGRATIONS.insert().values(
                version=SCHEMA_VERSION,
                applied_at=datetime.now(timezone.utc),
                description="Create/verify demo observation storage and history index",
            )
        )
        return SCHEMA_VERSION

    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current} is newer than supported version "
            f"{SCHEMA_VERSION}."
        )
    if current < SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current} requires an explicit migration to "
            f"{SCHEMA_VERSION}; no automatic upgrade path is defined."
        )
    return current
