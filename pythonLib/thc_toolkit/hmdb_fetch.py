"""Download hmdb.org marker-list CSV exports without a browser.

Mirrors what the website's "Download" button does on a Results.asp page:

  1. GET the Results.asp listing page; parse the hidden ``markers`` field
     (a comma-separated list of every marker ID in the listing).
  2. POST those IDs to ListsDownload.asp; the body of the response IS the
     CSV file (Content-Disposition exposes the suggested filename).

Authentication: HMDB's sign-in dance sets a session cookie through a
browser-only path we can't fully replay with raw HTTP (likely TLS/header
fingerprinting or a JS-set precondition). So this module reads a
pre-captured session cookie from disk and reuses it. The cookie persists
server-side for weeks (classic ASP session). When it expires, refresh it
through the ``hmdb-fetch`` agent skill, which drives a Playwright browser
through the login and writes a fresh cookie file.

Cookie file format (default ~/.config/thc-toolkit/hmdb.session)::

    HistoricalMarkerDB=SessionID={GUID}&UserID=NNNN

One line, the literal value of the ``Cookie`` header. Mode 0600 recommended.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests

BASE = "https://www.hmdb.org"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0 "
    "(thc-toolkit/0.1; joelotz@gmail.com)"
)
DEFAULT_COOKIE_PATH = "~/.config/thc-toolkit/hmdb.session"

# Hidden inputs on the Results.asp page. HMDB's HTML uses single quotes
# around values (and rarely whitespace around `=`), so we tolerate both.
_MARKERS_RE = re.compile(
    r"""name\s*=\s*['"]?markers['"]?\s+value\s*=\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(
    r"""name\s*=\s*['"]?markercount['"]?\s+value\s*=\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(
    r"""name\s*=\s*['"]?title['"]?\s+value\s*=\s*['"]([^'"]*)['"]""",
    re.IGNORECASE,
)
_FILENAME_RE = re.compile(r'filename="?([^";]+)"?', re.IGNORECASE)


class AuthExpired(SystemExit):
    """Raised when the cached cookie no longer authenticates."""


def _load_cookie(cookie_path: str | os.PathLike | None) -> tuple[str, str]:
    """Read the cookie file. Returns (name, value) for requests.cookies.set."""
    path = Path(cookie_path or DEFAULT_COOKIE_PATH).expanduser()
    if not path.exists():
        raise SystemExit(
            f"No HMDB session cookie at {path}. Run the hmdb-fetch skill "
            "with `refresh-auth` to log in via browser and create it."
        )
    raw = path.read_text().strip()
    # Accept either "Name=Value" or just "Value" (assume HistoricalMarkerDB)
    if "=" not in raw:
        raise SystemExit(
            f"Malformed cookie file {path}: expected 'Name=Value' line"
        )
    name, value = raw.split("=", 1)
    return name.strip(), value.strip()


def make_session(
    cookie_path: str | os.PathLike | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> requests.Session:
    """Build a session pre-loaded with the cached HMDB cookie."""
    name, value = _load_cookie(cookie_path)
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent})
    s.cookies.set(name, value, domain="www.hmdb.org", path="/")
    # browserwidth is set by HMDB JS in a real browser; some endpoints
    # behave better when it's present. Harmless to seed.
    s.cookies.set("browserwidth", "1920", domain="www.hmdb.org", path="/")
    return s


def verify_session(session: requests.Session) -> None:
    """Confirm the cookie still authenticates; raise AuthExpired otherwise."""
    r = session.get(f"{BASE}/mymarkers.asp", timeout=30, allow_redirects=True)
    r.raise_for_status()
    # When logged out, mymarkers.asp returns the autoclick redirector to
    # signin.asp; when logged in, the actual My Markers page renders.
    if "ErrorReturn" in r.text or "Sign In" in (r.text[:5000] or ""):
        raise AuthExpired(
            "HMDB session cookie is no longer valid. Refresh it by running "
            "the hmdb-fetch skill with `refresh-auth`."
        )


def fetch_state_listing(
    session: requests.Session, state: str = "Texas"
) -> tuple[str, str, str]:
    """Return (markers_csv_ids, markercount, title) for a state listing."""
    url = f"{BASE}/Results.asp?Search=State&State={state}&u="
    r = session.get(url, timeout=60)
    r.raise_for_status()
    html = r.text
    m = _MARKERS_RE.search(html)
    c = _COUNT_RE.search(html)
    t = _TITLE_RE.search(html)
    if not (m and c):
        raise SystemExit(
            "Could not locate hidden 'markers'/'markercount' fields on the "
            f"Results page for state={state}. The site layout may have "
            "changed; investigate Results.asp HTML."
        )
    return m.group(1), c.group(1), (
        t.group(1) if t
        else f"Historical Markers and War Memorials in {state}"
    )


def download_csv(
    session: requests.Session,
    markers: str,
    markercount: str,
    title: str,
    out_dir: str | os.PathLike = ".",
    filename: str | None = None,
) -> Path:
    """POST to ListsDownload.asp; write the response body verbatim."""
    r = session.post(
        f"{BASE}/ListsDownload.asp",
        data={"markers": markers, "markercount": markercount, "title": title},
        timeout=120,
    )
    r.raise_for_status()
    if filename is None:
        cd = r.headers.get("Content-Disposition", "")
        m = _FILENAME_RE.search(cd)
        filename = m.group(1) if m else (
            f"HMdb-Entries-{date.today().strftime('%Y%m%d')}.csv"
        )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_bytes(r.content)
    return path


def run_fetch(args) -> None:
    session = make_session(cookie_path=args.cookie)
    print(f"[INFO] verifying cookie")
    verify_session(session)
    print(f"[INFO] cookie OK; fetching state listing for {args.state}")
    markers, count, title = fetch_state_listing(session, state=args.state)
    print(f"[INFO] state listing returned {count} marker IDs "
          f"({len(markers)} bytes of IDs)")
    print(f"[INFO] requesting CSV download")
    path = download_csv(
        session,
        markers=markers,
        markercount=count,
        title=title,
        out_dir=args.out_dir,
        filename=args.out_file,
    )
    size_kb = path.stat().st_size / 1024
    print(f"[OK] wrote {path} ({size_kb:.1f} KB)")


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="thc hmdb fetch",
        description="Download an hmdb.org state-listing CSV without a "
        "browser, using a cached session cookie.",
    )
    ap.add_argument(
        "--state", default="Texas", help="State name (default: Texas)"
    )
    ap.add_argument(
        "--out-dir",
        default="data_files",
        help="Directory to write the downloaded CSV into "
        "(default: data_files)",
    )
    ap.add_argument(
        "--out-file",
        default=None,
        help="Override output filename (default: server-supplied name)",
    )
    ap.add_argument(
        "--cookie",
        default=None,
        help=f"Session cookie file (default: {DEFAULT_COOKIE_PATH})",
    )
    args = ap.parse_args()
    run_fetch(args)


if __name__ == "__main__":
    main()
