# 🗺 Texas Historical Marker Filter & Export Script

### Overview  
This script processes the **Texas Historical Commission marker dataset** and exports **one CSV per county**, containing only markers that **do not yet have an HMDB reference**. It helps identify unmapped markers so they can be researched, photographed, and added to HMDB.

---

## Input

| File | Description |
|---|---|
| `data.csv` | Full THC marker dataset with `ref:hmdb`, `addr:county`, `isMissing`, and `isPrivate` fields |

Place this CSV in the same directory as the script.

---

## Filtering Logic

The script selects markers where:

1. `ref:hmdb` is **missing, blank, or NaN**
2. **Excluded** if either:
   - `isMissing == True`
   - `isPrivate == True`

This leaves only *public, existing markers that need HMDB entries*.

---

## Output

| Output | Description |
|---|---|
| `./UnmappedMarkersPerCounty/` | Created automatically if missing |
| `{county}.csv` files | One file per county, filenames sanitized (spaces → `_`, slashes → `-`) |

Existing files inside this directory will be **overwritten**.

Example:

UnmappedMarkersPerCounty/
├─ Denton.csv
├─ Collin.csv
├─ Tarrant.csv
└─ ...

---

## What this script helps you do

- Quickly locate markers missing HMDB entries  
- Generate per-county "field targets" for research trips  
- Prepare data for mapping or navigation apps  
- Feed results into Folium/KML/GeoJSON workflows

---

## Reference Code

```python
import os
import pandas as pd

OUTPUT_DIR = "UnmappedMarkersPerCounty"
os.makedirs(OUTPUT_DIR, exist_ok=True)

df = pd.read_csv("data.csv", low_memory=False)

base_filtered = df[df["ref:hmdb"].isna() | (df["ref:hmdb"].astype(str).str.strip() == "")]
filtered = base_filtered[
    ~((base_filtered.get("isMissing") == True) | (base_filtered.get("isPrivate") == True))
]

for county, group in filtered.groupby("addr:county"):
    safe_name = str(county).replace(" ", "_").replace("/", "-")
    outfile = os.path.join(OUTPUT_DIR, f"{safe_name}.csv")

    group.to_csv(outfile, index=False)
    print(f"Saved: {outfile} ({len(group)} rows)")
    