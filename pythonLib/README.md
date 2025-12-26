# County-based tools
thc counties --input data.csv --output UnmappedMarkersPerCounty
thc counties --county Denton --stats
thc counties --merge all.csv --summary-json summary.json

# Route-based tools
thc route --track track01.kml --data data.csv --unmapped --open
thc route --track trip.kml --data data.csv --radius 10 --export-csv --geojson

# Docs
thc docs counties
thc docs route
