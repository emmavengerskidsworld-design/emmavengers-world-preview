"""Age switch on every quiz screen (16 Nov 2026, Emmanuel: 'the 8-13 quiz still reads automatically'): fresh phone
(no choice yet = Little, reads aloud), then tap 'Big 8-13' ON THE QUIZ SCREEN: the quiz redraws silent with the
Read to me switch, and the choice holds in every other quiz. Phone 390x844.  python3 tools/test_quiz_age_switch.py"""
import asyncio,threading,functools,http.server,sys
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a):pass
fails=[]
def ok(c,m):
    print(('OK   ' if c else 'FAIL ')+m,flush=True)
    if not c:fails.append(m)
HOOK="()=>{const o=say;window.__said=[];say=function(t,h,q){__said.push(...[].concat(t).filter(Boolean));return o(t,h,q)}}"
SCR=[("go('wquiz',{l:'letter',p:'hunt'})",'wquiz'),("go('wquiz',{l:'nature',p:'animalquiz'})",'wquiz'),("go('wquiz',{l:'world',p:'flagquiz'})",'wquiz'),
     ("go('wcount',{l:'number',p:'count'})",'wcount'),("go('qplay',{l:'number',p:'quiztime',b:'ew.quizbank.quiztime',fresh:1})",'qplay'),("go('cquiz',{c:'cameroon'})",'cquiz')]
async def main():
    srv=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Q,directory=str(ROOT)));threading.Thread(target=srv.serve_forever,daemon=True).start()
    async with async_playwright() as P:
        b=await P.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
        pg=await (await b.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)).new_page()
        errs=[];pg.on('pageerror',lambda e:errs.append(str(e)))
        await pg.goto(f'http://127.0.0.1:{srv.server_port}/');await pg.evaluate('localStorage.clear()');await pg.reload()
        await pg.wait_for_function('LANDS!==null&&screen==="home"&&window.CTRY_READY&&window.EWQuiz',timeout=30000);await pg.evaluate(HOOK)
        # fresh phone: the age switch is visible on the first quiz, Little selected
        await pg.evaluate(SCR[1][0]);await pg.wait_for_timeout(500)
        ok(await pg.is_visible('.qagebtn[data-age="little"].on') and await pg.is_visible('.qagebtn[data-age="big"]'),'fresh phone: age switch visible on the quiz, Little selected')
        bb=await pg.evaluate("(()=>{const r=document.querySelector('.qagebtn').getBoundingClientRect();return r.height})()");ok(bb>=48,f'age buttons >= 48 px ({bb})')
        ok(len(await pg.evaluate('__said'))>0,'fresh phone (Little): question read aloud')
        await pg.evaluate('__said.length=0;stopVoice()');await pg.tap('.qagebtn[data-age="big"]');await pg.wait_for_timeout(700)
        ok(await pg.evaluate("JSON.parse(localStorage.getItem('emmaCtryPrefs')).age")=='big','tapping Big saves the choice')
        ok(await pg.is_visible('.qagebtn[data-age="big"].on') and await pg.is_visible('#qread'),'after Big: Big selected + Read to me switch shown')
        ok((await pg.evaluate('__said'))==[],f'after Big: nothing read automatically {await pg.evaluate("__said")}')
        for js,scr in SCR:
            await pg.evaluate("go('home')");await pg.wait_for_timeout(200);await pg.evaluate('__said.length=0;stopVoice()')
            await pg.evaluate(js);await pg.wait_for_timeout(700)
            if scr=='cquiz':
                await pg.click('[data-pool="big"]');await pg.wait_for_selector('.copt');await pg.evaluate('__said.length=0');await pg.wait_for_timeout(500)
            ok(await pg.is_visible('.qagebtn[data-age="big"].on'),f'{js}: Big shown selected')
            ok((await pg.evaluate('__said'))==[],f'{js}: silent as Big {await pg.evaluate("__said")}')
        await pg.tap('.qagebtn[data-age="little"]');await pg.wait_for_timeout(800)
        ok(await pg.evaluate("JSON.parse(localStorage.getItem('emmaCtryPrefs')).age")=='little' and len(await pg.evaluate('__said'))>0,'switching back to Little reads aloud again')
        ok(not errs,f'no page errors {errs[:2]}')
        await b.close()
    srv.shutdown();print('ALL OK: quiz age switch' if not fails else f'FAILED {len(fails)}');sys.exit(1 if fails else 0)
asyncio.run(main())
