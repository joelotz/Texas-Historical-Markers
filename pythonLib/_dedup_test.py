"""
Step 4 — Resolve duplicate ref:US-TX:thc keys in test.csv.
For each duplicate group, keeps the row whose name best matches atlas_db.csv.
If no test row matches the atlas name, all rows for that THC ID are dropped.
Overwrites test.csv in place.
"""

import pandas as pd
import re


def norm(s):
    if pd.isna(s):
        return ""
    s = str(s)
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


test = pd.read_csv("test.csv", dtype=str)
atlas = pd.read_csv("atlas_db.csv", dtype=str, low_memory=False)

for df in (test, atlas):
    df["ref:US-TX:thc"] = df["ref:US-TX:thc"].str.strip()

atlas_idx = atlas[
    atlas["ref:US-TX:thc"].notna() & atlas["ref:US-TX:thc"].ne("")
].set_index("ref:US-TX:thc")

KEY = "ref:US-TX:thc"
dup_ids = test[test[KEY].notna() & test[KEY].ne("")]
dup_ids = dup_ids[dup_ids[KEY].duplicated(keep=False)][KEY].unique()

rows_to_drop = set()

for thc_id in dup_ids:
    grp = test[test[KEY] == thc_id]

    if thc_id not in atlas_idx.index:
        # No atlas entry — drop all rows for this ID
        rows_to_drop.update(grp.index)
        continue

    arow = atlas_idx.loc[thc_id]
    if isinstance(arow, pd.DataFrame):
        arow = arow.iloc[0]
    atlas_name = norm(arow.get("name", ""))

    scores = []
    for idx, row in grp.iterrows():
        t = norm(row.get("name", ""))
        if t == atlas_name:
            score = 2
        elif atlas_name and (t in atlas_name or atlas_name in t):
            score = 1
        else:
            ta, tb = set(t.split()), set(atlas_name.split())
            score = len(ta & tb) / max(len(ta), len(tb), 1) if (ta and tb) else 0
        scores.append((score, idx))

    scores.sort(reverse=True)

    if scores[0][0] == 0:
        # No match at all — drop all
        rows_to_drop.update(grp.index)
    else:
        # Keep the best match; on a tie keep the first occurrence
        rows_to_drop.update(idx for _, idx in scores[1:])

before = len(test)
test_clean = test.drop(index=list(rows_to_drop)).reset_index(drop=True)
after = len(test_clean)

remaining = test_clean[test_clean[KEY].notna() & test_clean[KEY].ne("")]
remaining = remaining[remaining[KEY].duplicated(keep=False)]

test_clean.to_csv("test.csv", index=False)
print(f"Deduplicated test.csv: {before} → {after} rows ({before - after} removed)")
print(f"Remaining duplicate THC keys: {len(remaining)}")
