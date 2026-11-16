import glob,os,re,json,collections,subprocess
from faster_whisper import WhisperModel
import jiwer, numpy as np
def load(f):
    b=subprocess.run(['ffmpeg','-loglevel','error','-i',f,'-f','s16le','-ac','1','-ar','16000','-'],capture_output=True,check=True).stdout
    return np.frombuffer(b,np.int16).astype(np.float32)/32768
T={"ari-hub":"We're in Cameroon! What shall we explore?",
   "learn-card":"Cameroon is a country in Africa. It is next to the ocean.",
   "quiz":"Which way is the library from Start on our practice map?",
   "house":"Find the spoon in the kitchen. Tap it!",
   "bible":"In the beginning, God made the heavens and the earth."}
def norm(s):
    s=s.lower().replace("we're","we are").replace("’","'")
    s=re.sub(r"[^a-z' ]"," ",s); return " ".join(s.split())
res={}
for mname in ["base.en","small.en"]:
    m=WhisperModel(mname,device="cpu",compute_type="int8")
    for f in sorted(glob.glob("/workspace/voice-samples/*.mp3")):
        var,line=os.path.basename(f)[:-4].split("__")
        segs,_=m.transcribe(load(f),language="en",beam_size=1,temperature=0,condition_on_previous_text=False)
        hyp=" ".join(s.text for s in segs)
        res.setdefault(var,{}).setdefault(mname,{})[line]=(hyp,jiwer.wer(norm(T[line]),norm(hyp)))
json.dump(res,open("/workspace/stage2-asr/wer.json","w"),indent=1)
print(f"{'variant':40s} base.en  small.en")
for var in sorted(res):
    w=[sum(v[1] for v in res[var][mn].values())/5 for mn in ["base.en","small.en"]]
    print(f"{var:40s} {w[0]*100:6.1f}% {w[1]*100:6.1f}%")
for var in sorted(res):
    for mn in ["base.en","small.en"]:
        for line,(h,w) in res[var][mn].items():
            if w>0: print(var,mn,line,round(w,2),"|",h)
