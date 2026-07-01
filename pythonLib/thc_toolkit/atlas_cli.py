"""Atlas encoding integrity: validate and repair.

Guards against the LibreOffice CSV round-trip corruption where opening
atlas_db.csv with a non-UTF-8 default encoding (ISO-8859-1 / cp1252) and
saving it back silently re-encodes every multi-byte character as
mojibake at the byte level.

`validate` is the read-only check used by the pre-commit hook. It
fails fast on:
  * bytes that aren't valid UTF-8 anywhere in the file, OR
  * any CRLF line ending (should be LF).

`repair` fixes both classes of drift in place, backing up first. Each
line is decoded as UTF-8; on failure it falls back to cp1252 then
latin-1 (latin-1 has all 256 byte values defined, so decoding always
succeeds). CRLFs are normalized to LF. Reports which lines needed
fallback so the human can spot-check that no characters were lost.
"""
from __future__ import annotations
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
    if errors:
        print(f"[FAIL] {path}: {len(errors)} issue(s)")
        for e in errors:
            print(f"  - {e}")
        print(f"  fix with: thc atlas repair --path {path}")
        sys.exit(1)
    print(f"[OK] {path}: UTF-8 clean, LF-only "
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
