"""2026-09-06 hmdb update, the edits `thc hmdb apply` cannot express.

Joe's decisions (this session):
  thc#3443  Monterey High School      isMissing True -> False (hmdb 308175 in place, THC In Situ)
  thc#2037  Fort Worth & Denver City  isMissing False -> True (hmdb 91695 Reported Missing); keep OSM node
  thc#6198  Saint Paul Baptist Church isMissing False -> True (hmdb 171539 Confirmed Missing since 2026-08-26,
                                      missed by the 2026-09-01 sync); OSM node decision pending
  thc#11907/13759/22621               DATA_NOTE for the re-catalogues Joe applied by hand
  thc#15483 Smith Cemetery            finish the enrichment Joe started by hand (hmdb 310012 is filed
                                      under Marker No. 7150, a typo): addr:city, isPending, Marker Notes
  new row   J. Goldstein DuPree       hmdb 310083, no THC Marker No.; appended after the other two
                                      no-thc# rows following the Richard Williams (hmdb 307955) pattern
"""
import csv, sys
from pathlib import Path
ROOT = Path("/mnt/DataDrive/Documents/OSM/Texas-Historical-Markers"); ATLAS = ROOT/"atlas_db.csv"
SP = Path("/tmp/claude-1000/-mnt-DataDrive-Documents-OSM-Texas-Historical-Markers/2bc9de20-d482-4850-83a6-7923bbe5f406/scratchpad")
D = "2026-09-06"
with ATLAS.open(newline="", encoding="utf-8") as f:
    r = csv.DictReader(f); rows = list(r); fields = list(r.fieldnames)
by = {}
for x in rows: by.setdefault(x["ref:US-TX:thc"], []).append(x)
def one(thc):
    h = by.get(thc, []); assert len(h) == 1, (thc, len(h)); return h[0]
def note(row, text):
    old = row["DATA_NOTE"].strip(); row["DATA_NOTE"] = (old + " | " + text) if old else text

r = one("3443"); assert r["isMissing"] == "True" and r["ref:hmdb"] == "308175"
r["isMissing"] = "False"; note(r, f"{D}: isMissing reset to False; hmdb 308175 reports the marker in place and THC lists it In Situ (True had come in with the 2026-08-14 repair).")
r = one("2037"); assert r["isMissing"] == "False" and r["ref:hmdb"] == "91695" and r["OsmNodeID"] == "12453470340"
r["isMissing"] = "True"; note(r, f"{D}: hmdb 91695 Reported Missing (first seen in the 2026-09-06 export); OSM node 12453470340 kept, only reported not confirmed.")
r = one("6198"); assert r["isMissing"] == "False" and r["ref:hmdb"] == "171539" and r["OsmNodeID"] == "12402961251"
r["isMissing"] = "True"; note(r, f"{D}: hmdb 171539 Confirmed Missing (hmdb updated 2026-08-26, missed by the 2026-09-01 sync).")
for thc, old, new in (("22621", "309543", "309757"), ("11907", "309566", "309753"), ("13759", "309576", "309760")):
    r = one(thc); assert r["ref:hmdb"] == new and r["memorial:website"].endswith("m=" + new), (thc, r["ref:hmdb"])
    extra = " New page is filed under the correct Marker No. 13759, so the 2026-09-01 note about the 1714 typo no longer applies." if thc == "13759" else ""
    note(r, f"{D}: hmdb re-catalogued this marker; ref:hmdb {old} -> {new} (old id in the 2026-09-01 export, gone from 2026-09-06; new page matches on title, Marker No., address and coordinate). Atlas swapped by Joe by hand.{extra}")
r = one("15483"); assert r["ref:hmdb"] == "310012" and r["isHMDB"] == "True"
r["addr:city"] = "Waxahachie"; r["isPending"] = "False"; r["isMissing"] = "False"; r["Marker Notes"] = ""
note(r, f"{D}: hmdb 310012 files this marker under Marker No. 7150 (hmdb typo: THC has no 7150; title, 1973 date and coordinate match this row to 5 m). Linked by Joe by MarkerID; enrichment completed by script (addr:city Palmer -> Waxahachie per hmdb).")

ins = (SP/"dupree_inscription.txt").read_text()
ins = ins.replace("\n\n Click or scan to see\nthis page online\n\n ", " ")
assert "Click or scan" not in ins and "Public Buildings and Grounds" in ins, ins[-700:]
assert not any(x["ref:hmdb"] == "310083" for x in rows)
new = {k: "" for k in fields}
new.update({
    "ref:US-TX:thc": "", "ref:hmdb": "310083", "name": "J. Goldstein DuPree", "OsmNodeID": "", "website": "",
    "memorial:website": "https://www.hmdb.org/m.asp?m=310083", "start_date": "2023",
    "isActive": "True", "isHMDB": "True", "isMissing": "False", "isPending": "False", "isOSM": "False", "isPrivate": "False",
    "addr:full": "22985 FM 1097", "addr:city": "Montgomery", "addr:county": "Montgomery",
    "verified:Latitude": "30.40357", "verified:Longitude": "-95.69663",
    "Recorded Texas Historic Landmark": "False", "thc:designation": "Historical Marker",
    "Marker Notes": ("On Willis Montgomery Road (FM 1097) 0.1 miles east of Liberty Road, on the right when traveling east, "
                     "next to the Montgomery Memorial Cemetery marker. Erected 2023 by the 88th Texas Legislature and the "
                     "Texas Historical Commission as authorized by SB 667. Not in the THC Atlas database."),
    "Marker Text": ins,
    "DATA_NOTE": (f"{D}: added from hmdb 310083 (first published 2026-09-05). No THC Marker No. on hmdb or in the 2026-06-25 THC "
                  "export; SB 667 legislative-series marker like Richard Williams (hmdb 307955). Row keyed on ref:hmdb only."),
})
rows.append(new)
assert all(len(x) == len(fields) for x in rows)
with ATLAS.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n"); w.writeheader(); w.writerows(rows)
print("written:", len(rows), "rows")
