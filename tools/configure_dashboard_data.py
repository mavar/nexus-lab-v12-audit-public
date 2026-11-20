"""Verify the public historical archive, extract safely, and configure only this dashboard copy."""
import argparse,json,hashlib,zipfile,os,tempfile,datetime,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser();p.add_argument("--archive",required=True);p.add_argument("--destination",default=str(ROOT/"market_ticks"));a=p.parse_args();dest=Path(a.destination).resolve()
with zipfile.ZipFile(a.archive) as z:
 manifest=json.loads(z.read("DATA_FILES.json"))
 assert len(manifest)==28,"Expected 14 days x 2 streams"
 for name,info in manifest.items():
  target=(dest/name).resolve()
  if not target.is_relative_to(dest):raise ValueError("Unsafe archive member")
  data=z.read(name)
  if len(data)!=info["bytes"] or hashlib.sha256(data).hexdigest()!=info["sha256"]:raise ValueError("Data hash mismatch: "+name)
  target.parent.mkdir(parents=True,exist_ok=True)
  if target.exists():
   if hashlib.sha256(target.read_bytes()).hexdigest()!=info["sha256"]:raise ValueError("Existing different data preserved: "+name)
  else:target.write_bytes(data)
config=ROOT/"dashboard_source/local-config.json"
if config.exists():
 backup=Path(os.environ.get("LOCALAPPDATA",tempfile.gettempdir()))/"NexusBackups";backup.mkdir(parents=True,exist_ok=True);shutil.copy2(config,backup/("dashboard-config-"+datetime.datetime.now().strftime("%Y%m%d-%H%M%S")+".json"))
config.write_text(json.dumps({"quoteRoot":str(dest/"exchange=MEXC/stream=book_ticker"),"tradeRoot":str(dest/"exchange=MEXC/stream=trades")},indent=2),encoding="utf8")
print("Verified/extracted",len(manifest),"files; local configuration created. No exchange connection.")
