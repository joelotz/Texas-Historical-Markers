# thc/utils.py
import pandas as pd
import json
import requests
from datetime import datetime
import shutil
import subprocess
import re
import unicodedata
from rich.console import Console
from rich.table import Table


def require_columns(df, required_columns, context="dataframe"):
    """Raise a clear error when required columns are missing."""
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"{context} missing required column(s): {', '.join(missing)}")


def _normalize_scalar(value):
    """Convert pandas/numpy scalar NA values into JSON-safe Python values."""
    if pd.isna(value):
        return None
    return value


_TRUTHY = {"true", "1", "yes", "y", "t"}
_FALSEY = {"false", "0", "no", "n", "f"}
_NULL_TOKENS = {"", "nan", "none", "null", "na", "<na>"}
_INT_PATTERN = re.compile(r"\d+")


def normalize_match_key(value):
    """Normalize free-text values for robust equality matching."""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold()


def normalize_match_series(series):
    """Vectorized form of normalize_match_key for a pandas Series."""
    return series.map(normalize_match_key)


def parse_bool_series(series, column, context="dataframe", na_value=False):
    """
    Parse booleans from mixed CSV data.
    Accepts common true/false tokens and raises on unknown values.
    """
    text = series.astype("string").str.strip().str.casefold()
    is_na = series.isna() | text.isin(_NULL_TOKENS)
    is_valid = is_na | text.isin(_TRUTHY) | text.isin(_FALSEY)
    if (~is_valid).any():
        bad = sorted(text[~is_valid].dropna().unique().tolist())
        sample = ", ".join(repr(v) for v in bad[:5])
        raise ValueError(
            f"{context} has invalid boolean values in {column}: {sample}. "
            "Use true/false style values."
        )

    out = pd.Series(pd.NA, index=series.index, dtype="boolean")
    out.loc[text.isin(_TRUTHY)] = True
    out.loc[text.isin(_FALSEY)] = False
    if na_value is not None:
        out = out.fillna(bool(na_value))
    return out.astype("boolean")


def coerce_nullable_int_series(series, column, context="dataframe"):
    """Strictly coerce nullable integer series; raise on invalid non-empty values."""
    values = series.astype("string").str.strip()
    lowered = values.str.casefold()
    is_blank = series.isna() | lowered.isin(_NULL_TOKENS)
    normalized = values.str.replace(r"\.0+$", "", regex=True)
    invalid = ~is_blank & ~normalized.map(
        lambda v: bool(_INT_PATTERN.fullmatch(str(v)))
    )
    if invalid.any():
        bad = sorted(values[invalid].unique().tolist())
        sample = ", ".join(repr(v) for v in bad[:5])
        raise ValueError(
            f"{context} has invalid integer values in {column}: {sample}. "
            "Expected empty or all-digit values."
        )
    as_num = pd.to_numeric(normalized.where(~is_blank, pd.NA), errors="raise")
    return as_num.astype("Int64")


def assert_no_duplicate_ids(df, columns, context="dataframe"):
    """Raise when duplicate non-empty IDs are present."""
    for col in columns:
        if col not in df.columns:
            continue
        values = df[col].astype("string").str.strip()
        lowered = values.str.casefold()
        cleaned = values.mask(lowered.isin(_NULL_TOKENS), pd.NA)
        canonical = cleaned.copy()
        digit_mask = canonical.notna() & canonical.str.fullmatch(r"\d+")
        canonical.loc[digit_mask] = (
            canonical.loc[digit_mask].str.lstrip("0").replace("", "0")
        )
        dupes = canonical[canonical.notna() & canonical.duplicated(keep=False)]
        if dupes.empty:
            continue
        sample = ", ".join(repr(v) for v in sorted(dupes.unique().tolist())[:5])
        raise ValueError(f"{context} has duplicate values in {col}: {sample}")


# -------------- CSV Viewing Utilities -------------- #
# Default PRETTY VIEW (shell formatting)
def viewcsv_pretty(path):
    """Default: Display CSV with column | less formatting."""
    column_bin = shutil.which("column")
    less_bin = shutil.which("less")
    if not column_bin or not less_bin:
        print("[WARN] 'column' and/or 'less' not found; falling back to raw output.")
        viewcsv_raw(path)
        return

    with subprocess.Popen(
        [column_bin, "-s,", "-t", path], stdout=subprocess.PIPE
    ) as fmt:
        subprocess.run([less_bin, "-S"], stdin=fmt.stdout, check=False)


# RAW Python print mode
def viewcsv_raw(path, max_rows=200):
    df = pd.read_csv(path)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", shutil.get_terminal_size().columns)
    pd.set_option("display.max_rows", max_rows)
    print(df.to_string(index=False))


# HEAD/TAIL return DataFrame for reuse
def viewcsv_head(path, n):
    return pd.read_csv(path).head(n)


def viewcsv_tail(path, n):
    return pd.read_csv(path).tail(n)


# SEARCH returns filtered dataframe
def viewcsv_search(path, text):
    df = pd.read_csv(path)
    if "name" not in df.columns:
        print("⚠ CSV has no 'name' column")
        return pd.DataFrame()
    mask = df["name"].astype(str).str.contains(text, case=False, na=False)
    return df[mask]


def viewcsv_interactive(df):
    """Scrollable CSV viewer using rich."""
    console = Console()
    table = Table(show_lines=True)

    # Add columns
    for col in df.columns:
        table.add_column(str(col))

    # Add rows
    for _, row in df.iterrows():
        table.add_row(*[str(x) for x in row.values])

    console.print(table)
    console.print("[dim]Press Ctrl+C or q to exit[/dim]")


def convert_hmdb_csv(input_file, output_file):
    """
    Convert HMDB CSV to standardized THC format.

    Fields converted to Int32 (nullable):
        ref:hmdb
        ref:US-TX:thc
    """

    column_map = {
        "MarkerID": "ref:hmdb",
        "Marker No.": "ref:US-TX:thc",
        "Title": "name",
        "Erected By": "ErectedBy",
        "Latitude (minus=S)": "hmdb:Latitude",
        "Longitude (minus=W)": "hmdb:Longitude",
        "Street Address": "addr:full",
        "City or Town": "addr:city",
        "County or Parish": "addr:county",
        "Missing": "isMissing",
    }

    df = pd.read_csv(input_file, dtype=str)

    # Verify required columns exist
    missing = [c for c in column_map if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected column(s): {missing}")

    # Select & rename
    df = df[list(column_map.keys())].rename(columns=column_map)

    # Convert reference IDs with strict validation.
    # Accept only all-digit values (after stripping); reject mixed/alphanumeric values.
    for col in ["ref:hmdb", "ref:US-TX:thc"]:
        values = df[col].fillna("").astype(str).str.strip()
        invalid_mask = values.ne("") & ~values.str.fullmatch(r"\d+")
        if invalid_mask.any():
            bad_values = values[invalid_mask].unique().tolist()
            sample = ", ".join(repr(v) for v in bad_values[:5])
            raise ValueError(
                f"Invalid non-numeric values in {col}: {sample}. "
                "Expected empty or all-digit values."
            )
        df[col] = values

    # Export
    df.to_csv(output_file, index=False)
    print(f"[OK] Converted HMDB → {output_file}")
    #   print(f"[INFO] Numeric integer fields applied to: ref:hmdb, ref:US-TX:thc")
    return df


# -------------- Additional Utility Functions -------------- #
def read_atlas(filename):
    types = {
        "ref:US-TX:thc": "Int32",
        "ref:hmdb": "Int32",
        "start_date": "Int32",
        "UTM Easting": "Int32",
        "UTM Northing": "Int32",
        "UTM Zone": "Int16",
        "isTHC": "boolean",
        "isHMDB": "boolean",
        "isOSM": "boolean",
        "isMissing": "boolean",
        "isPending": "boolean",
        "isPrivate": "boolean",
        "Recorded Texas Historic Landmark": "boolean",
        "inGoogle": "boolean",
    }
    return pd.read_csv(filename, dtype=types, low_memory=False)


def create_nodes(df):
    require_columns(
        df,
        [
            "name",
            "ref:US-TX:thc",
            "ref:hmdb",
            "website",
            "hmdb:Latitude",
            "hmdb:Longitude",
        ],
        context="create_nodes input",
    )
    assert_no_duplicate_ids(
        df, ["ref:US-TX:thc", "ref:hmdb"], context="create_nodes input"
    )
    thc_ref = coerce_nullable_int_series(
        df["ref:US-TX:thc"], "ref:US-TX:thc", context="create_nodes input"
    )
    hmdb_ref = coerce_nullable_int_series(
        df["ref:hmdb"], "ref:hmdb", context="create_nodes input"
    )
    nodes = []
    row_errors = []
    for index, row in df.iterrows():
        try:
            lat = pd.to_numeric(
                pd.Series([row["hmdb:Latitude"]]), errors="coerce"
            ).iloc[0]
            lon = pd.to_numeric(
                pd.Series([row["hmdb:Longitude"]]), errors="coerce"
            ).iloc[0]
            if pd.isna(lat) or pd.isna(lon):
                row_errors.append(f"row {index}: invalid hmdb:Latitude/hmdb:Longitude")
                continue

            row_thc = thc_ref.iloc[index]
            row_hmdb = hmdb_ref.iloc[index]
            tags = {
                "name": _normalize_scalar(row["name"]),
                "historic": "memorial",
                "memorial": "plaque",
                "material": "aluminium",
                "support": "pole",
                "operator": "Texas Historical Commission",
                "operator:wikidata": "Q2397965",
                "thc:designation": "Historical Marker",
                "ref:US-TX:thc": int(row_thc) if pd.notna(row_thc) else None,
                "ref:hmdb": int(row_hmdb) if pd.notna(row_hmdb) else None,
                "source:website": _normalize_scalar(row["website"]),
            }
            if pd.notna(row_hmdb):
                tags["memorial:website"] = (
                    f"https://www.hmdb.org/m.asp?m={int(row_hmdb)}"
                )
            if "start_date" in df.columns and pd.notna(row.get("start_date")):
                tags["start_date"] = _normalize_scalar(row["start_date"])

            nodes.append({"lat": float(lat), "lon": float(lon), "tags": tags})

        except Exception as e:
            row_errors.append(f"row {index}: {e}")

    if row_errors:
        sample = "; ".join(row_errors[:5])
        raise ValueError(f"create_nodes input has invalid rows: {sample}")

    return nodes


def push2josm(nodes):
    url = "http://localhost:8111/add_node"
    added = []
    for n in nodes:
        clean_tags = {
            k: v
            for k, v in n["tags"].items()
            if v is not None and not (isinstance(v, str) and v.strip() == "")
        }
        tag_str = "|".join(f"{k}={v}" for k, v in clean_tags.items())
        r = requests.get(
            url, params={"lat": n["lat"], "lon": n["lon"], "addtags": tag_str}
        )
        if r.status_code == 200:
            added.append(n["tags"]["ref:US-TX:thc"])
        else:
            print(f"[FAIL] {r.status_code} @ {n['lat']},{n['lon']}")
    print(f"[OK] {len(added)} nodes pushed")
    return added


def write2csv(df, filename, date=False):
    if date:
        filename = f"./file_backup/{datetime.now():%Y%m%d}_{filename}"
    df.to_csv(filename, index=False)
    print(f"[OK] wrote {filename}")


def find_missing_osm(atlas, geojson):
    require_columns(atlas, ["ref:US-TX:thc"], context="atlas")
    assert_no_duplicate_ids(atlas, ["ref:US-TX:thc"], context="atlas")
    with open(geojson) as f:
        data = json.load(f)
    osm_ref_values = [
        str(f["properties"]["ref:US-TX:thc"]).strip()
        for f in data.get("features", [])
        if "ref:US-TX:thc" in f.get("properties", {})
    ]
    counts = pd.Series(osm_ref_values).value_counts()
    dupes = set(counts[counts > 1].index.tolist())
    if dupes:
        sample = ", ".join(repr(v) for v in sorted(dupes)[:5])
        raise ValueError(f"geojson has duplicate values in ref:US-TX:thc: {sample}")

    osm_refs = {int(v) for v in osm_ref_values if v}
    atlas_refs = set(atlas["ref:US-TX:thc"].dropna().astype(int))
    missing = sorted(atlas_refs - osm_refs)
    print(f"[INFO] missing: {len(missing)}")
    return missing


def update_isOSM(refs, atlas):
    require_columns(atlas, ["ref:US-TX:thc", "isOSM"], context="atlas")
    before = atlas["isOSM"].sum()
    atlas.loc[atlas["ref:US-TX:thc"].isin(refs), "isOSM"] = True
    print(f"[OK] updated {atlas['isOSM'].sum() - before} flags")
    return atlas
