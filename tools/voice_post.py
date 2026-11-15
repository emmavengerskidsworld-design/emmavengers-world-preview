#!/usr/bin/env python3
"""Voice set-up as DATA -> Kokoro style + ffmpeg filters. Used by tools/gen_voice.py and tools/voice_eval/*.

locales.json "voice" record (all optional except voice):
  "voice": "af_aoede",                          main Kokoro voice
  "blend": [["af_kore", 0.2]],                  mix in other voices' style (weights; main voice gets the rest)
  "speed": 0.95, "pitch": 1.0,                  pitch 1.0 = no pitch processing
  "model": "fp32", "bitrate": "48k",
  "post": {                                     clean-up after synthesis, each step optional:
    "highpass": 90,                               Hz, removes rumble/low breath
    "presence": {"f": 3200, "g": 2.0, "w": 1.2},  dB boost (octaves wide) = crisper consonants
    "air":      {"f": 7500, "g": -3.0},           high-shelf cut of the breathy 'air' band
    "deess":    0.3,                              ffmpeg deesser intensity 0..1 (softens hissy s)
    "denoise":  6,                                afftdn noise reduction in dB (light = 4-8)
    "gate":     {"threshold": 0.015, "ratio": 2}  soft gate: quiets breath between words
  }"""


def style(k, v):
    """Kokoro style for a voice record: the voice name, or a weighted blend array."""
    blend = v.get('blend') or []
    if not blend:
        return v['voice']
    rest = 1.0 - sum(w for _, w in blend)
    if rest <= 0:
        raise ValueError('blend weights must leave a share for the main voice')
    s = k.get_voice_style(v['voice']) * rest
    for name, w in blend:
        s = s + k.get_voice_style(name) * w
    return s


def filters(post):
    """ffmpeg -af steps (list of strings) for a 'post' record."""
    p = post or {}
    f = []
    if p.get('highpass'):
        f.append(f"highpass=f={p['highpass']}")
    if p.get('denoise'):
        f.append(f"afftdn=nr={p['denoise']}:nf=-50:tn=1")
    if p.get('presence'):
        q = p['presence']
        f.append(f"equalizer=f={q['f']}:t=o:w={q.get('w', 1.2)}:g={q['g']}")
    if p.get('air'):
        q = p['air']
        f.append(f"highshelf=f={q['f']}:g={q['g']}")
    if p.get('deess'):
        f.append(f"deesser=i={p['deess']}")
    if p.get('gate'):
        q = p['gate']
        f.append(f"agate=threshold={q.get('threshold', 0.015)}:ratio={q.get('ratio', 2)}:attack=3:release=80:range=0.25")
    return f
