"""Apply exactly one frozen model to the reserved week. This program never tunes."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import joblib
import sklearn

from lab_api import HERE, ROOT, LearnInput, load_rules
from learn_jobs import HOLDOUT, entry_sides, evaluate, fee_for, sha256, validation_day
from learn_volume import trade_path


def hashed(path):return sha256(path.read_bytes()).hexdigest()


def check(a):
    start=datetime.fromisoformat(HOLDOUT['start']); end=datetime.fromisoformat(HOLDOUT['endExclusive'])
    if datetime.now(timezone.utc)<end:raise ValueError('Контрольная неделя ещё не закончилась.')
    if a.output.exists():raise ValueError('Контроль уже записан по указанному пути.')
    frozen=json.loads((a.frozen/'manifest.json').read_text(encoding='utf-8'))
    audit=json.loads(a.verified_capture.read_text(encoding='utf-8'))
    if frozen['holdout']!=HOLDOUT or datetime.fromisoformat(frozen['recordedUtc'])>=start:
        raise ValueError('Параметры должны быть зафиксированы до начала будущей недели.')
    if audit.get('purpose')!='holdout_metadata_only' or audit.get('prior_outcome_access') is not False or audit.get('frozen_id')!=frozen['id']:
        raise ValueError('Нужен отдельный паспорт качества этой недели и предварительно выбранного прогона.')
    if sklearn.__version__!=frozen['sklearn'] or load_rules()['_hash']!=frozen['rulesHash'] or any(hashed(HERE/n)!=h for n,h in frozen['codeSha256'].items()):
        raise ValueError('Код, правила или версия модели отличаются от замороженных.')
    cfg=LearnInput.model_validate(frozen['parameters'])
    dates=[start.date()+timedelta(days=i) for i in range(7)]
    for d in dates:
        files=list((ROOT/'symbol=SOLUSDT'/f'date={d}').glob('*.parquet'))
        if len(files)!=1 or hashed(files[0])!=audit.get('quoteSha256',{}).get(str(d)):
            raise ValueError(f'Нет проверенного файла котировок за {d}.')
        if cfg.volumeSeconds and hashed(trade_path(d))!=audit.get('tradeSha256',{}).get(str(d)):
            raise ValueError(f'Нет проверенного файла сделок за {d}.')
    model_file=a.frozen/'model.joblib'
    if hashed(model_file)!=frozen['modelSha256']:raise ValueError('Модель отличается от замороженной.')
    # Load only the local artifact produced by the freeze action, never a downloaded model.
    model=joblib.load(model_file)
    models=model if isinstance(model,dict) else {1:model}
    expected={'long':{1},'short':{-1},'both':{1,-1}}[cfg.direction]
    if models.keys()!=expected:raise ValueError('Набор сохранённых моделей не соответствует направлению.')
    days=[validation_day(day,cfg.volumeSeconds,cfg.extraSlipPct) for day in dates]
    signals=[entry_sides({side:m.predict_proba(day[3])[:,1] for side,m in models.items()},
                         cfg.confidencePct/100) for day in days]
    result=evaluate(cfg,days,signals,fee_for(cfg),render=True)
    with a.output.open('x',encoding='utf-8') as f:f.write(result.model_dump_json(indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--frozen',type=Path,required=True);p.add_argument('--verified-capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    check(p.parse_args())
