#!/usr/bin/env python3
"""Breathiness / crispness check of Kokoro voice set-ups (docs/voice-fix.md).
Measures on the same real app lines, before MP3 coding:
  HNR   harmonics-to-noise ratio (Praat, dB): higher = cleaner, less 'air' in the voice
  CPPS  smoothed cepstral peak prominence (Praat, dB): higher = clearer, less breathy (standard clinical breathiness measure)
  air   share of energy 8-12 kHz in vowel-like (voiced) frames (dB): higher = more breath noise riding on the vowels
  python3 tools/voice_eval/breathiness.py [out.json]"""
import os, sys, json, tempfile, subprocess
import numpy as np, soundfile as sf, parselmouth
from parselmouth.praat import call
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fix_samples as FS

LINES = [FS.LINES['book'], FS.LINES['ari'], FS.LINES['quiz']]

def measure(a, sr):
    snd = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)
    hnr = call(snd.to_harmonicity_cc(0.01, 120, 0.1, 1.0), 'Get mean', 0, 0)
    pcg = call(snd, 'To PowerCepstrogram', 60, 0.002, 5000, 50)
    cpps = call(pcg, 'Get CPPS', 'no', 0.01, 0.001, 60, 330, 0.05, 'parabolic', 0.001, 0, 'Exponential decay', 'Robust')
    pitch = snd.to_pitch(0.01, 120, 500)
    f0 = pitch.selected_array['frequency']
    # air: 8-12k energy share in voiced 20 ms frames
    hop = int(0.01 * sr); win = int(0.02 * sr); shares = []
    for i, f in enumerate(f0):
        s = i * hop
        if f <= 0 or s + win > len(a): continue
        X = np.abs(np.fft.rfft(a[s:s + win] * np.hanning(win))) ** 2; fr = np.fft.rfftfreq(win, 1 / sr)
        shares.append(X[(fr >= 8000) & (fr < 12000)].sum() / (X.sum() + 1e-12))
    return hnr, cpps, 10 * np.log10(np.mean(shares) + 1e-12), float(np.median(f0[f0 > 0]))

def setups():
    S = [('A-current-pipeline(int8,0.85,pitch1.05)', 'bf_isabella', 'en-gb', 0.85, 1.05, 'int8'),
         ('isabella int8 0.85 no-pitch', 'bf_isabella', 'en-gb', 0.85, 1.0, 'int8'),
         ('isabella fp32 0.85 no-pitch', 'bf_isabella', 'en-gb', 0.85, 1.0, 'fp32'),
         ('isabella fp32 0.95 no-pitch', 'bf_isabella', 'en-gb', 0.95, 1.0, 'fp32'),
         ('isabella fp32 1.0 no-pitch', 'bf_isabella', 'en-gb', 1.0, 1.0, 'fp32')]
    for v, lang in [('af_heart', 'en-us'), ('af_bella', 'en-us'), ('af_nicole', 'en-us'), ('af_sarah', 'en-us'), ('af_aoede', 'en-us'),
                    ('af_kore', 'en-us'), ('af_nova', 'en-us'), ('af_river', 'en-us'), ('af_alloy', 'en-us'), ('af_jessica', 'en-us'),
                    ('af_sky', 'en-us'), ('bf_emma', 'en-gb'), ('bf_alice', 'en-gb'), ('bf_lily', 'en-gb')]:
        S.append((f'{v} fp32 0.95', v, lang, 0.95, 1.0, 'fp32'))
    return S

def main(out):
    from kokoro_onnx import Kokoro
    ks = {}; res = {}
    for name, v, lang, sp, pitch, model in setups():
        k = ks.get(model) or ks.setdefault(model, Kokoro(os.path.join(FS.KOK, FS.MODELS[model]), os.path.join(FS.KOK, 'voices-v1.0.bin')))
        m = []
        for t in LINES:
            a, sr = k.create(t, voice=v, speed=sp, lang=lang)
            a = FS.tidy(a, sr, pitch)
            m.append(measure(a, 24000))
        res[name] = [float(np.mean([x[i] for x in m])) for i in range(4)]
        print(f'{name:42s} HNR {res[name][0]:5.1f}  CPPS {res[name][1]:5.1f}  air {res[name][2]:6.1f}  f0 {res[name][3]:4.0f}', flush=True)
    json.dump(res, open(out, 'w'), indent=1)

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '/workspace/stage2-asr/voicefix/breathiness.json')
