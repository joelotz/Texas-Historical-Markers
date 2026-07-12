# Texas Historical Markers

> Cleaner, more accurate, field-verified data for the historical markers scattered across the Lone Star State — free for anyone to use.

Texas is dotted with more than 17,000 historical markers. This repository collects that marker data, enriches it, corrects it, maps it, then hands it back to you in formats you can actually work with.

The [Texas Historical Commission (THC)](https://thc.texas.gov/) publishes an [Atlas Historical Data](https://atlas.thc.texas.gov/Data/DataDownload) download, but it has rough edges: location coordinates are frequently inaccurate, metadata is often missing, and the records rarely say whether a marker is still standing. This project fixes that. I provide a cleaned, enriched dataset in two ready-to-use formats:

- **[atlas_db.csv](https://github.com/joelotz/Texas-Historical-Markers/blob/main/atlas_db.csv)** — human-readable and spreadsheet-friendly
- **[atlas_db.sqlite](https://github.com/joelotz/Texas-Historical-Markers/blob/main/atlas_db.sqlite)** — a queryable SQLite database

**How the data gets better.** Short of physically visiting a marker, my most reliable source is the crowd-sourced [hmdb.org](https://www.hmdb.org), where the GPS coordinates embedded in contributors' marker photos give a far more accurate location than the THC's figures. On top of that, I add Wikimedia Commons images, Wikipedia articles, and Wikidata IDs wherever they exist. Finally, every marker is mapped into [OpenStreetMap](https://www.openstreetmap.org/) so the geolocation and metadata are open to anyone — and any application.

### Texas Historical Commission (THC)

The THC is a prolific state agency, founded in 1953 and devoted to preserving Texas's history:

> "We save the real places that tell the real stories of Texas."

Among its many duties, one is especially relevant here: the THC authorizes the state's official historical markers and plaques.

### Historical Marker Database (hmdb.org)

The [Historical Marker Database](https://www.hmdb.org/) (hmdb.org) is powered by a global community that crowd-sources the images, text, locations, and other details of historical markers around the world. I'm a contributor there, and I've folded that Texas reference data into this atlas to make it more accurate.

### OpenStreetMap (osm.org)

I've also mapped every marker into the open-source [OpenStreetMap](https://www.openstreetmap.org/) (osm.org) so that anyone — or any app — can use the geolocation and metadata freely. OSM is often called "the Wikipedia of maps." Worth remembering: OSM is a *database of map elements*, not the rendered map itself.

The THC does offer its own [historical markers map](https://thc.texas.gov/preserve/preservation-programs/historical-markers), which shows each marker's location and metadata — but it's slow and frequently non-functional. That's exactly why I mapped the markers into OpenStreetMap.

Want to see the whole set live? This link opens Overpass-Turbo and runs a query showing every Texas marker currently mapped in OSM:

- [Run the query](https://overpass-turbo.eu/s/2t7n)

## Data Dictionary

This section defines each data field. Field names follow OSM key conventions wherever possible.

| Column | Field                                                        | Type          | Description                                                  |
| ------ | ------------------------------------------------------------ | ------------- | ------------------------------------------------------------ |
| 1      | [ref:US-TX:thc](https://wiki.openstreetmap.org/wiki/Key:ref:US-TX:*) | 32-bit Integer | The unique THC marker reference number.                      |
| 2      | [ref:hmdb](https://wiki.openstreetmap.org/wiki/Key:ref:hmdb) | 32-bit Integer | The unique HMDB marker reference number.                     |
| 3      | [name](https://wiki.openstreetmap.org/wiki/Key:name)         | String        | The marker's name or title.                             |
| 4      | OsmNodeID                                                    | 16-bit Integer | The OpenStreetMap node ID — handy for jumping straight to the marker in OSM. |
| 5      | [website](https://wiki.openstreetmap.org/wiki/Key:website)   | String        | URL of the source THC page that defines the marker data. |
| 6      | memorial:website                                             | String        | URL of the marker's hmdb.org page.                 |
| 7      | isTHC                                                        | Boolean       | A flag indicating if the marker was erected by the THC. Some are erected instead by county or local city historical organizations. |
| 8      | isHMDB                                                       | Boolean       | A flag indicating if the marker appears in hmdb.org.                      |
| 9      | isMissing                                                    | Boolean       | A flag indicating if the THC or a contributor has identified the marker as missing or no longer on display. |
| 10     | isPending                                                    | Boolean       | A flag indicating if the THC has flagged the marker as pending — typically when a marker has been approved but locals have not yet erected it. Hard to confirm. |
| 11     | isOSM                                                        | Boolean       | A flag indicating if the marker is in the osm.org database.          |
| 12     | isPrivate                                                    | Boolean       | A flag indicating if the marker sits on private property. It may seem odd to track, but some markers are on private land — and in Texas, entering where you're not welcome is a bad idea. |
| 13     | [start_date](https://wiki.openstreetmap.org/wiki/Key:start_date) | 32-bit Integer | The year the THC authorized the marker's creation. |
| 14     | [addr:full](https://wiki.openstreetmap.org/wiki/Key:addr:*#Commonly_used_subkeys) | String        | The house number and street address of the marker. Sourced from the THC and refined through site visits or hmdb.org reverse geocoding where available. |
| 15     | [addr:city](https://wiki.openstreetmap.org/wiki/Key:addr:city) | String        | City where the marker is located.                            |
| 16     | [addr:county](https://wiki.openstreetmap.org/wiki/Key:addr:county) | String        | County where the marker is located. Handy for filtering.    |
| 17     | UTM Zone                                                     | 16-bit Integer | UTM zone calculated from the THC-provided UTM coordinates.   |
| 18     | UTM Easting                                                  | 32-bit Integer | THC-provided UTM coordinate. Often inaccurate — the hmdb coordinates are far more reliable. |
| 19     | UTM Northing                                                 | 32-bit Integer | THC-provided UTM coordinate. Often inaccurate — the hmdb coordinates are far more reliable. |
| 20     | thc:Latitude                                                 | Float         | Decimal-degree latitude calculated from the THC UTM coordinates. |
| 21     | thc:Longitude                                                | Float         | Decimal-degree longitude calculated from the THC UTM coordinates. |
| 22     | hmdb:Latitude                                                | Float         | Decimal-degree latitude provided by hmdb.org contributors. Much more accurate than the THC location. |
| 23     | hmdb:Longitude                                               | Float         | Decimal-degree longitude provided by hmdb.org contributors. Much more accurate than the THC location. |
| 24     | Recorded Texas Historic Landmark                             | Boolean       | Carried over from the THC Atlas data.                            |
| 25     | thc:designation                                              | Enumeration   | One of [Historical Marker, Recorded Texas Historic Landmark], as provided by the THC. |
| 26     | Marker Notes                                                 | String        | Supplementary notes, often carried over from the THC Atlas data.                      |
| 27     | [wikimedia_commons](https://wiki.openstreetmap.org/wiki/Key:wikimedia_commons) | String        | Public-domain images of the marker, hosted on Wikimedia Commons. |
| 28     | [subject:wikimedia_commons](https://wiki.openstreetmap.org/wiki/Key:wikimedia_commons)                                    | String        | Public-domain images of the marker's subject, hosted on Wikimedia Commons. |
| 29     | [subject:wikipedia](https://wiki.openstreetmap.org/wiki/Key:wikipedia#Secondary_Wikipedia_links)                                            | String        | Wikipedia link for the marker's subject.                 |
| 30     | [subject:wikidata](https://wiki.openstreetmap.org/wiki/Key:subject:wikidata)                                             | String        | Wikidata ID for the marker's subject (begins with "Q"). |
| 31     | Marker Text                                                  | String        | The marker's actual inscription.                        |
| 32     | inscription_size                                             | Integer       | The character length of the marker text (inscription).          |
| 33     | DATA_NOTE                                                    | String        | Internal notes captured during data reconciliation.                                                  |

## For AI-assisted contributors

This repo ships project-specific skills under [`.agents/skills/`](./.agents/skills/) that
codify the established workflows (HMDB reconciliation, OSM sync, data-quality audits,
CLI usage). They're written to be agent-agnostic — Claude Code, Codex, Cursor, Aider,
and similar tools can all consume them. See [AGENTS.md](./AGENTS.md#skills) for the
layout and how to use them.
