"""Semantic invariants for atlas_db.csv and hmdb_ignore.csv.

Distinct from ``thc atlas validate``, which is a byte-level encoding check run by
the pre-commit hook. These checks parse the data and assert relationships that
have each been violated in practice without anything noticing:

* An ignore entry naming a MarkerID the atlas uses as its own ``ref:hmdb``.
  ``reconcile()`` would skip the marker's only page and the row would read as
  unlinked. 13 entries reached this state on 2026-08-15 when hmdb merged the
  duplicate pages into the canonical ones.

* An ignore entry whose MarkerID no longer exists on hmdb. The skip keys on
  MarkerID, so a re-catalogued id stops firing and the duplicate resurfaces as a
  conflict. 29 of 41 entries went stale in a single week.

* ``memorial:website`` disagreeing with ``ref:hmdb`` on the same row -- the two
  are written together and drift only when something has gone wrong.

* A duplicate ``ref:US-TX:thc`` group whose rows do not each hold a distinct,
  non-empty ``ref:hmdb``. The composite key is what makes duplicate rows
  addressable; a blank member makes the group ambiguous.

Checks that need the hmdb snapshot are skipped, not failed, when it is absent.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

from .hmdb_sync import IGNORE_FILE_NAME, load_ignored_marker_ids

DEFAULT_ATLAS = "atlas_db.csv"
WEBSITE_TEMPLATE = "https://www.hmdb.org/m.asp?m={}"


def _s(v) -> str:
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "<na>") else s


def _load(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, low_memory=False, keep_default_na=False)


def check_ignore_not_claimed_by_atlas(atlas: pd.DataFrame, ignored: set[str]) -> list[str]:
    """No ignore MarkerID may be an atlas ref:hmdb."""
    used = {}
    for _, r in atlas.iterrows():
        ref = _s(r.get("ref:hmdb"))
        if ref:
            used.setdefault(ref, []).append(_s(r.get("ref:US-TX:thc")))
    clash = sorted(set(ignored) & set(used))
    return [
        f"{IGNORE_FILE_NAME} lists MarkerID {mid}, but the atlas uses it as the "
        f"ref:hmdb of thc#{','.join(used[mid])} — reconcile would skip a real marker"
        for mid in clash
    ]


def check_memorial_website_matches_ref(atlas: pd.DataFrame) -> list[str]:
    """memorial:website must be the canonical URL for that row's ref:hmdb."""
    out = []
    for _, r in atlas.iterrows():
        ref, site = _s(r.get("ref:hmdb")), _s(r.get("memorial:website"))
        if not ref or not site:
            continue
        want = WEBSITE_TEMPLATE.format(ref)
        if site != want:
            out.append(
                f"thc#{_s(r.get('ref:US-TX:thc'))}: memorial:website {site!r} "
                f"does not match ref:hmdb {ref} (expected {want!r})")
    return out


def check_duplicate_thc_groups(atlas: pd.DataFrame) -> list[str]:
    """Rows sharing a THC number must each hold a distinct, non-empty ref:hmdb."""
    out = []
    thc = atlas["ref:US-TX:thc"].map(_s)
    for number, group in atlas[thc != ""].groupby(thc[thc != ""]):
        if len(group) < 2:
            continue
        refs = [_s(v) for v in group["ref:hmdb"]]
        if any(r == "" for r in refs):
            out.append(f"thc#{number}: {len(group)} rows share this THC number but "
                       f"{sum(1 for r in refs if not r)} of them has a blank ref:hmdb")
        elif len(set(refs)) != len(refs):
            out.append(f"thc#{number}: {len(group)} rows share this THC number and "
                       f"repeat a ref:hmdb ({refs})")
    return out


def check_refs_live(atlas: pd.DataFrame, ignored: set[str],
                    snapshot: Path) -> list[str]:
    """Every atlas ref:hmdb and every ignore MarkerID must exist in the snapshot."""
    snap = pd.read_csv(snapshot, dtype=str, low_memory=False)
    live = {_s(v) for v in snap["MarkerID"]}
    out = []

    dead_refs = sorted({_s(r) for r in atlas["ref:hmdb"] if _s(r)} - live)
    if dead_refs:
        out.append(f"{len(dead_refs)} atlas ref:hmdb values are absent from "
                   f"{snapshot.name}: {', '.join(dead_refs[:10])}"
                   + (" …" if len(dead_refs) > 10 else ""))
    dead_ig = sorted(ignored - live)
    if dead_ig:
        out.append(f"{len(dead_ig)} {IGNORE_FILE_NAME} MarkerIDs are absent from "
                   f"{snapshot.name} — reconcile has stopped skipping them: "
                   f"{', '.join(dead_ig[:10])}" + (" …" if len(dead_ig) > 10 else ""))
    return out


def run_check(args) -> None:
    atlas_path = Path(args.path)
    if not atlas_path.exists():
        raise SystemExit(f"atlas file not found: {atlas_path}")
    atlas = _load(atlas_path)

    ignore_path = (Path(args.ignore) if args.ignore
                   else atlas_path.parent / IGNORE_FILE_NAME)
    ignored = load_ignored_marker_ids(ignore_path)

    results: list[tuple[str, list[str]]] = [
        ("ignore list vs atlas refs", check_ignore_not_claimed_by_atlas(atlas, ignored)),
        ("memorial:website vs ref:hmdb", check_memorial_website_matches_ref(atlas)),
        ("duplicate THC groups", check_duplicate_thc_groups(atlas)),
    ]

    snapshot = Path(args.hmdb) if args.hmdb else None
    if snapshot and snapshot.exists():
        results.append(("references live on hmdb",
                        check_refs_live(atlas, ignored, snapshot)))
    else:
        print("[SKIP] references live on hmdb — pass --hmdb <snapshot.csv> to enable")

    failures = 0
    for label, problems in results:
        if problems:
            failures += len(problems)
            print(f"[FAIL] {label}: {len(problems)} issue(s)")
            for p in problems[:20]:
                print(f"  - {p}")
            if len(problems) > 20:
                print(f"  … and {len(problems) - 20} more")
        else:
            print(f"[OK]   {label}")

    print(f"\natlas rows: {len(atlas):,}   {IGNORE_FILE_NAME} entries: {len(ignored)}")
    if failures:
        sys.exit(1)


# --- guard used by the OSM push helpers -------------------------------------

FLOAT_ID = re.compile(r"^\d+\.0$|[?&]m=\d+\.0\b")


def assert_no_float_formatted_tags(tags: dict) -> None:
    """Reject pandas floats that would reach OSM as "202023.0".

    Reading an ID column without ``dtype=str`` turns it into a float, and the
    ".0" then rides into ``ref:hmdb`` and the ``memorial:website`` URL, leaving a
    dead link. Seven nodes carried exactly this before it was noticed.
    """
    bad = {k: v for k, v in tags.items() if v and FLOAT_ID.search(str(v))}
    if bad:
        raise ValueError(
            "float-formatted tag value(s) would be uploaded: "
            + ", ".join(f"{k}={v!r}" for k, v in sorted(bad.items()))
            + " — read ID columns with dtype=str")
