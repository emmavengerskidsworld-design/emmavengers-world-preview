"""Content validator: JSON Schema (Draft 2020-12) + cross-record checks. Produces a list of Issues.

Severity: error = the build must stop; warn = allowed but listed in the report for a human; info = coverage facts."""
import json, os, re
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from .common import chain_for, ID_RE, LOCALE_RE, is_lt, walk_lt, vh, canonical
from . import legacy

PLACEHOLDER = re.compile(r'\{(\w+)\}')


def icu_args(s):
    """Argument names in an ICU-style message ({name}, {n, plural, one {# x} other {# xs}}, {g, select, ...}).
    Raises ValueError on unbalanced braces or a malformed plural/select (the app would show it wrongly)."""
    out, i, n = set(), 0, len(s)
    def block(i, depth):
        while i < n:
            c = s[i]
            if c == '{':
                j = i + 1
                while j < n and s[j] not in ',}{': j += 1
                arg = s[i + 1:j].strip()
                if j >= n or s[j] == '{' or not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', arg): raise ValueError(f'bad placeholder near {s[i:i+20]!r}')
                out.add(arg)
                if s[j] == '}': i = j + 1; continue
                k = j + 1
                while k < n and s[k] not in ',}': k += 1
                typ = s[j + 1:k].strip()
                if typ not in ('number', 'plural', 'select', 'selectordinal'): raise ValueError(f'unknown placeholder type {typ!r}')
                if k < n and s[k] == '}': i = k + 1; continue
                k += 1; opts = 0
                while True:
                    while k < n and s[k].isspace(): k += 1
                    if k >= n: raise ValueError('unclosed placeholder')
                    if s[k] == '}': k += 1; break
                    ks = k
                    while k < n and s[k] != '{' and not s[k].isspace(): k += 1
                    key = s[ks:k]
                    while k < n and s[k].isspace(): k += 1
                    if k >= n or s[k] != '{' or not key: raise ValueError(f'option {key!r} needs {{...}}')
                    k = block(k + 1, depth + 1); opts += 1
                    if typ != 'number' and key == 'other': opts = -999
                if typ in ('plural', 'select', 'selectordinal') and opts > -900: raise ValueError(f'{typ} needs an "other" option')
                i = k; continue
            if c == '}':
                if depth == 0: raise ValueError('unbalanced }')
                return i + 1
            i += 1
        if depth: raise ValueError('unclosed {')
        return i
    block(0, 0)
    return out
TAG = re.compile(r'<\s*/?\s*([a-zA-Z][a-zA-Z0-9]*)[^>]*>')
BAD = re.compile(r'javascript:|\bon[a-z]+\s*=|<\s*script|<\s*iframe|data:text/html', re.I)
TYPE_PREFIX = {'world': ['world'], 'land': ['land'], 'deck': ['deck'], 'library': ['library'], 'lexicon': ['lexicon'],
               'character': ['character'], 'strings': ['ui', 'strings'], 'country': ['country'], 'topic': ['topic', 'region'],
               'source': ['source'], 'lesson': ['lesson'], 'learn-card': ['card'], 'activity': ['activity'],
               'quiz-bank': ['quizbank'], 'quiz-item': ['quiz'], 'story': ['story'], 'line': ['line'], 'media': ['media'],
               'mission': ['mission'], 'together': ['together'], 'settings': ['settings'], 'quiz-rules': ['quizrules']}
# (record type, path regex) -> required target type(s). Paths use the walk() notation below.
REF_TYPES = [
    ('*', r'^tags\.topics\[\d+\]$', {'country', 'topic'}),
    ('*', r'^evidence\.sources\[\d+\]$', {'source'}),
    ('world', r'^payload\.lands\[\d+\]$', {'land'}),
    ('land', r'^payload\.places\[\d+\]\.(deck|objects)$', {'deck'}),
    ('land', r'^payload\.places\[\d+\]\.country$', {'country'}),
    ('library', r'^payload\.sections\[\d+\]\.source\.deck$', {'deck'}),
    ('country', r'^payload\.hub\.\w+$', {'line'}),
    ('country', r'^payload\.learn\.\w+$', {'lesson'}),
    ('country', r'^payload\.play\[\d+\]$', {'activity'}),
    ('country', r'^payload\.stories\[\d+\]$', {'story'}),
    ('country', r'^payload\.lines\[\d+\]$', {'line'}),
    ('country', r'^payload\.media\[\d+\]$', {'media'}),
    ('country', r'^payload\.quiz\.bank$', {'quiz-bank'}),
    ('lesson', r'^payload\.cards\[\d+\]$', {'learn-card'}),
    ('learn-card', r'^payload\.image$', {'media'}),
    ('*', r'^payload\.lines\[\d+\]$', {'line'}),
    ('line', r'^payload\.speaker$', {'character'}),
    ('quiz-bank', r'^payload\.items\[\d+\]$', {'quiz-item'}),
    ('quiz-bank', r'^payload\.sources\[\d+\]$', {'source'}),
    ('quiz-bank', r'^payload\.rules$', {'quiz-rules'}),
    ('quiz-bank', r'^payload\.lines\.\w+\[\d+\]$', {'line'}),
    ('quiz-item', r'^payload\.lines\.\w+\[\d+\]$', {'line'}),
    ('land', r'^payload\.places\[\d+\]\.quiz$', {'quiz-bank'}),
    ('activity', r'^payload\.claimFromQuiz$', {'quiz-item'}),
    ('media', r'^payload\.assetId$', {'media'}),
    ('mission', r'^payload\.speaker$', {'character'}),
    ('together', r'^payload\.links\[\d+\]$', {'story', 'lesson', 'activity', 'quiz-bank', 'country', 'topic', 'deck', 'mission'}),
]
WEB = re.compile(r'https?://|www\.|\.com\b', re.I)


class Issue:
    def __init__(self, sev, code, where, msg):
        self.sev, self.code, self.where, self.msg = sev, code, where, msg

    def __repr__(self):
        return f'{self.sev.upper():5} {self.code:18} {self.where}: {self.msg}'


def walk(obj, path=''):
    """Yield (path, value) for every scalar."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f'{path}.{k}' if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f'{path}[{i}]')
    else:
        yield path, obj


def schema_registry(schema_dir):
    res = []
    for f in sorted(os.listdir(schema_dir)):
        if f.endswith('.schema.json'):
            s = json.load(open(os.path.join(schema_dir, f), encoding='utf-8'))
            res.append((s['$id'], Resource.from_contents(s)))
    reg = Registry().with_resources(res)
    by_name = {f[:-12]: json.load(open(os.path.join(schema_dir, f), encoding='utf-8')) for f in os.listdir(schema_dir) if f.endswith('.schema.json')}
    return reg, by_name


class Validator:
    def __init__(self, src, schema_dir, channel=None, check_files=True):
        self.S = src
        self.issues = []
        self.reg, self.schemas = schema_registry(schema_dir)
        self.check_files = check_files
        self.cfg = src.cfg
        self.channel = channel or self.cfg.get('build', {}).get('channel', 'preview')
        self.stats = {}

    def add(self, sev, code, where, msg):
        self.issues.append(Issue(sev, code, where, msg))

    def schema_errors(self, name, doc, where):
        v = Draft202012Validator(self.schemas[name], registry=self.reg)
        errs = sorted(v.iter_errors(doc), key=lambda e: list(e.absolute_path))
        for e in errs[:20]:
            p = '.'.join(str(x) for x in e.absolute_path) or '(top)'
            msg = e.message if len(e.message) < 300 else e.message[:300] + '...'
            self.add('error', 'schema', where, f'{p}: {msg}')
        return bool(errs)

    # ------------------------------------------------------------------
    def run(self):
        S, cfg = self.S, self.cfg
        for e in S.errors:
            self.add('error', 'load', 'content/src', e)
        for c in ('locales', 'taxonomy', 'capabilities', 'collections', 'build', 'rights'):
            self.schema_errors(c, cfg.get(c, {}), f'content/src/{c}.json')
        for rel, doc, kind in S.raw_files:
            self.schema_errors(kind, doc, rel)
        for rid, a, b in S.duplicates:
            self.add('error', 'duplicate-id', f'{b[1]}', f'{rid} is already defined in {a[1]}')
        self.locales = set(S.locales)
        self.tax = cfg.get('taxonomy', {})
        self.cap = cfg.get('capabilities', {})
        chan = cfg.get('build', {}).get('channels', {}).get(self.channel)
        if not chan:
            self.add('error', 'channel', 'content/src/build.json', f'unknown channel {self.channel}')
            chan = {'statuses': []}
        self.allowed = set(chan['statuses'])
        colls = {c['id'] for c in cfg.get('collections', {}).get('collections', [])}
        for pid, P in S.packs.items():
            if P['meta'].get('collection') not in colls:
                self.add('error', 'collection', P['dir'] + '/pack.json', f'collection {P["meta"].get("collection")} is not in collections.json')
            for l in P['meta'].get('locales', {}).get('required', []):
                if l not in self.locales:
                    self.add('error', 'locale', P['dir'] + '/pack.json', f'required locale {l} is not in locales.json')
            sm = P['meta'].get('summary')
            if sm and S.pack_of(sm) != pid:
                self.add('error', 'summary', P['dir'] + '/pack.json', f'summary record {sm} is not in this pack')
        for rid, r in S.records.items():
            self.check_record(rid, r)
        self.check_refs()
        self.check_assets_and_voice()
        return self.issues

    # ------------------------------------------------------------------
    def check_record(self, rid, r):
        S = self.S
        w = S.where(rid)
        if not isinstance(rid, str) or not ID_RE.match(rid):
            self.add('error', 'id', w, f'id {rid!r} does not match ew.<type>.<slug> (lower-case, digits, dot or hyphen)')
            return
        if self.schema_errors('record', r, w):
            return
        t = r['type']
        if rid.split('.')[1] not in TYPE_PREFIX.get(t, []):
            self.add('error', 'id-type', w, f'a {t} id must start with ew.{TYPE_PREFIX[t][0]}.')
        n = len(canonical(r))
        if n > self.cfg['build']['budgets']['recordBytes']:
            self.add('error', 'budget', w, f'record is {n} bytes (limit {self.cfg["build"]["budgets"]["recordBytes"]})')
        # tags against the closed taxonomy
        T, X = r['tags'], self.tax
        if T.get('land') is not None and T['land'] not in X['lands']:
            self.add('error', 'tag', w, f'land {T["land"]!r} not in taxonomy')
        for k, allowed in (('relatedLands', 'lands'), ('subjects', 'subjects'), ('regions', 'regions'), ('sensitivity', 'sensitivity'), ('ageBands', 'ageBands'), ('modes', 'modes')):
            for v in T.get(k, []):
                if v not in X[allowed]:
                    self.add('error', 'tag', w, f'{k} value {v!r} not in taxonomy.{allowed}')
        if T.get('difficulty') not in (None, *X['difficulty']):
            self.add('error', 'tag', w, f'difficulty {T["difficulty"]!r} not in taxonomy')
        if r['status'] not in X['statuses']:
            self.add('error', 'status', w, f'status {r["status"]}')
        # languages
        pack = S.packs[S.pack_of(rid)]['meta']
        req = set(pack.get('locales', {}).get('required', [])) | set(r.get('l10n', {}).get('required', []))
        req.add(r['sourceLanguage'])
        if r['sourceLanguage'] not in self.locales:
            self.add('error', 'locale', w, f'sourceLanguage {r["sourceLanguage"]} not in locales.json')
        for lg in r.get('l10n', {}):
            if lg not in ('required', 'sourceOnly') and lg not in self.locales:
                self.add('error', 'locale', w, f'l10n has unknown locale {lg}')
        markup = self.cap.get('markupFields', {})
        for path, lt in walk_lt({'payload': r['payload'], 'tags': r['tags']}, self.locales):
            for lg in lt:
                if lg not in self.locales:
                    self.add('error', 'locale', w, f'{path}: language {lg!r} is not in locales.json (add it there first)')
            miss = sorted(req - set(lt))
            if miss:
                self.add('error', 'missing-text', w, f'{path}: no {"/".join(miss)} text (required for this pack)')
            ph = {}
            for lg, s in lt.items():
                try: ph[lg] = icu_args(s)
                except ValueError as e: self.add('error', 'placeholders', w, f'{path}.{lg}: {e}: {s[:60]!r}')
            # a question template on a land place may use different item fields per language (grammar forms such as
            # {nameDef} = "le lion"); type_land checks each one is a field of the deck items
            free = r['type'] == 'land' and path.endswith('.ask')
            if not free and len({frozenset(v) for v in ph.values()}) > 1:
                self.add('error', 'placeholders', w, f'{path}: placeholders differ between languages {ph}')
            for lg, s in lt.items():
                self.check_text(w, f'{path}.{lg}', s, None)
        for path, v in walk(r['payload'], 'payload'):
            if isinstance(v, str) and not ID_RE.match(v):
                field = path.rsplit('.', 1)[-1]
                self.check_text(w, path, v, markup.get(field))
        # sources for facts
        ev = r.get('evidence', {})
        factual = ev.get('factual', t in ('quiz-item',) or (t == 'learn-card' and r['payload'].get('kind') == 'info'))
        if factual and not ev.get('sources'):
            legacy_rec = r.get('review', {}).get('legacy')
            self.add('warn' if legacy_rec else 'error', 'no-source', w, 'states facts but cites no source')
        if t == 'deck' and r['payload']['kind'] in ('animal', 'country') and not ev.get('sources'):
            self.add('warn', 'no-source', w, f'{len(r["payload"]["items"])} {r["payload"]["kind"]} fact cards cite no sources (legacy content)')
        if t == 'source':
            p = r['payload']
            if not p.get('url') and not p.get('note'):
                self.add('error', 'source', w, 'a source needs a url or a note saying what it is')
            elif not p.get('url'):
                self.add('info', 'source-offline', w, f'editorial source without a web link: {p.get("note") or p["key"]}')
            if p.get('url') and not p.get('checkedOn'):
                self.add('warn', 'source-unchecked', w, 'url has no checkedOn date')
        # per type
        getattr(self, 'type_' + t.replace('-', '_'), lambda *a: None)(rid, r, w)
        # stale translations
        for lg, st in r.get('l10n', {}).items():
            if lg not in ('required', 'sourceOnly') and isinstance(st, dict) and st.get('sourceRevision') and r.get('revision') and st['sourceRevision'] < r['revision']:
                self.add('warn', 'stale-translation', w, f'{lg} was made from revision {st["sourceRevision"]}, record is now revision {r["revision"]}')

    def check_text(self, w, path, s, allowed_tags):
        if BAD.search(s):
            self.add('error', 'unsafe-text', w, f'{path}: looks like script/HTML: {s[:60]!r}')
            return
        tags = TAG.findall(s)
        if tags:
            bad = [x for x in tags if not allowed_tags or x.lower() not in allowed_tags]
            if bad:
                self.add('error', 'markup', w, f'{path}: HTML tags {bad} are not allowed here: {s[:60]!r}')
            else:
                self.add('info', 'markup', w, f'{path}: allowed markup {tags} in {s!r}')
        if len(s) > self.cfg['build']['budgets']['stringChars']:
            self.add('error', 'budget', w, f'{path}: text longer than {self.cfg["build"]["budgets"]["stringChars"]} characters')
        if s != s.strip() or '  ' in s:
            self.add('warn', 'whitespace', w, f'{path}: extra spaces in {s[:60]!r}')

    # ---- type checks -------------------------------------------------
    def type_land(self, rid, r, w):
        C = self.cap
        keys = set()
        for q in r['payload']['places']:
            if q['key'] in keys: self.add('error', 'duplicate-key', w, f'place {q["key"]} twice')
            keys.add(q['key'])
            if q['type'] not in C['placeTypes']:
                self.add('error', 'capability', w, f'place {q["key"]}: type {q["type"]!r} is not something the app can open ({C["placeTypes"]})')
            if q['type'] == 'link' and q.get('go') not in C['modules']:
                self.add('error', 'capability', w, f'place {q["key"]}: go={q.get("go")!r} is not a known module {C["modules"]}')
            if q['type'] == 'quiz' and q.get('mode') not in C.get('placeQuizModes', []):
                self.add('error', 'capability', w, f'place {q["key"]}: quiz mode {q.get("mode")!r} unknown')
            if q.get('quiz') and q['quiz'] in self.S.records:
                bank = self.S.records[q['quiz']]['payload']
                gen = (bank.get('generator') or {}).get('kind')
                want = {'quiz': 'deck-pick', 'count': 'count'}.get(q['type'])
                if q['type'] == 'bank' and not bank.get('items'):
                    self.add('error', 'quiz', w, f'place {q["key"]}: a bank place needs a quiz bank with items ({q["quiz"]} has none)')
                elif want and gen != want:
                    self.add('error', 'quiz', w, f'place {q["key"]}: a {q["type"]} place needs a bank with generator kind {want!r}, {q["quiz"]} has {gen!r}')
                elif q['type'] not in ('quiz', 'count', 'bank'):
                    self.add('error', 'quiz', w, f'place {q["key"]}: only quiz, count and bank places use a quiz bank')
            if q.get('ask') and q.get('deck') in self.S.records:
                items = self.S.records[q['deck']]['payload']['items']
                fields = set().union(*[set(i) for i in items]) | {'lname'}
                for lg, s in q['ask'].items():
                    for v in PLACEHOLDER.findall(s):
                        if v not in fields:
                            self.add('error', 'placeholders', w, f'place {q["key"]}: {{{v}}} is not a field of the deck items')
        if r['tags'].get('land') != r['payload']['key']:
            self.add('error', 'tag', w, 'tags.land must equal the land key')

    def type_deck(self, rid, r, w):
        p = r['payload']
        if p['kind'] not in self.cap.get('deckKinds', []):
            self.add('error', 'capability', w, f'deck kind {p["kind"]!r} unknown')
        seen = set()
        for it in p['items']:
            k = str(it.get('id', it.get('n')))
            if k in seen: self.add('error', 'duplicate-key', w, f'item {k} twice')
            seen.add(k)
        if p['kind'] == 'number':
            objs = {i['id'] for i in self.S.records.get('ew.deck.objects', {}).get('payload', {}).get('items', [])}
            for it in p['items']:
                if it.get('obj') and it['obj'] not in objs:
                    self.add('error', 'ref', w, f'number {it.get("n")}: object {it["obj"]!r} is not in ew.deck.objects')

    def type_library(self, rid, r, w):
        for s in r['payload']['sections']:
            m = s['source'].get('module')
            if m and m not in self.cap['modules']:
                self.add('error', 'capability', w, f'shelf {s["key"]}: module {m!r} unknown')

    def type_quiz_item(self, rid, r, w):
        """Each response type has its own fields (docs/quiz-engine.md). The key is bound to option ids, never to positions."""
        p, t = r['payload'], r['payload']['responseType']
        if t not in self.cap['quizResponseTypes']:
            planned = t in self.cap.get('plannedQuizResponseTypes', [])
            self.add('error', 'capability', w, f'responseType {t} is {"planned but not built yet" if planned else "unknown"}')
            return
        opts, key = p.get('options') or {}, p['answerKey']
        def need(cond, msg):
            if not cond: self.add('error', 'answer', w, msg)
            return cond
        if t in ('single-choice', 'picture-pick', 'order', 'match'):
            if not need(len(opts) >= 2, f'{t} needs at least 2 options'): return
        if t in ('single-choice', 'picture-pick'):
            need(isinstance(key, str) and key in opts, f'answerKey {key!r} is not one of the options {list(opts)}')
        if t == 'picture-pick':
            media = p.get('optionMedia') or {}
            need(set(media) == set(opts), f'picture-pick needs a picture (optionMedia) for every option: missing {sorted(set(opts) - set(media))}')
            if not p.get('optionSay'):
                self.add('warn', 'quiz-voice', w, 'picture answers have no optionSay: the voice cannot name them')
        if t == 'true-false':
            need(key in ('true', 'false'), 'true-false answerKey must be "true" or "false"')
            if opts: need(set(opts) == {'true', 'false'}, 'true-false options (if given) must be exactly "true" and "false"')
        if t == 'count':
            c = p.get('count')
            if need(bool(c), 'count needs count: {n, img}'):
                need(str(key) == str(c['n']), f'count answerKey {key!r} must equal count.n {c["n"]}')
                if c.get('numbers'): need(c['n'] in c['numbers'], f'count.numbers {c["numbers"]} must include the answer {c["n"]}')
        if t == 'order':
            need(isinstance(key, list) and sorted(key) == sorted(opts) and len(set(key)) == len(key),
                 f'order answerKey must list every option id once, in order: got {key!r} for {list(opts)}')
        if t == 'match':
            tg = p.get('targets') or {}
            if need(len(tg) >= 2, 'match needs targets (the right-hand column)'):
                need(isinstance(key, dict) and set(key) == set(opts) and set(key.values()) == set(tg) and len(set(key.values())) == len(key),
                     f'match answerKey must pair every option with a different target: {key!r}')
        if t not in ('single-choice', 'picture-pick', 'order', 'match', 'true-false') and opts:
            self.add('warn', 'quiz', w, f'{t} does not use options')
        for fld in ('optionMedia', 'optionSay'):
            extra = set(p.get(fld) or {}) - set(opts)
            if extra: self.add('error', 'answer', w, f'{fld} has ids that are not options: {sorted(extra)}')
        for grp in (opts, p.get('targets') or {}, p.get('optionSay') or {}):
            if not grp: continue
            langs = set().union(*[set(x) for x in grp.values()])
            for lg in langs:
                texts = [x.get(lg) for x in grp.values() if x.get(lg)]
                if len(texts) != len(set(x.strip().lower() for x in texts)):
                    self.add('error', 'answer', w, f'{lg}: two answers have the same text')
        for f in ('hint', 'feedback'):
            if f not in p: self.add('warn', 'quiz', w, f'no {f}')
        diff = r['tags'].get('difficulty')
        for d in (diff if isinstance(diff, list) else [diff] if diff else []):
            if d not in self.tax.get('difficulty', []): self.add('error', 'tag', w, f'difficulty {d!r} not in taxonomy.difficulty')

    def type_quiz_bank(self, rid, r, w):
        p = r['payload']
        if not p.get('items') and not p.get('generator'):
            self.add('error', 'quiz', w, 'a quiz bank needs items or a generator')
        g = p.get('generator')
        if g:
            if g['kind'] not in self.cap.get('quizGenerators', []):
                self.add('error', 'capability', w, f'generator {g["kind"]!r} is not built into the app {self.cap.get("quizGenerators")}')
            if g['kind'] == 'count' and g.get('min') is not None and g.get('max') is not None and g['min'] >= g['max']:
                self.add('error', 'quiz', w, f'generator min {g["min"]} must be below max {g["max"]}')
        bands = set(r['tags'].get('ageBands', []))
        for iid in p.get('items', []):
            it = self.S.records.get(iid)
            if it and bands and not set(it['tags'].get('ageBands', [])) <= bands:
                self.add('warn', 'tag', w, f'item {iid} is for {it["tags"]["ageBands"]}, outside the bank ages {sorted(bands)}')
        if p.get('ruleOverrides'): self._quiz_rules(p['ruleOverrides'], w, 'ruleOverrides.')

    def type_quiz_rules(self, rid, r, w):
        self._quiz_rules(r['payload'], w, '')

    def _quiz_rules(self, p, w, pre):
        st = p.get('stars') or {}
        if 'three' in st and 'two' in st and st['two'] < st['three']:
            self.add('error', 'quiz-rules', w, f'{pre}stars.two ({st["two"]}) must be >= stars.three ({st["three"]}) - more mistakes allowed for 2 stars than for 3')
        a = p.get('adaptive') or {}
        if a.get('start') and a['start'] not in self.tax.get('difficulty', []):
            self.add('error', 'quiz-rules', w, f'{pre}adaptive.start {a["start"]!r} not in taxonomy.difficulty')
        iv = (p.get('spaced') or {}).get('intervalsDays')
        if iv and iv != sorted(iv):
            self.add('error', 'quiz-rules', w, f'{pre}spaced.intervalsDays must go up: {iv}')
        vo = p.get('voice') or {}
        flag = lambda v, b: v if isinstance(v, bool) else (v or {}).get(b)
        if 'readQuestionOnShow' in vo:
            for b in self.tax.get('ageBands', ['5-7', '8-10', '11-13']):
                if flag(vo['readQuestionOnShow'], b) is False and not flag(vo.get('readAloudToggle'), b):
                    self.add('warn', 'quiz-rules', w, f'{pre}voice: ages {b} never hear a question unless they tap the speaker (no Read to me switch)')
        rt = p.get('retry') or {}
        if rt.get('untilCorrect') is False and rt.get('skipAfterTries') == 0:
            self.add('warn', 'quiz-rules', w, f'{pre}retry: no retry and no skip - a child could be stuck')

    def type_activity(self, rid, r, w):
        p = r['payload']
        if p['template'] not in self.cap['activityTemplates']:
            self.add('error', 'capability', w, f'template {p["template"]} is not built into the app {self.cap["activityTemplates"]}')
            return
        for q in p.get('questions', []) + ([p['next']] if p.get('next') else []):
            if q['key'] not in q['options']:
                self.add('error', 'answer', w, f'answer {q["key"]!r} not in options')
        if p['template'] == 'map-select.v1':
            ids = {n['id'] for n in p['neighbours']}
            for q in p['prompts']:
                bad = [a for a in q['accept'] if a not in ids]
                if bad: self.add('error', 'answer', w, f'prompt {q["dir"]}: accepts unknown {bad}')
                at = {n['id'] for n in p['neighbours'] if n['pos'] == q['dir']}
                if set(q['accept']) != at:
                    self.add('warn', 'answer', w, f'prompt {q["dir"]}: accepts {q["accept"]} but neighbours placed there are {sorted(at)}')
        if p['template'] == 'grid-route.v1':
            topic = self.topic_of(r)
            grid = topic and topic['payload'].get('practiceMap', {}).get('rows')
            if grid:
                cells = [c['id'] for row in grid for c in row]
                if p['goal'] not in cells: self.add('error', 'answer', w, f'goal {p["goal"]!r} is not on the practice map')
                y, x = p['start']
                if y >= len(grid) or x >= len(grid[0]): self.add('error', 'answer', w, f'start {p["start"]} is off the map')

    def type_story(self, rid, r, w):
        p = r['payload']
        if p['classification'] not in self.cap.get('storyClassifications', []):
            self.add('error', 'capability', w, f'classification {p["classification"]} unknown')
        if p['classification'] == 'bible-retelling':
            if not p.get('sourcePassages'): self.add('error', 'faith', w, 'a Bible retelling must name its passages (sourcePassages)')
            if 'bible-retelling' not in r['tags'].get('sensitivity', []): self.add('error', 'faith', w, 'a Bible retelling must carry sensitivity bible-retelling')

    def type_media(self, rid, r, w):
        if r['payload']['kind'] not in self.cap.get('mediaKinds', []):
            self.add('error', 'capability', w, f'media kind {r["payload"]["kind"]} unknown')
        if r['payload']['kind'] == 'placeholder':
            self.add('info', 'placeholder-art', w, f'placeholder picture: {r["payload"]["label"].get("en")}')

    def type_lesson(self, rid, r, w):
        for c in r['payload']['cards']:
            cr = self.S.records.get(c)
            if cr and not set(cr['tags']['ageBands']) <= set(r['tags']['ageBands']):
                self.add('error', 'tag', w, f'card {c} is for {cr["tags"]["ageBands"]}, outside the lesson ages {r["tags"]["ageBands"]}')

    def type_line(self, rid, r, w):
        for lg, s in r['payload']['text'].items():
            if len(s) > 160: self.add('warn', 'long-line', w, f'{lg}: guide line is {len(s)} characters (keep lines short for children)')

    # ---- Daily Ari Missions, Together Time, app settings (schema room added in Stage 2; screens come in Stage 5) ----
    def _no_web(self, r, w):
        """Missions and Together Time send the child into real life: never to a web address."""
        for path, v in walk(r['payload'], 'payload'):
            if isinstance(v, str) and WEB.search(v): self.add('error', 'web-link', w, f'{path}: no web addresses in {r["type"]} content: {v[:60]!r}')

    def type_mission(self, rid, r, w):
        p, X, T = r['payload'], self.tax, r['tags']
        if p['kind'] not in X.get('missionKinds', []): self.add('error', 'tag', w, f'mission kind {p["kind"]!r} not in taxonomy.missionKinds')
        for v in p.get('timeOfDay', []):
            if v not in X.get('timesOfDay', []): self.add('error', 'tag', w, f'timeOfDay {v!r} not in taxonomy.timesOfDay')
        needs_adult = p.get('adultNearby') or 'adult-accompaniment' in T.get('sensitivity', []) or p.get('where') == 'outdoors'
        if needs_adult and not p['parentConfirm']:
            self.add('error', 'mission-safety', w, 'a mission that needs a grown-up nearby (adultNearby / outdoors / adult-accompaniment) must have parentConfirm: true')
        if p.get('adultNearby') and not p.get('parentNote'):
            self.add('warn', 'mission-safety', w, 'adultNearby mission has no parentNote telling the parent what to watch')
        if p.get('proof') == 'none' and p['parentConfirm']:
            self.add('error', 'mission', w, 'proof "none" contradicts parentConfirm: true')
        if p['kind'] == 'prayer' and 'faith' not in T.get('subjects', []):
            self.add('warn', 'tag', w, 'prayer mission is not tagged with subject faith')
        self._no_web(r, w)

    def type_together(self, rid, r, w):
        p, X = r['payload'], self.tax
        if p['kind'] not in X.get('togetherKinds', []): self.add('error', 'tag', w, f'together kind {p["kind"]!r} not in taxonomy.togetherKinds')
        for v in p.get('timeOfDay', []):
            if v not in X.get('timesOfDay', []): self.add('error', 'tag', w, f'timeOfDay {v!r} not in taxonomy.timesOfDay')
        if (p['kind'] == 'parent-tip') != (p['audience'] == 'parent'):
            self.add('error', 'together', w, 'kind parent-tip and audience parent go together (tips are for the parent only)')
        if p['kind'] == 'parent-tip' and not r.get('evidence', {}).get('sources'):
            self.add('error', 'no-source', w, 'a parent tip gives advice, so it must cite at least one source')
        self._no_web(r, w)

    def type_settings(self, rid, r, w):
        p, X = r['payload'], self.tax
        if rid != 'ew.settings.app': self.add('error', 'settings', w, 'there is one settings record and its id is ew.settings.app')
        m = p.get('missions', {})
        if m.get('defaultMode') and m.get('modes') and m['defaultMode'] not in m['modes']:
            self.add('error', 'settings', w, f'missions.defaultMode {m["defaultMode"]!r} is not one of missions.modes')
        for k in m.get('kinds', []):
            if k not in X.get('missionKinds', []): self.add('error', 'settings', w, f'missions.kinds {k!r} not in taxonomy.missionKinds')
        g = p.get('parentGate', {})
        for k in ('primary', 'fallback'):
            if g.get(k) and g.get('methods') and g[k] not in g['methods']: self.add('error', 'settings', w, f'parentGate.{k} {g[k]!r} is not one of parentGate.methods')
        if m.get('confirm') == 'none' and m.get('defaultMode') == 'firm':
            self.add('error', 'settings', w, 'firm missions need a grown-up check (missions.confirm parent-gate)')
        for sec, key in (('missions', 'breakAfterMinutes'), ('screenTime', 'dailyMinutes')):
            v = p.get(sec, {}).get(key)
            if v and not (v['min'] <= v['max'] and (v['default'] is None or v['min'] <= v['default'] <= v['max'])):
                self.add('error', 'settings', w, f'{sec}.{key}: need min <= default <= max, got {v}')
        b = p.get('bedtime', {})
        for v in b.get('allowTimeOfDay', []):
            if v not in X.get('timesOfDay', []): self.add('error', 'settings', w, f'bedtime.allowTimeOfDay {v!r} not in taxonomy.timesOfDay')
        types = self.schemas['record']['properties']['type']['enum']
        for v in b.get('allowTypes', []):
            if v not in types: self.add('error', 'settings', w, f'bedtime.allowTypes {v!r} is not a record type')
        if b.get('enabled') and not (b.get('start') and b.get('end')): self.add('error', 'settings', w, 'bedtime is enabled but has no start/end time')
        for path in p.get('parentsMayChange', []):
            sec, key = path.split('.')
            if key not in self.schemas['payloads']['$defs']['settings']['properties'].get(sec, {}).get('properties', {}):
                self.add('error', 'settings', w, f'parentsMayChange {path!r} is not a setting')

    def type_lexicon(self, rid, r, w):
        pass  # checked against spoken lines in check_assets_and_voice

    def topic_of(self, r):
        for t in r['tags'].get('topics', []):
            if t in self.S.records: return self.S.records[t]
        return None

    # ---- references ----------------------------------------------------
    def check_refs(self):
        S = self.S
        self.excluded = set(S.records) - S.in_channel(self.allowed)
        rules = [(t, re.compile(p), want) for t, p, want in REF_TYPES]
        self.soft_links = []
        for rid, r in S.records.items():
            if not isinstance(r, dict) or 'type' not in r: continue
            w = S.where(rid)
            mypack = S.pack_of(rid)
            for path, v in walk({k: r.get(k) for k in ('tags', 'evidence', 'payload')}):
                if not isinstance(v, str) or not v.startswith('ew.'): continue
                if not ID_RE.match(v):
                    self.add('error', 'ref', w, f'{path}: {v!r} looks like an id but is malformed'); continue
                tgt = S.records.get(v)
                if tgt is None:
                    self.add('error', 'ref', w, f'{path}: points at {v}, which does not exist'); continue
                want = next((wt for t, rx, wt in rules if (t == '*' or t == r['type']) and rx.match(path)), None)
                if want and tgt['type'] not in want:
                    self.add('error', 'ref-type', w, f'{path}: {v} is a {tgt["type"]}, expected {"/".join(sorted(want))}')
                tp = S.pack_of(v)
                soft = r['type'] == 'land' and path.endswith('.country')
                # a land place may point at a draft quiz bank: on a channel that leaves the bank out, the build drops
                # the place (type bank) or just its "quiz" link (deck quizzes keep working with the built-in rules)
                qsoft = r['type'] == 'land' and path.endswith('.quiz')
                if tp != mypack and tp != 'core':
                    if soft: self.soft_links.append((rid, v))
                    else: self.add('error', 'pack-dependency', w, f'{path}: {v} is in pack {tp}; a pack may only use its own records and core')
                if rid not in self.excluded and v in self.excluded and not soft and not qsoft and path != 'payload.assetId':
                    self.add('error', 'ref-status', w, f'{path}: {v} has status {tgt["status"]}, which the {self.channel} channel leaves out')
                if tgt.get('status') == 'withdrawn' and rid not in self.excluded:
                    self.add('error', 'withdrawn', w, f'{path}: uses withdrawn record {v}')

    # ---- files on disk: pictures and voice clips -------------------------
    # ---- languages: coverage per language, fallback chains, right-to-left --------------------------------------
    RTL_SCRIPTS = {'Arab', 'Hebr', 'Thaa', 'Syrc', 'Nkoo', 'Adlm', 'Rohg', 'Mand', 'Samr'}
    STRONG_RTL = re.compile('[\u0590-\u08FF\uFB1D-\uFDFF\uFE70-\uFEFF]')
    BIDI_OVERRIDE = re.compile('[\u202D\u202E]')
    BIDI_EMBED = re.compile('[\u202A\u202B]')

    def check_languages(self, recs, LOC, chan_locs):
        S, lcfg = self.S, self.cfg.get('locales', {})
        src = lcfg.get('sourceLocale', 'en')
        scripts = lcfg.get('scripts', {})
        for tag, l in LOC.items():
            w = 'content/src/locales.json'
            if l.get('script') and l['script'] not in scripts:
                self.add('error', 'locale', w, f'{tag}: script {l["script"]} has no font stack in "scripts"')
            rtl_script = l.get('script') in self.RTL_SCRIPTS
            if (l.get('dir') == 'rtl') != rtl_script:
                self.add('error', 'rtl', w, f'{tag}: dir {l.get("dir")!r} does not match script {l.get("script")} (right-to-left scripts: {", ".join(sorted(self.RTL_SCRIPTS))})')
            for f in l.get('fallback', []):
                if f not in LOC: self.add('error', 'locale', w, f'{tag}: fallback {f} is not a language in locales.json')
                elif f == tag: self.add('error', 'locale', w, f'{tag}: falls back to itself')
            ch = chain_for(lcfg, tag)
            if ch[-1] != src and src in LOC: self.add('error', 'locale', w, f'{tag}: fallback chain {ch} does not end in the source language {src}')
            if l.get('status') == 'active' and not l.get('voice'):
                self.add('warn', 'no-voice', w, f'{tag} is active but has no voice: children see text only')
        # localized pictures <name>.<tag>.<ext>: the language must exist and the original picture must be there too
        pat = re.compile(r'^(.+)\.([A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)\.(webp|jpe?g|png)$')
        imgdir = os.path.join(S.root, 'img')
        self.stats['pictureVariants'] = {}
        for d, _, fs in os.walk(imgdir):
            for f in fs:
                m = pat.match(f)
                if not m or m.group(2).lower() in ('min', 'thumb', 'bg', 'old'): continue
                rel = os.path.relpath(os.path.join(d, f), S.root).replace(os.sep, '/')
                base = os.path.relpath(os.path.join(d, m.group(1) + '.' + m.group(3)), S.root).replace(os.sep, '/')
                tag = m.group(2)
                if tag not in LOC:
                    self.add('warn', 'picture-variant', rel, f'looks like a localized picture for {tag!r}, which is not a language in locales.json')
                elif not os.path.isfile(os.path.join(S.root, base)):
                    self.add('error', 'picture-variant', rel, f'localized picture has no original {base} (the original is shown in every other language)')
                else:
                    self.stats['pictureVariants'].setdefault(tag, []).append(base)
        # coverage: share of translatable texts each shipped language has (records marked sourceOnly are skipped)
        cov = {lg: {} for lg in chan_locs}
        self.missing_text = {lg: [] for lg in chan_locs}
        for rid, r in recs.items():
            if r.get('l10n', {}).get('sourceOnly'): continue
            pk = S.pack_of(rid)
            for path, lt in walk_lt({'payload': r['payload']}, self.locales):
                for lg in chan_locs:
                    c = cov[lg].setdefault(pk, [0, 0]); c[1] += 1
                    if lt.get(lg) is not None: c[0] += 1
                    elif lg != src and len(self.missing_text[lg]) < 2000: self.missing_text[lg].append((rid, path))
                    if lt.get(lg) is not None and (LOC.get(lg) or {}).get('dir') == 'rtl':
                        t = lt[lg]; wr = S.where(rid)
                        if self.BIDI_OVERRIDE.search(t): self.add('error', 'rtl', wr, f'{path}.{lg}: contains a bidi override (U+202D/U+202E) - can reverse text; use isolates (U+2066-2069)')
                        elif self.BIDI_EMBED.search(t): self.add('warn', 'rtl', wr, f'{path}.{lg}: uses old bidi embeddings (U+202A/B); prefer isolates (U+2066-2069)')
                        if not self.STRONG_RTL.search(t) and re.search('[A-Za-z]{3,}', t) and t != lt.get(src):
                            self.add('warn', 'rtl', wr, f'{path}.{lg}: right-to-left language text has no right-to-left letters: {t[:50]!r}')
                        elif t == lt.get(src) and re.search('[A-Za-z]{3,}', t):
                            self.add('warn', 'rtl', wr, f'{path}.{lg}: identical to the {src} text (not translated?)')
        self.coverage = cov
        for lg in chan_locs:
            if lg == src: continue
            n, tot = sum(v[0] for v in cov[lg].values()), sum(v[1] for v in cov[lg].values())
            st = (LOC.get(lg) or {}).get('status')
            miss = self.missing_text[lg]
            msg = f'[{lg}] {n}/{tot} texts translated ({(100 * n / tot if tot else 100):.0f}%); missing ones show in {" -> ".join(chain_for(lcfg, lg, chan_locs)[1:])}'
            self.add('warn' if st == 'active' and miss else 'info', 'coverage', 'content', msg)
            for rid, path in miss[:8 if st == 'active' else 0]:
                self.add('warn', 'missing-translation', S.where(rid), f'[{lg}] {path}')

    def check_assets_and_voice(self):
        if not self.check_files:
            return
        S, root = self.S, self.S.root
        rules = sorted(self.cfg.get('rights', {}).get('rules', []), key=lambda x: -len(x['prefix']))
        self.assets = {}
        map2 = os.path.join(root, 'img', 'world', 'map2')
        for rid, r in S.records.items():
            if 'payload' not in r: continue
            w = S.where(rid)
            for path, v in walk(r['payload'], 'payload'):
                if not isinstance(v, str): continue
                if re.match(r'^(img|voice|icons|fonts)/', v):
                    if not os.path.isfile(os.path.join(root, v)):
                        self.add('error', 'missing-file', w, f'{path}: file {v} does not exist')
                    elif not any(v.startswith(x['prefix']) for x in rules):
                        self.add('error', 'rights', w, f'{path}: no rights rule covers {v} (content/src/rights.json)')
                    self.assets.setdefault(v, set()).add(S.pack_of(rid))
                elif path.endswith(('.icon2', '.bg2', '.art2')) and not os.path.isfile(os.path.join(map2, v)):
                    self.add('info', 'optional-art', w, f'{path}: optional new art {v} not made yet (old art is used)')
        # spoken lines -> voice clips, per language, using the same rules as the app (world.js, country.js)
        self.spoken = {}            # text -> (pack, language) - first language that speaks it
        self.spoken_by_lang = {}    # language -> {text: (pack, language the text is in)}
        recs = {rid: S.records[rid] for rid in S.in_channel(self.allowed)}
        lcfg = self.cfg.get('locales', {})
        LOC = {l['tag']: l for l in lcfg.get('locales', [])}
        chan_locs = list(S.channel_locales)
        try:
            for lang in chan_locs:
                ch = chain_for(lcfg, lang, chan_locs)
                seen, got = {}, {}
                L = legacy.lands(recs, self.locales, ch, seen)
                ui = legacy.ui_spoken(recs, ch, seen)
                for t in legacy.world_spoken(L, seen, ui): got.setdefault(t, ('core', seen.get(t, lcfg.get('sourceLocale', 'en'))))
                for t, lg in legacy.quiz_spoken(recs, ch): got.setdefault(t, ('core', lg))
                uic = legacy.ui_strings(recs) if 'ew.ui.country-player' in recs else None
                for r in recs.values():
                    if r['type'] == 'country':
                        pk, bank = legacy.country(recs, r['id'])
                        offered = [l for l in pk['locales'] if l in chan_locs] or [lcfg.get('sourceLocale', 'en')]
                        cl = next((l for l in ch if l in offered), offered[0])   # country.js: app language if the pack has it
                        for t, lg in legacy.country_spoken(pk, bank, uic, (cl,)): got.setdefault(t, (S.pack_of(r['id']), lg))
                self.spoken_by_lang[lang] = got
                for t, v in got.items(): self.spoken.setdefault(t, v)
        except Exception as e:
            self.add('error', 'adapter', 'content/src', f'could not build the app view of the content: {type(e).__name__}: {e}')
            return
        self.voice_missing = {}
        src = lcfg.get('sourceLocale', 'en')
        for lang, got in self.spoken_by_lang.items():
            miss = []
            for t, (p, lg) in got.items():
                V = (LOC.get(lg) or {}).get('voice')
                if not V: continue          # that language has no voice yet (text only) - reported in coverage
                if not os.path.isfile(os.path.join(root, V['pack'], vh(t) + '.mp3')): miss.append((t, p, lg, V['pack']))
            self.voice_missing[lang] = miss
            st = (LOC.get(lang) or {}).get('status')
            sev = 'error' if (lang == src or st == 'active') else 'warn' if st == 'in-review' else 'info'
            for t, p, lg, pk in miss[:25]:
                self.add(sev, 'missing-voice', p, f'[{lang}] no voice clip {pk}{vh(t)}.mp3 for ({lg}): {t[:80]!r}')
            if len(miss) > 25:
                self.add(sev, 'missing-voice', 'content', f'[{lang}] ... and {len(miss) - 25} more lines without voice clips')
        self.stats['spoken'] = len(self.spoken)
        self.stats['voiceMissing'] = sum(len(v) for v in self.voice_missing.values())
        self.stats['voiceByLang'] = {lg: {'lines': len(got), 'missing': len(self.voice_missing.get(lg, [])),
                                          'voice': bool((LOC.get(lg) or {}).get('voice'))} for lg, got in self.spoken_by_lang.items()}
        self.check_languages(recs, LOC, chan_locs)
        lex = S.records.get('ew.lexicon.letter-sounds')
        if lex:
            for e in lex['payload']['entries']:
                if e['text'] not in self.spoken:
                    self.add('warn', 'lexicon', S.where(lex['id']), f'pronunciation entry {e["text"]!r} is not a spoken line')
