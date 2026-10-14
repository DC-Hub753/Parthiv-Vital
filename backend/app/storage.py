"""Durable SQLAlchemy repository and transactional event outbox."""
from __future__ import annotations
import json, os, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from sqlalchemy import Column, DateTime, Index, Integer, MetaData, String, Table, Text, create_engine, func, insert, inspect, select, update, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

_DEFAULT_DB=Path(__file__).resolve().parents[1]/"vitalguard_demo.sqlite3"
_METADATA=MetaData()
_OBSERVATIONS=Table("observations",_METADATA,
 Column("id",Integer,primary_key=True,autoincrement=True),Column("patient_id",String(64),nullable=False),
 Column("created_at",DateTime(timezone=True),nullable=False,server_default=func.now()),Column("input_json",Text,nullable=False),
 Column("prediction_json",Text,nullable=False),Column("model_version",String(128),nullable=False))
Index("idx_observations_patient_created",_OBSERVATIONS.c.patient_id,_OBSERVATIONS.c.created_at.desc(),_OBSERVATIONS.c.id.desc())
_EVENTS=Table("vitalguard_event_log",_METADATA,
 Column("id",Integer,primary_key=True,autoincrement=True),Column("event_id",String(36),nullable=False,unique=True),
 Column("event_type",String(100),nullable=False),Column("schema_version",Integer,nullable=False),
 Column("created_at",DateTime(timezone=True),nullable=False,server_default=func.now()),
 Column("session_id",String(128),nullable=True),Column("observation_id",Integer,nullable=False),
 Column("payload_json",Text,nullable=False),Column("published_at",DateTime(timezone=True),nullable=True),
 Column("publish_attempts",Integer,nullable=False,server_default="0"))
Index("idx_event_log_observation",_EVENTS.c.observation_id)
Index("idx_event_log_pending",_EVENTS.c.published_at,_EVENTS.c.id)

class StorageError(RuntimeError): """Safe-to-report persistence failure."""
_ENGINE_LOCK=threading.RLock(); _ENGINES:dict[str,Engine]={}; _INITIALIZED_URLS:set[str]=set()

def _database_url()->str:
 configured=os.getenv("DATABASE_URL","").strip()
 if configured:
  if configured.startswith("postgres://"): return "postgresql+psycopg://"+configured[len("postgres://"):]
  if configured.startswith("postgresql://"): return "postgresql+psycopg://"+configured[len("postgresql://"):]
  return configured
 path=os.getenv("VITALGUARD_DB_PATH",str(_DEFAULT_DB))
 if path==":memory:": return "sqlite+pysqlite:///:memory:"
 absolute=Path(path).expanduser().resolve(); absolute.parent.mkdir(parents=True,exist_ok=True)
 return f"sqlite+pysqlite:///{absolute.as_posix()}"

def _engine()->Engine:
 url=_database_url()
 with _ENGINE_LOCK:
  if url in _ENGINES:return _ENGINES[url]
  options:dict[str,Any]={"pool_pre_ping":True,"pool_recycle":1800}
  if url.startswith("sqlite"):
   connect_args={"check_same_thread":False,"timeout":10}
   if url.endswith(":memory:"):options["poolclass"]=StaticPool
  else:
   connect_args={"connect_timeout":int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS","5")),"options":f"-c statement_timeout={int(os.getenv('DB_STATEMENT_TIMEOUT_MS','10000'))}"}
   options.update(pool_size=max(1,int(os.getenv("DB_POOL_SIZE","5"))),max_overflow=max(0,int(os.getenv("DB_MAX_OVERFLOW","5"))),pool_timeout=max(1,int(os.getenv("DB_POOL_TIMEOUT_SECONDS","10"))))
  try:
   engine=create_engine(url,connect_args=connect_args,**options)
   if url.startswith("sqlite"):
    from sqlalchemy import event
    @event.listens_for(engine,"connect")
    def _sqlite_pragmas(dbapi_connection,_connection_record):
     cursor=dbapi_connection.cursor(); cursor.execute("PRAGMA busy_timeout=10000"); cursor.execute("PRAGMA foreign_keys=ON"); cursor.close()
   _ENGINES[url]=engine; return engine
  except (SQLAlchemyError,ValueError) as exc:raise StorageError("Database engine configuration failed.") from exc

def initialize_storage()->None:
 url=_database_url()
 with _ENGINE_LOCK:
  if url in _INITIALIZED_URLS:return
  engine=_engine()
  try:
   from .migrations import migrate
   with engine.begin() as connection:migrate(connection)
   _INITIALIZED_URLS.add(url)
  except Exception as exc:raise StorageError("Database schema initialization failed; see server logs.") from exc

def storage_status()->dict[str,Any]:
 url=_database_url(); parsed=urlsplit(url); backend="postgresql" if parsed.scheme.startswith("postgres") else ("sqlite" if parsed.scheme.startswith("sqlite") else "unknown")
 status={"backend":backend,"configured":bool(os.getenv("DATABASE_URL","").strip()) if backend=="postgresql" else True,"schema_version":None,"schema_ready":False}
 try:
  engine=_engine()
  with engine.connect() as connection:
   inspector=inspect(connection); tables=set(inspector.get_table_names())
   if "observations" not in tables or "vitalguard_storage_migrations" not in tables or "vitalguard_event_log" not in tables:
    status["reason"]="required schema, event log, or migration ledger is missing";return status
   columns={c["name"] for c in inspector.get_columns("observations")}
   if not {"id","patient_id","created_at","input_json","prediction_json","model_version"}.issubset(columns):
    status["reason"]="observations schema is incompatible";return status
   from .migrations import _MIGRATIONS,SCHEMA_VERSION
   version=connection.execute(select(_MIGRATIONS.c.version).order_by(_MIGRATIONS.c.version.desc()).limit(1)).scalar_one_or_none()
   status["schema_version"]=version; status["schema_ready"]=version==SCHEMA_VERSION
   if not status["schema_ready"]:status["reason"]="database migration version is incomplete or unsupported"
 except Exception:status["reason"]="database connection or schema inspection failed"
 return status

def save_observation(patient_id:str,inputs:dict[str,Any],prediction:dict[str,Any],session_id:str|None=None)->dict[str,Any]:
 initialize_storage(); engine=_engine()
 try:
  with engine.begin() as connection:
   observation_id=connection.execute(insert(_OBSERVATIONS).values(patient_id=patient_id,input_json=json.dumps(inputs,separators=(",",":"),allow_nan=False),prediction_json=json.dumps(prediction,separators=(",",":"),allow_nan=False),model_version=prediction["model_version"]).returning(_OBSERVATIONS.c.id)).scalar_one()
   row=connection.execute(select(_OBSERVATIONS).where(_OBSERVATIONS.c.id==observation_id)).mappings().one()
   # Serialize only event allocation/commit on PostgreSQL so an event_seq cursor cannot skip a transaction that commits late.\n   if engine.dialect.name=="postgresql": connection.execute(text("SELECT pg_advisory_xact_lock(734219812)"))\n   event_id=str(uuid.uuid4()); event_payload={"observation_id":observation_id,"patient_id":patient_id,"inputs":inputs,"prediction":prediction}
   event_seq=connection.execute(insert(_EVENTS).values(event_id=event_id,event_type="observation.created",schema_version=1,session_id=session_id,observation_id=observation_id,payload_json=json.dumps(event_payload,separators=(",",":"),allow_nan=False),publish_attempts=0).returning(_EVENTS.c.id)).scalar_one()
  saved=_serialize(row); saved["event"]={"event_id":event_id,"event_type":"observation.created","schema_version":1,"event_seq":event_seq,"session_id":session_id,"created_at":saved["created_at"],"payload":event_payload}
  return saved
 except (SQLAlchemyError,ValueError,KeyError,TypeError) as exc:raise StorageError("Observation and event could not be persisted.") from exc

def list_observations(patient_id:str|None=None,limit:int=50,before_id:int|None=None)->list[dict[str,Any]]:
 if not 1<=limit<=100:raise ValueError("limit must be between 1 and 100")
 initialize_storage(); engine=_engine()
 try:
  query=select(_OBSERVATIONS)
  if patient_id is not None:query=query.where(_OBSERVATIONS.c.patient_id==patient_id)
  if before_id is not None:query=query.where(_OBSERVATIONS.c.id<before_id)
  query=query.order_by(_OBSERVATIONS.c.id.desc()).limit(limit)
  with engine.connect() as connection:rows=connection.execute(query).mappings().all()
  return [_serialize(row) for row in rows]
 except SQLAlchemyError as exc:raise StorageError("Observation history could not be read.") from exc

def list_events_after(after_seq:int=0,limit:int=100)->list[dict[str,Any]]:
 if after_seq<0 or not 1<=limit<=500:raise ValueError("event cursor/limit out of range")
 initialize_storage(); engine=_engine()
 try:
  with engine.connect() as connection:rows=connection.execute(select(_EVENTS).where(_EVENTS.c.id>after_seq).order_by(_EVENTS.c.id.asc()).limit(limit)).mappings().all()
  return [_event_serialize(row) for row in rows]
 except SQLAlchemyError as exc:raise StorageError("Event history could not be read.") from exc

def list_pending_events(limit:int=50)->list[dict[str,Any]]:
 initialize_storage(); engine=_engine()
 try:
  with engine.connect() as connection:rows=connection.execute(select(_EVENTS).where(_EVENTS.c.published_at.is_(None)).order_by(_EVENTS.c.id.asc()).limit(max(1,min(limit,100)))).mappings().all()
  return [_event_serialize(row) for row in rows]
 except SQLAlchemyError as exc:raise StorageError("Pending events could not be read.") from exc

def mark_event_published(event_id:str)->None:
 initialize_storage(); engine=_engine()
 try:
  with engine.begin() as connection:connection.execute(update(_EVENTS).where(_EVENTS.c.event_id==event_id,_EVENTS.c.published_at.is_(None)).values(published_at=datetime.now(timezone.utc),publish_attempts=_EVENTS.c.publish_attempts+1))
 except SQLAlchemyError as exc:raise StorageError("Event publication state could not be updated.") from exc

def record_event_attempt(event_id:str)->None:
 initialize_storage(); engine=_engine()
 try:
  with engine.begin() as connection:connection.execute(update(_EVENTS).where(_EVENTS.c.event_id==event_id,_EVENTS.c.published_at.is_(None)).values(publish_attempts=_EVENTS.c.publish_attempts+1))
 except SQLAlchemyError as exc:raise StorageError("Event retry state could not be updated.") from exc

def _event_serialize(row:Any)->dict[str,Any]:
 created=row["created_at"]
 if hasattr(created,"isoformat"):created=created.isoformat()
 return {"event_seq":row["id"],"event_id":row["event_id"],"event_type":row["event_type"],"schema_version":row["schema_version"],"created_at":created,"session_id":row["session_id"],"observation_id":row["observation_id"],"payload":json.loads(row["payload_json"]),"published":row["published_at"] is not None,"publish_attempts":row["publish_attempts"]}

def _serialize(row:Any)->dict[str,Any]:
 created=row["created_at"]
 if hasattr(created,"isoformat"):created=created.isoformat()
 return {"id":row["id"],"patient_id":row["patient_id"],"created_at":created,"inputs":json.loads(row["input_json"]),"prediction":json.loads(row["prediction_json"]),"model_version":row["model_version"]}
