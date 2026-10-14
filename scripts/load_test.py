#!/usr/bin/env python3
"""Small HTTP load probe; emits measured results, never assumed capacity claims."""
import argparse, concurrent.futures, json, statistics, time, urllib.error, urllib.request
from datetime import datetime, timezone

def main():
 p=argparse.ArgumentParser(); p.add_argument("--base-url",default="http://127.0.0.1:8000"); p.add_argument("--requests",type=int,default=200); p.add_argument("--concurrency",type=int,default=10); p.add_argument("--timeout",type=float,default=10); p.add_argument("--output",default="load-test-results.json"); a=p.parse_args()
 if a.requests<1 or a.concurrency<1 or a.concurrency>500: p.error("requests must be positive and concurrency must be 1..500")
 url=a.base_url.rstrip("/")+"/api/v1/risk/predict"
 def one(i):
  body={"patient_id":f"LOAD-DEMO-{i%25:02d}","age":58,"heart_rate":82,"spo2":98,"systolic_bp":122,"diastolic_bp":78,"temperature":37.0,"respiratory_rate":16}
  req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={"Content-Type":"application/json","X-Session-ID":"load-test-session"},method="POST")
  started=time.perf_counter()
  try:
   with urllib.request.urlopen(req,timeout=a.timeout) as response:
    response.read(); return {"latency_ms":(time.perf_counter()-started)*1000,"status":response.status,"error":None}
  except (urllib.error.URLError,TimeoutError,Exception) as exc:
   return {"latency_ms":(time.perf_counter()-started)*1000,"status":None,"error":type(exc).__name__}
 started=time.perf_counter()
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as pool: results=list(pool.map(one,range(a.requests)))
 elapsed=time.perf_counter()-started; latencies=sorted(r["latency_ms"] for r in results); ok=sum(r["status"] is not None and 200<=r["status"]<300 for r in results)
 def percentile(q): return round(latencies[min(len(latencies)-1,max(0,int((len(latencies)-1)*q)))],2)
 report={"measured_at_utc":datetime.now(timezone.utc).isoformat(),"base_url":a.base_url,"requests":a.requests,"concurrency":a.concurrency,"elapsed_seconds":round(elapsed,3),"throughput_requests_per_second":round(a.requests/elapsed,2),"successes":ok,"errors":a.requests-ok,"error_rate":round((a.requests-ok)/a.requests,4),"latency_ms":{"p50":percentile(.50),"p95":percentile(.95),"max":round(max(latencies),2)},"status_codes":{},"error_types":{},"warning":"Environment-specific measurement, not a capacity guarantee. Use only a test deployment and synthetic payloads."}
 for r in results:
  key=str(r["status"]) if r["status"] is not None else "transport_error"; report["status_codes"][key]=report["status_codes"].get(key,0)+1
  if r["error"]: report["error_types"][r["error"]]=report["error_types"].get(r["error"],0)+1
 text=json.dumps(report,indent=2); print(text); open(a.output,"w",encoding="utf-8").write(text+"\n")
if __name__=="__main__":main()
