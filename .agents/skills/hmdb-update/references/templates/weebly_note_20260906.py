"""Append a DATA_NOTE where today's hmdb enrichment replaced a weebly-sourced verified coordinate."""
import csv, io, subprocess, math
from pathlib import Path
ROOT = Path("/mnt/DataDrive/Documents/OSM/Texas-Historical-Markers"); ATLAS = ROOT/"atlas_db.csv"
def hav(a,b,c,d):
    R=6371000; p1,p2=math.radians(a),math.radians(c); dp=p2-p1; dl=math.radians(d-b)
    return 2*R*math.asin(math.sqrt(math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2))
head=list(csv.DictReader(io.StringIO(subprocess.run(['git','-C',str(ROOT),'show','HEAD:atlas_db.csv'],capture_output=True).stdout.decode('utf-8'),newline='')))
with ATLAS.open(newline="", encoding="utf-8") as f:
    rd=csv.DictReader(f); cur=list(rd); fields=list(rd.fieldnames)
hm={}
for r in head: hm.setdefault((r['ref:US-TX:thc'], r['ref:hmdb']), r)   # today's newly linked rows had ref:hmdb='' at HEAD
todo=[]
for r in cur:
    if not r['ref:US-TX:thc'].strip(): continue
    h=hm.get((r['ref:US-TX:thc'], ''))
    if not h or 'weebly' not in h['DATA_NOTE'] or r['ref:hmdb']=='' : continue
    if (h['verified:Latitude'],h['verified:Longitude'])==(r['verified:Latitude'],r['verified:Longitude']): continue
    d=hav(float(h['verified:Latitude']),float(h['verified:Longitude']),float(r['verified:Latitude']),float(r['verified:Longitude']))
    todo.append((r,h,d))
for r,h,d in todo:
    r['DATA_NOTE']=r['DATA_NOTE'].rstrip()+f" | 2026-09-06: verified coordinate replaced by the hmdb {r['ref:hmdb']} field coordinate on linking; the weebly value {h['verified:Latitude']},{h['verified:Longitude']} was {d:.0f} m away."
    print(f"  thc#{r['ref:US-TX:thc']} {r['name'][:30]} {d:.0f} m")
print("rows annotated:", len(todo))
assert len(todo)==22, len(todo)
with ATLAS.open("w", newline="", encoding="utf-8") as f:
    w=csv.DictWriter(f, fieldnames=fields, lineterminator="\n"); w.writeheader(); w.writerows(cur)
print("written")
