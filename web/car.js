'use strict';
(function(){
  const KW={COMMIT:120,PROBE:80,HOLD:40,CONSERVE:0,'NO CALL':0};
  const PACE={COMMIT:1.14,PROBE:1.06,HOLD:1,CONSERVE:.9,'NO CALL':1};
  const FLAG={GREEN:1,YELLOW:.7,VSC:.68,SC:.46,RED:0};
  let viz=null,running=false,paused=false,reduce=false,raf=0,lastTs=0,roadOff=0,frames=0;

  function $(id){return document.getElementById(id);}
  function num(id,fallback){
    const n=Number($(id)&&$(id).value);
    return Number.isFinite(n)?n:fallback;
  }
  function readCall(){
    const t=((($('action')&&$('action').textContent)||'NO CALL')+'').trim().toUpperCase();
    if(t==='COMMIT'||t==='PROBE'||t==='HOLD'||t==='CONSERVE')return t;
    return 'NO CALL';
  }
  function readSnap(){
    const call=readCall();
    const track=(($('track_status')&&$('track_status').value)||'GREEN')+'';
    const speed=Math.max(0,num('own_speed_kph',300));
    const gap=num('gap_s',0.7);
    const energy=num('own_energy_mj',2.4);
    let pace=0;
    if(speed>=30&&track!=='RED'){
      const flag=FLAG[track]!==undefined?FLAG[track]:1;
      pace=flag*(track==='GREEN'?(PACE[call]||1):1);
    }
    return {call,track,speed,gap,energy,pace,kw:KW[call]||0,moving:pace>0&&!paused&&!reduce};
  }
  function setText(id,text,key,val){
    const el=$(id);
    if(!el)return;
    if(el.textContent!==text)el.textContent=text;
    if(key&&el.dataset)el.dataset[key]=val;
  }
  function refreshHud(s){
    setText('car-hud-call',s.call,'call',s.call);
    const box=$('car-hud-call-box');
    if(box&&box.dataset)box.dataset.call=s.call;
    setText('car-hud-kw',s.kw+' kW');
    setText('car-hud-speed',Math.round(s.speed)+' km/h');
    setText('car-hud-gap',(Number.isFinite(s.gap)?s.gap.toFixed(2):'—')+' s');
    setText('car-hud-energy',(Number.isFinite(s.energy)?s.energy.toFixed(2):'—')+' MJ');
    let lap='1 / 52';
    try{
      if(typeof window!=='undefined'&&typeof window.arenaLapInfo==='function'){
        const L=window.arenaLapInfo('own');
        if(L)lap=L.finished?('FIN '+L.total+' / '+L.total):(L.current+' / '+L.total);
      }
    }catch(e){}
    setText('car-hud-lap',lap);
    setText('car-hud-flag',s.track,'flag',s.track);
    const flagBox=$('car-hud-flag-box');
    if(flagBox&&flagBox.dataset)flagBox.dataset.flag=s.track;
    let gate='HOLD STATION';
    if(reduce)gate='MOTION OFF';
    else if(paused)gate='PAUSED';
    else if(s.track==='RED')gate='RED · STOPPED';
    else if(s.speed<30)gate='PARKED';
    else if(s.moving)gate='RACING · '+Math.round(s.speed*s.pace)+' km/h';
    setText('car-hud-gate',gate,'live',s.moving?'1':'0');
    const gateBox=$('car-hud-gate-box');
    if(gateBox&&gateBox.dataset)gateBox.dataset.live=s.moving?'1':'0';
    const btn=$('car-pause');
    if(btn){
      btn.textContent=paused?'Resume':'Pause';
      if(btn.dataset)btn.dataset.paused=paused?'1':'';
      try{btn.setAttribute('aria-pressed',paused?'true':'false');}catch(e){}
    }
  }
  function tex(draw,repeatX,repeatY){
    const c=document.createElement('canvas');
    c.width=256;c.height=256;
    const g=c.getContext('2d');
    draw(g,c);
    const t=new THREE.CanvasTexture(c);
    t.wrapS=t.wrapT=THREE.RepeatWrapping;
    t.repeat.set(repeatX,repeatY);
    t.anisotropy=8;
    t.colorSpace=THREE.SRGBColorSpace;
    return t;
  }
  function asphalt(){
    return tex((g)=>{
      g.fillStyle='#2c2d32';
      g.fillRect(0,0,256,256);
      for(let i=0;i<5200;i++){
        const n=Math.random();
        g.fillStyle=n>.55?'#33343a':'#24252a';
        g.fillRect(Math.random()*256,Math.random()*256,1+(n>.9?1:0),1);
      }
    },6,48);
  }
  function kerb(){
    return tex((g)=>{
      for(let i=0;i<8;i++){
        g.fillStyle=i%2?'#f4f4f5':'#c73d3c';
        g.fillRect(0,i*32,256,32);
      }
    },1,28);
  }
  function dash(){
    return tex((g)=>{
      g.fillStyle='#2c2d32';
      g.fillRect(0,0,256,256);
      g.fillStyle='#e8e8ee';
      g.fillRect(104,0,48,88);
    },1,52);
  }
  function carbon(){
    return tex((g)=>{
      g.fillStyle='#141416';
      g.fillRect(0,0,256,256);
      g.strokeStyle='#1e1e22';
      g.lineWidth=2;
      for(let y=-32;y<288;y+=10){
        g.beginPath();g.moveTo(0,y);g.lineTo(256,y+64);g.stroke();
        g.beginPath();g.moveTo(256,y);g.lineTo(0,y+64);g.stroke();
      }
    },2,2);
  }
  function mat(color,metal,rough){
    return new THREE.MeshStandardMaterial({color,metalness:metal,roughness:rough});
  }
  function box(w,h,d,material){
    return new THREE.Mesh(new THREE.BoxGeometry(w,h,d),material);
  }
  function put(parent,mesh,x,y,z){
    mesh.position.set(x,y,z);
    parent.add(mesh);
    return mesh;
  }
  function buildTrack(scene){
    const dark=mat(0x0d0d10,.2,.55);
    const road=new THREE.Mesh(new THREE.PlaneGeometry(18,420),new THREE.MeshStandardMaterial({map:asphalt(),roughness:.95,metalness:0}));
    road.rotation.x=-Math.PI/2;
    road.position.set(0,-0.02,-40);
    scene.add(road);

    const centre=new THREE.Mesh(new THREE.PlaneGeometry(.28,420),new THREE.MeshStandardMaterial({map:dash(),roughness:.7,metalness:0,transparent:true}));
    centre.rotation.x=-Math.PI/2;
    centre.position.set(0,0.005,-40);
    scene.add(centre);

    const kerbMap=kerb();
    [-7.4,7.4].forEach(x=>{
      const k=new THREE.Mesh(new THREE.PlaneGeometry(.7,420),new THREE.MeshStandardMaterial({map:kerbMap,roughness:.55,metalness:0}));
      k.rotation.x=-Math.PI/2;
      k.position.set(x,0.01,-40);
      scene.add(k);
    });
    [-8.15,8.15].forEach(x=>{
      const wall=box(.18,.28,420,dark);
      wall.position.set(x,0.12,-40);
      scene.add(wall);
    });

    const markers=new THREE.Group();
    for(let i=0;i<18;i++){
      const z=20-i*16;
      const board=box(.5,.36,.04,mat(i%3===0?0xc73d3c:i%3===1?0xf0b429:0x8a8f98,.08,.55));
      board.position.set(-6.55,.34,z);
      markers.add(board);
      const post=box(.05,.3,.05,dark);
      post.position.set(-6.55,.15,z+.04);
      markers.add(post);
      const lamp=box(.07,.04,.07,mat(0xd8d8de,.2,.35));
      lamp.position.set(6.65,.06,z);
      markers.add(lamp);
    }
    scene.add(markers);

    const grass=new THREE.Mesh(new THREE.PlaneGeometry(90,420),mat(0x1a2218,0,.95));
    grass.rotation.x=-Math.PI/2;
    grass.position.set(0,-0.04,-40);
    scene.add(grass);

    for(let i=0;i<16;i++){
      const z=24-i*20;
      const hill=box(11+i%3,1.4+(i%4)*.45,9,mat(0x16181c,0,.9));
      hill.position.set((i%2?-1:1)*(17+i%5),0.55,z);
      scene.add(hill);
    }

    return {road,centre,kerbMap,markers};
  }
  function makeWheel(rubber,dark){
    const g=new THREE.Group();
    const tire=new THREE.Mesh(new THREE.CylinderGeometry(.33,.33,.36,22),rubber);
    tire.rotation.z=Math.PI/2;
    g.add(tire);
    const rim=new THREE.Mesh(new THREE.CylinderGeometry(.2,.2,.38,16),dark);
    rim.rotation.z=Math.PI/2;
    g.add(rim);
    const hub=new THREE.Mesh(new THREE.CylinderGeometry(.08,.08,.4,10),mat(0x9aa0a8,.75,.25));
    hub.rotation.z=Math.PI/2;
    g.add(hub);
    return g;
  }
  function buildCar(){
    const carbonMap=carbon();
    const body=mat(0x1a1a1e,.38,.4);
    body.map=carbonMap;
    const paint=mat(0xc8ccd2,.74,.26);
    const dark=mat(0x121216,.22,.5);
    const rubber=mat(0x111114,.05,.86);
    const chrome=mat(0xd4d4d8,.88,.16);
    const pad=mat(0x2ee59d,.15,.4);
    const accent=mat(0xe24b4a,.2,.45);
    const glass=mat(0x6a7380,.45,.12);

    const car=new THREE.Group();
    const wheels=[];

    put(car,box(1.42,.05,5.15,dark),0,.06,0);
    put(car,box(.95,.28,1.55,body),0,.28,.05);
    put(car,box(.62,.16,.7,dark),0,.42,.05);

    const cover=new THREE.Mesh(new THREE.CylinderGeometry(.2,.28,1.55,12),paint);
    cover.rotation.x=Math.PI/2;
    put(car,cover,0,.52,.95);
    put(car,box(.34,.28,.42,paint),0,.62,1.45);
    put(car,box(.22,.34,.28,dark),0,.82,1.42);

    const nose=new THREE.Mesh(new THREE.CylinderGeometry(.05,.2,1.85,12),paint);
    nose.rotation.x=Math.PI/2;
    put(car,nose,0,.3,-1.85);
    put(car,box(.08,.12,1.55,accent),0,.38,-1.7);

    put(car,box(1.92,.035,.42,dark),0,.2,-2.72);
    put(car,box(1.7,.025,.18,dark),0,.24,-2.52);
    put(car,box(.05,.2,.46,paint),-.94,.3,-2.72);
    put(car,box(.05,.2,.46,paint),.94,.3,-2.72);

    put(car,box(.42,.32,1.55,paint),-.62,.36,.35);
    put(car,box(.42,.32,1.55,paint),.62,.36,.35);
    put(car,box(.18,.2,1.1,body),-.78,.22,.4);
    put(car,box(.18,.2,1.1,body),.78,.22,.4);

    const halo=new THREE.Mesh(new THREE.TorusGeometry(.42,.028,10,36,Math.PI*1.15),chrome);
    halo.rotation.x=Math.PI/2.08;
    put(car,halo,0,.95,.02);
    put(car,box(.055,.04,.55,chrome),0,1.05,.18);
    const helmet=new THREE.Mesh(new THREE.SphereGeometry(.13,14,12),mat(0xe24b4a,.12,.48));
    put(car,helmet,0,.72,.08);
    put(car,box(.16,.04,.14,dark),0,.8,.16);

    [-.52,.52].forEach(x=>{
      put(car,box(.03,.18,.03,dark),x,.78,.22);
      put(car,box(.2,.08,.04,dark),x*1.15,.88,.24);
      put(car,box(.14,.05,.02,glass),x*1.15,.88,.27);
    });

    put(car,box(1.05,.045,.32,dark),0,.92,2.12);
    put(car,box(.95,.03,.16,dark),0,.86,2.0);
    put(car,box(.05,.34,.38,paint),-.52,.86,2.1);
    put(car,box(.05,.34,.38,paint),.52,.86,2.1);
    put(car,box(.7,.03,.12,dark),0,.22,2.05);
    put(car,box(.28,.08,.22,pad),0,.48,1.95);

    [[-.78,-1.72],[.78,-1.72],[-.8,1.28],[.8,1.28]].forEach(function(p,i){
      const w=makeWheel(rubber,dark);
      w.position.set(p[0],.33,p[1]);
      car.add(w);
      wheels.push(w);
      if(i<2){
        put(car,box(.08,.06,.55,dark),p[0]*.35,.18,p[1]+.15);
      }
    });

    return {car,wheels,pad};
  }
  function resize(v){
    const stage=$('car-stage');
    const canvas=$('car-canvas');
    if(!stage||!canvas||!v)return;
    const w=Math.max(16,stage.clientWidth||canvas.clientWidth||800);
    const h=Math.max(16,stage.clientHeight||canvas.clientHeight||480);
    v.camera.aspect=w/h;
    v.camera.updateProjectionMatrix();
    v.renderer.setSize(w,h,false);
    v.renderer.setPixelRatio(Math.min(2,window.devicePixelRatio||1));
  }
  function disposeViz(){
    try{if(raf)cancelAnimationFrame(raf);}catch(e){}
    raf=0;
    if(viz&&viz.renderer){
      try{viz.renderer.dispose();}catch(e){}
    }
    viz=null;
  }
  function tick(ts){
    if(!viz)return;
    if(!running){raf=0;return;}
    raf=requestAnimationFrame(tick);
    try{step(ts);}catch(e){try{const c=$('car-canvas');if(c&&c.dataset)c.dataset.err=String(e&&e.message||e);}catch(x){}}
  }
  function step(ts){
    if(!lastTs)lastTs=ts;
    const dt=Math.min(.05,(ts-lastTs)/1000);
    lastTs=ts;
    const s=readSnap();
    refreshHud(s);
    if(s.moving){
      const scroll=(s.speed*s.pace)/70*dt;
      roadOff+=scroll;
      const maps=[viz.road&&viz.road.material&&viz.road.material.map,viz.centre&&viz.centre.material&&viz.centre.material.map,viz.kerbMap];
      if(maps[0])maps[0].offset.y=-roadOff;
      if(maps[1])maps[1].offset.y=-roadOff*1.25;
      if(maps[2])maps[2].offset.y=-roadOff*1.55;
      maps.forEach(function(m){if(m)m.needsUpdate=true;});
      if(viz.markers){
        viz.markers.position.z+=scroll*42;
        if(viz.markers.position.z>16)viz.markers.position.z-=16;
      }
      const steer=Math.sin(ts/720)*.08+Math.max(-.16,Math.min(.16,(s.gap||0)*.04));
      viz.car.rotation.y=steer;
      viz.car.position.x=steer*.35;
      viz.car.position.y=Math.sin(ts/75)*0.012*(s.speed/300);
      const spin=(s.speed*s.pace)/18*dt;
      (viz.wheels||[]).forEach(function(w){w.rotation.x+=spin;});
      viz.camera.position.set(3.35+steer*.2,1.42+Math.sin(ts/90)*0.02,4.15);
      viz.camera.lookAt(viz.car.position.x,.42,.05);
    }else if(viz.car){
      viz.camera.lookAt(viz.car.position.x,.42,.05);
    }
    if(viz.pad&&viz.pad.color)viz.pad.color.set(s.call==='COMMIT'?0x2ee59d:s.call==='PROBE'?0xf0b429:0x3a3a40);
    frames++;
    try{
      const canvas=$('car-canvas');
      if(canvas&&canvas.dataset){
        canvas.dataset.frames=String(frames);
        canvas.dataset.off=roadOff.toFixed(3);
        canvas.dataset.moving=s.moving?'1':'0';
      }
    }catch(e){}
    viz.renderer.render(viz.scene,viz.camera);
  }
  function startCarCockpit(){
    try{
      if(typeof THREE==='undefined')return;
      running=true;
      try{reduce=typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches;}catch(e){}
      if(viz&&viz.kind!=='fullcar')disposeViz();
      if(viz){
        resize(viz);
        lastTs=0;
        if(!raf)raf=requestAnimationFrame(tick);
        return;
      }
      const canvas=$('car-canvas');
      if(!canvas)return;
      const scene=new THREE.Scene();
      scene.background=new THREE.Color(0x151820);
      scene.fog=new THREE.Fog(0x151820,28,170);
      const camera=new THREE.PerspectiveCamera(42,16/9,.08,240);
      camera.position.set(3.35,1.42,4.15);
      camera.lookAt(0,.42,.05);
      const renderer=new THREE.WebGLRenderer({canvas,antialias:true,preserveDrawingBuffer:true});
      renderer.outputColorSpace=THREE.SRGBColorSpace;
      renderer.toneMapping=THREE.NoToneMapping;
      const key=new THREE.DirectionalLight(0xf4f1ea,1.45);
      key.position.set(7,11,5);
      scene.add(key);
      const fill=new THREE.DirectionalLight(0x8a90a0,.42);
      fill.position.set(-5,3,6);
      scene.add(fill);
      const rim=new THREE.DirectionalLight(0xd0d2d6,.35);
      rim.position.set(-3,2,-8);
      scene.add(rim);
      scene.add(new THREE.AmbientLight(0x6a6c72,.55));
      const track=buildTrack(scene);
      const built=buildCar();
      scene.add(built.car);
      viz={kind:'fullcar',scene,camera,renderer,road:track.road,centre:track.centre,kerbMap:track.kerbMap,markers:track.markers,car:built.car,wheels:built.wheels,pad:built.pad};
      resize(viz);
      lastTs=0;
      refreshHud(readSnap());
      if(typeof addEventListener==='function')addEventListener('resize',()=>{try{if(running)resize(viz);}catch(e){}});
      if(!raf)raf=requestAnimationFrame(tick);
    }catch(e){try{const c=$('car-canvas');if(c&&c.dataset)c.dataset.err=String(e&&e.message||e);}catch(x){}}
  }
  function stopCarCockpit(){
    running=false;
    lastTs=0;
  }
  function togglePause(){
    paused=!paused;
    refreshHud(readSnap());
  }
  try{
    if(typeof window!=='undefined'){
      window.startCarCockpit=startCarCockpit;
      window.stopCarCockpit=stopCarCockpit;
    }
  }catch(e){}
  try{
    const btn=$('car-pause');
    if(btn)btn.onclick=()=>togglePause();
  }catch(e){}
})();
