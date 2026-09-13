'use strict';
const $=id=>document.getElementById(id);
const stateFields=['own_speed_kph','rival_speed_kph','gap_s','own_energy_mj','data_age_s','track_status'];
let scenarios=[],currentRequest=null,currentResult=null,lastEvaluatedRequest=null,replay=[],replayIndex=0,replayBelief=null,replayPolicy=null,apiKey='',apiSession=false,busy=false,history=[],lastSpokenAction='',lastWasAbstain=false,radio=null,radioVoices={engineer:null,driver:null},engineerTalking=false,noiseNode=null,speechUnlocked=false,circuitViz=null,circuitHotTimer=null,arenaViz=null,flowWalkTimer=null,flowFocus='flow-n-snap';
const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,d=2)=>Number.isFinite(v)?Number(v).toFixed(d):'—';
const CALL_NAME={ATTACK:'COMMIT',DEFEND:'PROBE',HOLD:'HOLD',CONSERVE:'CONSERVE',REASSESS:'NO CALL',NO_RECOMMENDATION:'NO CALL'};
function prettyCall(a){
  const key=String(a||'').trim().replaceAll(' ','_').toUpperCase();
  return CALL_NAME[key]||String(a||'').replaceAll('_',' ');
}
function prettyText(s){
  return String(s||'').replaceAll('NO_RECOMMENDATION','NO CALL').replaceAll('NO RECOMMENDATION','NO CALL').replaceAll('REASSESS','NO CALL').replaceAll('ATTACK','COMMIT').replaceAll('DEFEND','PROBE');
}
function prettyReason(result){
  const r=String((result&&result.reason)||'');
  if(/not confirmed GREEN/i.test(r))return 'Track is not GREEN. Yellow, safety car (SC), virtual safety car (VSC) or red means caution — no deploy call.';
  if(/stale data/i.test(r))return 'This snapshot is too old. A deploy call needs fresh data.';
  if(/ambiguous/i.test(r))return 'The model is not sure enough — the top two calls are too close. No call until the picture is clearer.';
  return prettyText(r);
}
const FLOW_NODE_IDS=['flow-n-snap','flow-n-rival','flow-n-flag','flow-n-age','flow-n-move','flow-n-energy','flow-n-nocall','flow-n-belief','flow-n-model','flow-n-planner','flow-n-shield','flow-n-commit','flow-n-probe','flow-n-hold','flow-n-conserve','flow-n-eng','flow-n-drv','flow-n-fight','flow-n-arena'];
const FLOW_WALK=['flow-n-snap','flow-n-flag','flow-n-age','flow-n-move','flow-n-energy','flow-n-belief','flow-n-model','flow-n-planner','flow-n-shield','__call__','flow-n-eng','flow-n-drv','flow-n-fight','flow-n-arena'];
const FLOW_EDGES=[
  ['flow-e-snap-flag','flow-n-snap','flow-n-flag'],['flow-e-snap-age','flow-n-snap','flow-n-age'],['flow-e-snap-move','flow-n-snap','flow-n-move'],['flow-e-snap-energy','flow-n-snap','flow-n-energy'],
  ['flow-e-rival-belief','flow-n-rival','flow-n-belief'],['flow-e-rival-fight','flow-n-rival','flow-n-fight'],
  ['flow-e-flag-belief','flow-n-flag','flow-n-belief'],['flow-e-age-belief','flow-n-age','flow-n-belief'],['flow-e-move-planner','flow-n-move','flow-n-planner'],['flow-e-energy-shield','flow-n-energy','flow-n-shield'],
  ['flow-e-flag-nocall','flow-n-flag','flow-n-nocall'],['flow-e-age-nocall','flow-n-age','flow-n-nocall'],['flow-e-move-nocall','flow-n-move','flow-n-nocall'],['flow-e-energy-nocall','flow-n-energy','flow-n-nocall'],
  ['flow-e-belief-model','flow-n-belief','flow-n-model'],['flow-e-belief-planner','flow-n-belief','flow-n-planner'],['flow-e-model-planner','flow-n-model','flow-n-planner'],['flow-e-planner-shield','flow-n-planner','flow-n-shield'],
  ['flow-e-shield-commit','flow-n-shield','flow-n-commit'],['flow-e-shield-probe','flow-n-shield','flow-n-probe'],['flow-e-shield-hold','flow-n-shield','flow-n-hold'],['flow-e-shield-conserve','flow-n-shield','flow-n-conserve'],['flow-e-shield-nocall','flow-n-shield','flow-n-nocall'],
  ['flow-e-commit-eng','flow-n-commit','flow-n-eng'],['flow-e-probe-eng','flow-n-probe','flow-n-eng'],['flow-e-hold-eng','flow-n-hold','flow-n-eng'],['flow-e-conserve-eng','flow-n-conserve','flow-n-eng'],['flow-e-nocall-eng','flow-n-nocall','flow-n-eng'],
  ['flow-e-eng-drv','flow-n-eng','flow-n-drv'],['flow-e-drv-fight','flow-n-drv','flow-n-fight'],['flow-e-drv-arena','flow-n-drv','flow-n-arena'],
  ['flow-e-commit-fight','flow-n-commit','flow-n-fight'],['flow-e-probe-fight','flow-n-probe','flow-n-fight'],['flow-e-fight-arena','flow-n-fight','flow-n-arena']
];
const FLOW_META={
  'flow-n-snap':{kicker:'TRIGGER',title:'Race snapshot',goto:'pit',hops:['flow-n-flag','flow-n-age','flow-n-rival'],radio:'Snapshot in. Speed, gap, energy, age, flag.',lead:'Everything starts as one declared picture. The planner does not invent a live feed.',rows:()=>[['Our speed',`${fmt(readCircuitSpeed(),0)} km/h`],['Rival speed',`${fmt(readRivalSpeed(),0)} km/h`],['Gap',`${fmt(readCircuitGap(),2)} s`],['Energy',`${fmt(Number($('own_energy_mj')&&$('own_energy_mj').value),2)} MJ`],['Data age',`${fmt(Number($('data_age_s')&&$('data_age_s').value),1)} s`],['Track',($('track_status')&&$('track_status').value)||'GREEN']]},
  'flow-n-rival':{kicker:'TRIGGER',title:'Rival telemetry',goto:'pit',hops:['flow-n-belief','flow-n-fight'],radio:'Rival in the picture. Gap is lead or lag, not an overtake.',lead:'We only see rival speed and a signed gap. There is no rival battery feed.',rows:()=>[['Rival speed',`${fmt(readRivalSpeed(),0)} km/h`],['Gap',`${fmt(readCircuitGap(),2)} s`],['Relative',readCircuitGap()>0.005?'Rival ahead':readCircuitGap()<-0.005?'Rival behind':'Alongside']]},
  'flow-n-flag':{kicker:'GATE',title:'Track flag',goto:'pit',hops:['flow-n-belief','flow-n-nocall'],radio:'Track not green. No deploy.',lead:'Only GREEN may get a deploy call. Yellow, SC, VSC or red is caution.',rows:()=>[['Now',($('track_status')&&$('track_status').value)||'GREEN'],['Pass',(($('track_status')&&$('track_status').value)||'GREEN')==='GREEN'?'Open':'Blocked'],['Fail hop','NO CALL']]},
  'flow-n-age':{kicker:'GATE',title:'Data age',goto:'pit',hops:['flow-n-belief','flow-n-nocall'],radio:'NO CALL. Data too old.',lead:'A deploy call needs a fresh snapshot. Default limit is 5 seconds.',rows:()=>[['Age',`${fmt(Number($('data_age_s')&&$('data_age_s').value),1)} s`],['Limit','5 s'],['Pass',Number($('data_age_s')&&$('data_age_s').value)<=5?'Open':'Blocked']]},
  'flow-n-move':{kicker:'GATE',title:'Moving-car regime',goto:'pit',hops:['flow-n-planner','flow-n-nocall'],radio:'Outside moving-car regime. No call.',lead:'Parked or crawling cars do not get a race deploy plan.',rows:()=>[['Own speed',`${fmt(readCircuitSpeed(),0)} km/h`],['Floor','30 km/h'],['Pass',readCircuitSpeed()>=30?'Open':'Blocked']]},
  'flow-n-energy':{kicker:'GATE',title:'Energy capacity',goto:'evidence',hops:['flow-n-shield','flow-n-nocall'],radio:'Energy picture unsafe. No deploy.',lead:'Battery must sit in 0–4 MJ. Reserve 0.60 MJ plus spare must remain at plan end.',rows:()=>[['Energy',`${fmt(Number($('own_energy_mj')&&$('own_energy_mj').value),2)} MJ`],['Reserve','0.60 MJ'],['Spare',`${fmt(Number($('terminal_buffer_mj')&&$('terminal_buffer_mj').value),2)} MJ`]]},
  'flow-n-nocall':{kicker:'HOLD',title:'NO CALL',goto:'pit',hops:['flow-n-eng'],radio:'NO CALL. Picture unclear.',roger:'Roger. NO CALL.',lead:'The engineer holds station. Cars may still roll at snapshot pace, but there is no extra deploy.',rows:()=>[['Meaning','No attack, no cover'],['Radio','Engineer first, then driver roger'],['Arena','RACING · no deploy']]},
  'flow-n-belief':{kicker:'MIX',title:'Rival pace mix',goto:'pit',hops:['flow-n-model','flow-n-planner'],radio:'Rival mix updated.',lead:'Three assumed rival paces — slower, matched, faster. Not overtake odds. Not battery.',rows:()=>{const b=currentResult&&currentResult.belief;return b?[['Slower',`${Math.round(b.slow*100)}%`],['Matched',`${Math.round(b.neutral*100)}%`],['Faster',`${Math.round(b.fast*100)}%`]]:[['Mix','Evaluate a snapshot to fill this']];}},
  'flow-n-model':{kicker:'MODEL',title:'Model guess',goto:'evidence',hops:['flow-n-planner','flow-n-nocall'],radio:'NO CALL. Picture unclear.',lead:'Fast first guess of COMMIT / PROBE / HOLD / CONSERVE. If the top two are too close, it sits out. It never skips the energy rules.',rows:()=>[['Role','Suggest a first call'],['Ambiguity','→ NO CALL'],['Shield','Still required']]},
  'flow-n-planner':{kicker:'PLAN',title:'Full planner',goto:'lab',hops:['flow-n-shield'],radio:'Planner scored the four calls.',lead:'Looks several steps ahead. Drops plans that break energy or gap rules. The big word is the next call only.',rows:()=>[['Lookahead',($('horizon')&&$('horizon').textContent)||'24 s'],['Calls','COMMIT · PROBE · HOLD · CONSERVE'],['Lab','Compare vs HOLD-if-low and greedy']]},
  'flow-n-shield':{kicker:'RULES',title:'Energy shield',goto:'evidence',hops:['flow-n-commit','flow-n-probe','flow-n-hold','flow-n-conserve','flow-n-nocall'],radio:'Shield accepted.',lead:'Reserve, spare, finish MJ and max deploy still bind even when the model is confident.',rows:()=>[['Must-keep',($('required')&&$('required').textContent)||'—'],['Safer finish',($('finish')&&$('finish').textContent)||'—'],['Max deploy','120 kW']]},
  'flow-n-commit':{kicker:'120 kW',title:'COMMIT',goto:'arena',hops:['flow-n-eng','flow-n-fight'],radio:'COMMIT. Full deploy.',roger:'Roger. COMMIT.',lead:'Attack window. Full deploy. Arena pace about 114% when the call is live and the track is GREEN.',rows:()=>[['Deploy','120 kW'],['Use when','Rival is there to be passed or a DRS stretch is on'],['Risk','Burns battery · shield can still block']]},
  'flow-n-probe':{kicker:'80 kW',title:'PROBE',goto:'arena',hops:['flow-n-eng','flow-n-fight'],radio:'PROBE. Cover the rival.',roger:'Roger. PROBE.',lead:'Cover. Enough deploy to answer the rival without dumping the pack.',rows:()=>[['Deploy','80 kW'],['Use when','Rival attacks or the gap is unstable'],['Arena pace','About 106%']]},
  'flow-n-hold':{kicker:'40 kW',title:'HOLD',goto:'arena',hops:['flow-n-eng','flow-n-fight'],radio:'HOLD. Stay in the fight.',roger:'Roger. HOLD.',lead:'Stay. Keep the car in the fight with a light deploy. Common when energy is tight.',rows:()=>[['Deploy','40 kW'],['Use when','Low energy or the pass is not on'],['Arena pace','Snapshot speed']]},
  'flow-n-conserve':{kicker:'0 kW',title:'CONSERVE',goto:'arena',hops:['flow-n-eng'],radio:'CONSERVE. Save the battery.',roger:'Roger. CONSERVE.',lead:'Save. No extra deploy. The rival may stretch unless energy was the constraint.',rows:()=>[['Deploy','0 kW'],['Use when','Must-keep energy is at risk'],['Arena pace','About 90%']]},
  'flow-n-eng':{kicker:'ENGINEER',title:'Pit radio out',goto:'pit',hops:['flow-n-drv'],radio:'',lead:'The race engineer speaks first. One short line. Next call only — not the whole plan.',rows:()=>[['Order','Engineer, then driver'],['On save','Both sides of the radio'],['On evaluate','Engineer only if the call changed']]},
  'flow-n-drv':{kicker:'DRIVER',title:'Roger',goto:'pit',hops:['flow-n-fight','flow-n-arena'],radio:'',roger:'Roger. Copy.',lead:'The driver confirms. That is the contract: the call is heard, then the car does it.',rows:()=>[['Line','Roger. <call>.'],['When','After a saved decision, or after the engineer on a changed call'],['Next','Fight the rival or hold station']]},
  'flow-n-fight':{kicker:'RIVAL',title:'Tackle the rival',goto:'arena',hops:['flow-n-commit','flow-n-probe','flow-n-arena'],radio:'Gap is a lead or lag, not a proven overtake.',lead:'Signed gap picks the fight. Plus = rival ahead. Minus = rival behind. COMMIT attacks. PROBE covers. HOLD stays. CONSERVE gives the stretch unless energy is critical.',rows:()=>{const g=readCircuitGap();return [['Gap',`${fmt(g,2)} s`],['Fight',g>0.005?'They are ahead — COMMIT is the pass window, PROBE if they attack first':g<-0.005?'They are behind — PROBE covers, COMMIT extends':'Side by side — HOLD until one of you commits'],['Belief','Slower / matched / faster — not overtake odds']];}},
  'flow-n-arena':{kicker:'ARENA',title:'Cars on track',goto:'arena',hops:['flow-n-commit','flow-n-flag'],radio:'On track. Call sets pace.',lead:'Enter Arena plays the same constraints. GREEN + a real call changes pace. Yellow and SC slow the field. Red stops. Pause freezes the map.',rows:()=>[['COMMIT','114% · 120 kW'],['PROBE','106% · 80 kW'],['HOLD','100% · 40 kW'],['CONSERVE','90% · 0 kW'],['NO CALL','Racing · no extra deploy']]}
};
function liveCallNode(){
  const c=prettyCall(currentResult&&currentResult.recommendation);
  return {COMMIT:'flow-n-commit',PROBE:'flow-n-probe',HOLD:'flow-n-hold',CONSERVE:'flow-n-conserve'}[c]||'flow-n-nocall';
}
function refreshFlowLive(){
  try{
    const el=$('flow-live-call');
    const box=$('flow-toolbar-live')||(el&&el.parentElement);
    const call=prettyCall(currentResult&&currentResult.recommendation)||'NO CALL';
    if(el)el.textContent=call;
    if(box&&box.dataset)box.dataset.call=call;
    if(flowFocus==='flow-n-snap'||flowFocus==='flow-n-fight'||flowFocus==='flow-n-belief')selectFlowNode(flowFocus,true);
  }catch(e){}
}
function selectFlowNode(id,quiet){
  try{
    if(!id||!$(id))return;
    flowFocus=id;
    FLOW_NODE_IDS.forEach(nid=>{
      const el=$(nid);
      if(el&&el.dataset)el.dataset.on=nid===id?'1':'';
    });
    FLOW_EDGES.forEach(row=>{
      const el=$(row[0]);
      if(el&&el.dataset)el.dataset.on=(row[1]===id||row[2]===id)?'1':'';
    });
    const meta=FLOW_META[id];
    if(!meta)return;
    const kick=$('flow-inspect-kicker');
    const title=$('flow-inspect-title');
    const lead=$('flow-inspect-lead');
    if(kick)kick.textContent=meta.kicker;
    if(title)title.textContent=meta.title;
    if(lead)lead.textContent=meta.lead;
    const rows=typeof meta.rows==='function'?meta.rows():[];
    const hops=meta.hops||[];
    let html=`<div class="arena-kv">${rows.map(r=>`<span>${esc(r[0])}</span><strong>${esc(r[1])}</strong>`).join('')}</div>`;
    if(hops.length)html+=`<div class="flow-hops">${hops.map(h=>`<i data-hop="${esc(h)}">${esc((FLOW_META[h]&&FLOW_META[h].title)||h)}</i>`).join('')}</div>`;
    const box=$('flow-inspect');
    if(box)box.innerHTML=html;
    const call=prettyCall(currentResult&&currentResult.recommendation)||'NO CALL';
    const radioEl=$('flow-inspect-radio');
    const line=meta.radio||radioLine(call,prettyReason(currentResult||{}),currentResult&&currentResult.status);
    const roger=meta.roger||`Roger. ${call}.`;
    if(radioEl){
      radioEl.hidden=false;
      radioEl.textContent=`Engineer: ${line}  ·  Driver: ${roger}`;
    }
    const step=$('flow-step');
    if(step&&!quiet)step.textContent=`${meta.title}. ${meta.lead}`;
    const open=$('flow-open-related');
    if(open)open.textContent=meta.goto==='arena'?'Enter Arena':meta.goto==='lab'?'Scenario lab':meta.goto==='evidence'?'Evidence':'Pit wall';
  }catch(e){}
}
function applyFlowLane(){
  try{
    const lane=($('flow-lane')&&$('flow-lane').value)||'all';
    FLOW_NODE_IDS.forEach(id=>{
      const el=$(id);
      if(!el||!el.dataset)return;
      el.dataset.dim=(lane==='all'||el.dataset.lane===lane)?'':'1';
    });
  }catch(e){}
}
function stopFlowWalk(){
  if(flowWalkTimer){clearTimeout(flowWalkTimer);flowWalkTimer=null;}
  const b=$('flow-walk');
  if(b)b.textContent='Walk the call ↗';
}
function walkFlow(){
  if(flowWalkTimer){stopFlowWalk();return;}
  let i=0;
  const b=$('flow-walk');
  if(b)b.textContent='Stop walk';
  const tick=()=>{
    if(i>=FLOW_WALK.length){stopFlowWalk();return;}
    let id=FLOW_WALK[i++];
    if(id==='__call__')id=liveCallNode();
    selectFlowNode(id);
    const step=$('flow-step');
    if(step)step.textContent=`Walk ${i} / ${FLOW_WALK.length} · ${($('flow-inspect-title')&&$('flow-inspect-title').textContent)||id}`;
    let wait=850;
    try{if(typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches)wait=80;}catch(e){}
    flowWalkTimer=setTimeout(tick,wait);
  };
  tick();
}
function fitFlowBoard(){
  try{
    const canvas=$('flow-canvas');
    const board=$('flow-board');
    if(!canvas||!board||!board.style)return;
    const w=canvas.clientWidth||1;
    const s=Math.max(.38,Math.min(1,(w-8)/1680));
    board.style.transform=`scale(${s})`;
    board.style.transformOrigin='0 0';
    canvas.style.height=`${Math.ceil(700*s)}px`;
  }catch(e){}
}
function resetFlow(){
  stopFlowWalk();
  const lane=$('flow-lane');
  if(lane)lane.value='all';
  applyFlowLane();
  selectFlowNode('flow-n-snap');
}
function speakFlowRadio(){
  try{
    const meta=FLOW_META[flowFocus]||{};
    const call=prettyCall(currentResult&&currentResult.recommendation)||'NO CALL';
    const line=meta.radio||radioLine(call,prettyReason(currentResult||{}),currentResult&&currentResult.status);
    const roger=meta.roger||`Roger. ${call}.`;
    speakUtterance('engineer',line,()=>speakUtterance('driver',roger));
  }catch(e){}
}
function prettyController(name){
  const n=String(name||'');
  if(/greedy/i.test(n))return 'Greedy next-step';
  if(/HOLD/i.test(n)&&/reserve|aware/i.test(n))return 'HOLD-if-low';
  if(/planner/i.test(n))return 'Full planner';
  return prettyText(n);
}
function error(message){$('error').textContent=message;$('error').hidden=!message;}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,3500);}
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',...(apiKey?{'X-API-Key':apiKey}:{})},...(body?{body:JSON.stringify(body)}:{})});if(!r.ok){let message;try{const j=await r.json();message=typeof j.detail==='string'?j.detail:JSON.stringify(j.detail);}catch{message=await r.text();}throw Error(r.status===401?'API key required. Use the API key button to connect.':`Request failed (${r.status}): ${message}`);}return r.json();}
async function task(fn){if(busy)return;busy=true;error('');unlockSpeech();try{document.body.classList.toggle('is-busy',true);}catch(e){}const controls=['evaluate','save','compare','replay-step','scenario','import-file','replay-reset','arena-evaluate','arena-zoom'];controls.forEach(x=>$(x).disabled=true);try{await resumeRadio();await fn();}catch(e){error(e.message||String(e));}finally{busy=false;try{document.body.classList.toggle('is-busy',false);}catch(e){}controls.forEach(x=>$(x).disabled=false);}}
function syncSnapshotReadouts(){
  try{
    const own=Number($('own_speed_kph')&&$('own_speed_kph').value);
    const riv=Number($('rival_speed_kph')&&$('rival_speed_kph').value);
    const pace=$('pace-delta');
    if(pace&&Number.isFinite(own)&&Number.isFinite(riv)){
      const d=own-riv;
      pace.textContent=d===0?'Matched pace':`${Math.abs(d).toFixed(0)} km/h ${d>0?'faster':'slower'}`;
      if(pace.dataset)pace.dataset.sign=d>0?'up':d<0?'down':'even';
    }
    const gap=Number($('gap_s')&&$('gap_s').value);
    const fight=$('gap-delta');
    const gapField=$('gap_s')&&$('gap_s').parentElement;
    const sign=gap>0?'ahead':gap<0?'behind':'level';
    if(fight&&Number.isFinite(gap)){
      fight.textContent=gap===0?'Side by side':(gap>0?'Rival ahead':'Rival behind');
      if(fight.dataset)fight.dataset.sign=sign;
    }
    if(gapField&&gapField.dataset&&Number.isFinite(gap))gapField.dataset.sign=sign;
  }catch(e){}
}
function loadRequest(req){currentRequest=structuredClone(req);const s=req.state;$('own_energy_mj').max=req.policy?.capacity_mj??4;$('stage-unit').textContent=`${req.planning?.stage_s??4} s/step`;stateFields.forEach(k=>$(k).value=s[k]??(k==='data_age_s'?0:'GREEN'));$('terminal_buffer_mj').value=req.planning?.terminal_buffer_mj??.25;const stages=req.planning?.stages??6;if(![...$('stages').options].some(o=>+o.value===stages))$('stages').add(new Option(`${stages} stages`,stages));$('stages').value=stages;replayBelief=null;syncSnapshotReadouts();}
function readRequest(){if(!$('state-form').reportValidity())throw Error('Check the highlighted input values.');const req=structuredClone(currentRequest||{state:{timestamp_s:1}});stateFields.forEach(k=>req.state[k]=k==='track_status'?$(k).value:Number($(k).value));req.planning={...req.planning,stages:Number($('stages').value),terminal_buffer_mj:Number($('terminal_buffer_mj').value)};if(currentRequest?.state){const old=currentRequest.state;if(req.state.own_speed_kph!==old.own_speed_kph||req.state.rival_speed_kph!==old.rival_speed_kph)req.state.speed_source='user_supplied';if(req.state.gap_s!==old.gap_s)req.state.gap_source='user_supplied';if(req.state.own_energy_mj!==old.own_energy_mj)req.state.energy_source='user_supplied';}delete req.belief;return req;}
function chart(target,series,{threshold=null,unit='',startX=0}={}){
  const el=$(target);
  if(!series.length||!series.some(s=>s.points.length)){el.innerHTML='<p>No forecast available for this state.</p>';return;}
  const W=720,H=288,L=58,R=18,T=18,B=44;
  const all=series.flatMap(s=>s.points);
  let lo=Math.min(...all.map(p=>p.y),threshold??Infinity),hi=Math.max(...all.map(p=>p.y),threshold??-Infinity);
  if(!Number.isFinite(lo)||!Number.isFinite(hi)){lo=0;hi=1;}
  if(lo===hi){lo-=.5;hi+=.5;}
  const energy=/energy/i.test(unit);
  const pad=(hi-lo)*.14;
  lo-=pad;hi+=pad;
  if(energy)lo=Math.max(0,lo);
  const xmax=Math.max(...all.map(p=>p.x),1);
  const x=v=>L+(v-startX)/(xmax-startX||1)*(W-L-R);
  const y=v=>H-B-(v-lo)/(hi-lo||1)*(H-T-B);
  const yDec=(hi-lo)<1.2?2:1;
  const clip='clip-'+target;
  const toPath=pts=>pts.map((p,i)=>`${i?'L':'M'}${x(p.x).toFixed(2)},${y(p.y).toFixed(2)}`).join(' ');
  let svg=`<svg class="plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(unit)} chart"><title>${esc(series.map(s=>s.name).join(', '))}; ${esc(unit)}</title>`;
  svg+=`<defs><clipPath id="${clip}"><rect x="${L}" y="${T}" width="${W-L-R}" height="${H-T-B}"/></clipPath></defs>`;
  svg+=`<rect x="${L}" y="${T}" width="${W-L-R}" height="${H-T-B}" fill="#0b0b0d" stroke="#2c2c30"/>`;
  for(let i=0;i<=5;i++){
    const v=lo+(hi-lo)*i/5,yy=y(v).toFixed(2);
    svg+=`<line class="grid" x1="${L}" x2="${W-R}" y1="${yy}" y2="${yy}"/><text x="${L-8}" y="${+yy+4}" text-anchor="end" fill="#9a9aa0" font-size="11">${v.toFixed(yDec)}</text>`;
  }
  for(let i=0;i<=6;i++){
    const v=startX+(xmax-startX)*i/6,xx=x(v).toFixed(2);
    svg+=`<line class="grid" x1="${xx}" x2="${xx}" y1="${T}" y2="${H-B}"/><text x="${xx}" y="${H-16}" text-anchor="middle" fill="#9a9aa0" font-size="11">${v.toFixed(0)}s</text>`;
  }
  if(lo<0&&hi>0)svg+=`<line class="zero" x1="${L}" x2="${W-R}" y1="${y(0)}" y2="${y(0)}"/>`;
  svg+=`<g clip-path="url(#${clip})">`;
  if(threshold!==null){
    const yt=y(threshold),h=Math.max(0,H-B-yt);
    svg+=`<rect x="${L}" y="${yt}" width="${W-L-R}" height="${h}" fill="#f0b429" fill-opacity=".1"/>`;
    svg+=`<line class="threshold" x1="${L}" x2="${W-R}" y1="${yt}" y2="${yt}" stroke-dasharray="4 5"/>`;
  }
  if(series.length>=2&&series[1].dash&&series[0].points.length&&series[1].points.length){
    const top=toPath(series[0].points);
    const bot=series[1].points.slice().reverse().map((p,i)=>`${i?'L':'L'}${x(p.x).toFixed(2)},${y(p.y).toFixed(2)}`).join(' ');
    svg+=`<path d="${top} ${bot} Z" fill="#2ee59d" fill-opacity=".18" stroke="none"/>`;
  }
  series.forEach(s=>{
    svg+=`<path d="${toPath(s.points)}" fill="none" stroke="${s.color}" stroke-width="${s.dash?1.8:2.4}" stroke-linejoin="round" stroke-linecap="round" ${s.dash?'stroke-dasharray="5 5"':''}/>`;
    s.points.forEach(p=>{
      svg+=`<circle cx="${x(p.x).toFixed(2)}" cy="${y(p.y).toFixed(2)}" r="3.1" fill="${s.color}" stroke="#0b0b0d" stroke-width="1.2"><title>${esc(s.name)} · ${p.x.toFixed(0)}s · ${p.y.toFixed(2)}</title></circle>`;
    });
  });
  svg+='</g>';
  svg+=`<line class="axis" x1="${L}" y1="${T}" x2="${L}" y2="${H-B}"/><line class="axis" x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}"/>`;
  svg+=`<text transform="translate(14,${((T+H-B)/2).toFixed(1)}) rotate(-90)" text-anchor="middle" fill="#9a9aa0" font-size="11">${esc(unit)}</text>`;
  if(threshold!==null)svg+=`<text x="${W-R-6}" y="${y(threshold)-6}" text-anchor="end" fill="#f0b429" font-size="10">must-keep</text>`;
  svg+='</svg>';
  el.innerHTML=svg;
}
function render(result,req){currentResult=result;lastEvaluatedRequest=structuredClone(req);$('export').disabled=false;$('action').textContent=prettyCall(result.recommendation);try{$('action').dataset.call=prettyCall(result.recommendation);}catch(e){}$('action').style.fontSize=result.status==='abstain'?'2rem':'';$('action').style.color='';$('reason').textContent=prettyReason(result);$('decision-status').textContent=result.status==='advisory'?'NEEDS REVIEW':'NO CALL';try{$('decision-status').dataset.kind=result.status==='advisory'?'review':'hold';}catch(e){}$('horizon').textContent=`${result.horizon_s} SECOND LOOKAHEAD`;$('latency').textContent=`${fmt(result.latency_ms,1)} ms`;const p=req.policy||{};const required=(p.reserve_mj??.6)+(req.planning?.terminal_buffer_mj??.25);$('required').textContent=`${fmt(required)} MJ`;const best=result.candidates.find(c=>c.valid&&c.action===result.recommendation);$('finish').textContent=best?`${fmt(best.conservative_energy_mj)} MJ`:'—';$('sequence').innerHTML=best?best.trace.map(t=>`<div class="stage" data-action="${esc(t.action)}">${esc(prettyCall(t.action))}<span>+${t.time_s}s</span></div>`).join(''):'';
$('candidates').innerHTML=result.candidates.length?result.candidates.map(c=>`<tr class="${c.action===result.recommendation?'selected':''}"><td data-call="${esc(prettyCall(c.action))}">${esc(prettyCall(c.action))}</td><td>${fmt(c.score_s,3)}</td><td>${fmt(c.conservative_energy_mj)}</td><td>${fmt(c.gap_s,3)}${c.valid?'s':''}</td><td class="${c.valid?'':'rejected'}">${c.valid?(c.action===result.recommendation?'Recommended':'Feasible'):esc(prettyText(c.rejection_reasons.join('; ')))}</td></tr>`).join(''):'<tr><td colspan="5">Input gate failed. Candidate forecasts were not generated.</td></tr>';
$('belief').innerHTML=[['slow','Slower'],['neutral','Matched'],['fast','Faster']].map(([k,label])=>`<div class="belief-row"><span>${label}</span><div class="belief-bar"><div style="width:${result.belief[k]*100}%"></div></div><span>${(result.belief[k]*100).toFixed(0)}%</span></div>`).join('');
chart('energy-chart',best?[{name:'Expected energy',color:'#2ee59d',points:[{x:0,y:req.state.own_energy_mj},...best.trace.map(t=>({x:t.time_s,y:t.energy_mj}))]},{name:'Conservative energy',color:'#9a9aa0',dash:true,points:[{x:0,y:Math.max(0,req.state.own_energy_mj-(req.state.energy_uncertainty_mj??.1))},...best.trace.map(t=>({x:t.time_s,y:t.conservative_energy_mj}))]}]:[],{threshold:required,unit:'Energy MJ'});
$('rules').innerHTML=[['Reserve to keep',`${fmt(p.reserve_mj??.6)} MJ`],['Must-keep at plan end',`${fmt(required)} MJ`],['Max deploy power',`${p.max_deploy_kw??120} kW`],['Energy budget this window',`${fmt(req.planning?.deployment_budget_mj??2)} MJ`],['Max snapshot age',`${p.max_data_age_s??5}s`],['Track status','GREEN only (racing)'],['Rules status','Unverified model policy']].map(([a,b])=>`<div class="rule"><span>${esc(a)}</span><strong>${esc(b)}</strong></div>`).join('');
const src=req.state.speed_source??'synthetic';document.querySelector('.source-tag').innerHTML=`${esc(src==='synthetic'?'SYNTHETIC SCENARIO':src.toUpperCase()+' INPUT')}<span>Energy: ${esc(req.state.energy_source??'simulated')} · Rules unverified</span>`;
renderMl(result);
refreshArenaInspect();
refreshFlowLive();
}
function pct(v){return Number.isFinite(v)?`${(v*100).toFixed(1)}%`:'—';}
function renderMl(result){
  const panel=$('ml-candidate');
  const body=$('ml-candidate-body');
  if(!result.ml_policy){panel.hidden=true;body.textContent='';return;}
  panel.hidden=false;
  if(result.status==='abstain'){
    body.innerHTML=`<p class="ml-abstain">${esc(prettyReason(result))}</p>`;
    return;
  }
  const ml=result.ml_policy;
  const shield=result.shield||{};
  const status=shield.passed?'Allowed by the energy rules':prettyText(shield.reason||'');
  body.innerHTML=`<div class="ml-row"><span>Model guess</span><strong id="ml-predicted">${esc(prettyCall(ml.predicted_action||'—'))}</strong></div><div class="ml-row"><span>Confidence</span><strong id="ml-top-p">${esc(pct(ml.top_probability))}</strong></div><div class="ml-row"><span>Lead over 2nd call</span><strong id="ml-margin">${esc(pct(ml.probability_margin))}</strong></div><p class="${shield.passed?'ml-shield-ok':'ml-shield-fail'}">${esc(status)}</p>`;
}
function canSpeak(){try{return typeof speechSynthesis==='object'&&speechSynthesis&&typeof SpeechSynthesisUtterance==='function';}catch(e){return false;}}
function unlockSpeech(){
  try{
    if(!canSpeak()||speechUnlocked)return;
    const u=new SpeechSynthesisUtterance('.');
    u.volume=0;u.rate=2;u.lang='en-US';
    speechSynthesis.speak(u);
    speechUnlocked=true;
  }catch(e){}
}
function pickVoices(){
  try{
    if(!canSpeak())return;
    const list=speechSynthesis.getVoices()||[];
    if(!list.length)return;
    const en=list.filter(v=>/^en/i.test(v.lang||''));
    const pool=en.length?en:list;
    const engineer=pool.find(v=>/David|Daniel|George|Alex|Guy|Mark|Male|UK English Male/i.test(v.name))||pool[0];
    const driver=pool.find(v=>v!==engineer&&/Zira|Samantha|Jenny|Hazel|Female|Google US English/i.test(v.name))||pool.find(v=>v!==engineer)||engineer;
    radioVoices={engineer,driver};
  }catch(e){}
}
function makeNoiseBuffer(ctx,seconds){
  const n=Math.max(1,Math.floor(ctx.sampleRate*seconds));
  const buf=ctx.createBuffer(1,n,ctx.sampleRate);
  const data=buf.getChannelData(0);
  for(let i=0;i<n;i++)data[i]=Math.random()*2-1;
  return buf;
}
function ensureRadio(){
  try{
    if(radio&&radio.ctx)return radio;
    const Ctx=(typeof AudioContext==='function'&&AudioContext)||(typeof webkitAudioContext==='function'&&webkitAudioContext);
    if(!Ctx)return null;
    const ctx=new Ctx();
    const hp=ctx.createBiquadFilter();hp.type='highpass';hp.frequency.value=300;
    const lp=ctx.createBiquadFilter();lp.type='lowpass';lp.frequency.value=3000;
    const comp=ctx.createDynamicsCompressor();comp.threshold.value=-24;comp.knee.value=12;comp.ratio.value=4;comp.attack.value=.003;comp.release.value=.15;
    const master=ctx.createGain();master.gain.value=.4;
    hp.connect(lp);lp.connect(comp);comp.connect(master);master.connect(ctx.destination);
    radio={ctx,input:hp,clickBuf:makeNoiseBuffer(ctx,.08),noiseBuf:makeNoiseBuffer(ctx,1)};
    return radio;
  }catch(e){radio=null;return null;}
}
async function resumeRadio(){
  try{
    const r=ensureRadio();
    if(r&&r.ctx&&r.ctx.state==='suspended')await r.ctx.resume();
  }catch(e){}
}
function setWave(on){
  try{
    const el=$('radio-wave');
    if(el)el.classList.toggle('is-speaking',!!on);
  }catch(e){}
}
function playBurst(at){
  try{
    const r=ensureRadio();
    if(!r)return;
    const src=r.ctx.createBufferSource();
    src.buffer=r.clickBuf;
    const g=r.ctx.createGain();
    g.gain.value=.2;
    src.connect(g);g.connect(r.input);
    src.start(at);
  }catch(e){}
}
function radioClicks(){
  try{
    const r=ensureRadio();
    if(!r)return;
    const t=r.ctx.currentTime;
    playBurst(t);
    playBurst(t+.1);
  }catch(e){}
}
function startNoise(){
  try{
    stopNoise();
    const r=ensureRadio();
    if(!r)return;
    const src=r.ctx.createBufferSource();
    src.buffer=r.noiseBuf;
    src.loop=true;
    const g=r.ctx.createGain();
    g.gain.value=.03;
    src.connect(g);g.connect(r.input);
    src.start();
    noiseNode={src,g};
  }catch(e){}
}
function stopNoise(){
  try{
    if(noiseNode&&noiseNode.src)noiseNode.src.stop();
  }catch(e){}
  noiseNode=null;
}
function isAbstain(result){
  if(!result)return false;
  if(result.status==='abstain')return true;
  const reason=String((result.shield&&result.shield.reason)||'');
  if(result.shield&&result.shield.passed===false&&/precheck_abstain|uncertainty_gate/i.test(reason))return true;
  return false;
}
function prefersReduce(){
  try{
    return typeof globalThis.matchMedia==='function'&&globalThis.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }catch(e){return false;}
}
function flickerHero(){
  try{
    if(prefersReduce())return;
    const el=document.querySelector('.recommendation');
    if(!el||!el.classList||typeof el.classList.add!=='function')return;
    el.classList.remove('is-signal-loss');
    void el.offsetWidth;
    el.classList.add('is-signal-loss');
    const done=()=>{
      try{el.classList.remove('is-signal-loss');}catch(e){}
      try{el.removeEventListener('animationend',done);}catch(e){}
    };
    if(typeof el.addEventListener==='function')el.addEventListener('animationend',done);
  }catch(e){}
}
function radioLine(action,reason,status){
  const a=prettyCall(action||'NO CALL');
  const r=String(reason||'');
  if(status==='abstain'){
    if(/not GREEN|not confirmed GREEN/i.test(r))return `${a}. Track not green.`;
    if(/stale data|too old/i.test(r))return `${a}. Data too old.`;
    if(/not sure enough|ambiguous/i.test(r))return `${a}. Picture unclear.`;
    return `${a}. No call.`;
  }
  if(/accepted by the deterministic/i.test(r))return `${a}. Accepted by the shield.`;
  if(/shield rejected/i.test(r))return `${a}. Shield rejected.`;
  if(/unavailable/i.test(r))return `${a}. Candidate unavailable.`;
  const clause=r.split(/[.;]/)[0].trim().split(/\s+/).slice(0,8).join(' ');
  return clause?`${a}. ${clause}.`:a;
}
function speakUtterance(role,text,onDone){
  try{
    if(!canSpeak()||!text){if(onDone)onDone();return;}
    pickVoices();
    try{speechSynthesis.cancel();}catch(e){}
    radioClicks();
    try{
        startNoise();
        const u=new SpeechSynthesisUtterance(text);
        const voice=role==='engineer'?radioVoices.engineer:radioVoices.driver;
        if(voice)u.voice=voice;
        u.rate=role==='engineer'?(lastWasAbstain?.86:.92):1.06;
        u.pitch=role==='engineer'?(lastWasAbstain?.78:.82):1.18;
        u.onstart=()=>{if(role==='engineer'){engineerTalking=true;setWave(true);}};
        const finish=()=>{
          try{radioClicks();}catch(e){}
          stopNoise();
          if(role==='engineer'){engineerTalking=false;setWave(false);}
          if(onDone)onDone();
        };
        u.onend=finish;
        u.onerror=()=>{stopNoise();engineerTalking=false;setWave(false);if(onDone)onDone();};
        if(role==='engineer'){engineerTalking=true;setWave(true);}
        speechSynthesis.speak(u);
      }catch(e){stopNoise();setWave(false);if(onDone)onDone();}
  }catch(e){setWave(false);if(onDone)onDone();}
}
function afterPlan(result,save){
  try{
    const abstain=isAbstain(result);
    if(abstain&&!lastWasAbstain)flickerHero();
    lastWasAbstain=abstain;
    const action=(($('action')&&$('action').textContent)||'').trim();
    const changed=!!action&&action!==lastSpokenAction;
    if(changed)lastSpokenAction=action;
    const line=radioLine(action,prettyReason(result),result.status);
    if(changed&&save)speakUtterance('engineer',line,()=>speakUtterance('driver',`Roger. ${action}.`));
    else if(changed)speakUtterance('engineer',line);
    else if(save)speakUtterance('driver',`Roger. ${action||'copy'}.`);
  }catch(e){}
}
const CALL_KW={COMMIT:120,PROBE:80,HOLD:40,CONSERVE:0,'NO CALL':0};
const CALL_PACE={COMMIT:1.14,PROBE:1.06,HOLD:1,CONSERVE:.9,'NO CALL':0};
const ARENA_KM=5.891;
const ARENA_LAPS=52;
const ARENA_CLOCKS=[1,2,4,8,16,24];
const ARENA_MIN_T=0.036;
const FLAG_PACE={GREEN:1,YELLOW:.72,VSC:.68,SC:.46,RED:0};
function readRivalSpeed(){
  const n=Number($('rival_speed_kph')&&$('rival_speed_kph').value);
  if(Number.isFinite(n)&&n>=0)return n;
  const s=currentRequest&&currentRequest.state;
  return Number.isFinite(s&&s.rival_speed_kph)?s.rival_speed_kph:302;
}
function arenaReport(){
  const track=($('track_status')&&$('track_status').value)||'UNKNOWN';
  const age=Number($('data_age_s')&&$('data_age_s').value);
  const own=readCircuitSpeed();
  const energy=Number($('own_energy_mj')&&$('own_energy_mj').value);
  const call=prettyCall(currentResult&&currentResult.recommendation);
  const reasons=[];
  if(track!=='GREEN')reasons.push('Track is not GREEN');
  if(Number.isFinite(age)&&age>5)reasons.push('Snapshot too old');
  if(!(own>=30))reasons.push('Outside moving-car regime');
  if(Number.isFinite(energy)&&energy>4)reasons.push('Energy above capacity');
  if(!currentResult||currentResult.status==='abstain'||call==='NO CALL')reasons.push('No deploy call');
  return {track,age,own,energy,call,live:!reasons.length,reasons,kw:CALL_KW[call]||0,pace:CALL_PACE[call]||0};
}
function lapSeconds(kph){return ARENA_KM/Math.max(kph,1)*3600;}
function arenaDist(who){
  if(!arenaViz)return 0;
  const d=who==='rival'?arenaViz.distRival:arenaViz.distOwn;
  return Number.isFinite(d)?d:0;
}
function arenaLapInfo(who){
  const total=ARENA_LAPS;
  const raw=arenaDist(who);
  const dist=Number.isFinite(raw)?raw:0;
  const finished=dist>=total;
  const current=finished?total:Math.min(total,Math.max(1,1+Math.floor(Math.max(0,dist))));
  const frac=finished?1:(dist<0?0:dist-Math.floor(dist));
  const kph=who==='rival'?readRivalSpeed():readCircuitSpeed();
  const lapS=lapSeconds(Math.max(kph,1));
  return {total,current,finished,frac,dist,km:frac*ARENA_KM,lapS,remain:Math.max(0,total-Math.max(0,dist))};
}
function arenaLapDelta(){
  const d=arenaDist('rival')-arenaDist('own');
  if(!Number.isFinite(d))return 'Same lap';
  if(Math.abs(d)<0.5)return 'Same lap';
  const laps=Math.round(d);
  if(laps===0)return 'Same lap';
  return laps>0?`${laps} lap${laps===1?'':'s'} ahead`:`${Math.abs(laps)} lap${Math.abs(laps)===1?'':'s'} behind`;
}
function arenaFlagPace(track){return FLAG_PACE[track]!==undefined?FLAG_PACE[track]:1;}
function arenaOwnPace(rep){
  if(!(rep.own>=30))return 0;
  const flag=arenaFlagPace(rep.track);
  if(!flag)return 0;
  return rep.live?flag*rep.pace:flag;
}
function arenaRivalPace(rep){
  if(!(readRivalSpeed()>=1))return 0;
  return arenaFlagPace(rep.track);
}
function arenaGapT(gap,kph){
  const raw=gap/lapSeconds(Math.max(kph,1));
  const mag=Math.max(Math.abs(raw),ARENA_MIN_T);
  return (raw<0?-1:1)*mag;
}
function keepApart(tA,tB){
  let d=((tB-tA)%1+1.5)%1-.5;
  if(Math.abs(d)<ARENA_MIN_T)return wrap01(tA+(d<0?-1:1)*ARENA_MIN_T);
  return tB;
}
function arenaMotionSpeed(rep){return Math.max(0,rep.own*arenaOwnPace(rep));}
function arenaClock(){
  const n=Number($('arena-clock')&&$('arena-clock').value);
  if(Number.isFinite(n)&&n>0)return Math.min(32,Math.max(.5,n));
  return 8;
}
function syncArenaClockLabel(){
  const out=$('arena-clock-readout');
  if(out)out.textContent=`${arenaClock()}×`;
}
function setArenaPaused(on){
  if(arenaViz){arenaViz.paused=!!on;arenaViz.hud='';}
  const btn=$('arena-pause');
  if(btn){
    btn.textContent=on?'Resume':'Pause';
    if(btn.dataset)btn.dataset.paused=on?'1':'';
    try{btn.setAttribute('aria-pressed',on?'true':'false');}catch(e){}
  }
}
function toggleArenaPause(){
  setArenaPaused(!(arenaViz&&arenaViz.paused));
}
function bumpArenaClock(dir){
  const el=$('arena-clock');
  if(!el)return;
  const cur=arenaClock();
  let i=ARENA_CLOCKS.indexOf(cur);
  if(i<0){i=0;for(let k=0;k<ARENA_CLOCKS.length;k++)if(ARENA_CLOCKS[k]<=cur)i=k;}
  i=Math.max(0,Math.min(ARENA_CLOCKS.length-1,i+(dir<0?-1:1)));
  el.value=String(ARENA_CLOCKS[i]);
  syncArenaClockLabel();
  if(arenaViz)arenaViz.hud='';
}
function setHudText(id,text,key,val){
  const el=$(id);
  if(!el)return;
  if(el.textContent!==text)el.textContent=text;
  if(key&&el.dataset)el.dataset[key]=val;
}
function refreshArenaHud(rep,gap){
  setHudText('arena-hud-call',rep.call,'call',rep.call);
  setHudText('arena-hud-kw',`${rep.kw} kW`);
  setHudText('arena-hud-flag',rep.track,'flag',rep.track);
  const v=arenaMotionSpeed(rep);
  const paused=!!(arenaViz&&arenaViz.paused);
  const moving=v>0&&!(arenaViz&&arenaViz.reduce)&&!paused;
  let gate='HOLD STATION';
  if(arenaViz&&arenaViz.reduce)gate='MOTION OFF';
  else if(paused)gate='PAUSED';
  else if(rep.track==='RED')gate='RED · STOPPED';
  else if(!(rep.own>=30))gate='PARKED';
  else if(moving&&rep.live)gate=`LIVE · ${fmt(v,0)} km/h`;
  else if(moving&&rep.track!=='GREEN')gate=`${rep.track} · ${fmt(v,0)} km/h`;
  else if(moving)gate=`RACING · ${fmt(v,0)} km/h`;
  if(moving)gate=`${gate} · ${arenaClock()}×`;
  setHudText('arena-hud-gate',gate,'live',moving?'1':'0');
  syncArenaClockLabel();
  const ownLap=arenaLapInfo('own');
  const lapEl=$('arena-lap-label');
  if(lapEl){
    lapEl.textContent=ownLap.finished
      ?`5.891 km · finished ${ownLap.total} laps · 18 corners`
      :`5.891 km · lap ${ownLap.current} / ${ownLap.total} · 18 corners`;
  }
  const dock=$('arena-dock');
  if(dock&&dock.dataset)dock.dataset.call=rep.call;
}
function selectArenaCar(who){
  try{
    if(arenaViz){arenaViz.focus=who;arenaViz.follow=true;}
    const z=$('arena-zoom');
    if(z)z.textContent='Full circuit';
    const own=$('arena-car-own');
    const riv=$('arena-car-rival');
    if(own&&own.dataset)own.dataset.selected=who==='own'?'1':'';
    if(riv&&riv.dataset)riv.dataset.selected=who==='rival'?'1':'';
    refreshArenaInspect();
  }catch(e){}
}
function refreshArenaInspect(){
  try{
    const who=(arenaViz&&arenaViz.focus)||'own';
    const own=who==='own';
    const rep=arenaReport();
    const gap=readCircuitGap();
    const req=currentRequest||{};
    const st=req.state||{};
    const result=currentResult;
    const title=$('arena-inspect-title');
    const kick=$('arena-inspect-kicker');
    const lead=$('arena-inspect-lead');
    if(title)title.textContent=own?'GG-01 · GridGhost':'RIV-88 · Rival';
    if(kick)kick.textContent=own?'OUR CAR':'RIVAL CAR';
    const lap=arenaLapInfo(own?'own':'rival');
    const other=arenaLapInfo(own?'rival':'own');
    if(lead)lead.textContent=own
      ?(arenaMotionSpeed(rep)>0
        ?`On track. Lap ${lap.current} / ${lap.total}. ${rep.call} ${rep.live?`deploys ${rep.kw} kW.`:`holds deploy · ${rep.reasons[0]||'waiting'}`}`
        :`Stopped. ${rep.reasons.join(' · ')}`)
      :`Lap ${lap.current} / ${lap.total}. Gap ${gap>0?'ahead':gap<0?'behind':'alongside'} ${fmt(Math.abs(gap),2)}s · ${fmt(readRivalSpeed(),0)} km/h.`;
    const lapRow=lap.finished
      ?[`Lap`,`Finished · ${lap.total} / ${lap.total}`]
      :[`Lap`,`${lap.current} / ${lap.total}`];
    const rows=own?[
      ['Race',`Silverstone · ${lap.total} laps`],
      lapRow,
      ['This lap',`${fmt(lap.km,2)} / ${ARENA_KM} km · ${Math.round(lap.frac*100)}%`],
      ['Laps left',lap.finished?'0':fmt(lap.remain,2)],
      ['Pace',`${fmt(lap.lapS,1)} s / lap`],
      ['Speed',`${fmt(rep.own,0)} km/h`],
      ['Call pace',`${fmt(arenaMotionSpeed(rep),0)} km/h · ${rep.live?rep.call:'no deploy'}`],
      ['Deploy',`${rep.kw} kW · ${rep.call}`],
      ['Energy',`${fmt(Number.isFinite(rep.energy)?rep.energy:st.own_energy_mj)} MJ`],
      ['Data age',`${fmt(Number.isFinite(rep.age)?rep.age:0,1)} s`],
      ['Track',rep.track],
      ['Safer finish',($('finish')&&$('finish').textContent)||'—'],
      ['Must-keep',($('required')&&$('required').textContent)||'—'],
      ['Compute',($('latency')&&$('latency').textContent)||'—']
    ]:[
      ['Race',`Silverstone · ${lap.total} laps`],
      lapRow,
      ['This lap',`${fmt(lap.km,2)} / ${ARENA_KM} km · ${Math.round(lap.frac*100)}%`],
      ['Laps left',lap.finished?'0':fmt(lap.remain,2)],
      ['Pace',`${fmt(lap.lapS,1)} s / lap`],
      ['Vs us',`${arenaLapDelta()} · we are lap ${other.current}`],
      ['Rival speed',`${fmt(readRivalSpeed(),0)} km/h`],
      ['Gap',`${fmt(gap,2)} s`],
      ['Relative',gap>0.005?'Ahead of us':gap<-0.005?'Behind us':'Alongside'],
      ['Our call',rep.call],
      ['Track',rep.track]
    ];
    if(result&&result.belief&&!own){
      rows.push(['Rival slower',`${Math.round(result.belief.slow*100)}%`]);
      rows.push(['Rival matched',`${Math.round(result.belief.neutral*100)}%`]);
      rows.push(['Rival faster',`${Math.round(result.belief.fast*100)}%`]);
    }
    let html=`<div class="arena-kv">${rows.map(([k,v])=>`<span>${esc(k)}</span><strong>${esc(v)}</strong>`).join('')}</div>`;
    if(own&&result&&result.candidates&&result.candidates.length){
      html+=`<div class="arena-kv">${result.candidates.map(c=>`<span>${esc(prettyCall(c.action))}</span><strong>${c.valid?esc(fmt(c.score_s,3))+'s':esc(prettyText((c.rejection_reasons||[]).join('; ')||'blocked'))}</strong>`).join('')}</div>`;
    }
    const best=result&&result.candidates&&result.candidates.find(c=>c.valid&&c.action===result.recommendation);
    if(own&&best&&best.trace&&best.trace.length){
      html+=`<div class="arena-seq">${best.trace.map(t=>`<i data-call="${esc(prettyCall(t.action))}">${esc(prettyCall(t.action))} +${esc(String(t.time_s))}s</i>`).join('')}</div>`;
    }
    const box=$('arena-inspect');
    if(box)box.innerHTML=html;
    refreshArenaHud(rep,gap);
  }catch(e){}
}
function nearestT(path,len,x,y){
  let best=0,bestD=1e12;
  const n=160;
  for(let i=0;i<=n;i++){
    const t=i/n;
    const p=path.getPointAtLength(t*len);
    const d=(p.x-x)*(p.x-x)+(p.y-y)*(p.y-y);
    if(d<bestD){bestD=d;best=t;}
  }
  return best;
}
function worldToSvg(x,y){return {x:500-y,y:x};}
function updateArenaCamera(){
  const svg=$('arena-svg');
  if(!svg||!arenaViz||typeof arenaViz.path.getPointAtLength!=='function')return;
  ['arena-tag-own','arena-tag-rival'].forEach(id=>{
    const tag=$(id);
    if(tag)tag.setAttribute('opacity',arenaViz.follow?'0':'1');
  });
  if(!arenaViz.follow){
    svg.setAttribute('viewBox','-30 -24 560 548');
    return;
  }
  const t=arenaViz.focus==='rival'?(arenaViz.tRival??arenaViz.tOwn):arenaViz.tOwn;
  const p=arenaViz.path.getPointAtLength(wrap01(t)*arenaViz.len);
  const s=worldToSvg(p.x,p.y);
  svg.setAttribute('viewBox',`${(s.x-90).toFixed(1)} ${(s.y-68).toFixed(1)} 180 136`);
}
function placeTag(el,path,len,t,normalPx){
  if(!el||!path||typeof path.getPointAtLength!=='function')return;
  const a=path.getPointAtLength(wrap01(t)*len);
  const b=path.getPointAtLength(wrap01(t+0.001)*len);
  const dx=b.x-a.x,dy=b.y-a.y;
  const mag=Math.hypot(dx,dy)||1;
  const n=Number(normalPx)||0;
  el.setAttribute('transform',`translate(${a.x+(-dy/mag)*n},${a.y+(dx/mag)*n})`);
}
function seedArenaGap(){
  if(!arenaViz)return;
  const gap=readCircuitGap();
  if(!Number.isFinite(arenaViz.distOwn))arenaViz.distOwn=0;
  arenaViz.distRival=arenaViz.distOwn+arenaGapT(gap,readCircuitSpeed());
  const t0=Number.isFinite(arenaViz.t0)?arenaViz.t0:0;
  arenaViz.tOwn=wrap01(t0+arenaViz.distOwn);
  arenaViz.tRival=wrap01(t0+arenaViz.distRival);
  arenaViz.gapSeed=gap;
}
function placeArenaCars(tOwn,tRival){
  const lane=arenaViz&&arenaViz.follow?12:10;
  const sc=arenaViz&&arenaViz.follow?1.2:1;
  placeMarker($('arena-car-own'),arenaViz.path,arenaViz.len,tOwn,lane,sc);
  placeMarker($('arena-car-rival'),arenaViz.path,arenaViz.len,tRival,-lane,sc);
  placeTag($('arena-tag-own'),arenaViz.path,arenaViz.len,tOwn,16);
  placeTag($('arena-tag-rival'),arenaViz.path,arenaViz.len,tRival,-18);
}
function ensureArena(){
  try{
    const path=$('arena-path');
    if(path&&typeof path.getTotalLength==='function'&&arenaViz){
      const len=path.getTotalLength();
      if(Number.isFinite(len)&&len>0)arenaViz.len=len;
    }
    if(arenaViz&&!Number.isFinite(arenaViz.distOwn)){
      arenaViz.t0=Number.isFinite(arenaViz.t0)?arenaViz.t0:(arenaViz.tOwn||0);
      arenaViz.distOwn=0;
      arenaViz.distRival=0;
      seedArenaGap();
    }
    if(!arenaViz||!arenaViz.started)startArena();
  }catch(e){}
}
function startArena(){
  try{
    if(arenaViz&&arenaViz.started)return;
    const path=$('arena-path');
    if(!path||typeof path.getTotalLength!=='function')return;
    const len=path.getTotalLength();
    if(!Number.isFinite(len)||len<=0)return;
    let t0=0;
    try{t0=nearestT(path,len,125.68,305.7);}catch(e){}
    let reduce=false;
    try{reduce=typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches;}catch(e){}
    arenaViz={path,len,t0,tOwn:t0,tRival:t0,distOwn:0,distRival:0,gapSeed:null,lastTs:0,started:true,focus:'own',reduce,hud:'',follow:false,paused:false};
    try{seedArenaGap();placeArenaCars(arenaViz.tOwn,arenaViz.tRival);}catch(e){}
    if(typeof requestAnimationFrame!=='function')return;
    const tick=ts=>{
      try{
        if(!arenaViz.lastTs)arenaViz.lastTs=ts;
        const dt=Math.min(.08,(ts-arenaViz.lastTs)/1000);
        arenaViz.lastTs=ts;
        const rep=arenaReport();
        const gap=readCircuitGap();
        if(arenaViz.gapSeed!==gap)seedArenaGap();
        if(!arenaViz.reduce&&!arenaViz.paused){
          const ownV=rep.own*arenaOwnPace(rep);
          const rivV=readRivalSpeed()*arenaRivalPace(rep);
          const clock=arenaClock();
          if(ownV>0&&arenaViz.distOwn<ARENA_LAPS)arenaViz.distOwn=Math.min(ARENA_LAPS,arenaViz.distOwn+clock*dt/lapSeconds(ownV));
          if(rivV>0&&arenaViz.distRival<ARENA_LAPS)arenaViz.distRival=Math.min(ARENA_LAPS,arenaViz.distRival+clock*dt/lapSeconds(rivV));
        }
        const t0=Number.isFinite(arenaViz.t0)?arenaViz.t0:0;
        arenaViz.tOwn=wrap01(t0+arenaViz.distOwn);
        arenaViz.tRival=wrap01(t0+arenaViz.distRival);
        const tOwn=arenaViz.tOwn;
        const tRival=keepApart(tOwn,arenaViz.tRival);
        placeArenaCars(tOwn,tRival);
        updateArenaCamera();
        const ownLap=arenaLapInfo('own');
        const rivLap=arenaLapInfo('rival');
        const sig=`${rep.call}|${rep.live}|${rep.track}|${fmt(arenaMotionSpeed(rep),0)}|${arenaClock()}|${arenaViz.paused?1:0}|${ownLap.current}|${Math.floor(ownLap.frac*20)}|${rivLap.current}|${Math.floor(rivLap.frac*20)}`;
        if(sig!==arenaViz.hud){arenaViz.hud=sig;refreshArenaInspect();}
      }catch(e){}
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }catch(e){}
}
const CIRCUIT_NS='http://www.w3.org/2000/svg';
const CIRCUIT_LAP_S=20;
const CIRCUIT_OWN='#2ee59d';
const CIRCUIT_RIVAL='#e24b4a';
function wrap01(t){t=t%1;return t<0?t+1:t;}
function placeMarker(el,path,len,t,normalPx,scale){
  if(!el||!path||typeof path.getPointAtLength!=='function')return;
  const a=path.getPointAtLength(wrap01(t)*len);
  const b=path.getPointAtLength(wrap01(t+0.001)*len);
  const dx=b.x-a.x,dy=b.y-a.y;
  const mag=Math.hypot(dx,dy)||1;
  const n=Number(normalPx)||0;
  const deg=Math.atan2(dy,dx)*180/Math.PI;
  const sc=Number(scale)||1;
  el.setAttribute('transform',`translate(${a.x+(-dy/mag)*n},${a.y+(dx/mag)*n}) rotate(${deg})${sc!==1?` scale(${sc})`:''}`);
}
function svgNode(name,attrs){
  const el=document.createElementNS(CIRCUIT_NS,name);
  if(attrs)Object.keys(attrs).forEach(k=>el.setAttribute(k,attrs[k]));
  return el;
}
function makeCarGroup(svg,fill,opacity,extraClass){
  const g=svgNode('g',extraClass?{class:extraClass}:null);
  if(opacity!=null)g.setAttribute('opacity',String(opacity));
  g.appendChild(svgNode('circle',{r:8,fill,stroke:'#0a0a0c','stroke-width':1.8}));
  g.appendChild(svgNode('circle',{r:2.6,fill:'#f2f2f2'}));
  svg.appendChild(g);
  return g;
}
function makeFlag(svg,fill,code,below){
  const g=svgNode('g',{class:'circuit-flag'});
  const y=below?10:-22;
  g.appendChild(svgNode('rect',{x:8,y,width:28,height:12,fill:'#0a0a0c',stroke:fill,'stroke-width':1}));
  const t=svgNode('text',{x:22,y:y+9,'text-anchor':'middle'});
  t.textContent=code;
  g.appendChild(t);
  svg.appendChild(g);
  return g;
}
function placeFlag(el,path,len,t){
  if(!el||!path||typeof path.getPointAtLength!=='function')return;
  const a=path.getPointAtLength(wrap01(t)*len);
  el.setAttribute('transform',`translate(${a.x},${a.y})`);
}
function readCircuitSpeed(){
  const n=Number($('own_speed_kph')&&$('own_speed_kph').value);
  if(Number.isFinite(n)&&n>0)return n;
  const s=currentRequest&&currentRequest.state;
  return Number.isFinite(s&&s.own_speed_kph)?s.own_speed_kph:300;
}
function readCircuitGap(){
  const n=Number($('gap_s')&&$('gap_s').value);
  if(Number.isFinite(n))return n;
  const s=currentRequest&&currentRequest.state;
  return Number.isFinite(s&&s.gap_s)?s.gap_s:0;
}
function startCircuit(){
  try{
    if(circuitViz&&circuitViz.started)return;
    const path=$('circuit-path');
    if(!path||typeof path.getTotalLength!=='function')return;
    const totalLength=path.getTotalLength();
    if(!Number.isFinite(totalLength)||totalLength<=0)return;
    const svg=$('circuit-svg')||path.ownerSVGElement;
    if(!svg||typeof document.createElementNS!=='function')return;
    circuitViz={
      path,svg,len:totalLength,
      own:makeCarGroup(svg,CIRCUIT_OWN),
      ownT1:makeCarGroup(svg,CIRCUIT_OWN,.3,'circuit-trail'),
      ownT2:makeCarGroup(svg,CIRCUIT_OWN,.15,'circuit-trail'),
      rival:makeCarGroup(svg,CIRCUIT_RIVAL),
      rivT1:makeCarGroup(svg,CIRCUIT_RIVAL,.3,'circuit-trail'),
      rivT2:makeCarGroup(svg,CIRCUIT_RIVAL,.15,'circuit-trail'),
      ownFlag:makeFlag(svg,CIRCUIT_OWN,'GG'),
      rivFlag:makeFlag(svg,CIRCUIT_RIVAL,'RIV',true),
      tOwn:0,lastTs:0,started:false,lastReadout:''
    };
    if(typeof requestAnimationFrame!=='function')return;
    const tick=ts=>{
      try{
        if(!circuitViz.lastTs)circuitViz.lastTs=ts;
        const dt=Math.min(.08,(ts-circuitViz.lastTs)/1000);
        circuitViz.lastTs=ts;
        circuitViz.tOwn=wrap01(circuitViz.tOwn+(readCircuitSpeed()/300)*dt/CIRCUIT_LAP_S);
        const tOwn=circuitViz.tOwn;
        const tRival=wrap01(tOwn+readCircuitGap()/CIRCUIT_LAP_S);
        const len=circuitViz.len,p=circuitViz.path;
        placeMarker(circuitViz.own,p,len,tOwn,0);
        placeMarker(circuitViz.ownT1,p,len,tOwn-.01,0);
        placeMarker(circuitViz.ownT2,p,len,tOwn-.02,0);
        placeMarker(circuitViz.rival,p,len,tRival,0);
        placeMarker(circuitViz.rivT1,p,len,tRival-.01,0);
        placeMarker(circuitViz.rivT2,p,len,tRival-.02,0);
        placeFlag(circuitViz.ownFlag,p,len,tOwn);
        placeFlag(circuitViz.rivFlag,p,len,tRival);
        const out=$('circuit-readout');
        if(out){
          const gap=readCircuitGap();
          const side=gap>0.005?'ahead':gap<-0.005?'behind':'alongside';
          const line=`Moving at ${fmt(readCircuitSpeed(),0)} km/h · rival ${fmt(Math.abs(gap),2)}s ${side}.`;
          if(line!==circuitViz.lastReadout){out.textContent=line;circuitViz.lastReadout=line;}
        }
      }catch(e){}
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    circuitViz.started=true;
  }catch(e){}
}
function highlightCircuit(result){
  try{
    if(!circuitViz||!result)return;
    const rec=String(result.recommendation||'');
    if(result.status==='abstain'||rec==='REASSESS'||rec==='NO_RECOMMENDATION')return;
    const hot=$('circuit-highlight');
    if(!hot||typeof hot.setAttribute!=='function')return;
    const t=circuitViz.tOwn||0;
    let t0=t,spanT=.08;
    if(rec==='ATTACK'){t0=t;spanT=.12;}
    else if(rec==='DEFEND'){t0=t-.12;spanT=.12;}
    else if(rec==='HOLD'||rec==='CONSERVE'){t0=t-.04;spanT=.08;}
    else return;
    const start=wrap01(t0)*circuitViz.len;
    const span=Math.max(12,spanT*circuitViz.len);
    const gap=Math.max(0,circuitViz.len-span);
    hot.setAttribute('stroke-dasharray',`${span} ${gap}`);
    hot.setAttribute('stroke-dashoffset',String(-start));
    if(hot.classList&&typeof hot.classList.add==='function'){
      hot.classList.add('is-hot');
      if(circuitHotTimer)clearTimeout(circuitHotTimer);
      circuitHotTimer=setTimeout(()=>{try{hot.classList.remove('is-hot');}catch(e){}},1000);
    }
  }catch(e){}
}
async function evaluate(save=false,req=null){const input=req||readRequest();const r=await api(`/v2/plan?save=${save}`,input);render(r,input);highlightCircuit(r);afterPlan(r,save);if(save)toast(`Decision #${r.evaluation_id} saved with input and policy.`);return r;}
function setView(name){document.querySelectorAll('.view').forEach(v=>v.hidden=v.id!==name+'-view');document.querySelectorAll('.nav').forEach(b=>{const on=b.dataset.view===name;b.classList.toggle('active',on);try{if(on)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}catch(e){}});try{document.body.classList.toggle('is-arena',name==='arena');document.body.classList.toggle('is-flow',name==='flow');document.body.classList.toggle('is-car',name==='car');}catch(e){}const names={pit:['PIT WALL','Next energy call','COMMIT, PROBE, HOLD or CONSERVE — or NO CALL if the picture is not safe.'],lab:['SCENARIO LAB','Three decision rules','Same start. Compare the full planner, HOLD-if-low, and greedy next-step.'],evidence:['EVIDENCE & HISTORY','Why this call','Rules, model facts, and saved calls you can reload.'],arena:['ENTER ARENA','Silverstone arena','Cars run from the live snapshot. COMMIT, PROBE, HOLD and CONSERVE change pace. Yellow and SC slow the field. Red stops.'],flow:['CALL FLOW','How a call is made','Snapshot in. Gates. Planner. Engineer to driver. How we tackle the rival.'],car:['CAR','Full car','The complete car stays in view. Road speed follows the snapshot and the next energy call.']};const meta=names[name]||names.pit;$('view-name').textContent=meta[0];$('page-title').textContent=meta[1];$('page-description').textContent=meta[2];if(name==='evidence')task(loadHistory);if(name==='arena'){ensureArena();refreshArenaInspect();}if(name==='flow'){refreshFlowLive();selectFlowNode(flowFocus||'flow-n-snap');fitFlowBoard();}try{if(typeof window!=='undefined'&&name==='car'&&typeof window.startCarCockpit==='function')window.startCarCockpit();if(typeof window!=='undefined'&&name!=='car'&&typeof window.stopCarCockpit==='function')window.stopCarCockpit();}catch(e){}}
async function loadHistory(){history=await api('/v2/history');$('history').innerHTML=history.length?history.map(h=>`<tr><td>#${h.id}</td><td>${esc(new Date(h.created).toLocaleString())}</td><td data-call="${esc(prettyCall(h.output.recommendation))}">${esc(prettyCall(h.output.recommendation))}</td><td>${fmt(h.input.state.own_energy_mj)} MJ</td><td>${fmt(h.output.latency_ms,1)} ms</td><td><button class="quiet" data-load="${h.id}">Inspect ↗</button></td></tr>`).join(''):'<tr><td colspan="6">No saved calls yet. Use “Save decision” on the pit wall.</td></tr>';$('history').querySelectorAll('[data-load]').forEach(btn=>btn.onclick=()=>{const h=history.find(h=>h.id===+btn.dataset.load);loadRequest(h.input);render(h.output,h.input);$('scenario-description').textContent=`Saved evaluation #${h.id}`;setView('pit');});}
function setLive(on,label){try{document.body.classList.toggle('is-live',!!on);$('connection').classList.toggle('is-live',!!on);}catch(e){}$('connection').textContent=label||(on?'API connected':'Local demo');const feed=$('feed-status');if(feed){feed.hidden=!on;if(on)feed.textContent='API connected · snapshot taken automatically';}}
function setTape(index,total,label){$('replay-progress').textContent=label?`${index} / ${total} ${label}`:`${index} / ${total}`;const fill=$('tape-fill');if(fill&&fill.style)fill.style.width=total>0?`${Math.min(100,index/total*100)}%`:'0%';}
async function init(){try{await api('/health');}catch(e){setLive(false,'Not connected');throw e;}try{scenarios=await api('/v2/scenarios');}catch(e){setLive(false, /API key/i.test(e.message||'')?'API key required':'Not connected');throw e;}setLive(!!apiSession,apiSession?'API connected':'Local demo');$('scenario').innerHTML=scenarios.map(s=>`<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('');replay=(await api('/v1/demo')).states;setTape(0,replay.length);loadRequest(scenarios[0].request);$('scenario-description').textContent=apiSession?scenarios[0].description:'Choose a dataset to analyse. Connect the API only when you have a backend key.';await evaluate();}
$('evaluate').onclick=()=>task(()=>evaluate());$('save').onclick=()=>task(()=>evaluate(true));$('demo-toggle').onclick=()=>{try{document.body.classList.toggle('is-manual');$('demo-toggle').textContent=document.body.classList.contains('is-manual')?'Hide demos':'Demo snapshots';}catch(e){}};
$('scenario').onchange=()=>task(async()=>{const s=scenarios.find(s=>s.id===$('scenario').value);loadRequest(s.request);$('scenario-description').textContent=s.description;await evaluate();});
document.querySelectorAll('.nav').forEach(b=>b.onclick=()=>setView(b.dataset.view));$('refresh-history').onclick=()=>task(loadHistory);
$('replay-step').onclick=()=>task(async()=>{if(replayIndex>=replay.length){toast('Replay finished. Reset to begin again.');return;}const req={state:replay[replayIndex],...(replayPolicy?{policy:replayPolicy}:{})};if(replayBelief)req.belief=replayBelief;loadRequest(req);const r=await evaluate(false,req);replayBelief=r.belief;replayIndex++;setTape(replayIndex,replay.length);$('scenario-description').textContent=`Tape frame ${replayIndex} of ${replay.length}. Playing history — the recorded race does not change.`;});
$('replay-reset').onclick=()=>{replayIndex=0;replayBelief=null;setTape(0,replay.length);toast('Replay cursor and belief reset.');};
$('import-file').onchange=()=>task(async()=>{const f=$('import-file').files[0];if(!f)return;if(f.size>2*1024*1024)throw Error('Choose a JSON file smaller than 2 MB.');const data=JSON.parse(await f.text());let req=data.request||data;if(data.states){if(!Array.isArray(data.states)||!data.states.length||data.states.length>2000)throw Error('Replay must contain 1 to 2,000 states.');const valid=await api('/v1/replay',{states:data.states,...(data.policy?{policy:data.policy}:{})});replay=data.states;replayPolicy=data.policy||null;replayIndex=0;replayBelief=null;setTape(0,replay.length,'imported frames');req={state:replay[0],...(data.policy?{policy:data.policy}:{})};}if(!req.state)throw Error('Expected {state: ...}, {request: ...}, or {states: [...]} JSON.');const r=await api('/v2/plan',req);loadRequest(req);render(r,req);$('scenario-description').textContent=`Imported: ${f.name}. Source fields are caller declarations.`;toast('JSON validated and loaded.');});
$('export').onclick=()=>{if(!currentResult)return;const b=new Blob([JSON.stringify({request:lastEvaluatedRequest,result:currentResult},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='race-strategy-decision.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
$('compare').onclick=()=>task(async()=>{if(!$('seed').reportValidity())return;const req=readRequest();$('compare').textContent='Simulating…';try{const r=await api('/v2/compare',{request:req,seed:Number($('seed').value),ticks:15});const colors=['#e24b4a','#2ee59d','#f0b429'];$('comparison-results').innerHTML=r.results.map((v,i)=>`<article class="panel comparison-card" data-lane="${i}"><p class="eyebrow">${String(i+1).padStart(2,'0')} / RULE</p><h3>${esc(prettyController(v.controller))}</h3><strong>${fmt(v.final_energy_mj)} <small style="display:inline">MJ remaining</small></strong><p>Gap at the end: ${fmt(v.final_gap_s,3)}s</p><small>${v.reserve_violations} times under reserve · ${v.switches} call changes</small></article>`).join('');for(const [id,key,unit] of [['compare-energy','energy_mj','Energy MJ'],['compare-gap','gap_s','Signed gap s']])chart(id,r.results.map((v,i)=>({name:v.controller,color:colors[i],points:v.trace.map(t=>({x:t.time_s,y:t[key]}))})),{unit,threshold:key==='energy_mj'?(req.policy?.reserve_mj??.6):null});$('comparison-note').textContent=`${r.duration_s}s simulated · Seed ${r.seed} · ${fmt(r.latency_ms,0)} ms. Red: full planner · Green: HOLD-if-low · Amber: greedy next-step. ${r.scope}`;}finally{$('compare').textContent='Run comparison ↗';}});
$('key-button').onclick=()=>$('key-dialog').showModal();$('key-dialog').addEventListener('close',()=>{if($('key-dialog').returnValue==='apply'){apiKey=$('api-key').value;apiSession=true;$('api-key').value='';task(init);}});
// An edited form must not leave an old result looking current.
$('state-form').addEventListener('input',()=>{$('decision-status').textContent='INPUT CHANGED · RE-EVALUATE';try{$('decision-status').dataset.kind='stale';}catch(e){}$('export').disabled=true;syncSnapshotReadouts();});
try{if(canSpeak()){speechSynthesis.addEventListener('voiceschanged',pickVoices);pickVoices();}}catch(e){}
try{$('arena-enter').onclick=()=>setView('arena');}catch(e){}
try{$('arena-to-pit').onclick=()=>setView('pit');}catch(e){}
try{$('arena-zoom').onclick=()=>{if(!arenaViz)return;arenaViz.follow=!arenaViz.follow;$('arena-zoom').textContent=arenaViz.follow?'Full circuit':'Follow car';updateArenaCamera();};}catch(e){}
try{$('arena-clock').onchange=()=>{syncArenaClockLabel();if(arenaViz)arenaViz.hud='';};}catch(e){}
try{$('arena-clock-up').onclick=()=>bumpArenaClock(1);}catch(e){}
try{$('arena-clock-down').onclick=()=>bumpArenaClock(-1);}catch(e){}
try{$('arena-pause').onclick=()=>toggleArenaPause();}catch(e){}
try{$('arena-evaluate').onclick=()=>task(()=>evaluate());}catch(e){}
try{FLOW_NODE_IDS.forEach(id=>{const el=$(id);if(el)el.onclick=()=>selectFlowNode(id);});}catch(e){}
try{$('flow-inspect').onclick=e=>{const t=e&&e.target;if(t&&t.dataset&&t.dataset.hop)selectFlowNode(t.dataset.hop);};}catch(e){}
try{$('flow-walk').onclick=()=>walkFlow();}catch(e){}
try{$('flow-reset').onclick=()=>resetFlow();}catch(e){}
try{$('flow-lane').onchange=()=>applyFlowLane();}catch(e){}
try{$('flow-to-pit').onclick=()=>setView('pit');}catch(e){}
try{$('flow-to-arena').onclick=()=>setView('arena');}catch(e){}
try{$('car-to-pit').onclick=()=>setView('pit');}catch(e){}
try{$('car-to-arena').onclick=()=>setView('arena');}catch(e){}
try{$('flow-speak').onclick=()=>speakFlowRadio();}catch(e){}
try{$('flow-open-related').onclick=()=>{const g=FLOW_META[flowFocus]&&FLOW_META[flowFocus].goto;setView(g||'pit');};}catch(e){}
try{if(typeof addEventListener==='function')addEventListener('resize',()=>{try{fitFlowBoard();}catch(e){}});}catch(e){}
try{$('arena-hit-own').onclick=()=>selectArenaCar('own');$('arena-hit-own').onkeydown=e=>{if(e&&(e.key==='Enter'||e.key===' ')){try{e.preventDefault();}catch(x){}selectArenaCar('own');}};}catch(e){}
try{$('arena-hit-rival').onclick=()=>selectArenaCar('rival');$('arena-hit-rival').onkeydown=e=>{if(e&&(e.key==='Enter'||e.key===' ')){try{e.preventDefault();}catch(x){}selectArenaCar('rival');}};}catch(e){}
try{if(typeof window!=='undefined')window.arenaLapInfo=arenaLapInfo;}catch(e){}
startCircuit();
startArena();
task(init);
