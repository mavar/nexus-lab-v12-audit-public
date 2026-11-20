"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { components } from "@/lib/api";
import { axisValues, defaults, fields, MODELS as LEARN_MODELS, POINTS_HINT, START_HINT, type Axis, type Key } from "@/lib/learning-controls";

type Input = components["schemas"]["RunInput"];
type Result = components["schemas"]["RunResult"] | components["schemas"]["History"];
type Learn = components["schemas"]["LearnInput"];
type Job = components["schemas"]["LearnJob"];
type Trade = components["schemas"]["Trade"];
type Quote = components["schemas"]["QuotePoint"];
type Rule = Input["rule"];

const RULES: { id: Rule; label: string }[] = [
  {id:"momentum_10s", label:"Рост за несколько секунд"},
  {id:"ema_cross", label:"Пересечение двух средних"},
  {id:"prior_range_break", label:"Пробой недавнего максимума"},
];
const initial = {rule:"momentum_10s" as Rule, lookback:10, thresholdPct:.05, fast:8, slow:32, takePct:.1, stopPct:.2, holdSeconds:120, startBalance:100};
const DIRECTIONS={long:"Лонг",short:"Шорт",both:"Оба"};
const initialLearn = {model:"logistic" as NonNullable<Learn["model"]>,direction:"long" as keyof typeof DIRECTIONS,targetPct:.10,dipPct:.05,holdSeconds:120,stopPct:.2,confidencePct:20,complexity:1,startBalance:100,volumeSeconds:60,extraSlipPct:0,tradeFeePct:.05};
const money = (v:number) => v.toLocaleString("ru-RU",{minimumFractionDigits:2,maximumFractionDigits:2});
const signed = (v:number) => `${v>0?"+":""}${money(v)}`;
const fmt = (v:number) => new Date(v).toISOString().slice(5,16).replace("T"," ");
const precise = (v:number) => new Date(v).toISOString().slice(11,23);
const reason = {target:"Цель",stop:"Стоп",dip:"Предел падения",time:"Время",gap:"Разрыв",session:"Конец дня"};
const inputStyle="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-base text-slate-950 outline-offset-2";

function Hint({text,label="Подсказка"}:{text:string;label?:string}) {
  const id=useId();
  return <span className="group relative inline-block align-middle text-xs font-normal text-slate-500">
    <button type="button" aria-label={label} aria-describedby={id} onKeyDown={e=>{if(e.key==="Escape")e.currentTarget.blur()}} className="cursor-help rounded-full border border-slate-300 px-1.5 py-0.5 focus-visible:ring-2">?</button>
    <span id={id} role="tooltip" className="fixed inset-x-4 bottom-4 z-30 hidden rounded-xl border border-slate-200 bg-white p-3 leading-relaxed text-slate-700 shadow-lg group-hover:block group-focus-within:block sm:absolute sm:inset-auto sm:top-full sm:right-0 sm:w-56">{text}</span>
  </span>;
}

function NumberField({label,value,change,min,max,step=1,hint}:{label:string;value:number;change:(n:number)=>void;min:number;max:number;step?:number|string;hint?:string}){
  const id=useId();
  return <div className="grid gap-1.5 text-sm font-medium text-slate-700"><div><label htmlFor={id}>{label}</label>{hint&&<> <Hint text={hint} label={"Подсказка: "+label}/></>}</div><input id={id} className={inputStyle} type="number" required value={Number.isFinite(value)?value:""} min={min} max={max} step={step} onChange={e=>change(e.target.valueAsNumber)}/></div>
}

function Plot({quotes,trades,balance,initialTime,initialBalance,detail=false}:{quotes:Quote[];trades:Trade[];balance?:boolean;initialTime?:number;initialBalance?:number;detail?:boolean}){
  const entries=trades.map(t=>({time:t.entryTime,price:t.entryPrice}));
  const exits=trades.map(t=>({time:t.exitTime,price:t.exitPrice,pnl:t.pnl}));
  const positiveExits=exits.filter(t=>t.pnl>0);
  const negativeExits=exits.filter(t=>t.pnl<0);
  const flatExits=exits.filter(t=>t.pnl===0);
  const equity:Quote[]=balance?[{time:initialTime??0,price:initialBalance??0},...trades.map(t=>({time:t.exitTime,price:t.balance}))]:quotes;
  const prices=(balance?equity:[...quotes,...entries,...exits]).flatMap(p=>p.price==null?[]:[p.price]);
  if(!equity.length||!prices.length)return <div className="grid h-40 place-items-center rounded-xl bg-slate-50 text-sm text-slate-500">Нет котировок на этом отрезке.</div>;
  const min=prices.reduce((a,b)=>Math.min(a,b),Infinity),max=prices.reduce((a,b)=>Math.max(a,b),-Infinity),pad=Math.max((max-min)*.08,Math.abs(max)*.0002);
  const trade=detail?trades[0]:undefined;
  return <div className="h-56 w-full sm:h-72" role="img" aria-label={balance?"Баланс по закрытым сделкам":"Цена, входы и выходы"}>
    <ResponsiveContainer width="100%" height="100%"><ComposedChart data={equity} margin={{top:9,right:11,bottom:5,left:3}}>
      <CartesianGrid stroke="#e1e8f0" strokeDasharray="4 4"/><XAxis dataKey="time" type="number" domain={["dataMin","dataMax"]} tickFormatter={detail?precise:fmt} minTickGap={30} tick={{fontSize:11}}/><YAxis domain={[min-pad,max+pad]} width={59} tickFormatter={money} tick={{fontSize:11}}/>
      <Tooltip labelFormatter={t=>detail?precise(Number(t)):fmt(Number(t))+" UTC"} formatter={v=>money(Number(v))+" USDT"}/>
      {balance?<Area name="Баланс" dataKey="price" type="stepAfter" fill="#dbeafe" stroke="#135dcc" strokeWidth={2} dot={false} isAnimationActive={false}/>:<Line name="Цена" dataKey="price" stroke="#335f86" strokeWidth={1.45} dot={false} isAnimationActive={false} connectNulls={false}/>}
      {!balance&&entries.length>0&&<Scatter name="Вход" data={entries} dataKey="price" fill="#335f86" shape="triangle" isAnimationActive={false}/>}
      {!balance&&positiveExits.length>0&&<Scatter name="Прибыльный выход" data={positiveExits} dataKey="price" fill="#15803d" stroke="#fff" shape="diamond" isAnimationActive={false}/>}
      {!balance&&negativeExits.length>0&&<Scatter name="Убыточный выход" data={negativeExits} dataKey="price" fill="#be123c" stroke="#fff" shape="cross" isAnimationActive={false}/>}
      {!balance&&flatExits.length>0&&<Scatter name="Выход в ноль" data={flatExits} dataKey="price" fill="#64748b" shape="circle" isAnimationActive={false}/>}
      {trade&&<ReferenceLine x={trade.entryTime} stroke="#078451" strokeDasharray="4 3"/>}{trade&&<ReferenceLine x={trade.exitTime} stroke="#a33a78" strokeDasharray="4 3"/>}
    </ComposedChart></ResponsiveContainer>
  </div>;
}

function Metric({label,value,foot,hint,tone=""}:{label:string;value:string;foot?:string;hint:string;tone?:string}){
  return <div className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5"><div className="text-[13px] font-medium text-slate-600">{label} <Hint text={hint} label={"Подсказка: "+label}/></div><div className={`mt-1 break-words text-[clamp(25px,3.2vw,43px)] leading-tight font-bold tracking-tight tabular-nums ${tone}`}>{value}</div>{foot&&<div className="mt-1 text-xs text-slate-500">{foot}</div>}</div>;
}

export default function Home(){
  const [dataMode,setDataMode]=useState<string|null>(null);
  useEffect(()=>{
    fetch("/api/v1/health").then(r=>r.ok?r.json():null)
      .then(status=>{if(status)setDataMode(status.dataMode)}).catch(()=>{});
  },[]);
  const [tab,setTab]=useState<"test"|"labels">("test"),[labelsSeen,setLabelsSeen]=useState(false),[cfg,setCfg]=useState(initial);
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[result,setResult]=useState<Result|null>(null),[page,setPage]=useState(0),[selected,setSelected]=useState<Trade|null>(null),[detail,setDetail]=useState<Quote[]>([]);
  const [learning,setLearning]=useState(true),[lc,setLc]=useState(initialLearn),[job,setJob]=useState<Job|null>(null),[frozen,setFrozen]=useState(""),[freezing,setFreezing]=useState(false);
  const tradeCounts=useMemo(()=>{
    const counts={wins:0,losses:0,flat:0};
    for(const trade of result?.trades??[]){
      if(trade.pnl>0) counts.wins++;
      else if(trade.pnl<0) counts.losses++;
      else counts.flat++;
    }
    return counts;
  },[result]);
  const [auto,setAuto]=useState(true),[ranges,setRanges]=useState(()=>defaults(initialLearn.model)),[shown,setShown]=useState(50),[cancelling,setCancelling]=useState(false);
  const rows=fields(lc.model);
  const total=rows.reduce((count,row)=>count*axisValues(row,ranges[row.key]).length,1);
  const changeAxis=(key:Key,part:keyof Axis,n:number)=>setRanges(prev=>({...prev,[key]:{...prev[key],[part]:n}}));
  const field=<K extends keyof typeof initial>(key:K,value:(typeof initial)[K])=>setCfg(s=>({...s,[key]:value}));
  const stage=result?.openPosition?"Баланс по закрытым":"Итоговый баланс";
  const profitClass=result&&result.pnl>0?"text-emerald-700":result&&result.pnl<0?"text-rose-700":"";
  const current=useMemo(()=>result?.trades.slice(page*25,(page+1)*25)??[],[result,page]);
  const best=job?.best, settingsResult=best?.config, baseResult=result&&"config" in result?result.config:null;
  const lf=<K extends keyof typeof initialLearn>(key:K,value:(typeof initialLearn)[K])=>setLc(s=>({...s,[key]:value}));
  useEffect(()=>{
    if(!selected)return;
    const controller=new AbortController(),day=Math.floor(selected.entryTime/86400000)*86400000;
    const start=Math.max(day,selected.entryTime-5000),end=Math.min(day+86400000,selected.exitTime+5001);
    fetch(`/api/v1/quotes?start=${start}&end=${end}`,{signal:controller.signal}).then(r=>r.ok?r.json():[]).then(setDetail).catch(()=>{});
    return ()=>controller.abort();
  },[selected]);
  async function jsonResponse(response:Response){const value=await response.json();if(!response.ok)throw Error(typeof value.detail==="string"?value.detail:value.detail?.[0]?.msg??"Проверь настройки.");return value}
  const run=async(e:React.FormEvent)=>{
    e.preventDefault();setError("");setBusy(true);setCancelling(false);setSelected(null);setResult(null);setPage(0);setJob(null);setFrozen("");setShown(50);
    try{
      if(learning){
        const body:Learn={...lc,optimize:auto,search:auto?ranges:null};
        let state:Job=await jsonResponse(await fetch("/api/v1/learning",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}));
        setJob(state);
        while(state.state==="running"){
          await new Promise(r=>setTimeout(r,350));
          state=await jsonResponse(await fetch(`/api/v1/learning/${state.id}`,{cache:"no-store"}));setJob(state);
        }
        if(state.state==="error")throw Error(state.error??"Не удалось обучить модель.");
        if(state.result)setResult(state.result);
        const w=state.best?.config;
        if(auto&&w&&state.qualified) setLc(s=>({...s,targetPct:w.targetPct??s.targetPct,dipPct:w.dipPct??s.dipPct,holdSeconds:w.holdSeconds??s.holdSeconds,stopPct:w.stopPct??s.stopPct,confidencePct:w.confidencePct??s.confidencePct,complexity:w.complexity??s.complexity,volumeSeconds:w.volumeSeconds??s.volumeSeconds}));
        return;
      }
      const body:Input=cfg;
      const response=await fetch("/api/v1/runs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      setResult(await jsonResponse(response));
    }catch(e){setError(e instanceof Error?e.message:"Не удалось выполнить прогон.");}finally{setBusy(false)}
  };
  async function cancel(){if(!job)return;setCancelling(true);try{await jsonResponse(await fetch(`/api/v1/learning/${job.id}/cancel`,{method:"POST"}))}catch(e){setError(e instanceof Error?e.message:"Не удалось остановить.");setCancelling(false)}}
  async function freeze(){if(!job)return;setError("");setFreezing(true);try{const v=await jsonResponse(await fetch(`/api/v1/learning/${job.id}/freeze`,{method:"POST"}));setFrozen(`Модель сохранена · ${String(v.id).slice(0,8)} · ${v.holdout}`)}catch(e){setError(e instanceof Error?e.message:"Не удалось сохранить модель.")}finally{setFreezing(false)}}
  return <main className="mx-auto max-w-[1460px] px-4 py-5 sm:px-7 sm:py-8">
    <header className="flex flex-wrap items-end justify-between gap-3"><div><div className="text-xs font-bold tracking-widest text-blue-700 uppercase">Nexus · локальная лаборатория</div><h1 className="mt-1 text-3xl font-bold tracking-tight sm:text-4xl">SOLUSDT</h1></div><p className="text-sm text-slate-500">14–20 июня 2026 · UTC</p></header>
    {dataMode==="synthetic"&&<p role="status" className="mt-3 rounded-xl border border-amber-300 bg-amber-50 p-3 font-semibold text-amber-950">Демонстрация · искусственные цены</p>}
    <nav className="my-5 flex flex-wrap gap-2" aria-label="Разделы"><Button variant="outline" aria-pressed={tab==="labels"} onClick={()=>{setLabelsSeen(true);setTab("labels")}}>Разметка</Button><Button variant={tab==="test"?"default":"outline"} aria-pressed={tab==="test"} onClick={()=>setTab("test")}>Тесты алгоритмов</Button></nav>
    {labelsSeen&&<iframe hidden={tab!=="labels"} title="Прежняя разметка SOLUSDT" src="/label-review" className="min-h-[84vh] w-full rounded-xl border border-slate-200 bg-white"/>}
    <div hidden={tab!=="test"}>
    <div className="mb-3 flex flex-wrap gap-2"><Button variant={learning?"default":"outline"} disabled={busy} onClick={()=>{setLearning(true);setResult(null);setJob(null);setFrozen("")}}>Обучение на разметке</Button><Button variant={!learning?"default":"outline"} disabled={busy} onClick={()=>{setLearning(false);setResult(null);setJob(null);setFrozen("")}}>Простые правила</Button></div>
    {learning&&<div className="mb-3 grid gap-2 sm:grid-cols-3"><div className="rounded-xl bg-blue-50 p-3"><b>1. Учим: 14–17 июня</b><div className="text-xs text-slate-600">На размеченных входах</div></div><div className="rounded-xl bg-blue-50 p-3"><b>2. Сравниваем: 18–20 июня</b><div className="text-xs text-slate-600">Подбор, ещё не финальный тест</div></div><div className="rounded-xl bg-slate-200 p-3"><b>3. Проверка: 23–29 ноября</b><div className="text-xs text-slate-600">Будущие котировки не подключены</div></div></div>}
    <Card className="border-slate-200 bg-white"><CardHeader><CardTitle className="text-xl">Параметры прогона <Hint text={learning?"Сначала модель учится на старых примерах. Потом пробует торговать на других днях. В тесте команда на покупку или продажу идёт 0,3 секунды.":"Тест правила без обучения. Комиссия 0,05% за вход и за выход. Команда идёт 0,3 секунды."}/></CardTitle></CardHeader>
      <CardContent><form onSubmit={run} className="grid gap-4"><fieldset disabled={busy} className="contents">
      {learning?<>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Режим прогона">
          <Button type="button" variant={auto?"default":"outline"} aria-pressed={auto} onClick={()=>setAuto(true)}>Автоподбор</Button>
          <Button type="button" variant={auto?"outline":"default"} aria-pressed={!auto} onClick={()=>setAuto(false)}>Один прогон</Button>
          <Hint label="Подсказка: режим прогона" text="Автоподбор перебирает все сочетания показанных чисел. Один прогон обучает и проверяет один набор — числа, которые ты ввёл."/>
        </div>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Направление сделок">
          {(Object.keys(DIRECTIONS) as Array<keyof typeof DIRECTIONS>).map(direction=><Button key={direction} type="button" disabled={direction!=="long"} variant={lc.direction===direction?"default":"outline"} aria-pressed={lc.direction===direction} onClick={()=>lf("direction",direction)}>{DIRECTIONS[direction]}</Button>)}
          <Hint label="Подсказка: направление сделок" text="Лонг ищет рост, шорт — падение. Для шорта нужны цены, комиссии и выплаты по фьючерсу MEXC. Сейчас есть данные обычной покупки и продажи SOL."/>
          <span className="text-xs text-slate-600">Для шорта нужны данные фьючерса MEXC.</span>
        </div>
        <div className="grid max-w-2xl gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5 text-sm font-medium text-slate-700"><div><label htmlFor="learn-model">Модель</label> <Hint label="Подсказка: модель" text="Выбираешь способ, которым программа учится отличать удачные входы от остальных. Автоподбор меняет настройки выбранной модели. Чтобы сравнить модели, запусти каждую отдельно."/></div><select id="learn-model" className={inputStyle} value={lc.model} onChange={e=>{const model=e.target.value as typeof lc.model;setLc(x=>({...x,model,complexity:model==="tree"?3:1}));setRanges(x=>({...x,complexity:defaults(model).complexity}))}}>{Object.entries(LEARN_MODELS).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></div>
          <NumberField label="Стартовый баланс, USDT" value={lc.startBalance} change={n=>lf("startBalance",n)} min={1} max={1000000} step={.01} hint={START_HINT}/>
        </div>
        <div className="grid max-w-2xl gap-3 sm:grid-cols-2">
          <NumberField label="Комиссия за вход или выход, %" value={lc.tradeFeePct} change={n=>lf("tradeFeePct",n)} min={0} max={3} step="any" hint="Комиссия списывается дважды — при входе и при выходе. Для июньского теста стоит 0,05%. Если знаешь свою ставку MEXC для рыночной сделки, поставь её."/>
          <NumberField label="Доп. ухудшение цены за вход или выход, %" value={lc.extraSlipPct} change={n=>lf("extraSlipPct",n)} min={0} max={3} step="any" hint="От 0 до 3%. Покупка станет дороже, продажа дешевле. 0 оставляет цену из данных. Для пробного теста можно поставить 0,02%, чтобы проверить, что будет при чуть худшей цене."/>
        </div>
        {auto?<div className="grid gap-3 rounded-xl bg-slate-50 p-3 sm:p-4">
          <div className="flex flex-wrap items-center justify-between gap-2"><div><p className="font-semibold">Что проверим</p><p className="text-xs text-slate-600">От 2 до 6 чисел на диапазон, включая края. Для одного числа укажи одинаковые границы и 1 точку.</p></div><Button type="button" variant="outline" onClick={()=>setRanges(Object.fromEntries(rows.map(r=>[r.key,{lower:r.min,upper:r.max,points:ranges[r.key].points>1?ranges[r.key].points:2}])) as typeof ranges)}>На всю ширину</Button><Button type="button" variant="outline" onClick={()=>setRanges(defaults(lc.model))}>Стартовые диапазоны</Button></div>
          <div className="grid gap-2 lg:grid-cols-2">
          {rows.map(row=>{const a=ranges[row.key],values=axisValues(row,a);return <div key={row.key} role="group" aria-label={row.label} className="rounded-lg border border-slate-200 bg-white p-3">
            <div className="mb-2 text-sm font-semibold">{row.label} <Hint text={row.hint} label={"Подсказка: "+row.label}/></div>
            <div className="grid grid-cols-3 gap-2"><NumberField label="От" value={a.lower} min={row.min} max={row.max} step={row.step===1?1:"any"} change={n=>changeAxis(row.key,"lower",n)}/><NumberField label="До" value={a.upper} min={row.min} max={row.max} step={row.step===1?1:"any"} change={n=>changeAxis(row.key,"upper",n)}/><NumberField label="Точек" value={a.points} min={1} max={6} hint={POINTS_HINT} change={n=>changeAxis(row.key,"points",n)}/></div>
            <p className={`mt-2 text-xs ${values.length?"text-slate-600":"text-rose-700"}`}>{values.length?"Проверим: "+values.join(" · "):"Проверь границы и число точек."}</p>
          </div>})}
          </div>
          <div className="text-sm"><b className="mr-2 text-xl tabular-nums">{total.toLocaleString("ru-RU")}</b> сочетаний <Hint text="Проверяем каждое сочетание показанных чисел. Чем больше точек, тем дольше подбор. Если для настройки нет достаточного количества примеров удачных и неудачных входов, программа её пропустит и покажет число пропусков."/></div>
        </div>:<div className="grid grid-cols-2 gap-3 lg:grid-cols-3">{rows.map(row=><NumberField key={row.key} label={row.label} hint={row.hint} value={lc[row.key]} change={n=>lf(row.key,n)} min={row.min} max={row.max} step={row.step===1?1:"any"}/>)}</div>}
      </>:<>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="grid gap-1.5 text-sm font-medium text-slate-700">Алгоритм<select value={cfg.rule} className={inputStyle} onChange={e=>{const rule=e.target.value as Rule;setCfg(x=>({...x,rule,lookback:rule==="prior_range_break"?60:10,thresholdPct:rule==="prior_range_break"?0:.05}))}}>{RULES.map(r=><option key={r.id} value={r.id}>{r.label}</option>)}</select></label>
        {cfg.rule==="ema_cross"?<><NumberField label="Быстрая средняя, сек" value={cfg.fast} change={n=>field("fast",n)} min={2} max={3600}/><NumberField label="Медленная средняя, сек" value={cfg.slow} change={n=>field("slow",n)} min={3} max={7200}/></>:<><NumberField label="Смотреть назад, сек" value={cfg.lookback} change={n=>field("lookback",n)} min={2} max={3600}/><NumberField label="Порог сигнала, %" value={cfg.thresholdPct} change={n=>field("thresholdPct",n)} min={0} max={5} step={.001}/></>}
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4"><NumberField label="Старт, USDT" value={cfg.startBalance} change={n=>field("startBalance",n)} min={.01} max={1000000} step={.01}/><NumberField label="Цель чистыми, %" value={cfg.takePct} change={n=>field("takePct",n)} min={.001} max={20} step={.001}/><NumberField label="Стоп по чистому убытку, %" value={cfg.stopPct} change={n=>field("stopPct",n)} min={.001} max={20} step={.001}/><NumberField label="Ждать выхода, сек" value={cfg.holdSeconds} change={n=>field("holdSeconds",n)} min={5} max={21600}/></div>
      </>}</fieldset>
      <div className="flex flex-wrap items-center gap-3"><Button type="submit" disabled={busy||learning&&auto&&!total}>{busy?"Выполняю…":learning?(auto?"Подобрать и проверить":"Обучить и проверить"):"Запустить тест"}</Button>
      {(busy||job)&&<div className="flex min-w-[125px] max-w-lg flex-1 flex-wrap items-center gap-2" aria-live="polite"><progress aria-label="Прогресс расчёта" className="h-2.5 w-36 shrink-0 accent-blue-700" value={job?.progress} max={100}/><span className="text-xs text-slate-600">{job?`${job.progress}% · ${job.stage} · сравнено ${job.compared??0} из ${job.total}${job.skipped?`, пропущено ${job.skipped}`:""}`:'Запускаю…'}</span></div>}
      {busy&&job?.state==="running"&&<Button type="button" variant="outline" disabled={cancelling} onClick={cancel}>{cancelling?"Останавливаю…":"Остановить"}</Button>}
      {error&&<p role="alert" className="text-sm text-rose-700">{error}</p>}</div>
      </form></CardContent></Card>
    {result&&<section className="mt-5 grid gap-4" aria-live="polite">
      <p className="text-sm font-medium text-slate-600">{settingsResult?`${settingsResult.optimize?(job?.qualified?"Лучшее из проверенных":"Пробный итог: ни один вариант не прошёл отбор"):"Один прогон с твоими настройками"} · ${LEARN_MODELS[settingsResult.model??"logistic"]} · ${DIRECTIONS[settingsResult.direction??"long"]} · 18–20 июня`:`${RULES.find(r=>r.id===baseResult?.rule)?.label} · лонг · цель ${baseResult?.takePct}% · стоп ${baseResult?.stopPct}% · до ${baseResult?.holdSeconds} сек`}</p>
      {result.openPosition&&<p className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">В конце {result.processedDays}-го дня нет цены для закрытия открытой сделки. Показан баланс только по закрытым; прогон остановлен.</p>}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label={stage} value={`${money(result.balance)} USDT`} hint="Сколько денег осталось после всех закрытых сделок: старт плюс прибыль или минус убыток. Открытая сделка в этой сумме не учтена."/>
        <Metric label="Чистый результат" value={`${signed(result.pnl)} USDT`} foot={`${signed(result.returnPct)}%`} tone={profitClass} hint="Итоговый баланс минус стартовый. Плюс — заработал, минус — потерял. Комиссии уже вычтены."/>
        <Metric label="Закрыто сделок" value={String(result.trades.length)} foot={`${money(result.winPct)}% в плюс`} hint="Сколько сделок дошли до закрытия. Открытые сделки не входят в счёт."/>
        <Metric label="Максимальная просадка" value={`${money(result.drawdownPct)}%`} foot="по закрытым сделкам" hint="Самое большое падение баланса от его предыдущего пика, включая старт. Например: 100 → 120 → 108. Итог в плюсе на 8, просадка 10%. Если баланс ни разу не падал, просадка 0%."/>
      </div>
      <div className="grid grid-cols-3 gap-3" aria-label="Исходы закрытых сделок">
        <Metric label="Прибыльные" value={String(tradeCounts.wins)} tone="text-emerald-700" hint="Сколько сделок принесли деньги после всех расходов. На графике это зелёный ромб."/>
        <Metric label="Убыточные" value={String(tradeCounts.losses)} tone="text-rose-700" hint="Сколько сделок потеряли деньги после расходов. На графике это красный крест."/>
        <Metric label="В ноль" value={String(tradeCounts.flat)} hint="Сколько сделок закрылись без прибыли и убытка. На графике это серая точка."/>
      </div>
      {best&&settingsResult&&job&&<Card><CardHeader><CardTitle>Какие настройки дали этот результат</CardTitle></CardHeader><CardContent className="grid gap-3">
        <dl className="grid grid-cols-2 gap-2 lg:grid-cols-4">{fields(settingsResult.model??"logistic").map(row=><div key={row.key} className="rounded-lg bg-slate-50 p-2"><dt className="text-xs text-slate-600">{row.label}</dt><dd className="font-semibold tabular-nums">{settingsResult[row.key]}</dd></div>)}<div className="rounded-lg bg-slate-50 p-2"><dt className="text-xs text-slate-600">Стартовый баланс, USDT</dt><dd className="font-semibold tabular-nums">{settingsResult.startBalance}</dd></div></dl>
        <p className="text-sm text-slate-600">Сравнено на 18–20 июня: <b>{job.compared} из {job.total}</b>. Пропущено из-за нехватки данных: {job.skipped??0}. Для показанной модели: {best.positiveLabels.toLocaleString("ru-RU")} удачных учебных входов из {best.eligibleLabels.toLocaleString("ru-RU")}.</p>
        <p className="text-sm text-slate-600">Расходы в расчёте: комиссия {result.feePct}% за вход и за выход · доп. ухудшение цены {settingsResult.extraSlipPct??0}% за вход и за выход. Разница цен покупки и продажи уже учтена.</p>
        {settingsResult.optimize&&<p className="text-sm text-slate-600">Правило выбора: полный прогон и минимум 20 закрытых сделок. Среди таких вариантов выше тот, у которого больше итоговый баланс; при равенстве — меньше просадка, затем больше сделок. {job.qualified?`Прошли отбор: ${job.qualified}.`:"Никто не прошёл отбор. Показан пробный итог: сначала полный прогон, затем наибольший баланс."}</p>}
        <details className="text-sm"><summary className="cursor-pointer font-semibold text-blue-800">Какие числа использовал поиск</summary><dl className="mt-2 grid gap-2 sm:grid-cols-2">{fields(settingsResult.model??"logistic").map(row=><div key={row.key}><dt className="text-slate-600">{row.label}</dt><dd className="font-semibold tabular-nums">{job.axes[row.key]?.join(" · ")}</dd></div>)}</dl></details>
        <div className="flex flex-wrap items-center gap-2"><Button variant="outline" disabled={freezing||!!frozen||!best.complete||best.tradeCount<20} onClick={freeze}>Зафиксировать для будущей недели</Button><span className="text-xs text-slate-600">{frozen||(!best.complete||best.tradeCount<20?"Нужен полный прогон и минимум 20 закрытых сделок.":"Июньский итог — ещё не проверка на будущей неделе.")}</span></div>
        {job.ranking&&job.ranking.length>1&&<details className="text-sm"><summary className="cursor-pointer font-semibold text-blue-800">Рейтинг: {job.ranking.length} вариантов</summary><div className="mt-1 max-h-80 overflow-auto"><table className="w-full min-w-[750px] text-left tabular-nums"><thead><tr>{["Цель, %","Падение, %","Срок, с","Настройка модели","Вход от, %","Стоп, %","Объём, с","Сделок","Просадка, %","Баланс, USDT"].map(h=><th className="p-2" key={h}>{h}</th>)}</tr></thead><tbody>{job.ranking.slice(0,shown).map((r,i)=><tr className="border-t border-slate-100" key={i}><td className="p-2">{r.config.targetPct}</td><td>{r.config.dipPct}</td><td>{r.config.holdSeconds}</td><td>{r.config.complexity}</td><td>{r.config.confidencePct}</td><td>{r.config.stopPct}</td><td>{r.config.volumeSeconds??0}</td><td>{r.tradeCount}</td><td>{money(r.drawdownPct)}</td><td>{money(r.balance)}{!r.complete?" · неполный":""}</td></tr>)}</tbody></table></div>{job.ranking.length>shown&&<Button type="button" variant="outline" className="mt-2" onClick={()=>setShown(n=>n+50)}>Показать ещё</Button>}</details>}
      </CardContent></Card>}
      <Card><CardHeader><CardTitle>Баланс</CardTitle></CardHeader><CardContent><Plot quotes={[]} trades={result.trades} balance initialTime={result.begin} initialBalance={settingsResult?.startBalance??baseResult?.startBalance}/></CardContent></Card>
      <Card><CardHeader><CardTitle>Цена и сделки <Hint text="Нажми на время в таблице, чтобы увидеть одну сделку крупно."/></CardTitle></CardHeader><CardContent>
        <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs font-medium">
          <span className="text-slate-700">▲ Вход</span><span className="text-emerald-700">◆ Выход в плюс</span><span className="text-rose-700">✚ Выход в минус</span>{tradeCounts.flat>0&&<span className="text-slate-600">● Выход в ноль</span>}
        </div>
        <Plot quotes={result.quotes} trades={result.trades}/>
      </CardContent></Card>
      {selected&&<Card><CardHeader><CardTitle>{DIRECTIONS[selected.side??"long"]} · {fmt(selected.entryTime)} UTC <span className={selected.pnl<0?"text-rose-700":"text-emerald-700"}>{signed(selected.pnl)} USDT</span></CardTitle></CardHeader><CardContent><p className="mb-2 text-sm text-slate-600">Вход {precise(selected.entryTime)} по {selected.entryPrice} · выход {precise(selected.exitTime)} по {selected.exitPrice} · {reason[selected.reason]}</p><Plot quotes={detail} trades={[selected]} detail/></CardContent></Card>}
      <Card><CardHeader><CardTitle>Все сделки <Hint text="Итог считается после исполнения выхода. Стоп или цель подают команду, а цена за 300 мс может измениться."/></CardTitle></CardHeader><CardContent>
        {!current.length?<p className="text-sm text-slate-500">Нет закрытых сделок при этих настройках.</p>:<div className="overflow-x-auto"><table className="w-full min-w-[640px] border-collapse text-left text-sm tabular-nums"><thead className="bg-slate-50 text-slate-600"><tr>{["№ / вход UTC","Сторона","Выход UTC","Цена: вход → выход","Причина","Чистыми","Баланс"].map(h=><th className="px-3 py-2" key={h}>{h}</th>)}</tr></thead><tbody>{current.map((t,i)=><tr key={t.entryTime} className="border-b border-slate-100"><td className="px-3 py-2"><button className="font-semibold text-blue-800 underline-offset-2 hover:underline" onClick={()=>{setDetail([]);setSelected(t)}}>{page*25+i+1} · {fmt(t.entryTime)}</button></td><td>{DIRECTIONS[t.side??"long"]}</td><td>{fmt(t.exitTime)}</td><td>{t.entryPrice} → {t.exitPrice}</td><td>{reason[t.reason]}{t.gapExposed?" · разрыв":""}</td><td className={t.pnl<0?"text-rose-700":"text-emerald-700"}>{signed(t.pnl)} USDT</td><td>{money(t.balance)}</td></tr>)}</tbody></table></div>}
        {result.trades.length>25&&<div className="mt-3 flex items-center gap-3"><Button variant="outline" disabled={page===0} onClick={()=>setPage(p=>p-1)}>Назад</Button><span>{page+1} из {Math.ceil(result.trades.length/25)}</span><Button variant="outline" disabled={(page+1)*25>=result.trades.length} onClick={()=>setPage(p=>p+1)}>Дальше</Button></div>}
      </CardContent></Card>
    </section>}
    </div>
  </main>;
}
