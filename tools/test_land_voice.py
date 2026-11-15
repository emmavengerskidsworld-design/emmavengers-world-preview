"""Number Land / World Land voice on a fresh phone (Pixel 7, slow 4G via tools/throttle_server.py, nothing cached yet):
   python3 tools/test_land_voice.py [--budget 400] [--rate 200000]
Guards the bugs Emmanuel recorded on his phone (Stage 2 preview, 15 Nov 2026):
  1. land intros (Number Land, World Land) play to the end - not cut, not started late
  2. a number card plays every one of its lines in order, each to the end ("One!" "One apple!"; "Two!" "One, two!" "Two ducks!")
  3. Count It! first round reads the intro then the question; the speaker button reads the QUESTION
  4. tap-to-sound / enter-to-sound under --budget ms (median)
A clip counts as cut when its buffer source is stopped (or the media element paused) before its end, other than by
the child's own next tap. Prints a JSON timeline on failure."""
import asyncio,sys,json,statistics,subprocess,os,socket,time,argparse
from playwright.async_api import async_playwright
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap=argparse.ArgumentParser();ap.add_argument('--budget',type=float,default=400);ap.add_argument('--rate',default='200000');A=ap.parse_args()
INIT=r"""
window.__ev=[];window.__t0=0;addEventListener('pointerdown',()=>{window.__t0=performance.now()},true);
const vhx=t=>{let h=0x811c9dc5;for(let i=0;i<t.length;i++){h^=t.charCodeAt(i);h=Math.imul(h,0x01000193)>>>0}return h.toString(16).padStart(8,'0')};
window.__vh=vhx;
const op=HTMLMediaElement.prototype.play;HTMLMediaElement.prototype.play=function(){const el=this;
 el.addEventListener('playing',()=>{if(el.muted)return;const e={t:performance.now(),src:el.currentSrc,k:'el',dur:el.duration*1000};__ev.push(e);
  const pz=()=>{if(!e.end){e.end=performance.now();e.cut=el.currentTime<el.duration-0.05}};el.addEventListener('ended',()=>{e.end=performance.now();e.cut=false},{once:true});el.addEventListener('pause',pz,{once:true});el.addEventListener('emptied',pz,{once:true})},{once:true});return op.apply(this,arguments)};
if(window.AudioBufferSourceNode){const os=AudioBufferSourceNode.prototype.start,ost=AudioBufferSourceNode.prototype.stop;
 AudioBufferSourceNode.prototype.start=function(when){const n=this,c=n.context,now=performance.now(),d=Math.max(0,((when||0)-c.currentTime)*1000);
  if(n.__src){const e={t:now+d,src:n.__src,k:'buf',dur:n.buffer.duration*1000};n.__e=e;__ev.push(e);n.addEventListener('ended',()=>{if(!e.end){e.end=performance.now();e.cut=false}})}return os.apply(this,arguments)};
 AudioBufferSourceNode.prototype.stop=function(){const e=this.__e;if(e&&!e.end){const now=performance.now();e.end=now;e.cut=now<e.t+e.dur-50}return ost.apply(this,arguments)}}
"""
fails=[]
def ok(c,msg,extra=None):
    print(('ok    ' if c else 'FAIL  ')+msg,flush=True)
    if not c:
        fails.append(msg)
        if extra is not None: print('      ',json.dumps(extra)[:1500])
async def timeline(pg,since):
    return await pg.evaluate('s=>__ev.filter(e=>e.t>=s).map(e=>({t:Math.round(e.t-s),src:e.src.split("/").pop(),k:e.k,dur:Math.round(e.dur),end:e.end?Math.round(e.end-s):null,cut:!!e.cut}))',since)
async def vh(pg,t): return await pg.evaluate('t=>__vh(t)',t)
async def wait_quiet(pg,ms=15000):
    try: await pg.wait_for_function('!vPlaying()&&__ev.length&&__ev.every(e=>e.end)',timeout=ms)
    except Exception: pass
async def expect_lines(pg,since,texts,tag):
    """the lines play in this order, each started and finished, none cut"""
    await wait_quiet(pg)
    tl=await timeline(pg,since);want=[await vh(pg,t)+'.mp3' for t in texts]
    got=[e['src'] for e in tl]
    ok(got[:len(want)]==want,f'{tag}: plays {texts}',tl)
    cut=[e for e in tl if e['cut'] or e['end'] is None]
    ok(not cut,f'{tag}: no line cut off',tl)
    return tl
async def main():
    s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close()
    try: prev=open('/tmp/emma-lat-rate').read()
    except Exception: prev=None
    open('/tmp/emma-lat-rate','w').write(A.rate)
    srv=subprocess.Popen([sys.executable,os.path.join(ROOT,'tools','throttle_server.py'),ROOT,str(port)]);time.sleep(1)
    lat={}
    try:
        async with async_playwright() as p:
            b=await p.chromium.launch(args=['--autoplay-policy=user-gesture-required'])
            ctx=await b.new_context(**p.devices['Pixel 7']);await ctx.add_init_script(INIT);pg=await ctx.new_page()
            errs=[];pg.on('pageerror',lambda e:errs.append(str(e)))
            # 0. a quick child on a phone that has visited ONCE before (Emmanuel's case): World Land tapped 1 s after the
            #    first tap. The service worker must already be in charge after that first visit (app shell only, a few MB)
            #    - before the Stage 2 fix it waited for the whole 55 MB core, so every clip came from the network (~2 s).
            qc=await b.new_context(**p.devices['Pixel 7']);await qc.add_init_script(INIT);qp=await qc.new_page()
            await qp.goto(f'http://127.0.0.1:{port}/',wait_until='load')
            await qp.wait_for_function('typeof LANDS!=="undefined"&&LANDS!==null&&screen==="home"',timeout=120000)
            t_sw=time.time()
            try: await qp.wait_for_function('!!(navigator.serviceWorker&&navigator.serviceWorker.controller)',timeout=120000)
            except Exception: pass
            sw_s=round(time.time()-t_sw,1);ctl=await qp.evaluate('!!(navigator.serviceWorker&&navigator.serviceWorker.controller)')
            ok(ctl and sw_s<=90,f'first visit: service worker in charge after {sw_s} s (app shell only)')
            await qp.wait_for_timeout(8000)   # the child looks at the map a little (intros reach the phone)
            await qp.reload(wait_until='load');await qp.wait_for_function('typeof LANDS!=="undefined"&&LANDS!==null&&screen==="home"',timeout=60000)
            await qp.tap('#title');await qp.wait_for_timeout(1000)
            wi=await qp.evaluate("LANDS.lands.find(l=>l.id==='world').intro")
            print('      before tap:',await qp.evaluate("(()=>{const u=voiceUrl(LANDS.lands.find(l=>l.id==='world').intro);return {inMemory:vBuf.has(u),sw:!!(navigator.serviceWorker&&navigator.serviceWorker.controller)}})()"))
            t0=await qp.evaluate('performance.now()');await qp.tap('.wsignb[data-l="world"]')
            tl=await expect_lines(qp,t0,[wi],'second visit, quick child: World Land intro');lat['quick enter world']=tl[0]['t'] if tl else None
            await qc.close()
            await pg.goto(f'http://127.0.0.1:{port}/',wait_until='load')
            await pg.wait_for_function('typeof LANDS!=="undefined"&&LANDS!==null&&screen==="home"',timeout=120000)
            await pg.tap('#title');await pg.wait_for_timeout(3000);await pg.evaluate('stopVoice()')
            L=await pg.evaluate("(()=>{const n=LANDS.lands.find(l=>l.id==='number'),w=LANDS.lands.find(l=>l.id==='world');return {nIntro:n.intro,wIntro:w.intro,places:n.places.map(p=>({id:p.id,type:p.type,intro:p.intro}))}})()")
            # 1. Number Land intro
            t0=await pg.evaluate('performance.now()');await pg.tap('.wsignb[data-l="number"]')
            tl=await expect_lines(pg,t0,[L['nIntro']],'Number Land intro');lat['enter number']=tl[0]['t'] if tl else None
            # 2. number cards 1, 2, 4
            cards=[x for x in L['places'] if x['type']=='cards'][0];count=[x for x in L['places'] if x['type']=='count'][0]
            await pg.tap(f'.wplace[data-p="{cards["id"]}"]');await pg.wait_for_function("screen==='wcards'");await wait_quiet(pg)
            say=await pg.evaluate("LANDS.decks[placeById(landById('number'),'%s').deck].items.map(it=>it.say)"%cards['id'])
            taps=[]
            for i in (0,1,3):
                await pg.evaluate("document.querySelectorAll('.pop').forEach(x=>x.remove());stopVoice();__ev=[]")
                t0=await pg.evaluate('performance.now()');await pg.tap(f'.wtile[data-i="{i}"]')
                tl=await expect_lines(pg,t0,say[i],f'number card {i+1}')
                if tl: taps.append(tl[0]['t'])
            lat['card taps']=taps
            await pg.evaluate("document.querySelectorAll('.pop').forEach(x=>x.remove());stopVoice()")
            # 3. Count It!
            await pg.evaluate("go('land',{id:'number'})");await wait_quiet(pg);await pg.evaluate('stopVoice();__ev=[]')
            t0=await pg.evaluate('performance.now()');await pg.tap(f'.wplace[data-p="{count["id"]}"]');await pg.wait_for_function("screen==='wcount'")
            ask=await pg.evaluate("document.querySelector('.prompt span').textContent")
            await expect_lines(pg,t0,[count['intro'],ask],'Count It! first round: intro then question')
            await pg.evaluate('__ev=[]');t0=await pg.evaluate('performance.now()');await pg.tap('.prompt .say')
            await expect_lines(pg,t0,[ask],'Count It! speaker button reads the question')
            # 4. World Land intro
            await pg.evaluate("go('home')");await wait_quiet(pg);await pg.evaluate('stopVoice();__ev=[]')
            t0=await pg.evaluate('performance.now()');await pg.tap('.wsignb[data-l="world"]')
            tl=await expect_lines(pg,t0,[L['wIntro']],'World Land intro');lat['enter world']=tl[0]['t'] if tl else None
            ok(not errs,f'no page errors {errs[:3]}')
            await b.close()
    finally:
        srv.terminate()
        if prev is None:
            try: os.remove('/tmp/emma-lat-rate')
            except Exception: pass
        else: open('/tmp/emma-lat-rate','w').write(prev)
    allv=[v for k,v in lat.items() if k!='card taps' and v is not None]+lat.get('card taps',[])
    med=statistics.median(allv) if allv else None
    ok(med is not None and med<=A.budget and max(allv)<=A.budget*3,f'voice starts fast: median {med} ms, all {lat}')
    print('LAND VOICE','PASSED' if not fails else 'FAILED: '+'; '.join(fails));return 1 if fails else 0
sys.exit(asyncio.run(main()))
