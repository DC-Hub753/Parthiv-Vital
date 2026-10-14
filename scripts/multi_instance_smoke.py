#!/usr/bin/env python3
"""Verify cross-instance WebSocket fan-out against two already-running test instances."""
import argparse, asyncio, json, time, urllib.request, uuid
import websockets

def post_observation(base_url, patient_id):
 payload={"patient_id":patient_id,"age":58,"heart_rate":82,"spo2":98,"systolic_bp":122,"diastolic_bp":78,"temperature":37.0,"respiratory_rate":16}
 request=urllib.request.Request(base_url.rstrip("/")+"/api/v1/risk/predict",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
 with urllib.request.urlopen(request,timeout=10) as response:return json.loads(response.read())

async def next_event(socket,patient_id,deadline,buffered):
 while time.monotonic()<deadline:
  for event in list(buffered):
   if event.get("event_type")=="observation.created" and event.get("payload",{}).get("patient_id")==patient_id:
    buffered.remove(event); return event
  message=await asyncio.wait_for(socket.recv(),timeout=max(.1,deadline-time.monotonic()))
  event=json.loads(message)
  if event.get("event_type")=="observation.created" and event.get("payload",{}).get("patient_id")==patient_id:return event
 raise TimeoutError("Expected observation event was not delivered before timeout")

async def wait_ready(socket,timeout):
 deadline=time.monotonic()+timeout; buffered=[]
 while time.monotonic()<deadline:
  message=await asyncio.wait_for(socket.recv(),timeout=max(.1,deadline-time.monotonic()))
  event=json.loads(message)
  if event.get("event_type")=="stream.ready":return buffered
  if event.get("event_type")=="observation.created":buffered.append(event)
 raise TimeoutError("WebSocket stream did not become ready")

async def run(a):
 ws_a=a.instance_a.rstrip("/").replace("https://","wss://").replace("http://","ws://")+"/api/v1/live/events?after_seq=0"
 ws_b=a.instance_b.rstrip("/").replace("https://","wss://").replace("http://","ws://")+"/api/v1/live/events?after_seq=0"
 patient="PHASE4-"+uuid.uuid4().hex[:12]
 started=time.monotonic()
 async with websockets.connect(ws_a,open_timeout=a.timeout) as one, websockets.connect(ws_b,open_timeout=a.timeout) as two:
  buffered_a,buffered_b=await asyncio.gather(wait_ready(one,a.timeout),wait_ready(two,a.timeout))
  result=await asyncio.to_thread(post_observation,a.instance_a,patient)
  deadline=time.monotonic()+a.timeout
  event_a,event_b=await asyncio.gather(next_event(one,patient,deadline,buffered_a),next_event(two,patient,deadline,buffered_b))
  report={"instance_a":a.instance_a,"instance_b":a.instance_b,"patient_id":patient,"observation_id":result.get("observation_id"),"event_id_a":event_a.get("event_id"),"event_id_b":event_b.get("event_id"),"same_event_id":event_a.get("event_id")==event_b.get("event_id"),"elapsed_seconds":round(time.monotonic()-started,3),"cross_instance_delivery_verified":event_a.get("event_id")==event_b.get("event_id"),"warning":"Run only against a test deployment with shared PostgreSQL and Redis."}
  print(json.dumps(report,indent=2))
  if not report["cross_instance_delivery_verified"]:raise SystemExit(1)

def main():
 p=argparse.ArgumentParser(); p.add_argument("--instance-a",required=True); p.add_argument("--instance-b",required=True); p.add_argument("--timeout",type=float,default=15); a=p.parse_args()
 asyncio.run(run(a))
if __name__=="__main__":main()
