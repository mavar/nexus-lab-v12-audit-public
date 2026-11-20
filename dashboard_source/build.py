"""Build an offline dashboard from local SOLUSDT parquet, or a synthetic demo."""
import argparse
import base64
from datetime import date, timedelta, datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

DAY = 86_400_000


def source_quotes(path, start):
    import pyarrow.parquet as pq

    table = pq.ParquetFile(path).read(columns=['recv_ts_ms', 'best_bid', 'best_ask', 'bid_qty', 'ask_qty'])
    t, bid, ask, bq, aq = (table[i].to_numpy() for i in range(5))
    assert np.isfinite(t).all()
    order = np.argsort(t, kind='stable')
    order = order[np.r_[np.diff(t[order]) > 0, True]]
    valid = np.isfinite(bid) & np.isfinite(ask) & np.isfinite(bq) & np.isfinite(aq) & (bid > 0) & (bid <= ask) & (bq > 0) & (aq > 0)
    # Do not drop a bad quote and bridge through it as if the stream were continuous.
    if not valid[order].all():
        raise ValueError(f'invalid best-price rows in {path.name}')
    return t[order] - start, bid[order], ask[order], {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'rows_before_dedup': len(t)}


def pack_day(day, t, bid, ask, meta):
    assert len(t) >= 2 and t[0] >= 0 and t[-1] < DAY and np.all(np.diff(t) > 0)
    d = np.diff(t); gaps = np.flatnonzero(d > 2000)
    mark = np.r_[True, (np.diff(bid) != 0) | (np.diff(ask) != 0) | (d > 2000)] | np.r_[d > 2000, True]
    raw = np.asarray(np.diff(t, prepend=0), '<u4').tobytes() + np.asarray(bid[mark], '<f8').tobytes() + np.asarray(ask[mark], '<f8').tobytes() + np.asarray(t[mark], '<u4').tobytes()
    gap_list = [[int(t[i]), int(t[i+1])] for i in gaps]
    if t[0] > 2000:
        gap_list.insert(0, [0, int(t[0])])
    if DAY - t[-1] > 2000:
        gap_list.append([int(t[-1]), DAY])
    # The week overview uses minute endpoints and preserves each actual gap's edges.
    sample = np.searchsorted(t, np.arange(0, DAY, 60000), side='right') - 1
    take = np.unique(np.r_[sample[sample >= 0], gaps, gaps+1, 0, len(t)-1]).astype(int)
    return dict(date=day.isoformat(), n=len(t), changes=int(mark.sum()), packed=base64.b64encode(gzip.compress(raw, mtime=0)).decode('ascii'), gaps=gap_list,
                overview=np.column_stack([t[take], bid[take], ask[take]]).tolist(), source=meta)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, help='directory of book_ticker stream, with symbol=…/date=…/…parquet')
    p.add_argument('--pair', default='SOLUSDT'); p.add_argument('--start', type=date.fromisoformat, default=date(2026, 6, 14))
    p.add_argument('--output', type=Path, required=True); p.add_argument('--demo', action='store_true'); a = p.parse_args()
    if not a.root and not a.demo:
        p.error('pass --root or --demo')
    days = []
    for i in range(7):
        day = a.start + timedelta(days=i)
        if a.demo:
            t = np.arange(60_000, 3_600_100, 100)
            bid = np.round(100 + np.sin(t / 145000 + i) + .35 * np.sin(t / 38000), 3); ask = bid + .01
            data = (t, bid, ask, {'synthetic': True})
        else:
            files = list((a.root / f'symbol={a.pair}' / f'date={day}').glob('*.parquet'))
            if len(files) != 1:
                raise ValueError(f'{a.pair} {day}: expected one quote file, found {len(files)}')
            data = source_quotes(files[0], int(datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).timestamp()*1000))
        days.append(pack_day(day, *data)); print(day, days[-1]['n'], 'quotes;', len(days[-1]['gaps']), 'gaps', flush=True)
    here = Path(__file__).resolve().parent
    sources = {n: (here/n).read_text(encoding='utf-8') for n in ['engine.js', 'charts.js', 'app.js', 'lab.js', 'index.html']}
    synthetic = a.demo or bool(a.root and (a.root.parent/'DEMO.json').is_file())
    assets = json.dumps(dict(pair='DEMO (синтетика)' if synthetic else a.pair, days=days), ensure_ascii=False, separators=(',', ':'))
    page = sources['index.html'].replace('/* DATA */', assets).replace('/* ENGINE FOR WORKER */', json.dumps(sources['engine.js'])).replace('/* ENGINE */', sources['engine.js']).replace('/* CHARTS */', sources['charts.js']).replace('/* APP */', sources['app.js']).replace('/* LAB */', sources['lab.js'])
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output/'review.html').write_text(page, encoding='utf-8')
    (a.output/'OPEN_REVIEW.bat').write_text('@echo off\nstart "" "%~dp0review.html"\n', encoding='ascii')
    manifest = {'pair': a.pair, 'week_utc': [str(a.start), str(a.start+timedelta(days=6))], 'days': [{k: d[k] for k in ['date','n','gaps','source']} for d in days], 'code_sha256': {n:hashlib.sha256(s.encode()).hexdigest() for n,s in sources.items()}, 'no_overnight': True}
    (a.output/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
