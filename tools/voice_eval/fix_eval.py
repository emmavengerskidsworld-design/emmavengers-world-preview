#!/usr/bin/env python3
"""ASR check of voice set-ups on the same real app lines (docs/voice-fix.md).
  python3 tools/voice_eval/fix_eval.py gen  <lines.json> <outdir>     render each candidate (fix_samples.VARIANTS) per line
  python3 tools/voice_eval/fix_eval.py asr  <lines.json> <outdir> [model]   whisper (default small.en, float32) -> <outdir>/asr.json + WER table
lines.json = [[text, current_clip_path], ...]; the current clip is scored as variant 'A-current'."""
import os, sys, json, re, subprocess, collections
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fix_samples as FS

ONES = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS = 'x x twenty thirty forty fifty sixty seventy eighty ninety'.split()
UK = {'neighbor': 'neighbour', 'neighbors': 'neighbours', 'color': 'colour', 'colorful': 'colourful', 'colors': 'colours',
      'savior': 'saviour', 'favorite': 'favourite', 'center': 'centre', 'traveling': 'travelling', 'gray': 'grey',
      'okay': 'ok', 'arc': 'ark'}

def say(n):
    n = int(n)
    if n < 20: return ONES[n]
    if n < 100: return TENS[n // 10] + ('' if n % 10 == 0 else ' ' + ONES[n % 10])
    if n < 1000: return ONES[n // 100] + ' hundred' + ('' if n % 100 == 0 else ' and ' + say(n % 100))
    if n < 1000000: return say(n // 1000) + ' thousand' + ('' if n % 1000 == 0 else ' ' + say(n % 1000))
    return str(n)

def norm(s):
    s = re.sub(r'(?<=\d),(?=\d{3})', '', s)
    s = re.sub(r'\d+', lambda m: ' ' + say(m.group()) + ' ', s)
    s = s.lower().replace('’', "'").replace('é', 'e')
    for a, b in [("we're", 'we are'), ("don't", 'do not'), ("won't", 'will not'), ("didn't", 'did not'), ("it's", 'it is'),
                 ("let's", 'let us'), ("that's", 'that is'), ("i'm", 'i am'), ("you've", 'you have'), ("i'll", 'i will'),
                 ("here's", 'here is'), ("can't", 'cannot'), ("isn't", 'is not'), ("doesn't", 'does not')]:
        s = s.replace(a, b)
    s = re.sub(r"(\w)-(\w)", r"\1 \2", s)
    s = re.sub(r"[^a-z0-9' ]", ' ', s).replace(" '", ' ').replace("' ", ' ')
    return ' '.join(UK.get(w, w) for w in s.split())

def gen(lines, out, variants=None):
    from kokoro_onnx import Kokoro
    import voice_lexicon
    ks = {}
    for vid, (label, voice, lang, speed, pitch, model, br, lexon) in FS.VARIANTS.items():
        if variants and vid not in variants: continue
        k = ks.get(model) or ks.setdefault(model, Kokoro(os.path.join(FS.KOK, FS.MODELS[model]), os.path.join(FS.KOK, 'voices-v1.0.bin')))
        os.makedirs(os.path.join(out, vid), exist_ok=True)
        for t, cur in lines:
            f = os.path.join(out, vid, FS.vh(t) + '.mp3')
            if os.path.exists(f): continue
            ph = voice_lexicon.phonemize(t, lang, k.tokenizer.phonemize)[0] if lexon else None
            a, sr = k.create(ph, voice=voice, speed=speed, lang=lang, is_phonemes=True) if ph else k.create(t, voice=voice, speed=speed, lang=lang)
            FS.write_mp3([FS.tidy(a, sr, pitch)], f, br)
        print('rendered', vid, flush=True)

def asr(lines, out, model='small.en'):
    import jiwer
    from faster_whisper import WhisperModel
    m = WhisperModel(model, device='cpu', compute_type='float32', cpu_threads=8)  # int8 gives garbage on this CPU (tested)
    res = json.load(open(os.path.join(out, 'asr.json'))) if os.path.exists(os.path.join(out, 'asr.json')) else {}
    vids = ['A-current'] + [v for v in FS.VARIANTS if os.path.isdir(os.path.join(out, v))]
    for vid in vids:
        R = res.setdefault(vid, {})
        for t, cur in lines:
            if t in R: continue
            f = os.path.join(ROOT, cur) if vid == 'A-current' else os.path.join(out, vid, FS.vh(t) + '.mp3')
            segs, _ = m.transcribe(FS.decode(f, 16000), language='en', beam_size=5, condition_on_previous_text=False,
                                     no_speech_threshold=None, log_prob_threshold=None)
            R[t] = ' '.join(s.text for s in segs).strip()
        json.dump(res, open(os.path.join(out, 'asr.json'), 'w'), indent=0, ensure_ascii=False)
        print('asr', vid, flush=True)
    print(f"{'variant':26s} WER (all words)  lines with an error")
    for vid in vids:
        refs = [norm(t) for t, _ in lines]; hyps = [norm(res[vid][t]) for t, _ in lines]
        bad = sum(r != h for r, h in zip(refs, hyps))
        print(f'{vid:26s} {jiwer.wer(refs, hyps)*100:6.1f}%          {bad}/{len(lines)}')

if __name__ == '__main__':
    cmd, lj, out = sys.argv[1:4]
    lines = json.load(open(lj))
    if cmd == 'gen': gen(lines, out, sys.argv[4].split(',') if len(sys.argv) > 4 else None)
    else: asr(lines, out, *(sys.argv[4:5]))
