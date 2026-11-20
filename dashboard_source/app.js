'use strict';
const $=id=>document.getElementById(id), WEEK=DATA.days.length*DAY, HOUR=3600000;
const origin=Date.parse(DATA.days[0].date+'T00:00:00Z');
const utc=t=>new Date(origin+t).toISOString().slice(11,23), time=t=>new Date(origin+t).toISOString().slice(0,19).replace('T',' ');
const pct=v=>`${v>0?'+':''}${v.toFixed(3)}%`, price=v=>v.toLocaleString('ru-RU',{maximumFractionDigits:8}), sideName=m=>({long:'лонг',short:'шорт',both:'лонг + шорт'})[m];
const waitText=s=>[s>=3600?`${Math.floor(s/3600)} ч`:'',s%3600>=60?`${Math.floor(s%3600/60)} мин`:'',s%60?`${s%60} с`:''].filter(Boolean).join(' ');
const opt=(label,value)=>new Option(label,value), pause=()=>new Promise(r=>setTimeout(r,0));
const inputDate=t=>new Date(origin+t).toISOString().slice(0,16);
const sorted=a=>[...new Set(a)].sort((a,b)=>a-b);
let settings={goal:.1,dip:.05,seconds:120}, scope={a:2*DAY,b:3*DAY}, view={...scope}, selected=2*DAY+3943000, mode='long', focusSide=1;
let showRows=[], showTimes=[], allSignals=[], ranking=[], ratingScope, cachedDay=-1, cachedQuotes, cachedEngines, cachedMode, frame, chartsId=0, timer, searchId=0, worker;
const presetDates=DATA.days.map(d=>d.date);
function updateInputs(){
  const list=$('goals');list.replaceChildren();
  for(const goal of sorted([...GOALS,settings.goal])){const label=document.createElement('label'),r=document.createElement('input');r.type='radio';r.name='goal';r.value=goal;r.checked=goal===settings.goal;r.onchange=()=>setParams({...settings,goal});label.append(r,goal===0?'Больше нуля':`От +${price(goal)}%`);list.append(label)}
  if(!Array.from($('dip').options).some(a=>Number(a.value)===settings.dip))$('dip').add(opt(`${price(settings.dip)}%`,settings.dip));
  $('dip').value=String(settings.dip);
  const k=Math.max(0,TIMES.findIndex(x=>x>=settings.seconds)-1);$('horizon').value=Math.round(k*100+100*(settings.seconds-TIMES[k])/(TIMES[k+1]-TIMES[k]));
  $('horizonValue').textContent=waitText(settings.seconds);
  $('horizon').setAttribute('aria-valuetext',waitText(settings.seconds));
  $('applied').textContent=`На графике: ${settings.goal?'цель от +'+price(settings.goal)+'%':'любая чистая прибыль'} · до ${waitText(settings.seconds)} · падение до ${price(settings.dip)}%.`;
}
function setParams(p){settings={goal:Number(p.goal),dip:Number(p.dip),seconds:Number(p.seconds)};updateInputs();scheduleRefresh()}
function packRange(a,b){return {a,b}}
function scopeText(s){return `${time(s.a)} — ${time(s.b)} UTC`}
function setScope(){
  const kind=$('scope').value,d=Number($('date').value)*DAY,h=Number($('hour').value)*HOUR;
  $('dateLabel').hidden=kind==='week'||kind==='custom';$('hourLabel').hidden=kind!=='hour';for(const id of ['fromLabel','toLabel','setRange'])$(id).hidden=kind!=='custom';
  let a=d,b=d+DAY;if(kind==='week'){a=0;b=WEEK}else if(kind==='hour'){a+=h;b=a+HOUR}else if(kind==='custom'){a=Date.parse($('from').value+'Z')-origin;b=Date.parse($('to').value+'Z')-origin;if(!(a>=0&&a<b&&b<=WEEK)){$('job').textContent='Укажите начало и конец внутри доступной недели (UTC).';return}}
  scope=packRange(a,b);view={...scope};if(selected<a||selected>=b)selected=a+Math.min(60000,(b-a)/2);
  $('scopeHeading').textContent={day:'на день',hour:'на час',week:'на неделю',custom:'на отрезок'}[kind];scheduleRefresh();
}
function direction(){mode=$('side').value;if(mode!=='both')focusSide=mode==='long'?1:-1;$('detailSide').disabled=mode!=='both';$('detailSide').value=String(focusSide);scheduleRefresh()}
async function quotes(i){if(cachedDay!==i){const q=await unpack(DATA.days[i]);if(cachedDay!==i){cachedDay=i;cachedQuotes=q;cachedEngines=null}}return cachedQuotes}
function shifted(r,offset){return [r[0]+offset,r[1]+offset,r[2],r[3],r[4]+offset,r[5],r[6],r[7]+offset,r[8]]}
function isGood(r){return r[2]>0&&r[2]>=settings.goal/100}
function scheduleRefresh(){chartsId++;clearTimeout(timer);$('chartStatus').textContent='Пересчитываю входы…';$('signalCount').textContent='…';$('money').textContent='';timer=setTimeout(refresh,70);render()}
async function refresh(){
  const id=chartsId,s={...settings},m=mode;let active=Math.floor(selected/DAY),rows=[],total=0,count=0,log=0;
  try{
    for(const {i,a,b} of parts(scope)){
      if(id!==chartsId)return;const q=await quotes(i);if(id!==chartsId)return;
      if(!cachedEngines||cachedMode!==m){cachedEngines=dayModes(q,m);cachedMode=m}
      const labels=labelMode(cachedEngines,s.seconds,s.dip/100,a,b,true),v=scores(labels,[s.goal])[0];
      log+=v.log;total+=v.possible;count+=v.count;
      // Keep successful rows for the entire view, and every admissible exit for the inspected day.
      for(const r of labels)if(i===active||r[2]>0&&r[2]>=s.goal/100)rows.push(shifted(r,i*DAY));
      await pause();
    }
    await quotes(active);if(id!==chartsId)return;
    showRows=rows;showTimes=rows.map(r=>r[0]);allSignals=rows.filter(isGood);
    $('signalCount').textContent=total.toLocaleString('ru-RU');
    const cap=100*Math.exp(log);$('money').innerHTML=`Отбор задним числом · ${count} сделок · ${pct(Math.expm1(log)*100)} · <b class="${cap.toFixed(2)>100?'gain':''}">100 → ${cap.toFixed(2)} USDT</b>`;
    $('chartStatus').textContent=`${scopeText(scope)} · ${sideName(mode)}. Сумма относится к выбранному периоду.`;
    render();
  }catch(e){if(id===chartsId)$('chartStatus').textContent='Не удалось загрузить график: '+e.message}
}
function focusRow(){const t=Math.round(selected/1000)*1000,i=lower(showTimes,t);return showRows.slice(i,i+2).find(r=>r[0]===t&&r[3]===focusSide)}
function render(){
  cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{
    const selectedDay=Math.floor(selected/DAY),f=focusRow(),start=f?.[4]??selected+300,pad=Math.max(5000,Math.min(120000,settings.seconds*60)),win={a:start,b:Math.min((selectedDay+1)*DAY,scope.b,start+settings.seconds*1000)};
    chartFor($('main'),view,allSignals,f,win);
    chartFor($('zoom'),{a:Math.max(selectedDay*DAY,start-pad),b:Math.min((selectedDay+1)*DAY,Math.max(start+1000,win.b+pad))},[],f,win);
    const row=(k,v)=>`<dt>${k}</dt><dd>${v}</dd>`;
    $('detail').innerHTML=`<h2>${focusSide===1?'Вход по покупке':'Условный шорт'}</h2><p class="sub">${time(selected).slice(0,19)} UTC</p>`+(f?`<p class="${f[2]>0?'gain':''}">${pct(f[2]*100)} чистыми · ${isGood(f)?'цель достигнута':'цель не достигнута'}</p><dl>${row('Вход',`${utc(f[4])} · ${price(f[5])}`)}${row('Выход',`${utc(f[1])} · ${price(f[6])}`)}${row('Движение против входа',`${(f[8]*100).toFixed(4)}%`)}</dl>`:'<p>Для этого направления и секунды нет допустимого выхода или полных данных.</p>')+'<p class="small">Падение считаем по цене выхода от момента входа. Для шорта движение против позиции — рост цены. Комиссии входят в итог.</p>';
  });
}
function chartFor(canvas,r,marks,f,win){
  if(r.b<=r.a)return;const series=[],gaps=[];
  for(const {i,a,b} of parts(r)){
    const base=i*DAY,day=DATA.days[i];if(!day)continue;
    for(const [x,y] of day.gaps)if(y>=a&&x<=b)gaps.push([x+base,y+base]);
    let set=[];
    if(cachedDay===i&&cachedQuotes&&r.b-r.a<=DAY){
      const {ct,cb,ca}=cachedQuotes,lo=Math.max(0,lower(ct,a)-1),hi=Math.min(ct.length,lower(ct,b+1)+1);
      for(let k=lo;k<hi;k++)set.push([ct[k]+base,cb[k],ca[k]]);
      // In a flat segment preserve the known price at the right boundary, never past a feed gap.
      if(set.length&&set[0][0]<r.a&&!day.gaps.some(([x,y])=>x<a&&y>a))set[0][0]=r.a;
    }else set=day.overview.filter(p=>p[0]>=a-60000&&p[0]<=b+60000).map(p=>[p[0]+base,p[1],p[2]]);
    series.push(set);
  }
  chart(canvas,r,series,gaps,marks,f,win);
}
function selectAt(t,s=focusSide){const previous=Math.floor(selected/DAY);selected=Math.max(scope.a,Math.min(scope.b-1000,Math.round(t/1000)*1000));focusSide=s;$('detailSide').value=String(s);if(Math.floor(selected/DAY)!==previous)scheduleRefresh();else render()}
function bindChart(){
  const canvas=$('main');let drag;
  const project=e=>view.a+(e.offsetX-72)/(canvas.clientWidth-86)*(view.b-view.a);
  const clamp=(a,span)=>{span=Math.max(Math.min(5000,scope.b-scope.a),Math.min(scope.b-scope.a,span));a=Math.max(scope.a,Math.min(scope.b-span,a));return {a,b:a+span}};
  canvas.onpointerdown=e=>{if(e.button!==0)return;drag={x:e.offsetX,a:view.a,span:view.b-view.a,moved:false};canvas.setPointerCapture(e.pointerId)};
  canvas.onpointermove=e=>{if(!drag)return;const delta=e.offsetX-drag.x;if(Math.abs(delta)>3)drag.moved=true;if(drag.moved){view=clamp(drag.a-delta/(canvas.clientWidth-86)*drag.span,drag.span);render()}};
  canvas.onpointerup=e=>{if(!drag)return;const moved=drag.moved;drag=null;if(!moved)selectAt(project(e))};canvas.onpointercancel=()=>{drag=null};
  canvas.addEventListener('wheel',e=>{e.preventDefault();const t=project(e),k=e.deltaY<0?.76:1.32;view=clamp(t+(view.a-t)*k,(view.b-view.a)*k);render()},{passive:false});
  canvas.ondblclick=()=>{view={...scope};render()};
}
function showWinner(r,size){const w=$('winner');w.hidden=false;w.innerHTML=`<dl><dt>Цель чистыми</dt><dd>${r.goal?price(r.goal)+'%':'больше нуля'}</dd><dt>Ждать выхода до</dt><dd>${waitText(r.seconds)}</dd><dt>Падение до</dt><dd>${price(r.dip)}%</dd></dl><p>Найдено сделок: <b>${r.count}</b></p><p class="gain">100 → ${r.capital.toFixed(2)} USDT <small>(${pct(r.capital-100)})</small></p><p class="sub">${r.daily.map(v=>DATA.days[v.day].date.slice(5)+': '+pct(v.net)).join(' · ')}</p><p class="small">Проверено сочетаний: ${size.toLocaleString('ru-RU')}</p>`}
function receiveRank(id,rank,s,m){if(id!==searchId||!rank)return;stopUI();ranking=rank;ratingScope={...s,mode:m};$('openRating').disabled=false;$('job').textContent=`${scopeText(s)} · ${sideName(m)} · рейтинг готов.`;if(rank[0]?.count){apply(rank[0]);showWinner(rank[0],rank.length)}else {$('winner').hidden=true;$('job').textContent+=' Удачных сделок по ограничениям нет.'}}
function apply(r){
  // Applying a row restores its scope and direction as well as the three trade settings.
  if(scope.a!==ratingScope.a||scope.b!==ratingScope.b){$('scope').value='custom';$('from').value=inputDate(ratingScope.a);$('to').value=inputDate(ratingScope.b);setScope()}
  $('side').value=ratingScope.mode;direction();setParams(r);view={...scope};showWinner(r,ranking.length);
}
function stopUI(){$('cancel').hidden=true;$('progress').hidden=true;$('run').disabled=false}
function cancelSearch(){searchId++;worker?.terminate();worker=null;stopUI();$('job').textContent='Поиск остановлен.'}
async function runSearch(){
  const fields=['optDip','optGoal','optTime'].map($),invalid=fields.find(x=>!x.checkValidity());if(invalid){invalid.reportValidity();return}
  const val=fields.map((x,i)=>x.value===''?[1,0,360][i]:Number(x.value));
  const limit={dip:val[0],goal:val[1],seconds:Math.floor(val[2]*60+1e-9)},s={...scope},m=mode,id=++searchId;
  $('progress').hidden=false;$('progress').value=0;$('run').disabled=true;$('cancel').hidden=false;$('job').textContent='Подготовка котировок…';$('winner').hidden=true;
  let fallbackStarted=false;
  const progress=(n,total,i)=>{if(id===searchId){$('progress').max=total;$('progress').value=n;$('job').textContent=`${DATA.days[i].date} · ${n} из ${total} групп по сроку и падению. В каждой группе проверяем все цели.`}};
  const fail=e=>{if(id===searchId){stopUI();$('job').textContent='Не удалось закончить поиск: '+e}};
  const fallback=async()=>{
    if(fallbackStarted||id!==searchId)return;fallbackStarted=true;worker?.terminate();worker=null;
    try{receiveRank(id,await search(DATA.days,s,m,limit,progress,()=>id!==searchId),s,m)}catch(e){fail(e.message)}
  };
  try{
    const source=ENGINE_SOURCE+'\nself.onmessage=async ({data:d})=>{try{const r=await search(d.days,d.scope,d.mode,d.limit,(...p)=>postMessage({p}));postMessage({r})}catch(e){postMessage({error:e.message})}}';
    const url=URL.createObjectURL(new Blob([source],{type:'text/javascript'}));try{worker=new Worker(url)}finally{URL.revokeObjectURL(url)}
    worker.onerror=e=>{e.preventDefault();fallback()};worker.onmessage=({data:d})=>{if(id!==searchId||fallbackStarted)return;if(d.error){fallback();return}if(d.p)progress(...d.p);else{worker?.terminate();worker=null;receiveRank(id,d.r,s,m)}};
    worker.postMessage({days:DATA.days,scope:s,mode:m,limit});
  }catch{fallback()}
}
const filterFields=[['goal','Цель, %'],['seconds','Ожидание, мин'],['dip','Падение, %'],['capital','Итог из 100'],['count','Сделок']];
function filterRows(){
  const tests=filterFields.map(([key])=>[key,...['min','max'].map(m=>{const v=$(`${key}-${m}`).value;return v===''?null:Number(v)})]);
  const entries=ranking.map((r,i)=>[r,i]).filter(([r])=>tests.every(([k,a,b])=>{const z=k==='seconds'?r[k]/60:r[k];return (a===null||z>=a)&&(b===null||z<=b)}));
  const key=$('sort').value,sign=['capital','count'].includes(key)?-1:1;entries.sort((a,b)=>sign*(a[0][key]-b[0][key])||a[1]-b[1]);
  $('ratingCount').textContent=`Показано ${entries.length.toLocaleString('ru-RU')} из ${ranking.length.toLocaleString('ru-RU')}`;
  $('ratingRows').innerHTML=entries.map(([r,i])=>`<tr><td class="${r.capital>100?'gain':''}">${r.capital.toFixed(2)} USDT</td><td>${price(r.goal)}</td><td>${waitText(r.seconds)}</td><td>${price(r.dip)}</td><td>${r.count}</td><td><button data-index="${i}">Применить</button></td></tr>`).join('');
}
function init(){
  $('title').textContent=`${DATA.pair} · недельная разметка`;
  const broken=DATA.days.reduce((n,d)=>n+d.gaps.reduce((a,[x,y])=>a+y-x,0),0);
  $('coverage').textContent=`${presetDates[0]} — ${presetDates.at(-1)} UTC · ${DATA.days.reduce((n,d)=>n+d.n,0).toLocaleString('ru-RU')} котировок · ${Math.round(broken/60000)} мин разрывов. Пропуски не заполняются.`;
  for(let i=0;i<DATA.days.length;i++)$('date').add(opt(presetDates[i],i));$('date').value='2';
  for(let i=0;i<24;i++)$('hour').add(opt(`${String(i).padStart(2,'0')}:00`,i));$('hour').value='1';
  for(const d of DIPS)$('dip').add(opt(`${price(d)}%`,d));
  $('from').value=inputDate(scope.a);$('to').value=inputDate(scope.b);for(const key of ['from','to']){$(key).min=inputDate(0);$(key).max=inputDate(WEEK)}
  for(const id of ['scope','date','hour'])$(id).onchange=setScope;$('setRange').onclick=setScope;$('side').onchange=direction;
  $('horizon').oninput=()=>{const v=Number($('horizon').value),i=Math.min(TIMES.length-2,Math.floor(v/100));settings.seconds=Math.round(TIMES[i]+(v-i*100)/100*(TIMES[i+1]-TIMES[i]));$('horizonValue').textContent=waitText(settings.seconds);scheduleRefresh()};$('horizon').onchange=updateInputs;
  $('dip').onchange=()=>setParams({...settings,dip:Number($('dip').value)});
  $('prev').onclick=()=>selectAt(selected-1000);$('next').onclick=()=>selectAt(selected+1000);$('detailSide').onchange=()=>selectAt(selected,Number($('detailSide').value));
  $('nextSignal').onclick=()=>{const n=allSignals.find(r=>r[0]>selected)||allSignals[0];if(n)selectAt(n[0],n[3])};
  $('run').onclick=runSearch;$('cancel').onclick=cancelSearch;
  $('ratingFilters').innerHTML=filterFields.map(([key,name])=>`<label>${name}<div><input type="number" step="any" placeholder="от" aria-label="${name}: от" id="${key}-min"><input type="number" step="any" placeholder="до" aria-label="${name}: до" id="${key}-max"></div></label>`).join('');
  $('ratingFilters').oninput=filterRows;$('sort').onchange=filterRows;$('clearFilters').onclick=()=>{$('ratingFilters').querySelectorAll('input').forEach(i=>i.value='');filterRows()};
  $('openRating').onclick=()=>{$('ratingContext').textContent=`${scopeText(ratingScope)} · ${sideName(ratingScope.mode)} · задним числом. Падение — предел на одну позицию.`;filterRows();$('rating').showModal()};$('closeRating').onclick=()=>$('rating').close();
  $('ratingRows').onclick=e=>{const key=e.target.closest('[data-index]')?.dataset.index;if(key!==undefined){apply(ranking[Number(key)]);$('rating').close()}};
  bindChart();window.addEventListener('resize',render);updateInputs();setScope();direction();
}
try{init()}catch(e){$('chartStatus').textContent='Не удалось открыть страницу: '+e.message}
