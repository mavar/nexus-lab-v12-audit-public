# -*- coding: utf-8 -*-
"""Self-contained offline NEXUS V12 dashboard built from recorded candidates and actual OHLCV."""
from pathlib import Path
import json,html
import numpy as np
from .prepare_finam import load_or_prepare

def build(prepared,results,out):
    prepared=Path(prepared);results=Path(results);out=Path(out)
    D={'experiments':{},'plots':{},'timeframes':[]}
    for path in sorted(results.glob('*m_*/RESULT.json')):
        s=json.loads(path.read_text(encoding='utf8'))
        # A compact learning curve of the best chromosome in EVERY generation.
        winners={}
        journal=path.parent/'CANDIDATES.jsonl'
        if journal.exists():
            for ln in journal.read_text(encoding='utf8').splitlines():
                try:r=json.loads(ln)
                except json.JSONDecodeError:break
                gen=int(r['gen'])
                if (not r.get('error')) and (gen not in winners or float(r['score'])>float(winners[gen]['score'])):
                    winners[gen]={'gen':gen,'id':r['id'],'score':r['score'],'curve':r.get('curve',[]),'operation':r.get('gene',{}).get('operation'),'size':r.get('train_size')}
        s['per_gen_best']=[winners[k] for k in sorted(winners)]
        key=f"{s['timeframe']}_{s['direction']}";D['experiments'][key]=s
        tf=s['timeframe']
        if tf not in D['timeframes']:D['timeframes'].append(tf)
    if not D['experiments']:raise ValueError('No completed run results to display yet')
    for tf in D['timeframes']:
        d=load_or_prepare('',prepared,tf)
        groups={}
        for day,z in d.groupby('day'):
            groups[day]={'split':str(z.split.iloc[0]),'points':[[int(i),str(dt),float(p),int(a),int(b)] for i,dt,p,a,b in zip(z.index,z.dt,z.close,z.long_label,z.short_label)]}
        D['plots'][str(tf)]=groups
    jsdata=json.dumps(D,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    # Script JSON cannot contain a closing script tag. Escaping above is deliberate.
    template=Path(__file__).with_name('dashboard_v12_template.html').read_text(encoding='utf8')
    doc=template.replace('/*__PLOTLY__*/',Path(__file__).with_name('plotly.min.js').read_text(encoding='utf8')).replace('/*__DATA__*/',jsdata)
    out.parent.mkdir(exist_ok=True,parents=True);out.write_text(doc,encoding='utf8')
    return out
