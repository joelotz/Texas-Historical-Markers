"""Atlas encoding integrity: validate and repair.

Guards against the LibreOffice CSV round-trip corruption where opening
atlas_db.csv with a non-UTF-8 default encoding (ISO-8859-1 / cp1252) and
saving it back silently re-encodes every multi-byte character as
mojibake at the byte level.

`validate` is the read-only check used by the pre-commit hook. It
fails fast on:
  * bytes that aren't valid UTF-8 anywhere in the file, OR
  * any CRLF line ending (should be LF), OR
  * any row whose column count differs from the header's.

The column check exists because a spreadsheet save-back can append empty
trailing columns to the header and every row -- 2026-08-22 it turned 33
columns into 43 across all 17,516 rows. That shifts cell content sideways:
two hand-typed marker inscriptions ended up outside `Marker Text`, one of
them in the tenth phantom column where it read as simply missing. Encoding
and line endings were both pristine, so the file passed validate.

`repair` fixes both classes of drift in place, backing up first. Each
line is decoded as UTF-8; on failure it falls back to cp1252 then
latin-1 (latin-1 has all 256 byte values defined, so decoding always
succeeds). CRLFs are normalized to LF. Reports which lines needed
fallback so the human can spot-check that no characters were lost.
"""
from __future__ import annotations
import csv
import io
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

DEFAULT_ATLAS = "atlas_db.csv"


def _read_bytes_or_die(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        raise SystemExit(f"atlas file not found: {path}")


def _scan(raw: bytes) -> dict:
    """Return dict with utf8_ok, crlf_count, bad_line_numbers (up to 20)."""
    utf8_ok = True
    utf8_first_bad = None
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        utf8_ok = False
        utf8_first_bad = e.start
    crlf_count = raw.count(b"\r\n")
    return {
        "utf8_ok": utf8_ok,
        "utf8_first_bad_byte": utf8_first_bad,
        "crlf_count": crlf_count,
        "total_bytes": len(raw),
    }


def _scan_widths(raw: bytes) -> dict:
    """Header width, and the rows that disagree with it.

    Parsed with the csv module rather than by splitting on commas, so that
    quoted fields containing commas or embedded newlines are counted
    correctly -- Marker Text routinely holds both.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {}                      # the UTF-8 error is the useful one; report that first
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        return {"header_width": 0, "bad_rows": [], "n_rows": 0}
    width = len(header)
    bad, n = [], 0
    for i, row in enumerate(reader, start=2):   # line 1 is the header
        n += 1
        if len(row) != width:
            if len(bad) < 20:
                bad.append((i, len(row)))
    trailing_blank = 0
    for name in reversed(header):
        if name.strip():
            break
        trailing_blank += 1
    return {"header_width": width, "bad_rows": bad, "n_rows": n,
            "trailing_blank_header_cols": trailing_blank}


def run_validate(args) -> None:
    path = Path(args.path)
    raw = _read_bytes_or_die(path)
    info = _scan(raw)
    errors = []
    if not info["utf8_ok"]:
        errors.append(
            f"non-UTF-8 byte at offset {info['utf8_first_bad_byte']} "
            f"(likely cp1252/latin-1 contamination — probably a "
            f"LibreOffice save)"
        )
    if info["crlf_count"] > 0:
        errors.append(
            f"{info['crlf_count']} CRLF line endings found (expected LF)"
        )

    widths = _scan_widths(raw)
    blank = widths.get("trailing_blank_header_cols", 0)
    if blank:
        errors.append(
            f"{blank} unnamed trailing column(s) in the header "
            f"(width {widths['header_width']}) — a spreadsheet save-back "
            f"appended them; cell content may have shifted sideways, so "
            f"check that nothing landed outside its column before stripping"
        )
    if widths.get("bad_rows"):
        shown = ", ".join(f"line {ln} has {w}" for ln, w in widths["bad_rows"][:5])
        more = "" if len(widths["bad_rows"]) <= 5 else f" (+{len(widths['bad_rows']) - 5} more)"
        errors.append(
            f"{len(widths['bad_rows'])} row(s) do not match the header width "
            f"of {widths['header_width']}: {shown}{more}"
        )

    if errors:
        print(f"[FAIL] {path}: {len(errors)} issue(s)")
        for e in errors:
            print(f"  - {e}")
        # `repair` only rewrites encoding and line endings. Pointing a width
        # problem at it would be worse than useless: the fix there is to find
        # where the shifted content went and put it back, by hand.
        if not info["utf8_ok"] or info["crlf_count"]:
            print(f"  fix encoding/line endings with: thc atlas repair --path {path}")
        if widths.get("bad_rows") or blank:
            print("  column-width problems are NOT repairable automatically — "
                  "content may have shifted sideways. Find where it went "
                  "before removing anything.")
        sys.exit(1)
    print(f"[OK] {path}: UTF-8 clean, LF-only, "
          f"{widths['header_width']} columns across {widths['n_rows']:,} rows "
          f"({info['total_bytes']:,} bytes)")


def run_repair(args) -> None:
    path = Path(args.path)
    raw = _read_bytes_or_die(path)
    info = _scan(raw)
    if info["utf8_ok"] and info["crlf_count"] == 0:
        print(f"[OK] {path}: already clean, nothing to do")
        return

    if not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_suffix(f"{path.suffix}.preencoding.bak.{ts}")
        shutil.copy2(path, backup)
        print(f"[OK] backup → {backup.name}")

    lines = raw.split(b"\n")
    out_lines: list[str] = []
    fallbacks: list[tuple[int, str, str]] = []
    crlf_normalized = 0
    for i, b in enumerate(lines):
        if b.endswith(b"\r"):
            crlf_normalized += 1
            b = b[:-1]
        try:
            s = b.decode("utf-8")
            used = "utf-8"
        except UnicodeDecodeError:
            try:
                s = b.decode("cp1252")
                used = "cp1252"
            except UnicodeDecodeError:
                s = b.decode("latin-1")
                used = "latin-1"
            fallbacks.append((i + 1, used, s))
        out_lines.append(s)

    out = "\n".join(out_lines).encode("utf-8")
    # Sanity check: result must round-trip as UTF-8
    out.decode("utf-8")
    path.write_bytes(out)
    print(f"[OK] rewrote {path} as canonical UTF-8 / LF")
    print(f"     CRLF→LF: {crlf_normalized}")
    print(f"     cp1252/latin-1 fallback lines: {len(fallbacks)}")
    if fallbacks and args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w") as rf:
            rf.write(f"encoding-repair report for {path}\n")
            rf.write(f"CRLF→LF: {crlf_normalized}\n")
            rf.write(f"fallback lines: {len(fallbacks)}\n")
            rf.write(
                f"fallback breakdown: "
                f"{dict(Counter(u for _, u, _ in fallbacks))}\n\n"
            )
            for ln, used, content in fallbacks:
                rf.write(f"line {ln} [{used}]: {content[:300]}\n")
        print(f"[OK] wrote {report_path}")
