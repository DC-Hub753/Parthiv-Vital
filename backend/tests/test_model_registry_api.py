from fastapi.testclient import TestClient
import pytest
from app.main import app

@pytest.fixture
def client(tmp_path,monkeypatch):
 monkeypatch.setenv("VITALGUARD_DB_PATH",str(tmp_path/"test.sqlite3"))
 monkeypatch.delenv("VITALGUARD_MODEL_PATH",raising=False)
 from app import model
 model.load_model.cache_clear()
 with TestClient(app) as c: yield c

def test_active_model_info_is_honest_and_versioned(client):
 r=client.get("/api/v1/model/info"); assert r.status_code==200; body=r.json()
 assert body["mode"]=="synthetic_demo"; assert body["model_version"].startswith("synthetic-logreg"); assert body["clinically_validated"] is False

def test_evaluation_endpoint_does_not_fabricate_metrics(client):
 r=client.get("/api/v1/model/evaluation"); assert r.status_code==200; body=r.json()
 assert body["demo_only"] is True and body["clinically_validated"] is False
 assert body["mode"]=="synthetic_demo"; assert body["candidates"]=={}

def test_missing_configured_artifact_returns_503_not_synthetic_fallback(client,monkeypatch,tmp_path):
 from app import model
 monkeypatch.setenv("VITALGUARD_MODEL_PATH",str(tmp_path/"missing.joblib")); model.load_model.cache_clear()
 payload={"patient_id":"DEMO-001","age":58,"heart_rate":82,"spo2":98,"systolic_bp":122,"diastolic_bp":78,"temperature":37,"respiratory_rate":16}
 response=client.post("/api/v1/risk/predict",json=payload)
 assert response.status_code==503 and response.json()["error"]=="model_unavailable"
 monkeypatch.delenv("VITALGUARD_MODEL_PATH",raising=False); model.load_model.cache_clear()
