"""Report the local dashboard build, dependencies and seven June source files."""
import importlib.util
import json
import platform
from datetime import date, timedelta
from pathlib import Path

from dashboard_config import HERE, config, data_mode, load_rules, path_setting


def main():
    quotes = path_setting('NEXUS_QUOTE_ROOT','quoteRoot',r'G:\mexc_base\exchange=MEXC\stream=book_ticker')
    trades = path_setting('NEXUS_TRADE_ROOT','tradeRoot',r'G:\mexc_base\exchange=MEXC\stream=trades')
    labels = path_setting('NEXUS_LABEL_HTML','labelHtml',str(HERE/'dist/review.html'))
    counts = []
    for i in range(7):
        day = date(2026,6,14)+timedelta(days=i)
        counts.append({'date':str(day), 'quoteFiles':len(list((quotes/'symbol=SOLUSDT'/f'date={day}').glob('*.parquet'))),
                       'tradeFiles':len(list((trades/'symbol=SOLUSDT'/f'date={day}').glob('*.parquet')))})
    rules = load_rules()
    report = {'python':platform.python_version(),'project':str(HERE),'dataMode':data_mode(quotes),
              'dependencies':{name:importlib.util.find_spec(name) is not None for name in
                              ('numpy','pyarrow','fastapi','uvicorn','numba','sklearn')},
              'pageBuilt':(HERE/'web/out/index.html').is_file(),'labelPageAvailable':labels.is_file(),
              'quoteRoot':str(quotes),'tradeRoot':str(trades),'labelHtml':str(labels),
              'rulesHash':rules['_hash'],'sourceFileCounts':counts}
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
