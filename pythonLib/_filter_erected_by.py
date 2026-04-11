"""
Step 3 — Filter test.csv to THC-only rows by ErectedBy value.
Overwrites test.csv in place.
"""
import pandas as pd, re, sys

KEEP_PATTERNS = [
    'texas historical commission',
    'state historical survey committee',
    'texas state historical survey committee',
    'texas historical survey committee',
    'historical survey committee',
    'state of texas',
]
EXPLICIT_DROP = [
    'state of texas highway department',
    'state of texas, board of control',
]

def should_keep(val):
    if pd.isna(val):
        return False
    v = str(val).lower().strip()
    if any(ex in v for ex in EXPLICIT_DROP):
        return False
    return any(p in v for p in KEEP_PATTERNS)

df = pd.read_csv('test.csv', dtype=str)
before = len(df)
kept = df[df['ErectedBy'].apply(should_keep)].reset_index(drop=True)
after = len(kept)

kept.to_csv('test.csv', index=False)
print(f"Filtered test.csv: {before} → {after} rows ({before - after} removed)")
