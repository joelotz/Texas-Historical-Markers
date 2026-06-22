"""HMDB → atlas_db enrichment: identification and apply.

Two-phase workflow for syncing hmdb.org marker exports into the canonical
atlas_db.csv. See ``.agents/skills/hmdb-sync`` for the user-facing skill and
``hmdb.md`` at the project root for the strategy.

Phase 1 — ``thc hmdb reconcile`` (identification + auto-apply for exact matches):
    Filter the source CSV to official THC markers (fuzzy on ``Erected By``),
    restrict to rows whose ``Marker No.`` already exists in atlas as
    ``ref:US-TX:thc``, classify by hmdb-id state, and gate by title fuzzy
    match. Rows whose name normalizes identically (``name_similarity == 1.0``,
    which includes "The X" vs "X") are written straight into atlas with a
    backup; everything else goes to review CSVs:

        auto_applied.csv            — exact-name matches written to atlas
        review_candidates.csv       — fuzzy match passed (<1.0) — needs approval
        review_name_mismatches.csv  — title/name fuzzy match failed
        review_hmdb_conflicts.csv   — atlas already has a different ref:hmdb

Phase 2 — ``thc hmdb apply`` (writes to atlas):
    Read the dispositioned review CSVs, look up each approved row in the
    original hmdb export, and strict-overwrite ten enrichment fields on
    the matched atlas row. Writes a timestamped ``atlas_db.csv.bak.<ts>``
    backup first unless ``--no-backup`` is set.

Approval rule: a review row counts as approved if its ``approve`` cell,
uppercased and stripped, starts with ``YES``.
"""

from __future__ import annotations

import csv
import shutil
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
import re

# ----------------------------- reconcile ------------------------------------

THC_CANONICAL_PHRASES = (
    "texas historical commission",
    "texas state historical survey committee",
    "state historical survey committee",
    "state of texas",
)
THC_EXCLUSIONS = (
    "state of texas highway department",
    "state of texas, board of control",
)

THC_FUZZ_THRESHOLD = 0.85
NAME_FUZZ_THRESHOLD = 0.85

REVIEW_COLUMNS = [
    "ref:US-TX:thc",
    "hmdb_MarkerID",
    "hmdb_Title",
    "atlas_name",
    "name_similarity",
    "hmdb_Erected_By",
    "hmdb_City_or_Town",
    "atlas_addr_city",
    "hmdb_County_or_Parish",
    "atlas_addr_county",
    "hmdb_Missing",
    "hmdb_Link",
    "approve",
]
CONFLICT_EXTRA_COLUMN = "atlas_existing_ref:hmdb"


def normalize_phrase(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_name(s: str) -> str:
    s = normalize_phrase(s)
    if s.startswith("the "):
        s = s[4:]
    return s


def is_thc_erected_by(erected_by: str) -> bool:
    norm = normalize_phrase(erected_by)
    if not norm:
        return False
    if any(excl in norm for excl in THC_EXCLUSIONS):
        return False
    for canon in THC_CANONICAL_PHRASES:
        if canon in norm:
            return True
    norm_words = norm.split()
    for canon in THC_CANONICAL_PHRASES:
        canon_words = canon.split()
        if SequenceMatcher(None, canon, norm).ratio() >= THC_FUZZ_THRESHOLD:
            return True
        window_len = len(canon_words)
        if len(norm_words) >= window_len:
            for i in range(len(norm_words) - window_len + 1):
                window = " ".join(norm_words[i : i + window_len])
                if SequenceMatcher(None, canon, window).ratio() >= THC_FUZZ_THRESHOLD:
                    return True
    return False


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _load_atlas_by_thc(path: Path) -> dict[str, dict]:
    by_thc: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            thc = (row.get("ref:US-TX:thc") or "").strip()
            if thc:
                by_thc[thc] = row
    return by_thc


def _load_hmdb_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _load_hmdb_by_thc(path: Path) -> dict[str, dict]:
    by_thc: dict[str, dict] = {}
    for row in _load_hmdb_rows(path):
        thc = (row.get("Marker No.") or "").strip()
        if thc:
            by_thc[thc] = row
    return by_thc


def _review_row(hmdb_row: dict, atlas_row: dict | None, score: float) -> dict:
    return {
        "ref:US-TX:thc": (hmdb_row.get("Marker No.") or "").strip(),
        "hmdb_MarkerID": (hmdb_row.get("MarkerID") or "").strip(),
        "hmdb_Title": (hmdb_row.get("Title") or "").strip(),
        "atlas_name": (atlas_row.get("name") or "").strip() if atlas_row else "",
        "name_similarity": f"{score:.3f}",
        "hmdb_Erected_By": (hmdb_row.get("Erected By") or "").strip(),
        "hmdb_City_or_Town": (hmdb_row.get("City or Town") or "").strip(),
        "atlas_addr_city": (atlas_row.get("addr:city") or "").strip() if atlas_row else "",
        "hmdb_County_or_Parish": (hmdb_row.get("County or Parish") or "").strip(),
        "atlas_addr_county": (atlas_row.get("addr:county") or "").strip() if atlas_row else "",
        "hmdb_Missing": (hmdb_row.get("Missing") or "").strip(),
        "hmdb_Link": (hmdb_row.get("Link") or "").strip(),
        "approve": "",
    }


def _write_review(path: Path, rows: list[dict], extra_columns: tuple[str, ...] = ()) -> None:
    fieldnames = list(REVIEW_COLUMNS)
    for col in extra_columns:
        if col not in fieldnames:
            fieldnames.insert(fieldnames.index("approve"), col)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


NAME_AUTO_APPLY_THRESHOLD = 1.0


def reconcile(
    hmdb_path: Path,
    atlas_path: Path,
    out_dir: Path,
    make_backup: bool = True,
) -> dict:
    """Identify hmdb rows for atlas enrichment.

    Rows that match an atlas THC# with an identical normalized name
    (``name_similarity == 1.0``, which includes "The X" vs "X") are
    written straight to atlas with a backup. Lower-confidence matches
    and conflicts go to review CSVs for human disposition.
    """
    hmdb_rows = _load_hmdb_rows(hmdb_path)
    atlas_by_thc = _load_atlas_by_thc(atlas_path)

    stats = {
        "hmdb_total": len(hmdb_rows),
        "thc_filter_pass": 0,
        "thc_in_atlas": 0,
        "already_documented": 0,
        "auto_applied": 0,
        "candidates": 0,
        "name_mismatches": 0,
        "conflicts": 0,
        "backup_path": None,
    }

    auto_applied_rows: list[dict] = []
    candidates: list[dict] = []
    name_mismatches: list[dict] = []
    conflicts: list[dict] = []
    auto_hmdb_by_thc: dict[str, dict] = {}

    for hmdb_row in hmdb_rows:
        if not is_thc_erected_by(hmdb_row.get("Erected By") or ""):
            continue
        stats["thc_filter_pass"] += 1

        thc = (hmdb_row.get("Marker No.") or "").strip()
        if not thc or thc not in atlas_by_thc:
            continue
        stats["thc_in_atlas"] += 1

        atlas_row = atlas_by_thc[thc]
        atlas_hmdb = (atlas_row.get("ref:hmdb") or "").strip()
        hmdb_id = (hmdb_row.get("MarkerID") or "").strip()
        score = name_similarity(hmdb_row.get("Title") or "", atlas_row.get("name") or "")

        if atlas_hmdb and atlas_hmdb == hmdb_id:
            stats["already_documented"] += 1
            continue

        if atlas_hmdb and atlas_hmdb != hmdb_id:
            conflict = _review_row(hmdb_row, atlas_row, score)
            conflict[CONFLICT_EXTRA_COLUMN] = atlas_hmdb
            conflicts.append(conflict)
            stats["conflicts"] += 1
            continue

        review = _review_row(hmdb_row, atlas_row, score)
        if score >= NAME_AUTO_APPLY_THRESHOLD:
            review["approve"] = "YES (auto)"
            auto_applied_rows.append(review)
            auto_hmdb_by_thc[thc] = hmdb_row
            stats["auto_applied"] += 1
        elif score >= NAME_FUZZ_THRESHOLD:
            candidates.append(review)
            stats["candidates"] += 1
        else:
            name_mismatches.append(review)
            stats["name_mismatches"] += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_review(out_dir / "auto_applied.csv", auto_applied_rows)
    _write_review(out_dir / "review_candidates.csv", candidates)
    _write_review(out_dir / "review_name_mismatches.csv", name_mismatches)
    _write_review(out_dir / "review_hmdb_conflicts.csv", conflicts, (CONFLICT_EXTRA_COLUMN,))

    if auto_hmdb_by_thc:
        write_result = _write_atlas_enrichment(
            atlas_path,
            auto_hmdb_by_thc,
            set(auto_hmdb_by_thc),
            make_backup=make_backup,
        )
        stats["backup_path"] = (
            str(write_result["backup_path"]) if write_result["backup_path"] else None
        )

    return stats


# ------------------------------- apply --------------------------------------

REVIEW_FILES_TO_APPLY = ("review_candidates.csv", "review_name_mismatches.csv")
MISSING_FLAGS = {"reported missing", "confirmed missing"}

ENRICHMENT_FIELDS = (
    "ref:hmdb",
    "memorial:website",
    "isHMDB",
    "isMissing",
    "isPending",
    "addr:full",
    "addr:city",
    "hmdb:Latitude",
    "hmdb:Longitude",
    "Marker Notes",
)


def is_approved(cell: str) -> bool:
    return (cell or "").strip().upper().startswith("YES")


def _collect_approved_thc_ids(review_dir: Path) -> set[str]:
    approved: set[str] = set()
    for name in REVIEW_FILES_TO_APPLY:
        path = review_dir / name
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if is_approved(row.get("approve", "")):
                    thc = (row.get("ref:US-TX:thc") or "").strip()
                    if thc:
                        approved.add(thc)
    return approved


def _hmdb_to_enrichment(hmdb_row: dict) -> dict[str, str]:
    missing_flag = (hmdb_row.get("Missing") or "").strip().lower()
    return {
        "ref:hmdb": (hmdb_row.get("MarkerID") or "").strip(),
        "memorial:website": (hmdb_row.get("Link") or "").strip(),
        "isHMDB": "True",
        "isMissing": "True" if missing_flag in MISSING_FLAGS else "False",
        "isPending": "False",
        "addr:full": (hmdb_row.get("Street Address") or "").strip(),
        "addr:city": (hmdb_row.get("City or Town") or "").strip(),
        "hmdb:Latitude": (hmdb_row.get("Latitude (minus=S)") or "").strip(),
        "hmdb:Longitude": (hmdb_row.get("Longitude (minus=W)") or "").strip(),
        "Marker Notes": "",
    }


def _write_atlas_enrichment(
    atlas_path: Path,
    hmdb_by_thc: dict[str, dict],
    thc_ids: set[str],
    make_backup: bool,
) -> dict:
    """Strict-overwrite ENRICHMENT_FIELDS on atlas rows whose ref:US-TX:thc is in thc_ids.

    Requires every id in ``thc_ids`` to be present in ``hmdb_by_thc``.
    Backs up atlas before writing unless ``make_backup`` is False, then
    skips the rewrite entirely if no rows were touched.
    """
    missing_in_hmdb = [t for t in thc_ids if t not in hmdb_by_thc]
    if missing_in_hmdb:
        raise SystemExit(
            f"ERROR: requested THC IDs missing from hmdb data: {missing_in_hmdb}"
        )

    with atlas_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    missing_fields = [f for f in ENRICHMENT_FIELDS if f not in fieldnames]
    if missing_fields:
        raise SystemExit(
            f"ERROR: atlas is missing expected columns: {missing_fields}"
        )

    updated_ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        thc = (row.get("ref:US-TX:thc") or "").strip()
        if thc not in thc_ids:
            continue
        seen.add(thc)
        for k, v in _hmdb_to_enrichment(hmdb_by_thc[thc]).items():
            row[k] = v
        updated_ids.append(thc)

    backup_path: Path | None = None
    if updated_ids and make_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = atlas_path.with_suffix(atlas_path.suffix + f".bak.{ts}")
        shutil.copy2(atlas_path, backup_path)

    if updated_ids:
        with atlas_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    return {
        "backup_path": backup_path,
        "updated_ids": updated_ids,
        "not_in_atlas": sorted(set(thc_ids) - seen),
    }


def apply_updates(
    atlas_path: Path,
    hmdb_path: Path,
    review_dir: Path,
    make_backup: bool = True,
) -> dict:
    approved = _collect_approved_thc_ids(review_dir)
    hmdb_by_thc = _load_hmdb_by_thc(hmdb_path)

    result = _write_atlas_enrichment(
        atlas_path, hmdb_by_thc, approved, make_backup=make_backup
    )

    if result["not_in_atlas"]:
        print(
            f"WARNING: approved THC IDs not found in atlas: {result['not_in_atlas']}",
            file=sys.stderr,
        )

    return {
        "approved": len(approved),
        "updated": len(result["updated_ids"]),
        "not_in_atlas": len(result["not_in_atlas"]),
        "updated_ids": result["updated_ids"],
        "backup_path": str(result["backup_path"]) if result["backup_path"] else None,
    }


# -------------------------------- CLI ---------------------------------------


def run_reconcile(args) -> None:
    stats = reconcile(
        Path(args.hmdb),
        Path(args.atlas),
        Path(args.out_dir),
        make_backup=not getattr(args, "no_backup", False),
    )
    print(f"hmdb rows read         : {stats['hmdb_total']}")
    print(f"  passed THC filter    : {stats['thc_filter_pass']}")
    print(f"  with THC# in atlas   : {stats['thc_in_atlas']}")
    print(f"    already documented : {stats['already_documented']}")
    print(f"    auto-applied       : {stats['auto_applied']}    → {args.out_dir}/auto_applied.csv")
    print(f"    candidates         : {stats['candidates']}    → {args.out_dir}/review_candidates.csv")
    print(f"    name mismatches    : {stats['name_mismatches']}    → {args.out_dir}/review_name_mismatches.csv")
    print(f"    hmdb conflicts     : {stats['conflicts']}    → {args.out_dir}/review_hmdb_conflicts.csv")
    if stats["backup_path"]:
        print(f"Backup written         : {stats['backup_path']}")


def run_apply(args) -> None:
    result = apply_updates(
        atlas_path=Path(args.atlas),
        hmdb_path=Path(args.hmdb),
        review_dir=Path(args.review_dir),
        make_backup=not args.no_backup,
    )
    if result["backup_path"]:
        print(f"Backup written: {result['backup_path']}")
    print(f"Approved rows           : {result['approved']}")
    print(f"Atlas rows updated      : {result['updated']}")
    print(f"Approved but not in atlas: {result['not_in_atlas']}")
    if result["updated_ids"]:
        print("Updated THC IDs:")
        for t in result["updated_ids"]:
            print(f"  {t}")
