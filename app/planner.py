"""V2 beam-search scenario planner. All racing response values are demonstration assumptions."""
from time import perf_counter
from pydantic import Field
import numpy as np
from .schemas import StrictModel, State, Policy, Belief, DecisionRequest
from .engine import ACTIONS, PACE_OFFSETS, decide

class Planning(StrictModel):
    stages: int = Field(6,ge=1,le=8)
    stage_s: float = Field(4,ge=1,le=5)
    terminal_buffer_mj: float = Field(.25,ge=0,le=2)
    deployment_budget_mj: float = Field(2.0,gt=0,le=20)
    # Future windows are user/scenario assumptions, never inferred from private telemetry.
    attack_windows: list[bool] = Field(default_factory=lambda:[True]*8,min_length=8,max_length=8)
    switch_cost_s: float = Field(.015,ge=0,le=.5)

class PlanRequest(StrictModel):
    state: State
    policy: Policy = Field(default_factory=Policy)
    belief: Belief = Field(default_factory=Belief)
    planning: Planning = Field(default_factory=Planning)

class CompareRequest(StrictModel):
    request: PlanRequest
    seed: int = Field(7,ge=0,le=1000000)
    ticks: int = Field(15,ge=3,le=30)

NAMES=tuple(ACTIONS)

def plan(body: PlanRequest):
    started=perf_counter()
    s,p,cfg=body.state,body.policy,body.planning
    # Reuse all established freshness/quality/flag gates and the Bayesian update.
    checked=decide(DecisionRequest(state=s,policy=p,belief=body.belief))
    result={'version':'2.0-scenario-mpc','recommendation':'NO_RECOMMENDATION','status':'abstain',
            'reason':checked.reason,'belief':checked.belief.model_dump(),'candidates':[],
            'horizon_s':cfg.stages*cfg.stage_s,'latency_ms':0.,'score_margin_s':0.,
            'constraints_status':'Model policy only; FIA compliance not verified',
            'provenance':checked.provenance,'search':'Beam width 12 per first action; approximate, not globally optimal',
            'uncertainty':'Three assumed pace scenarios; no calibrated overtake probability'}
    if not checked.candidates:
        result['latency_ms']=(perf_counter()-started)*1000;return result
    b=checked.belief;w=np.array([b.slow,b.neutral,b.fast]);v=max(s.own_speed_kph/3.6,1)
    recovery=min(s.recovery_kw,p.max_recovery_kw)
    low_recovery=min(max(0,s.recovery_kw-s.recovery_uncertainty_kw),p.max_recovery_kw)
    # node: gaps, energy, low energy, used deployment, score, path, trace
    start={'gaps':np.full(3,s.gap_s),'energy':s.own_energy_mj,
           'low':max(0,s.own_energy_mj-s.energy_uncertainty_mj),'deployed':0.,
           'score':0.,'path':[],'trace':[]}
    def advance(node,action,k):
        power,response=ACTIONS[action];gap=float(w@node['gaps']);reasons=[]
        if power>p.max_deploy_kw:reasons.append('deployment power cap')
        if action=='ATTACK' and (not 0<gap<=1.5 or not cfg.attack_windows[k]):
            reasons.append('attack window unavailable')
        if action=='DEFEND' and not -1.5<=gap<0:reasons.append('rival not in defence window')
        deployed=node['deployed']+power*cfg.stage_s/1000
        if deployed>cfg.deployment_budget_mj+1e-9:reasons.append('planning-window deployment budget')
        energy=min(p.capacity_mj,node['energy']+(recovery-power)*cfg.stage_s/1000)
        low=min(p.capacity_mj,node['low']+(low_recovery-power)*cfg.stage_s/1000)
        if min(node['low'],low)<p.reserve_mj-1e-9:reasons.append('conservative energy below reserve')
        if k==cfg.stages-1 and low<p.reserve_mj+cfg.terminal_buffer_mj-1e-9:
            reasons.append('terminal energy buffer')
        if reasons:return None,reasons
        own_delta=p.speed_gain_mps_per_kw*(power-40)
        relative=PACE_OFFSETS+response*np.array([0.,1.,3.])-own_delta
        gaps=node['gaps']+relative*cfg.stage_s/v
        mean=float(w@gaps);std=float(np.sqrt(w@((gaps-mean)**2)))
        switches=sum(a!=b for a,b in zip(node['path'],node['path'][1:]))
        if node['path'] and node['path'][-1]!=action:switches+=1
        score=s.gap_s-mean-p.energy_price_s_per_mj*(s.own_energy_mj-energy) \
            -p.uncertainty_penalty*std-cfg.switch_cost_s*switches
        trace={'time_s':(k+1)*cfg.stage_s,'action':action,'energy_mj':energy,
               'conservative_energy_mj':low,'gap_s':mean,'gap_min_s':float(gaps.min()),
               'gap_max_s':float(gaps.max()),'gap_std_s':std}
        return {'gaps':gaps,'energy':energy,'low':low,'deployed':deployed,'score':score,
                'path':node['path']+[action],'trace':node['trace']+[trace]},[]
    for first in NAMES:
        nodes=[start];failure=[]
        for stage in range(cfg.stages):
            expanded=[]
            for node in nodes:
                for action in ([first] if stage==0 else NAMES):
                    next_node,reasons=advance(node,action,stage)
                    if next_node:expanded.append(next_node)
                    else:failure.extend(reasons)
            ranked=sorted(expanded,key=lambda n:n['score'],reverse=True)
            nodes=ranked[:11]
            # Preserve the most energy-rich branch so a feasible conservation path
            # is not pruned merely because it has little short-term progress.
            if ranked:
                safest=max(ranked,key=lambda n:(n['low'],n['score']))
                if not any(n is safest for n in nodes): nodes.append(safest)
                elif len(ranked)>11:nodes.append(ranked[11])
            if not nodes:break
        if nodes and len(nodes[0]['path'])==cfg.stages:
            best=nodes[0]
            result['candidates'].append({'action':first,'valid':True,'score_s':best['score'],
                'sequence':best['path'],'trace':best['trace'],'rejection_reasons':[],
                'energy_mj':best['energy'],'conservative_energy_mj':best['low'],
                'deployment_mj':best['deployed'],'gap_s':float(w@best['gaps'])})
        else:
            result['candidates'].append({'action':first,'valid':False,'score_s':None,
                'sequence':[],'trace':[],'rejection_reasons':sorted(set(failure)),
                'energy_mj':None,'conservative_energy_mj':None,'deployment_mj':None,'gap_s':None})
    feasible=sorted([a for a in result['candidates'] if a['valid']],key=lambda a:a['score_s'],reverse=True)
    if feasible:
        best=feasible[0]
        if len(feasible)>1:result['score_margin_s']=best['score_s']-feasible[1]['score_s']
        result.update(recommendation=best['action'],status='advisory',
            reason=f"{best['action']} starts the best retained {result['horizon_s']:g}s plan. "
                   f"Conservative finish: {best['conservative_energy_mj']:.2f} MJ; "
                   f"required: {p.reserve_mj+cfg.terminal_buffer_mj:.2f} MJ. Execute only after engineer review.")
    else:result['reason']='No complete feasible plan was found in the bounded search. Engineer review required.'
    result['latency_ms']=(perf_counter()-started)*1000
    return result


def compare(body: CompareRequest):
    """Common seeded rival trace; simplified plant differs from forecast coefficient by 10%.
    Demonstrates closed-loop behavior, NOT independent real-world validation.
    """
    started=perf_counter();rng=np.random.default_rng(body.seed)
    environment=np.cumsum(rng.normal(0,.25,body.ticks)) + .2
    rows=[];initial=body.request.state;p=body.request.policy;cfg=body.request.planning
    if initial.track_status!='GREEN' or initial.data_age_s>p.max_data_age_s or initial.quality<p.min_quality or initial.own_speed_kph<30 or initial.own_energy_mj>p.capacity_mj:
        raise ValueError('Comparison requires GREEN, fresh, sufficiently complete input, speed >=30 km/h, and energy within capacity')
    for name in ['Planner','Reserve-aware HOLD','Greedy one-stage']:
        state=initial.model_copy();belief=body.request.belief;trace=[];violations=0;switches=0;prev=None
        for tick in range(body.ticks):
            # Same deterministic rival environment for every controller.
            state=state.model_copy(update={'rival_speed_kph':max(0,min(450,initial.own_speed_kph+float(environment[tick])*3.6)),
                                           'timestamp_s':initial.timestamp_s+tick*cfg.stage_s})
            opts=cfg if name!='Greedy one-stage' else cfg.model_copy(update={'stages':1,'terminal_buffer_mj':0})
            decision=plan(PlanRequest(state=state,policy=p,belief=belief,planning=opts))
            belief=Belief(**decision['belief'])
            action=decision['recommendation']
            if name=='Reserve-aware HOLD':
                low=state.own_energy_mj-state.energy_uncertainty_mj+(min(max(0,state.recovery_kw-state.recovery_uncertainty_kw),p.max_recovery_kw)-40)*cfg.stage_s/1000
                action='HOLD' if low>=p.reserve_mj and p.max_deploy_kw>=40 else 'CONSERVE'
            fallback=action=='NO_RECOMMENDATION'
            if fallback:action='CONSERVE' # Explicit simulator fallback; not issued as an operational recommendation.
            power,response=ACTIONS[action]
            energy=max(0,min(p.capacity_mj,state.own_energy_mj+(min(state.recovery_kw,p.max_recovery_kw)-power)*cfg.stage_s/1000))
            # Independent noise realization and slightly mismatched power response.
            relative=float(environment[tick])+response-0.9*p.speed_gain_mps_per_kw*(power-40)
            gap=state.gap_s+relative*cfg.stage_s/max(initial.own_speed_kph/3.6,1)
            if energy<p.reserve_mj:violations+=1
            if prev and prev!=action:switches+=1
            prev=action
            state=state.model_copy(update={'own_energy_mj':energy,'gap_s':max(-30,min(30,gap))})
            trace.append({'time_s':(tick+1)*cfg.stage_s,'energy_mj':energy,'gap_s':state.gap_s,
                          'action':action,'simulator_fallback':fallback})
        rows.append({'controller':name,'final_energy_mj':state.own_energy_mj,'final_gap_s':state.gap_s,
                     'progress_s':initial.gap_s-state.gap_s,'reserve_violations':violations,
                     'switches':switches,'trace':trace})
    return {'seed':body.seed,'duration_s':body.ticks*cfg.stage_s,'results':rows,
            'latency_ms':(perf_counter()-started)*1000,
            'scope':'Synthetic closed-loop comparison; not real racing accuracy or proof of overtaking.',
            'fallback':'If planner abstains, simulator applies CONSERVE and marks the frame.'}
