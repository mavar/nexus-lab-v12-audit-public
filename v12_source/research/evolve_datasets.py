# -*- coding: utf-8 -*-
"""NEXUS V12: evolutionary selection of TRAIN examples, LONG/SHORT separately.

Key invariants:
  * ALL labels/feature engineering are built before the search from the provided TRAIN data.
  * No SELECT or CHECK rows enter a chromosome; SELECT only scores candidates.
  * CHECK is never read while evolving; held-out check only after the frozen winner.
  * Every distinct chromosome trains a fresh PyTorch net, including mutated children.
  * Exact chromosome member IDs, provenance, parents and per-epoch curves are logged.
  * Resume uses append-only candidate journal; interrupted candidate is rerun.
"""
from __future__ import annotations
import argparse,base64,copy,csv,gzip,hashlib,json,os,time,zlib
from collections import Counter
from pathlib import Path
import numpy as np
from sklearn.metrics import average_precision_score,log_loss
from sklearn.preprocessing import StandardScaler
from .prepare_finam import TIMEFRAMES,FEATURES,FEATURE_INDEX,load_or_prepare

SEED=20261119

def metric(y,p):
    y=np.asarray(y,dtype=np.int8);p=np.asarray(p,dtype=float)
    b=float(y.mean()) if len(y) else 0.
    if len(y)<4 or not (0<b<1):return {'ap':None,'lift':None,'base':round(b,6),'top_good':0,'top_total':0}
    ap=float(average_precision_score(y,p));k=max(1,int(np.ceil(len(y)*.01)))
    top=np.argsort(-p,kind='stable')[:k]
    return {'ap':round(ap,6),'lift':round(ap/b,5),'base':round(b,6),'top_good':int(y[top].sum()),'top_total':k}

def encode_ids(ids):
    x=np.asarray(sorted(set(map(int,ids))),dtype='<u4')
    return base64.b64encode(zlib.compress(x.tobytes(),6)).decode('ascii')
def decode_ids(s):
    return np.frombuffer(zlib.decompress(base64.b64decode(s)),dtype='<u4').astype(np.int64)

def stamp(g):
    keys=['pos','early','unmarked','arch','lr','dropout','epochs']
    return hashlib.sha256(json.dumps({k:g[k] for k in keys},sort_keys=True).encode()).hexdigest()[:16]

def pools_for(frame,side):
    y=frame[f'{side}_label'].to_numpy(dtype=np.int8)
    tr=np.where(frame.split.to_numpy()=='train')[0]
    pos=tr[y[tr]==1];neg=tr[y[tr]==0]
    # Candidate pre-signals are TRAIN-only. A point is promoted only provisionally.
    sign=1 if side=='long' else -1
    early={}
    for lag in (15,30,60):
        col=f'future_{lag}m'
        if col in frame:
            ret=frame[col].to_numpy(dtype=float)
            early[lag]=neg[np.isfinite(ret[neg])&(sign*ret[neg]>=.0025)]
    return pos,neg,early

def initial(pop_size,frame,side,tf):
    base,neg,early=pools_for(frame,side)
    candidates=[]
    modes=['full','random75','random50','random90','by_day','early','unknown','random60']
    for i in range(pop_size):
        rng=np.random.default_rng(SEED+tf*10000+(side=='short')*900000+i*871)
        mode=modes[i] if i<len(modes) else modes[1+(i-len(modes))%(len(modes)-1)]
        if mode=='full': p=base
        elif mode=='random90':p=rng.choice(base,max(1,int(len(base)*.9)),replace=False)
        elif mode=='random75':p=rng.choice(base,max(1,int(len(base)*.75)),replace=False)
        elif mode=='random60':p=rng.choice(base,max(1,int(len(base)*.60)),replace=False)
        elif mode=='random50':p=rng.choice(base,max(1,int(len(base)*.50)),replace=False)
        elif mode=='by_day':
            groups=frame.day.to_numpy()[base]
            unique=np.unique(groups)
            rng.shuffle(unique);p=base[np.isin(groups,unique[:max(8,int(len(unique)*.75))])]
        else:p=rng.choice(base,max(1,int(len(base)*.8)),replace=False)
        e=np.empty(0,dtype=int);u=np.empty(0,dtype=int)
        if mode=='early' and early:
            lag=next(iter(early));e=rng.choice(early[lag],size=min(len(early[lag]),max(2,int(len(p)*.04))),replace=False)
        if mode=='unknown':u=rng.choice(neg,size=min(len(neg),max(2,int(len(p)*.03))),replace=False)
        candidates.append(dict(pos=encode_ids(p),early=encode_ids(e),unmarked=encode_ids(u),arch='small',lr=.003,dropout=.05,epochs=None,parent='-',operation=mode))
    return candidates

def children(parents,population,frame,side,tf,gen):
    base,neg,early=pools_for(frame,side)
    rng=np.random.default_rng(SEED+tf*10000+(side=='short')*900000+gen*10603)
    eligible=parents[:max(2,min(7,len(parents)//3))]
    kids=[copy.deepcopy(parents[0]['gene']),copy.deepcopy(parents[1]['gene'])] if len(parents)>1 else [copy.deepcopy(parents[0]['gene'])]
    for g in kids:g['operation']='elite';g['parent']=stamp(g)
    ops=['swap','grow','shrink','swap','grow','new_early','new_unknown','remove_unknown','crossover','random_immigrant','shrink','swap']
    while len(kids)<population:
        op=ops[int(rng.integers(len(ops)))]
        father=eligible[int(rng.integers(len(eligible)))]
        gene=copy.deepcopy(father['gene']);gene['parent']=stamp(father['gene']);gene['operation']=op
        p=decode_ids(gene['pos']);e=decode_ids(gene['early']);u=decode_ids(gene['unmarked'])
        if op=='random_immigrant':
            k=max(25,int(len(base)*float(rng.uniform(.35,1))))
            p=rng.choice(base,min(len(base),k),replace=False);e=u=np.empty(0,dtype=int)
        elif op=='crossover':
            mom=eligible[int(rng.integers(len(eligible)))]
            q=decode_ids(mom['gene']['pos']);p=np.union1d(p,q) if rng.random()<.5 else np.intersect1d(p,q)
            if len(p)<max(30,int(.25*len(base))):p=np.union1d(p,rng.choice(base,max(1,int(.3*len(base))),replace=False))
        elif op=='grow':
            add=np.setdiff1d(base,p,assume_unique=False)
            if len(add):p=np.union1d(p,rng.choice(add,size=min(len(add),max(2,int(len(p)*rng.uniform(.05,.25)))),replace=False))
        elif op=='shrink':
            if len(p)>max(50,int(len(base)*.25)):
                n=min(len(p)-max(50,int(len(base)*.25)),max(2,int(len(p)*rng.uniform(.05,.22))))
                p=rng.choice(p,size=len(p)-n,replace=False)
        elif op=='swap':
            n=max(2,int(len(p)*rng.uniform(.05,.22)))
            if len(p)>n:p=rng.choice(p,len(p)-n,replace=False)
            avail=np.setdiff1d(base,p,assume_unique=False)
            if len(avail):p=np.union1d(p,rng.choice(avail,size=min(len(avail),n),replace=False))
        elif op=='new_early' and early:
            lag=int(rng.choice(list(early)));avail=np.setdiff1d(early[lag],np.r_[p,e,u])
            if len(avail):e=np.union1d(e,rng.choice(avail,size=min(len(avail),max(2,int(len(p)*rng.uniform(.01,.07)))),replace=False))
            gene['delay_minutes']=lag
        elif op=='new_unknown':
            avail=np.setdiff1d(neg,np.r_[p,e,u]);maxnew=min(len(avail),max(2,int(len(p)*rng.uniform(.01,.07))))
            if maxnew:u=np.union1d(u,rng.choice(avail,size=maxnew,replace=False))
        elif op=='remove_unknown':
            if len(u):u=rng.choice(u,size=len(u)//2,replace=False) if len(u)>1 else np.empty(0,int)
            if len(e):e=rng.choice(e,size=len(e)//2,replace=False) if len(e)>1 else np.empty(0,int)
        gene.update(pos=encode_ids(p),early=encode_ids(e),unmarked=encode_ids(u))
        kids.append(gene)
    return kids

def train_candidate(X,y,genes,train_pos,train_neg,select,epochs,device,fold_days,seed=31,shuffle_training_labels=False):
    import torch
    from torch import nn
    torch.set_num_threads(1)
    torch.manual_seed(int(seed))
    tr=np.r_[train_pos,train_neg]
    labels=np.r_[np.ones(len(train_pos),dtype=np.float32),np.zeros(len(train_neg),dtype=np.float32)]
    if shuffle_training_labels:labels=np.random.default_rng(5529).permutation(labels)
    scaler=StandardScaler().fit(X[tr]);tx=np.clip(scaler.transform(X[tr]).astype('float32'),-20,20)
    vx=np.clip(scaler.transform(X[select]).astype('float32'),-20,20)
    architecture=genes['arch'];d=X.shape[1]
    widths={'small':[24,12],'wide':[64,32],'deep':[32,24,16,8],'linear':[]}[architecture]
    layers=[]
    for w in widths:
        layers.extend([nn.Linear(d,w),nn.ReLU()]);
        if genes['dropout']:layers.append(nn.Dropout(float(genes['dropout'])))
        d=w
    layers.append(nn.Linear(d,1));net=nn.Sequential(*layers).to(device)
    x=torch.from_numpy(tx).to(device);t=torch.from_numpy(labels).to(device);q=torch.from_numpy(vx).to(device)
    opt=torch.optim.AdamW(net.parameters(),lr=float(genes['lr']),weight_decay=.003)
    weights=np.r_[np.ones(len(decode_ids(genes['pos'])),np.float32),np.full(len(decode_ids(genes['early'])),.55,np.float32),np.full(len(decode_ids(genes['unmarked'])),.2,np.float32),np.ones(len(train_neg),np.float32)]
    w=torch.from_numpy(weights).to(device)
    rng=np.random.default_rng(int(seed))
    monitored=set([1,2,4,8,12,16,24,32,40,64,epochs]);monitored={e for e in monitored if 1<=e<=epochs}
    curve=[];ep_time=[]
    for ep in range(1,epochs+1):
        start=time.perf_counter();net.train();perm=rng.permutation(len(tr))
        for startidx in range(0,len(tr),384):
            ids=torch.as_tensor(perm[startidx:startidx+384],dtype=torch.long,device=device)
            opt.zero_grad(set_to_none=True)
            logits=net(x[ids]).reshape(-1)
            loss=(nn.functional.binary_cross_entropy_with_logits(logits,t[ids],reduction='none')*w[ids]).mean()
            if not torch.isfinite(loss):raise ValueError('NaN loss during training')
            loss.backward();opt.step()
        ep_time.append(round(time.perf_counter()-start,3))
        if ep in monitored:
            net.eval()
            with torch.no_grad():
                pred=torch.sigmoid(net(q).reshape(-1)).cpu().numpy()
                train_pred=torch.sigmoid(net(x).reshape(-1)).cpu().numpy()
            info=metric(y[select],pred)
            # log loss on actual (not pseudo) positive training labels
            trloss=float(log_loss(labels,np.clip(train_pred,1e-6,1-1e-6),labels=[0,1]))
            valloss=float(log_loss(y[select],np.clip(pred,1e-6,1-1e-6),labels=[0,1]))
            curve.append({'epoch':ep,'train_loss':round(trloss,5),'select_loss':round(valloss,5),'select_ap':info['ap'],'select_lift':info['lift'],'seconds':round(sum(ep_time),3)})
    return pred,curve

def score_candidate(frame,y,select,pred,npos,n_days,curve):
    days=frame.day.to_numpy()[select]
    cut='2026-08-24'
    segments=[days<cut,days>=cut]
    folds=[]
    for mask in segments:
        st=metric(y[select][mask],pred[mask]);folds.append(st)
        if st['lift'] is None:return -100.,folds
    lifts=[f['lift'] for f in folds]
    # Stability on two later windows, rather than minimizing trades.
    score=.7*min(lifts)+.3*float(np.mean(lifts))-.10*abs(lifts[0]-lifts[1])
    if npos<70:score-=.5
    if n_days<9:score-=1.
    return round(float(score),5),folds

def create_context(frame,X,side,tf):
    y=frame[f'{side}_label'].to_numpy(np.int8)
    pospool,negativepool,early=pools_for(frame,side)
    split=frame.split.to_numpy();select=np.where(split=='select')[0];check=np.where(split=='check')[0]
    return dict(frame=frame,X=X,y=y,pospool=pospool,negativepool=negativepool,early=early,select=select,check=check,tf=tf,side=side)

def eval_gene(g,ctx,epochs,device):
    pos=decode_ids(g['pos']);early=decode_ids(g['early']);new=decode_ids(g['unmarked']);chosen=np.r_[pos,early,new]
    if len(pos)<30 or len(chosen)!=len(set(map(int,chosen))):raise ValueError('Invalid chromosome: too few originals or duplicate points')
    if not (ctx['frame'].split.iloc[chosen]=='train').all():raise ValueError('A non-TRAIN row entered the chromosome')
    if not np.isin(pos,ctx['pospool']).all():raise ValueError('Unmarked original selected')
    unique_days=len(np.unique(ctx['frame'].day.iloc[chosen]))
    if unique_days<7:raise ValueError('Too few independent training days')
    nneg=min(len(ctx['negativepool'])-len(early)-len(new),2*len(chosen))
    negatives=np.setdiff1d(ctx['negativepool'],chosen,assume_unique=False)
    neg=np.random.default_rng(500+ctx['tf']).choice(negatives,size=min(len(negatives),nneg),replace=False)
    pred,curve=train_candidate(ctx['X'],ctx['y'],g,chosen,neg,ctx['select'],epochs,device,None)
    score,folds=score_candidate(ctx['frame'],ctx['y'],ctx['select'],pred,len(chosen),unique_days,curve)
    best_ap=max([(v['select_ap'],v['epoch']) for v in curve if v['select_ap'] is not None],default=(None,None))
    last_ap=curve[-1]['select_ap']
    return dict(score=score,folds=folds,curve=curve,train_size=int(len(chosen)),n_original=len(pos),n_early=len(early),n_unmarked=len(new),n_negative=len(neg),n_days=unique_days,
        best_ap_epoch=best_ap[1],overfit_ap_drop=(round(best_ap[0]-last_ap,5) if best_ap[0] is not None and last_ap is not None else None),
        member_sample=[int(v) for v in chosen[:30]])

def _append_jsonl(path,rec):
    with open(path,'a',encoding='utf8') as f:
        f.write(json.dumps(rec,ensure_ascii=False,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())

def _read_jsonl(path):
    if not path.exists():return []
    records=[]; goodpos=0
    with open(path,'rb') as f:
        while True:
            line=f.readline()
            if not line:break
            try:records.append(json.loads(line.decode('utf8')));goodpos=f.tell()
            except (UnicodeDecodeError,json.JSONDecodeError):break
    if path.stat().st_size!=goodpos:
        # Windows power-off can leave a torn final line. Preserve it separately.
        with open(path,'rb+') as f:
            f.seek(goodpos);tail=f.read();f.truncate(goodpos)
        (path.parent/'RECOVERED_INCOMPLETE_LINE.bin').write_bytes(tail)
    return records

def run_one(ctx,out,generations,population,epochs,device,report_every=1):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    journal=out/'CANDIDATES.jsonl'
    old=_read_jsonl(journal);old_by_slot={(r['gen'],r['slot']):r for r in old}
    if len(old)!=len(old_by_slot):raise RuntimeError('Duplicate journal slot. Stop and inspect before restarting.')
    fingerprint=hashlib.sha256(ctx["frame"][["dt","close",f"{ctx['side']}_label"]].to_csv(index=False).encode()).hexdigest()
    if old:
        meta=json.loads((out/'SETTINGS.json').read_text(encoding='utf8'))
        assert meta['generations']==generations and meta['population']==population and meta['epochs']==epochs, 'Cannot resume with changed settings'
        assert meta.get('data_sha256')==fingerprint, 'Cannot resume with different source data'
        if (out/'RESULT.json').exists():return json.loads((out/'RESULT.json').read_text(encoding='utf8'))
        print(f'Продолжаю {ctx["tf"]}m {ctx["side"]}: {len(old)} already evaluated',flush=True)
    else:
        (out/'SETTINGS.json').write_text(json.dumps(dict(generations=generations,population=population,epochs=epochs,device=device,tf=ctx['tf'],side=ctx['side'],data_sha256=fingerprint),ensure_ascii=False,indent=2),encoding='utf8')
    best=None;generation_history=[];seen_original=set();seen_early=set();seen_unmarked=set();unique_fingerprints=set();valid_count=0;trained_count=0;error_count=0;ops=Counter();cache={};inclusions=np.zeros(len(ctx['frame']),dtype=np.int32)
    pop=initial(population,ctx['frame'],ctx['side'],ctx['tf'])
    start=time.perf_counter()
    for gen in range(1,generations+1):
        records=[]
        for slot,gene in enumerate(pop,1):
            if (gen,slot) in old_by_slot:
                r=old_by_slot[(gen,slot)];assert stamp(gene)==r['id'],'Journal mismatch: source/config changed'
            else:
                st=time.perf_counter();ident=stamp(gene)
                if ident in cache:
                    r=copy.deepcopy(cache[ident]);r['cached']=True;r['elapsed']=0.
                else:
                    try:r=eval_gene(gene,ctx,epochs,device);r['error']=None
                    except Exception as e:r=dict(score=-100.,curve=[],folds=[],train_size=0,n_original=0,n_early=0,n_unmarked=0,n_negative=0,n_days=0,error=f'{type(e).__name__}: {e}')
                    r['cached']=False;r['elapsed']=round(time.perf_counter()-st,3)
                r=dict(r,id=ident,gen=gen,slot=slot,gene=gene)
                _append_jsonl(journal,r)
            if not r.get('cached') and not r.get('error'):cache[r['id']]=r
            for pool,field in [(seen_original,'pos'),(seen_early,'early'),(seen_unmarked,'unmarked')]:pool.update(decode_ids(gene[field]).tolist())
            if r['id'] not in unique_fingerprints:inclusions[decode_ids(gene['pos'])]+=1
            unique_fingerprints.add(r['id']);valid_count+=not r.get('error');trained_count+=not r.get('cached') and not r.get('error');error_count+=bool(r.get('error'));ops[gene['operation']]+=1
            records.append(r)
            if slot%max(1,report_every)==0 or slot==population:
                print(f'{ctx["tf"]}m {ctx["side"]} gen {gen}/{generations} | variant {slot}/{population} | score {r["score"]:.3f} | group {r["train_size"]} | {r["gene"]["operation"]}',flush=True)
        valid=sorted((r for r in records if not r.get('error')),key=lambda x:x['score'],reverse=True)
        if not valid:raise RuntimeError('All candidates invalid')
        best=valid[0] if best is None or valid[0]['score']>best['score'] else best
        genrec=dict(gen=gen,best=valid[0]['score'],mean=round(float(np.mean([r['score'] for r in valid])),5),worst=valid[-1]['score'],alltime=best['score'],best_size=valid[0]['train_size'],best_id=valid[0]['id'],best_operation=valid[0]['gene']['operation'],unique=len(set(r['id'] for r in records)),valid=len(valid),tested=gen*population,
            original_coverage=len(seen_original),early_coverage=len(seen_early),unmarked_coverage=len(seen_unmarked),original_total=len(ctx['pospool']),unmarked_total=len(ctx['negativepool']))
        generation_history.append(genrec)
        # Save after every generation; final synthesis can be regenerated on resume.
        (out/'GENERATIONS.json').write_text(json.dumps(generation_history,ensure_ascii=False,indent=2),encoding='utf8')
        print(f'GEN {gen}: best {genrec["best"]:.3f} | unique {len(unique_fingerprints)} | seen labeled {len(seen_original)}/{len(ctx["pospool"])} | new {len(seen_unmarked)}',flush=True)
        if gen<generations:pop=children(valid,population,ctx['frame'],ctx['side'],ctx['tf'],gen)
    # Only frozen champion is evaluated on held-out CHECK.
    def check_gene(g,seed=31,shuffle=False,with_signals=False):
        p=decode_ids(g['pos']);e=decode_ids(g['early']);u=decode_ids(g['unmarked']);chosen=np.r_[p,e,u]
        negpool=np.setdiff1d(ctx['negativepool'],chosen,assume_unique=False)
        neg=np.random.default_rng(500+ctx['tf']).choice(negpool,size=min(len(negpool),2*len(chosen)),replace=False)
        # fixed model and training budget, no model selection on CHECK
        pred,_=train_candidate(ctx['X'],ctx['y'],g,chosen,neg,ctx['check'],epochs,device,None,seed=seed,shuffle_training_labels=shuffle)
        stat=metric(ctx['y'][ctx['check']],pred)
        if not with_signals:return stat
        k=stat['top_total'];chosen_top=np.argsort(-pred,kind='stable')[:k];res=[]
        for i in chosen_top:
            idx=int(ctx['check'][i]);r=ctx['frame'].iloc[idx]
            res.append(dict(row_id=idx,day=str(r.day),dt=str(r['dt']),price=float(r.close),confidence=float(pred[i]),correct=int(ctx['y'][idx])))
        return stat,res
    winner_check,check_signals=check_gene(best['gene'],with_signals=True)
    base=initial(1,ctx['frame'],ctx['side'],ctx['tf'])[0]
    full_check=check_gene(base)
    shuffle_check=check_gene(best['gene'],shuffle=True)
    check_repeat=[check_gene(best['gene'],seed=x) for x in [17,73]]
    all_repeat=[check_gene(base,seed=x) for x in [17,73]]
    randoms=[]
    for r in range(3):
        p=np.random.default_rng(73+r).choice(ctx['pospool'],size=min(len(ctx['pospool']),best['train_size']),replace=False)
        gg=copy.deepcopy(base);gg.update(pos=encode_ids(p),early=encode_ids([]),unmarked=encode_ids([]))
        randoms.append(check_gene(gg))
    winner=copy.deepcopy(best)
    # Provide human-readable real points, not just compressed member IDs.
    winner['samples']=[{'row_id':int(idx),'day':str(ctx['frame'].day.iloc[idx]),'dt':str(ctx['frame'].dt.iloc[idx]),'price':float(ctx['frame'].close.iloc[idx]),'source':label} for code,label in [('pos','old'),('early','early'),('unmarked','new')] for idx in decode_ids(winner['gene'][code])]
    pos_frequency=inclusions[ctx['pospool']]
    freq_hist={'never':int((pos_frequency==0).sum()),'rare_1_25pct':int(((pos_frequency>0)&(pos_frequency<=len(unique_fingerprints)*.25)).sum()),'some_25_75pct':int(((pos_frequency>len(unique_fingerprints)*.25)&(pos_frequency<len(unique_fingerprints)*.75)).sum()),'frequent_75_100pct':int((pos_frequency>=len(unique_fingerprints)*.75).sum())}
    summary=dict(timeframe=ctx['tf'],direction=ctx['side'],device=device,generations=generations,population=population,
        total_planned=generations*population,unique_tested=len(unique_fingerprints),actual_retrainings=trained_count,cached_evaluations=generations*population-trained_count-error_count,invalid_candidates=error_count,operations=dict(ops),training_epochs=epochs,
        original_labeled_total=len(ctx['pospool']),original_labeled_visited=len(seen_original),original_coverage_percent=round(100*len(seen_original)/max(1,len(ctx['pospool'])),2),
        unmarked_total=len(ctx['negativepool']),unmarked_tried=len(seen_unmarked),early_tried=len(seen_early),inclusion_histogram=freq_hist,avg_inclusion_rate=round(float(pos_frequency.mean()/max(1,len(unique_fingerprints)))*100,2),
        winner=winner,check_signals=check_signals,check=winner_check,all_check=full_check,random_check=randoms,shuffled_labels_check=shuffle_check,selected_repeat_seeds=check_repeat,all_repeat_seeds=all_repeat,generations_history=generation_history,elapsed_seconds=round(time.perf_counter()-start,2),
        note='Selection objective: recognition of held-out annotated price movements. No trading returns.')
    (out/'RESULT.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    # Human-readable exports. Full bit-encoded chromosomes stay in CANDIDATES.jsonl.
    with (out/'CANDIDATES_TABLE.csv').open('w',newline='',encoding='utf-8-sig') as f:
        cols=['gen','slot','id','parent','change','score','group_size','original','early','new','training_days','best_epoch','overfit_drop','cached','error']
        writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader()
        for r in _read_jsonl(journal):
            gene=r.get('gene',{})
            writer.writerow(dict(gen=r.get('gen'),slot=r.get('slot'),id=r.get('id'),parent=gene.get('parent'),change=gene.get('operation'),score=r.get('score'),group_size=r.get('train_size'),original=r.get('n_original'),early=r.get('n_early'),new=r.get('n_unmarked'),training_days=r.get('n_days'),best_epoch=r.get('best_ap_epoch'),overfit_drop=r.get('overfit_ap_drop'),cached=r.get('cached'),error=r.get('error')))
    with (out/'WINNER_SAMPLES.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['row_id','day','dt','price','source']);writer.writeheader();writer.writerows(winner['samples'])
    with (out/'LABEL_COVERAGE.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f);writer.writerow(['row_id','day','date_time','times_used_in_distinct_genomes'])
        for idx in ctx['pospool']:
            row=ctx['frame'].iloc[int(idx)];writer.writerow([int(idx),row.day,str(row['dt']),int(inclusions[idx])])
    return summary

def run(prepared,results,tfs=TIMEFRAMES,generations=50,population=36,epochs=24,device='auto'):
    import torch
    actual='cuda' if device in ('auto','cuda') and torch.cuda.is_available() else 'cpu'
    if device=='cuda' and actual!='cuda':raise RuntimeError('CUDA requested but unavailable')
    results=Path(results);results.mkdir(exist_ok=True,parents=True)
    print('NEXUS V12 dataset selection, device:',actual,flush=True)
    summaries=[]
    for tf in tfs:
        frame=load_or_prepare('',prepared,tf)
        X=np.nan_to_num(frame[FEATURES].to_numpy(np.float32),nan=0,posinf=0,neginf=0)
        for side in ['long','short']:
            ctx=create_context(frame,X,side,tf)
            s=run_one(ctx,results/f'{tf}m_{side}',generations,population,epochs,actual)
            summaries.append({k:s[k] for k in ['timeframe','direction','total_planned','unique_tested','original_coverage_percent','unmarked_tried','winner','check','all_check'] if k!='winner'}|{'selected_size':s['winner']['train_size'],'winner_score':s['winner']['score']})
        (results/'SUMMARY.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding='utf8')
    return summaries
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--prepared',default='prepared');a.add_argument('--results',default='results');a.add_argument('--tf',type=int,nargs='*',default=list(TIMEFRAMES));a.add_argument('--generations',type=int,default=50);a.add_argument('--population',type=int,default=36);a.add_argument('--epochs',type=int,default=24);a.add_argument('--device',choices=['auto','cuda','cpu'],default='auto')
    q=a.parse_args();run(q.prepared,q.results,q.tf,q.generations,q.population,q.epochs,q.device)
