#!/usr/bin/env python3
"""Voice clip jobs per language, straight from the content (same spoken-line rules as the app).

  python3 tools/voice_jobs.py --lang fr                 lines of French with no clip yet  -> JSON jobs on stdout
  python3 tools/voice_jobs.py --lang en --all           every English line of the content (to regenerate a voice)
  python3 tools/voice_jobs.py --summary                 per language: lines, clips present, missing

Then:  python3 tools/gen_voice.py jobs.json --locale fr    (voice, speed, pitch and folder come from locales.json)
Rows are [text, path] (+ IPA phonemes for letter sounds). Lines of the English-only modules (House, Bible, Mia's
Day) are not in the content library yet: tools/check_voice.py lists those."""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from content.source import Source
from content.validate import Validator
from content.common import vh

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lines(channel='preview'):
    S = Source(os.path.join(ROOT, 'content', 'src'), ROOT, channel=channel)
    V = Validator(S, os.path.join(ROOT, 'content', 'schema', 'v1'), channel=channel)
    V.run()
    LOC = {l['tag']: l for l in S.cfg['locales']['locales']}
    lex = S.records.get('ew.lexicon.letter-sounds')
    ph = {e['text']: e['ipa'] for e in lex['payload']['entries']} if lex else {}
    out = {}
    for lang, got in V.spoken_by_lang.items():
        for t, (p, lg) in got.items():
            v = (LOC.get(lg) or {}).get('voice')
            if not v: continue
            out.setdefault(lg, {})[t] = (v['pack'] + vh(t) + '.mp3', ph.get(t) if lg == 'en' else None)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lang'); ap.add_argument('--all', action='store_true'); ap.add_argument('--summary', action='store_true')
    ap.add_argument('--channel', default='preview')
    a = ap.parse_args()
    L = lines(a.channel)
    if a.summary or not a.lang:
        for lg, d in sorted(L.items()):
            have = sum(os.path.isfile(os.path.join(ROOT, p)) for p, _ in d.values())
            print(f'{lg}: {len(d)} lines, {have} clips, {len(d) - have} missing')
        return
    rows = []
    for t, (p, ipa) in sorted(L.get(a.lang, {}).items()):
        if a.all or not os.path.isfile(os.path.join(ROOT, p)):
            rows.append([t, p] + ([ipa] if ipa else []))
    print(json.dumps(rows, ensure_ascii=False, indent=0))


if __name__ == '__main__':
    main()
