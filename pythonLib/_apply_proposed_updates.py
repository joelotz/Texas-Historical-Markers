"""
Step 9 — Apply proposed HMDB additions to atlas_db.csv.
Reads review_proposed_updates.csv and sets ref:hmdb, hmdb:Latitude,
hmdb:Longitude, isHMDB=True, and memorial:website for rows that were
previously missing a HMDB ID.
"""

import pandas as pd

atlas = pd.read_csv("atlas_db.csv", dtype=str, low_memory=False)
proposed = pd.read_csv("review_proposed_updates.csv", dtype=str)

atlas["ref:US-TX:thc"] = atlas["ref:US-TX:thc"].str.strip()
atlas = atlas.set_index("ref:US-TX:thc")

updated = 0
for _, row in proposed.iterrows():
    thc_id = str(row["ref:US-TX:thc"]).strip()
    if thc_id not in atlas.index:
        continue
    atlas.at[thc_id, "ref:hmdb"] = row["new_ref:hmdb"]
    atlas.at[thc_id, "hmdb:Latitude"] = row["new_hmdb:Latitude"]
    atlas.at[thc_id, "hmdb:Longitude"] = row["new_hmdb:Longitude"]
    atlas.at[thc_id, "isHMDB"] = "True"
    atlas.at[thc_id, "memorial:website"] = row["new_memorial:website"]
    updated += 1

atlas.reset_index().to_csv("atlas_db.csv", index=False)
print(f"Applied {updated} proposed HMDB updates to atlas_db.csv")
