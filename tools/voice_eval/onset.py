import sys,glob,subprocess,numpy as np,random
def load(f):
    b=subprocess.run(['ffmpeg','-loglevel','error','-i',f,'-f','s16le','-ac','1','-ar','24000','-'],capture_output=True,check=True).stdout
    return np.frombuffer(b,np.int16).astype(np.float32)/32768
def onset(f,rel_db=-20):
    y=load(f);w=240  # 10ms frames
    n=len(y)//w; r=np.sqrt((y[:n*w].reshape(n,w)**2).mean(1)+1e-12); db=20*np.log10(r)
    thr=db.max()+rel_db; i=np.argmax(db>thr); return i*10, len(y)/24
for pat in sys.argv[1:]:
    fs=sorted(glob.glob(pat)); random.seed(1); fs=random.sample(fs,min(150,len(fs)))
    o=[onset(f) for f in fs]; a=np.array([x[0] for x in o])
    print(f"{pat:50s} n={len(fs)} onset(-20dB rel peak) median {np.median(a):.0f} ms  p90 {np.percentile(a,90):.0f} ms  max {a.max():.0f}")
