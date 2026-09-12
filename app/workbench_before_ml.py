import json
from datetime import datetime,timezone
from pathlib import Path
from fastapi import Depends, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .planner import PlanRequest,CompareRequest,plan,compare

ROOT=Path(__file__).resolve().parents[1]

def mount_workbench(app,authorize,store):
    app.mount('/assets',StaticFiles(directory=ROOT/'web'),name='assets')
    @app.get('/',include_in_schema=False)
    def home():return FileResponse(ROOT/'web/index.html')
    @app.get('/v2/scenarios',dependencies=[Depends(authorize)])
    def scenarios():return json.loads((ROOT/'data/scenarios.json').read_text())
    @app.post('/v2/plan',dependencies=[Depends(authorize)])
    def evaluate(body:PlanRequest,save:bool=False,db=Depends(store)):
        result=plan(body)
        if save:
            with db.connect() as c:
                c.execute('CREATE TABLE IF NOT EXISTS evaluations (id INTEGER PRIMARY KEY, created TEXT, input TEXT, output TEXT)')
                cur=c.execute('INSERT INTO evaluations (created,input,output) VALUES (?,?,?)',
                    (datetime.now(timezone.utc).isoformat(),body.model_dump_json(),json.dumps(result)))
                result['evaluation_id']=cur.lastrowid
        return result
    @app.post('/v2/compare',dependencies=[Depends(authorize)])
    def simulation(body:CompareRequest):
        try:return compare(body)
        except ValueError as e:raise HTTPException(422,str(e)) from e
    @app.get('/v2/history',dependencies=[Depends(authorize)])
    def history(limit:int=Query(30,ge=1,le=100),db=Depends(store)):
        with db.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS evaluations (id INTEGER PRIMARY KEY, created TEXT, input TEXT, output TEXT)')
            records=c.execute('SELECT * FROM evaluations ORDER BY id DESC LIMIT ?',(limit,)).fetchall()
        return [{'id':r['id'],'created':r['created'],'input':json.loads(r['input']),
                 'output':json.loads(r['output'])} for r in records]
