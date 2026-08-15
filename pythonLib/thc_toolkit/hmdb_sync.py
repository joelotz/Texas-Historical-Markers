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
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from html import unescape
from pathlib import Path
import re

# ----------------------------- reconcile ------------------------------------

THC_CANONICAL_PHRASES = (
    "texas historical commission",
    "texas state historical survey committee",
    "state historical survey committee",
    "state of texas",
)
# All exclusion phrases MUST be pre-normalized (lowercase, punctuation
# stripped, single-space) because they are matched against the output of
# normalize_phrase(). A literal comma in an exclusion never matches.
THC_EXCLUSIONS = (
    "state of texas highway department",
    "state of texas board of control",
    # DAR co-sponsored markers (any "Daughters of the American Revolution"
    # variant, including "(DAR)" abbreviation and trailing "A.D. <year>")
    "daughters of the american revolution",
    # Civic groups that paid for a State of Texas-cast marker
    "la plata study club",
    # County-level historical survey committees aren't the state THC
    "mcculloch county historical survey committee",
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


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(s: str) -> str:
    """Drop HTML markup hmdb leaves in free-text fields.

    hmdb exports carry raw markup in ``Title`` and ``Erected By`` — e.g.
    ``<i>El Colegio Altamirano</i>`` or an unbalanced trailing ``</small>``.
    Left in place the tags survive ``normalize_phrase`` as bare word
    characters (``<i>`` becomes the token ``i``), which drags name
    similarity below the auto-apply threshold for otherwise identical names.
    """
    return _HTML_TAG_RE.sub("", unescape(s or "")).strip()


def normalize_phrase(s: str) -> str:
    s = strip_html(s).lower()
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


def _group_atlas_by_thc(rows: list[dict]) -> dict[str, list[dict]]:
    """Index atlas rows by THC number, keeping every row under that number.

    A THC number can legitimately carry more than one atlas row: hmdb
    sometimes catalogs two entries for what are really two separate
    physical markers sharing a Marker No. Indexing to a single row would
    hide all but the last one.
    """
    by_thc: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        thc = (row.get("ref:US-TX:thc") or "").strip()
        if thc:
            by_thc[thc].append(row)
    return dict(by_thc)


def _load_atlas_by_thc(path: Path) -> dict[str, list[dict]]:
    with path.open(newline="", encoding="utf-8") as f:
        return _group_atlas_by_thc(list(csv.DictReader(f)))


def _resolve_atlas_row(
    atlas_rows: list[dict], hmdb_id: str, claimed: set[int] | None = None
) -> tuple[dict, str]:
    """Decide which row of a THC group a given hmdb entry belongs to.

    Returns ``(row, disposition)`` where disposition is:

    ``documented``
        A row already carries this exact MarkerID — nothing to do.
    ``open``
        No row carries it, but one has an empty ``ref:hmdb`` and is free
        to take it.
    ``conflict``
        Every row carries some other MarkerID, so a human must decide.

    ``claimed`` holds ``id()`` values of rows already spoken for earlier
    in the same pass, so two hmdb entries cannot both take one blank row.
    """
    for row in atlas_rows:
        if (row.get("ref:hmdb") or "").strip() == hmdb_id:
            return row, "documented"
    for row in atlas_rows:
        if (row.get("ref:hmdb") or "").strip():
            continue
        if claimed is not None and id(row) in claimed:
            continue
        return row, "open"
    return atlas_rows[0], "conflict"


def _load_hmdb_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _load_hmdb_by_id(path: Path) -> dict[str, dict]:
    """Index hmdb rows by MarkerID.

    Deliberately not by ``Marker No.``: hmdb can carry several entries
    under one Marker No., so that index would collapse them and hand back
    an arbitrary one. MarkerID is the only unique key.
    """
    by_id: dict[str, dict] = {}
    for row in _load_hmdb_rows(path):
        marker_id = (row.get("MarkerID") or "").strip()
        if marker_id:
            by_id[marker_id] = row
    return by_id


def _review_row(hmdb_row: dict, atlas_row: dict | None, score: float) -> dict:
    return {
        "ref:US-TX:thc": (hmdb_row.get("Marker No.") or "").strip(),
        "hmdb_MarkerID": (hmdb_row.get("MarkerID") or "").strip(),
        "hmdb_Title": strip_html(hmdb_row.get("Title") or ""),
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
    ignore_path: Path | None = None,
) -> dict:
    """Identify hmdb rows for atlas enrichment.

    Rows that match an atlas THC# with an identical normalized name
    (``name_similarity == 1.0``, which includes "The X" vs "X") are
    written straight to atlas with a backup. Lower-confidence matches
    and conflicts go to review CSVs for human disposition.
    """
    hmdb_rows = _load_hmdb_rows(hmdb_path)
    atlas_by_thc = _load_atlas_by_thc(atlas_path)
    if ignore_path is None:
        ignore_path = atlas_path.parent / IGNORE_FILE_NAME
    ignored = load_ignored_marker_ids(ignore_path)

    stats = {
        "hmdb_total": len(hmdb_rows),
        "ignored": 0,
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
    claimed: set[int] = set()

    for hmdb_row in hmdb_rows:
        if not is_thc_erected_by(hmdb_row.get("Erected By") or ""):
            continue
        stats["thc_filter_pass"] += 1

        # A known duplicate page. Skipped before classification so it cannot
        # resurface as a conflict or candidate on every pull.
        if (hmdb_row.get("MarkerID") or "").strip() in ignored:
            stats["ignored"] += 1
            continue

        thc = (hmdb_row.get("Marker No.") or "").strip()
        if not thc or thc not in atlas_by_thc:
            continue
        stats["thc_in_atlas"] += 1

        atlas_rows = atlas_by_thc[thc]
        hmdb_id = (hmdb_row.get("MarkerID") or "").strip()
        atlas_row, disposition = _resolve_atlas_row(atlas_rows, hmdb_id, claimed)
        score = name_similarity(hmdb_row.get("Title") or "", atlas_row.get("name") or "")

        if disposition == "documented":
            stats["already_documented"] += 1
            continue

        # Every row under this THC# already points somewhere else, or the one
        # free row was taken by an earlier hmdb entry in this same pass.
        if disposition == "conflict" or thc in auto_hmdb_by_thc:
            conflict = _review_row(hmdb_row, atlas_row, score)
            conflict[CONFLICT_EXTRA_COLUMN] = "; ".join(
                sorted(
                    {
                        ref
                        for r in atlas_rows
                        if (ref := (r.get("ref:hmdb") or "").strip())
                    }
                )
            )
            conflicts.append(conflict)
            stats["conflicts"] += 1
            continue

        claimed.add(id(atlas_row))
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
            list(auto_hmdb_by_thc.items()),
            make_backup=make_backup,
        )
        stats["backup_path"] = (
            str(write_result["backup_path"]) if write_result["backup_path"] else None
        )

    return stats


# ------------------------------- apply --------------------------------------

REVIEW_FILES_TO_APPLY = ("review_candidates.csv", "review_name_mismatches.csv")
MISSING_FLAGS = {"reported missing", "confirmed missing"}
IGNORE_FILE_NAME = "hmdb_ignore.csv"


def load_ignored_marker_ids(path: Path | None) -> set[str]:
    """MarkerIDs recorded as duplicate hmdb pages, to be skipped on reconcile.

    hmdb sometimes carries a second page for a marker the atlas already
    documents. Absorbing each into an extra atlas row made ``ref:US-TX:thc``
    non-unique; recording them here keeps one row per marker instead.

    Keyed on MarkerID, never ``Marker No.`` -- hmdb typos that field, so the
    same entry can be filed under a number belonging to a different marker.
    A missing file is not an error; it just means nothing is ignored.
    """
    if path is None or not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as f:
        return {
            marker_id
            for row in csv.DictReader(f)
            if (marker_id := (row.get("hmdb_MarkerID") or "").strip())
        }

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


def _collect_approved(review_dir: Path) -> list[tuple[str, str]]:
    """Return approved ``(thc, hmdb_MarkerID)`` pairs, in file order.

    The MarkerID matters: a review file can approve a specific hmdb entry
    under a Marker No. that carries several, and only the MarkerID says
    which one the human meant.
    """
    approved: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for name in REVIEW_FILES_TO_APPLY:
        path = review_dir / name
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not is_approved(row.get("approve", "")):
                    continue
                thc = (row.get("ref:US-TX:thc") or "").strip()
                marker_id = (row.get("hmdb_MarkerID") or "").strip()
                if thc and marker_id and (thc, marker_id) not in seen:
                    seen.add((thc, marker_id))
                    approved.append((thc, marker_id))
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
    targets: list[tuple[str, dict]],
    make_backup: bool,
) -> dict:
    """Strict-overwrite ENRICHMENT_FIELDS for each ``(thc, hmdb_row)`` target.

    Each target enriches exactly one atlas row — the one already carrying
    that MarkerID, else a free row under the same THC#. Backs up atlas
    before writing unless ``make_backup`` is False, then skips the rewrite
    entirely if no rows were touched.
    """
    with atlas_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    missing_fields = [f for f in ENRICHMENT_FIELDS if f not in fieldnames]
    if missing_fields:
        raise SystemExit(
            f"ERROR: atlas is missing expected columns: {missing_fields}"
        )

    # A THC# can cover several atlas rows (two physical markers sharing a
    # Marker No.). Enrich only the row this hmdb entry actually refers to,
    # never the whole group — that would overwrite the sibling's ref:hmdb.
    rows_by_thc = _group_atlas_by_thc(rows)

    updated_ids: list[str] = []
    not_in_atlas: list[str] = []
    claimed: set[int] = set()
    for thc, hmdb_row in targets:
        group = rows_by_thc.get(thc)
        if not group:
            not_in_atlas.append(thc)
            continue
        target, _ = _resolve_atlas_row(
            group, (hmdb_row.get("MarkerID") or "").strip(), claimed
        )
        claimed.add(id(target))
        for k, v in _hmdb_to_enrichment(hmdb_row).items():
            target[k] = v
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
        "not_in_atlas": sorted(set(not_in_atlas)),
    }


def apply_updates(
    atlas_path: Path,
    hmdb_path: Path,
    review_dir: Path,
    make_backup: bool = True,
) -> dict:
    approved = _collect_approved(review_dir)
    hmdb_by_id = _load_hmdb_by_id(hmdb_path)

    missing = sorted({mid for _, mid in approved if mid not in hmdb_by_id})
    if missing:
        raise SystemExit(
            f"ERROR: approved hmdb MarkerIDs missing from hmdb data: {missing}"
        )

    result = _write_atlas_enrichment(
        atlas_path,
        [(thc, hmdb_by_id[mid]) for thc, mid in approved],
        make_backup=make_backup,
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
    print(f"  skipped as duplicate : {stats['ignored']}    ← {IGNORE_FILE_NAME}")
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
