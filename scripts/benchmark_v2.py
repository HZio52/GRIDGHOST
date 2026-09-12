import json,platform
from pathlib import Path
import numpy as np
from app.planner import PlanRequest,plan,CompareRequest,compare

def main():
    rows=json.loads(Path('data/scenarios.json').read_text())
    request=PlanRequest(**rows[0]['request'])
    for _ in range(10):plan(request)
    times=[plan(request)['latency_ms'] for _ in range(200)]
    comparison=compare(CompareRequest(request=request))
    result={'python':platform.python_version(),'platform':platform.platform(),
      'scope':'200 valid close-fight plans; 10 warmups; single process; no network/source delay',
      'planner':{'n':len(times),'p50_ms':float(np.percentile(times,50)),
                 'p95_ms':float(np.percentile(times,95)),'p99_ms':float(np.percentile(times,99)),
                 'max_ms':max(times)},'simulation':comparison,
      'limitations':'Synthetic evidence only; no real-world prediction accuracy claim.'}
    Path('docs/benchmark_v2.json').write_text(json.dumps(result,indent=2));print(json.dumps(result['planner'],indent=2))
if __name__=='__main__':main()
