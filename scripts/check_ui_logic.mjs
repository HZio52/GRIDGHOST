/* No browser automation: exercises the actual client script against the live API
   with a minimal DOM test double. Does not verify layout or browser rendering. */
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const base=process.argv[2]||'http://127.0.0.1:8000';
const html=fs.readFileSync('web/index.html','utf8');
class Element{
 constructor(id=''){this.id=id;this.value='';this.hidden=false;this.disabled=false;this.style={};this.dataset={};this.listeners={};this.files=[];this.classList={toggle(){}};this.options=[];this._html='';this.textContent='';}
 set innerHTML(s){this._html=s;if(this.id==='scenario')this.options=[...s.matchAll(/<option value="([^"]+)"/g)].map(m=>({value:m[1]}));}
 get innerHTML(){return this._html;}
 add(o){this.options.push(o);}
 reportValidity(){return true;}
 addEventListener(name,fn){this.listeners[name]=fn;}
 querySelectorAll(){return [];}
 click(){return this.onclick?.();}
 showModal(){}
}
const els=Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element(m[1])]));
for(const m of html.matchAll(/<input[^>]*id="([^"]+)"[^>]*value="([^"]*)"/g))els[m[1]].value=m[2];
els.stages.options=[{value:'3'},{value:'6'},{value:'8'}];
const views=['pit','lab','evidence'].map(k=>els[k+'-view']);
const navs=['pit','lab','evidence'].map(k=>{const e=new Element();e.dataset.view=k;return e;});
const source=new Element();
const document={getElementById:id=>{assert(els[id],`Missing HTML id ${id}`);return els[id];},
 querySelectorAll:q=>q==='.view'?views:q==='.nav'?navs:[],querySelector:q=>q==='.source-tag'?source:null,
 createElement:()=>new Element()};
const context=vm.createContext({document,console,fetch:(path,opts)=>fetch(new URL(path,base),opts),
 structuredClone,Blob,URL,setTimeout,clearTimeout,Option:function(text,value){this.value=value;}});
vm.runInContext(fs.readFileSync('web/app.js','utf8'),context);
async function idle(){for(let i=0;i<1000;i++){if(!vm.runInContext('busy',context))return;await new Promise(r=>setTimeout(r,10));}throw Error('UI task timeout');}
function noError(){assert(els.error.hidden,els.error.textContent);}
await idle();noError();assert.equal(els.action.textContent,'NO CALL');
assert.equal(els['decision-status'].textContent,'NO CALL');
els.scenario.value='yellow_flag';await els.scenario.onchange();noError();assert.equal(els.action.textContent,'NO CALL');
els.scenario.value='low_energy';await els.scenario.onchange();noError();assert.equal(els.action.textContent,'HOLD');
assert(els['energy-chart'].innerHTML.includes('<svg'));
await els.save.onclick();noError();assert(els.toast.textContent.includes('saved'));
await els['refresh-history'].onclick();noError();assert(els.history.innerHTML.includes('HOLD'));
await els['replay-step'].onclick();noError();assert(els['replay-progress'].textContent.startsWith('1 /'));
await els.compare.onclick();noError();assert(els['comparison-results'].innerHTML.includes('HOLD-if-low'));
assert(els['compare-energy'].innerHTML.includes('<svg'));
console.log('PASS: actual client script + live API: initial plan, caution abstention, save, history, replay, simulation, SVG creation.');
console.log('LIMIT: minimal DOM double; no rendered browser or native file-dialog verification.');
