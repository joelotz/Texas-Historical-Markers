# Texas Historical Markers

The [Texas Historical Commission (THC)](https://thc.texas.gov/) is a prolific state agency started in 1953 and dedicated to the preservation of it’s state’s history. “We save the real places that tell the real stories of Texas.”  One interesting responsibility of the THC is to authorize historical markers or plagues. I enjoy visiting and mapping these markers. It forces me to get out of the house and travel, and learn history along the way. 


THC provides a [https://thc.texas.gov/preserve/preservation-programs/historical-markers](https://thc.texas.gov/preserve/preservation-programs/historical-markers) that shows a map with the location and metadata of all the historical markers. The website is slow and often non-functional. It also does not provide any type of download mechanism. I have created a flat file “database” that provides the entire atlas database along with additional data fields.

There is a community of people that use a website named The [Historical Marker Database](https://www.hmdb.org/) (hmdb.org) that crowd sources images, text, location, and other data for historical markers around the world. I am a contributor to this site and have added the Texas reference data to provided atlas database.  I have also mapped the markers in the opensource [OpenStreetMap](https://www.openstreetmap.org/) (osm.org) so the geolocation data and meta fields can be used by anyone or any application. 

### Overpass-Turbo

- [Query URL](https://overpass-turbo.eu/s/1Wdd)

- [Interactive map from overpass-query](https://overpass-turbo.eu/map.html?Q=%2F%2F+%40name+Texas+Historical+Markers%0A%0A%5Bout%3Ajson%5D%5Btimeout%3A25%5D%3B%0A%2F%2F+Define+the+area+of+Texas%0Aarea%5B%22name%22%3D%22Texas%22%5D-%3E.searchArea%3B%0A%0A%2F%2F+Search+for+nodes+with+the+specified+criteria%0Anode%0A++%5B%22memorial%22%3D%22plaque%22%5D%0A++%5B%22operator%22%3D%22Texas+Historical+Commission%22%5D%0A++%28area.searchArea%29%3B%0A%0A%2F%2F+Output+the+results%0Aout+body%3B%0A%3E%3B%0Aout+skel+qt%3B%0A%7B%7Bdata%3Aoverpass%2Cserver%3D%2F%2Foverpass-api.de%2Fapi%2F%7D%7D)

  

## Data Dictionary of Atlas data file

Note the field names are compliant to OSM keys.

| Field                                                        | Type          | Description                                                  |
| ------------------------------------------------------------ | ------------- | ------------------------------------------------------------ |
| [ref:US-TX:thc](https://wiki.openstreetmap.org/wiki/Key:ref:US-TX:*) | 32bit Integer | The unique THC marker reference number.                      |
| [ref:hmdb](https://wiki.openstreetmap.org/wiki/Key:ref:hmdb) | 32bit Integer | The unique HMDB marker reference number.                     |
| [name](https://wiki.openstreetmap.org/wiki/Key:name)         | String        | The name or title of the marker.                             |
| [website](https://wiki.openstreetmap.org/wiki/Key:website)   | String        | URL of the source THC web page that defines the marker data. |
| memorial:website                                             | String        | URL of the hmdb.org web page of this marker.                 |
| isTHC                                                        | Boolean       | Indicates if the organization that erected the marker is THC.  Markers may be erected by county or local city historical orgs. |
| isHMDB                                                       | Boolean       | Indicates if the marker is in hmdb.org.                      |
| isMissing                                                    | Boolean       | Indicates if THC or someone has identified this marker as missing and not currently being displayed. |
| isPending                                                    | Boolean       | Indicates that THC has marked this as pending. Typical occurs when the org as approved the marker but locals have not erected it. Not easily confirmed. |
| isOSM                                                        | Boolean       | Indicates if the marker is in osm.org map database.          |
| [start_date](https://wiki.openstreetmap.org/wiki/Key:start_date) | 32bit Integer | The date THC authorized the creation of this historical marker. |
| addr:full                                                    | String        | The house number and street address of the marker. Data is from hmdb.org reverse geocoding when available, otherwise, source is THC. |
| addr:city                                                    | String        | City where the marker is located.                            |
| addr:county                                                  | String        | County where the marker is located. Useful for filtering.    |
| UTM Zone                                                     | 16bit Integer | Calculated UTM Zone based on THC provided UTM coordinates.   |
| UTM Easting                                                  | 32bit Integer | THC provide UTM coordinate. Often inaccurate. The hmdb:Latitude are accurate. |
| UTM Northing                                                 | 32bit Integer | THC provide UTM coordinate. Often inaccurate. The hmdb:Longitude are accurate. |
| thc:Latitude                                                 | Float         | Degree decimal coordinate calculated from the THC UTM coordinates. |
| thc:Longitude                                                | Float         | Degree decimal coordinate calculated from the THC UTM coordinates. |
| hmdb:Latitude                                                | Float         | Degree decimal coordinates provide by users from the hmdb.org page. Much more accurate then the THC provided location. |
| hmdb:Longitude                                               | Float         | Degree decimal coordinates provide by users from the hmdb.org page. Much more accurate then the THC provided location. |
| Recorded Texas Historic Landmark                             | Boolean       | Carried from Atlas provided data.                            |
| thc:designation                                              | Enumeration   | [Historical Marker, Recorded Texas Historic Landmark], provided by THC. |
| Private Property                                             | Boolean       | True=Private property that often restricts access to the historical marker |
| Marker Notes                                                 | String        | Often carried from Atlas provided data.                      |
| wikimedia_commons                                            | String        | Public Domain mages of the markers located in https://meta.wikimedia.org/. |
| Marker Text                                                  | String        | The actual inscription of the marker.                        |
| inscription_size                                             | Integer       | The character link of the marker text (inscription)          |
| DATA_NOTE                                                    | String        |                                                              |



