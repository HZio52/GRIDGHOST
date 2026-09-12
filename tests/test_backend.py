from concurrent.futures import ThreadPoolExecutor
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.engine import decide,simulate
from app.main import create_app
from app.openf1 import OpenF1Client,normalize
from app.schemas import Belief,DecisionRequest,Policy,State,RunCreate
from app.storage import Store,Conflict

@pytest.fixture
def state():
    return State(timestamp_s=1,own_speed_kph=300,rival_speed_kph=302,gap_s=.7,
                 own_energy_mj=2.4,track_status='GREEN')
@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.delenv('API_KEY',raising=False)
    with TestClient(create_app(str(tmp_path/'test.sqlite3'))) as c: yield c

def test_energy_units_and_worst_case(state):
    c=simulate(state,Policy(),Belief(),'ATTACK')
    assert c.expected_energy_mj == pytest.approx(2.4-(120-10)*8/1000)
    assert c.worst_case_energy_mj == pytest.approx(2.4-.1-(120-5)*8/1000)

def test_initial_breach_not_hidden_by_recovery(state):
    s=state.model_copy(update={'own_energy_mj':.2,'recovery_kw':50})
    o=decide(DecisionRequest(state=s))
    assert o.status=='abstain' and all(not c.valid for c in o.candidates)

def test_low_energy_rejects_attack(state):
    o=decide(DecisionRequest(state=state.model_copy(update={'own_energy_mj':1.2})))
    assert not next(c for c in o.candidates if c.action=='ATTACK').valid
    assert next(c for c in o.candidates if c.action==o.recommendation).worst_case_energy_mj>=.6

@pytest.mark.parametrize('change',[{'data_age_s':6},{'quality':.2},{'track_status':'YELLOW'},
    {'track_status':'UNKNOWN'},{'track_status':'SC'},{'track_status':'RED'},
    {'track_status':'VSC'},{'own_speed_kph':0},{'own_energy_mj':5}])
def test_gates_do_not_update_belief(state,change):
    o=decide(DecisionRequest(state=state.model_copy(update=change)))
    assert o.status=='abstain' and not o.candidates and o.belief.updates==0

def test_deterministic_except_latency(state):
    a=decide(DecisionRequest(state=state)).model_dump(exclude={'engine_latency_ms'})
    b=decide(DecisionRequest(state=state)).model_dump(exclude={'engine_latency_ms'})
    assert a==b

def test_belief_adapts(state):
    b=Belief(); s=state.model_copy(update={'rival_speed_kph':330})
    for _ in range(100): b=decide(DecisionRequest(state=s,belief=b)).belief
    assert b.fast>b.neutral>b.slow
    assert b.fast+b.neutral+b.slow==pytest.approx(1) and b.updates==100

@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1,500])
def test_bad_speed_rejected(state,value):
    with pytest.raises(ValidationError): State(**(state.model_dump()|{'own_speed_kph':value}))

def test_power_cap_and_gap_eligibility(state):
    o=decide(DecisionRequest(state=state,policy=Policy(max_deploy_kw=40)))
    assert o.recommendation in ('HOLD','CONSERVE')
    assert not next(c for c in o.candidates if c.action=='DEFEND').valid

def test_worst_case_reserve_property(state):
    rng=np.random.default_rng(5)
    for _ in range(200):
        s=state.model_copy(update={'own_energy_mj':float(rng.uniform(0,4)),
                                 'recovery_kw':float(rng.uniform(0,100)),
                                 'energy_uncertainty_mj':float(rng.uniform(0,.4))})
        o=decide(DecisionRequest(state=s))
        if o.status=='advisory':
            assert next(c for c in o.candidates if c.action==o.recommendation).worst_case_energy_mj >= .6-1e-9

def test_api_run_persistence_export_duplicate(client,state):
    r=client.post('/v1/runs',json={'name':'demo'}); assert r.status_code==201
    run=r.json()['id']
    r=client.post(f'/v1/runs/{run}/steps',json=state.model_dump()); assert r.status_code==200
    assert r.json()['belief']['updates']==1
    assert client.post(f'/v1/runs/{run}/steps',json=state.model_dump()).status_code==409
    assert len(client.get(f'/v1/runs/{run}/decisions').json())==1
    assert client.get(f'/v1/runs/{run}/export.csv').text.startswith('timestamp_s,')
    assert client.get('/v1/runs/missing').status_code==404

def test_storage_survives_restart(tmp_path,state):
    path=str(tmp_path/'persist.db'); db=Store(path); run=db.create(RunCreate())['id'];db.step(run,state)
    assert Store(path).get(run)['belief']['updates']==1

def test_concurrent_duplicate_is_atomic(tmp_path,state):
    db=Store(str(tmp_path/'parallel.db')); run=db.create(RunCreate())['id']
    def send(_):
        try: db.step(run,state); return 'ok'
        except Conflict: return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(send,range(2)))
    assert sorted(results)==['conflict','ok'] and db.get(run)['belief']['updates']==1

def test_replay_and_validation(client,state):
    assert client.get('/health').status_code==200
    assert client.get('/openapi.json').status_code==200
    r=client.post('/v1/replay',json=client.get('/v1/demo').json());assert r.status_code==200
    assert len(r.json()['decisions'])==12
    assert client.post('/v1/replay',json={'states':[state.model_dump()]*2}).status_code==422
    assert client.post('/v1/decide',json={'state':state.model_dump(),'unknown':1}).status_code==422

def test_auth(client,monkeypatch):
    monkeypatch.setenv('API_KEY','test-key')
    assert client.get('/v1/policy').status_code==401
    assert client.get('/v1/policy',headers={'X-API-Key':'test-key'}).status_code==200

def raw_fixture():
    a='2024-01-01T00:00:00+00:00'; b='2024-01-01T00:00:01+00:00'
    return {'car_data':[{'date':b,'driver_number':1,'speed':300},
                        {'date':a,'driver_number':2,'speed':310}],
            'position':[{'date':a,'driver_number':1,'position':2},
                        {'date':a,'driver_number':2,'position':1}],
            'intervals':[{'date':a,'driver_number':1,'interval':.5}]}

def test_normalizer_no_future_telemetry():
    raw=raw_fixture()
    raw['car_data'].append({'date':'2024-01-01T00:00:02+00:00','driver_number':2,'speed':400})
    rows=normalize(raw,1,2,2.4)['states']
    assert rows[0]['rival_speed_kph']==310 and rows[0]['track_status']=='UNKNOWN'
    assert rows[0]['energy_source']=='simulated' and rows[0]['gap_s']==.5

def test_normalizer_non_adjacent_and_lapped():
    raw=raw_fixture();raw['position'][0]['position']=3
    assert normalize(raw,1,2,2.4)['states']==[]
    raw=raw_fixture();raw['intervals'][0]['interval']='+1 LAP'
    assert normalize(raw,1,2,2.4)['states']==[]

def test_http_adapter_contract():
    def handle(req):
        assert req.url.host=='api.openf1.org' and req.url.params['session_key']=='9159'
        return httpx.Response(200,json=[{'speed':300}])
    client=OpenF1Client(httpx.MockTransport(handle))
    assert client.fetch('car_data',{'session_key':9159})==[{'speed':300}]
    with pytest.raises(ValueError): client.fetch('../bad',{})

def test_http_failure_is_not_synthetic_success():
    client=OpenF1Client(httpx.MockTransport(lambda req:httpx.Response(401)))
    with pytest.raises(httpx.HTTPStatusError): client.fetch('car_data',{})

def test_belief_can_change_action(state):
    state=state.model_copy(update={'rival_speed_kph':300})
    slow=decide(DecisionRequest(state=state,belief=Belief(slow=.98,neutral=.01,fast=.01)))
    fast=decide(DecisionRequest(state=state,belief=Belief(slow=.01,neutral=.01,fast=.98)))
    assert slow.recommendation=='ATTACK' and fast.recommendation=='HOLD'
