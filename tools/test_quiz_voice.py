"""Quiz voice rule browser test (Stage 3, approved by Emmanuel 2026-11-16):  python3 tools/test_quiz_voice.py [shots_dir]
The rule is data (quiz-rules voice, per age band). Phone portrait 390x844, preview content.
 LITTLE (ages 5-7): when a question appears the voice reads the question AND every answer - picture answers too
   (Animal Quiz, Flag Quiz, Quiz Time picture-pick), Letter Hunt, Count It!, Cameroon; no Read to me switch needed.
 BIG (ages 8-13): nothing is read automatically; the speaker button reads the question + every answer; tapping an
   answer says just that answer's word (before Ari's line); a 'Read to me' switch (>= 48 px) that, once on, reads the
   current question at once and every next question automatically, is remembered on this phone per profile (also after
   a reload and in the other quiz players), and stops when turned off.
 Every word the voice says here has a recorded clip (no text-to-speech)."""
import asyncio,threading,functools,http.server,sys,json
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/ew-tests/quiz-voice-shots');OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'tools'))
from content import hydrate
_cat,RECS=hydrate.load(str(ROOT/'content/preview'))
if isinstance(RECS,list):RECS={r['id']:r for r in RECS}
BANANA=RECS['ew.quiz.quiztime-find-banana']['payload']
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
SAID='__said.slice()'
async def clear(pg):await pg.evaluate('__said.length=0')
async def said_after(pg,ms=500):await pg.wait_for_timeout(ms);return await pg.evaluate(SAID)
async def set_age(pg,age):await pg.evaluate("a=>localStorage.setItem('emmaCtryPrefs',JSON.stringify({lang:'en',age:a,guide:true}))",age)
# what each land quiz screen should say: [question, answers...] read from the screen + LANDS + the generator data
LAND_EXPECT="""()=>{const p=placeById(landById(curLand),state.place),G=EWQuiz.generator(p.quiz)||{},q=document.querySelector('.prompt span').textContent;
 let ans=[];if(screen==='wcount'){const N=wDeck(p.deck).items;ans=[...document.querySelectorAll('.wn')].map(b=>EWQuiz.deckSay(N[+b.dataset.n-1],G.answerSay))}
 else{const D=wDeck(p.deck).items;ans=[...document.querySelectorAll('[data-ok]')].map(b=>{if(p.mode==='letter')return EWQuiz.deckSay(D.find(x=>x.id===b.textContent.trim()),G.answerSay);return b.getAttribute('aria-label')})}
 return {q,ans,wrong:[...document.querySelectorAll('[data-ok="0"],.wn')].map((b,i)=>i).length}}"""
LANDQ=[('letter','hunt','wquiz'),('nature','animalquiz','wquiz'),('world','flagquiz','wquiz'),('number','count','wcount')]
async def open_land(pg,l,p,scr,r=False):
    await clear(pg);await pg.evaluate(f"go('{scr}',{{l:'{l}',p:'{p}'{',r:1' if r else ''}}})");await pg.wait_for_function(f"screen==='{scr}'")
    return await pg.evaluate(LAND_EXPECT)
async def open_banana(pg):
    await clear(pg);await pg.evaluate("go('qplay',{l:'number',p:'quiztime',b:'ew.quizbank.quiztime',fresh:1})");await pg.wait_for_function("screen==='qplay'")
    await clear(pg);await pg.evaluate("()=>{const s=EWQuiz._state();s.ids=['ew.quiz.quiztime-find-banana'];go('qplay',Object.assign({},s.a,{i:0,keep:1}))}");await pg.wait_for_timeout(100)
async def open_cameroon(pg,pool):
    await pg.evaluate("go('ctry',{c:'cameroon'})");await pg.wait_for_timeout(600)
    await clear(pg);await pg.evaluate(f"go('cquiz',{{c:'cameroon',pool:'{pool}',practice:true,round:['ew.quiz.pilot-cameroon-q01','ew.quiz.pilot-cameroon-q02'],i:0}})");await pg.wait_for_selector('.copt')
    return await pg.evaluate("({q:document.querySelector('#cqp').textContent.trim(),ans:[...document.querySelectorAll('.copt')].map(b=>b.textContent.trim()),key:CT.qcur.key})")
async def clips(pg,texts):
    return await pg.evaluate("async ts=>{const bad=[];for(const t of ts){const u=voiceUrl(t);if(!u){bad.push('no clip: '+t);continue}const r=await fetch(u);if(!r.ok)bad.push(u+' '+t)}return bad}",[t for t in texts if t])
async def main():
    h=functools.partial(Q,directory=str(ROOT));http.server.ThreadingHTTPServer.allow_reuse_address=True
    srv=http.server.ThreadingHTTPServer(('127.0.0.1',0),h);threading.Thread(target=srv.serve_forever,daemon=True).start();url=f'http://127.0.0.1:{srv.server_port}/'
    async with async_playwright() as P:
        b=await P.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
        ctx=await b.new_context(viewport={'width':390,'height':844},device_scale_factor=2,is_mobile=True,has_touch=True);pg=await ctx.new_page()
        errs=[];pg.on('pageerror',lambda e:errs.append('PAGEERR '+str(e)));pg.on('console',lambda m:m.type=='error' and 'favicon' not in m.text and errs.append('CONSOLE '+m.text))
        async def boot(clear_ls=False):
            await pg.goto(url,wait_until='load')
            if clear_ls:await pg.evaluate('localStorage.clear()');await pg.reload(wait_until='load')
            await pg.wait_for_function('LANDS!==null&&screen==="home"&&window.CTRY_READY&&window.EWQuiz',timeout=30000);await pg.evaluate(HOOK)
        await boot(True)
        heard=set()
        # ================= LITTLE (5-7) =================
        await set_age(pg,'little')
        for l,p,scr in LANDQ:
            e=await open_land(pg,l,p,scr);s=await said_after(pg)
            heard.update([e['q']]+e['ans'])
            ok(e['q'] in s and all(a and a in s for a in e['ans']),f'LITTLE {p}: question + every answer read on show {e["ans"]} (missing {[a for a in e["ans"] if a not in s]})')
            ok(not await pg.query_selector('#qread'),f'LITTLE {p}: no Read to me switch (everything is read anyway)')
            if p=='animalquiz':await pg.screenshot(path=str(OUT/'little-animal.png'))
        await open_banana(pg);s=await said_after(pg)
        words=[v['en'] for v in BANANA['optionSay'].values()]
        ok(BANANA['prompt']['en'] in s and all(w in s for w in words),f'LITTLE Quiz Time picture-pick: question + every picture answer read {words}')
        e=await open_cameroon(pg,'little');s=await said_after(pg)
        ok(e['q'] in s and all(a in s for a in e['ans']),f'LITTLE Cameroon: question + every answer read on show')
        ok(not await pg.query_selector('#qread'),'LITTLE Cameroon: no switch')
        # ================= BIG (8-13) =================
        await set_age(pg,'big')
        for l,p,scr in LANDQ:
            e=await open_land(pg,l,p,scr);s=await said_after(pg)
            ok(not s,f'BIG {p}: nothing read automatically {s[:3]}')
            ok(await pg.is_visible('#qread') and await pg.get_attribute('#qread','aria-checked')=='false',f'BIG {p}: Read to me switch visible, off')
            bb=await pg.evaluate("(()=>{const r=document.querySelector('#qread').getBoundingClientRect();return [r.width,r.height]})()");ok(bb[0]>=48 and bb[1]>=48,f'BIG {p}: switch is a big enough button {bb}')
            await clear(pg);await pg.click('.say');s=await said_after(pg,150)
            ok(e['q'] in s and all(a in s for a in e['ans']),f'BIG {p}: speaker reads the question + every answer')
            # tap a wrong answer -> its word first
            sel='.wn' if scr=='wcount' else '[data-ok]'
            idx=await pg.evaluate(f"""(()=>{{const bs=[...document.querySelectorAll('{sel}')];return bs.findIndex(b=>{'b.dataset.n!=document.querySelectorAll(".wobj").length' if scr=='wcount' else 'b.dataset.ok==="0"'})}})()""")
            await clear(pg);await pg.locator(sel).nth(idx).click();s=await said_after(pg,200)
            ok(s and s[-2]==e['ans'][idx] if len(s)>=2 else False,f'BIG {p}: tapping an answer says that answer\'s word ({e["ans"][idx]!r}) then Ari\'s try-again {s[-2:]}')
            if p=='flagquiz':await pg.screenshot(path=str(OUT/'big-flag.png'))
        await open_banana(pg);s=await said_after(pg)
        ok(not s,f'BIG Quiz Time: nothing read automatically {s[:2]}')
        await clear(pg);await pg.click('#qsay');s=await said_after(pg,150)
        ok(BANANA['prompt']['en'] in s and all(w in s for w in words),'BIG Quiz Time: speaker reads question + every picture answer')
        wrong_id=[o for o in BANANA['options'] if o!=BANANA['answerKey']][0]
        await clear(pg);await pg.click(f'.qscr [data-o="{wrong_id}"]');s=await said_after(pg,200)
        ok(s and s[0]==BANANA['optionSay'][wrong_id]['en'],f'BIG Quiz Time: tapping a picture says its word first {s[:2]}')
        await clear(pg);await pg.click(f'.qscr [data-o="{BANANA["answerKey"]}"]');s=await said_after(pg,200)
        ok(s and s[0]==BANANA['optionSay'][BANANA['answerKey']]['en'],f'BIG Quiz Time: tapping the right picture says its word, then the praise {s[:2]}')
        e=await open_cameroon(pg,'big');s=await said_after(pg)
        ok(not s,f'BIG Cameroon: nothing read automatically {s[:2]}')
        ok(await pg.is_visible('#qread'),'BIG Cameroon: Read to me switch visible')
        wr=await pg.evaluate("[...document.querySelectorAll('.copt')].findIndex(b=>b.dataset.o!==CT.qcur.key)")
        await clear(pg);await pg.locator('.copt').nth(wr).click();s=await said_after(pg,200)
        ok(s and s[0]==e['ans'][wr],f'BIG Cameroon: tapping an answer says it first {s[:2]}')
        # ---- the switch: on -> reads now, stays on for the next question, after a reload, in the other players
        e=await open_land(pg,'nature','animalquiz','wquiz')
        await clear(pg);await pg.click('#qread');s=await said_after(pg,200)
        ok(await pg.get_attribute('#qread','aria-checked')=='true' and e['q'] in s and all(a in s for a in e['ans']),'BIG: turning Read to me on reads the question + answers at once')
        pref=await pg.evaluate("JSON.parse(localStorage.emmaQuiz).profiles.default.prefs");ok(pref=={'readAloud':True},f'BIG: the switch is kept on this phone (profile default) {pref}')
        e=await open_land(pg,'nature','animalquiz','wquiz',r=True);s=await said_after(pg)
        ok(e['q'] in s and all(a in s for a in e['ans']) and await pg.get_attribute('#qread','aria-checked')=='true','BIG: next question is read automatically while the switch is on')
        await pg.screenshot(path=str(OUT/'big-read-on.png'))
        await boot();await set_age(pg,'big')
        e=await open_land(pg,'world','flagquiz','wquiz');s=await said_after(pg)
        ok(e['q'] in s and all(a in s for a in e['ans']),'BIG: still on after closing and reopening the app')
        await open_banana(pg);s=await said_after(pg)
        ok(BANANA['prompt']['en'] in s and await pg.get_attribute('#qread','aria-checked')=='true','BIG: on in Quiz Time too')
        e=await open_cameroon(pg,'big');s=await said_after(pg)
        ok(e['q'] in s and all(a in s for a in e['ans']),'BIG: on in the Cameroon quiz too')
        await pg.click('#qread');ok(await pg.get_attribute('#qread','aria-checked')=='false','BIG: switch turns off')
        e=await open_land(pg,'number','count','wcount');s=await said_after(pg)
        ok(not s,f'BIG: off again -> nothing read automatically {s[:2]}')
        # another profile keeps its own switch
        await pg.evaluate("localStorage.setItem('emmaProfile','kid2')");await pg.evaluate("EWQuiz.progress.readAloud(true)");await pg.evaluate("localStorage.removeItem('emmaProfile')")
        ok(not await pg.evaluate("EWQuiz.progress.readAloud()"),'the switch is per profile')
        # French: the switch label and the words come in French
        await pg.evaluate("EWi18n.set('fr')");await pg.wait_for_function("EWi18n.lang==='fr'",timeout=20000);await pg.wait_for_timeout(500)
        await open_land(pg,'nature','animalquiz','wquiz');lab=(await pg.text_content('#qread')).strip()
        ok('Lis-moi' in lab,f'French: switch label {lab!r}')
        await pg.evaluate("EWi18n.set('en')");await pg.wait_for_timeout(500)
        bad=await clips(pg,list(heard));ok(not bad,f'every word read in these quizzes has a recorded clip {bad[:3]}')
        ok(not errs,f'no console errors {errs[:4]}')
        await b.close()
    srv.shutdown()
    print(f'\n{len(fails)} FAILED: quiz voice rule test' if fails else '\nALL OK: quiz voice rule test');return 1 if fails else 0
if __name__=='__main__':sys.exit(asyncio.run(main()))
