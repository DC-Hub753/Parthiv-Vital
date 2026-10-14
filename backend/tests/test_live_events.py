from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
import pytest
from app.main import app
from app.storage import list_events_after, save_observation

@pytest.fixture
def client(tmp_path,monkeypatch):
 monkeypatch.delenv("DATABASE_URL",raising=False)
 monkeypatch.setenv("VITALGUARD_DB_PATH",str(tmp_path/"events.sqlite3"))
 with TestClient(app) as c: yield c

def payload(patient_id="DEMO-EVENT-001"):
 return {"patient_id":patient_id,"age":58,"heart_rate":82,"spo2":98,"systolic_bp":122,"diastolic_bp":78,"temperature":37.0,"respiratory_rate":16}

def test_observation_and_event_are_persisted_together(client):
 response=client.post("/api/v1/risk/predict",json=payload())
 assert response.status_code==200
 events=list_events_after(0,100)
 assert len(events)==1
 event=events[0]
 assert event["event_type"]=="observation.created" and event["schema_version"]==1
 assert event["event_id"] and event["event_seq"]>0 and event["observation_id"]==response.json()["observation_id"]
 assert event["payload"]["patient_id"]=="DEMO-EVENT-001"
 assert event["payload"]["prediction"]["model_version"]==response.json()["model_version"]

def test_event_history_is_ordered_and_cursor_paginated(client):
 for i in range(3):
  response=client.post("/api/v1/risk/predict",json=payload(f"DEMO-{i}")); assert response.status_code==200
 first=client.get("/api/v1/events",params={"after_seq":0,"limit":2})
 assert first.status_code==200 and first.json()["count"]==2
 seqs=[item["event_seq"] for item in first.json()["items"]]
 assert seqs==sorted(seqs) and first.json()["next_after_seq"]==seqs[-1]
 second=client.get("/api/v1/events",params={"after_seq":seqs[-1],"limit":2})
 assert second.json()["count"]==1 and second.json()["items"][0]["event_seq"]>seqs[-1]

def test_websocket_replays_durable_history_after_reconnect(client):
 client.post("/api/v1/risk/predict",json=payload())
 with client.websocket_connect("/api/v1/live/events?after_seq=0") as websocket:
  event=websocket.receive_json()
  ready=websocket.receive_json()
  assert event["event_type"]=="observation.created"
  assert ready["event_type"]=="stream.ready"
  assert ready["broker_mode"] in {"redis_pubsub","local_single_instance"}

def test_concurrent_observations_create_unique_event_ids_and_sequences(client):
 def write(i):
  return client.post("/api/v1/risk/predict",json=payload(f"CONCURRENT-{i}")).status_code
 with ThreadPoolExecutor(max_workers=8) as pool:
  statuses=list(pool.map(write,range(16)))
 assert statuses==[200]*16
 events=list_events_after(0,100)
 assert len(events)==16
 assert len({event["event_id"] for event in events})==16
 assert len({event["event_seq"] for event in events})==16
 assert [event["event_seq"] for event in events]==sorted(event["event_seq"] for event in events)

def test_local_fallback_is_explicitly_single_instance(client):
 health=client.get("/health").json()
 if health["broker"]["mode"]=="local_single_instance":
  assert health["broker"]["cross_instance_delivery"] is False

@pytest.mark.anyio
async def test_redis_broker_publishes_stable_event_payload(monkeypatch):
 from app.event_broker import broker
 class FakeRedis:
  def __init__(self): self.calls=[]
  async def publish(self,channel,payload): self.calls.append((channel,payload)); return 2
 fake=FakeRedis(); original=(broker.redis_url,broker._redis,broker._healthy)
 try:
  broker.redis_url="redis://unit-test"; broker._redis=fake; broker._healthy=True
  event={"event_id":"stable-id","event_seq":7,"event_type":"observation.created","schema_version":1,"created_at":"2026-10-14T00:00:00Z","session_id":None,"observation_id":7,"payload":{}}
  assert await broker.publish(event) is True
  assert fake.calls[0][0]==broker.channel
  assert '"event_id":"stable-id"' in fake.calls[0][1]
 finally:
  broker.redis_url,broker._redis,broker._healthy=original

@pytest.mark.anyio
async def test_configured_broker_failure_is_not_reported_as_published():
 from app.event_broker import broker
 original=(broker.redis_url,broker._redis,broker._healthy)
 try:
  broker.redis_url="redis://unit-test"; broker._redis=None; broker._healthy=False
  assert await broker.publish({"event_id":"pending"}) is False
 finally:
  broker.redis_url,broker._redis,broker._healthy=original
