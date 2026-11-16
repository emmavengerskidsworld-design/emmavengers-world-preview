"""Quiz engine browser test (Stage 3):  python3 tools/test_quiz.py [shots_dir]
Phone portrait 390x844, preview content (drafts). Checks:
 - Number Land shows the draft 'Quiz Time!' place (type bank) and it opens the generic quiz player (qplay)
 - every one of the 6 response types (single-choice, picture-pick, count, true-false, order, match) plays:
   the question text is the record's text, the voice says the question on screen entry (+ every answer for ages 5-7),
   the speaker button reads the question AND every answer, a wrong answer is gentle (option greyed + disabled, Ari's
   try-again line, the hint, Skip), the right answer shows the feedback and Next; stars at the end
 - every line the quiz can speak has a recorded clip (English E3 voice folder voice/, French voice/fr/)
 - English -> French switch redraws the same question in French (French clips), and back
 - progress is stored on this phone only (localStorage emmaQuiz, per profile), nothing else
 - the land quizzes on the engine: Letter Hunt / Animal Quiz / Flag Quiz / Count It! play a full round to the stars
 - all quiz buttons >= 48 px, no horizontal overflow, no console errors
 - OFFLINE: after one online visit the service worker serves the quiz (screens, pictures and voice clips)"""
import asyncio,threading,functools,http.server,sys,json,os,re
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/ew-tests/quiz-shots');OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'tools'))
from content import hydrate
_cat,_recs=hydrate.load(str(ROOT/'content/preview'));RECS={r['id']:r for r in _recs} if isinstance(_recs,list) else _recs
BANK=RECS['ew.quizbank.quiztime'];ITEMS=[RECS[i] for i in BANK['payload']['items']]
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a):pass
    def handle(self):
        try:super().handle()
        except Exception:pass
fails=[]
def ok(c,m):
    print(('OK   ' if c else 'FAIL ')+m,flush=True)
    if not c:fails.append(m)
HOOK="""()=>{if(window.__said)return;const o=say;window.__said=[];say=function(t,h,q){__said.push(...[].concat(t).filter(Boolean));return o(t,h,q)}}"""
SIZES="""()=>{const W=innerWidth;const small=[...document.querySelectorAll('#main button')].filter(b=>{const r=b.getBoundingClientRect();return r.width&&b.offsetParent&&(r.width<47.5||r.height<47.5)}).map(b=>(b.id||b.className)+' '+Math.round(b.getBoundingClientRect().width)+'x'+Math.round(b.getBoundingClientRect().height));
 return {sw:document.documentElement.scrollWidth,W,small:small.slice(0,5),broken:[...document.images].filter(i=>i.getAttribute('src')&&i.complete&&!i.naturalWidth).map(i=>i.src)}}"""
def T(lt,lang='en'):return lt.get(lang) if isinstance(lt,dict) else lt
async def clip_ok(pg,texts):
    return await pg.evaluate("async ts=>{const bad=[];for(const t of ts){const u=voiceUrl(t);if(!u){bad.push('no url: '+t);continue}try{const r=await fetch(u);if(!r.ok)bad.push(u+' '+t)}catch(e){bad.push('fetch failed: '+u+' '+t)}}return bad}",texts)
async def start_all(pg):
    """open Quiz Time and put all 8 questions in the round (one of each type at least)"""
    await pg.evaluate("go('qplay',{l:'number',p:'quiztime',b:'ew.quizbank.quiztime',fresh:1})");await pg.wait_for_function("screen==='qplay'")
    await pg.evaluate("ids=>{const s=EWQuiz._state();s.ids=ids;go('qplay',Object.assign({},s.a,{i:0}))}",[i['id'] for i in ITEMS])
    await pg.wait_for_timeout(200)
def correct_clicks(it):
    p=it['payload'];t=p['responseType'];k=p['answerKey']
    if t in('single-choice','picture-pick','true-false'):return [f'.qscr [data-o="{k}"]']
    if t=='count':return [f'.qscr .wn[data-o="{k}"]']
    if t=='order':return [f'.qorder .copt[data-o="{x}"]' for x in k]
    if t=='match':return [s for a,b in k.items() for s in (f'.qleft[data-o="{a}"]',f'.qright[data-t="{b}"]')]
def wrong_clicks(it):
    p=it['payload'];t=p['responseType'];k=p['answerKey']
    if t in('single-choice','picture-pick'):return [f'.qscr [data-o="{[o for o in p["options"] if o!=k][0]}"]']
    if t=='true-false':return [f'.qscr [data-o="{"false" if k=="true" else "true"}"]']
    if t=='count':return None
    if t=='order':return [f'.qorder .copt[data-o="{x}"]' for x in reversed(k)]
    if t=='match':a=list(k)[0];bad=[v for v in k.values() if v!=k[a]][0];return [f'.qleft[data-o="{a}"]',f'.qright[data-t="{bad}"]']
async def play_item(pg,it,i,lang='en',wrong=True):
    p=it['payload'];typ=p['responseType'];tag=f'[{lang}] q{i+1} {typ}'
    ok(await pg.evaluate('screen')=='qplay',f'{tag}: on the quiz screen')
    ok(await pg.get_attribute('.qscr','data-type')==typ,f'{tag}: screen plays the {typ} type')
    ok((await pg.text_content('#qprompt span')).strip()==T(p['prompt'],lang),f'{tag}: question text = record text')
    said=await pg.evaluate('__said.slice()')
    ok(T(p['prompt'],lang) in said,f'{tag}: the voice says the question on screen entry')
    # the answers the speaker must read
    ans=[]
    if typ=='true-false':
        ui=RECS['ew.ui.app']['payload']['strings'];ans=[T(ui['quizTrue'],lang),T(ui['quizFalse'],lang)]
    elif typ!='count':
        say=p.get('optionSay',{})
        ans=[T(say[o],lang) if o in say else T(v,lang) for o,v in p.get('options',{}).items()]+[T(v,lang) for v in p.get('targets',{}).values()]
    if ans:ok(all(a in said for a in ans),f'{tag}: ages 5-7 hear every answer on screen entry {[a for a in ans if a not in said]}')
    await pg.evaluate('__said.length=0');await pg.click('#qsay');await pg.wait_for_timeout(100)
    sp=await pg.evaluate('__said.slice()')
    ok(T(p['prompt'],lang) in sp and all(a in sp for a in ans),f'{tag}: speaker reads the question and every answer')
    r=await pg.evaluate(SIZES);ok(r['sw']<=r['W']+1,f'{tag}: no horizontal overflow');ok(not r['small'],f'{tag}: buttons >= 48px {r["small"]}');ok(not r['broken'],f'{tag}: pictures load {r["broken"][:2]}')
    if i==0 or typ in('order','match'):await pg.screenshot(path=str(OUT/f'{lang}-q{i+1}-{typ}.png'),full_page=True)
    w=wrong_clicks(it) if wrong else None
    if w:
        await pg.evaluate('__said.length=0')
        for s in w:await pg.click(s);await pg.wait_for_timeout(60)
        await pg.wait_for_timeout(150)
        ok(await pg.is_visible('#qhintline') and (await pg.text_content('#qhintline')).strip()==T(p['hint'],lang),f'{tag}: a miss shows the hint')
        ok(await pg.is_visible('#qskip'),f'{tag}: a miss offers Skip')
        tl=[T(RECS[x]['payload']['text'],lang) for x in BANK['payload']['lines']['tryAgain']]
        sd=await pg.evaluate('__said.slice()')
        ok(any(t in sd for t in tl),f'{tag}: Ari says a gentle try-again line (pre-written)')
        if typ in('single-choice','picture-pick','true-false'):ok(await pg.is_disabled(w[0]),f'{tag}: the wrong answer is greyed out')
        ok(not await pg.query_selector('.qscr .wrong-x, .qscr .lives, .qscr .timer'),f'{tag}: no crosses, lives or timers')
    for s in correct_clicks(it):await pg.click(s);await pg.wait_for_timeout(60)
    await pg.wait_for_selector('#qnext',timeout=4000)
    fb=(await pg.text_content('.cfb.ok')).strip()
    ok(T(p['feedback'],lang) in fb,f'{tag}: right answer shows the feedback')
    await pg.evaluate('__said.length=0');await pg.click('#qnext');await pg.wait_for_timeout(150)
async def main():
    h=functools.partial(Q,directory=str(ROOT));http.server.ThreadingHTTPServer.allow_reuse_address=True
    srv=http.server.ThreadingHTTPServer(('127.0.0.1',0),h);threading.Thread(target=srv.serve_forever,daemon=True).start();url=f'http://127.0.0.1:{srv.server_port}/'
    async with async_playwright() as P:
        b=await P.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
        ctx=await b.new_context(viewport={'width':390,'height':844},device_scale_factor=2,is_mobile=True,has_touch=True);pg=await ctx.new_page()
        errs=[];pg.on('pageerror',lambda e:errs.append('PAGEERR '+str(e)));pg.on('console',lambda m:m.type=='error' and 'favicon' not in m.text and errs.append('CONSOLE '+m.text));pg.on('response',lambda r:r.status>=400 and errs.append(f'HTTP {r.status} {r.url}'))
        net=[];pg.on('request',lambda r:net.append(r.url))
        await pg.goto(url,wait_until='load');await pg.evaluate('localStorage.clear()');await pg.reload(wait_until='load')
        await pg.wait_for_function('LANDS!==null&&screen==="home"&&window.CTRY_READY&&window.EWQuiz',timeout=30000)
        await pg.evaluate(HOOK)
        # Number Land -> Quiz Time (draft place, preview only)
        await pg.evaluate("go('land',{id:'number'})");await pg.wait_for_function("screen==='land'")
        ok(await pg.is_visible('.wplace[data-p="quiztime"]'),'Number Land shows the Quiz Time place (preview)')
        ok(await pg.is_visible('.wplace[data-p="count"]'),'Count It! still there')
        await pg.screenshot(path=str(OUT/'number-land.png'))
        await pg.click('.wplace[data-p="quiztime"]');await pg.wait_for_function("screen==='qplay'",timeout=5000)
        st=await pg.evaluate("(()=>{const s=EWQuiz._state();return {n:s.ids.length,band:s.band,sel:s.R.selection,level:s.level,ids:s.ids}})()")
        ok(st['n']==4 and st['band']=='5-7' and st['sel']=='leitner',f'Quiz Time: a round of 4 for ages 5-7 with spaced review (rules from data) {st}')
        diffs=[RECS[i]['tags'].get('difficulty') for i in st['ids']]
        ok(diffs.count('starter')>=min(4,sum(1 for x in ITEMS if x['tags'].get('difficulty')=='starter')) ,f'adaptive: a new child starts with starter questions first {diffs}')
        said=await pg.evaluate('__said.slice()')
        ok(T(BANK['payload']['intro']) in said,'first question: the quiz intro is spoken')
        # every type, English
        await pg.evaluate('__said.length=0');await start_all(pg)
        for i,it in enumerate(ITEMS):
            await play_item(pg,it,i,'en',wrong=(i<6))
        ok(await pg.evaluate('screen')=='qdone',f'after the last question: the stars screen')
        await pg.wait_for_selector('.qdone .bigstars');stars=await pg.evaluate("[...document.querySelectorAll('.qdone .bigstars span')].filter(s=>!(s.getAttribute('style')||'').includes('grayscale')).length")
        ok(stars in(1,2,3),f'stars shown ({stars}) - many misses still give at least 1 star')
        await pg.screenshot(path=str(OUT/'en-done.png'),full_page=True)
        done_lines=[T(RECS[x]['payload']['text']) for x in BANK['payload']['lines']['done']]
        sd=await pg.evaluate('__said.slice()');ok(any(t in sd for t in done_lines),'Ari says the done line')
        # progress stored on the phone only, per profile
        pr=await pg.evaluate("JSON.parse(localStorage.getItem('emmaQuiz')||'{}')")
        prof=(pr.get('profiles') or {}).get('default') or {}
        ok(len(prof.get('items',{}))>=8 and 'ew.quizbank.quiztime' in prof.get('banks',{}),'progress saved on this phone (Leitner boxes per question, best stars per quiz)')
        ok(not re.search(r'name|answer|text',json.dumps(prof.get('items',{}))),'progress holds no names or answer texts')
        bx=prof['items'].get(ITEMS[6]['id'],{})
        ok(bx.get('box')==1 and bx.get('due') is not None,f'right first time -> Leitner box up (box {bx.get("box")})')
        bx0=prof['items'].get(ITEMS[0]['id'],{})
        ok(bx0.get('box')==0,f'a miss -> box 0 (comes back in the next round) (box {bx0.get("box")})')
        ok(not [u for u in net if not u.startswith(url) and not u.startswith('data:') and not u.startswith('blob:')],'no request leaves the site')
        # voice clips for every quiz line (English)
        lines=await pg.evaluate('__quizVoice()')
        bad=await clip_ok(pg,lines);ok(len(lines)>40 and not bad,f'every English quiz line has an E3 clip ({len(lines)} lines) {bad[:3]}')
        # French
        await pg.evaluate("EWi18n.set('fr')");await pg.wait_for_function("EWi18n.lang==='fr'",timeout=15000);await pg.wait_for_timeout(600)
        await pg.evaluate('__said.length=0');await start_all(pg)
        await pg.evaluate("(()=>{})()")
        for i,it in enumerate(ITEMS[:6]):
            await play_item(pg,it,i,'fr',wrong=(i in(0,3,4)))
        frl=await pg.evaluate('__quizVoice()')
        ok(any('Vrai' in x for x in frl),'French quiz lines are French')
        bad=await clip_ok(pg,frl);ok(not bad,f'every French quiz line has a ff_siwis clip in voice/fr/ ({len(frl)}) {bad[:3]}')
        langs=await pg.evaluate("ts=>ts.map(t=>EWi18n.langOf(t))",frl[:20])
        ok(all(l=='fr' for l in langs),f'French lines are spoken by the French voice {set(langs)}')
        # mid-question language switch redraws the same question
        await start_all(pg);await pg.evaluate("EWi18n.set('en')");await pg.wait_for_function("EWi18n.lang==='en'",timeout=15000);await pg.wait_for_timeout(600)
        ok(await pg.evaluate('screen')=='qplay' and (await pg.text_content('#qprompt span')).strip()==T(ITEMS[0]['payload']['prompt']),'switching language mid-quiz redraws the same question in English')
        # land quizzes on the engine
        for land,place,scr in [('letter','hunt','wquiz'),('nature','animalquiz','wquiz'),('world','flagquiz','wquiz'),('number','count','wcount')]:
            await pg.evaluate(f"go('land',{{id:'{land}'}})");await pg.click(f'.wplace[data-p="{place}"]');await pg.wait_for_function(f"screen==='{scr}'")
            R=await pg.evaluate(f"(()=>{{const p=placeById(landById('{land}'),'{place}');const R=wRules(p);return {{quiz:p.quiz,sel:R.selection,choices:EWQuiz.choicesFor(R),three:R.stars.three}}}})()")
            ok(R['quiz'] and R['sel']=='random' and R['choices']==3,f'{place}: rules come from its quiz bank {R}')
            for k in range(12):
                if await pg.evaluate('screen')=='wreward':break
                n=await pg.evaluate("document.querySelectorAll(scr==='wcount'?'.wn':'[data-ok]').length".replace('scr',f"'{scr}'"))
                ok(n==3,f'{place} q{k+1}: 3 answer buttons') if k==0 else None
                if scr=='wcount':
                    cnt=await pg.evaluate("document.querySelectorAll('.wobj').length")
                    await pg.click(f'.wn[data-n="{cnt}"]')
                else:await pg.click('[data-ok="1"]')
                await pg.wait_for_function(f"screen!=='{scr}'||!document.querySelector('[data-ok],.wn')||[...document.querySelectorAll('[data-ok],.wn')].every(b=>b.disabled)",timeout=3000)
                await pg.wait_for_function(f"screen==='wreward'||(screen==='{scr}'&&[...document.querySelectorAll('[data-ok],.wn')].some(b=>!b.disabled))",timeout=8000)
            ok(await pg.evaluate('screen')=='wreward',f'{place}: full round to the stars screen')
            s3=await pg.evaluate("[...document.querySelectorAll('.bigstars span')].filter(s=>!(s.getAttribute('style')||'').includes('grayscale')).length")
            ok(s3==3,f'{place}: no mistakes = 3 stars')
        # offline
        info=await pg.evaluate("""async()=>{await navigator.serviceWorker.ready;const t0=Date.now();
          for(;;){if(navigator.serviceWorker.controller){const ks=await caches.keys();const want=JSON.parse((await fetch('sw.js').then(r=>r.text())).match(/ASSETS=(\\[.*?\\]);/)[1]).length;
            let c=0;for(const k of ks.filter(k=>k.startsWith('emma-house-')))c+=(await (await caches.open(k)).keys()).length;if(c>=want)return {ok:true,c,want,ms:Date.now()-t0}}
            if(Date.now()-t0>180000)return {timeout:true};await new Promise(z=>setTimeout(z,1000))}}""")
        ok(info.get('ok'),f'offline worker has the app cached {info}')
        await ctx.set_offline(True);await pg.reload(wait_until='load')
        await pg.wait_for_function('LANDS!==null&&window.CTRY_READY&&window.EWQuiz',timeout=30000);await pg.evaluate(HOOK)
        await start_all(pg)
        ok(await pg.evaluate('screen')=='qplay' and (await pg.text_content('#qprompt span')).strip()==T(ITEMS[0]['payload']['prompt']),'OFFLINE: Quiz Time opens')
        bad=await clip_ok(pg,await pg.evaluate('__quizVoice()'));ok(not bad,f'OFFLINE: every quiz voice clip comes from the phone {bad[:3]}')
        await play_item(pg,ITEMS[0],0,'en',wrong=False)
        await ctx.set_offline(False)
        ok(not errs,f'no console errors {errs[:4]}')
        await b.close()
    srv.shutdown()
    print(f'\n{"ALL OK" if not fails else str(len(fails))+" FAILED"}: quiz engine browser test');return 1 if fails else 0
sys.exit(asyncio.run(main()))
