---
name: hmdb-fetch
description: Download the fresh hmdb.org Texas marker CSV without a browser, using a cached session cookie that `thc hmdb fetch` now refreshes by itself (headed Chrome login) when it has expired. Use when the user asks to pull / refresh / re-download hmdb data, or as step 1 of the hmdb-update skill. Nothing to do by hand for auth any more unless the automatic login fails.
---

# HMDB → CSV fetch

Downloads `HMdb-Entries-<State>-YYYYMMDD.csv` from hmdb.org by replaying
what its Results-page "Download" button does:

1. GET `Results.asp?Search=State&State=<State>&u=` — the server returns
   an HTML page whose hidden form field carries every marker ID for the
   state in one comma-separated list (~120KB for Texas).
2. POST those IDs to `ListsDownload.asp` — the response body IS the CSV.

The Python lives in `pythonLib/thc_toolkit/hmdb_fetch.py`, the browser
login in `pythonLib/thc_toolkit/hmdb_login.js`, wired into the unified CLI
as `thc hmdb fetch`.

## Read first

See [references/auth.md](references/auth.md) for the auth model. The short
version: HMDB sets the session cookie only through a real browser sign-in,
and since 2026-09 its Cloudflare challenge blocks headless browsers. So the
CLI keeps a cached cookie at `~/.config/thc-toolkit/hmdb.session` and, when
it stops verifying, re-logs in through a **headed** system Chrome on the
user's X display (`hmdb_login.js`, own persistent profile, credentials
from `~/.config/thc-toolkit/hmdb.env`). The window appears for a few
seconds and closes itself.

## Standard fetch — this is the whole procedure

```bash
thc hmdb fetch                          # Texas → data_files/, auto re-auth if needed
thc hmdb fetch --state California       # other state
thc hmdb fetch --out-dir /tmp           # custom dir
thc hmdb fetch --out-file my.csv        # override filename
thc hmdb fetch --check-auth             # verify (and refresh) the cookie only, no download
thc hmdb fetch --refresh-auth           # force a new login first
thc hmdb fetch --no-auto-refresh        # fail on an expired cookie instead of logging in
```

What the CLI does:

1. Loads the cookie; if the file is missing, logs in first.
2. Verifies it against `mymarkers.asp`. On the "ErrorReturn" redirector
   (logged out) it runs `hmdb_login.js` once and verifies again.
3. Fetches the state listing, parses the hidden marker-ID field.
4. POSTs to `ListsDownload.asp`, writes the response bytes verbatim.

Output filename is whatever HMDB suggests via `Content-Disposition`
(e.g. `HMdb-Entries-Texas-20260906.csv`). Pass `--out-file` to override.

Observed cookie lifetime is short (it failed within an hour on
2026-09-06), so expect the `[WARN] cookie expired; re-logging in` line to
be normal, not an error. The persistent Chrome profile usually still has
a live hmdb session, so the re-login takes ~5 s and needs no password
round-trip ("already signed in").

## When the automatic login fails

The CLI prints the `[login]` lines from the script and stops. Check, in
order:

1. **No X display** (SSH session, headless box): the script needs
   `DISPLAY` (defaults to `:1`, Joe's desktop). Run the fetch from a
   terminal on the desktop, or `DISPLAY=:1 thc hmdb fetch`.
2. **Cloudflare "Just a moment..." never clears**: happens in headless
   mode (`HEADED=0`) — never use it — or when the profile at
   `~/.cache/thc-toolkit-hmdb-profile` is stale; delete that directory
   and retry.
3. **Credentials**: `~/.config/thc-toolkit/hmdb.env` must hold
   `HMDB_EMAIL=` / `HMDB_PASSWORD=` (mode 0600). If absent, ask the user.
4. **playwright-core missing**: the script looks in `node_modules`, then
   the npx cache (`~/.npm/_npx/*/node_modules/playwright-core`, present
   whenever the Playwright MCP has ever run). `npm i -g playwright-core`
   also works. Chrome binary: `/opt/google/chrome/chrome` or `CHROME_PATH`.
5. **Last resort**: sign in by hand in any browser and paste the
   `HistoricalMarkerDB=SessionID={GUID}&UserID=NNNN` cookie into
   `~/.config/thc-toolkit/hmdb.session` (one line, mode 0600).

Do **not** fall back to the Playwright MCP browser tools for the login:
their shared profile is locked whenever another Claude session has the
browser open (`Browser is already in use for
~/.cache/ms-playwright-mcp/...`), and the headless MCP browser is blocked
by Cloudflare anyway. That combination cost most of an hour on
2026-09-06 and is why the login lives in the CLI now.

## Chain with hmdb-update

The full update cycle (fetch → report → approve → apply → OSM) is the
`hmdb-update` skill; `thc hmdb fetch` is its first step. The lower-level
reconcile/apply mechanics are in `hmdb-sync`.

## Guardrails

- **Never commit** `~/.config/thc-toolkit/hmdb.session` or `hmdb.env` to
  the repo. They live under `~/.config/`, intentionally outside the
  working tree.
- **Do not** echo the cookie value or password into shell command history
  or the transcript. `hmdb_login.js` and `refresh_auth()` never print
  either; keep it that way.
- **Respect HMDB**: a full Texas pull is ~5.6 MB and one POST. Don't
  fetch more often than ~daily; the data changes at ~1–20 new TX markers
  per day. Use `--check-auth` to test the auth path without downloading.
- **Don't change** `User-Agent` or other request shape casually — HMDB's
  edge fingerprints, and the working pattern is encoded in
  `hmdb_fetch.DEFAULT_USER_AGENT`. Plain `requests` traffic with that UA
  is *not* Cloudflare-challenged (verified 2026-09-06); only browser
  sign-in is.
