"""Tap-to-sound latency on CACHED clips (installed app, service worker ready):  python3 tools/test_tap_latency.py [--label X] [--budget 150]
Pixel 7 emulation with the CPU slowed 4x (mid-range Android), real autoplay policy (sound only after a tap). Measures the time from the finger touching the screen
(pointerdown) to the moment the voice clip is scheduled to sound (Web Audio start time, or the <audio> 'playing' event),
for English and French lines in the Cameroon pilot and English lines in the world games (cards, quiz, House).
Each case is tapped several times (first tap of a line and repeats). Fails if the median of any case > budget or any
single tap > 2x budget. Results also go to /tmp/ew-tap-latency-<label>.json."""
import asyncio, sys, json, threading, functools, http.server, os, statistics, argparse
from playwright.async_api import async_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser(); ap.add_argument('--label', default='now'); ap.add_argument('--budget', type=float, default=150); ap.add_argument('--url'); ap.add_argument('--cpu', type=float, default=4, help='CPU slow-down (4 = mid-range Android phone)'); A = ap.parse_args()
INIT = """window.__ev=[];window.__t0=0;addEventListener('pointerdown',()=>{window.__t0=performance.now()},true);
const op=HTMLMediaElement.prototype.play;HTMLMediaElement.prototype.play=function(){const el=this;const h=()=>{if(!el.muted)__ev.push({t:performance.now(),src:el.currentSrc,k:'audio-element'})};el.addEventListener('playing',h,{once:true});return op.apply(this,arguments)};
if(window.AudioBufferSourceNode){const os=AudioBufferSourceNode.prototype.start;AudioBufferSourceNode.prototype.start=function(when){const n=this,c=n.context,now=performance.now(),d=Math.max(0,((when||0)-c.currentTime)*1000);
 if(n.__src)__ev.push({t:now+d+(c.outputLatency||0)*0,src:n.__src,k:'web-audio'});return os.apply(this,arguments)}}"""
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def handle(self):
        try: super().handle()
        except Exception: pass
async def measure(pg, sel):
    await pg.evaluate('__ev=[];stopVoice()'); await pg.wait_for_timeout(250)
    await pg.tap(sel)
    for _ in range(100):
        r = await pg.evaluate('(()=>{const e=__ev.find(x=>x.t>=__t0);return e?[e.t-__t0,e.src,e.k]:null})()')
        if r: return round(r[0], 1), r[1].split('/')[-1], r[2]
        await pg.wait_for_timeout(50)
    return None, 'NO AUDIO', None
async def main():
    url = A.url
    if not url:
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Q, directory=ROOT)); threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{srv.server_address[1]}/'
    out = {}; fails = []
    async with async_playwright() as p:
        b = await p.chromium.launch(args=['--autoplay-policy=user-gesture-required'])
        ctx = await b.new_context(**p.devices['Pixel 7']); await ctx.add_init_script(INIT); pg = await ctx.new_page()
        await pg.goto(url, wait_until='load')
        await pg.evaluate("""async()=>{await navigator.serviceWorker.ready;const t0=Date.now();for(;;){const sw=await fetch('sw.js').then(r=>r.text());const want=JSON.parse(sw.match(/ASSETS=(\\[.*?\\]);/)[1]).length;
          let have=0;for(const k of (await caches.keys()).filter(k=>k.startsWith('emma-house-')))have+=(await (await caches.open(k)).keys()).length;if(have>=want&&navigator.serviceWorker.controller)return;if(Date.now()-t0>600000)throw new Error('precache timeout');await new Promise(z=>setTimeout(z,1000))}}""")
        await pg.reload(wait_until='load'); await pg.wait_for_function('LANDS!==null&&screen==="home"&&window.CTRY_READY', timeout=30000)
        await pg.tap('#title'); await pg.wait_for_timeout(1500)  # a child's first touch unlocks sound
        cdp = await ctx.new_cdp_session(pg); await cdp.send('Emulation.setCPUThrottlingRate', {'rate': A.cpu})
        async def case(name, setup, sels, n=5):
            """sels: one selector tapped n times (repeat of the same line) or a list (a NEW line on every tap)"""
            await pg.evaluate(setup); await pg.wait_for_timeout(1500)
            rs = []
            for i in range(n):
                sel = sels if isinstance(sels, str) else sels[i]
                ms, src, k = await measure(pg, sel); rs.append({'ms': ms, 'clip': src, 'path': k}); await pg.wait_for_timeout(500)
                await pg.evaluate("document.querySelectorAll('.pop').forEach(p=>p.remove())")
            ms = [r['ms'] for r in rs if r['ms'] is not None]
            med = statistics.median(ms) if ms else None
            out[name] = {'median': med, 'max': max(ms) if ms else None, 'taps': rs}
            bad = med is None or med > A.budget or len(ms) < n or max(ms) > 2 * A.budget
            if bad: fails.append(name)
            print(f'{"ok  " if not bad else "FAIL"} {name:<44} median {med} ms  max {max(ms) if ms else None} ms  path {rs[0]["path"]}  {[r["ms"] for r in rs]}', flush=True)
        prefs = lambda lg: f"localStorage.setItem('emmaCtryPrefs',JSON.stringify({{lang:'{lg}',age:'little',guide:false}}));"
        for lg in ('en', 'fr'):
            await case(f'Cameroon: next card, new line ({lg})', prefs(lg) + "go('clearn',{c:'cameroon',i:0})", ['#cnext'] * 5)
            await case(f'Cameroon: replay button ({lg})', prefs(lg) + "go('clearn',{c:'cameroon',i:0})", '#csay')
        for land, place, nm in (('world', 'countries', 'country cards'), ('letter', 'abc', 'ABC cards'), ('nature', 'safari', 'animal cards')):
            await case(f'{nm}: new line each tap (en)', f"go('wcards',{{l:'{land}',p:'{place}'}})", [f'.wtile[data-i="{i}"]' for i in range(5)])
        await case('animal cards: same line again (en)', "go('wcards',{l:'nature',p:'safari'})", '.wtile[data-i="3"]')
        await b.close()
    json.dump(out, open(f'/tmp/ew-tap-latency-{A.label}.json', 'w'), indent=1)
    print('TAP LATENCY', 'PASSED' if not fails else 'FAILED: ' + ', '.join(fails))
    return 1 if fails else 0
sys.exit(asyncio.run(main()))
