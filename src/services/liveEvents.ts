import { APP_CONFIG } from './config.ts';

export interface LiveEvent {
  event_id: string; event_seq: number; event_type: string; schema_version: number;
  created_at: string; session_id: string | null; observation_id: number; payload: Record<string, unknown>;
}
export type VitalGuardEvent = LiveEvent;
interface EventPage { items: LiveEvent[]; count: number; next_after_seq: number }
export type LiveState = 'connecting' | 'connected' | 'reconnecting' | 'degraded' | 'closed';
export class EventCursor {
 private cursor:number; private readonly seen=new Set<string>();
 constructor(initialSequence=0){this.cursor=Math.max(0,initialSequence);}
 get lastSequence():number{return this.cursor;}
 accept(event:LiveEvent):boolean{
  if(!event.event_id||!Number.isSafeInteger(event.event_seq)||event.event_seq<1||event.event_seq<=this.cursor||this.seen.has(event.event_id))return false;
  this.seen.add(event.event_id); this.cursor=Math.max(this.cursor,event.event_seq);
  if(this.seen.size>5000){const keep=[...this.seen].slice(-2500);this.seen.clear();keep.forEach(id=>this.seen.add(id));}
  return true;
 }
}
export function subscribeLiveEvents(onEvent:(event:LiveEvent)=>void,onState?:(state:LiveState)=>void,initialSequence=0):()=>void{
 const cursor=new EventCursor(initialSequence); let socket:WebSocket|undefined; let retryTimer:ReturnType<typeof setTimeout>|undefined;
 let closed=false; let delay=500; let queue=Promise.resolve();
 const deliver=(event:LiveEvent)=>{if(cursor.accept(event))onEvent(event);};
 const reconcile=async()=>{
  let pages=0;
  while(!closed&&pages<20){
   const response=await fetch(`${APP_CONFIG.apiBaseUrl}/api/v1/events?after_seq=${cursor.lastSequence}&limit=500`,{signal:AbortSignal.timeout(8000)});
   if(!response.ok)throw new Error(`Event reconciliation failed (${response.status})`);
   const page=await response.json() as EventPage;
   if(!page.items.length)return;
   page.items.forEach(deliver); pages+=1;
   if(page.items.length<500)return;
  }
 };
 const connect=()=>{
  if(closed)return; onState?.(socket?'reconnecting':'connecting');
  const wsBase=APP_CONFIG.apiBaseUrl.replace(/^http/,'ws');
  socket=new WebSocket(`${wsBase}/api/v1/live/events?after_seq=${cursor.lastSequence}`);
  socket.onopen=()=>{delay=500;onState?.('connected');};
  socket.onmessage=(message)=>{
   queue=queue.then(async()=>{
    const parsed=JSON.parse(String(message.data)) as Partial<LiveEvent>&{event_type?:string};
    if(parsed.event_type==='stream.ready'){try{await reconcile();}catch{onState?.('degraded');}return;}
    if(!parsed.event_id||!Number.isSafeInteger(parsed.event_seq))return;
    const event=parsed as LiveEvent;
    if(event.event_seq>cursor.lastSequence+1){try{await reconcile();}catch{onState?.('degraded');}}
    deliver(event);
   }).catch(()=>onState?.('degraded'));
  };
  socket.onerror=()=>onState?.('degraded');
  socket.onclose=()=>{if(closed)return;onState?.('reconnecting');retryTimer=setTimeout(connect,delay);delay=Math.min(10000,delay*2);};
 };
 connect();
 return()=>{closed=true;if(retryTimer)clearTimeout(retryTimer);socket?.close();onState?.('closed');};
}
// Compatibility wrapper for callers that only need observation event callbacks.
export type LiveStatus = 'connecting' | 'connected' | 'reconnecting' | 'offline';
export function createLiveSocket(onEvent:(event:LiveEvent)=>void,onStatus:(state:LiveStatus)=>void){
 return subscribeLiveEvents(onEvent,(state)=>onStatus(state==='degraded'||state==='closed'?'offline':state));
}
export async function reconcileObservationHistory(afterSequence=0):Promise<EventPage>{
 const response=await fetch(`${APP_CONFIG.apiBaseUrl}/api/v1/events?after_seq=${afterSequence}&limit=500`,{signal:AbortSignal.timeout(8000)});
 if(!response.ok)throw new Error(`History reconciliation failed (${response.status})`);
 return response.json() as Promise<EventPage>;
}
