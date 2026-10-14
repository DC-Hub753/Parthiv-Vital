"""Redis Pub/Sub event fan-out with explicit single-instance fallback.

The SQL outbox is authoritative. Redis messages are at-least-once notifications;
clients deduplicate by event_id and reconcile from the durable event history.
"""
from __future__ import annotations
import asyncio, json, logging, os
from typing import Any
from fastapi import WebSocket
logger=logging.getLogger(__name__)
class EventBroker:
 def __init__(self):
  self.redis_url=os.getenv("REDIS_URL","").strip()
  self.channel=os.getenv("EVENT_BROKER_CHANNEL","vitalguard.events.v1")
  self._redis=None; self._pubsub=None; self._listener=None; self._clients:set[WebSocket]=set()
  self._running=False; self._healthy=False
 @property
 def configured(self)->bool:return bool(self.redis_url)
 @property
 def mode(self)->str:return "redis_pubsub" if self.configured else "local_single_instance"
 @property
 def healthy(self)->bool:return self._healthy if self.configured else True
 async def start(self):
  self._running=True
  if not self.configured:
   self._healthy=True; return
  try:
   from redis.asyncio import Redis
   self._redis=Redis.from_url(self.redis_url,decode_responses=True,socket_connect_timeout=2,socket_timeout=3,health_check_interval=15)
   await self._redis.ping()
   self._pubsub=self._redis.pubsub()
   await self._pubsub.subscribe(self.channel)
   self._healthy=True
   self._listener=asyncio.create_task(self._listen(),name="vitalguard-redis-event-listener")
  except Exception:
   self._healthy=False
   logger.exception("Redis event broker unavailable; cross-instance delivery is degraded")
 async def stop(self):
  self._running=False
  if self._listener:
   self._listener.cancel()
   try:await self._listener
   except asyncio.CancelledError:pass
  if self._pubsub:
   try:await self._pubsub.aclose()
   except Exception:logger.exception("Error closing Redis Pub/Sub")
  if self._redis:
   try:await self._redis.aclose()
   except Exception:logger.exception("Error closing Redis client")
  self._healthy=False
 async def _listen(self):
  while self._running:
   try:
    async for message in self._pubsub.listen():
     if not self._running:break
     if message and message.get("type")=="message":
      try:await self.broadcast_local(json.loads(message["data"]))
      except (json.JSONDecodeError,TypeError):logger.warning("Discarded malformed broker event")
   except asyncio.CancelledError:raise
   except Exception:
    self._healthy=False; logger.exception("Redis event subscription disconnected")
    await asyncio.sleep(1)
    try:
     await self._pubsub.subscribe(self.channel); await self._redis.ping(); self._healthy=True
    except Exception:await asyncio.sleep(2)
 async def subscribe(self,websocket:WebSocket):
  await websocket.accept(); self._clients.add(websocket)
 async def unsubscribe(self,websocket:WebSocket):
  self._clients.discard(websocket)
 async def broadcast_local(self,event:dict[str,Any]):
  dead=[]
  for client in tuple(self._clients):
   try:await client.send_json(event)
   except Exception:dead.append(client)
  for client in dead:self._clients.discard(client)
 async def publish(self,event:dict[str,Any])->bool:
  if self.configured:
   if not self._redis or not self._healthy:return False
   try:
    await self._redis.publish(self.channel,json.dumps(event,separators=(",",":"),allow_nan=False))
    return True
   except Exception:
    self._healthy=False;logger.exception("Redis event publish failed");return False
  await self.broadcast_local(event)
  return True
broker=EventBroker()

async def publish_after_commit(event:dict[str,Any])->None:
 """Best-effort immediate publish after commit; the durable outbox retries Redis failures."""
 from .storage import mark_event_published
 accepted=await broker.publish(event)
 if accepted:
  try: mark_event_published(event["event_id"])
  except Exception: logger.exception("Event reached broker but outbox acknowledgement failed; duplicate retry is possible")
