"""Fixed small neural net on SBRF and five real crypto tables. Technical smoke, not a GA result."""
import argparse,json,time,os
from pathlib import Path
import numpy as np,pandas as pd,torch
from torch import nn
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import average_precision_score
HERE=Path(__file__).resolve().parent;PUBLIC=HERE.parent
p=argparse.ArgumentParser();p.add_argument("--crypto",default=str(PUBLIC/"data/prepared_crypto"));p.add_argument("--sbrf",default=str(PUBLIC/"v12_source/prepared/SBRF_1m_research.csv.gz"));p.add_argument("--output",default=str(PUBLIC/"local_checks/multi_market_smoke.json"));p.add_argument("--epochs",type=int,default=3);a=p.parse_args()
from prepare_crypto import FEATURES
paths=[Path(a.sbrf)]+sorted(Path(a.crypto).glob("*_1m_research.csv.gz"));results=[]
for path in paths:
 d=pd.read_csv(path);X=d[FEATURES].to_numpy(np.float32);split=d.split.to_numpy();tr=np.where(split=="train")[0];sel=np.where(split=="select")[0];check=np.where(split=="check")[0]
 for side in ["long","short"]:
  start=time.perf_counter();y=d[side+"_label"].to_numpy(np.int8);pos=tr[y[tr]==1];ng=tr[y[tr]==0];neg=np.random.default_rng(500).choice(ng,size=min(len(ng),2*len(pos)),replace=False);ids=np.r_[pos,neg]
  assert len(pos)>0 and len(neg)>0
  scaler=StandardScaler().fit(X[ids]);tx=np.clip(scaler.transform(X[ids]),-20,20).astype("float32");labels=y[ids].astype("float32")
  torch.set_num_threads(1);torch.manual_seed(31);net=nn.Sequential(nn.Linear(26,24),nn.ReLU(),nn.Dropout(.05),nn.Linear(24,12),nn.ReLU(),nn.Dropout(.05),nn.Linear(12,1));optim=torch.optim.AdamW(net.parameters(),lr=.003,weight_decay=.003)
  xx=torch.from_numpy(tx);yy=torch.from_numpy(labels);rng=np.random.default_rng(31)
  for epoch in range(a.epochs):
   net.train();perm=rng.permutation(len(ids))
   for i in range(0,len(ids),384):
    ix=perm[i:i+384];optim.zero_grad(set_to_none=True);loss=nn.functional.binary_cross_entropy_with_logits(net(xx[ix]).reshape(-1),yy[ix]);assert torch.isfinite(loss);loss.backward();optim.step()
  # Freeze the completed model before touching either evaluation block. No selection/tuning.
  net.eval();net.requires_grad_(False);metrics={}
  for name,ix in [("select",sel),("check",check)]:
   with torch.no_grad():pred=torch.sigmoid(net(torch.from_numpy(np.clip(scaler.transform(X[ix]),-20,20).astype("float32"))).reshape(-1)).numpy()
   assert np.isfinite(pred).all();base=float(y[ix].mean());ap=float(average_precision_score(y[ix],pred)) if 0<base<1 else None
   metrics[name]={"rows":len(ix),"positive_fraction":base,"ap":ap,"lift":ap/base if ap is not None else None}
  results.append({"file":path.name,"side":side,"epochs":a.epochs,"parameter_count":sum(x.numel() for x in net.parameters()),"train_positive":len(pos),"train_negative":len(neg),"metrics":metrics,"seconds":time.perf_counter()-start})
  print(path.name,side,'trained',len(ids),flush=True)
out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps({"purpose":"Technical data/model compatibility only; no genetic selection and no profitability claim","results":results},indent=2),encoding="utf8");print('Completed',len(results),'real training runs',flush=True)
