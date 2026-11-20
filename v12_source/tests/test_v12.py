# -*- coding: utf-8 -*-
"""Regression tests for chromosome diversity, data boundaries, restart and visual evidence."""
import json
from pathlib import Path
import numpy as np
import pytest
from research.prepare_finam import FEATURES,load_or_prepare
from research.evolve_datasets import (encode_ids,decode_ids,initial,children,create_context,
    eval_gene,_append_jsonl,_read_jsonl,metric,stamp)
from research.dashboard_v12 import build

ROOT=Path(__file__).resolve().parents[1]
def frame(tf=30):
    if not (ROOT/'prepared'/f'SBRF_{tf}m_research.csv.gz').exists():
        pytest.skip(f'Данные {tf} минут ещё не скопированы в prepared/')
    return load_or_prepare('',ROOT/'prepared',tf)

def test_encoding_exact():
    a=np.array([50,3,3,1,900,12]);assert decode_ids(encode_ids(a)).tolist()==[1,3,12,50,900]

def test_population_starts_with_entire_labeled_universe():
    d=frame();gen=initial(6,d,'long',30)
    y=d.long_label.to_numpy();p=np.where((d.split=='train')&(y==1))[0]
    assert set(decode_ids(gen[0]['pos']))==set(p)
    assert len({stamp(g) for g in gen})>=5

def test_children_inherit_and_diversify():
    d=frame(15);original=initial(10,d,'long',15)
    parents=[{'gene':g,'score':5-i} for i,g in enumerate(original)]
    kids=children(parents,36,d,'long',15,1)
    assert len(kids)==36
    assert len({stamp(g) for g in kids})>=15
    assert {'swap','grow','shrink','new_unknown'}.intersection({k['operation'] for k in kids})
    tr=np.where(d.split=='train')[0]
    for gene in kids:
        chosen=np.r_[decode_ids(gene['pos']),decode_ids(gene['early']),decode_ids(gene['unmarked'])]
        assert np.isin(chosen,tr).all()
        assert len(chosen)==len(np.unique(chosen))

def test_training_logs_both_errors_and_curve():
    d=frame(30);X=np.nan_to_num(d[FEATURES].to_numpy(np.float32))
    ctx=create_context(d,X,'short',30)
    gene=initial(1,d,'short',30)[0]
    res=eval_gene(gene,ctx,3,'cpu')
    assert res['curve'][-1]['epoch']==3
    assert all(c['train_loss']>=0 and c['select_loss']>=0 for c in res['curve'])
    assert sum([res['n_original'],res['n_early'],res['n_unmarked']])==res['train_size']

def test_torn_final_line_recovered(tmp_path):
    p=tmp_path/'CANDIDATES.jsonl';_append_jsonl(p,{'gen':1,'slot':1})
    with p.open('ab') as f:f.write(b'{"gen":2,"slot":')
    data=_read_jsonl(p)
    assert data==[{'gen':1,'slot':1}]
    assert 'slot' in (tmp_path/'RECOVERED_INCOMPLETE_LINE.bin').read_text()
    _append_jsonl(p,{'gen':2,'slot':1})
    assert len(_read_jsonl(p))==2

def test_no_select_or_check_members():
    d=frame(5)
    for side in ['long','short']:
        for gene in initial(8,d,side,5):
            chosen=np.r_[decode_ids(gene['pos']),decode_ids(gene['early']),decode_ids(gene['unmarked'])]
            assert (d.split.iloc[chosen]=='train').all()

def test_metric_baseline_for_uninformative_prediction():
    y=np.r_[np.zeros(100),np.ones(25)].astype('int8');p=np.ones(len(y))*.25
    assert metric(y,p)['lift']==pytest.approx(1.0,abs=.0001)

def test_dashboard_has_real_price_and_default_chosen_training_day(tmp_path):
    old=ROOT/'results'/'SMOKE'
    if not old.exists():pytest.skip('End-to-end smoke has not been run')
    p=build(ROOT/'prepared',old,tmp_path/'viz.html')
    raw=p.read_text(encoding='utf8')
    assert '<script id="data" type="application/json">' in raw
    assert 'Где учили нейросеть' in raw
    assert 'G03' in raw
    import re
    d=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',raw,re.S).group(1))
    obj=d['experiments']['30_short'];sel=obj['winner']['samples'];bys={}
    for row in sel:bys[row['day']]=bys.get(row['day'],0)+1
    day=max(bys,key=bys.get)
    ids={p[0] for p in d['plots']['30'][day]['points']}
    assert bys[day]>0 and any(p['row_id'] in ids for p in sel if p['day']==day)

def test_resume_halfway_without_rewriting_earlier_candidates(tmp_path):
    import shutil
    from research.evolve_datasets import run_one
    src=ROOT/'results'/'SMOKE'/'30m_short'
    if not (src/'RESULT.json').exists():pytest.skip('Run --smoke first')
    dest=tmp_path/'30m_short'
    dest.mkdir()
    shutil.copy2(src/'SETTINGS.json',dest/'SETTINGS.json')
    original=(src/'CANDIDATES.jsonl').read_text(encoding='utf8').splitlines()
    assert len(original)==8
    (dest/'CANDIDATES.jsonl').write_text('\n'.join(original[:5])+'\n',encoding='utf8')
    d=frame(30);X=np.nan_to_num(d[FEATURES].to_numpy(np.float32))
    result=run_one(create_context(d,X,'short',30),dest,2,4,3,'cpu',report_every=9)
    assert len((dest/'CANDIDATES.jsonl').read_text(encoding='utf8').splitlines())==8
    assert (dest/'CANDIDATES.jsonl').read_text(encoding='utf8').splitlines()[:5]==original[:5]
    assert result['winner']['id']==json.loads((src/'RESULT.json').read_text())['winner']['id']
