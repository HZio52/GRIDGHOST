import json,platform,statistics,tempfile
from pathlib import Path
from time import perf_counter
import numpy as np
from fastapi.testclient import TestClient
from app.main import create_app
from app.engine import decide
from app.schemas import DecisionRequest

def summary(xs):
    return {'count':len(xs),'p50_ms':float(np.percentile(xs,50)),
            'p95_ms':float(np.percentile(xs,95)),'p99_ms':float(np.percentile(xs,99)),
            'max_ms':max(xs)}

def main():
    states=json.loads(Path('data/close_fight_s07.json').read_text())['states']
    requests=[DecisionRequest(state=s) for s in states]
    for i in range(50): decide(requests[i%len(requests)])
    engine=[]
    for i in range(1000):
        t=perf_counter();decide(requests[i%len(requests)]);engine.append((perf_counter()-t)*1000)
    api=[]; persisted=[]
    with tempfile.TemporaryDirectory() as d, TestClient(create_app(str(Path(d)/'test.db'))) as c:
        run=c.post('/v1/runs',json={}).json()['id']
        for i in range(200):
            state=dict(states[i%len(states)],timestamp_s=float(i+1))
            t=perf_counter();r=c.post('/v1/decide',json={'state':state});r.raise_for_status()
            api.append((perf_counter()-t)*1000)
            t=perf_counter();r=c.post(f'/v1/runs/{run}/steps',json=state);r.raise_for_status()
            persisted.append((perf_counter()-t)*1000)
    result={'environment':{'python':platform.python_version(),'platform':platform.platform(),
                          'processor':platform.processor() or 'not reported'},
            'method':'Single client; mixed synthetic cases; 50 engine warmups; no external telemetry/network',
            'engine':summary(engine),'in_process_api':summary(api),'in_process_api_with_sqlite':summary(persisted),
            'limitations':'TestClient measures in-process requests, not real HTTP network, driver radio, or source delay.'}
    Path('docs/benchmark.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__': main()
