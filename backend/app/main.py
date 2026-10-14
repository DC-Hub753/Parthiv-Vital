from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .model import FEATURES, MODEL_VERSION, explain, predict_probability, risk_level
from .schemas import RiskPrediction, VitalInput
from .simulator_routes import router as simulator_router
from .storage import StorageError, initialize_storage, list_observations, save_observation, storage_status

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        initialize_storage()
    except StorageError:
        logger.exception("VitalGuard storage initialization failed")
    yield


app = FastAPI(
    title="VitalGuard AI Risk Engine",
    version="0.5.0",
    description=("Demo API for synthetic observations and risk-signal visualization. "
                 "Not clinically validated and not for clinical use."),
    lifespan=lifespan,
)
app.include_router(simulator_router)


@app.exception_handler(StorageError)
async def storage_error_handler(_request: Request, _exc: StorageError):
    return JSONResponse(status_code=503, content={"error":"storage_unavailable","message":"Persistence is temporarily unavailable. No successful write is reported.","demo_only":True})


_default_origins = ["http://localhost:5173", "http://127.0.0.1:5173", "https://vitalguard-ai-g215.onrender.com"]
_origins = os.getenv("CORS_ORIGINS", ",".join(_default_origins))
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in _origins.split(",") if origin.strip()], allow_credentials=False, allow_methods=["GET","POST","OPTIONS"], allow_headers=["Content-Type"])


@app.get("/")
def root():
    return {"service":"VitalGuard AI Risk Engine","status":"ok","docs":"/docs","health":"/health","demo_only":True}


@app.get("/health")
def health():
    database=storage_status(); healthy=database["schema_ready"]
    payload={"status":"ok" if healthy else "degraded","service":"VitalGuard AI Risk Engine","model_version":MODEL_VERSION,"database_backend":database["backend"],"database_configured":database["configured"],"schema_version":database["schema_version"],"schema_ready":healthy,"demo_only":True}
    if not healthy:
        payload["database_reason"]=database.get("reason","schema is not ready")
        return JSONResponse(status_code=503,content=payload)
    return payload


@app.get("/api/v1/model/info")
def model_info():
    configured=os.getenv("VITALGUARD_MODEL_PATH","").strip()
    artifact_exists=bool(configured and Path(configured).expanduser().is_file())
    return {"name":"VitalGuard risk classifier","model_version":MODEL_VERSION,"algorithm":"StandardScaler + LogisticRegression","features":list(FEATURES),"model_loading":"external joblib artifact" if artifact_exists else "lazy synthetic fallback","artifact_configured":bool(configured),"artifact_available":artifact_exists,"training_data":"synthetic heuristic labels unless an externally trained artifact is configured","demo_only":True,"clinically_validated":False,"clinical_training_verified":False}


@app.post("/api/v1/risk/predict", response_model=RiskPrediction)
def predict(payload: VitalInput):
    values=payload.model_dump(exclude={"patient_id"})
    probability=predict_probability(values); score=round(probability*100)
    result=RiskPrediction(patient_id=payload.patient_id,risk_score=score,risk_level=risk_level(score),model_probability=round(probability,4),factors=explain(values),model_version=MODEL_VERSION)
    saved=save_observation(payload.patient_id,values,result.model_dump())
    return result.model_copy(update={"observation_id":saved["id"],"created_at":saved["created_at"]})


@app.get("/api/v1/observations")
def observation_history(patient_id: str | None=Query(default=None,min_length=1,max_length=64),limit: int=Query(default=50,ge=1,le=100),before_id: int | None=Query(default=None,ge=1)):
    """Return recent saved demo predictions, optionally filtered by demo patient ID."""
    records=list_observations(patient_id=patient_id,limit=limit,before_id=before_id)
    next_cursor=records[-1]["id"] if len(records)==limit else None
    return {"items":records,"count":len(records),"limit":limit,"next_before_id":next_cursor,"demo_only":True,"disclaimer":"Synthetic demonstration records only; not for clinical use."}
