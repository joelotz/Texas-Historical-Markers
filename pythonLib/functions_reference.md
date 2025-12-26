# THC Toolkit — Function Reference Guide

A clean overview of **all callable functions** in your THC toolkit modules.  
Perfect for quick lookup, repo documentation, or onboarding future contributors.

---

## 📂 counties_cli.py — County-Based CSV Processing
| Function | Purpose |
|---|---|
| `load_filtered(input_file)` | Load dataset & filter unmapped/public markers. |
| `enforce_integer_safe(df)` | Ensure key IDs export as nullable Int64. |
| `apply_simple(df)` | Reduce dataset to core simplified column set. |
| `export_counties(df, outdir, simple=False)` | Export full or simple CSVs per county. |
| `export_single_county(df, county, outdir, simple=False)` | Export a county-specific CSV. |
| `merge_all(df, filename, simple=False)` | Produce a single merged CSV. |
| `write_summary_json(summary, filename)` | Store row counts to a JSON file. |
| `print_stats_table(summary)` | Pretty stats output in terminal. |
| `cli()` / `main()` | Script entry functions. |

---

## 📂 osm_cli.py — Atlas → OSM Integration Tools
| Function | Purpose |
|---|---|
| `read_atlas(filename)` | Load atlas CSV with correct typing. |
| `create_nodes(df)` | Generate OSM node dicts with THC tags. |
| `push2josm(nodes)` | Push nodes directly into JOSM RC API. |
| `write2csv(df, filename, date=False)` | Save DataFrame, optional dated name. |
| `find_missing_osm(atlas, geojson)` | Detect THC markers missing in OSM. |
| `update_isOSM(refs, atlas)` | Mark atlas entries as present in OSM. |
| `main()` | CLI wrapper. |

---

## 📂 route_cli.py — Markers Along Route (KML)
| Function | Purpose |
|---|---|
| `load_kml_route(path)` | Parse KML into Line/MultiLine geometry. |
| `run_with_args(track,data,radius,...)` | Search markers near route; export map/CSV/KML/GeoJSON. |
| `main()` | CLI wrapper. |

---

## 📂 cli.py — Unified THC Command Interface
| Function | Purpose |
|---|---|
| `run_counties(args)` | Handle `thc counties` dispatch. |
| `run_route(args)` | Handle `thc route` dispatch. |
| `run_docs(args)` | Display module documentation. |
| `run_viewcsv(args)` | Terminal CSV viewing utility. |
| `main()` | Full command interface entrypoint. |

---

## 📂 utils.py — Reusable Utilities (most importable)
### CSV Viewing Helpers
`viewcsv_pretty(path)` — Pretty-print columns with `column -t | less`  
`viewcsv_raw(path,max_rows)` — Raw DataFrame print  
`viewcsv_head(path,n)` — First N rows  
`viewcsv_tail(path,n)` — Last N rows  
`viewcsv_search(path,text)` — Filter name column by keyword  
`viewcsv_interactive(df)` — Scrollable rich table viewer  

### Converters
`convert_hmdb_csv(input_file,output_file)` — HMDB → THC formatted CSV  

### Atlas/OSM Tools
`read_atlas(filename)`  
`create_nodes(df)`  
`push2josm(nodes)`  
`write2csv(df,filename,date=False)`  
`find_missing_osm(atlas,geojson)`  
`update_isOSM(refs,atlas)`  

---

## 📌 Quick Import Snippet

```python
from thc.utils import (
    read_atlas, create_nodes, push2josm, convert_hmdb_csv,
    find_missing_osm, update_isOSM, write2csv,
    viewcsv_pretty, viewcsv_raw, viewcsv_head,
    viewcsv_tail, viewcsv_search, viewcsv_interactive
)

from thc.route_cli import load_kml_route, run_with_args
from thc.counties_cli import (
    load_filtered, export_counties, export_single_county,
    merge_all, print_stats_table, write_summary_json
)
```