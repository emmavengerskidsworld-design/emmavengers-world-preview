#!/usr/bin/env python3
"""Self-check for very short voice lines ("Six!", "Two ducks!"): Kokoro sometimes garbles a line of one to three
words (Stage 2: the old clips said "One apples", "Zikzha" for "Six!", "To you, Duxley" for "Two ducks!"). gen_voice.py
(locales.json voice.verifyShort = max words) renders a few takes, has Whisper listen to each and keeps the first one
heard as written; lines no take passes are listed for a human to review."""
import os, re, sys, subprocess
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'voice_eval'))
_m = None
HOMO = {'too': 'two', 'to': 'two', 'for': 'four', 'won': 'one', 'ate': 'eight', 'tu': 'two'}

def model():
    global _m
    if _m is None:
        from faster_whisper import WhisperModel
        _m = WhisperModel(os.environ.get('VOICE_CHECK_MODEL', 'small.en'), device='cpu', compute_type='float32', cpu_threads=4)  # int8 is unreliable on this CPU
    return _m

def norm(s):
    from fix_eval import norm as n
    return ' '.join(HOMO.get(w, w) for w in n(s).split())

def heard(mp3):
    b = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', mp3, '-f', 's16le', '-ac', '1', '-ar', '16000', '-'], capture_output=True, check=True).stdout
    a = np.frombuffer(b, np.int16).astype(np.float32) / 32768
    a = np.concatenate([np.zeros(4000, np.float32), a, np.zeros(8000, np.float32)])
    segs, _ = model().transcribe(a, language='en', beam_size=5, condition_on_previous_text=False, without_timestamps=True)
    return ' '.join(s.text for s in segs).strip()

def passes(text, mp3):
    h = heard(mp3)
    return norm(h) == norm(text), h

def takes(text, speed):
    """the variants tried, in order: as written, a calm full stop instead of '!',
    no end mark at all (one-word lines like "Six!" grow a vowel tail - "Zexa" - with one),
    then each a touch faster, then as written a touch slower"""
    t2 = re.sub(r'!+$', '.', text)
    t3 = re.sub(r'[!.?]+$', '', text)
    texts = [text] + [t for t in (t2, t3) if t != text]
    texts = list(dict.fromkeys(texts))
    out = [(t, speed) for t in texts]
    out += [(t, round(speed + 0.08, 2)) for t in texts]
    out.append((text, round(speed - 0.05, 2)))
    return out
