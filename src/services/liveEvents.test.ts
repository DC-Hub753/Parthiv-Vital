import { describe, expect, it } from 'vitest';
import { EventCursor, type VitalGuardEvent } from './liveEvents.ts';
const event=(event_id:string,event_seq:number):VitalGuardEvent=>({event_id,event_seq,event_type:'observation.created',schema_version:1,created_at:'2026-10-14T00:00:00Z',session_id:null,observation_id:event_seq,payload:{}});

describe('EventCursor',()=>{
 it('deduplicates broker retries by stable event ID',()=>{
  const cursor=new EventCursor();
  expect(cursor.accept(event('event-a',1))).toBe(true);
  expect(cursor.accept(event('event-a',1))).toBe(false);
  expect(cursor.lastSequence).toBe(1);
 });
 it('retains a monotonic cursor when events arrive out of order',()=>{
  const cursor=new EventCursor(4);
  expect(cursor.accept(event('event-c',9))).toBe(true);
  expect(cursor.accept(event('event-b',7))).toBe(true);
  expect(cursor.lastSequence).toBe(9);
 });
 it('rejects malformed event IDs and sequence values',()=>{
  const cursor=new EventCursor();
  expect(cursor.accept(event('',1))).toBe(false);
  expect(cursor.accept(event('event-zero',0))).toBe(false);
 });
});
