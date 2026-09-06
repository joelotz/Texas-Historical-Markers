"""Undo LibreOffice trailing-zero churn in the working tree (baseline HEAD e372064).
Keep Joe's 2026-09-06 hand edits on the rows in KEEP (non-coordinate columns, and
thc#15483's newly added verified coord). Restore every verified:/estimated:
coordinate string where HEAD and working tree parse within 1e-8.
Refuses to write if any other difference is found or Calc holds a lock.
"""
import csv, io, subprocess, sys
from pathlib import Path
ROOT = Path("/mnt/DataDrive/Documents/OSM/Texas-Historical-Markers"); ATLAS = ROOT/"atlas_db.csv"
if (ROOT/".~lock.atlas_db.csv#").exists(): sys.exit("Calc has atlas_db.csv open; close it first")
KEEP = {"948", "24309", "8728", "11614", "22847", "24365", "11907", "13759", "15483", "22621"}
COORDS = ["verified:Latitude", "verified:Longitude", "estimated:Latitude", "estimated:Longitude"]
head_txt = subprocess.run(["git", "-C", str(ROOT), "show", "HEAD:atlas_db.csv"], capture_output=True, check=True).stdout.decode("utf-8")
head = list(csv.reader(io.StringIO(head_txt, newline="")))
with ATLAS.open(newline="", encoding="utf-8") as f: cur = list(csv.reader(f))
assert head[0] == cur[0] and len(head) == len(cur), (len(head), len(cur))
hdr = cur[0]; ci = {c: hdr.index(c) for c in COORDS}
restored = 0; kept = {}; other = []
for i in range(1, len(cur)):
    h, c = head[i], cur[i]
    assert h[0] == c[0], f"row order drifted at {i}: {h[0]} vs {c[0]}"
    if h == c: continue
    for col, j in ci.items():
        if h[j] != c[j]:
            try: same = abs(float(h[j]) - float(c[j])) < 1e-8
            except ValueError: same = False
            if same: c[j] = h[j]; restored += 1
    if h != c:
        diff = [(hdr[k], h[k], c[k]) for k in range(len(hdr)) if h[k] != c[k]]
        if c[0] in KEEP: kept[c[0]] = [d[0] for d in diff]
        else: other.append((c[0], diff))
print(f"restored cells: {restored}")
for k, cols in kept.items(): print(f"  kept thc#{k}: {cols}")
print(f"unexplained rows: {len(other)}")
for o in other[:5]: print("  UNEXPLAINED:", o)
if other: sys.exit("refusing to write: unexplained differences")
with ATLAS.open("w", newline="", encoding="utf-8") as f:
    csv.writer(f, lineterminator="\n").writerows(cur)
print("written")
