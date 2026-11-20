"""Create a repeatable synthetic seven-day dataset for an independent checkout."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent


def main():
    root = HERE/'data/demo'
    path = HERE/'local-config.json'
    settings = {'quoteRoot':str(root/'stream=book_ticker'),'tradeRoot':str(root/'stream=trades'),
                'labelHtml':str(root/'labels/review.html')}
    if path.exists() and json.loads(path.read_text(encoding='utf-8-sig')) != settings:
        raise ValueError('local-config.json selects another dataset. Preserve it before selecting demo data.')
    root.mkdir(parents=True,exist_ok=True)
    (root/'DEMO.json').write_text(json.dumps({'synthetic':True,'seed':42})+'\n',encoding='utf-8')
    start = datetime(2026,6,14,tzinfo=timezone.utc)
    for i in range(7):
        day = start+timedelta(days=i)
        base = int(day.timestamp()*1000)
        dt = np.r_[np.arange(0,86_400_000,1000,dtype=np.int64),86_399_500,86_399_900]
        mid = 70 + .8*np.sin(dt/200_000+i) + .3*np.sin(dt/31_000) + .1*np.sin(dt/7100)
        for stream,table in (
            ('book_ticker',pa.table({'recv_ts_ms':base+dt,'best_bid':mid-.005,'best_ask':mid+.005,
                                    'bid_qty':np.full(len(dt),100.),'ask_qty':np.full(len(dt),100.)})),
            ('trades',pa.table({'recv_ts_ms':base+dt,'trade_time_ms':base+dt-20,
                               'exchange_ts_ms':base+dt-10,'symbol':['SOLUSDT']*len(dt),
                               'price':mid,'quantity':2+np.sin(dt/5000)**2,'trade_type':np.ones(len(dt),np.int64)})),
        ):
            folder = root/f'stream={stream}'/'symbol=SOLUSDT'/f'date={day:%Y-%m-%d}'
            folder.mkdir(parents=True,exist_ok=True)
            pq.write_table(table,folder/f'{stream}_SOLUSDT_{day:%Y-%m-%d}.parquet')
        print(f'{day:%Y-%m-%d} synthetic quotes and trades ready',flush=True)
    subprocess.run([sys.executable,'build.py','--root',str(root/'stream=book_ticker'),
                    '--output',str(root/'labels')],cwd=HERE,check=True)
    path.write_text(json.dumps(settings,indent=2)+'\n',encoding='utf-8')
    print('Synthetic data selected in local-config.json')


if __name__=='__main__':
    main()
