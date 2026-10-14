"""WebSocket event stream; durable recovery is available through the HTTP event history."""
from __future__ import annotations
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from .event_broker import broker
from .storage import list_events_after

router=APIRouter(tags=["live-events"])
@router.websocket("/api/v1/live/events")
async def live_event_stream(websocket:WebSocket):
 try:after_seq=max(0,int(websocket.query_params.get("after_seq","0")))
 except ValueError:after_seq=0
 await broker.subscribe(websocket)
 try:
  # Replay after subscribing to avoid a replay/subscribe gap. Duplicate delivery is
  # expected at the boundary; event_id/event_seq are stable dedupe keys.
  events=list_events_after(after_seq=after_seq,limit=500)
  for event in events:await websocket.send_json(event)
  await websocket.send_json({"event_type":"stream.ready","schema_version":1,"after_seq":after_seq,"broker_mode":broker.mode,"cross_instance_delivery":broker.configured and broker.healthy})
  while True: await websocket.receive_text()
 except WebSocketDisconnect:pass
 except Exception:
  # Storage or socket failures terminate this connection; clients reconnect and
  # reconcile via after_seq against the durable HTTP endpoint.
  pass
 finally:await broker.unsubscribe(websocket)
