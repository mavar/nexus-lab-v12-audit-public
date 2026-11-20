'use strict';
const RULES=[
  {id:'momentum_10s',name:'1. Движение за 10 секунд — рекомендую для первого запуска',summary:'Сравниваем цену сейчас и 10 секунд назад. Если рост выше заданного порога — пробуем покупку.',inputs:'Две цены и один порог; ни модели, ни стакана глубже лучших цен.'},
  {id:'ema_cross',name:'2. Две средние',summary:'Если быстрая средняя поднимается выше медленной, пробуем покупку.',inputs:'Два числа обновляются с каждой новой ценой.'},
  {id:'prior_range_break',name:'3. Пробой недавнего максимума',summary:'Пробуем купить, когда цена выше максимума за предыдущую минуту. Текущую цену в этот максимум не включаем.',inputs:'Минутная история цен; это всё ещё простой расчёт.'}
];
const HOLDOUT={startUtc:'2026-11-23T00:00:00Z',endUtcExclusive:'2026-11-30T00:00:00Z',status:'future_capture_unconfirmed'};
function initLab(){
  const a=$('tabLabels'),b=$('tabLab'),tabs=[a,b];let chosen;
  $('labTitle').textContent=`Первый пробный запуск — ${DATA.pair}`;
  $('labTrainDates').textContent=`${DATA.days[0].date} — ${DATA.days.at(-1).date}`;
  const update=()=>{$('labParams').textContent=`В черновике будут настройки со вкладки «Разметка»: ${sideName(mode)} · до ${waitText(settings.seconds)} · цель ${price(settings.goal)}% · предел падения ${price(settings.dip)}%.`};
  function show(lab){
    $('labelPanel').hidden=lab;$('labPanel').hidden=!lab;
    for(const [i,t] of tabs.entries()){const active=Boolean(i)===lab;t.setAttribute('aria-selected',String(active));t.tabIndex=active?0:-1;t.classList.toggle('primary',active)}
    if(lab)update();else render();
  }
  a.onclick=()=>show(false);b.onclick=()=>show(true);
  for(const [i,t] of tabs.entries())t.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;const next=e.key==='Home'?0:e.key==='End'?1:1-i;show(Boolean(next));tabs[next].focus();e.preventDefault()};
  for(const r of RULES){
    const label=document.createElement('label'),input=document.createElement('input'),copy=document.createElement('div');
    input.type='radio';input.name='labRule';input.value=r.id;
    copy.innerHTML=`<b>${r.name}</b><p>${r.summary}</p><p class="small">${r.inputs}</p>`;
    input.onchange=()=>{chosen=r;$('labSave').disabled=false};label.append(input,copy);$('labChoices').append(label);
  }
  $('labSave').onclick=()=>{
    if(!chosen)return;
    const plan={status:'draft_not_a_run',pair:DATA.pair,rule:chosen.id,direction:mode,labelSettings:{...settings},
      training:{startUtc:new Date(origin).toISOString(),endUtcExclusive:new Date(origin+WEEK).toISOString(),quoteDays:DATA.days.map(d=>({date:d.date,sha256:d.source.sha256??null}))},holdout:HOLDOUT,
      execution:{feePerSidePct:.05,delayMs:300,onePosition:true,overnight:false,exitPolicy:'goal_stop_time_to_be_frozen_before_holdout'}};
    const href=URL.createObjectURL(new Blob([JSON.stringify(plan,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=href;link.download='nexus-test-plan-draft.json';link.click();setTimeout(()=>URL.revokeObjectURL(href),1000);
  };
}
initLab();
