"""Build the offline caches: scans the repo and writes sw.js (+ bible-manifest.json) with a build id.
Run after ANY change (new room, images, voice clips, Bible book, index.html):  python3 tools/build_sw.py

Caching layers
  0. SHELL (downloaded at install, ~5 MB): html/css/js/fonts/icons/manifest + Emmavengers World map art (img/world/).
     The service worker takes over as soon as the shell is on the phone; the rest of CORE then downloads in the
     background (pausing while the child taps). Before Stage 2's fix the whole 55 MB core had to finish first, so on
     a slow phone the app could stay uncontrolled for a long time: no offline, every voice clip from the network.
  1. CORE (all of it on the phone after the first visit): html/css/js/icons/manifest, room pictures, morning clips, default Mia voice,
     and every Bible book COVER (so the library shelf shows offline).
  2. BIBLE BOOKS (cache 'emma-books', survives app updates): each book's pages (img/bible/<slug>/*.jpg) and its
     narration clips. Cached in full the first time a book is opened online, and every book listed in
     bible-manifest.json is prefetched in the background whenever the game is online — so newly added books
     download automatically. A book is re-fetched only when its version (content hash) changes.
  3. VOICE PACKS: voice/<id>/*.mp3 (lily, zara, ...) are cached on demand when a child picks that voice.
"""
import os, re, hashlib, json
try:
    from PIL import Image
except Exception:
    Image = None
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {'.git', 'tools', 'node_modules', 'voice-samples'}
SKIP_FILES = {'sw.js', 'README.md', '.nojekyll', 'bible-manifest.json'}
SKIP_EXT = ('.bak', '.py', '.log', '.md', '.DS_Store')
# content libraries (content/library = live, content/preview = preview; built by tools/content_build.py): library.js
# downloads and verifies them itself and keeps them in IndexedDB, only in the languages the child uses. So the
# service worker never precaches or stores them (no second copy, no other languages downloaded behind the child's
# back). Sources, schemas, docs and registry locks are never downloaded by the app.
SKIP_PATHS = ('content/', 'docs/')
LOCALES = json.load(open(os.path.join(ROOT, 'content', 'src', 'locales.json'), encoding='utf-8'))
TAGS = {l['tag'] for l in LOCALES['locales']}
SRC = LOCALES.get('sourceLocale', 'en')
# voice/<tag>/ = the voice of one language (locales.json "voice.pack"); downloaded when that language is chosen
LANG_VOICE = {l['voice']['pack'].strip('/').split('/')[-1]: l['tag'] for l in LOCALES['locales']
              if l.get('voice') and l['voice']['pack'].rstrip('/') != 'voice'}
# localized picture variants (<name>.<tag>.<ext>, e.g. img/world/nature-land.fr.webp): fetched when used, not precached
VARIANT = re.compile(r'\.(' + '|'.join(sorted((re.escape(t) for t in TAGS if t != SRC), key=len, reverse=True) or ['$^']) + r')\.(webp|jpe?g|png|svg)$')

def make_thumbs():
    """Small shelf thumbnails for Bible covers (fast Library screen on slow networks)."""
    bd = os.path.join(ROOT, 'img', 'bible')
    if not Image or not os.path.isdir(bd): return
    for slug in os.listdir(bd):
        c, t = os.path.join(bd, slug, 'cover.jpg'), os.path.join(bd, slug, 'thumb.jpg')
        if os.path.exists(c) and (not os.path.exists(t) or os.path.getmtime(t) < os.path.getmtime(c)):
            im = Image.open(c).convert('RGB'); im.thumbnail((480, 270)); im.save(t, quality=78, optimize=True)
make_thumbs()

def make_world_thumbs():
    """192px tile thumbnails for Emmavengers World grids (fast first voice on slow networks)."""
    src = os.path.join(ROOT, 'img', 'world')
    if not Image or not os.path.isdir(src): return
    for sub in ('letters', 'animals', 'numbers', 'countries', 'prayers'):
        d = os.path.join(src, sub)
        if not os.path.isdir(d): continue
        od = os.path.join(src, 'thumbs', sub); os.makedirs(od, exist_ok=True)
        for f in os.listdir(d):
            if not f.endswith('.webp'): continue
            a, b = os.path.join(d, f), os.path.join(od, f)
            if not os.path.exists(b) or os.path.getmtime(b) < os.path.getmtime(a):
                im = Image.open(a); im.thumbnail((192, 192)); im.save(b, 'WEBP', quality=80, method=6)
make_world_thumbs()

def write_map2_ready():
    """img/world/map2/ready.json lists the new world-map art that exists, so the game uses it (else placeholders)."""
    d = os.path.join(ROOT, 'img', 'world', 'map2'); os.makedirs(d, exist_ok=True)
    have = sorted(f for f in os.listdir(d) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')))
    json.dump(have, open(os.path.join(d, 'ready.json'), 'w'))
write_map2_ready()

def vh(t):
    h = 0x811c9dc5; b = t.encode('utf-16-le')
    for i in range(0, len(b), 2):
        h ^= b[i] | (b[i+1] << 8); h = (h * 0x01000193) & 0xffffffff
    return f'{h:08x}'
assert vh('Pick a room to play!') == '2d584f8e'

html = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
m = re.search(r'/\*BIBLE_DATA\*/(.*?)/\*END_BIBLE_DATA\*/', html, re.S)
BIBLE = json.loads(m.group(1)) if m else {}
outside = html[:m.start()] + html[m.end():] if m else html
def strings(b):
    s = [x for p in b['pages'] for x in p['say']] + [b.get('done', '')]
    s += [q['q'] for q in b['quiz']] + [o for q in b['quiz'] for o in q['opts']]
    return [x for x in dict.fromkeys(s) if x]

# book voice hashes; a clip leaves the core precache only if its text is not also used literally elsewhere in the game
book_voice, book_only = {}, set()
for slug, b in BIBLE.items():
    hs = []
    for t in strings(b):
        h = vh(t)
        if os.path.exists(os.path.join(ROOT, 'voice', h + '.mp3')):
            hs.append(h)
            if json.dumps(t)[1:-1] not in outside and t not in outside:
                book_only.add(h)
    book_voice[slug] = sorted(set(hs))
book_dirs = {slug: b['dir'].rstrip('/') + '/' for slug, b in BIBLE.items()}

files, total, core_total = [], 0, 0
revs = []  # SHA-256 prefix of each precached file (same order as ASSETS after './'): lets the SW reuse ONLY unchanged files
h = hashlib.sha256()
voice_packs = {}
books = {slug: {'files': [], 'h': hashlib.sha256(), 'bytes': 0} for slug in BIBLE}
for d, ds, fs in os.walk(ROOT):
    ds[:] = sorted(x for x in ds if x not in SKIP_DIRS and not x.startswith('.'))
    rel_dir = os.path.relpath(d, ROOT).replace(os.sep, '/')
    under_voice_pack = rel_dir.startswith('voice/') and rel_dir != 'voice'
    for f in sorted(fs):
        rel = os.path.relpath(os.path.join(d, f), ROOT).replace(os.sep, '/')
        if f in SKIP_FILES or rel in SKIP_FILES or f.endswith(SKIP_EXT) or f.startswith('.') or rel.startswith(SKIP_PATHS):
            continue
        if VARIANT.search(f):
            continue
        data = open(os.path.join(ROOT, rel), 'rb').read()
        total += len(data)
        dig = hashlib.sha256(data).digest()
        h.update(rel.encode() + b'\0' + dig)
        url = './' + rel
        if under_voice_pack:
            vd = rel.split('/')[1]
            # a language's voice folder is pack 'lang:<folder>' (fr and fr-CM share voice/fr/ -> one pack 'lang:fr')
            voice_packs.setdefault('lang:' + vd if vd in LANG_VOICE else vd, []).append(url)
            continue
        slug = next((s for s, bd in book_dirs.items() if rel.startswith(bd)), None)
        if slug and f not in ('cover.jpg', 'thumb.jpg'):
            bk = books[slug]; bk['files'].append(url); bk['h'].update(rel.encode() + dig); bk['bytes'] += len(data)
            continue
        if rel_dir == 'voice' and f[:-4] in book_only:
            for s2, hs in book_voice.items():
                if f[:-4] in hs:
                    books[s2]['h'].update(rel.encode() + dig); books[s2]['bytes'] += len(data)
            continue
        files.append(url); revs.append(dig.hex()[:16]); core_total += len(data)

voice_packs['mia'] = [u for u in files if u.startswith('./voice/') and u.endswith('.mp3') and u.count('/') == 2] + \
                     sorted({f'./voice/{x}.mp3' for x in book_only})
manifest = {slug: {'v': books[slug]['h'].hexdigest()[:12], 'title': BIBLE[slug]['title'], 'files': books[slug]['files'],
                   'voice': book_voice[slug]} for slug in BIBLE}
SHELL_EXT = ('.html', '.js', '.css', '.ttf', '.woff', '.woff2', '.otf', '.png', '.svg', '.json', '.webmanifest', '.ico')
def is_shell(u):
    p = u[2:]
    return (not p.startswith('voice/')) and ('/' not in p and p.endswith(SHELL_EXT) or p.startswith('icons/') or p.startswith('fonts/')
                                             or p.startswith('img/world/'))
shell = ''.join('1' if is_shell(u) else '0' for u in files)
shell_bytes = sum(os.path.getsize(os.path.join(ROOT, u[2:])) for u in files if is_shell(u))
tpl = open(os.path.join(ROOT, 'tools', 'sw.template.js')).read()
h.update(b'sw.template.js\0' + tpl.encode())  # a service-worker code change is a new build too
build = h.hexdigest()[:12]
out = (tpl.replace('__BUILD__', build)
          .replace('__ASSETS__', json.dumps(['./'] + files, separators=(',', ':')))
          .replace('__SHELL__', json.dumps('1' + shell))
          .replace('__REVS__', json.dumps([''] + revs, separators=(',', ':')))
          .replace('__VOICE_PACKS__', json.dumps(voice_packs, separators=(',', ':')))
          .replace('__LANG_DIRS__', json.dumps(sorted(LANG_VOICE), separators=(',', ':')))
          .replace('__BOOKS__', json.dumps(manifest, separators=(',', ':'))))
open(os.path.join(ROOT, 'sw.js'), 'w').write(out)
json.dump({'build': build, 'books': manifest}, open(os.path.join(ROOT, 'bible-manifest.json'), 'w'), separators=(',', ':'))
pack_n = {k: len(v) for k, v in sorted(voice_packs.items())}
bk_n = {s: f"{len(b['files'])} img + {len(book_voice[s])} voice, {b['bytes']/1e6:.1f} MB" for s, b in books.items()}
print(f'build {build}: core precache {len(files)} files, {core_total/1e6:.1f} MB (repo total {total/1e6:.1f} MB); '
      f'shell at install {shell.count("1") + 1} files, {shell_bytes/1e6:.1f} MB')
print(f'bible books (cached on open + background prefetch online): {bk_n}')
print(f'voice packs (on demand): {pack_n}')
