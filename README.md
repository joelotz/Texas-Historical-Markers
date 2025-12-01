# Texas Historical Markers

The [Texas Historical Commission (THC)](https://thc.texas.gov/) is a prolific state agency started in 1953 and dedicated to the preservation of it’s state’s history. “We save the real places that tell the real stories of Texas.”  One interesting responsibility of the THC is to authorize historical markers or plagues. I enjoy visiting and mapping these markers. It forces me to get out of the house and travel, and learn history along the way. 


THC provides a [https://thc.texas.gov/preserve/preservation-programs/historical-markers](https://thc.texas.gov/preserve/preservation-programs/historical-markers) that shows a map with the location and metadata of all the historical markers. The website is slow and often non-functional. It also does not provide any type of download mechanism. I have created a flat file “database” that provides the entire atlas database along with additional data fields.

There is a community of people that use a website named The [Historical Marker Database](https://www.hmdb.org/) (hmdb.org) that crowd sources images, text, location, and other data for historical markers around the world. I am a contributor to this site and have added the Texas reference data to provided atlas database.  I have also mapped the markers in the opensource [OpenStreetMap](https://www.openstreetmap.org/) (osm.org) so the geolocation data and meta fields can be used by anyone or any application. 

### Overpass-Turbo

- [Query URL](https://overpass-turbo.eu/s/1Wdd)

- [Interactive map from overpass-query](https://overpass-turbo.eu/map.html?Q=%2F%2F+%40name+Texas+Historical+Markers%0A%0A%5Bout%3Ajson%5D%5Btimeout%3A25%5D%3B%0A%2F%2F+Define+the+area+of+Texas%0Aarea%5B%22name%22%3D%22Texas%22%5D-%3E.searchArea%3B%0A%0A%2F%2F+Search+for+nodes+with+the+specified+criteria%0Anode%0A++%5B%22memorial%22%3D%22plaque%22%5D%0A++%5B%22operator%22%3D%22Texas+Historical+Commission%22%5D%0A++%28area.searchArea%29%3B%0A%0A%2F%2F+Output+the+results%0Aout+body%3B%0A%3E%3B%0Aout+skel+qt%3B%0A%7B%7Bdata%3Aoverpass%2Cserver%3D%2F%2Foverpass-api.de%2Fapi%2F%7D%7D)

  

## Data Dictionary of Atlas data file

Note the field names are compliant to OSM keys.

| Column | Field                                                        | Type          | Description                                                  |
| ------ | ------------------------------------------------------------ | ------------- | ------------------------------------------------------------ |
| 1      | [ref:US-TX:thc](https://wiki.openstreetmap.org/wiki/Key:ref:US-TX:*) | 32bit Integer | The unique THC marker reference number.                      |
| 2      | [ref:hmdb](https://wiki.openstreetmap.org/wiki/Key:ref:hmdb) | 32bit Integer | The unique HMDB marker reference number.                     |
| 3      | [name](https://wiki.openstreetmap.org/wiki/Key:name)         | String        | The name or title of the marker.                             |
| 4      | OsmNodeID                                                    | 16bit Integer | The OpenStreetMaps Node ID. Useful for quickly searching for the marker within OSM. |
| 5      | [website](https://wiki.openstreetmap.org/wiki/Key:website)   | String        | URL of the source THC web page that defines the marker data. |
| 6      | memorial:website                                             | String        | URL of the hmdb.org web page of this marker.                 |
| 7      | isTHC                                                        | Boolean       | Indicates if the organization that erected the marker is THC.  Markers may be erected by county or local city historical orgs. |
| 8      | isHMDB                                                       | Boolean       | Indicates if the marker is in hmdb.org.                      |
| 9      | isMissing                                                    | Boolean       | Indicates if THC or someone has identified this marker as missing and not currently being displayed. |
| 10     | isPending                                                    | Boolean       | Indicates that THC has marked this as pending. Typical occurs when the org as approved the marker but locals have not erected it. Not easily confirmed. |
| 11     | isOSM                                                        | Boolean       | Indicates if the marker is in osm.org map database.          |
| 12     | [start_date](https://wiki.openstreetmap.org/wiki/Key:start_date) | 32bit Integer | The date THC authorized the creation of this historical marker. |
| 13     | [addr:full](https://wiki.openstreetmap.org/wiki/Key:addr:*#Commonly_used_subkeys) | String        | The house number and street address of the marker. Data is from THC but updated from site visits or hmdb.org reverse geocoding when available. |
| 14     | [addr:city](https://wiki.openstreetmap.org/wiki/Key:addr:city) | String        | City where the marker is located.                            |
| 15     | [addr:county](https://wiki.openstreetmap.org/wiki/Key:addr:county) | String        | County where the marker is located. Useful for filtering.    |
| 16     | UTM Zone                                                     | 16bit Integer | Calculated UTM Zone based on THC provided UTM coordinates.   |
| 17     | UTM Easting                                                  | 32bit Integer | THC provide UTM coordinate. Often inaccurate. The hmdb:Latitude are much more accurate. |
| 18     | UTM Northing                                                 | 32bit Integer | THC provide UTM coordinate. Often inaccurate. The hmdb:Longitude are much more accurate. |
| 19     | thc:Latitude                                                 | Float         | Degree decimal coordinate calculated from the THC UTM coordinates. |
| 20     | thc:Longitude                                                | Float         | Degree decimal coordinate calculated from the THC UTM coordinates. |
| 21     | hmdb:Latitude                                                | Float         | Degree decimal coordinates provide by users from the hmdb.org page. Much more accurate then the THC provided location. |
| 22     | hmdb:Longitude                                               | Float         | Degree decimal coordinates provide by users from the hmdb.org page. Much more accurate then the THC provided location. |
| 23     | Recorded Texas Historic Landmark                             | Boolean       | Carried from Atlas provided data.                            |
| 24     | thc:designation                                              | Enumeration   | [Historical Marker, Recorded Texas Historic Landmark], provided by THC. |
| 25     | Private Property                                             | Boolean       | True=Private property that often restricts access to the historical marker |
| 26     | Marker Notes                                                 | String        | Often carried from Atlas provided data.                      |
| 27     | [wikimedia_commons](https://wiki.openstreetmap.org/wiki/Key:wikimedia_commons) | String        | Public Domain images of the markers located in https://meta.wikimedia.org/. |
| 28     | subject:wikimedia_commons                                    | String        | Public Domain images of the subject the marker is about, located in https://meta.wikimedia.org/. |
| 29     | subject:wikipedia                                            | String        | Wikipedia link to the subject of the marker.                 |
| 30     | wikidata                                                     | String        | Wikidata ID for the marker. Will start with a “Q”.           |
| 31     | subject:wikidata                                             | String        | Wikidata ID for the subject of the marker. Will start with a “Q”. |
| 32     | Marker Text                                                  | String        | The actual inscription of the marker.                        |
| 33     | inscription_size                                             | Integer       | The character link of the marker text (inscription)          |
| 34     | DATA_NOTE                                                    | String        | {DELETE ME}                                                  |



