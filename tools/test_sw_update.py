"""Old preview install must pick up a new preview build by itself.

  python3 tools/test_sw_update.py

Serves 62cab96 at /emmavengers-world-preview/ (the same path as the test site), waits until
that service worker is in control, then swaps the files for the current tree and reloads once.
The new worker has to take over and show the red TEST badge without a tap on "New update ready"
and without a second manual reload. GitHub Pages caches sw.js for 10 minutes; this test does
the same (Cache-Control: max-age=600) and still registers with updateViaCache: 'none' on the
new page. The first reload uses the old page's register('sw.js') call, which is what a phone
already running the previous test site will do.
"""
import asyncio, http.server, posixpath, subprocess, sys, threading, time
from pathlib import Path
from urllib.parse import urlparse, unquote
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OLD_REV = '62cab96'
PREFIX = '/emmavengers-world-preview'
fails = []

def ok(c, m):
    print(('OK   ' if c else 'FAIL ') + m, flush=True)
    if not c:
        fails.append(m)

def archive_old(dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    # Reuse a previous extract of this commit (the 62cab96 tree is ~180 MB).
    marker = dest / 'sw.js'
    if marker.exists():
        return
    p = subprocess.Popen(['git', 'archive', OLD_REV], cwd=str(ROOT), stdout=subprocess.PIPE)
    subprocess.check_call(['tar', '-x', '-C', str(dest)], stdin=p.stdout)
    p.stdout.close()
    if p.wait() != 0:
        raise SystemExit('git archive failed')

STATE = {'root': None}

class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def end_headers(self):
        self.send_header('Cache-Control', 'max-age=600')
        super().end_headers()
    def translate_path(self, path):
        p = unquote(urlparse(path).path)
        if p.startswith(PREFIX):
            p = p[len(PREFIX):]
        if not p or p == '/':
            p = '/index.html'
        rel = posixpath.normpath(p).lstrip('/')
        full = (STATE['root'] / rel).resolve()
        try:
            full.relative_to(STATE['root'].resolve())
        except ValueError:
            return '/dev/null'
        return str(full)

async def sw_info(pg):
    return await pg.evaluate("""async () => {
      const badge = !!document.getElementById('testBadge');
      const upd = !!document.getElementById('updBtn');
      const title = document.title;
      const ctrl = !!navigator.serviceWorker.controller;
      const reg = await navigator.serviceWorker.getRegistration();
      const info = {
        badge, upd, title, ctrl,
        waiting: !!(reg && reg.waiting),
        installing: !!(reg && reg.installing),
        build: null,
      };
      if (navigator.serviceWorker.controller) {
        info.build = await new Promise((resolve) => {
          const t = setTimeout(() => resolve(null), 2000);
          const onm = (e) => {
            if (e.data && e.data.build) {
              clearTimeout(t);
              navigator.serviceWorker.removeEventListener('message', onm);
              resolve(e.data.build);
            }
          };
          navigator.serviceWorker.addEventListener('message', onm);
          navigator.serviceWorker.controller.postMessage('build');
        });
      }
      return info;
    }""")

async def main():
    old_dir = Path('/tmp/ew-sw-old-'+OLD_REV); old_dir.mkdir(parents=True, exist_ok=True)
    print('archiving', OLD_REV, 'to', old_dir, flush=True)
    archive_old(old_dir)
    STATE['root'] = old_dir

    http.server.ThreadingHTTPServer.allow_reuse_address = True
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{srv.server_port}{PREFIX}/'
    print('URL', url, flush=True)

    new_build = None
    import re
    new_build = re.search(r"const BUILD='([^']+)'", (ROOT / 'sw.js').read_text()).group(1)
    old_sw = (old_dir / 'sw.js').read_text()
    old_build = re.search(r"const BUILD='([^']+)'", old_sw).group(1)
    print('old build', old_build, 'new build', new_build, flush=True)

    async with async_playwright() as P:
        b = await P.chromium.launch()
        ctx = await b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        pg = await ctx.new_page()
        errors = []
        pg.on('pageerror', lambda e: errors.append(str(e)))

        await pg.goto(url, wait_until='load')
        await pg.wait_for_function('!!navigator.serviceWorker.controller', timeout=90000)
        info = await sw_info(pg)
        ok(info['build'] == old_build, f'first visit is controlled by the old worker ({info["build"]})')
        ok(not info['badge'], 'first visit has no TEST badge (old page)')

        # Swap the files the way a new GitHub Pages deploy does, then reopen once.
        # The new worker may client.navigate() this tab mid-reload, which can cancel
        # Playwright's reload() promise — so we only wait for a commit, with a timeout,
        # and then poll until the TEST page is showing.
        STATE['root'] = ROOT
        print('reopening after deploy', flush=True)
        try:
            await asyncio.wait_for(pg.reload(wait_until='commit'), timeout=20)
        except Exception as e:
            print('reload promise ended:', type(e).__name__, e, flush=True)
        deadline = time.time() + 60
        last = info
        while time.time() < deadline:
            try:
                last = await asyncio.wait_for(sw_info(pg), timeout=5)
            except Exception as e:
                last = {'error': type(e).__name__}
            if last.get('badge') and last.get('build') == new_build:
                break
            await pg.wait_for_timeout(500)
        ok(last.get('badge') is True, f'after one reopen the TEST badge appears (last={last})')
        ok(last.get('title') == 'Emmavengers TEST', f'title becomes Emmavengers TEST ({last.get("title")})')
        ok(last.get('build') == new_build, f'controller is the new worker {new_build} (got {last.get("build")})')
        ok(not last.get('upd'), 'no need to tap "New update ready"')
        ok(not errors, f'no page errors {errors}')

        # First visit (no previous worker): the TEST page shows, and it must not keep reloading.
        ctx2=await b.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
        pg2=await ctx2.new_page()
        await pg2.goto(url, wait_until='load')
        await pg2.wait_for_function('!!document.getElementById("testBadge")', timeout=30000)
        builds=[]
        for _ in range(4):
            builds.append(await asyncio.wait_for(sw_info(pg2), timeout=5))
            await pg2.wait_for_timeout(800)
        ok(all(x.get('badge') and x.get('title')=='Emmavengers TEST' for x in builds),
           f'first visit stays on the TEST page (no reload loop) {builds[-1]}')
        await ctx2.close()
        await b.close()
    srv.shutdown()
    if fails:
        print('\nFAILED:', *fails, sep='\n  ')
        sys.exit(1)
    print('\nAll SW update checks passed.')

if __name__ == '__main__':
    asyncio.run(main())
