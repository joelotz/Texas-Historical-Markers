#!/usr/bin/env python3
"""
THC CSV / SQLite sync helpers.

CSV remains the source of truth. SQLite is a generated working copy that is
useful for fast filtering, sorting, and browser-backed views.

Commands:
    thc sqlite build   -> rebuild SQLite from CSV
    thc sqlite export  -> export CSV back out of SQLite
    thc sqlite verify  -> compare row counts and key columns
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd

from .utils import (
    assert_no_duplicate_ids,
    coerce_nullable_int_series,
    parse_bool_series,
    require_columns,
)

DEFAULT_TABLE_NAME = "atlas"
DEFAULT_KEY_COLUMNS = ("ref:US-TX:thc", "ref:hmdb", "OsmNodeID")
DEFAULT_BOOL_COLUMNS = ("isMissing", "isPrivate", "isOSM")
DEFAULT_INDEX_COLUMNS = (
    "ref:US-TX:thc",
    "ref:hmdb",
    "OsmNodeID",
    "addr:county",
    "addr:city",
    "isOSM",
    "isMissing",
    "isPrivate",
)


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _safe_index_name(table_name: str, column_name: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_]+", "_", f"{table_name}_{column_name}")
    return f"idx_{slug.strip('_')}"


def _ensure_parent_dir(path: str | Path) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def _load_csv_frame(csv_path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, low_memory=False)
    require_columns(df, list(DEFAULT_KEY_COLUMNS), context="sqlite sync source CSV")

    for col in DEFAULT_KEY_COLUMNS:
        df[col] = coerce_nullable_int_series(
            df[col], col, context="sqlite sync source CSV"
        )

    for col in DEFAULT_BOOL_COLUMNS:
        if col in df.columns:
            df[col] = parse_bool_series(
                df[col], col, context="sqlite sync source CSV", na_value=None
            )

    return df


def _load_sqlite_frame(sqlite_path: str | Path, table_name: str) -> pd.DataFrame:
    with sqlite3.connect(sqlite_path) as conn:
        query = f"SELECT * FROM {_quote_identifier(table_name)} ORDER BY rowid"
        return pd.read_sql_query(query, conn)


def _normalize_key_frame(
    df: pd.DataFrame, key_columns: Iterable[str], context: str
) -> pd.DataFrame:
    require_columns(df, list(key_columns), context=context)
    out = pd.DataFrame(index=df.index)
    for col in key_columns:
        out[col] = coerce_nullable_int_series(df[col], col, context=context).astype(
            "string"
        )
    return out


def _prepare_sqlite_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in DEFAULT_KEY_COLUMNS:
        out[col] = coerce_nullable_int_series(
            out[col], col, context="sqlite sync build"
        ).astype("string")
    for col in DEFAULT_BOOL_COLUMNS:
        if col in out.columns:
            out[col] = (
                parse_bool_series(
                    out[col], col, context="sqlite sync build", na_value=None
                )
                .astype("string")
                .fillna("")
            )
    for col in out.columns:
        if col in DEFAULT_KEY_COLUMNS or col in DEFAULT_BOOL_COLUMNS:
            continue
        out[col] = out[col].astype("string").fillna("")
    return out


def _normalize_frame_for_compare(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for col in normalized.columns:
        if col in DEFAULT_KEY_COLUMNS:
            normalized[col] = (
                coerce_nullable_int_series(
                    normalized[col], col, context="sqlite sync compare"
                )
                .astype("string")
                .fillna("")
            )
        elif col in DEFAULT_BOOL_COLUMNS:
            normalized[col] = (
                parse_bool_series(
                    normalized[col], col, context="sqlite sync compare", na_value=None
                )
                .astype("string")
                .fillna("")
            )
        else:
            normalized[col] = (
                normalized[col]
                .astype("string")
                .fillna("")
                .str.strip()
                .str.replace(r"\.0+$", "", regex=True)
            )
    return normalized


def build_sqlite_from_csv(
    csv_path: str | Path,
    sqlite_path: str | Path,
    table_name: str = DEFAULT_TABLE_NAME,
    strict_ids: bool = False,
) -> dict[str, object]:
    """
    Rebuild a SQLite database from CSV.

    The SQLite table is replaced in place. Indexes are added for the common
    THC sync and filtering columns when they are present.
    """
    df = _load_csv_frame(csv_path)
    if strict_ids:
        assert_no_duplicate_ids(
            df, list(DEFAULT_KEY_COLUMNS), context="sqlite sync source CSV"
        )
    df = _prepare_sqlite_frame(df)

    _ensure_parent_dir(sqlite_path)
    with sqlite3.connect(sqlite_path) as conn:
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        present = set(df.columns)
        for column in DEFAULT_INDEX_COLUMNS:
            if column not in present:
                continue
            index_name = _safe_index_name(table_name, column)
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {_quote_identifier(index_name)} "
                f"ON {_quote_identifier(table_name)} ({_quote_identifier(column)})"
            )
        conn.commit()

    report = {
        "csv_path": str(csv_path),
        "sqlite_path": str(sqlite_path),
        "table_name": table_name,
        "rows": len(df),
        "columns": list(df.columns),
    }
    print(
        f"✔ Rebuilt SQLite table '{table_name}' at {sqlite_path} "
        f"from {csv_path} ({len(df)} rows)"
    )
    return report


def export_csv_from_sqlite(
    sqlite_path: str | Path,
    csv_path: str | Path,
    table_name: str = DEFAULT_TABLE_NAME,
) -> pd.DataFrame:
    """
    Export a CSV from SQLite.

    The export preserves column order from the SQLite table and normalizes the
    canonical THC ID / boolean columns back into CSV-friendly values.
    """
    df = _load_sqlite_frame(sqlite_path, table_name)
    require_columns(df, list(DEFAULT_KEY_COLUMNS), context="sqlite sync export SQLite")

    normalized = df.copy()
    for col in DEFAULT_KEY_COLUMNS:
        normalized[col] = coerce_nullable_int_series(
            normalized[col], col, context="sqlite sync export"
        )
    for col in DEFAULT_BOOL_COLUMNS:
        if col in normalized.columns:
            normalized[col] = parse_bool_series(
                normalized[col], col, context="sqlite sync export", na_value=None
            )

    _ensure_parent_dir(csv_path)
    normalized.to_csv(csv_path, index=False)
    print(
        f"✔ Exported CSV at {csv_path} from SQLite table '{table_name}' "
        f"({len(normalized)} rows)"
    )
    return normalized


def verify_sqlite_sync(
    csv_path: str | Path,
    sqlite_path: str | Path,
    table_name: str = DEFAULT_TABLE_NAME,
    key_columns: Iterable[str] = DEFAULT_KEY_COLUMNS,
) -> dict[str, object]:
    """
    Compare row counts and key columns between the CSV and SQLite table.
    """
    csv_df = _load_csv_frame(csv_path)
    sqlite_df = _load_sqlite_frame(sqlite_path, table_name)

    if list(csv_df.columns) != list(sqlite_df.columns):
        raise ValueError(
            "column order mismatch between CSV and SQLite: "
            f"CSV={list(csv_df.columns)} SQLite={list(sqlite_df.columns)}"
        )

    if len(csv_df) != len(sqlite_df):
        raise ValueError(
            f"row count mismatch: CSV has {len(csv_df)} rows, SQLite has {len(sqlite_df)} rows"
        )

    csv_norm = _normalize_frame_for_compare(csv_df)
    sqlite_norm = _normalize_frame_for_compare(sqlite_df)

    if not csv_norm.equals(sqlite_norm):
        mismatch_mask = csv_norm.ne(sqlite_norm).any(axis=1)
        first_bad = mismatch_mask[mismatch_mask].index[0] if mismatch_mask.any() else 0
        raise ValueError(
            "row mismatch detected at row "
            f"{first_bad}: CSV={csv_norm.iloc[first_bad].to_dict()} "
            f"SQLite={sqlite_norm.iloc[first_bad].to_dict()}"
        )

    report = {
        "match": True,
        "rows": len(csv_norm),
        "table_name": table_name,
        "key_columns": list(key_columns),
    }
    print(
        f"✔ CSV and SQLite are in sync for table '{table_name}' "
        f"({len(csv_norm)} rows, keys: {', '.join(key_columns)})"
    )
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="thc sqlite", description="CSV / SQLite sync tools"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Rebuild SQLite from CSV")
    build.add_argument("--csv", required=True, help="Source CSV file")
    build.add_argument("--sqlite", required=True, help="Destination SQLite file")
    build.add_argument("--table", default=DEFAULT_TABLE_NAME, help="SQLite table name")

    export = sub.add_parser("export", help="Export CSV from SQLite")
    export.add_argument("--sqlite", required=True, help="Source SQLite file")
    export.add_argument("--csv", required=True, help="Destination CSV file")
    export.add_argument("--table", default=DEFAULT_TABLE_NAME, help="SQLite table name")

    verify = sub.add_parser("verify", help="Verify CSV and SQLite are aligned")
    verify.add_argument("--csv", required=True, help="Source CSV file")
    verify.add_argument("--sqlite", required=True, help="SQLite file to check")
    verify.add_argument("--table", default=DEFAULT_TABLE_NAME, help="SQLite table name")

    args = parser.parse_args(argv)

    if args.command == "build":
        build_sqlite_from_csv(args.csv, args.sqlite, table_name=args.table)
    elif args.command == "export":
        export_csv_from_sqlite(args.sqlite, args.csv, table_name=args.table)
    elif args.command == "verify":
        verify_sqlite_sync(args.csv, args.sqlite, table_name=args.table)


if __name__ == "__main__":  # pragma: no cover
    main()
