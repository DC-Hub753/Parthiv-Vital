"""Additive schema migrations for durable demo observations and event history."""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, inspect, select
from sqlalchemy.engine import Connection
from .storage import _OBSERVATIONS, _EVENTS

SCHEMA_VERSION=2
_MIGRATION_METADATA=MetaData()
_MIGRATIONS=Table("vitalguard_storage_migrations",_MIGRATION_METADATA,
 Column("version",Integer,primary_key=True),Column("applied_at",DateTime(timezone=True),nullable=False),Column("description",String(200),nullable=False))
_REQUIRED={"id","patient_id","created_at","input_json","prediction_json","model_version"}
_REQUIRED_EVENT={"id","event_id","event_type","schema_version","created_at","session_id","observation_id","payload_json","published_at","publish_attempts"}

def _record(connection,version,description):
 connection.execute(_MIGRATIONS.insert().values(version=version,applied_at=datetime.now(timezone.utc),description=description))

def migrate(connection:Connection)->int:
 inspector=inspect(connection); tables=set(inspector.get_table_names())
 if "observations" in tables:
  existing={c["name"] for c in inspector.get_columns("observations")}; missing=_REQUIRED-existing
  if missing: raise RuntimeError("Existing observations table is incompatible; missing columns: "+", ".join(sorted(missing)))
 else: _OBSERVATIONS.create(connection,checkfirst=False)
 inspector=inspect(connection); indexes={i["name"] for i in inspector.get_indexes("observations")}
 for index in _OBSERVATIONS.indexes:
  if index.name not in indexes: index.create(connection,checkfirst=False)
 _MIGRATIONS.create(connection,checkfirst=True)
 current=connection.execute(select(_MIGRATIONS.c.version).order_by(_MIGRATIONS.c.version.desc()).limit(1)).scalar_one_or_none()
 if current is None:
  _record(connection,1,"Create/verify demo observation storage and history index"); current=1
 if current>SCHEMA_VERSION: raise RuntimeError(f"Database schema version {current} is newer than supported version {SCHEMA_VERSION}.")
 if current<1: raise RuntimeError("Unsupported migration ledger state.")
 if current<2:
  _EVENTS.create(connection,checkfirst=True)
  event_columns={c["name"] for c in inspect(connection).get_columns("vitalguard_event_log")}
  missing_events=_REQUIRED_EVENT-event_columns
  if missing_events: raise RuntimeError("Existing event log is incompatible; missing columns: "+", ".join(sorted(missing_events)))
  _record(connection,2,"Add durable event log/outbox for observation-created events")
 else:
  if "vitalguard_event_log" not in set(inspect(connection).get_table_names()): raise RuntimeError("Schema ledger says version 2 but durable event log is missing.")
  event_columns={c["name"] for c in inspect(connection).get_columns("vitalguard_event_log")}
  missing_events=_REQUIRED_EVENT-event_columns
  if missing_events: raise RuntimeError("Existing event log is incompatible; missing columns: "+", ".join(sorted(missing_events)))
 return SCHEMA_VERSION
