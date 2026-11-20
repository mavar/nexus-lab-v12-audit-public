"""Causal 26-feature V12-compatible table from real MEXC trade bars. No trading returns."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
GROUPS={"price":["ret1","ret3","ret6","body","range","upper","lower","volatility"],"time":["hour_s","hour_c","weekday_s","weekday_c","minute_s","minute_c","hour_start","monday","friday"],"volume":["vol_ratio","vol_change","close_volume_gravity","volume_pivot_distance"],"technical":["ema_cross","macd_scaled","rsi_scaled","bollinger_position","price_to_ema"]}
FEATURES=sum(GROUPS.values(),[])

def prepare(path,tf=1,horizon=60,threshold=.0025):
 raw=pd.read_csv(path,parse_dates=["dt"]);raw["dt"]=pd.to_datetime(raw.dt,utc=True)
 z=raw.set_index("dt");# dt is the time at which the COMPLETED bar is available.
 if tf>1:
  z=z.resample(str(tf)+"min",closed="right",label="right").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum","trade_count":"sum","price_bar_ok":"sum"})
  z.loc[z.price_bar_ok!=tf,["open","high","low","close","volume"]]=np.nan
 else:z.loc[~z.price_bar_ok,["open","high","low","close","volume"]]=np.nan
 d=z.reset_index()[["dt","open","high","low","close","volume"]].copy();d["day"]=d.dt.dt.strftime("%Y-%m-%d");d["tf"]=tf
 # Identical intraday policy to the audited SBRF example, made explicit for a 24h crypto market.
 g=d.groupby("day",sort=False);c=d.close;o=d.open;h=d.high;l=d.low;v=d.volume;dt=d.dt
 shift=lambda col,k:g[col].shift(k)
 for k in [1,3,6]:d["ret"+str(k)]=np.log(c/shift("close",k))
 d["body"]=(c-o)/c;d["range"]=(h-l)/c;d["upper"]=(h-np.maximum(o,c))/c;d["lower"]=(np.minimum(o,c)-l)/c
 d["volatility"]=g["ret1"].transform(lambda s:s.rolling(12,min_periods=12).std())
 minute=dt.dt.hour*60+dt.dt.minute;wd=dt.dt.dayofweek
 d["hour_s"]=np.sin(2*np.pi*minute/1440);d["hour_c"]=np.cos(2*np.pi*minute/1440)
 d["weekday_s"]=np.sin(2*np.pi*wd/7);d["weekday_c"]=np.cos(2*np.pi*wd/7)
 d["minute_s"]=np.sin(2*np.pi*dt.dt.minute/60);d["minute_c"]=np.cos(2*np.pi*dt.dt.minute/60)
 d["hour_start"]=(dt.dt.minute<tf).astype(float);d["monday"]=(wd==0).astype(float);d["friday"]=(wd==4).astype(float)
 d["vol_ratio"]=np.log1p(v)-np.log1p(g.volume.transform(lambda s:s.rolling(12,min_periods=12).mean()));d["vol_change"]=np.log1p(v)-np.log1p(shift("volume",1))
 d["weighted_close"]=c*v;center=g.weighted_close.transform(lambda s:s.rolling(12,min_periods=12).sum())/g.volume.transform(lambda s:s.rolling(12,min_periods=12).sum()).replace(0,np.nan)
 d["close_volume_gravity"]=(c-center)/c
 pivot=np.full(len(d),np.nan)
 for _,ix in g.indices.items():
  ix=np.asarray(ix);vv=v.iloc[ix].to_numpy();cc=c.iloc[ix].to_numpy()
  for j in range(11,len(ix)):
   window=vv[j-11:j+1]
   if np.isfinite(window).all():pivot[ix[j]]=cc[j-11+int(np.argmax(window))]
 d["volume_pivot_distance"]=(c-pivot)/c
 fast=g.close.transform(lambda s:s.ewm(span=5,adjust=False).mean());slow=g.close.transform(lambda s:s.ewm(span=12,adjust=False).mean());slow2=g.close.transform(lambda s:s.ewm(span=26,adjust=False).mean())
 signal=g.close.transform(lambda s:(s.ewm(span=5,adjust=False).mean()-s.ewm(span=26,adjust=False).mean()).ewm(span=9,adjust=False).mean())
 d["ema_cross"]=(fast-slow)/c;d["macd_scaled"]=(fast-slow2-signal)/c;diff=c-shift("close",1)
 up=np.maximum(diff,0).groupby(d.day).transform(lambda s:s.rolling(14,min_periods=14).mean());down=np.maximum(-diff,0).groupby(d.day).transform(lambda s:s.rolling(14,min_periods=14).mean())
 d["rsi_scaled"]=np.where(up+down>0,up/(up+down),.5)-.5
 mid=g.close.transform(lambda s:s.rolling(20,min_periods=20).mean());std=g.close.transform(lambda s:s.rolling(20,min_periods=20).std());d["bollinger_position"]=(c-mid)/(2*std.replace(0,np.nan));d["price_to_ema"]=(c-slow)/c
 # Reject a feature window with gaps instead of letting ewm silently bridge them.
 past_ok=g.close.transform(lambda s:s.notna().rolling(26,min_periods=26).sum()).eq(26)
 for lag in [0,15,30,60]:
  if lag%tf or horizon%tf:continue
  n=(lag+horizon)//tf;future_ok=g.close.transform(lambda s:s.notna().rolling(n+1,min_periods=n+1).sum().shift(-n)).eq(n+1)
  d["future_"+str(lag)+"m"]=np.where(future_ok,shift("close",-n)/shift("close",-(lag//tf))-1,np.nan)
 d["future_base"]=d.future_0m;d["long_label"]=(d.future_base>=threshold).astype("int8");d["short_label"]=(d.future_base<=-threshold).astype("int8")
 d["split"]=np.select([d.dt<pd.Timestamp("2026-06-21",tz="UTC"),d.dt<pd.Timestamp("2026-06-26",tz="UTC"),d.dt<pd.Timestamp("2026-07-01",tz="UTC")],["train","select","check"],default="exclude")
 # Do not let the labeling horizon cross a partition or UTC day boundary.
 end=dt+pd.Timedelta(minutes=horizon);cut=pd.Series(np.where(d.split=="train","2026-06-21",np.where(d.split=="select","2026-06-26","2026-07-01")),index=d.index)
 boundary_ok=end<pd.to_datetime(cut,utc=True)
 keep=past_ok&boundary_ok&d[FEATURES+["future_base"]].notna().all(axis=1)&(d.split!="exclude")
 d["source_row_id"]=np.arange(len(d));d["symbol"]=str(raw.symbol.iloc[0]);d=d.loc[keep].copy()
 # All delayed hypotheses also obey their partition boundaries.
 for lag in [15,30,60]:
  col="future_"+str(lag)+"m"
  if col in d:d.loc[d.dt+pd.Timedelta(minutes=horizon+lag)>=pd.to_datetime(cut.loc[d.index],utc=True),col]=np.nan
 cols=["symbol","source_row_id","dt","day","split","tf","open","high","low","close","volume","long_label","short_label"]+FEATURES+[x for x in d if x.startswith("future_")]
 d=d[cols].reset_index(drop=True);assert np.isfinite(d[FEATURES].to_numpy()).all();return d

if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--data",required=True);p.add_argument("--out",required=True);p.add_argument("--tf",type=int,nargs="+",default=[1,5,10,15,30]);a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True);manifest={}
 for source in sorted(Path(a.data).glob("*_1m.csv")):
  for tf in a.tf:
   d=prepare(source,tf);dest=out/(source.stem.split("_")[0]+"_"+str(tf)+"m_research.csv.gz");d.to_csv(dest,index=False,compression="gzip")
   info={"rows":len(d),"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"sha256":hashlib.sha256(dest.read_bytes()).hexdigest(),"splits":{str(k):{"rows":len(z),"days":z.day.nunique(),"long":int(z.long_label.sum()),"short":int(z.short_label.sum())} for k,z in d.groupby("split")}}
   manifest[dest.name]=info;print(dest.name,len(d),flush=True)
 (out/"PREPARED_MANIFEST.json").write_text(json.dumps(manifest,indent=2),encoding="utf8")
