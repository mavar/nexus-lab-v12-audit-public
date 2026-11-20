"""Export real MEXC one-minute trade bars with independently observed quote quality."""
import os,json,time,hashlib,datetime,argparse
from pathlib import Path
import numpy as np,pandas as pd,duckdb,pyarrow.parquet as pq
P=argparse.ArgumentParser();P.add_argument("--source",default="G:/mexc_base/exchange=MEXC");P.add_argument("--output",required=True);a=P.parse_args()
root=Path(a.source);out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
symbols=["SOLUSDT","BTCUSDT","ETHUSDT","XRPUSDT","DOGEUSDT"]
start=pd.Timestamp("2026-06-03",tz="UTC");end=pd.Timestamp("2026-07-01",tz="UTC");grid=np.arange(start.value//1000000,end.value//1000000,60000,dtype=np.int64)
con=duckdb.connect();con.execute("SET threads=1");con.execute("SET memory_limit='1GB'")
manifest={"exchange":"MEXC","market":"spot","bar":"1 minute by local receive timestamp","start_utc":str(start),"end_utc_exclusive":str(end),"symbols":{},"data_kind":"real historical observations, no synthetic or forward-filled prices","trade_volume_unit":"base asset; quote_volume USDT","duplicate_policy":"keep all trade rows: exchange trade ID unavailable; identical-looking rows can be legitimate","split_proposal":{"train_end_exclusive":"2026-06-21T00:00:00Z","select_end_exclusive":"2026-06-26T00:00:00Z","check_end_exclusive":"2026-07-01T00:00:00Z"}}
sources=[]
for sym in symbols:
 st=time.perf_counter();print("Export",sym,flush=True)
 files={stream:sorted((root/("stream="+stream)/("symbol="+sym)).glob("date=*/*.parquet")) for stream in ["trades","book_ticker"]}
 for stream,paths in files.items():
  for p in paths:
   sources.append({"stream":stream,"symbol":sym,"relative_source":p.relative_to(root).as_posix(),"bytes":p.stat().st_size,"rows":pq.ParquetFile(p).metadata.num_rows,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
 # Stable tie order uses original physical row order, single-threaded scan. Labels never enter aggregation.
 trades=con.execute("""WITH r AS (
 SELECT row_number() OVER () source_row,recv_ts_ms::BIGINT t,price::DOUBLE p,quantity::DOUBLE q,trade_time_ms
 FROM read_parquet(?,hive_partitioning=false,union_by_name=true)),
 v AS (SELECT *,isfinite(p) AND p>0 AND isfinite(q) AND q>0 ok FROM r)
 SELECT (t//60000)*60000 minute_ms,count(*) trade_rows,
 count(*) FILTER(WHERE NOT ok) invalid_trade_rows,
 first(p ORDER BY t,source_row) FILTER(WHERE ok) open,
 max(p) FILTER(WHERE ok) high,min(p) FILTER(WHERE ok) low,
 last(p ORDER BY t,source_row) FILTER(WHERE ok) AS "close",
 sum(q) FILTER(WHERE ok) volume,sum(p*q) FILTER(WHERE ok) quote_volume,
 count(*) FILTER(WHERE ok) trade_count,
 count(*)-count(DISTINCT (t,p,q,trade_time_ms)) identical_looking_trade_rows
 FROM v GROUP BY 1 ORDER BY 1""",[[str(p) for p in files["trades"]]]).df()
 quotes=con.execute("""WITH r AS (
 SELECT row_number() OVER () source_row,recv_ts_ms::BIGINT t,best_bid::DOUBLE bid,best_ask::DOUBLE ask,bid_qty::DOUBLE bq,ask_qty::DOUBLE aq
 FROM read_parquet(?,hive_partitioning=false,union_by_name=true)),
 v AS (SELECT *,isfinite(bid) AND isfinite(ask) AND bid>0 AND ask>=bid AND isfinite(bq) AND bq>=0 AND isfinite(aq) AND aq>=0 ok FROM r),
 g AS (SELECT *,t-lag(t) OVER (ORDER BY t,source_row) quote_gap_ms FROM v)
 SELECT (t//60000)*60000 minute_ms,count(*) quote_rows,
 count(*) FILTER(WHERE NOT ok) invalid_quote_rows,
 last(bid ORDER BY t,source_row) FILTER(WHERE ok) best_bid,
 last(ask ORDER BY t,source_row) FILTER(WHERE ok) best_ask,
 last(bq ORDER BY t,source_row) FILTER(WHERE ok) bid_qty,
 last(aq ORDER BY t,source_row) FILTER(WHERE ok) ask_qty,
 max(t) FILTER(WHERE ok) last_quote_ts_ms,max(quote_gap_ms) max_quote_gap_ms
 FROM g GROUP BY 1 ORDER BY 1""",[[str(p) for p in files["book_ticker"]]]).df()
 d=pd.DataFrame({"minute_ms":grid}).merge(trades,on="minute_ms",how="left").merge(quotes,on="minute_ms",how="left")
 for col in ["trade_rows","invalid_trade_rows","trade_count","identical_looking_trade_rows","quote_rows","invalid_quote_rows"]:d[col]=d[col].fillna(0).astype("int64")
 d["last_quote_age_ms"]=d.minute_ms+60000-d.last_quote_ts_ms
 d["price_bar_ok"]=(d.trade_count>0)&(d.invalid_trade_rows==0)
 d["quote_bar_ok"]=(d.quote_rows>0)&(d.invalid_quote_rows==0)&(d.last_quote_age_ms<=2000)&(d.max_quote_gap_ms<=2000)
 d["symbol"]=sym;d["dt"]=pd.to_datetime(d.minute_ms+60000,unit="ms",utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
 d["bar_start_utc"]=pd.to_datetime(d.minute_ms,unit="ms",utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
 d["spread_bps"]=(d.best_ask-d.best_bid)/((d.best_ask+d.best_bid)/2)*10000
 cols=["symbol","dt","bar_start_utc","open","high","low","close","volume","quote_volume","trade_count","trade_rows","identical_looking_trade_rows","invalid_trade_rows","best_bid","best_ask","bid_qty","ask_qty","spread_bps","quote_rows","invalid_quote_rows","last_quote_ts_ms","last_quote_age_ms","max_quote_gap_ms","price_bar_ok","quote_bar_ok"]
 d=d[cols]
 path=out/(sym+"_1m.csv");d.to_csv(path,index=False,float_format="%.12g")
 quality=d.assign(day=d.bar_start_utc.str[:10]).groupby("day").agg(rows=("dt","size"),price_bars=("price_bar_ok","sum"),quote_bars=("quote_bar_ok","sum"),trades=("trade_count","sum"),quote_rows=("quote_rows","sum"),identical_looking_trade_rows=("identical_looking_trade_rows","sum"))
 quality.to_csv(out/(sym+"_quality_by_day.csv"))
 info={"file":path.name,"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"calendar_minute_rows":len(d),"price_bars":int(d.price_bar_ok.sum()),"quote_bars":int(d.quote_bar_ok.sum()),"trade_rows":int(d.trade_rows.sum()),"identical_looking_trade_rows":int(d.identical_looking_trade_rows.sum()),"raw_quote_rows":int(d.quote_rows.sum()),"missing_price_minutes":int((~d.price_bar_ok).sum()),"observed_days":int((quality.price_bars>0).sum()),"seconds":time.perf_counter()-st}
 manifest["symbols"][sym]=info
 (out/"DATA_MANIFEST.json").write_text(json.dumps(manifest,indent=2),encoding="utf8")
 print(sym,info,flush=True)
 # Five-row plain JSON example lets an AI understand the exact format without reading the whole data file.
 sample=d[d.price_bar_ok].head(5).replace({np.nan:None}).to_dict("records")
 (out/(sym+"_example.json")).write_text(json.dumps(sample,indent=2,allow_nan=False),encoding="utf8")
(out/"SOURCE_FILES.json").write_text(json.dumps(sources,indent=2),encoding="utf8")
print("Completed",flush=True)
