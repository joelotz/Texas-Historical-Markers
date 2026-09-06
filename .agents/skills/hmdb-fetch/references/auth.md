# HMDB authentication — what we learned

## TL;DR

HMDB's session cookie (`HistoricalMarkerDB=SessionID={GUID}&UserID=NNNN`)
gets set somewhere in the sign-in flow but **never via an HTTP
`Set-Cookie` header that raw `requests` can capture**. It only appears
after a real browser completes the sign-in form. Once present, the
cookie alone fully authenticates `requests`-driven calls.

So the architecture is hybrid:

* **Login** → `pythonLib/thc_toolkit/hmdb_login.js`: playwright-core
  driving the **headed** system Chrome with its own persistent profile
  (`~/.cache/thc-toolkit-hmdb-profile`). Run automatically by
  `thc hmdb fetch` (`hmdb_fetch.refresh_auth()`) when the cookie stops
  verifying, or on `--refresh-auth`.
* **Everything else** → `requests` with the cached cookie.

## 2026-09-06: Cloudflare, and why the login is headed and not the MCP

Two things changed since the June investigation:

1. **hmdb.org sits behind a Cloudflare managed challenge for browser
   sign-in.** A headless Chrome (playwright-core, any User-Agent, with or
   without `--disable-blink-features=AutomationControlled`) gets the "Just
   a moment..." interstitial on `mymarkers.asp` and `SignInProcess.asp`
   and it never clears (waited 60 s). The same script with
   `headless: false` on `DISPLAY=:1` clears the challenge in ~2 s and
   signs in. Plain `requests` GET/POST traffic with the toolkit UA is
   **not** challenged — the Results/ListsDownload path still works.
2. **The Playwright MCP browser profile is shared and single-instance.**
   `browser_navigate` fails with `Browser is already in use for
   ~/.cache/ms-playwright-mcp/mcp-chrome-<hash>` whenever another Claude
   session has the MCP browser open (it was: PID from a session started
   the previous evening). Killing another session's browser is not an
   option, and the MCP browser is headless anyway.

Hence the login script: it finds playwright-core in the npx cache the MCP
leaves behind (`~/.npm/_npx/*/node_modules/playwright-core`), launches
`/opt/google/chrome/chrome` headed with its own profile, fills the form
from `~/.config/thc-toolkit/hmdb.env`, follows the "One Moment Please"
autoclick chain until the `HistoricalMarkerDB` cookie shows up, and writes
`~/.config/thc-toolkit/hmdb.session`. On a second run the profile is
usually still signed in and the script reports "already signed in" without
touching the form. Never prints the password or cookie.

## Cookie lifetime

The June notes said "weeks". Observed on 2026-09-06: a cookie captured at
12:31 verified at 12:45 and failed by 13:17 (with the download in between).
Treat the cookie as short-lived and the auto-refresh as the normal path;
`thc hmdb fetch --check-auth` proves the path without a download.

## The probe that found the original cookie behaviour (2026-06-29)

1. `GET /signin.asp` directly → 403 ("can only be reached from within
   our website"). Need to come in via a redirector.
2. `GET /mymarkers.asp` (unauthenticated) → 200 with an autoclick form
   posting to `signin.asp`. No `Set-Cookie`.
3. `POST /signin.asp` with `autoclick=Click Here` → 200 with the real
   sign-in form. Still no `Set-Cookie`. Inputs: `Email`, `Password`,
   `ReturnToThisPage` (hidden), `ErrorMessage` (hidden), `autoclick`
   (hidden), `Submit` (`Sign In`).
4. `POST /signin.asp` with all of the above → 200, response body is
   another autoclick "One Moment Please" form that echoes the credentials
   back in hidden inputs. **Still no `Set-Cookie`.** Re-posting that
   chained form gives the same loop.

When the same sequence runs through a real browser, the cookie appears.
`document.cookie` after a successful login shows:

```
browserwidth=1221; HistoricalMarkerDB=SessionID=%7B...%7D&UserID=11117
```

Neither cookie is HttpOnly, but the `HistoricalMarkerDB` value isn't
constructed by any JS visible in the sign-in page's source. It originates
from the server, conditional on browser behaviours `requests` doesn't
exhibit. Reverse-engineering further would be brittle.

## Why the cookie alone is enough

Confirmed end-to-end with `requests.Session()`:

```python
s = requests.Session()
s.cookies.set("HistoricalMarkerDB", "SessionID={...}&UserID=11117",
              domain="www.hmdb.org", path="/")
# GET /mymarkers.asp → renders the actual My Markers page (no autoclick)
# GET /Results.asp?Search=State&State=Texas&u= → parseable marker-id list
# POST /ListsDownload.asp → CSV body, exact byte-for-byte match with
#   the file the browser's Download button produces
# GET /m.asp?m=<id> → also shows the user's own "Not Yet Published" pages,
#   which anonymous requests bounce to the ErrorReturn redirector
```

## Why we seed `browserwidth=1920`

The sign-in page's only inline JavaScript sets `browserwidth` via
`document.cookie` to `window.innerWidth`. Some HMDB endpoints behave
better when it's present. Cheap to seed; can't hurt.

## Why we hard-code a Firefox-ish User-Agent on the requests side

HMDB tolerates the default `python-requests/2.x` UA once authenticated,
but a consistent browser-shaped UA reduces the chance of a future edge
rule kicking us out. `hmdb_login.js` deliberately does **not** override
Chrome's own UA (a Firefox UA on a Chrome engine looked more suspicious
to Cloudflare, not less).

## Files

* `~/.config/thc-toolkit/hmdb.env` — `HMDB_EMAIL=...` / `HMDB_PASSWORD=...`
  read by `hmdb_login.js`. Mode 0600.
* `~/.config/thc-toolkit/hmdb.session` — single line:
  `HistoricalMarkerDB=SessionID={GUID}&UserID=NNNN`. Mode 0600.
* `~/.cache/thc-toolkit-hmdb-profile/` — the login script's Chrome
  profile (holds Cloudflare clearance + the hmdb session). Safe to delete.

All outside the repo and never enter the tree.
