import csv
import io
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from .engine import decide
from .schemas import Belief, Decision, DecisionRequest, Policy, ReplayRequest, RunCreate, State
from .storage import Conflict, Store

ROOT = Path(__file__).resolve().parents[1]

def create_app(db_path=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(db_path or os.getenv('DATABASE_PATH', 'data/strategy.sqlite3'))
        yield

    app = FastAPI(title='Race Strategy Lab', version='2.0.0', lifespan=lifespan,
        description='Educational scenario planner. No car control; no verified FIA compliance. '
                    'Simulated energy and unvalidated response models are explicitly labelled.')
    origins = [s.strip() for s in os.getenv('CORS_ORIGINS', '').split(',') if s.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET','POST'],
                           allow_headers=['Content-Type','X-API-Key'])
    def authorize(x_api_key: str | None = Header(default=None)):
        expected = os.getenv('API_KEY')
        if expected and not secrets.compare_digest(x_api_key or '', expected):
            raise HTTPException(401, 'Invalid API key')
    def store(request: Request): return request.app.state.store

    @app.middleware('http')
    async def timing(request, call_next):
        start = perf_counter()
        response = await call_next(request)
        response.headers['X-Processing-Time-Ms'] = f'{(perf_counter()-start)*1000:.3f}'
        return response

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return Response(json.dumps({'detail':'Run not found'}),status_code=404, media_type='application/json')
    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return Response(json.dumps({'detail':str(exc)}),status_code=409, media_type='application/json')

    @app.get('/health')
    def health(): return {'status':'ok','mode':'educational_mvp'}

    @app.get('/v1/policy', dependencies=[Depends(authorize)])
    def policy(): return {'policy':Policy().model_dump(), 'status':'model_policy; not FIA verified'}

    @app.get('/v1/demo', dependencies=[Depends(authorize)])
    def demo(): return json.loads((ROOT/'data/close_fight_s07.json').read_text())

    @app.post('/v1/decide', response_model=Decision, dependencies=[Depends(authorize)])
    def decision(body: DecisionRequest): return decide(body)

    @app.post('/v1/runs', status_code=201, dependencies=[Depends(authorize)])
    def create_run(body: RunCreate, db=Depends(store)): return db.create(body)

    @app.get('/v1/runs/{run_id}', dependencies=[Depends(authorize)])
    def get_run(run_id: str, db=Depends(store)): return db.get(run_id)

    @app.post('/v1/runs/{run_id}/steps', response_model=Decision, dependencies=[Depends(authorize)])
    def step(run_id: str, body: State, db=Depends(store)): return db.step(run_id, body)

    @app.get('/v1/runs/{run_id}/decisions', dependencies=[Depends(authorize)])
    def history(run_id: str, limit: int=Query(100,ge=1,le=1000),
                offset: int=Query(0,ge=0), db=Depends(store)):
        return db.history(run_id,limit,offset)

    @app.get('/v1/runs/{run_id}/export.csv', dependencies=[Depends(authorize)])
    def export(run_id: str, limit: int=Query(1000,ge=1,le=10000),
               offset: int=Query(0,ge=0), db=Depends(store)):
        rows = db.history(run_id,limit,offset)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(['timestamp_s','recommendation','status','engine_latency_ms','reason'])
        for r in rows:
            o=r['output']; writer.writerow([r['timestamp_s'],o['recommendation'],o['status'],
                                           o['engine_latency_ms'],o['reason']])
        return Response(buffer.getvalue(),media_type='text/csv',
                        headers={'Content-Disposition':'attachment; filename="decisions.csv"'})

    @app.post('/v1/replay', dependencies=[Depends(authorize)])
    def replay(body: ReplayRequest):
        if any(b.timestamp_s <= a.timestamp_s for a,b in zip(body.states,body.states[1:])):
            raise HTTPException(422,'Replay timestamps must strictly increase')
        belief=Belief(); results=[]
        for state in body.states:
            result=decide(DecisionRequest(state=state,policy=body.policy,belief=belief))
            belief=result.belief
            results.append({'timestamp_s':state.timestamp_s,**result.model_dump()})
        return {'mode':'observation_replay; recommendations do not change recorded future',
                'decisions':results}
    from .workbench import mount_workbench
    mount_workbench(app, authorize, store)
    return app

app = create_app()
