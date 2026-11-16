#!/usr/bin/env python3
"""Pronunciation fixes for the recorded voice, kept as DATA (content/voice-lexicon/<lang>.json).

The phonemizer (espeak-ng) guesses names it does not know: 'Yaoundé', 'Tchami', 'Esau', 'Emmavengers' ...
Each entry gives the IPA Kokoro should say for one whole word (matched case-insensitively at word edges,
possessive 's / ’s included). Everything else in the line is phonemized as usual, so a new line that uses a
fixed word is said right automatically - no code change, just add an entry.

  python3 tools/voice_lexicon.py --lang en --show "Esau ran to Yaoundé."    print the phonemes with fixes
  python3 tools/voice_lexicon.py --lang en --check                          list entries + espeak's own guess
Used by tools/gen_voice.py (on by default; --no-lexicon to switch off).
"""
import json, os, re, sys, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, 'content', 'voice-lexicon')


def load(lang):
    """Entries for a language tag ('en', 'en-gb' -> en.json; 'fr-fr' -> fr.json). {} if none."""
    base = (lang or '').split('-')[0].lower()
    p = os.path.join(DIR, base + '.json')
    if not os.path.isfile(p):
        return {}
    d = json.load(open(p, encoding='utf-8'))
    out = {}
    for e in d.get('entries', []):
        ipa = e.get('ipa-' + lang.lower()) or e['ipa']   # optional dialect override, e.g. "ipa-en-us"
        out[e['word'].lower()] = ipa
    return out


def _pattern(lex):
    words = sorted(lex, key=len, reverse=True)
    return re.compile(r"(?<![\w'’-])(" + '|'.join(re.escape(w) for w in words) + r")(['’]s)?(?![\w-])", re.I)


# real words espeak always says the same way, ending in a consonant (no British linking 'r'); a vowel-initial one
# keeps 'an'/'the' before vowel-initial names natural
PLACEHOLDERS = ('kumquat', 'aardvark')


def _possessive(ipa):
    last = ipa.rstrip('ˈˌː')[-1:]
    return ipa + ('ɪz' if last in 'szʃʒ' else ('s' if last in 'ptkfθ' else 'z'))


def phonemize(text, lang, phonemize_fn, lex=None):
    """Return (phonemes, fixed_words). phonemize_fn(text, lang) is the engine's own phonemizer
    (kokoro_onnx: Kokoro(...).tokenizer.phonemize). Returns (None, []) when no entry applies.
    The whole line is phonemized at once (so weak forms, stress and pauses stay natural) with each fixed word
    swapped for a placeholder, whose phonemes are then replaced by the entry's IPA."""
    lex = load(lang) if lex is None else lex
    if not lex:
        return None, []
    pat = _pattern(lex)
    found = list(pat.finditer(text))
    if not found or any(re.search(p, text, re.I) for p in PLACEHOLDERS):
        return None, []
    vowel = lambda m: lex[m.group(1).lower()].lstrip('ˈˌ')[:1] in 'aeiouɑɒæɐəɛɜɪʊʌɔ'
    swapped, pos = '', 0
    for m in found:
        swapped += text[pos:m.start()] + PLACEHOLDERS[1 if vowel(m) else 0]
        pos = m.end()
    swapped += text[pos:]
    ph = phonemize_fn(swapped, lang)
    marks = {p: phonemize_fn(p, lang).strip() for p in PLACEHOLDERS}
    rx = re.compile('|'.join(re.escape(v) for v in marks.values()))
    pieces = rx.split(ph)
    if len(pieces) != len(found) + 1:
        raise ValueError(f'voice_lexicon: could not place fixes in {text!r} -> {ph!r}')
    out = pieces[0]
    for m, rest in zip(found, pieces[1:]):
        ipa = lex[m.group(1).lower()]
        out += (_possessive(ipa) if m.group(2) else ipa) + rest
    return out, [m.group(1) for m in found]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lang', default='en-gb')
    ap.add_argument('--show')
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    from kokoro_onnx import Kokoro
    kok = os.environ.get('KOKORO_DIR', '/workspace/kok')
    k = Kokoro(os.path.join(kok, 'kokoro-v1.0.int8.onnx'), os.path.join(kok, 'voices-v1.0.bin'))
    ph = k.tokenizer.phonemize
    if a.show:
        print('espeak :', ph(a.show, a.lang))
        p, f = phonemize(a.show, a.lang, ph)
        print('fixed  :', p, f)
    if a.check:
        for w, ipa in load(a.lang).items():
            print(f'{w:14s} espeak {ph(w, a.lang):20s} -> {ipa}')


if __name__ == '__main__':
    main()
