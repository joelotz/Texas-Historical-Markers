#!/usr/bin/env python3
import argparse
import pandas as pd

NULL_TOKENS = {"", "nan", "none", "null", "na", "<na>"}
ID_COLS = ["ref:US-TX:thc", "ref:hmdb"]
REQUIRED = ["ref:US-TX:thc", "ref:hmdb", "isMissing", "isPrivate", "addr:county", "addr:city"]


def canonical_id(value: str) -> str:
    v = value.strip()
    if not v or v.casefold() in NULL_TOKENS:
        return ""
    if v.isdigit():
        return v.lstrip("0") or "0"
    return v


def main() -> int:
    p = argparse.ArgumentParser(description="Quick THC atlas CSV contract check")
    p.add_argument("--csv", required=True)
    args = p.parse_args()

    df = pd.read_csv(args.csv, low_memory=False)

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        print(f"[FAIL] missing required columns: {', '.join(missing)}")
        return 1

    failed = False

    for col in ID_COLS:
        vals = df[col].astype("string").fillna("").str.strip()
        bad = vals[(vals != "") & ~vals.str.fullmatch(r"\d+(?:\.0+)?")]
        if not bad.empty:
            failed = True
            print(f"[FAIL] {col} has non-numeric values, sample: {bad.unique()[:5].tolist()}")

        canon = vals.map(canonical_id)
        dupes = canon[(canon != "") & canon.duplicated(keep=False)]
        if not dupes.empty:
            failed = True
            print(f"[FAIL] {col} has duplicate IDs, sample: {sorted(dupes.unique().tolist())[:5]}")

    if failed:
        return 1

    print("[OK] atlas contract check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
