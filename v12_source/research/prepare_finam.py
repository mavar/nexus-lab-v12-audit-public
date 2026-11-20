# -*- coding: utf-8 -*-
"""Read Finam OHLCV bars. Every input feature uses COMPLETED bars at or before t.
Forward returns are for TRAIN labeling or later offline evaluation ONLY.
Source timestamps are left as-is: the export's timezone was not specified.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

TIMEFRAMES = (1,5,10,15,30)
COLS = {'<DATE>':'date','<TIME>':'time','<OPEN>':'open','<HIGH>':'high','<LOW>':'low','<CLOSE>':'close','<VOL>':'volume'}
FILE_NAMES = {1:'SBRF_260701_260930_1M.csv',5:'SBRF_260701_260930_5M.csv',10:'SBRF_260701_260930_10M.csv',15:'SBRF_260701_260930_15m.csv',30:'SBRF_260701_260930_30m.csv'}
GROUPS = {
 'price':['ret1','ret3','ret6','body','range','upper','lower','volatility'],
 'time':['hour_s','hour_c','weekday_s','weekday_c','minute_s','minute_c','hour_start','monday','friday'],
 'volume':['vol_ratio','vol_change','close_volume_gravity','volume_pivot_distance'],
 'technical':['ema_cross','macd_scaled','rsi_scaled','bollinger_position','price_to_ema'],
}
FEATURES = sum(GROUPS.values(),[])
FEATURE_INDEX = {k:[FEATURES.index(c) for c in cols] for k,cols in GROUPS.items()}


def _gshift(d, col, k):
    return d.groupby('day',sort=False)[col].shift(k)


def make_frame(raw_file, tf, end_date='2026-09-26'):
    tf=int(tf)
    d=pd.read_csv(raw_file,sep=';').rename(columns=COLS)
    d['dt']=pd.to_datetime(d['date'].astype(str)+d['time'].astype(str).str.zfill(6),format='%Y%m%d%H%M%S')
    d=d.loc[(d['dt'] >= '2026-07-06') & (d['dt'] < end_date)].copy()
    d=d.sort_values('dt').drop_duplicates('dt').reset_index(drop=True)
    d['day']=d['dt'].dt.strftime('%Y-%m-%d')
    d['split']=np.select([d['dt']<'2026-08-17',d['dt']<'2026-08-29',d['dt']>='2026-09-01'],['train','select','check'],default='gap')
    g=d.groupby('day',sort=False)
    c=d['close'].astype('float64');o=d['open'].astype('float64'); h=d['high'].astype('float64'); l=d['low'].astype('float64')
    dt=d['dt']
    for k in (1,3,6):
        prev=_gshift(d,'close',k)
        at=_gshift(d,'dt',k)
        d[f'ret{k}']=np.where(dt-at==pd.Timedelta(minutes=tf*k),np.log(c/prev),np.nan)
    d['body']=(c-o)/c
    d['range']=(h-l)/c
    d['upper']=(h-np.maximum(o,c))/c
    d['lower']=(np.minimum(o,c)-l)/c
    d['volatility']=g['ret1'].transform(lambda s:s.rolling(12,min_periods=12).std())
    minute=dt.dt.hour*60+dt.dt.minute
    d['hour_s']=np.sin(2*np.pi*minute/1440)
    d['hour_c']=np.cos(2*np.pi*minute/1440)
    wd=dt.dt.dayofweek
    d['weekday_s']=np.sin(2*np.pi*wd/7)
    d['weekday_c']=np.cos(2*np.pi*wd/7)
    d['minute_s']=np.sin(2*np.pi*dt.dt.minute/60)
    d['minute_c']=np.cos(2*np.pi*dt.dt.minute/60)
    d['hour_start']=(dt.dt.minute<tf).astype(float)
    d['monday']=(wd==0).astype(float)
    d['friday']=(wd==4).astype(float)
    volume=d['volume'].astype(float)
    meanvol=g['volume'].transform(lambda s:s.rolling(12,min_periods=12).mean())
    d['vol_ratio']=np.log1p(volume)-np.log1p(meanvol)
    d['vol_change']=np.log1p(volume)-np.log1p(_gshift(d,'volume',1))
    # Close-price-volume centre over past 12 completed bars (NOT true order book depth).
    d['weighted_close']=c * volume
    sumweight=g['weighted_close'].transform(lambda s:s.rolling(12,min_periods=12).sum())
    sumvolume=g['volume'].transform(lambda s:s.rolling(12,min_periods=12).sum())
    center=sumweight/sumvolume.replace(0,np.nan)
    d['close_volume_gravity']=(c-center)/c
    # Largest-volume completed candle among previous 12 (a proxy for horizontal volume interest).
    def rolling_pivot(s):
        return s.rolling(12,min_periods=12).apply(np.argmax,raw=True)
    # use shifted volume-rank proxy without expensive rolling apply
    pivot_idx=np.full(len(d),np.nan)
    for _, ix in g.indices.items():
        ix=np.asarray(ix)
        vols=volume.iloc[ix].to_numpy()
        for j in range(11,len(ix)):
            k=j-11+int(np.argmax(vols[j-11:j+1]))
            pivot_idx[ix[j]]=float(c.iloc[ix[k]])
    d['volume_pivot_distance']=(c-pivot_idx)/c
    # Rolling technical indicators; reset between trading days to prevent hidden session-gap artifacts.
    ema_fast=g['close'].transform(lambda s:s.ewm(span=5,adjust=False).mean())
    ema_slow=g['close'].transform(lambda s:s.ewm(span=12,adjust=False).mean())
    ema_slow2=g['close'].transform(lambda s:s.ewm(span=26,adjust=False).mean())
    macd=ema_fast-ema_slow2
    macd_signal=g['close'].transform(lambda s:(s.ewm(span=5,adjust=False).mean()-s.ewm(span=26,adjust=False).mean()).ewm(span=9,adjust=False).mean())
    d['ema_cross']=(ema_fast-ema_slow)/c
    d['macd_scaled']=(macd-macd_signal)/c
    diff=c-_gshift(d,'close',1)
    up=np.maximum(diff,0);down=np.maximum(-diff,0)
    gains=up.groupby(d['day']).transform(lambda s:s.rolling(14,min_periods=14).mean())
    losses=down.groupby(d['day']).transform(lambda s:s.rolling(14,min_periods=14).mean())
    rsi=np.where((gains+losses)>0,gains/(gains+losses),.5)
    d['rsi_scaled']=rsi-.5
    mid=g['close'].transform(lambda s:s.rolling(20,min_periods=20).mean())
    std=g['close'].transform(lambda s:s.rolling(20,min_periods=20).std())
    d['bollinger_position']=(c-mid)/(2*std.replace(0,np.nan))
    d['price_to_ema']=(c-ema_slow)/c
    # same-day EXACT future endpoints - no overnight leakage in either label or tests
    for lag in (0,15,30,60):
        # Only permit lags and horizons expressible in bars of this TF.
        if lag%tf: continue
        start=lag//tf; end=(lag+60)//tf
        current_price=c if start==0 else g['close'].shift(-start)
        target=g['close'].shift(-end)
        start_dt=dt if start==0 else g['dt'].shift(-start)
        end_dt=g['dt'].shift(-end)
        d[f'future_{lag}m']=np.where((start_dt-dt==pd.Timedelta(minutes=lag)) & (end_dt-dt==pd.Timedelta(minutes=lag+60)),target/current_price-1,np.nan)
    d['future_base']=d['future_0m']
    d['long_label']=(d['future_base']>=.0025).astype(np.int8)
    d['short_label']=(d['future_base']<=-.0025).astype(np.int8)
    d['rising']=d['long_label']
    d['falling']=d['short_label']
    valid=d[FEATURES+['future_base']].notna().all(axis=1)&(d['split']!='gap')
    d=d.loc[valid].copy().reset_index(drop=True)
    d['tf']=tf
    d.drop(columns=['weighted_close'],inplace=True)
    return d


def load_or_prepare(root, output, tf):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    path=output/f'SBRF_{tf}m_research.csv.gz'
    if path.exists():
        d=pd.read_csv(path,parse_dates=['dt'])
    else:
        f=Path(root)/'data'/FILE_NAMES[tf]
        d=make_frame(f,tf)
        cols=['dt','day','split','tf','open','high','low','close','volume','long_label','short_label']+FEATURES+[
            c for c in ['future_0m','future_15m','future_30m','future_60m'] if c in d.columns]
        d=d[cols]
        d.to_csv(path,index=False,compression='gzip')
    return d

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--raw',required=True);p.add_argument('--out',required=True);p.add_argument('--tf',type=int,nargs='*',default=list(TIMEFRAMES))
    args=p.parse_args()
    for tf in args.tf:
        d=load_or_prepare(args.raw,args.out,tf)
        print(tf,len(d),d.groupby('split')[['long_label','short_label']].agg(['size','sum']).to_string(),flush=True)
