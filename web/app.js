'use strict';
const $=id=>document.getElementById(id);
const stateFields=['own_speed_kph','rival_speed_kph','gap_s','own_energy_mj','data_age_s','track_status'];
let scenarios=[],currentRequest=null,currentResult=null,lastEvaluatedRequest=null,replay=[],replayIndex=0,replayBelief=null,replayPolicy=null,apiKey='',busy=false,history=[],lastSpokenAction='',lastWasAbstain=false,radio=null,radioVoices={engineer:null,driver:null},engineerTalking=false,noiseNode=null,speechUnlocked=false;
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
async function task(fn){if(busy)return;busy=true;error('');unlockSpeech();const controls=['evaluate','save','compare','replay-step','scenario','import-file','replay-reset'];controls.forEach(x=>$(x).disabled=true);try{await resumeRadio();await fn();}catch(e){error(e.message||String(e));}finally{busy=false;controls.forEach(x=>$(x).disabled=false);}}
function loadRequest(req){currentRequest=structuredClone(req);const s=req.state;$('own_energy_mj').max=req.policy?.capacity_mj??4;$('stage-unit').textContent=`${req.planning?.stage_s??4} seconds each`;stateFields.forEach(k=>$(k).value=s[k]??(k==='data_age_s'?0:'GREEN'));$('terminal_buffer_mj').value=req.planning?.terminal_buffer_mj??.25;const stages=req.planning?.stages??6;if(![...$('stages').options].some(o=>+o.value===stages))$('stages').add(new Option(`${stages} stages`,stages));$('stages').value=stages;replayBelief=null;}
function readRequest(){if(!$('state-form').reportValidity())throw Error('Check the highlighted input values.');const req=structuredClone(currentRequest||{state:{timestamp_s:1}});stateFields.forEach(k=>req.state[k]=k==='track_status'?$(k).value:Number($(k).value));req.planning={...req.planning,stages:Number($('stages').value),terminal_buffer_mj:Number($('terminal_buffer_mj').value)};if(currentRequest?.state){const old=currentRequest.state;if(req.state.own_speed_kph!==old.own_speed_kph||req.state.rival_speed_kph!==old.rival_speed_kph)req.state.speed_source='user_supplied';if(req.state.gap_s!==old.gap_s)req.state.gap_source='user_supplied';if(req.state.own_energy_mj!==old.own_energy_mj)req.state.energy_source='user_supplied';}delete req.belief;return req;}
function chart(target,series,{threshold=null,unit='',startX=0}={}){const el=$(target);if(!series.length||!series.some(s=>s.points.length)){el.innerHTML='<p>No forecast available for this state.</p>';return;}const W=700,H=245,L=48,R=18,T=18,B=32;const all=series.flatMap(s=>s.points);let lo=Math.min(...all.map(p=>p.y),threshold??Infinity),hi=Math.max(...all.map(p=>p.y),threshold??-Infinity);if(lo===hi){lo-=.5;hi+=.5;}const pad=(hi-lo)*.15;lo-=pad;hi+=pad;const xmax=Math.max(...all.map(p=>p.x),1);const x=v=>L+(v-startX)/(xmax-startX||1)*(W-L-R),y=v=>H-B-(v-lo)/(hi-lo)*(H-T-B);let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(unit)} chart"><title>${esc(series.map(s=>s.name).join(', '))}; ${esc(unit)}</title>`;for(let i=0;i<=4;i++){let v=lo+(hi-lo)*i/4;svg+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="#dce1e5"/><text x="${L-9}" y="${y(v)+4}" text-anchor="end" fill="#66717b" font-size="12">${v.toFixed(1)}</text>`;}for(let i=0;i<=4;i++){let v=xmax*i/4;svg+=`<text x="${x(v)}" y="${H-8}" text-anchor="middle" fill="#66717b" font-size="12">${v.toFixed(0)}s</text>`;}if(threshold!==null)svg+=`<line x1="${L}" x2="${W-R}" y1="${y(threshold)}" y2="${y(threshold)}" stroke="#bd761d" stroke-dasharray="5 6"/>`;series.forEach(s=>{const path=s.points.map((p,i)=>`${i?'L':'M'}${x(p.x).toFixed(2)},${y(p.y).toFixed(2)}`).join(' ');svg+=`<path d="${path}" fill="none" stroke="${s.color}" stroke-width="2.5" ${s.dash?'stroke-dasharray="5 5"':''}/>`;});svg+='</svg>';el.innerHTML=svg;}
function render(result,req){currentResult=result;lastEvaluatedRequest=structuredClone(req);$('export').disabled=false;$('action').textContent=prettyCall(result.recommendation);$('action').style.fontSize=result.status==='abstain'?'2rem':'';$('action').style.color=result.status==='abstain'?'#ffbf83':'';$('reason').textContent=prettyReason(result);$('decision-status').textContent=result.status==='advisory'?'NEEDS REVIEW':'NO CALL';$('horizon').textContent=`${result.horizon_s} SECOND LOOKAHEAD`;$('latency').textContent=`${fmt(result.latency_ms,1)} ms`;const p=req.policy||{};const required=(p.reserve_mj??.6)+(req.planning?.terminal_buffer_mj??.25);$('required').textContent=`${fmt(required)} MJ`;const best=result.candidates.find(c=>c.valid&&c.action===result.recommendation);$('finish').textContent=best?`${fmt(best.conservative_energy_mj)} MJ`:'—';$('sequence').innerHTML=best?best.trace.map(t=>`<div class="stage" data-action="${esc(t.action)}">${esc(prettyCall(t.action))}<span>+${t.time_s}s</span></div>`).join(''):'';
$('candidates').innerHTML=result.candidates.length?result.candidates.map(c=>`<tr class="${c.action===result.recommendation?'selected':''}"><td>${esc(prettyCall(c.action))}</td><td>${fmt(c.score_s,3)}</td><td>${fmt(c.conservative_energy_mj)}</td><td>${fmt(c.gap_s,3)}${c.valid?'s':''}</td><td class="${c.valid?'':'rejected'}">${c.valid?(c.action===result.recommendation?'Recommended':'Feasible'):esc(prettyText(c.rejection_reasons.join('; ')))}</td></tr>`).join(''):'<tr><td colspan="5">Input gate failed. Candidate forecasts were not generated.</td></tr>';
$('belief').innerHTML=[['slow','Slower'],['neutral','Matched'],['fast','Faster']].map(([k,label])=>`<div class="belief-row"><span>${label}</span><div class="belief-bar"><div style="width:${result.belief[k]*100}%"></div></div><span>${(result.belief[k]*100).toFixed(0)}%</span></div>`).join('');
chart('energy-chart',best?[{name:'Expected energy',color:'#e4002b',points:[{x:0,y:req.state.own_energy_mj},...best.trace.map(t=>({x:t.time_s,y:t.energy_mj}))]},{name:'Conservative energy',color:'#526c8e',dash:true,points:[{x:0,y:Math.max(0,req.state.own_energy_mj-(req.state.energy_uncertainty_mj??.1))},...best.trace.map(t=>({x:t.time_s,y:t.conservative_energy_mj}))]}]:[],{threshold:required,unit:'Energy MJ'});
$('rules').innerHTML=[['Reserve to keep',`${fmt(p.reserve_mj??.6)} MJ`],['Must-keep at plan end',`${fmt(required)} MJ`],['Max deploy power',`${p.max_deploy_kw??120} kW`],['Energy budget this window',`${fmt(req.planning?.deployment_budget_mj??2)} MJ`],['Max snapshot age',`${p.max_data_age_s??5}s`],['Track status','GREEN only (racing)'],['Rules status','Unverified model policy']].map(([a,b])=>`<div class="rule"><span>${esc(a)}</span><strong>${esc(b)}</strong></div>`).join('');
const src=req.state.speed_source??'synthetic';document.querySelector('.source-tag').innerHTML=`${esc(src==='synthetic'?'SYNTHETIC SCENARIO':src.toUpperCase()+' INPUT')}<span>Energy: ${esc(req.state.energy_source??'simulated')} · Rules unverified</span>`;
renderMl(result);
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
async function evaluate(save=false,req=null){const input=req||readRequest();const r=await api(`/v2/plan?save=${save}`,input);render(r,input);afterPlan(r,save);if(save)toast(`Decision #${r.evaluation_id} saved with input and policy.`);return r;}
function setView(name){document.querySelectorAll('.view').forEach(v=>v.hidden=v.id!==name+'-view');document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b.dataset.view===name));const names={pit:['PIT WALL','Next energy call','COMMIT, PROBE, HOLD or CONSERVE — or NO CALL if the picture is not safe.'],lab:['SCENARIO LAB','Three decision rules','Same start. Compare the full planner, HOLD-if-low, and greedy next-step.'],evidence:['EVIDENCE & HISTORY','Why this call','Rules, model facts, and saved calls you can reload.']};$('view-name').textContent=names[name][0];$('page-title').textContent=names[name][1];$('page-description').textContent=names[name][2];if(name==='evidence')task(loadHistory);}
async function loadHistory(){history=await api('/v2/history');$('history').innerHTML=history.length?history.map(h=>`<tr><td>#${h.id}</td><td>${esc(new Date(h.created).toLocaleString())}</td><td>${esc(prettyCall(h.output.recommendation))}</td><td>${fmt(h.input.state.own_energy_mj)} MJ</td><td>${fmt(h.output.latency_ms,1)} ms</td><td><button class="quiet" data-load="${h.id}">Inspect ↗</button></td></tr>`).join(''):'<tr><td colspan="6">No saved calls yet. Use “Save decision” on the pit wall.</td></tr>';$('history').querySelectorAll('[data-load]').forEach(btn=>btn.onclick=()=>{const h=history.find(h=>h.id===+btn.dataset.load);loadRequest(h.input);render(h.output,h.input);$('scenario-description').textContent=`Saved evaluation #${h.id}`;setView('pit');});}
async function init(){await api('/health');$('connection').textContent='Backend connected';scenarios=await api('/v2/scenarios');$('scenario').innerHTML=scenarios.map(s=>`<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('');replay=(await api('/v1/demo')).states;loadRequest(scenarios[0].request);$('scenario-description').textContent=scenarios[0].description;await evaluate();}
$('evaluate').onclick=()=>task(()=>evaluate());$('save').onclick=()=>task(()=>evaluate(true));$('scenario').onchange=()=>task(async()=>{const s=scenarios.find(s=>s.id===$('scenario').value);loadRequest(s.request);$('scenario-description').textContent=s.description;await evaluate();});
document.querySelectorAll('.nav').forEach(b=>b.onclick=()=>setView(b.dataset.view));$('refresh-history').onclick=()=>task(loadHistory);
$('replay-step').onclick=()=>task(async()=>{if(replayIndex>=replay.length){toast('Replay finished. Reset to begin again.');return;}const req={state:replay[replayIndex],...(replayPolicy?{policy:replayPolicy}:{})};if(replayBelief)req.belief=replayBelief;loadRequest(req);const r=await evaluate(false,req);replayBelief=r.belief;replayIndex++;$('replay-progress').textContent=`${replayIndex} / ${replay.length} frames`;$('scenario-description').textContent=`Tape frame ${replayIndex} of ${replay.length}. Playing history — the recorded race does not change.`;});
$('replay-reset').onclick=()=>{replayIndex=0;replayBelief=null;$('replay-progress').textContent=`0 / ${replay.length} frames`;toast('Replay cursor and belief reset.');};
$('import-file').onchange=()=>task(async()=>{const f=$('import-file').files[0];if(!f)return;if(f.size>2*1024*1024)throw Error('Choose a JSON file smaller than 2 MB.');const data=JSON.parse(await f.text());let req=data.request||data;if(data.states){if(!Array.isArray(data.states)||!data.states.length||data.states.length>2000)throw Error('Replay must contain 1 to 2,000 states.');const valid=await api('/v1/replay',{states:data.states,...(data.policy?{policy:data.policy}:{})});replay=data.states;replayPolicy=data.policy||null;replayIndex=0;replayBelief=null;$('replay-progress').textContent=`0 / ${replay.length} imported frames`;req={state:replay[0],...(data.policy?{policy:data.policy}:{})};}if(!req.state)throw Error('Expected {state: ...}, {request: ...}, or {states: [...]} JSON.');const r=await api('/v2/plan',req);loadRequest(req);render(r,req);$('scenario-description').textContent=`Imported: ${f.name}. Source fields are caller declarations.`;toast('JSON validated and loaded.');});
$('export').onclick=()=>{if(!currentResult)return;const b=new Blob([JSON.stringify({request:lastEvaluatedRequest,result:currentResult},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='race-strategy-decision.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
$('compare').onclick=()=>task(async()=>{if(!$('seed').reportValidity())return;const req=readRequest();$('compare').textContent='Simulating…';try{const r=await api('/v2/compare',{request:req,seed:Number($('seed').value),ticks:15});const colors=['#e4002b','#526c8e','#bd761d'];$('comparison-results').innerHTML=r.results.map((v,i)=>`<article class="panel comparison-card" style="border-top:2px solid ${colors[i]}"><h3>${esc(prettyController(v.controller))}</h3><strong>${fmt(v.final_energy_mj)} <small style="display:inline">MJ remaining</small></strong><p>Gap at the end: ${fmt(v.final_gap_s,3)}s</p><small>${v.reserve_violations} times under reserve · ${v.switches} call changes</small></article>`).join('');for(const [id,key,unit] of [['compare-energy','energy_mj','Energy MJ'],['compare-gap','gap_s','Signed gap s']])chart(id,r.results.map((v,i)=>({name:v.controller,color:colors[i],points:v.trace.map(t=>({x:t.time_s,y:t[key]}))})),{unit,threshold:key==='energy_mj'?(req.policy?.reserve_mj??.6):null});$('comparison-note').textContent=`${r.duration_s}s simulated · Seed ${r.seed} · ${fmt(r.latency_ms,0)} ms. Red: full planner · Blue: HOLD-if-low · Orange: greedy next-step. ${r.scope}`;}finally{$('compare').textContent='Run comparison ↗';}});
$('key-button').onclick=()=>$('key-dialog').showModal();$('key-dialog').addEventListener('close',()=>{if($('key-dialog').returnValue==='apply'){apiKey=$('api-key').value;$('api-key').value='';task(init);}});
// An edited form must not leave an old result looking current.
$('state-form').addEventListener('input',()=>{$('decision-status').textContent='INPUT CHANGED · RE-EVALUATE';$('export').disabled=true;});
try{if(canSpeak()){speechSynthesis.addEventListener('voiceschanged',pickVoices);pickVoices();}}catch(e){}
task(init);
