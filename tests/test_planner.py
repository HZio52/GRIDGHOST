import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.planner import PlanRequest, CompareRequest, Planning, plan, compare
from app.schemas import Policy

@pytest.fixture
def request_body():return PlanRequest(**json.loads(Path('data/scenarios.json').read_text())[0]['request'])

def test_complete_plan_respects_all_energy_constraints(request_body):
    r=plan(request_body);assert r['status']=='advisory'
    for c in r['candidates']:
        if c['valid']:
            assert len(c['sequence'])==6
            assert c['deployment_mj']<=2+1e-9
            assert all(t['conservative_energy_mj']>=.6-1e-9 for t in c['trace'])
            assert c['conservative_energy_mj']>=.85-1e-9

def test_conserve_branch_preserved(request_body):
    request_body.state.own_energy_mj=1.1
    r=plan(request_body)
    assert next(c for c in r['candidates'] if c['action']=='CONSERVE')['valid']

def test_windows_and_terminal_buffer(request_body):
    request_body.planning.attack_windows=[False]*8
    r=plan(request_body)
    assert all('ATTACK' not in c['sequence'] for c in r['candidates'] if c['valid'])
    request_body.planning.terminal_buffer_mj=2
    assert plan(request_body)['status']=='abstain'

@pytest.mark.parametrize('field,value',[('track_status','YELLOW'),('data_age_s',10),('quality',.1)])
def test_invalid_observations_do_not_update_pace(request_body,field,value):
    setattr(request_body.state,field,value)
    r=plan(request_body);assert r['status']=='abstain' and r['belief']['updates']==0

def test_reproducible_comparison(request_body):
    body=CompareRequest(request=request_body,ticks=3)
    a=compare(body);b=compare(body)
    a.pop('latency_ms');b.pop('latency_ms')
    assert a==b and len(a['results'])==3
    assert all(len(r['trace'])==3 for r in a['results'])

def test_planner_output_reproducible(request_body):
    a=plan(request_body);b=plan(request_body)
    a.pop('latency_ms');b.pop('latency_ms');assert a==b

def test_web_and_audit_round_trip(tmp_path,request_body,monkeypatch):
    monkeypatch.delenv('API_KEY',raising=False)
    db=str(tmp_path/'audit.sqlite3')
    with TestClient(create_app(db)) as c:
        assert 'Energy deployment' in c.get('/').text
        assert c.get('/assets/app.js').status_code==200
        assert len(c.get('/v2/scenarios').json())==6
        r=c.post('/v2/plan?save=true',json=request_body.model_dump());assert r.status_code==200
        id=r.json()['evaluation_id']
        history=c.get('/v2/history').json();assert history[0]['id']==id
        assert history[0]['input']['state']==request_body.state.model_dump()
    with TestClient(create_app(db)) as c:assert len(c.get('/v2/history').json())==1

def test_v2_auth_and_validation(tmp_path,monkeypatch):
    monkeypatch.setenv('API_KEY','demo-secret')
    with TestClient(create_app(str(tmp_path/'test.db'))) as c:
        assert c.get('/').status_code==200
        assert c.get('/v2/scenarios').status_code==401
        assert c.get('/v2/scenarios',headers={'X-API-Key':'demo-secret'}).status_code==200
        assert c.post('/v2/plan',json={},headers={'X-API-Key':'demo-secret'}).status_code==422
