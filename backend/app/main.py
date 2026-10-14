from contextlib import asynccontextmanager
import logging, os
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .model import FEATURES, ModelArtifactError, active_model_metadata, explain, predict_probability, risk_level
from .model_evaluation import evaluation_report
from .schemas import RiskPrediction, VitalInput
from .simulator_routes import router as simulator_router
from .storage import StorageError, initialize_storage, list_observations, save_observation, storage_status
logger=logging.getLogger(__name__)
@asynccontextmanager
async def lifespan(_app:FastAPI):
    try: initialize_storage()
    except StorageError: logger.exception("VitalGuard storage initialization failed")
    yield
app=FastAPI(title="VitalGuard AI Risk Engine",version="0.6.0",description="Synthetic demo API; not clinically validated or for clinical use.",lifespan=lifespan)
app.include_router(simulator_router)
@app.exception_handler(StorageError)
async def storage_error_handler(_request:Request,_exc:StorageError):
    return JSONResponse(status_code=503,content={"error":"storage_unavailable","message":"Persistence is temporarily unavailable. No successful write is reported.","demo_only":True})
@app.exception_handler(ModelArtifactError)
async def model_artifact_error_handler(_request:Request,_exc:ModelArtifactError):
    return JSONResponse(status_code=503,content={"error":"model_unavailable","message":"Configured model artifact is unavailable or incompatible; no prediction was produced.","demo_only":True})
_default_origins=["http://localhost:5173","http://127.0.0.1:5173","https://vitalguard-ai-g215.onrender.com"]
_origins=os.getenv("CORS_ORIGINS",",".join(_default_origins))
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in _origins.split(",") if x.strip()],allow_credentials=False,allow_methods=["GET","POST","OPTIONS"],allow_headers=["Content-Type"])
@app.get("/")
def root(): return {"service":"VitalGuard AI Risk Engine","status":"ok","docs":"/docs","health":"/health","demo_only":True}
@app.get("/health")
def health():
    database=storage_status(); healthy=database["schema_ready"]; meta=active_model_metadata()
    payload={"status":"ok" if healthy and (not meta["artifact_configured"] or meta["artifact_available"]) else "degraded","service":"VitalGuard AI Risk Engine","model_version":meta["model_version"],"model_mode":meta["mode"],"database_backend":database["backend"],"database_configured":database["configured"],"schema_version":database["schema_version"],"schema_ready":healthy,"demo_only":True}
    if not healthy or payload["status"]!="ok": payload["database_reason"]=database.get("reason","configured model artifact is unavailable"); return JSONResponse(status_code=503,content=payload)
    return payload
@app.get("/api/v1/model/info")
def model_info():
    meta=active_model_metadata()
    return {"name":"VitalGuard risk classifier","model_version":meta["model_version"],"algorithm":meta["algorithm"],"features":list(FEATURES),"model_loading":"versioned external artifact" if meta["artifact_configured"] else "lazy synthetic demo fallback","mode":meta["mode"],"artifact_configured":meta["artifact_configured"],"artifact_available":meta["artifact_available"],"training_data_version":meta.get("training_data_version"),"training_data":"synthetic heuristic labels unless a versioned artifact is configured","demo_only":True,"clinically_validated":False,"clinical_training_verified":meta.get("clinical_training_verified",False)}
@app.get("/api/v1/model/evaluation")
def model_evaluation(): return evaluation_report()
@app.post("/api/v1/risk/predict",response_model=RiskPrediction)
def predict(payload:VitalInput):
    values=payload.model_dump(exclude={"patient_id"}); probability=predict_probability(values); score=round(probability*100); meta=active_model_metadata()
    result=RiskPrediction(patient_id=payload.patient_id,risk_score=score,risk_level=risk_level(score),model_probability=round(probability,4),factors=explain(values),model_version=meta["model_version"])
    saved=save_observation(payload.patient_id,values,result.model_dump())
    return result.model_copy(update={"observation_id":saved["id"],"created_at":saved["created_at"]})
@app.get("/api/v1/observations")
def observation_history(patient_id:str|None=Query(default=None,min_length=1,max_length=64),limit:int=Query(default=50,ge=1,le=100),before_id:int|None=Query(default=None,ge=1)):
    records=list_observations(patient_id=patient_id,limit=limit,before_id=before_id); cursor=records[-1]["id"] if len(records)==limit else None
    return {"items":records,"count":len(records),"limit":limit,"next_before_id":cursor,"demo_only":True,"disclaimer":"Synthetic demonstration records only; not for clinical use."}
