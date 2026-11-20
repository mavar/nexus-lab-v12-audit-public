import sys,os,json,time,tempfile,shutil,hashlib
from pathlib import Path
import numpy as np
BASE=Path(__file__).resolve().parent.parent;ROOT=BASE/"v12_source";OUT=BASE/"local_checks";OUT.mkdir(exist_ok=True);sys.path.insert(0,str(ROOT))
import research.evolve_datasets as e
from research.prepare_finam import FEATURES,load_or_prepare
work=Path(tempfile.mkdtemp(prefix="nexus_cache_proof_"));calls=[];original=e.train_candidate

def spy(*args,**kw):
 st=time.perf_counter();pred,curve=original(*args,**kw)
 calls.append({"train_positive":len(args[3]),"train_negative":len(args[4]),"prediction_rows":len(args[5]),"X_sha256":hashlib.sha256(args[0].tobytes()).hexdigest(),"pred_sha256":hashlib.sha256(pred.tobytes()).hexdigest(),"seconds":time.perf_counter()-st})
 return pred,curve

def ctx(change=None):
 d=load_or_prepare("",ROOT/"prepared",30);X=d[FEATURES].to_numpy(np.float32)
 if change=="feature":X[:,0]=np.random.default_rng(1980).normal(0,10,len(d));d[FEATURES[0]]=X[:,0]
 if change=="close":d.loc[0,"close"]+=1
 if change=="split":d.loc[d.split=="train","split"]="check"
 return e.create_context(d,X,"long",30)

def execute(label,c,out):
 calls.clear();st=time.perf_counter()
 try:
  result=e.run_one(c,out,2,4,3,"cpu",report_every=999)
  entry={"returned":True,"winner_id":result["winner"]["id"],"winner_score":result["winner"]["score"],"check_ap":result["check"]["ap"],"train_calls":list(calls)}
 except Exception as ex:entry={"returned":False,"error":type(ex).__name__+": "+str(ex),"train_calls":list(calls)}
 entry["wall_seconds"]=time.perf_counter()-st;entry["training_call_count"]=len(calls)
 R[label]=entry;print(label,json.dumps({k:v for k,v in entry.items() if k!="train_calls"}),flush=True)
 (OUT/"cache_definitive.json").write_text(json.dumps(R,ensure_ascii=False,indent=2),encoding="utf8")
R={"workdir":str(work),"method":"Spy records real train_candidate invocations and calls original implementation; no mocked model scores."}
e.train_candidate=spy
try:
 execute("original_fresh_run",ctx(),work/"original")
 execute("unchanged_completed_restart",ctx(),work/"original")
 execute("changed_feature_completed_restart",ctx("feature"),work/"original")
 execute("changed_feature_fresh_directory",ctx("feature"),work/"fresh_changed")
 partial=work/"replay_without_RESULT";partial.mkdir()
 for name in ["SETTINGS.json","CANDIDATES.jsonl"]:shutil.copy2(work/"original"/name,partial/name)
 execute("changed_feature_replay_saved_candidates",ctx("feature"),partial)
 execute("changed_split_completed_restart",ctx("split"),work/"original")
 execute("changed_close_completed_restart",ctx("close"),work/"original")
 # One positive: explicit boundary failure instead of a learned classifier.
 tiny=ctx();tiny["frame"]["long_label"]=0;tiny["frame"].loc[0,"long_label"]=1
 cx=e.create_context(tiny["frame"],tiny["X"],"long",30)
 try:e.eval_gene(e.initial(1,cx["frame"],"long",30)[0],cx,1,"cpu");R["single_positive"]="accepted"
 except Exception as ex:R["single_positive"]=str(ex)
 # Fixed date in score prevents evaluating otherwise valid June data.
 c=ctx();pred=np.linspace(0,1,len(c["select"]));normal=e.score_candidate(c["frame"],c["y"],c["select"],pred,100,12,[])
 shifted=c["frame"].copy();shifted["day"]=(__import__("pandas").to_datetime(shifted.day)-__import__("pandas").Timedelta(days=60)).dt.strftime("%Y-%m-%d")
 moved=e.score_candidate(shifted,c["y"],c["select"],pred,100,12,[])
 R["fixed_date_portability"]={"original_score":normal[0],"earlier_calendar_score":moved[0],"folds":moved[1]}
finally:e.train_candidate=original
(OUT/"cache_definitive.json").write_text(json.dumps(R,ensure_ascii=False,indent=2),encoding="utf8")
assert R["original_fresh_run"]["training_call_count"]>10
assert R["unchanged_completed_restart"]["training_call_count"]==0
assert R["changed_feature_completed_restart"]["training_call_count"]==0
assert R["changed_feature_fresh_directory"]["training_call_count"]>10
assert R["changed_feature_replay_saved_candidates"]["training_call_count"]==10
assert not R["changed_close_completed_restart"]["returned"]
print("DEFINITIVELY REPRODUCED",flush=True)
