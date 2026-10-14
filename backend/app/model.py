"""Inference-only interface for VitalGuard risk models.

Training lives under ml/ and never runs at API import. Without a configured
artifact, this module uses a deterministic synthetic demo fallback lazily.
"""
from __future__ import annotations
import json, os
from functools import lru_cache
from pathlib import Path
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURES=("age","heart_rate","spo2","systolic_bp","diastolic_bp","temperature","respiratory_rate")
SYNTHETIC_MODEL_VERSION="synthetic-logreg-0.3.0"
class ModelArtifactError(RuntimeError):
    """Configured artifact is absent or incompatible; never silently fallback."""

def _heuristic_score(rows):
    age,hr,spo2,sys,dia,temp,rr=rows.T; score=np.zeros(len(rows),dtype=float)
    score+=np.clip(np.abs(hr-82)-12,0,70)*.55; score+=np.clip(96-spo2,0,30)*4.4; score+=np.clip(105-sys,0,80)*.72
    score+=np.clip(rr-18,0,35)*1.5; score+=np.clip(12-rr,0,12)*1.8; score+=np.clip(np.abs(temp-37)-.5,0,5)*10
    score+=np.clip(age-65,0,45)*.18; score+=np.clip(55-dia,0,35)*.3
    return np.clip(score,0,100)
def _training_data(seed=20261010,samples=12000):
    rng=np.random.default_rng(seed)
    rows=np.column_stack([rng.integers(18,101,samples),rng.normal(84,22,samples).clip(35,190),rng.normal(96,3.2,samples).clip(75,100),rng.normal(122,22,samples).clip(65,220),rng.normal(76,13,samples).clip(35,130),rng.normal(37,1,samples).clip(34,42),rng.normal(17,6,samples).clip(5,42)])
    return rows,((_heuristic_score(rows)+rng.normal(0,7,samples))>=35).astype(int)
def build_model():
    """Construct the synthetic fallback lazily; this is not clinical training."""
    rows,labels=_training_data(); pipe=Pipeline([("scale",StandardScaler()),("classifier",LogisticRegression(max_iter=1200,class_weight="balanced",random_state=42))]); pipe.fit(rows,labels); return pipe

def _artifact_path(): return os.getenv("VITALGUARD_MODEL_PATH","").strip()
def _manifest_for(path):
    explicit=os.getenv("VITALGUARD_MODEL_MANIFEST","").strip()
    candidates=[Path(explicit).expanduser()] if explicit else [Path(path).expanduser().parent/"manifest.json"]
    for candidate in candidates:
        if candidate.is_file():
            try:return json.loads(candidate.read_text())
            except (OSError,json.JSONDecodeError): continue
    return {}

@lru_cache(maxsize=4)
def load_model(artifact_path=None):
    path=artifact_path if artifact_path is not None else _artifact_path()
    if path:
        artifact=Path(path).expanduser()
        if not artifact.is_file(): raise ModelArtifactError("Configured model artifact does not exist; refusing silent fallback.")
        try: loaded=joblib.load(artifact)
        except Exception as exc: raise ModelArtifactError("Configured model artifact could not be loaded.") from exc
        if not callable(getattr(loaded,"predict_proba",None)): raise ModelArtifactError("Configured model artifact lacks predict_proba.")
        count=getattr(loaded,"n_features_in_",None)
        if count is not None and int(count)!=len(FEATURES): raise ModelArtifactError("Configured model artifact has an incompatible feature count.")
        names=getattr(loaded,"feature_names_in_",None)
        if names is not None and tuple(str(x) for x in names)!=FEATURES: raise ModelArtifactError("Configured model artifact feature order does not match the API schema.")
        classes=getattr(loaded,"classes_",None)
        if classes is None and hasattr(loaded,"named_steps"): classes=getattr(loaded.named_steps.get("classifier",loaded.named_steps.get("clf")),"classes_",None)
        if classes is not None and set(np.asarray(classes).tolist())!={0,1}: raise ModelArtifactError("Configured model artifact must support binary classes 0 and 1.")
        return loaded
    return build_model()

def active_model_metadata():
    path=_artifact_path()
    if not path:
        return {"model_version":SYNTHETIC_MODEL_VERSION,"algorithm":"StandardScaler + LogisticRegression","mode":"synthetic_demo","artifact_configured":False,"artifact_available":False,"training_data_version":"generated-heuristic-labels","clinical_training_verified":False,"clinically_validated":False}
    artifact=Path(path).expanduser(); manifest=_manifest_for(path); selected=manifest.get("selected_candidate")
    candidates=manifest.get("candidates",{}); candidate=next((name for name,meta in candidates.items() if meta.get("artifact")==artifact.name),None)
    algorithm=candidate or os.getenv("VITALGUARD_MODEL_ALGORITHM",artifact.stem.replace("vitalguard_", ""))
    dataset_version=manifest.get("dataset_version")
    version=os.getenv("VITALGUARD_MODEL_VERSION") or manifest.get("model_version") or f"{algorithm}:{dataset_version or 'unversioned-artifact'}"
    exists=artifact.is_file()
    if exists:
        try: load_model(path)
        except ModelArtifactError: exists=False
    return {"model_version":version,"algorithm":algorithm,"mode":"research_artifact" if exists else "artifact_unavailable","artifact_configured":True,"artifact_available":exists,"training_data_version":dataset_version,"selected_candidate":selected,"clinical_training_verified":bool(manifest.get("clinical_training_verified",False)),"clinically_validated":bool(manifest.get("clinically_validated",False))}

class _LazyModel:
    def predict_proba(self,rows): return load_model().predict_proba(rows)
MODEL=_LazyModel()
def predict_probability(values):
    try: row=np.array([[float(values[name]) for name in FEATURES]],dtype=float)
    except (KeyError,TypeError,ValueError) as exc: raise ValueError("Invalid or missing model feature") from exc
    if not np.isfinite(row).all(): raise ValueError("Model features must be finite")
    probability=float(load_model().predict_proba(row)[0,1])
    if not np.isfinite(probability) or not 0<=probability<=1: raise ValueError("Model produced an invalid probability")
    return probability

def explain(values):
    candidates=[("spo2",values["spo2"],values["spo2"]<94,"Low oxygen saturation can be a risk signal in this demo."),("heart_rate",values["heart_rate"],values["heart_rate"]<50 or values["heart_rate"]>110,"Heart rate is outside the demo reference band of 50–110 bpm."),("systolic_bp",values["systolic_bp"],values["systolic_bp"]<100,"Low systolic blood pressure can be a risk signal in this demo."),("respiratory_rate",values["respiratory_rate"],values["respiratory_rate"]<10 or values["respiratory_rate"]>22,"Respiratory rate is outside the demo reference band of 10–22/min."),("temperature",values["temperature"],values["temperature"]<36 or values["temperature"]>38,"Temperature is outside the demo reference band of 36–38 °C.")]
    factors=[{"feature":f,"observed_value":round(float(v),1),"direction":"increases-risk","explanation":e} for f,v,flag,e in candidates if flag]
    return factors or [{"feature":"observations","observed_value":0.0,"direction":"decreases-risk","explanation":"No configured demo thresholds were crossed; this does not rule out a medical problem."}]
def risk_level(score):
    if score>=85:return "critical"
    if score>=65:return "high"
    if score>=30:return "moderate"
    return "low"
