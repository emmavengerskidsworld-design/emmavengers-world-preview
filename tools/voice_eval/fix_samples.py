#!/usr/bin/env python3
"""Voice-fix comparison samples (Stage 2 'heavy voice' report, docs/voice-fix.md).
Makes the same 4 real app lines in each candidate set-up, one MP3 per variant (lines joined with short pauses):
  python3 tools/voice_eval/fix_samples.py /workspace/stage2-shots/voice-fix
Variant A is the CURRENT app clips copied from voice/ (not regenerated)."""
import os, sys, json, subprocess, tempfile
import numpy as np, soundfile as sf
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import voice_lexicon
KOK = os.environ.get('KOKORO_DIR', '/workspace/kok')

LINES = {
 'book': "Isaac and Rebekah had twin boys. Esau was born first, red and hairy! He grew up loving to hunt outdoors. Jacob was quieter and liked to stay at home among the tents.",
 'ari': "Ari and Ezra flew to a classroom in Cameroon. The children were making a big map.",
 'quiz': "One website says Yaoundé has 'about one million' people. Newer UN data gives a much larger figure. What should you do?",
 'tricky': "An Emmavengers World Story, by Cletus Emmanuel.",
 'tricky2': "Esther drew green hills. Tchami drew wide grassland in the north.",
}
# id: (label, kokoro voice, lang, speed, pitch, model, bitrate, lexicon)
VARIANTS = {
 'B-isabella-natural':      ('bf_isabella natural speed, no pitch shift, clean model, 48k', 'bf_isabella', 'en-gb', 0.95, 1.0, 'fp32', '48k', False),
 'C1-heart-bright':         ('af_heart (top Kokoro voice, American), natural, clean, 48k', 'af_heart', 'en-us', 0.95, 1.0, 'fp32', '48k', False),
 'C2-bella-bright':         ('af_bella (warm bright American), natural, clean, 48k',      'af_bella', 'en-us', 0.95, 1.0, 'fp32', '48k', False),
 'C3-emma-british':         ('bf_emma (lighter British), natural, clean, 48k',            'bf_emma', 'en-gb', 0.95, 1.0, 'fp32', '48k', False),
 'C4-aoede-crisp':          ('af_aoede (cleanest tone: highest HNR, low breath), natural, clean, 48k', 'af_aoede', 'en-us', 0.95, 1.0, 'fp32', '48k', False),
 'C5-jessica-light':        ('af_jessica (light, crisp, high CPPS), natural, clean, 48k', 'af_jessica', 'en-us', 0.95, 1.0, 'fp32', '48k', False),
 'C6-alice-british-crisp':  ('bf_alice (British, light, little breath noise), natural, clean, 48k', 'bf_alice', 'en-gb', 0.95, 1.0, 'fp32', '48k', False),
 'C7-kore-firm':            ('af_kore (clearest/firmest by CPPS, a bit lower pitch), natural, clean, 48k', 'af_kore', 'en-us', 0.95, 1.0, 'fp32', '48k', False),
 'D1-heart-fixed-words':    ('af_heart + pronunciation dictionary',                       'af_heart', 'en-us', 0.95, 1.0, 'fp32', '48k', True),
 'D3-aoede-fixed-words':    ('af_aoede natural + pronunciation dictionary (recommended)',  'af_aoede', 'en-us', 0.95, 1.0, 'fp32', '48k', True),
 'D2-isabella-fixed-words': ('bf_isabella natural + pronunciation dictionary',             'bf_isabella', 'en-gb', 0.95, 1.0, 'fp32', '48k', True),
}
MODELS = {'int8': 'kokoro-v1.0.int8.onnx', 'fp32': 'models/kokoro-v1.0.onnx', 'fp16': 'models/kokoro-v1.0.fp16.onnx'}

def vh(t):
    h = 0x811c9dc5; b = t.encode('utf-16-le')
    for i in range(0, len(b), 2):
        h ^= b[i] | (b[i+1] << 8); h = (h * 0x01000193) & 0xffffffff
    return f'{h:08x}'

def decode(f, sr=24000):
    b = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', f, '-f', 's16le', '-ac', '1', '-ar', str(sr), '-'], capture_output=True, check=True).stdout
    return np.frombuffer(b, np.int16).astype(np.float32) / 32768

def tidy(a, sr, pitch):
    """Same tail as gen_voice.py: optional pitch shift, trim silences. Returns float array."""
    with tempfile.TemporaryDirectory() as d:
        i, o = os.path.join(d, 'i.wav'), os.path.join(d, 'o.wav')
        sf.write(i, a, sr)
        af = '' if pitch == 1.0 else f'asetrate={sr}*{pitch},aresample=24000,atempo={1/pitch:.6f},'
        af += 'silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse'
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', i, '-af', af, '-ar', '24000', o], check=True)
        return sf.read(o)[0]

def write_mp3(chunks, out, bitrate):
    gap = np.zeros(int(24000 * 0.7), np.float32)
    a = np.concatenate([np.concatenate([c, gap]) for c in chunks])
    with tempfile.TemporaryDirectory() as d:
        w = os.path.join(d, 'a.wav'); sf.write(w, a, 24000)
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', w, '-ac', '1', '-b:a', bitrate, out], check=True)

def main(outdir, keep_lines=False):
    os.makedirs(outdir, exist_ok=True)
    order = ['book', 'ari', 'quiz', 'tricky', 'tricky2']
    # A: current clips straight from the app
    chunks = [decode(os.path.join(ROOT, 'voice', vh(LINES[k]) + '.mp3')) for k in order]
    write_mp3(chunks, os.path.join(outdir, 'A-current.mp3'), '32k')   # mp3 re-encode at the same 32k as the app
    if keep_lines:
        for k in order:
            subprocess.run(['cp', os.path.join(ROOT, 'voice', vh(LINES[k]) + '.mp3'), os.path.join(outdir, 'lines', f'A-current__{k}.mp3')])
    from kokoro_onnx import Kokoro
    ks = {}
    meta = {'A-current': 'the app now: bf_isabella, speed 0.85, pitch 1.05 (resample+stretch), int8 model, 32k MP3'}
    for vid, (label, voice, lang, speed, pitch, model, br, lexon) in VARIANTS.items():
        k = ks.get(model) or ks.setdefault(model, Kokoro(os.path.join(KOK, MODELS[model]), os.path.join(KOK, 'voices-v1.0.bin')))
        chunks = []
        for key in order:
            t = LINES[key]
            ph = voice_lexicon.phonemize(t, lang, k.tokenizer.phonemize)[0] if lexon else None
            a, sr = k.create(ph, voice=voice, speed=speed, lang=lang, is_phonemes=True) if ph else k.create(t, voice=voice, speed=speed, lang=lang)
            c = tidy(a, sr, pitch); chunks.append(c)
            if keep_lines:
                write_mp3([c], os.path.join(outdir, 'lines', f'{vid}__{key}.mp3'), br)
        write_mp3(chunks, os.path.join(outdir, vid + '.mp3'), br)
        meta[vid] = label
        print('wrote', vid, flush=True)
    json.dump({'lines': [LINES[k] for k in order], 'variants': meta}, open(os.path.join(outdir, 'samples.json'), 'w'), indent=1, ensure_ascii=False)

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '/workspace/stage2-shots/voice-fix'
    os.makedirs(os.path.join(out, 'lines'), exist_ok=True)
    main(out, keep_lines=True)
