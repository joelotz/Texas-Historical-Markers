# Texas Historical Markers

The [Texas Historical Commission (THC)](https://thc.texas.gov/) is a prolific state agency started in 1953 and dedicated to the preservation of it’s state’s history. “We save the real places that tell the real stories of Texas.”  One interesting responsibility of the THC is to authorize historical markers or plagues. I enjoy visiting and mapping these markers. It forces me to get out of the house and travel, and learn history along the way. 


THC provides a [https://thc.texas.gov/preserve/preservation-programs/historical-markers](https://thc.texas.gov/preserve/preservation-programs/historical-markers) that shows a map with the location and metadata of all the historical markers. The website is slow and often non-functional. It also does not provide any type of download mechanism. I have created a flat file “database” that provides the entire atlas database along with additional data fields.


There is a community of people that use a website named The Historical Marker Database (hmdb.org) that crowd sources images, text, location, and other data for historical markers around the world. I am a contributor to this site and have added the Texas reference data to provided atlas database.  I have also mapped the markers in the opensource OpenStreetMap (osm.org) so the geolocation data and meta fields can be used by anyone or any application. 

## Data Dictionary of Atlas data file

Note the field names are compliant to OSM keys.

| Field                                                        | Type    | Description                                                  |
| ------------------------------------------------------------ | ------- | ------------------------------------------------------------ |
| [ref:US-TX:thc](https://wiki.openstreetmap.org/wiki/Key:ref:US-TX:*) | Integer | The unique THC marker reference number.                      |
| website                                                      | String  | URL of the source THC web page that defines the marker data. |
| memorial:website                                             | String  | URL of the hmdb.org web page of this marker.                 |
| ref:hmdb                                                     | Integer | The unique HMDB marker reference number.                     |
|                                                              |         |                                                              |
|                                                              |         |                                                              |
| start_date                                                   | Integer | The date THC authorized the creation of this historical marker. |
| name                                                         | String  | The name or title of the marker.                             |
| addr:full                                                    | String  | The house number and street address of the marker. This is often inaccurate. |
| addr:city                                                    | String  | City where the marker is located.                            |
| addr:county                                                  | String  | County where the marker is located. Useful for filtering.    |
| UTM Zone                                                     | Integer | Calculated UTM Zone based on THC provided UTM coordinates.   |
| UTM Easting                                                  | Float   | THC provide UTM coordinate. Often inaccurate. The hmdb lat/long are accurate. |
| UTM Northing                                                 | Float   | THC provide UTM coordinate. Often inaccurate. The hmdb lat/long are accurate. |
| thc:Latitude                                                 |         | Degree decimal coordinate calculated from the THC UTM coordinates. |
| thc:Longitude                                                |         | Degree decimal coordinate calculated from the THC UTM coordinates. |
| hmdb:Latitude                                                |         | Degree decimal coordinates provide by users from the hmdb.org page. Much more accurate then the THC provided location. |
| hmdb:Longitude                                               |         | Degree decimal coordinates provide by users from the hmdb.org page. Much more accurate then the THC provided location. |
| Recorded Texas Historic Landmark                             |         | Carried from Atlas provided data.                            |
| thc:designation                                              |         |                                                              |
| Private Property                                             | Boolean | True=Private property that often restricts access to the historical marker |
| Marker Notes                                                 |         | Often carried from Atlas provided data.                      |
| wikimedia_commons                                            |         |                                                              |
| Marker Text                                                  |         | The actual inscription of the marker.                        |
| DATA_NOTE                                                    |         |                                                              |



