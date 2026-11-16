import numpy as np,subprocess,glob,os,json
v=np.load('/workspace/kok/voices-v1.0.bin')
ref=v['ff_siwis']
def cos(a,b):a=a.reshape(-1);b=b.reshape(-1);return float(a@b/np.linalg.norm(a)/np.linalg.norm(b))
names=['af_heart','af_bella','af_nicole','af_sarah','bf_emma','af_aoede','af_kore','bf_isabella','af_jessica','af_river','af_sky','af_alloy','bf_alice','bf_lily','af_nova']
print("embedding cosine vs ff_siwis:")
for n in sorted(names,key=lambda n:-cos(v[n],ref)):
    if n in v: print(f"  {n:12s} {cos(v[n],ref):.3f}")
import librosa
def f0(f):
    y,sr=librosa.load(f,sr=16000)
    p,vf,_=librosa.pyin(y,fmin=120,fmax=500,sr=sr)
    return float(np.nanmedian(p)), float(np.mean(librosa.feature.spectral_centroid(y=y,sr=sr)))
out={}
for var in sorted({os.path.basename(f).split('__')[0] for f in glob.glob('/workspace/voice-samples/*.mp3')}):
    vals=[f0(f) for f in glob.glob(f'/workspace/voice-samples/{var}__*.mp3')]
    out[var]=(np.mean([a for a,b in vals]),np.mean([b for a,b in vals]))
    print(f"{var:40s} medianF0 {out[var][0]:6.1f} Hz  centroid {out[var][1]:6.0f} Hz")
