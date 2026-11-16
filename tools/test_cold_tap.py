"""First-visit (NOT yet cached) tap-to-voice latency, English vs French, on a slow phone network:
   python3 tools/test_cold_tap.py [--budget 150] [--wait 3]
A fresh phone (Pixel 7, no service worker cache yet) opens the app over a throttled server (slow 4G: 200 KB/s shared,
150 ms RTT, tools/throttle_server.py), picks the language, waits --wait seconds, opens Cameroon Learn and taps
'next card' 5 times (a child tapping quickly, 0.8 s apart). Stage 2 bug this guards: English lines streamed from the
network on every tap (the English clips sit in the background precache, which pauses whenever the child taps) while
French lines were already on the phone (language pack downloaded urgently). Fails if the median tap-to-sound of either
language is over --budget ms."""
import asyncio,sys,json,statistics,subprocess,os,socket,time,argparse
from playwright.async_api import async_playwright
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap=argparse.ArgumentParser();ap.add_argument('--budget',type=float,default=150);ap.add_argument('--wait',type=float,default=3);A=ap.parse_args()
INIT=open(os.path.join(ROOT,'tools','test_voice_latency.py')).read().split('INIT="""')[1].split('"""')[0]
async def run(p,url,lg):
    b=await p.chromium.launch(args=['--autoplay-policy=user-gesture-required'])
    ctx=await b.new_context(**p.devices['Pixel 7']);await ctx.add_init_script(INIT);pg=await ctx.new_page()
    await pg.goto(url,wait_until='load')
    await pg.wait_for_function('typeof LANDS!=="undefined"&&LANDS!==null&&window.CTRY_READY',timeout=120000)
    await pg.tap('#title');await pg.wait_for_timeout(500)
    await pg.evaluate(f"localStorage.setItem('emmaCtryPrefs',JSON.stringify({{lang:'{lg}',age:'little',guide:false}}));window.EWi18n&&EWi18n.lang!=='{lg}'?EWi18n.set('{lg}'):0")
    await pg.wait_for_timeout(A.wait*1000)
    await pg.evaluate("go('clearn',{c:'cameroon',i:0})");await pg.wait_for_timeout(1500)
    rs=[]
    for i in range(5):
        await pg.evaluate('__ev=[];stopVoice()');await pg.wait_for_timeout(200)
        await pg.tap('#cnext');r=None
        for _ in range(150):
            r=await pg.evaluate('(()=>{const e=__ev.find(x=>x.t>=__t0);return e?[Math.round(e.t-__t0),e.src.split("/").slice(-2).join("/"),e.k||"tts"]:null})()')
            if r:break
            await pg.wait_for_timeout(50)
        rs.append(r);await pg.wait_for_timeout(800)
    await b.close();return rs
async def main():
    s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close()
    try: prev=open('/tmp/emma-lat-rate').read()
    except Exception: prev=None
    open('/tmp/emma-lat-rate','w').write('200000')
    srv=subprocess.Popen([sys.executable,os.path.join(ROOT,'tools','throttle_server.py'),ROOT,str(port)]);time.sleep(1)
    fails=[];out={}
    try:
        async with async_playwright() as p:
            for lg in ('en','fr'):
                rs=await run(p,f'http://127.0.0.1:{port}/',lg);ms=[r[0] for r in rs if r]
                med=statistics.median(ms) if len(ms)==5 else None;out[lg]={'median':med,'taps':rs}
                bad=med is None or med>A.budget
                if bad:fails.append(lg)
                print(f'{"FAIL" if bad else "ok  "} cold Cameroon next card ({lg}): median {med} ms  {rs}',flush=True)
    finally:
        srv.terminate()
        if prev is None:
            try: os.remove('/tmp/emma-lat-rate')
            except Exception: pass
        else: open('/tmp/emma-lat-rate','w').write(prev)
    json.dump(out,open('/tmp/ew-cold-tap.json','w'),indent=1)
    print('COLD TAP','PASSED' if not fails else 'FAILED: '+', '.join(fails));return 1 if fails else 0
sys.exit(asyncio.run(main()))
