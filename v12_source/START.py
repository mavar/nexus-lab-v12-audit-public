# -*- coding: utf-8 -*-
"""One entry point for NEXUS V12 research; resume same saved run automatically."""
from __future__ import annotations
import argparse,os,sys,subprocess,json,traceback,zipfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def maybe_switch_to_cuda_python(disabled):
    if disabled or os.name!='nt' or '--inner' in sys.argv:return
    local=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData'/'Local')))/'NEXUS_Runtime'/'cuda126_py312'/'Scripts'/'python.exe'
    if local.exists() and str(local).casefold()!=str(Path(sys.executable)).casefold():
        chk=subprocess.run([str(local),'-c','import torch,numpy,pandas,sklearn; assert torch.cuda.is_available()'],capture_output=True,text=True,timeout=45)
        if chk.returncode==0:
            print('Найдено проверенное окружение GTX 1070. Продолжаю в нём.',flush=True)
            sys.stdout.flush();sys.stderr.flush()
            raise SystemExit(subprocess.call([str(local),str(Path(__file__).resolve()),'--inner']+sys.argv[1:]))

def package_report(results,successful):
    archive=ROOT/'NEXUS_V12_REPORT.zip';temp=ROOT/'NEXUS_V12_REPORT.tmp.zip'
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=7,allowZip64=True) as z:
        for p in results.rglob('*'):
            if not p.is_file():continue
            rel=p.relative_to(results)
            # The complete genome file remains available locally, but is large.
            if p.name=='CANDIDATES.jsonl':
                compact=[]
                for line in p.read_text(encoding='utf8').splitlines():
                    try:
                        d=json.loads(line)
                        compact.append({k:d.get(k) for k in ['gen','slot','id','score','error','cached','elapsed','train_size','n_original','n_early','n_unmarked','n_days','best_ap_epoch','overfit_ap_drop','curve','folds']}
                          | {'parent':d.get('gene',{}).get('parent'),'operation':d.get('gene',{}).get('operation')})
                    except json.JSONDecodeError:break
                z.writestr(str(rel.with_name('CANDIDATES_COMPACT.json')),json.dumps(compact,ensure_ascii=False,separators=(',',':')))
            elif p.suffix not in ['.bin']:
                z.write(p,str(rel))
        p=ROOT/'МИКРОКОНСТИТУЦИЯ_NEXUS_LAB.md'
        if p.exists():z.write(p,p.name)
        z.writestr('REPORT_STATUS.txt','SUCCESS' if successful else 'PARTIAL or ERROR. Re-run START.py with the same options to resume.')
    os.replace(temp,archive)
    return archive

class Tee:
    def __init__(self,*destinations):self.destinations=destinations
    def write(self,s):
        for out in self.destinations:out.write(s);out.flush()
    def flush(self):
        for out in self.destinations:out.flush()

def main():
    ap=argparse.ArgumentParser(description='NEXUS: evolutionary selection of best teaching examples.')
    ap.add_argument('--inner',action='store_true',help=argparse.SUPPRESS)
    ap.add_argument('--smoke',action='store_true',help='Short technical check: 30m, 2 generations, 4 candidates, 3 epochs')
    ap.add_argument('--cpu',action='store_true',help='Force CPU')
    ap.add_argument('--tf',type=int,nargs='*',choices=[1,5,10,15,30],default=None,help='Choose timeframes, default all')
    ap.add_argument('--generations',type=int,default=50)
    ap.add_argument('--population',type=int,default=36)
    ap.add_argument('--epochs',type=int,default=24)
    args=ap.parse_args()
    if not (ROOT/'МИКРОКОНСТИТУЦИЯ_NEXUS_LAB.md').exists():raise RuntimeError('Missing NEXUS constitution')
    maybe_switch_to_cuda_python(args.cpu)
    tfs=args.tf or ([30] if args.smoke else [1,5,10,15,30]);generations=2 if args.smoke else args.generations;population=4 if args.smoke else args.population;epochs=3 if args.smoke else args.epochs
    if generations<1 or population<3 or epochs<1:raise ValueError('Too small parameter')
    needed=[tf for tf in tfs if not (ROOT/'prepared'/f'SBRF_{tf}m_research.csv.gz').exists()]
    if needed:raise FileNotFoundError(f'Нет подготовленных файлов {needed}. Распакуй архивы данных A и B в папку проекта, чтобы файлы лежали в prepared/.')
    import torch
    gpu=torch.cuda.is_available()
    print('CUDA:',gpu,'GPU:',torch.cuda.get_device_name(0) if gpu else 'нет',flush=True)
    print('План:',len(tfs),'таймфреймов, 2 направления,',generations,'поколений x',population,'вариантов,',epochs,'проходов обучения',flush=True)
    if 'Yandex' in str(ROOT) or 'Яндекс' in str(ROOT):print('Совет: для долгой записи лучше использовать локальную несинхронизируемую папку.',flush=True)
    results=ROOT/'results'/('SMOKE' if args.smoke else 'FULL');results.mkdir(exist_ok=True,parents=True)
    log=results/'RUN_LOG.txt'
    success=False;oldstdout=sys.stdout;oldstderr=sys.stderr
    with open(log,'a',encoding='utf8',buffering=1) as fd:
        sys.stdout=Tee(oldstdout,fd);sys.stderr=Tee(oldstderr,fd)
        try:
            from research.evolve_datasets import run
            from research.dashboard_v12 import build
            print('\nЗапуск',time.strftime('%Y-%m-%d %H:%M:%S'),flush=True)
            run(ROOT/'prepared',results,tfs,generations,population,epochs,'cpu' if args.cpu else 'auto')
            f=build(ROOT/'prepared',results,ROOT/'NEXUS_DASHBOARD.html')
            print('Просмотрщик:',f,flush=True)
            (results/'RUN_STATUS.txt').write_text('SUCCESS\n',encoding='utf8')
            success=True
        except BaseException:
            err=traceback.format_exc();print(err,flush=True)
            (results/'RUN_STATUS.txt').write_text('ERROR\n'+err,encoding='utf8')
        finally:
            try:
                print('Архив отчёта:',package_report(results,success),flush=True)
            except Exception as e:print('Не удалось собрать отчёт:',repr(e),flush=True)
            sys.stdout=oldstdout;sys.stderr=oldstderr
    if not success:raise SystemExit(1)
if __name__=='__main__':main()
