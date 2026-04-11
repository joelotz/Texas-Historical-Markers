"""
Step 8 — Apply HMDB conflict corrections to atlas_db.csv.
Reads review_hmdb_conflicts.csv and updates ref:hmdb, hmdb:Latitude,
hmdb:Longitude, isHMDB, and memorial:website using the test file values.
"""
import pandas as pd

atlas  = pd.read_csv('atlas_db.csv', dtype=str, low_memory=False)
diffs  = pd.read_csv('review_hmdb_conflicts.csv', dtype=str)
test   = pd.read_csv('test.csv', dtype=str)

atlas['ref:US-TX:thc'] = atlas['ref:US-TX:thc'].str.strip()
test['ref:US-TX:thc']  = test['ref:US-TX:thc'].str.strip()
test_idx = test.set_index('ref:US-TX:thc')

atlas = atlas.set_index('ref:US-TX:thc')

updated = 0
for _, row in diffs.iterrows():
    thc_id   = str(row['ref:US-TX:thc']).strip()
    new_hmdb = str(row['test_ref:hmdb']).strip()

    if thc_id not in atlas.index:
        continue

    atlas.at[thc_id, 'ref:hmdb']         = new_hmdb
    atlas.at[thc_id, 'memorial:website'] = f'https://www.hmdb.org/m.asp?m={new_hmdb}'
    atlas.at[thc_id, 'isHMDB']           = 'True'

    if thc_id in test_idx.index:
        trow = test_idx.loc[thc_id]
        if isinstance(trow, pd.DataFrame): trow = trow.iloc[0]
        lat = str(trow.get('hmdb:Latitude',  '')).strip()
        lon = str(trow.get('hmdb:Longitude', '')).strip()
        if lat not in ('', 'nan'): atlas.at[thc_id, 'hmdb:Latitude']  = lat
        if lon not in ('', 'nan'): atlas.at[thc_id, 'hmdb:Longitude'] = lon

    updated += 1

atlas.reset_index().to_csv('atlas_db.csv', index=False)
print(f"Applied {updated} HMDB conflict corrections to atlas_db.csv")
