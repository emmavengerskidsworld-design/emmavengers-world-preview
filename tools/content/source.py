"""Load the authoring source (content/src) into records.

Layout: content/src/{locales,taxonomy,capabilities,collections,build,rights}.json are settings.
Any folder holding a pack.json is a pack; every other .json file in that folder (not sub-folders) is a source file
whose records belong to that pack. Pack defaults are merged into each record (record values win; tags key by key)."""
import copy, os
from .common import load_json

CONFIGS = ('locales', 'taxonomy', 'capabilities', 'collections', 'build', 'rights')


def channel_locales(cfg, channel):
    """Language tags a build channel ships (build.json channels.<c>.locales lists language statuses)."""
    ch = cfg.get('build', {}).get('channels', {}).get(channel or cfg.get('build', {}).get('channel'), {})
    ok = set(ch.get('locales', ['active', 'in-review']))
    return [l['tag'] for l in cfg.get('locales', {}).get('locales', []) if l.get('status') in ok]


def resolve_path(rec, path):
    """'payload.places.cameroon.name' -> the localized-text dict it names (list items are addressed by their
    key/id, or by number). Returns (container, key) or raises KeyError with a readable reason."""
    cur, parts = rec, path.split('.')
    for i, seg in enumerate(parts):
        last = i == len(parts) - 1
        if isinstance(cur, list):
            hit = next((x for x in cur if isinstance(x, dict) and (x.get('key') == seg or x.get('id') == seg)), None)
            if last and seg.isdigit() and int(seg) < len(cur): return cur, int(seg)
            if hit is None and seg.isdigit() and int(seg) < len(cur): hit = cur[int(seg)]
            if hit is None: raise KeyError(f'no list item with key/id {seg!r}')
            if last: raise KeyError('path ends on a list item, not a text')
            cur = hit; continue
        if not isinstance(cur, dict) or seg not in cur: raise KeyError(f'{seg!r} not found')
        if last: return cur, seg
        cur = cur[seg]
    raise KeyError('empty path')


class Source:
    def __init__(self, src_dir, repo_root, channel=None):
        self.dir = os.path.abspath(src_dir)
        self.root = os.path.abspath(repo_root)
        self.cfg = {}
        self.packs = {}       # pack id -> {'meta':..., 'dir':..., 'files': [...], 'records': [ids]}
        self.records = {}     # id -> merged record (first one if duplicated)
        self.origin = {}      # id -> (pack id, relative file, index)
        self.duplicates = []  # (id, first origin, second origin)
        self.raw_files = []   # (relpath, json) for schema checks
        self.errors = []      # load errors (bad JSON etc.)
        for c in CONFIGS:
            p = os.path.join(self.dir, c + '.json')
            try:
                self.cfg[c] = load_json(p)
            except Exception as e:
                self.errors.append(f'{c}.json: cannot read ({e})')
                self.cfg[c] = {}
        self.locales = [l['tag'] for l in self.cfg.get('locales', {}).get('locales', [])]
        self.channel = channel or self.cfg.get('build', {}).get('channel')
        self.channel_locales = channel_locales(self.cfg, self.channel)
        l10n_dir = os.path.join(self.dir, 'l10n')
        for d, ds, fs in os.walk(self.dir):
            ds.sort()
            if os.path.abspath(d).startswith(l10n_dir) or 'pack.json' not in fs:
                continue
            self._load_pack(d, sorted(fs))
        self.overlays = []          # (file, locale, record id, path) applied
        self.overlay_skipped = []   # (file, locale) not in this channel
        if os.path.isdir(l10n_dir):
            for tag in sorted(os.listdir(l10n_dir)):
                td = os.path.join(l10n_dir, tag)
                if not os.path.isdir(td): continue
                for f in sorted(os.listdir(td)):
                    if f.endswith('.json'): self._load_overlay(os.path.join(td, f), tag)

    def rel(self, p):
        return os.path.relpath(p, self.dir).replace(os.sep, '/')

    def _load_pack(self, d, fs):
        pj = os.path.join(d, 'pack.json')
        try:
            meta = load_json(pj)
        except Exception as e:
            self.errors.append(f'{self.rel(pj)}: cannot read ({e})')
            return
        self.raw_files.append((self.rel(pj), meta, 'pack-source'))
        pid = meta.get('id')
        if pid in self.packs:
            self.errors.append(f'{self.rel(pj)}: pack id {pid} already used by {self.packs[pid]["dir"]}')
            return
        P = self.packs[pid] = {'meta': meta, 'dir': self.rel(d), 'files': [], 'records': []}
        defaults = meta.get('defaults', {})
        for f in fs:
            if not f.endswith('.json') or f == 'pack.json':
                continue
            p = os.path.join(d, f)
            try:
                doc = load_json(p)
            except Exception as e:
                self.errors.append(f'{self.rel(p)}: not valid JSON ({e})')
                continue
            self.raw_files.append((self.rel(p), doc, 'source-file'))
            P['files'].append(self.rel(p))
            for i, r in enumerate(doc.get('records', []) if isinstance(doc, dict) else []):
                if not isinstance(r, dict):
                    self.errors.append(f'{self.rel(p)} record #{i}: not an object')
                    continue
                m = merge_defaults(defaults, r)
                rid = m.get('id')
                o = (pid, self.rel(p), i)
                if rid in self.records:
                    self.duplicates.append((rid, self.origin[rid], o))
                    continue
                self.records[rid] = m
                self.origin[rid] = o
                P['records'].append(rid)

    def _load_overlay(self, p, tag):
        """content/src/l10n/<tag>/<name>.json: texts of one language for records defined elsewhere
        {"locale": "<tag>", "strings": {"<record id>": {"<path>": "<text>"}}}. Applied only when the build channel
        ships that language (a test-only language never reaches preview or live files)."""
        rel = self.rel(p)
        try:
            doc = load_json(p)
        except Exception as e:
            self.errors.append(f'{rel}: not valid JSON ({e})'); return
        self.raw_files.append((rel, doc, 'l10n-file'))
        if not isinstance(doc, dict) or doc.get('locale') != tag:
            self.errors.append(f'{rel}: "locale" must be {tag!r} (the folder name)'); return
        if tag not in self.locales:
            self.errors.append(f'{rel}: language {tag} is not in locales.json'); return
        if tag not in self.channel_locales:
            self.overlay_skipped.append((rel, tag)); return
        for rid, paths in (doc.get('strings') or {}).items():
            r = self.records.get(rid)
            if r is None:
                self.errors.append(f'{rel}: {rid} does not exist'); continue
            for path, text in paths.items():
                try:
                    box, k = resolve_path(r, path)
                except KeyError as e:
                    self.errors.append(f'{rel}: {rid} {path}: {e}'); continue
                lt = box[k]
                if not (isinstance(lt, dict) and lt and all(isinstance(x, str) for x in lt.values())):
                    self.errors.append(f'{rel}: {rid} {path} is not a translatable text'); continue
                if tag in lt and lt[tag] != text:
                    self.errors.append(f'{rel}: {rid} {path} already has {tag} text in the record; keep one copy'); continue
                lt[tag] = text
                self.overlays.append((rel, tag, rid, path))

    def in_channel(self, statuses):
        """Ids that ship on a channel: the record's own status is allowed AND, for a topic pack (one with a summary
        record, e.g. a country), the topic itself is allowed. So a published card inside a draft country stays out
        until the country is published, and the country appears as one complete unit."""
        statuses = set(statuses)
        out = set()
        for rid, r in self.records.items():
            if not isinstance(r, dict) or r.get('status') not in statuses: continue
            P = self.packs.get(self.pack_of(rid)) or {}
            sm = (P.get('meta') or {}).get('summary')
            if sm and sm != rid and (self.records.get(sm) or {}).get('status') not in statuses: continue
            out.add(rid)
        return out

    def pack_of(self, rid):
        o = self.origin.get(rid)
        return o[0] if o else None

    def where(self, rid):
        o = self.origin.get(rid)
        return f'{o[1]} ({rid})' if o else rid


def merge_defaults(defaults, r):
    m = copy.deepcopy(r)
    for k, v in defaults.items():
        if k == 'tags':
            t = copy.deepcopy(v)
            t.update(m.get('tags', {}))
            m['tags'] = t
        elif k in ('review', 'l10n'):
            t = copy.deepcopy(m.get(k, {}))  # the record's own keys keep their order; pack defaults fill the gaps
            for kk, vv in v.items():
                if kk not in t: t[kk] = copy.deepcopy(vv)
            m[k] = t
        elif k not in m:
            m[k] = copy.deepcopy(v)
    # put the envelope in a stable, readable order
    order = ['id', 'type', 'status', 'sourceLanguage', 'tags', 'evidence', 'review', 'l10n', 'payload']
    return {k: m[k] for k in order if k in m} | {k: v for k, v in m.items() if k not in order}
