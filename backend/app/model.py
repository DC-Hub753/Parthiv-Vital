"""Demo risk model with optional separately trained artifact loading.

API startup never trains a model. Set VITALGUARD_MODEL_PATH to a trusted joblib
artifact to load an externally trained model. Without one, a deterministic
synthetic fallback is constructed lazily on first inference; it is not clinical.
"""
from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = ("age", "heart_rate", "spo2", "systolic_bp", "diastolic_bp", "temperature", "respiratory_rate")
MODEL_VERSION = os.getenv("VITALGUARD_MODEL_VERSION", "synthetic-logreg-0.2.0")

def _heuristic_score(rows: np.ndarray) -> np.ndarray:
    age, hr, spo2, sys, dia, temp, rr = rows.T
    score = np.zeros(len(rows), dtype=float)
    score += np.clip(np.abs(hr - 82) - 12, 0, 70) * 0.55
    score += np.clip(96 - spo2, 0, 30) * 4.4
    score += np.clip(105 - sys, 0, 80) * 0.72
    score += np.clip(rr - 18, 0, 35) * 1.5
    score += np.clip(12 - rr, 0, 12) * 1.8
    score += np.clip(np.abs(temp - 37) - 0.5, 0, 5) * 10
    score += np.clip(age - 65, 0, 45) * 0.18
    score += np.clip(55 - dia, 0, 35) * 0.3
    return np.clip(score, 0, 100)

def _training_data(seed: int = 20261010, samples: int = 12000):
    rng = np.random.default_rng(seed)
    rows = np.column_stack([rng.integers(18,101,samples),rng.normal(84,22,samples).clip(35,190),rng.normal(96,3.2,samples).clip(75,100),rng.normal(122,22,samples).clip(65,220),rng.normal(76,13,samples).clip(35,130),rng.normal(37,1,samples).clip(34,42),rng.normal(17,6,samples).clip(5,42)])
    labels = ((_heuristic_score(rows) + rng.normal(0,7,samples)) >= 35).astype(int)
    return rows, labels

def build_model() -> Pipeline:
    """Build only the explicitly labeled synthetic fallback, never at import."""
    rows, labels = _training_data()
    model=Pipeline([("scale",StandardScaler()),("classifier",LogisticRegression(max_iter=1200,class_weight="balanced",random_state=42))])
    model.fit(rows,labels)
    return model

@lru_cache(maxsize=2)
def load_model(artifact_path: str | None = None):
    """Load trusted artifact, or lazily build demo fallback when unset."""
    path = artifact_path or os.getenv("VITALGUARD_MODEL_PATH", "").strip()
    if path:
        artifact=Path(path).expanduser()
        if not artifact.is_file():
            raise RuntimeError("Configured model artifact does not exist; refusing silent fallback.")
        model=joblib.load(artifact)
        if not hasattr(model,"predict_proba"):
            raise RuntimeError("Configured model artifact lacks predict_proba.")
        return model
    return build_model()

# Compatibility alias for code that imported MODEL, but inference remains lazy.
class _LazyModel:
    def predict_proba(self, rows): return load_model().predict_proba(rows)
MODEL = _LazyModel()

def predict_probability(values: dict[str,float]) -> float:
    try: row=np.array([[float(values[name]) for name in FEATURES]],dtype=float)
    except (KeyError,TypeError,ValueError) as exc: raise ValueError("Invalid or missing model feature") from exc
    if not np.isfinite(row).all(): raise ValueError("Model features must be finite")
    probability=float(load_model().predict_proba(row)[0,1])
    if not np.isfinite(probability): raise ValueError("Model produced a non-finite probability")
    return probability

def explain(values: dict[str,float]) -> list[dict[str,object]]:
    """Return rule-based demo indicators, not causal model explanations."""
    candidates=[("spo2",values["spo2"],values["spo2"]<94,"Low oxygen saturation can be a risk signal in this demo."),("heart_rate",values["heart_rate"],values["heart_rate"]<50 or values["heart_rate"]>110,"Heart rate is outside the demo reference band of 50–110 bpm."),("systolic_bp",values["systolic_bp"],values["systolic_bp"]<100,"Low systolic blood pressure can be a risk signal in this demo."),("respiratory_rate",values["respiratory_rate"],values["respiratory_rate"]<10 or values["respiratory_rate"]>22,"Respiratory rate is outside the demo reference band of 10–22/min."),("temperature",values["temperature"],values["temperature"]<36 or values["temperature"]>38,"Temperature is outside the demo reference band of 36–38 °C.")]
    factors=[{"feature":f,"observed_value":round(float(v),1),"direction":"increases-risk","explanation":e} for f,v,flag,e in candidates if flag]
    return factors or [{"feature":"observations","observed_value":0.0,"direction":"decreases-risk","explanation":"No configured demo thresholds were crossed; this does not rule out a medical problem."}]

def risk_level(score: int) -> str:
    if score>=85:return "critical"
    if score>=65:return "high"
    if score>=30:return "moderate"
    return "low"
