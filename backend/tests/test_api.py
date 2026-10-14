from fastapi.testclient import TestClient
import pytest
from app.main import app

@pytest.fixture
def client(tmp_path,monkeypatch):
 monkeypatch.setenv("VITALGUARD_DB_PATH",str(tmp_path/"test.sqlite3"))
 with TestClient(app) as c: yield c

def valid_payload():
 return {"patient_id":"DEMO-001","age":58,"heart_rate":82,"spo2":98,"systolic_bp":122,"diastolic_bp":78,"temperature":37.0,"respiratory_rate":16}

def test_health_endpoint(client):
 response=client.get("/health"); assert response.status_code==200; body=response.json()
 assert body["status"]=="ok" and body["demo_only"] is True
 assert body["database"]["backend"] in {"sqlite","postgresql"} and body["database"]["schema_ready"] is True and body["database"]["schema_version"]==2 and "broker" in body

def test_model_info_is_explicit_about_synthetic_data(client):
 response=client.get("/api/v1/model/info"); assert response.status_code==200; body=response.json()
 assert body["clinically_validated"] is False
 assert "synthetic" in body["training_data"] and body["mode"]=="synthetic_demo"

def test_prediction_is_saved_and_returns_observation_metadata(client):
 response=client.post("/api/v1/risk/predict",json=valid_payload()); assert response.status_code==200; body=response.json()
 assert body["patient_id"]=="DEMO-001" and 0<=body["risk_score"]<=100
 assert body["risk_level"] in {"low","moderate","high","critical"} and 0<=body["model_probability"]<=1
 assert body["demo_only"] is True and isinstance(body["factors"],list) and body["observation_id"]>0 and body["created_at"]
 history=client.get("/api/v1/observations",params={"patient_id":"DEMO-001"})
 assert history.status_code==200 and history.json()["count"]==1
 assert history.json()["items"][0]["id"]==body["observation_id"] and history.json()["items"][0]["inputs"]["spo2"]==98

def test_history_can_filter_patient_and_limit(client):
 client.post("/api/v1/risk/predict",json=valid_payload()); other=valid_payload(); other["patient_id"]="DEMO-002"; client.post("/api/v1/risk/predict",json=other)
 first=client.get("/api/v1/observations",params={"patient_id":"DEMO-001","limit":1})
 assert first.status_code==200 and first.json()["count"]==1 and first.json()["items"][0]["patient_id"]=="DEMO-001"
 all_records=client.get("/api/v1/observations",params={"limit":1})
 assert all_records.json()["count"]==1 and all_records.json()["next_before_id"] is not None

def test_invalid_vitals_are_rejected(client):
 payload=valid_payload(); payload["spo2"]=140
 assert client.post("/api/v1/risk/predict",json=payload).status_code==422

def test_diastolic_pressure_must_be_lower_than_systolic(client):
 payload=valid_payload(); payload["diastolic_bp"]=130
 assert client.post("/api/v1/risk/predict",json=payload).status_code==422

def test_history_limit_is_bounded(client):
 assert client.get("/api/v1/observations",params={"limit":101}).status_code==422

def test_postgres_database_url_is_normalized(monkeypatch):
 from app.storage import _database_url
 monkeypatch.setenv("DATABASE_URL","postgres://demo:secret@localhost:5432/vitalguard")
 assert _database_url()=="postgresql+psycopg://demo:secret@localhost:5432/vitalguard"

def test_configured_sqlite_database_url_is_supported(tmp_path,monkeypatch):
 from app.storage import list_observations,save_observation
 monkeypatch.setenv("DATABASE_URL",f"sqlite:///{tmp_path/'configured.sqlite3'}"); monkeypatch.delenv("VITALGUARD_DB_PATH",raising=False)
 saved=save_observation("DEMO-DB-URL",{"age":58,"spo2":98},{"model_version":"test-model","risk_score":12})
 rows=list_observations(patient_id="DEMO-DB-URL",limit=10)
 assert saved["id"]>0 and len(rows)==1 and rows[0]["inputs"]["spo2"]==98 and rows[0]["prediction"]["risk_score"]==12

def test_storage_failure_returns_controlled_503(client,monkeypatch):
 from app import main
 from app.storage import StorageError
 def fail_write(*_args,**_kwargs): raise StorageError("internal database details must not be exposed")
 monkeypatch.setattr(main,"save_observation",fail_write)
 response=client.post("/api/v1/risk/predict",json=valid_payload())
 assert response.status_code==503 and response.json()["error"]=="storage_unavailable"
 assert "internal database details" not in response.text
