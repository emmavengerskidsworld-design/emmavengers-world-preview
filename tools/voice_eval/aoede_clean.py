#!/usr/bin/env python3
"""Aoede clean-up trials (docs/voice-fix.md, step 2): blend + post filters as data (tools/voice_post.py).
  python3 tools/voice_eval/aoede_clean.py measure            breathiness/brightness table for every trial
  python3 tools/voice_eval/aoede_clean.py samples OUT ID..   5-line samples (MP3) for chosen trials
  python3 tools/voice_eval/aoede_clean.py gen LINES OUTDIR ID..   one clip per line (for fix_eval.py asr)"""
import os, sys, json, subprocess, tempfile
import numpy as np, soundfile as sf
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import fix_samples as FS, breathiness as BR, voice_post, voice_lexicon

EQ = {'highpass': 90, 'presence': {'f': 3200, 'g': 2.0, 'w': 1.2}, 'air': {'f': 7500, 'g': -3.0}}
EQ2 = {'highpass': 100, 'presence': {'f': 3000, 'g': 3.0, 'w': 1.2}, 'air': {'f': 6500, 'g': -5.0}, 'deess': 0.4}
T = {  # id: (description, voice record)
 'base':        ('D3 as picked: af_aoede 0.95', {}),
 'eq':          ('+ high-pass 90 Hz, +2 dB presence 3.2 kHz, -3 dB air shelf 7.5 kHz', {'post': EQ}),
 'eq-dn':       ('+ EQ + light denoise (afftdn 6 dB)', {'post': dict(EQ, denoise=6)}),
 'eq-dn-gate':  ('+ EQ + denoise + soft gate between words', {'post': dict(EQ, denoise=6, gate={'threshold': 0.015, 'ratio': 2})}),
 'eq-deess':    ('+ EQ + de-esser 0.3', {'post': dict(EQ, deess=0.3)}),
 'k20':         ('blend 80% aoede / 20% kore', {'blend': [['af_kore', 0.2]]}),
 'k30':         ('blend 70% aoede / 30% kore', {'blend': [['af_kore', 0.3]]}),
 'k20-eq':      ('blend 80/20 kore + EQ', {'blend': [['af_kore', 0.2]], 'post': EQ}),
 'k20-eq-dn':   ('blend 80/20 kore + EQ + light denoise', {'blend': [['af_kore', 0.2]], 'post': dict(EQ, denoise=6)}),
 'k30-eq-dn':   ('blend 70/30 kore + EQ + light denoise', {'blend': [['af_kore', 0.3]], 'post': dict(EQ, denoise=6)}),
 'eq2':         ('+ firmer EQ: high-pass 100, +3 dB presence 3 kHz, -5 dB air shelf 6.5 kHz, de-ess 0.4', {'post': EQ2}),
 'n20':         ('blend 80% aoede / 20% nova (least airy voice)', {'blend': [['af_nova', 0.2]]}),
 'n30':         ('blend 70% aoede / 30% nova', {'blend': [['af_nova', 0.3]]}),
 'al20':        ('blend 80% aoede / 20% alloy', {'blend': [['af_alloy', 0.2]]}),
 'k15n15':      ('blend 70% aoede / 15% kore / 15% nova', {'blend': [['af_kore', 0.15], ['af_nova', 0.15]]}),
 'n20-eq':      ('blend 80/20 nova + EQ', {'blend': [['af_nova', 0.2]], 'post': EQ}),
 'k15n15-eq':   ('blend 70/15/15 kore+nova + EQ', {'blend': [['af_kore', 0.15], ['af_nova', 0.15]], 'post': EQ}),
 'k15n15-eq2':  ('blend 70/15/15 kore+nova + firmer EQ', {'blend': [['af_kore', 0.15], ['af_nova', 0.15]], 'post': EQ2}),
 'k20-eq-s1':   ('blend 80/20 kore + EQ, speed 1.0', {'blend': [['af_kore', 0.2]], 'post': EQ, 'speed': 1.0}),
}

_k = None
def kok():
    global _k
    if _k is None:
        from kokoro_onnx import Kokoro
        _k = Kokoro(os.path.join(FS.KOK, FS.MODELS['fp32']), os.path.join(FS.KOK, 'voices-v1.0.bin'))
    return _k

def render(text, rec):
    """float32 24 kHz audio, after post filters and silence trim (as gen_voice.py)."""
    k = kok(); v = dict({'voice': 'af_aoede', 'lang': 'en-us', 'speed': 0.95}, **rec)
    ph = voice_lexicon.phonemize(text, v['lang'], k.tokenizer.phonemize)[0]
    st = voice_post.style(k, v)
    a, sr = k.create(ph, voice=st, speed=v['speed'], lang=v['lang'], is_phonemes=True) if ph else k.create(text, voice=st, speed=v['speed'], lang=v['lang'])
    af = voice_post.filters(v.get('post')) + ['silenceremove=start_periods=1:start_threshold=-50dB', 'areverse',
                                              'silenceremove=start_periods=1:start_threshold=-50dB', 'areverse']
    with tempfile.TemporaryDirectory() as d:
        i, o = os.path.join(d, 'i.wav'), os.path.join(d, 'o.wav')
        sf.write(i, a, sr)
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', i, '-af', ','.join(af), '-ar', '24000', o], check=True)
        return sf.read(o, dtype='float32')[0]

def centroid(a):
    X = np.abs(np.fft.rfft(a)) ** 2; fr = np.fft.rfftfreq(len(a), 1 / 24000); return float((fr * X).sum() / X.sum())

def measure(ids=None):
    p = '/workspace/stage2-asr/voicefix/aoede_clean.json'
    res = json.load(open(p)) if os.path.exists(p) else {}
    for tid, (desc, rec) in T.items():
        if ids and tid not in ids: continue
        m = []
        for t in BR.LINES:
            a = render(t, rec); m.append(BR.measure(a, 24000) + (centroid(a),))
        r = [float(np.mean([x[i] for x in m])) for i in range(5)]
        res[tid] = dict(zip(['hnr', 'cpps', 'air', 'f0', 'centroid'], r), desc=desc)
        print(f"{tid:12s} HNR {r[0]:5.1f}  CPPS {r[1]:5.1f}  air {r[2]:6.1f}  f0 {r[3]:4.0f}  bright {r[4]:5.0f} Hz  | {desc}", flush=True)
    json.dump(res, open(p, 'w'), indent=1)

if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'measure': measure(sys.argv[2:])
    elif cmd == 'samples':
        out = sys.argv[2]; os.makedirs(out, exist_ok=True)
        for spec in sys.argv[3:]:
            name, tid = spec.split('=')
            FS.write_mp3([render(FS.LINES[k], T[tid][1]) for k in ['book', 'ari', 'quiz', 'tricky', 'tricky2']], os.path.join(out, name + '.mp3'), '48k')
            print('wrote', name, flush=True)
    elif cmd == 'gen':
        lines = json.load(open(sys.argv[2])); out = sys.argv[3]
        for tid in sys.argv[4:]:
            d = os.path.join(out, tid); os.makedirs(d, exist_ok=True)
            for t, _ in lines:
                f = os.path.join(d, FS.vh(t) + '.mp3')
                if not os.path.exists(f): FS.write_mp3([render(t, T[tid][1])], f, '48k')
            print('rendered', tid, flush=True)
