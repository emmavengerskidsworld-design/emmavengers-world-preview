"""Check the deployed preview site:  python3 tools/verify_preview.py [URL]
online + offline, Cameroon opens, data identical to the pre-Stage-1 files except the documented changes since then
(Stage 2 grammar fields nameDef/nameOf on deck items; French texts arrive in a language pack on the switch; Cameroon's
go-live approval on 2026-11-10: status, editorial.approvalRef, locales.en.status), the language switch (French labels +
full French pack, back to English), and the English voice: a tap plays a clip from voice/ whose bytes are exactly the
repo's (Stage 2 voice fix: af_aoede E3) clip, with no browser text-to-speech fallback."""
import asyncio,json,sys,hashlib,copy
from playwright.async_api import async_playwright
U=sys.argv[1] if len(sys.argv)>1 else 'https://emmavengerskidsworld-design.github.io/emmavengers-world-preview/'
import os;R=os.path.dirname(os.path.dirname(os.path.abspath(__file__)));F=os.path.join(os.path.dirname(os.path.abspath(__file__)),'fixtures','legacy-v0')+'/'
res=[]
INIT=open(os.path.join(R,'tools','test_voice_latency.py')).read().split('INIT="""')[1].split('"""')[0]
GOLIVE=('status',('editorial','approvalRef'),('locales','en','status'))   # Cameroon go-live approval (2026-11-10)
def golive(x):
  x=copy.deepcopy(x)
  for k in GOLIVE:
    k=(k,) if isinstance(k,str) else k;o=x
    for j in k[:-1]:o=o.get(j,{})
    o.pop(k[-1],None)
  return x
def no_fr(x,parent=None):   # the fixture without French texts: they now arrive in the French pack on the switch
  if isinstance(x,dict):return {k:no_fr(v,k) for k,v in x.items() if not(k=='fr' and 'en' in x and parent not in('locales','localeKeys'))}
  if isinstance(x,list):return [no_fr(v,parent) for v in x]
  return x
def no_grammar(L):   # Stage 2 grammar helper fields for question templates (docs/languages.md)
  L=copy.deepcopy(L)
  for d in L.get('decks',{}).values():
    for it in d.get('items',[]):it.pop('nameDef',None);it.pop('nameOf',None)
  return L
def no_stage3(L):   # Stage 3 quiz engine: places gain a 'quiz' link to their quiz bank (rules), new 'bank' places (docs/quiz-engine.md)
  L=copy.deepcopy(L)
  for l in L.get('lands',[]):
    l['places']=[p for p in l.get('places',[]) if p.get('type')!='bank']
    for p in l['places']:p.pop('quiz',None)
  return L
async def voice_tap(pg,lg):
  await pg.evaluate("go('clearn',{c:'cameroon',i:0})");await pg.wait_for_timeout(1500)
  await pg.evaluate('__ev=[];stopVoice()');await pg.wait_for_timeout(200);await pg.tap('#cnext');e=None
  for _ in range(200):
    e=await pg.evaluate('__ev.find(x=>x.t>=__t0)||null')
    if e:break
    await pg.wait_for_timeout(50)
  if not e:return None
  e['ms']=round(e['t']-await pg.evaluate('__t0'));await pg.wait_for_timeout(3000)
  e['all']=await pg.evaluate('__ev.map(x=>x.src)');return e
def ok(c,m): res.append(c); print(('ok   ' if c else 'FAIL ')+m)
async def main():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required']);ctx=await b.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True);await ctx.add_init_script(INIT);pg=await ctx.new_page();errs=[]
    pg.on('pageerror',lambda e:errs.append(str(e)));pg.on('console',lambda m:m.type=='error' and errs.append(m.text+' @ '+str((m.location or {}).get('url',''))))
    await pg.goto(U,wait_until='load');await pg.wait_for_function('typeof LANDS!=="undefined"&&LANDS!==null&&screen==="home"&&window.CTRY_READY',timeout=60000)
    st=await pg.evaluate('EWLib.status()');ok(st['ready'] and st['source']=='network',f"online first visit: release {st['sequence']}, {len(st['fetched'])} files, {st['bytes']/1024:.0f} KB, storage {st['storage']}")
    L=json.loads(await pg.evaluate('JSON.stringify(LANDS)'));ok(no_stage3(no_grammar(L))==json.load(open(F+'lands.json')),'LANDS identical to the pre-Stage-1 lands.json (+ Stage 2 nameDef/nameOf, Stage 3 quiz links / Quiz Time place only)')
    ok(all('nameDef' in i for i in L['decks']['animals']['items']),'Stage 2 grammar fields present on the animal deck')
    pk=json.loads(await pg.evaluate('JSON.stringify(CT.packs.cameroon)'));ok(golive(pk)==golive(no_fr(json.load(open(F+'cameroon.json')))),'Cameroon pack (English) identical to the original, except the go-live approval fields')
    await pg.evaluate("go('land',{id:'world'})");await pg.wait_for_timeout(800)
    await pg.click('.wplace[data-p="cameroon"]');await pg.wait_for_timeout(1500)
    s=await pg.evaluate('screen');t=await pg.evaluate('document.querySelector("#main")?document.querySelector("#main").innerText.slice(0,120):document.body.innerText.slice(0,120)')
    ok(s in('ctry',) or 'Cameroon' in t,f'online: Cameroon opens (screen {s}: {t[:60]!r})');await pg.screenshot(path='/tmp/live-cameroon-online.png')
    # ---- English voice: the tapped line plays the repo's (en.voice in locales.json) clip from voice/, no text-to-speech
    await pg.evaluate("localStorage.setItem('emmaCtryPrefs',JSON.stringify({lang:'en',age:'little',guide:true}))")
    e=await voice_tap(pg,'en')
    if e:
      f=e['src'].split('?')[0].split('/')[-1];loc=os.path.join(R,'voice',f)
      site=bytes(await pg.evaluate("async u=>Array.from(new Uint8Array(await (await fetch(u,{cache:'no-store'})).arrayBuffer()))",e['src']))
      same=os.path.exists(loc) and hashlib.sha256(site).hexdigest()==hashlib.sha256(open(loc,'rb').read()).hexdigest()
      ok(e['src'].split('?')[0].split('/')[-2]=='voice' and same and 'TTS' not in e['all'],f"English tap plays voice/{f} ({e['k']}, {e['ms']} ms after the tap), bytes = repo clip: {same}, no TTS: {'TTS' not in e['all']}")
    else: ok(False,'English tap: no sound started within 10 s')
    # ---- language switch: French labels, the full French pack, French voice, back to English
    await pg.evaluate("go('ctry',{c:'cameroon'})");await pg.wait_for_timeout(1200);await pg.click('.clang[data-lang="fr"]')
    try: await pg.wait_for_function("EWi18n.lang==='fr'&&!document.querySelector('.clang[disabled]')&&(document.querySelector('.cmodes .cmode b')||{}).textContent==='Apprendre'",timeout=30000);fr=True
    except Exception: fr=False
    lab=await pg.evaluate("[...document.querySelectorAll('.cmodes .cmode b')].map(b=>b.textContent)");ok(fr and lab==['Apprendre','Jouer','Quiz','Histoires'],f'switch to French: labels {lab}')
    pk=json.loads(await pg.evaluate('JSON.stringify(CT.packs.cameroon)'));ok(golive(pk)==golive(json.load(open(F+'cameroon.json'))),'French: Cameroon pack with French identical to the original')
    e=await voice_tap(pg,'fr');ok(bool(e) and 'voice/' in e['src'] and 'TTS' not in e['all'],f"French tap plays a recorded clip ({e and e['src'].split('/')[-1]}, {e and e['ms']} ms)")
    await pg.evaluate("go('ctry',{c:'cameroon'})");await pg.wait_for_timeout(1200);await pg.click('.clang[data-lang="en"]')
    try: await pg.wait_for_function("EWi18n.lang==='en'&&(document.querySelector('.cmode[data-mode=learn] b')||{}).textContent==='Learn'",timeout=30000);en=True
    except Exception: en=False
    ok(en,'switch back to English: Learn label')
    # ---- Stage 3 quiz engine: Quiz Time (preview draft) opens, the speaker reads the question from a recorded clip
    ok(await pg.evaluate('!!window.EWQuiz&&!!EWLib.get("ew.quizrules.default")'),'quiz engine loaded with its rules records')
    await pg.evaluate("go('land',{id:'number'})");await pg.wait_for_timeout(900)
    if await pg.is_visible('.wplace[data-p="quiztime"]'):
      await pg.click('.wplace[data-p="quiztime"]');await pg.wait_for_timeout(1500)
      q=await pg.evaluate("[screen,(document.querySelector('#qprompt')||{}).textContent||'',document.querySelectorAll('#main .copt,#main .qtf button,#main .qslot').length]")
      ok(q[0]=='qplay' and q[1].strip() and q[2]>=2,f'Quiz Time opens: {q[1].strip()[:50]!r}, {q[2]} answer buttons')
      await pg.evaluate('__ev=[];stopVoice();window.__t0=performance.now()');await pg.tap('#qsay');e=None
      for _ in range(200):
        e=await pg.evaluate('__ev.find(x=>x.t>=__t0)||null')
        if e:break
        await pg.wait_for_timeout(50)
      await pg.wait_for_timeout(2500);allv=await pg.evaluate('__ev.map(x=>x.src)')
      ok(bool(e) and '/voice/' in e['src'] and 'TTS' not in allv,f"quiz speaker plays recorded clips ({len(allv)} sounds, first {e and e['src'].split('/')[-1]})")
    else: ok(False,'Quiz Time place missing on Number Land (preview should show the draft)')
    await pg.evaluate("go('wquiz',{l:'nature',p:'animalquiz'})");await pg.wait_for_timeout(1200)
    ok(await pg.evaluate("screen==='wquiz'&&document.querySelectorAll('#main [data-ok]').length>=2"),'a land quiz (Animal Quiz) still plays on the engine')
    await pg.evaluate("go('home')");await pg.wait_for_timeout(500)
    info=await pg.evaluate("""async()=>{await navigator.serviceWorker.ready;const t0=Date.now();for(;;){const sw=await fetch('sw.js').then(r=>r.text());const want=JSON.parse(sw.match(/ASSETS=(\\[.*?\\]);/)[1]);
      /* every file of THIS build's core on the phone (the worker takes charge after the shell; the rest downloads in the background) */let have=0;for(const u of want)if(await caches.match(new URL(u,location.href).href,{ignoreSearch:true}))have++;
      if(have>=want.length&&navigator.serviceWorker.controller)return {have,want:want.length,s:(Date.now()-t0)/1000};if(Date.now()-t0>600000)return {timeout:true,have,want:want.length};await new Promise(z=>setTimeout(z,2000))}}""")
    ok(not info.get('timeout'),f'service worker precache complete {info}')
    await ctx.set_offline(True);await pg.reload(wait_until='load')
    await pg.wait_for_function('typeof LANDS!=="undefined"&&LANDS!==null&&screen==="home"&&window.CTRY_READY',timeout=30000)
    st=await pg.evaluate('EWLib.status()');ok(st['source']=='device' and not st['fetched'],f"OFFLINE reload: content from device copy, release {st['sequence']}")
    await pg.evaluate("go('land',{id:'world'})");await pg.wait_for_timeout(800);await pg.click('.wplace[data-p="cameroon"]');await pg.wait_for_timeout(1500)
    s=await pg.evaluate('screen');ok(s=='ctry',f'OFFLINE: Cameroon opens (screen {s})');await pg.screenshot(path='/tmp/live-cameroon-offline.png')
    ok(not errs,f'no page errors {errs[:6]}')
    await b.close()
asyncio.run(main());print('LIVE VERIFY','PASSED' if all(res) else 'FAILED');sys.exit(0 if all(res) else 1)
