from contextlib import asynccontextmanager
import asyncio, logging, os
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .event_broker import broker, publish_after_commit
from .live_events import router as live_events_router
from .model import FEATURES, ModelArtifactError, active_model_metadata, explain, predict_probability, risk_level
from .model_evaluation import evaluation_report
from .schemas import RiskPrediction, VitalInput
from .simulator_routes import router as simulator_router
from .storage import StorageError, initialize_storage, list_events_after, list_observations, list_pending_events, mark_event_published, record_event_attempt, save_observation, storage_status
logger=logging.getLogger(__name__)

async def _outbox_worker():
    """Retry durable events until Redis accepts them; duplicate delivery is expected."""
    while True:
        try:
            if broker.configured and not broker.healthy:
                await broker.ensure_connected()
            if broker.configured and broker.healthy:
                pending=await asyncio.to_thread(list_pending_events,limit=50)
                for event in pending:
                    if await broker.publish(event):
                        await asyncio.to_thread(mark_event_published,event["event_id"])
                    else:
                        await asyncio.to_thread(record_event_attempt,event["event_id"])
        except asyncio.CancelledError: raise
        except Exception: logger.exception("Event outbox dispatch failed; events remain recoverable")
        await asyncio.sleep(max(0.1,min(10.0,float(os.getenv("EVENT_OUTBOX_POLL_SECONDS","1")))))

@asynccontextmanager
async def lifespan(_app:FastAPI):
    try: initialize_storage()
    except StorageError: logger.exception("VitalGuard storage initialization failed")
    await broker.start()
    worker=asyncio.create_task(_outbox_worker(),name="vitalguard-event-outbox")
    try: yield
    finally:
        worker.cancel()
        try: await worker
        except asyncio.CancelledError: pass
        await broker.stop()

app=FastAPI(title="VitalGuard AI Risk Engine",version="0.7.0",description="Synthetic demo API; not clinically validated or for clinical use.",lifespan=lifespan)
app.include_router(simulator_router)
app.include_router(live_events_router)

@app.exception_handler(StorageError)
async def storage_error_handler(_request:Request,_exc:StorageError):
    return JSONResponse(status_code=503,content={"error":"storage_unavailable","message":"Persistence is temporarily unavailable. No successful write is reported.","demo_only":True})
@app.exception_handler(ModelArtifactError)
async def model_artifact_error_handler(_request:Request,_exc:ModelArtifactError):
    return JSONResponse(status_code=503,content={"error":"model_unavailable","message":"Configured model artifact is unavailable or incompatible; no prediction was produced.","demo_only":True})
_default_origins=["http://localhost:5173","http://127.0.0.1:5173","https://vitalguard-ai-g215.onrender.com"]
_origins=os.getenv("CORS_ORIGINS",",".join(_default_origins))
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in _origins.split(",") if x.strip()],allow_credentials=False,allow_methods=["GET","POST","OPTIONS"],allow_headers=["Content-Type","X-Session-ID"])

@app.get("/")
def root(): return {"service":"VitalGuard AI Risk Engine","status":"ok","docs":"/docs","health":"/health","demo_only":True}
@app.get("/health")
def health():
    database=storage_status(); meta=active_model_metadata(); db_ok=database["schema_ready"]
    model_ok=not meta["artifact_configured"] or meta["artifact_available"]
    broker_state={"mode":broker.mode,"configured":broker.configured,"healthy":broker.healthy,"cross_instance_delivery":broker.configured and broker.healthy}
    status="ok" if db_ok and model_ok and broker_state["healthy"] else "degraded"
    payload={"status":status,"api":{"healthy":True},"database":{"healthy":db_ok,"backend":database["backend"],"configured":database["configured"],"schema_version":database["schema_version"],"schema_ready":db_ok},"broker":broker_state,"model_version":meta["model_version"],"model_mode":meta["mode"],"demo_only":True}
    if not db_ok or not model_ok:return JSONResponse(status_code=503,content=payload)
    return payload
@app.get("/api/v1/model/info")
def model_info():
    meta=active_model_metadata()
    return {"name":"VitalGuard risk classifier","model_version":meta["model_version"],"algorithm":meta["algorithm"],"features":list(FEATURES),"model_loading":"versioned external artifact" if meta["artifact_configured"] else "lazy synthetic demo fallback","mode":meta["mode"],"artifact_configured":meta["artifact_configured"],"artifact_available":meta["artifact_available"],"training_data_version":meta.get("training_data_version"),"training_data":"synthetic heuristic labels unless a versioned artifact is configured","demo_only":True,"clinically_validated":False,"clinical_training_verified":meta.get("clinical_training_verified",False)}
@app.get("/api/v1/model/evaluation")
def model_evaluation(): return evaluation_report()
@app.post("/api/v1/risk/predict",response_model=RiskPrediction)
async def predict(payload:VitalInput,request:Request):
    values=payload.model_dump(exclude={"patient_id"}); probability=await asyncio.to_thread(predict_probability,values); score=round(probability*100); meta=active_model_metadata()
    result=RiskPrediction(patient_id=payload.patient_id,risk_score=score,risk_level=risk_level(score),model_probability=round(probability,4),factors=explain(values),model_version=meta["model_version"])
    session_id=request.headers.get("X-Session-ID")
    if session_id and len(session_id)>128: session_id=session_id[:128]
    saved=await asyncio.to_thread(save_observation,payload.patient_id,values,result.model_dump(),session_id=session_id)
    await publish_after_commit(saved["event"])
    return result.model_copy(update={"observation_id":saved["id"],"created_at":saved["created_at"]})
@app.get("/api/v1/observations")
def observation_history(patient_id:str|None=Query(default=None,min_length=1,max_length=64),limit:int=Query(default=50,ge=1,le=100),before_id:int|None=Query(default=None,ge=1)):
    records=list_observations(patient_id=patient_id,limit=limit,before_id=before_id); cursor=records[-1]["id"] if len(records)==limit else None
    return {"items":records,"count":len(records),"limit":limit,"next_before_id":cursor,"demo_only":True,"disclaimer":"Synthetic demonstration records only; not for clinical use."}
@app.get("/api/v1/events")
def event_history(after_seq:int=Query(default=0,ge=0),limit:int=Query(default=100,ge=1,le=500)):
    events=list_events_after(after_seq=after_seq,limit=limit)
    return {"items":events,"count":len(events),"limit":limit,"next_after_seq":events[-1]["event_seq"] if events else after_seq,"demo_only":True,"delivery_semantics":"durable database history; WebSocket notifications are at-least-once and clients must deduplicate event_id"}
