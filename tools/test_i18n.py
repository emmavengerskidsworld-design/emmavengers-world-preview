"""Languages in the real app (Chromium, Playwright):  python3 tools/test_i18n.py [shots_dir]
Builds the TEST channel (content/src with the test-only sample languages ar + fr-CM, never shipped) into a temp folder
and serves it in place of content/preview/, then checks on phone sizes 390 x 844 and 360 x 780:
  - first visit picks the phone's language (en-US -> English, fr-FR -> French) and downloads ONLY that language
  - the language picker (header 🌐 and Parents' Corner) switches every app word, the land texts, html lang/dir,
    and is remembered on the device; only the chosen language + its fallbacks are downloaded, others are removed
  - fallback chain fr-CM -> fr -> en: regional text, then French, then English - and each text is spoken by its
    own language's voice (English text in voice/, French text in voice/fr/, a language with no voice -> phone voice)
  - Arabic (test-only, right-to-left): dir=rtl, Arabic font stack, Arabic plural rules, mirrored layout with no
    horizontal overflow on the world map, a land, the language panel, Parents' Corner and Voice Settings
  - a localized picture (<name>.<tag>.<ext>) is shown in its language and falls back to the original elsewhere
  - the committed live + preview libraries carry no test-only language and live carries no machine-draft text
Screenshots (en, fr, test-ar at 390 wide) go to shots_dir (default /workspace/stage2-shots)."""
import asyncio, functools, http.server, io, contextlib, json, os, shutil, sys, tempfile, threading
from playwright.async_api import async_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import content_build
from content.common import load_json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = sys.argv[1] if len(sys.argv) > 1 else '/workspace/stage2-shots'
os.makedirs(SHOTS, exist_ok=True)
fails, n = [], [0]
def ok(c, m):
    n[0] += 1; print(('  ok  ' if c else '  FAIL ') + m, flush=True)
    if not c: fails.append(m)

# ---------- 0. committed libraries never carry test-only languages / unreviewed text on live ----------
print('0. committed libraries')
LOC = {l['tag']: l for l in load_json(os.path.join(ROOT, 'content/src/locales.json'))['locales']}
TEST_ONLY = {t for t, l in LOC.items() if l['status'] == 'test-only'}
ok(TEST_ONLY >= {'ar', 'fr-CM'}, f'test-only sample languages defined: {sorted(TEST_ONLY)}')
for lib in ('content/library', 'content/preview'):
    cat = load_json(os.path.join(ROOT, lib, 'catalog.json')); tags = [l['tag'] for l in cat['locales']]
    files = [f for d, _, fs in os.walk(os.path.join(ROOT, lib)) for f in fs]
    ok(not (set(tags) & TEST_ONLY) and not any(('@' + t + '.') in f for f in files for t in TEST_ONLY), f'{lib}: languages {tags}, no test-only language or file')
live = load_json(os.path.join(ROOT, 'content/library/catalog.json'))
blob = ''.join(open(os.path.join(d, f), encoding='utf-8').read() for d, _, fs in os.walk(os.path.join(ROOT, 'content/library')) for f in fs if f.endswith('.json'))
mfr = load_json(os.path.join(ROOT, 'content/src/l10n/fr/core-lands.json'))
ok(mfr['reviewStatus'] in ('machine-draft', 'draft') and mfr['strings']['ew.land.faith']['payload.name'] not in blob,
   f'live library has none of the {mfr["reviewStatus"]} French land names ("{mfr["strings"]["ew.land.faith"]["payload.name"]}" only on preview)')

# ---------- test release: test channel + one localized picture, in a temp root ----------
T = tempfile.mkdtemp(prefix='ewi18n-'); TR = os.path.join(T, 'root'); os.makedirs(TR)
for e in os.listdir(ROOT):
    if e not in ('img', '.git'): os.symlink(os.path.join(ROOT, e), os.path.join(TR, e))
shutil.copytree(os.path.join(ROOT, 'img'), os.path.join(TR, 'img'), copy_function=os.symlink)
PIC = 'img/world/nature-land.jpg'; PIC_AR = 'img/world/nature-land.ar.jpg'
from PIL import Image, ImageDraw
im = Image.open(os.path.join(ROOT, PIC)).convert('RGB'); d = ImageDraw.Draw(im); d.rectangle([0, 0, im.width - 1, 230], fill=(200, 30, 60)); im.save(os.path.join(TR, PIC_AR), quality=80)
LIB = os.path.join(T, 'lib')
with contextlib.redirect_stdout(io.StringIO()):
    rc = content_build.main(['--channel', 'test', '--root', TR, '--lib', LIB, '--lock', os.path.join(T, 'lock.json'), '--report', os.path.join(T, 'r.md'), '--quiet', '--no-files'])
ok(rc == 0, 'test channel builds (en, fr, ar, fr-CM)')
tcat = load_json(os.path.join(LIB, 'catalog.json'))
ok({l['tag'] for l in tcat['locales']} == {'en', 'fr', 'ar', 'fr-CM'}, f'test catalog languages: {[l["tag"] for l in tcat["locales"]]}')
ar = next(l for l in tcat['locales'] if l['tag'] == 'ar')
ok(ar.get('pictures') == [PIC] and ar['dir'] == 'rtl' and ar['voice'] is None and 'Noto' in ' '.join(ar.get('fonts', [])), f'ar entry: rtl, Arabic fonts, no voice, localized picture {ar.get("pictures")}')

LOG = []
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def handle(self):
        try: super().handle()
        except Exception: pass
    def translate_path(self, path):
        p = path.split('?')[0]
        if p.startswith('/content/preview/'):
            LOG.append(p[len('/content/preview/'):]); return os.path.join(LIB, p[len('/content/preview/'):])
        if p == '/' + PIC_AR: LOG.append(p); return os.path.join(TR, PIC_AR)
        return super().translate_path(path)
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store'); super().end_headers()
srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(H, directory=ROOT)); threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{srv.server_port}/'
langs_dl = lambda: sorted({f.split('@')[1].split('.')[0] for f in LOG if '@' in f})  # file names use lower-case tags

OVER = """()=>{const W=innerWidth,bad=[];document.querySelectorAll('button,.btn,img,h1,h2,.prompt,.wmap,.wsign,.wcard,.lcard,.box,.vcard,input,p').forEach(e=>{const r=e.getBoundingClientRect();
 if(!r.width||getComputedStyle(e).visibility=='hidden'||e.closest('[hidden]'))return;if(r.left<-2||r.right>W+2)bad.push((e.id||e.className||e.tagName)+' '+Math.round(r.left)+'..'+Math.round(r.right))});
 const m=document.querySelector('#wmap');if(m){const mr=m.getBoundingClientRect();m.querySelectorAll('.wsign,.w6title').forEach(e=>{const r=e.getBoundingClientRect();
  if(r.width&&(r.left<mr.left-1||r.right>mr.right+1))bad.push('label cut by the map edge: '+e.textContent.trim()+' '+Math.round(r.left-mr.left)+'..'+Math.round(r.right-mr.left)+' of '+Math.round(mr.width))})}
 return {sw:document.documentElement.scrollWidth,W,bad:bad.slice(0,5)}}"""
async def no_overflow(pg, tag):
    r = await pg.evaluate(OVER); ok(r['sw'] <= r['W'] + 1 and not r['bad'], f'{tag}: no horizontal overflow (page {r["sw"]} <= {r["W"]}{", " + str(r["bad"]) if r["bad"] else ""})')
READY = 'typeof LANDS!=="undefined"&&LANDS&&window.EWi18n&&EWi18n.ok&&screen==="home"'
STATE = '({lang:EWi18n.lang,chain:EWi18n.chain,dl:EWLib.downloadedLocales().sort(),html:document.documentElement.lang,dir:document.documentElement.dir,script:document.documentElement.dataset.script,title:document.querySelector("#title").textContent,lbl:document.querySelector("#langBtn").getAttribute("aria-label")})'
async def pick(pg, tag):
    await pg.click('#langBtn'); await pg.wait_for_selector(f'#lpanel .lcard[data-lang="{tag}"]')
    await pg.click(f'#lpanel .lcard[data-lang="{tag}"]'); await pg.wait_for_function(f'EWi18n.lang==="{tag}"', timeout=10000)
    await pg.wait_for_timeout(900)
async def parents(pg):
    await pg.click('#parentBtn'); q = await pg.text_content('#ppanel .subh')
    import re
    nums = [int(x) for x in re.findall(r'\d+', q.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')))][:2]
    await pg.fill('#pIn', str(nums[0] * nums[1])); await pg.click('#pOk'); await pg.wait_for_selector('#pYt', timeout=4000)

async def main():
    async with async_playwright() as pw:
        br = await pw.chromium.launch()
        async def ctx_for(w, h, locale='en-US'):
            c = await br.new_context(viewport={'width': w, 'height': h}, device_scale_factor=2, locale=locale, service_workers='block', has_touch=True)
            pg = await c.new_page(); errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            return c, pg, errs

        print('1. first visit: the phone language, and only that language is downloaded')
        c, pg, errs = await ctx_for(390, 844); LOG.clear()
        await pg.goto(URL); await pg.wait_for_function(READY, timeout=20000)
        s = await pg.evaluate(STATE)
        ok(s['lang'] == 'en' and s['dl'] == ['en'] and langs_dl() == ['en'], f'en-US phone -> English; downloaded {s["dl"]}, fetched language files {langs_dl()}')
        ok('🌐' in await pg.text_content('#langBtn'), 'language button in the header')
        await no_overflow(pg, '390 en home'); await pg.screenshot(path=os.path.join(SHOTS, 'en-390-home.png'))
        en_title = s['title']
        c2, pg2, _ = await ctx_for(390, 844, 'fr-FR'); LOG.clear()
        await pg2.goto(URL); await pg2.wait_for_function(READY, timeout=20000); await pg2.wait_for_timeout(1500); s2 = await pg2.evaluate(STATE)
        ok(s2['lang'] == 'fr' and s2['title'] != en_title and s2['html'] == 'fr' and s2['dl'] == ['en', 'fr'] and 'ar' not in langs_dl(), f'fr-FR phone -> French ("{s2["title"]}"), downloaded {s2["dl"]} (French + its fallback English)')
        await c2.close()

        print('2. language picker switches everything and is remembered')
        LOG.clear(); await pick(pg, 'fr'); s = await pg.evaluate(STATE)
        ok(s['lang'] == 'fr' and s['html'] == 'fr' and s['dir'] == 'ltr' and s['title'] != en_title, f'picker -> French: title "{s["title"]}", html lang {s["html"]}')
        ok(s['lbl'] != 'Language', f'header button label in French ("{s["lbl"]}")')
        ok(langs_dl() == ['fr'] and s['dl'] == ['en', 'fr'], f'switch downloads only French ({langs_dl()}); device has {s["dl"]}')
        w = await pg.evaluate('({t:LANDS.world.intro,v:voiceUrl(LANDS.world.intro)})')
        ok(w['v'] and w['v'].startswith('voice/fr/'), f'French text spoken by the French voice ({w["v"]})')
        await no_overflow(pg, '390 fr home'); await pg.screenshot(path=os.path.join(SHOTS, 'fr-390-home.png'))
        await pg.set_viewport_size({'width': 360, 'height': 780}); await pg.wait_for_timeout(400); await no_overflow(pg, '360 fr home')
        await pg.set_viewport_size({'width': 390, 'height': 844}); await pg.wait_for_timeout(400)
        await pg.click('.wsignb[data-l="nature"]'); await pg.wait_for_function('screen==="land"'); await pg.wait_for_timeout(500)
        bg = await pg.evaluate('getComputedStyle(document.querySelector("#wmap")).backgroundImage')
        ok('nature-land.jpg' in bg, 'French has no copy of the Nature Land picture -> the original is shown (fallback)')
        ok(await pg.text_content('#wback') != 'Back to Map', f'land screen words in French ("{await pg.text_content("#wback")}")')
        await no_overflow(pg, '390 fr land'); await pg.screenshot(path=os.path.join(SHOTS, 'fr-390-land.png'))
        await pg.reload(); await pg.wait_for_function(READY, timeout=20000); LOG.clear()
        s = await pg.evaluate(STATE); ok(s['lang'] == 'fr', 'reload: French remembered on the device')
        await parents(pg)
        ok(await pg.query_selector('#pLangs .lcard[data-lang="fr"].on') is not None, "Parents' Corner shows the language choice (French selected)")
        await pg.click('#pLangs .lcard[data-lang="en"]'); await pg.wait_for_function('EWi18n.lang==="en"', timeout=10000); await pg.wait_for_timeout(600)
        s = await pg.evaluate(STATE); ok(s['lang'] == 'en' and s['html'] == 'en', "Parents' Corner switches back to English")
        await pg.evaluate('emmaBack()'); await pg.wait_for_timeout(1500)
        s = await pg.evaluate(STATE); ok(s['dl'] == ['en'], f'French removed from the device after switching back ({s["dl"]})')

        print('3. fallback chain fr-CM -> fr -> en')
        await pg.evaluate('EWi18n.set("fr-CM")'); await pg.wait_for_timeout(900); s = await pg.evaluate(STATE)
        ok(s['chain'] == ['fr-CM', 'fr', 'en'], f'chain {s["chain"]}')
        fcm = load_json(os.path.join(ROOT, 'content/src/l10n/fr-CM/test-sample.json'))
        want = next(iter(next(iter(fcm['strings'].values())).values()))
        ok(want in json.dumps(await pg.evaluate('LANDS'), ensure_ascii=False), f'regional text used: "{want}"')
        r = await pg.evaluate("""(()=>{const L=LANDS.lands.find(l=>l.id==='letter'),N=LANDS.lands.find(l=>l.id==='nature');
          const en=LANDS.decks.letters?LANDS.decks.letters.items[0].word:null;
          const all=[];const w=o=>{if(typeof o==='string')all.push(o);else if(o&&typeof o==='object')Object.values(o).forEach(w)};w(L);
          const e=all.find(t=>EWi18n.langOf(t)==='en'&&t.includes(" "));  /* a Letter Land text with no French translation */
          return {fr:N.intro,frl:EWi18n.langOf(N.intro),frv:voiceUrl(N.intro),en:e||'',enl:e&&EWi18n.langOf(e),env:e?voiceUrl(e):''}})()""")
        ok(r['frl'] == 'fr' and r['frv'].startswith('voice/fr/'), f'French fallback text "{r["fr"][:40]}" -> {r["frv"]}')
        ok(r['enl'] == 'en' and r['env'].startswith('voice/') and not r['env'].startswith('voice/fr/'), f'English fallback text "{r["en"][:40]}" -> English voice {r["env"]}')

        print('4. Arabic (test-only): right-to-left, plurals, pictures, no overflow')
        for W, H in ((390, 844), (360, 780)):
            c3, p3, e3 = await ctx_for(W, H); await p3.goto(URL); await p3.wait_for_function(READY, timeout=20000); LOG.clear()
            await pick(p3, 'ar'); s = await p3.evaluate(STATE)
            ok(s['dir'] == 'rtl' and s['html'] == 'ar' and s['script'] == 'Arab', f'{W}: html dir={s["dir"]} lang={s["html"]} script={s["script"]}')
            ok(langs_dl() == ['ar'] and s['dl'] == ['ar', 'en'], f'{W}: downloads only Arabic ({langs_dl()}), device has {s["dl"]}')
            f = await p3.evaluate('getComputedStyle(document.body).fontFamily'); ok('Noto' in f and 'Arab' in f, f'{W}: Arabic font stack ({f[:60]}...)')
            if W == 390:
                pl = await p3.evaluate('[0,1,2,3,11,100].map(n=>EWi18n.t("toLearn",{n}))')
                ok(len(set(pl)) >= 5, f'Arabic plural forms (zero/one/two/few/many/other): {len(set(pl))} different texts')
                ok(await p3.evaluate('getComputedStyle(document.querySelector("#score")).direction') == 'ltr', 'score stays left-to-right inside RTL')
                v = await p3.evaluate('voiceUrl(LANDS.world.title)'); ok(v is None, 'Arabic text has no recorded voice -> the phone reads it (voiceUrl null)')
            await no_overflow(p3, f'{W} ar home'); 
            if W == 390: await p3.screenshot(path=os.path.join(SHOTS, 'test-ar-390-home.png'))
            await p3.click('.wsignb[data-l="nature"]'); await p3.wait_for_function('screen==="land"'); await p3.wait_for_timeout(700)
            bg = await p3.evaluate('getComputedStyle(document.querySelector("#wmap")).backgroundImage')
            ok('nature-land.ar.jpg' in bg, f'{W}: Arabic copy of the Nature Land picture shown')
            await no_overflow(p3, f'{W} ar land')
            if W == 390: await p3.screenshot(path=os.path.join(SHOTS, 'test-ar-390-land.png'))
            await p3.click('#wback'); await p3.wait_for_function('screen==="home"')
            await p3.click('#langBtn'); await p3.wait_for_selector('#lpanel .lcard'); await p3.wait_for_timeout(600); await no_overflow(p3, f'{W} ar language panel')
            if W == 390: await p3.screenshot(path=os.path.join(SHOTS, 'test-ar-390-language.png'))
            await p3.click('#lClose'); await parents(p3); await no_overflow(p3, f"{W} ar Parents' Corner")
            if W == 390: await p3.screenshot(path=os.path.join(SHOTS, 'test-ar-390-parents.png'))
            await p3.click('#pVoice'); await p3.wait_for_selector('#vpanel .vcard'); await no_overflow(p3, f'{W} ar Voice Settings')
            ok(not e3, f'{W}: no JS errors in Arabic {e3[:2]}')
            await c3.close()
        ok(not errs, f'no JS errors {errs[:3]}')
        await br.close()

asyncio.run(main())
shutil.rmtree(T, ignore_errors=True)
print(f'\n{n[0] - len(fails)}/{n[0]} checks passed')
if fails: print('FAILED:\n - ' + '\n - '.join(fails)); sys.exit(1)
