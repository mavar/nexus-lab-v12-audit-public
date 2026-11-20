"""June-only supervised pilot with asynchronous progress, a chronological split and freezing."""
from datetime import timedelta, datetime, timezone
from hashlib import sha256
from itertools import product
from math import floor, prod
import json
import logging
import os
from pathlib import Path
import threading
from uuid import uuid4

import joblib
import numpy as np
import sklearn
from fastapi import HTTPException
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import GaussianNB
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from threadpoolctl import threadpool_limits
from lab_api import (DAY_MS, HERE, START, History, LearnInput, QuotePoint, RankedModel, ROOT, Trade,
                     OpenPosition, load_rules, lock, midnight, read_day, series, TimedExit)
from harness_timed import DELAY_MS, execute_directional_day, prepare_entries
from learn_labels import features, prepare, labeled_returns
from learn_volume import add_volume, read_trades, trade_path

FIT=tuple(START+timedelta(days=i) for i in range(4))
SELECT=tuple(START+timedelta(days=i) for i in range(4,7))
HOLDOUT={'start':'2026-11-23T00:00:00Z','endExclusive':'2026-11-30T00:00:00Z','status':'requires_separate_untouched_capture_and_review'}
ART=Path(os.getenv('LOCALAPPDATA',Path.home()))/'NexusLabelLab'/'frozen-models'
JOBS={}; GUARD=threading.Lock()
MIN_SPOT_ORDER_USDT = 1.


def model_for(cfg):
    if cfg.model=='tree':return DecisionTreeClassifier(max_depth=int(cfg.complexity),min_samples_leaf=60,random_state=42)
    if cfg.model=='bayes':return make_pipeline(StandardScaler(),GaussianNB(var_smoothing=1e-3*cfg.complexity))
    return make_pipeline(StandardScaler(),LogisticRegression(C=cfg.complexity,max_iter=150,random_state=42))


def grid(cfg):
    bounds=dict(holdSeconds=(15,21600),targetPct=(.001,5),dipPct=(0,2),
                complexity=(2,6) if cfg.model=='tree' else (.01,10),confidencePct=(.01,99.99),stopPct=(.001,10),
                volumeSeconds=(0,3600))
    if not cfg.optimize:return {key:[getattr(cfg,key)] for key in bounds}
    if not cfg.search or cfg.search.keys()-{'volumeSeconds'}!=bounds.keys()-{'volumeSeconds'}:
        raise ValueError('Заполни диапазоны для подбора.')
    axes={}
    for key,(low,high) in bounds.items():
        if key=='volumeSeconds' and key not in cfg.search:
            axes[key]=[cfg.volumeSeconds]
            continue
        axis=cfg.search[key]; a,b,n=axis.lower,axis.upper,axis.points
        integer=key in ('holdSeconds','volumeSeconds') or key=='complexity' and cfg.model=='tree'
        if not low<=a<=b<=high or integer and not (a.is_integer() and b.is_integer()):
            raise ValueError(f'Проверь границы {key}: {low}–{high}.')
        if (a==b)!=(n==1):raise ValueError('Одна точка — одинаковые границы; разные границы — минимум две точки.')
        values=[a+(b-a)*i/max(1,n-1) for i in range(n)]
        axes[key]=sorted({floor(x+.5) if integer else floor(x*1_000_000+.5)/1_000_000 for x in values})
    return axes


def entry_sides(probabilities, threshold):
    long = probabilities.get(1)
    short = probabilities.get(-1)
    if short is None:
        return (long >= threshold).astype(np.int8)
    if long is None:
        return -(short >= threshold).astype(np.int8)
    # One decision per second. Use the higher model score, with a fixed long tie-break.
    return np.where(np.maximum(long, short) >= threshold, np.where(long >= short, 1, -1), 0).astype(np.int8)


def execution_quotes(quotes, slip_pct):
    if not slip_pct:
        return quotes
    t,bid,ask=quotes
    return t,bid*(1-slip_pct/100),ask*(1+slip_pct/100)


def fee_for(cfg):
    return float(load_rules()['fees']['taker_pct']) if cfg.tradeFeePct is None else cfg.tradeFeePct


def evaluate(cfg, days, candidates, fee_pct, render=False):
    bal=peak=cfg.startBalance; dd=0.; trades=[]; quotes=[]; opened=None; attempted=skipped=count=wins=0
    terms=TimedExit(cfg.targetPct/100,cfg.stopPct/100,cfg.holdSeconds*1000,fee_pct/100,adverse=cfg.dipPct/100)
    min_balance = MIN_SPOT_ORDER_USDT * (1 + terms.fee)
    for i,((day,q,clk,_,prepared),sides) in enumerate(zip(days,candidates,strict=True)):
        t,b,a=q; s=midnight(day)
        attempted+=np.count_nonzero(sides)
        closed,opened,skip=execute_directional_day(t,b,a,clk,sides,s+DAY_MS,terms,prepared,details=render);skipped+=skip
        if render:
            quotes.extend(series(*read_day(day),180_000));quotes.append(QuotePoint(time=s+DAY_MS-1,price=None))
        for tr in closed:
            if bal < min_balance:
                break
            pnl=bal*(tr['netRate'] if render else tr);bal+=pnl;peak=max(bal,peak);dd=max(dd,1-bal/peak);count+=1;wins+=pnl>0
            if render:trades.append(Trade(**tr,pnl=pnl,balance=bal))
        if bal < min_balance:
            opened = None
            break
        if opened:break
    if not render:return bal,count,dd*100,not bool(opened)
    return History(begin=midnight(days[0][0]),end=midnight(days[-1][0])+DAY_MS,processedDays=i+1,feePct=fee_pct,delayMs=terms.delay_ms,balance=bal,
                   pnl=bal-cfg.startBalance,returnPct=(bal/cfg.startBalance-1)*100,winPct=100*wins/max(1,count),drawdownPct=dd*100,
                   entriesSkipped=skipped,signals=attempted,openPosition=OpenPosition(**opened) if opened else None,trades=trades,quotes=quotes)


def with_volume(day,quotes,clock,x,seconds):
    return add_volume(quotes,clock,x,read_trades(day),seconds) if seconds else (clock,x)


def validation_day(day, seconds=0, slip_pct=0.):
    quotes = read_day(day)
    clock, x = with_volume(day,quotes,*features(*quotes),seconds)
    return day, execution_quotes(quotes,slip_pct), clock, x, prepare_entries(quotes[0], clock, midnight(day)+DAY_MS, DELAY_MS)


def work(cfg,axes,report):
    directions = {'long': (1,), 'short': (-1,), 'both': (1,-1)}[cfg.direction]
    H,P,D,C,S,Z,V=axes.values()
    shapes=list(product(H,D))
    fee=fee_for(cfg)
    labels={(side,h,dip):[] for side in directions for h,dip in shapes}
    training={seconds:[] for seconds in V}
    sample_indices={seconds:[] for seconds in V}
    validation={seconds:[] for seconds in V}
    checks=len(S)*len(Z)
    total=len(FIT)*(len(V)+len(labels))+len(SELECT)*len(V)+len(shapes)*len(V)*len(P)*len(C)*(1+checks)+1
    done=compared=skipped=0
    def step(stage):
        nonlocal done
        done+=1;report(min(99,done*100//total),stage,compared,skipped)
    for day in FIT:
        t,b,ask=read_day(day);clk,x=features(t,b,ask);clk,x=clk[::3],x[::3]
        for seconds in V:
            available,expanded=with_volume(day,(t,b,ask),clk,x,seconds)
            training[seconds].append(expanded)
            sample_indices[seconds].append(np.searchsorted(clk,available))
            step(f'Готовлю данные для обучения · {day:%d.%m}')
        t,b,ask=execution_quotes((t,b,ask),cfg.extraSlipPct)
        for side in directions:
            structures=prepare(t,b if side==1 else -ask)
            for h,dip in shapes:
                labels[side,h,dip].append(labeled_returns(t,b,ask,clk,midnight(day)+DAY_MS,h*1000,dip/100,fee/100,structures,side))
                step(f'Размечаю учебные входы · {day:%d.%m}')
    for day in SELECT:
        for seconds in V:
            validation[seconds].append(validation_day(day,seconds,cfg.extraSlipPct));step(f'Готовлю более поздний июньский отрезок · {day:%d.%m}')
    training={seconds:np.concatenate(x) for seconds,x in training.items()}
    ranks=[]; winner=None
    def order(r):return (r.complete and r.tradeCount>=20,r.complete,r.balance,-r.drawdownPct,r.tradeCount)
    with threadpool_limits(limits=1):
        for h,dip,seconds in product(H,D,V):
            days=validation[seconds]
            if any(not len(day[3]) for day in days):
                skipped+=len(P)*len(C)*checks
                done+=len(P)*len(C)*(1+checks)-1
                step(f'Пропуск: не хватает данных для окна объёма {seconds} сек.')
                continue
            samples={}
            for side in directions:
                raw=np.concatenate([day[indices] for day,indices in zip(labels[side,h,dip],sample_indices[seconds],strict=True)])
                known=np.isfinite(raw)
                samples[side]=(training[seconds][known],raw[known])
            for tp in P:
                targets={side:raw>=tp/100 for side,(_,raw) in samples.items()}
                positives=[int(y.sum()) for y in targets.values()]
                if any(min(n,len(y)-n)<10 for y,n in zip(targets.values(),positives,strict=True)):
                    skipped+=len(C)*checks
                    done+=len(C)*(1+checks)-1
                    step('Пропуск: слишком мало примеров одного класса для выбранного направления')
                    continue
                for complexity in C:
                    candidate=cfg.model_copy(update=dict(search=None,holdSeconds=h,targetPct=tp,dipPct=dip,complexity=complexity,volumeSeconds=seconds))
                    fitted={}
                    for side,(xx,_) in samples.items():
                        fitted[side]=model_for(candidate).fit(xx,targets[side])
                    scores=[{side:model.predict_proba(day[3])[:,1] for side,model in fitted.items()} for day in days]
                    step(f'Обучаю модель · {h} с, цель {tp}%')
                    for confidence in S:
                        signals=[entry_sides(day,confidence/100) for day in scores]
                        for stop in Z:
                            params=candidate.model_copy(update=dict(confidencePct=confidence,stopPct=stop))
                            bal,count,dd,complete=evaluate(params,days,signals,fee)
                            r=RankedModel(config=params,balance=bal,tradeCount=count,drawdownPct=dd,complete=complete,
                                          positiveLabels=sum(positives),eligibleLabels=sum(map(len,targets.values())))
                            ranks.append(r)
                            if winner is None or order(r)>order(winner[0]):winner=(r,fitted,signals)
                            compared+=1;step('Сравниваю настройки на 18–20 июня')
    if not winner:raise ValueError('Для выбранной цели недостаточно положительных или отрицательных меток. Уменьши цель или измени срок/предел падения.')
    best,fitted,signals=winner;result=evaluate(best.config,validation[best.config.volumeSeconds],signals,fee,render=True);step('Формирую графики и список сделок')
    return best,sorted(ranks,key=order,reverse=True),result,fitted


class Cancelled(Exception):
    pass


def status(key):
    with GUARD:
        if key not in JOBS:raise HTTPException(404,'Прогон больше не хранится.')
        return {k:v for k,v in JOBS[key].items() if k not in ('estimator','stop')}


def cancel(key):
    with GUARD:
        j=JOBS.get(key)
        if not j:raise HTTPException(404,'Прогон больше не хранится.')
        if j['state']=='running':
            j['stop'].set()
            j['stage']='Останавливаю после текущего расчёта…'
    return status(key)


def start(cfg:LearnInput):
    if cfg.direction!='long':
        raise HTTPException(422,'Для шорта нужны котировки фьючерса SOLUSDT и история выплат MEXC. Сейчас подключён спот.')
    if cfg.startBalance < MIN_SPOT_ORDER_USDT * (1 + fee_for(cfg)/100):
        raise HTTPException(422,'На MEXC покупка SOLUSDT от 1 USDT. На балансе ещё должно хватить на комиссию.')
    try:axes=grid(cfg)
    except ValueError as e:raise HTTPException(422,str(e)) from None
    if not lock.acquire(blocking=False):raise HTTPException(409,'Другой прогон уже выполняется.')
    key=uuid4().hex;stop=threading.Event()
    with GUARD:
        while len(JOBS)>=4:JOBS.pop(next(iter(JOBS)))
        JOBS[key]=dict(id=key,state='running',progress=0,stage='Подготовка данных июня…',stop=stop,axes=axes,total=prod(map(len,axes.values())))
    def report(progress,stage,compared,skipped):
        with GUARD:
            JOBS[key].update(progress=progress,compared=compared,skipped=skipped)
            if stop.is_set():raise Cancelled
            JOBS[key]['stage']=stage
    def run():
        try:
            best,ranks,result,estimator=work(cfg,axes,report)
            with GUARD:
                if stop.is_set():raise Cancelled
                JOBS[key].update(state='done',progress=100,stage='Готово',best=best,ranking=ranks,result=result,estimator=estimator,
                                 qualified=sum(r.complete and r.tradeCount>=20 for r in ranks))
        except Cancelled:
            with GUARD:JOBS[key].update(state='cancelled',stage='Подбор остановлен')
        except Exception as e:
            logging.exception('Learning job failed')
            with GUARD:JOBS[key].update(state='error',stage='Прогон остановлен',error=str(e))
        finally:lock.release()
    try:threading.Thread(target=run,daemon=True).start()
    except Exception:
        lock.release();raise
    return status(key)


def freeze(key):
    from dashboard_config import data_mode
    if data_mode(ROOT)=='synthetic':
        raise HTTPException(409,'Демонстрационные данные: фиксация для будущей недели отключена.')
    if datetime.now(timezone.utc)>=datetime.fromisoformat(HOLDOUT['start']):
        raise HTTPException(409,'Срок фиксации для этой контрольной недели прошёл.')
    with GUARD:
        j=JOBS.get(key)
        if not j or j['state']!='done':raise HTTPException(409,'Сначала закончи прогон.')
        best=j['best']; model=j['estimator']
    if not best.complete or best.tradeCount<20:
        raise HTTPException(409,'Не фиксирую для будущей проверки: неполный итог или меньше 20 закрытых сделок.')
    path=ART/key
    try:path.mkdir(parents=True,exist_ok=False)
    except FileExistsError:
        if (path/'manifest.json').is_file():return {'id':key,'holdout':'Уже зафиксировано. Будущие данные ещё не подключены.'}
        raise HTTPException(409,'Фиксация уже выполняется или не завершилась.') from None
    temp=path/'model.tmp';joblib.dump(model,temp);temp.replace(path/'model.joblib')
    files=[HERE/x for x in ['learn_jobs.py','learn_labels.py','learn_volume.py','harness_timed.py','lab_api.py','check_frozen_week.py','dashboard_config.py']]
    sources={str(day):sha256(next((ROOT/'symbol=SOLUSDT'/f'date={day}').glob('*.parquet')).read_bytes()).hexdigest() for day in FIT+SELECT}
    trade_hashes={str(day):sha256(trade_path(day).read_bytes()).hexdigest() for day in FIT+SELECT} if best.config.volumeSeconds else {}
    manifest=dict(id=key,recordedUtc=datetime.now(timezone.utc).isoformat(),fit=list(map(str,FIT)),select=list(map(str,SELECT)),parameters=best.config.model_dump(),tradeSha256=trade_hashes,
                  codeSha256={f.name:sha256(f.read_bytes()).hexdigest() for f in files},quoteSha256=sources,sklearn=sklearn.__version__,
                  rulesHash=load_rules()['_hash'],modelSha256=sha256((path/'model.joblib').read_bytes()).hexdigest(),holdout=HOLDOUT)
    temp=path/'manifest.tmp';temp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path/'manifest.json')
    return {'id':key,'holdout':'23–29 ноября UTC; будущие данные ещё не подключены.'}
