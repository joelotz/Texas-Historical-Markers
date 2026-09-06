// hmdb.org sign-in in a real (headed) Chrome; writes the session cookie for `thc hmdb fetch`.
//
// Why headed: since 2026-09 hmdb.org sits behind a Cloudflare managed challenge that never
// clears for headless Chrome (any UA) but auto-clears for a headed real Chrome. Why not the
// Playwright MCP tools: their shared browser profile is locked whenever another Claude session
// has it open. This script uses playwright-core (found in the npx cache) + the system Chrome,
// with its own persistent profile so Cloudflare's clearance cookie is reused next time.
//
// Inputs : ~/.config/thc-toolkit/hmdb.env  (HMDB_EMAIL=..., HMDB_PASSWORD=...)  mode 0600
// Output : ~/.config/thc-toolkit/hmdb.session  ("HistoricalMarkerDB=SessionID={GUID}&UserID=NNNN")
// Env    : DISPLAY (required; defaults to :1), HEADED=0 to try headless (expect Cloudflare to block),
//          CHROME_PATH to override the browser binary, HMDB_LOGIN_TIMEOUT_S (default 90).
// Never prints the password or the cookie value.
const fs = require('fs');
const os = require('os');
const path = require('path');

function findPlaywright() {
  try { return require('playwright-core'); } catch (_) {}
  try { return require('playwright'); } catch (_) {}
  const npx = path.join(os.homedir(), '.npm', '_npx');
  if (fs.existsSync(npx)) {
    for (const d of fs.readdirSync(npx)) {
      for (const pkg of ['playwright-core', 'playwright']) {
        const p = path.join(npx, d, 'node_modules', pkg);
        if (fs.existsSync(p)) { try { return require(p); } catch (_) {} }
      }
    }
  }
  console.error('playwright-core not found: run `npx -y @playwright/mcp@latest --help` once, or `npm i -g playwright-core`');
  process.exit(3);
}
function findChrome() {
  const cands = [process.env.CHROME_PATH, '/opt/google/chrome/chrome', '/usr/bin/google-chrome',
                 '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/snap/bin/chromium'].filter(Boolean);
  for (const c of cands) if (fs.existsSync(c)) return c;
  console.error('no Chrome/Chromium binary found; set CHROME_PATH'); process.exit(3);
}

const { chromium } = findPlaywright();
const cfg = path.join(os.homedir(), '.config', 'thc-toolkit');
const envPath = path.join(cfg, 'hmdb.env');
if (!fs.existsSync(envPath)) { console.error(`missing ${envPath} (HMDB_EMAIL / HMDB_PASSWORD)`); process.exit(2); }
const env = Object.fromEntries(fs.readFileSync(envPath, 'utf8').split('\n').filter(l => l.includes('='))
  .map(l => { const i = l.indexOf('='); return [l.slice(0, i).trim(), l.slice(i + 1).trim()]; }));
if (!env.HMDB_EMAIL || !env.HMDB_PASSWORD) { console.error('hmdb.env lacks HMDB_EMAIL / HMDB_PASSWORD'); process.exit(2); }
const headed = process.env.HEADED !== '0';
if (headed && !process.env.DISPLAY) process.env.DISPLAY = ':1';
const timeoutS = Number(process.env.HMDB_LOGIN_TIMEOUT_S || 90);

(async () => {
  const profile = path.join(os.homedir(), '.cache', 'thc-toolkit-hmdb-profile');
  const ctx = await chromium.launchPersistentContext(profile, {
    executablePath: findChrome(), headless: !headed, viewport: { width: 1920, height: 1080 },
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled'],
    ignoreDefaultArgs: ['--enable-automation'],
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  const deadline = Date.now() + timeoutS * 1000;
  try {
    // /signin.asp 403s on direct navigation; mymarkers.asp redirects there when logged out.
    await page.goto('https://www.hmdb.org/mymarkers.asp', { waitUntil: 'load', timeout: 60000 });
    while (!(await page.$('input[name=Email]'))) {
      const cookies = await ctx.cookies('https://www.hmdb.org');
      const auth = cookies.find(c => c.name === 'HistoricalMarkerDB' && /UserID=\d+/.test(c.value));
      if (auth && /MyMarkers\.asp/i.test(page.url()) && !/ErrorReturn/.test(await page.content())) {
        console.log('already signed in (profile cookie still valid)'); return writeCookie(auth.value);
      }
      if (Date.now() > deadline) throw new Error(`no sign-in form after ${timeoutS}s; page title: ${await page.title()} (Cloudflare challenge not cleared?)`);
      await page.waitForTimeout(2000);
    }
    console.log('sign-in form at', page.url());
    await page.fill('input[name=Email]', env.HMDB_EMAIL);
    await page.fill('input[name=Password]', env.HMDB_PASSWORD);
    await Promise.all([page.waitForLoadState('load'), page.click('input[type=submit], input[value="Sign In"]')]);
    while (Date.now() < deadline) {                       // "One Moment Please" autoclick chain
      await page.waitForTimeout(2000);
      const cookies = await ctx.cookies('https://www.hmdb.org');
      const auth = cookies.find(c => c.name === 'HistoricalMarkerDB' && /UserID=\d+/.test(c.value));
      if (auth) { console.log('signed in; url', page.url()); return writeCookie(auth.value); }
      console.log('waiting for session cookie; url', page.url(), 'title', await page.title());
    }
    throw new Error('login did not yield a session cookie in time');
  } catch (e) {
    console.error('login failed:', e.message); process.exitCode = 1;
  } finally {
    await ctx.close();
  }
  function writeCookie(value) {
    const out = path.join(cfg, 'hmdb.session');
    fs.writeFileSync(out, `HistoricalMarkerDB=${value}\n`, { mode: 0o600 }); fs.chmodSync(out, 0o600);
    console.log('cookie written to', out, 'UserID', (value.match(/UserID=(\d+)/) || [])[1]);
  }
})();
