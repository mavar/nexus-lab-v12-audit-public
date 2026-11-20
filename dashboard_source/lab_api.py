"""Loopback-only API for the June technical pilot. No exchange connection."""
import os
from datetime import date, timedelta, datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from build import source_quotes

HERE=Path(__file__).resolve().parent
from harness_timed import DAY_MS, GAP_MS, TimedExit, execute_long_day, signals
from dashboard_config import load_rules, path_setting

ROOT=path_setting('NEXUS_QUOTE_ROOT','quoteRoot',r'G:\mexc_base\exchange=MEXC\stream=book_ticker')
LABEL_HTML=path_setting('NEXUS_LABEL_HTML','labelHtml',str(HERE/'dist/review.html'))
START=date(2026,6,14)
RULE=Literal['momentum_10s','ema_cross','prior_range_break']
lock=Lock()
app=FastAPI(title='Nexus local test laboratory')
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost'])


class RunInput(BaseModel):
    rule: RULE
    lookback: int=Field(10,ge=2,le=3600)
    thresholdPct: float=Field(.05,ge=0,le=5)
    fast: int=Field(8,ge=2,le=3600)
    slow: int=Field(32,ge=3,le=7200)
    takePct: float=Field(.1,gt=0,le=20)
    stopPct: float=Field(.2,gt=0,le=20)
    holdSeconds: int=Field(120,ge=5,le=21600)
    startBalance: float=Field(100,gt=0,le=1_000_000)

    @model_validator(mode='after')
    def validate_periods(self):
        if self.rule=='ema_cross' and self.fast>=self.slow:
            raise ValueError('Быстрая средняя должна быть короче медленной.')
        return self


class Trade(BaseModel):
    side:Literal['long','short']='long'
    decisionTime:int
    entryTime:int
    exitCommandTime:int
    exitTime:int
    entryPrice:float
    exitPrice:float
    netRate:float
    reason:Literal['target','stop','dip','time','gap','session']
    gapExposed:bool
    pnl:float
    balance:float


class OpenPosition(BaseModel):
    side:Literal['long','short']='long'
    entryTime:int
    entryPrice:float
    reason:str
    decisionTime:int


class QuotePoint(BaseModel):
    time:int
    price:float|None


class History(BaseModel):
    begin:int
    end:int
    processedDays:int
    feePct:float
    delayMs:int
    balance:float
    pnl:float
    returnPct:float
    winPct:float
    drawdownPct:float
    entriesSkipped:int
    signals:int
    openPosition:OpenPosition|None
    trades:list[Trade]
    quotes:list[QuotePoint]


class RunResult(History):
    config:RunInput


SearchField=Literal['holdSeconds','targetPct','dipPct','complexity','confidencePct','stopPct','volumeSeconds']


class SearchAxis(BaseModel):
    lower:float
    upper:float
    points:int=Field(ge=1,le=6)


class LearnInput(BaseModel):
    direction:Literal['long','short','both']='long'
    volumeSeconds:int=Field(0,ge=0,le=3600)
    extraSlipPct:float=Field(0,ge=0,le=3)
    tradeFeePct:float|None=Field(None,ge=0,le=3)
    model:Literal['logistic','tree','bayes']='logistic'
    optimize:bool=False
    search:dict[SearchField,SearchAxis]|None=None
    targetPct:float=Field(.10,gt=0,le=5)
    dipPct:float=Field(.05,ge=0,le=2)
    holdSeconds:int=Field(120,ge=15,le=21600)
    stopPct:float=Field(.2,gt=0,le=10)
    confidencePct:float=Field(20,gt=0,lt=100)
    complexity:float=Field(1,ge=.01,le=10)
    startBalance:float=Field(100,gt=0,le=1_000_000)

    @model_validator(mode='after')
    def depth_integral(self):
        if self.model=='tree' and not (self.complexity.is_integer() and 2<=self.complexity<=6):
            raise ValueError('Для дерева глубина — целое число 2–6.')
        return self


class RankedModel(BaseModel):
    config:LearnInput
    balance:float
    tradeCount:int
    drawdownPct:float
    complete:bool
    positiveLabels:int
    eligibleLabels:int


class LearnJob(BaseModel):
    id:str
    state:Literal['running','done','error','cancelled']
    progress:int
    stage:str
    axes:dict[SearchField,list[float]]
    total:int
    compared:int=0
    skipped:int=0
    qualified:int=0
    error:str|None=None
    best:RankedModel|None=None
    ranking:list[RankedModel]=Field(default_factory=list)
    result:History|None=None


class FreezeResult(BaseModel):
    id:str
    holdout:str


def midnight(day):
    return int(datetime.combine(day,datetime.min.time(),tzinfo=timezone.utc).timestamp()*1000)


@lru_cache(maxsize=2)
def read_day(day):
    files=list((ROOT/'symbol=SOLUSDT'/f'date={day}').glob('*.parquet'))
    if len(files)!=1:
        raise FileNotFoundError(f'Нет ровно одного файла котировок SOLUSDT за {day}.')
    t,b,a,_=source_quotes(files[0],0)
    s=midnight(day)
    if len(t)<2 or t[0]<s or t[-1]>=s+DAY_MS:
        raise ValueError(f'Некорректные границы дня {day}.')
    return t,b,a


def series(ts,bid,ask,step):
    pick=np.unique(np.r_[0,np.searchsorted(ts,np.arange(ts[0],ts[-1],step)),len(ts)-1])
    gaps=np.flatnonzero(np.diff(ts)>GAP_MS)
    pick=np.unique(np.r_[pick,gaps,gaps+1]); p=[(int(ts[i]),float((bid[i]+ask[i])/2)) for i in pick]
    p.extend((int(ts[i])+1,None) for i in gaps)
    return [QuotePoint(time=t,price=v) for t,v in sorted(p,key=lambda x:x[0])]


def calculate(cfg: RunInput):
    fee_pct=float(load_rules()['fees']['taker_pct'])
    terms=TimedExit(cfg.takePct/100,cfg.stopPct/100,cfg.holdSeconds*1000,fee_pct/100)
    balance=peak=cfg.startBalance; dd=0.; trades=[]; quotes=[]; pending=None; skipped=num_signals=0
    for i in range(7):
        day=START+timedelta(days=i); t,b,a=read_day(day); s=midnight(day)
        sig=signals(t,b,a,s,cfg.rule,cfg.lookback,cfg.thresholdPct/100,cfg.fast,cfg.slow)
        closed,opened,skip=execute_long_day(t,b,a,sig,s+DAY_MS,terms)
        quotes.extend(series(t,b,a,180_000));quotes.append(QuotePoint(time=s+DAY_MS-1,price=None)); skipped+=skip;num_signals+=len(sig)
        for tr in closed:
            pnl=balance*tr['netRate'];balance+=pnl;peak=max(balance,peak);dd=max(dd,1-balance/peak)
            trades.append(Trade(**tr,pnl=pnl,balance=balance))
        if opened:
            pending=OpenPosition(**opened);break
    win=sum(tr.pnl>0 for tr in trades)
    return RunResult(config=cfg,begin=midnight(START),end=midnight(START+timedelta(days=7)),processedDays=i+1,
                     feePct=fee_pct,delayMs=terms.delay_ms,balance=balance,pnl=balance-cfg.startBalance,
                     returnPct=(balance/cfg.startBalance-1)*100,winPct=100*win/max(1,len(trades)),drawdownPct=dd*100,
                     entriesSkipped=skipped,signals=num_signals,openPosition=pending,trades=trades,quotes=quotes)


def validate_origin(request):
    origin=request.headers.get('origin')
    if origin and origin!=str(request.base_url).rstrip('/'):
        raise HTTPException(403,'Чужой сайт не может запускать локальный расчёт.')


@app.post('/api/v1/runs',response_model=RunResult)
def run(cfg:RunInput,request:Request):
    validate_origin(request)
    if not lock.acquire(blocking=False):
        raise HTTPException(409,'Один прогон уже выполняется.')
    try:
        return calculate(cfg)
    except (FileNotFoundError,ValueError) as e:
        raise HTTPException(422,str(e)) from e
    finally:
        lock.release()


@app.get('/api/v1/quotes',response_model=list[QuotePoint])
def get_quotes(start:int,end:int):
    day=datetime.fromtimestamp(start/1000,tz=timezone.utc).date()
    if not (START<=day<START+timedelta(days=7) and start<end<=midnight(day)+DAY_MS and end-start<=22_000_000):
        raise HTTPException(422,'Недопустимый отрезок графика.')
    try:
        t,b,a=read_day(day)
    except (FileNotFoundError,ValueError) as e:
        raise HTTPException(422,str(e)) from e
    l,r=np.searchsorted(t,[start,end]);return series(t[l:r],b[l:r],a[l:r],max(1000,(end-start)//450)) if r>l else []


@app.get('/label-review',include_in_schema=False)
def label_review():
    if not LABEL_HTML.is_file():
        raise HTTPException(404,'Прежний файл разметки не найден. Проверьте NEXUS_LABEL_HTML.')
    return FileResponse(LABEL_HTML,media_type='text/html')


@app.get('/api/v1/health',include_in_schema=False)
def health():
    from dashboard_config import data_mode
    return {'service':'nexus-local-lab','pageBuilt':(HERE/'web/out/index.html').exists(),
            'projectRoot':str(HERE),'dataMode':data_mode(ROOT),'quotesAvailable':ROOT.is_dir(),
            'labelPageAvailable':LABEL_HTML.is_file()}


@app.post('/api/v1/learning',response_model=LearnJob)
def start_learning(cfg:LearnInput,request:Request):
    validate_origin(request)
    from learn_jobs import start
    return start(cfg)


@app.get('/api/v1/learning/{job_id}',response_model=LearnJob)
def learning_status(job_id:str):
    from learn_jobs import status
    return status(job_id)


@app.post('/api/v1/learning/{job_id}/cancel',response_model=LearnJob)
def cancel_learning(job_id:str,request:Request):
    validate_origin(request)
    from learn_jobs import cancel
    return cancel(job_id)


@app.post('/api/v1/learning/{job_id}/freeze',response_model=FreezeResult)
def freeze_learning(job_id:str,request:Request):
    validate_origin(request)
    from learn_jobs import freeze
    return freeze(job_id)


if (HERE/'web/out').is_dir():
    app.mount('/',StaticFiles(directory=HERE/'web/out',html=True))
