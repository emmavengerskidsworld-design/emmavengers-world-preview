import json,subprocess,os,re,soundfile as sf,numpy as np,jiwer,sys
from kokoro_onnx import Kokoro
L=json.load(open('lines40.json'))
k=Kokoro('/workspace/kok/kokoro-v1.0.int8.onnx','/workspace/kok/voices-v1.0.bin')
def tail(sr,sh):return (f"asetrate={sr}*{sh},aresample=24000,atempo={1/sh:.6f}," if sh!=1 else "")+"silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse,apad=pad_dur=0.15"
O=[("siwis-en-0.8-1.1","ff_siwis","en-us",0.8,1.1),("REF-mia","af_heart","en-us",0.72,1.18),
   ("isabella-0.85-1.05","bf_isabella","en-gb",0.85,1.05),("isabella-0.85-1.10","bf_isabella","en-gb",0.85,1.10),
   ("emma-0.85-1.10","bf_emma","en-gb",0.85,1.10),("sarah-0.85-1.10","af_sarah","en-us",0.85,1.10),("aoede-0.85-1.10","af_aoede","en-us",0.85,1.10)]
os.makedirs('big',exist_ok=True)
for name,v,lang,sp,sh in O:
  for i,(t,_) in enumerate(L):
    out=f'big/{name}__{i:02d}.mp3'
    if os.path.exists(out):continue
    a,sr=k.create(t,voice=v,speed=sp,lang=lang);sf.write('/tmp/b.wav',a,sr)
    subprocess.run(["ffmpeg","-loglevel","error","-y","-i","/tmp/b.wav","-af",tail(sr,sh),"-ac","1","-b:a","32k",out],check=True)
print("gen ok",flush=True)
from faster_whisper import WhisperModel
def load(f):
    b=subprocess.run(['ffmpeg','-loglevel','error','-i',f,'-f','s16le','-ac','1','-ar','16000','-'],capture_output=True,check=True).stdout
    return np.frombuffer(b,np.int16).astype(np.float32)/32768
N={"one":"1","two":"2","three":"3","four":"4","five":"5","six":"6","seven":"7","eight":"8","nine":"9","ten":"10"}
def norm(s):
    s=s.lower().replace("’","'")
    for a,b in [("we're","we are"),("let's","let us"),("it's","it is"),("you're","you are"),("don't","do not"),("that's","that is"),("what's","what is"),("i'm","i am")]: s=s.replace(a,b)
    s=re.sub(r"[^a-z0-9' ]"," ",s); return " ".join(N.get(w,w) for w in s.split())
R={}
for mn in ["base.en","small.en"]:
  m=WhisperModel(mn,device="cpu",compute_type="int8")
  for name,*_ in O:
    refs,hyps=[],[]
    for i,(t,_) in enumerate(L):
      segs,_=m.transcribe(load(f'big/{name}__{i:02d}.mp3'),language="en",beam_size=1,temperature=0,condition_on_previous_text=False)
      refs.append(norm(t));hyps.append(norm(" ".join(s.text for s in segs)) or "x")
    R.setdefault(name,{})[mn]=(jiwer.wer(refs,hyps),sum(r!=h for r,h in zip(refs,hyps)))
for name in R: print(f"{name:22s} base.en WER {R[name]['base.en'][0]*100:5.1f}% ({R[name]['base.en'][1]}/40 lines with errors)  small.en WER {R[name]['small.en'][0]*100:5.1f}% ({R[name]['small.en'][1]}/40)")
json.dump(R,open('big.json','w'),indent=1)
