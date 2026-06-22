# THC Command Reference

## Install and verify

```bash
cd pythonLib
pip install -e .
make verify
```

## Root CLI entrypoint

```bash
cd pythonLib
thc --help
```

Fallback:

```bash
cd pythonLib
python -m thc_toolkit.cli --help
```

## Canonical subcommands

```bash
thc counties --help
thc route --help
thc map --help
thc viewcsv --help
thc convertHMDB --help
thc docs counties
```

## Typical workflows

```bash
cd pythonLib
thc counties --input ../atlas_db.csv --output ../scripts/UnmappedMarkersPerCounty --stats
thc route --track ../scripts/test.kml --data ../atlas_db.csv --radius 5 --csv
thc map --data ../atlas_db.csv --county Travis --unmapped --csv
```

## Verification command

```bash
cd pythonLib
PYTHON=../.venv/bin/python make verify
```
