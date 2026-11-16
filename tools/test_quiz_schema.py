"""Quiz engine content tests (no browser):  python3 tools/test_quiz_schema.py
 1. the committed quiz records (items, banks, rules, Ari/Ezra lines) are valid on both channels, no errors
 2. the validator catches each class of quiz mistake (one small broken copy of the content per case)
 3. channels: live keeps the published land quizzes + rules and drops the draft Quiz Time bank and its place;
    preview keeps them; a published bank that loses its rules record is an error, not a silent change
 4. voice: every spoken quiz line (question, answers, hints, Ari/Ezra lines) needs an English clip"""
import os, sys, json, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from content.source import Source
from content.validate import Validator
from content.compile import Build
from content import hydrate, legacy
from content.common import load_json, write_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC, SCHEMA = os.path.join(ROOT, 'content/src'), os.path.join(ROOT, 'content/schema/v1')
Q, LANDS, CMR = 'core/quiz.json', 'core/lands.json', 'countries/cameroon/quiz.json'
fails, n = [], [0]
def ok(c, m):
    n[0] += 1; print(('  ok  ' if c else '  FAIL ') + m)
    if not c: fails.append(m)
def tmp_src():
    d = tempfile.mkdtemp(prefix='ewq-'); shutil.copytree(SRC, os.path.join(d, 'src')); return d
def validate(src, channel=None, files=False):
    S = Source(src, ROOT); V = Validator(S, SCHEMA, channel=channel, check_files=files); return S, V, V.run()
def errors(iss): return [i for i in iss if i.sev == 'error']
def edit(src, rel, fn):
    p = os.path.join(src, rel); d = load_json(p); fn(d); write_json(p, d)
def rec(d, rid): return next(r for r in d['records'] if r['id'] == rid)
def pay(rid): return lambda d: rec(d, rid)['payload']

print('1. committed quiz content')
for ch in ('live', 'preview'):
    S, V, iss = validate(SRC, ch, files=True)
    qe = [i for i in errors(iss)]
    ok(not qe, f'{ch}: no validation errors {qe[:3]}')
    types = {}
    for r in S.records.values(): types[r['type']] = types.get(r['type'], 0) + 1
    ok(types.get('quiz-rules', 0) >= 3, f'{ch}: rules are data (quiz-rules records: {types.get("quiz-rules")})')
S, V, iss = validate(SRC, 'preview')
rts = {r['payload']['responseType'] for r in S.records.values() if r['type'] == 'quiz-item'}
ok({'single-choice', 'picture-pick', 'count', 'true-false', 'order', 'match'} <= rts, f'all six question types are used by real records {sorted(rts)}')
lines = [r for r in S.records.values() if r['id'].startswith('ew.line.quiz-')]
ok(lines and all(r['payload'].get('speaker') in ('ew.character.ari', 'ew.character.ezra') for r in lines) and not any('owl' in json.dumps(r).lower() for r in lines), f'quiz feedback lines are pre-written Ari/Ezra lines ({len(lines)})')

print('2. validator catches quiz mistakes')
IT = 'ew.quiz.quiztime-'
CASES = [
    ('single-choice key not an option', Q, lambda d: pay(IT + 'after-four')(d).update(answerKey='z'), 'not one of the options'),
    ('picture-pick without pictures', Q, lambda d: pay(IT + 'find-banana')(d).pop('optionMedia'), 'optionMedia'),
    ('true-false key must be true/false', Q, lambda d: pay(IT + 'three-more')(d).update(answerKey='maybe'), None),
    ('count key must equal count.n', Q, lambda d: pay(IT + 'count-stars')(d).update(answerKey='7'), 'must equal count.n'),
    ('order key must list every option once', Q, lambda d: pay(IT + 'order-123')(d).update(answerKey=['a', 'a', 'c']), 'every option id once'),
    ('match key must pair every option with a different target', Q, lambda d: pay(IT + 'match-words')(d).update(answerKey={'n1': 'one', 'n2': 'one', 'n3': 'three'}), 'different target'),
    ('unknown question type', Q, lambda d: pay(IT + 'after-four')(d).update(responseType='essay'), None),
    ('two answers with the same text', Q, lambda d: pay(IT + 'after-four')(d)['options']['a'].update(en=pay(IT + 'after-four')(d)['options']['b']['en']), 'same text'),
    ('optionSay for a missing option', Q, lambda d: pay(IT + 'after-four')(d).setdefault('optionSay', {}).update(zz={'en': 'Zed.'}), 'not options'),
    ('difficulty not in the taxonomy', Q, lambda d: rec(d, IT + 'after-four')['tags'].update(difficulty='impossible'), 'difficulty'),
    ('bank with neither items nor a generator', Q, lambda d: pay('ew.quizbank.quiztime')(d).pop('items'), 'items'),
    ('bank naming a rules record that does not exist', Q, lambda d: pay('ew.quizbank.quiztime')(d).update(rules='ew.quizrules.nope'), None),
    ('bank item that does not exist', Q, lambda d: pay('ew.quizbank.quiztime')(d)['items'].append('ew.quiz.nope'), None),
    ('generator the app cannot run', Q, lambda d: pay('ew.quizbank.count-it')(d)['generator'].update(kind='spell'), None),
    ('count generator min >= max', Q, lambda d: pay('ew.quizbank.count-it')(d)['generator'].update(min=10, max=3), 'below max'),
    ('stars: two stars stricter than three', Q, lambda d: pay('ew.quizrules.default')(d)['stars'].update(three=3, two=1), 'stars.two'),
    ('adaptive start level not in the taxonomy', Q, lambda d: pay('ew.quizrules.default')(d)['adaptive'].update(start='genius'), 'adaptive.start'),
    ('spaced review intervals going down', Q, lambda d: pay('ew.quizrules.default')(d)['spaced'].update(intervalsDays=[0, 7, 3]), 'intervalsDays'),
    ('a bank override with bad stars', Q, lambda d: pay('ew.quizbank.quiztime')(d).update(ruleOverrides={'stars': {'three': 2, 'two': 1}}), 'ruleOverrides.stars'),
    ('Ari line that does not exist', Q, lambda d: pay('ew.quizbank.quiztime')(d)['lines']['correct'].append('ew.line.nope'), None),
    ('land Count It! pointing at a deck quiz', LANDS, lambda d: next(p for p in rec(d, 'ew.land.number')['payload']['places'] if p['key'] == 'count').update(quiz='ew.quizbank.flag-quiz'), None),
    ('quiz place without a bank', LANDS, lambda d: next(p for p in rec(d, 'ew.land.number')['payload']['places'] if p['key'] == 'quiztime').pop('quiz'), None),
    ('Cameroon rules record missing', CMR, lambda d: next(r for r in d['records'] if r['type'] == 'quiz-bank')['payload'].update(rules='ew.quizrules.gone'), None),
]
for name, rel, fn, want in CASES:
    t = tmp_src(); s = os.path.join(t, 'src')
    try:
        edit(s, rel, fn); S, V, iss = validate(s, 'preview')
        es = errors(iss); hit = [e for e in es if (want is None or want in e.msg)]
        ok(bool(hit), f'{name}: {"error " + repr(hit[0].msg[:90]) if hit else "NOT caught " + repr([e.msg[:60] for e in es][:2])}')
    except Exception as e:
        ok(False, f'{name}: crashed {type(e).__name__}: {e}')
    finally: shutil.rmtree(t)
# a gentle warning (not an error) when picture answers cannot be named by the voice
t = tmp_src(); s = os.path.join(t, 'src'); edit(s, Q, lambda d: pay(IT + 'find-banana')(d).pop('optionSay', None))
S, V, iss = validate(s, 'preview'); ok(any(i.sev == 'warn' and 'optionSay' in i.msg for i in iss), 'picture answers with no optionSay -> warning'); shutil.rmtree(t)

t = tmp_src(); s = os.path.join(t, 'src'); edit(s, Q, lambda d: pay('ew.quizrules.default')(d)['voice'].update(readAloudToggle={'5-7': False, '8-10': False, '11-13': False}))
S, V, iss = validate(s, 'preview'); ok(any(i.sev == 'warn' and 'never hear a question' in i.msg for i in iss), 'voice: an age band with no auto-reading and no Read to me switch -> warning'); shutil.rmtree(t)
t = tmp_src(); s = os.path.join(t, 'src'); edit(s, Q, lambda d: pay('ew.quizrules.default')(d)['voice'].update(tapReadsAnswer={'8-10': 'yes'}))
S, V, iss = validate(s, 'preview'); ok(bool(errors(iss)), 'voice: a band value that is not true/false is an error'); shutil.rmtree(t)
t = tmp_src(); s = os.path.join(t, 'src'); edit(s, Q, lambda d: pay('ew.quizbank.flag-quiz')(d)['generator'].update(answerSay='flag'))
S, V, iss = validate(s, 'preview'); ok(bool(errors(iss)), 'generator.answerSay must be a known card field'); shutil.rmtree(t)

print('3. channels')
def build(src, ch):
    t = tempfile.mkdtemp(prefix='ewql-'); S, V, iss = validate(src, ch); B = Build(S, V, None, channel=ch).run()
    B.write(os.path.join(t, 'lib'), os.path.join(t, 'lock.json')); cat, recs = hydrate.load(os.path.join(t, 'lib')); shutil.rmtree(t); return recs
for ch in ('live', 'preview'):
    recs = build(SRC, ch); L = legacy.lands(recs, ['en', 'fr']); num = next(x for x in L['lands'] if x['id'] == 'number')
    keys = [p.get('id') or p.get('key') for p in num['places']]
    has = 'ew.quizbank.quiztime' in recs
    if ch == 'live':
        ok(not has and 'quiztime' not in keys and not any(r.startswith('ew.quiz.quiztime-') for r in recs), f'live: the draft Quiz Time bank, items and place are left out {keys}')
        ok(not any(r.startswith('ew.line.quiz-') for r in recs), 'live: draft Ari/Ezra quiz lines are left out')
    else:
        ok(has and 'quiztime' in keys, f'preview: Quiz Time is there {keys}')
    for b in ('ew.quizbank.letter-hunt', 'ew.quizbank.animal-quiz', 'ew.quizbank.flag-quiz', 'ew.quizbank.count-it', 'ew.quizrules.default', 'ew.quizrules.land-classic', 'ew.quizrules.country-classic'):
        ok(b in recs, f'{ch}: {b} is shipped')
    cb = next((r for r in recs.values() if r['type'] == 'quiz-bank' and r['payload'].get('rules') == 'ew.quizrules.country-classic'), None)
    ok(cb is not None, f'{ch}: the Cameroon quiz bank ships with its rules link')

print('4. voice')
t = tmp_src(); s = os.path.join(t, 'src')
edit(s, Q, lambda d: pay(IT + 'after-four')(d)['prompt'].update(en='Which number comes after four, little star?'))
S, V, iss = validate(s, 'preview', files=True)
ok(any(e.code.startswith('voice') or 'clip' in e.msg.lower() for e in errors(iss)), 'a new English question with no recorded clip is an error')
shutil.rmtree(t)
t = tmp_src(); s = os.path.join(t, 'src')
edit(s, Q, lambda d: pay(IT + 'after-four')(d)['hint'].update(en='Count up one from four, friend.'))
S, V, iss = validate(s, 'preview', files=True)
ok(any(e.code.startswith('voice') or 'clip' in e.msg.lower() for e in errors(iss)), 'a new English hint with no clip is an error')
shutil.rmtree(t)

print(f'\n{n[0] - len(fails)}/{n[0]} checks passed' if not fails else f'\n{len(fails)} of {n[0]} FAILED: ' + '; '.join(fails[:5]))
sys.exit(1 if fails else 0)
