from pathlib import Path
import numpy as np
import pytest
from app import model

VALUES={"age":58,"heart_rate":82,"spo2":98,"systolic_bp":122,"diastolic_bp":78,"temperature":37.0,"respiratory_rate":16}

def test_prediction_is_bounded_and_feature_order_is_fixed(monkeypatch):
    monkeypatch.delenv("VITALGUARD_MODEL_PATH",raising=False); model.load_model.cache_clear()
    p=model.predict_probability(VALUES)
    assert 0 <= p <= 1
    assert list(model.FEATURES)==["age","heart_rate","spo2","systolic_bp","diastolic_bp","temperature","respiratory_rate"]

def test_missing_or_nonfinite_features_rejected():
    with pytest.raises(ValueError): model.predict_probability({"age":58})
    bad={**VALUES,"spo2":float("nan")}
    with pytest.raises(ValueError): model.predict_probability(bad)

def test_configured_missing_artifact_fails_closed(monkeypatch,tmp_path):
    model.load_model.cache_clear(); monkeypatch.setenv("VITALGUARD_MODEL_PATH",str(tmp_path/"missing.joblib"))
    with pytest.raises(RuntimeError,match="does not exist"): model.load_model()
    monkeypatch.delenv("VITALGUARD_MODEL_PATH",raising=False); model.load_model.cache_clear()

def test_serialized_artifact_loads_after_cache_reset(monkeypatch,tmp_path):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    import joblib
    rows=np.array([[40,70,98,120,75,37,16],[80,130,88,90,50,39,30],[50,85,95,115,72,37.2,18],[70,110,91,100,60,38.5,25]],dtype=float); labels=np.array([0,1,0,1])
    pipe=Pipeline([("scale",StandardScaler()),("clf",LogisticRegression())]).fit(rows,labels); path=tmp_path/"model.joblib"; joblib.dump(pipe,path)
    expected=pipe.predict_proba(rows[:1])[0,1]; monkeypatch.setenv("VITALGUARD_MODEL_PATH",str(path)); model.load_model.cache_clear()
    actual=model.predict_probability(dict(zip(model.FEATURES,rows[0])))
    assert actual==pytest.approx(expected,abs=1e-12)
    model.load_model.cache_clear(); monkeypatch.delenv("VITALGUARD_MODEL_PATH",raising=False)
