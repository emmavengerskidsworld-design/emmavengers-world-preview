/* ===== Emmavengers World languages (Stage 2) =====
   One place for everything language-related, so a new language needs DATA only (content/src/locales.json +
   texts + voice clips), never code:
   - EWi18n.lang / .dir / .chain        chosen language, its direction and fallback chain (e.g. fr-CM -> fr -> en)
   - EWi18n.t(key, vars)                app words (buttons, praise, titles) from the content record ew.ui.app, in the
                                        chosen language with fallback; ICU-style placeholders: {name}, {n, number},
                                        {n, plural, one {# star} other {# stars}}, {g, select, a {..} other {..}}
                                        (plural categories from Intl.PluralRules = CLDR, so Arabic gets zero/one/two/few/many)
   - EWi18n.list(key)                   a word list (e.g. praise lines) - one entry per line in the text
   - EWi18n.n(x)                        number in the language's own digits/format (Intl.NumberFormat)
   - EWi18n.pick(lt)                    a {"en":..,"fr":..} text in the chosen language -> string
   - EWi18n.voiceBase(text)             folder of the clip for a text (the language the text really came from)
   - EWi18n.set(tag)                    switch language: downloads only that language's files, updates <html lang dir>,
                                        the font stack for its script, and tells the screens to redraw ('ewlang' event)
   Right-to-left languages get <html dir="rtl">; layout CSS uses logical properties (inline-start/end), so text
   and controls mirror; maps and pictures keep their art direction. */
(function (G) {
'use strict';
const D = G.document;
const I = { lang: 'en', dir: 'ltr', chain: ['en'], ok: false, ready: null, locales: [] };
let LIB = null, UI = {}, nfCache = {}, prCache = {};
const loc = t => I.locales.find(l => l.tag === t) || null;

/* ---------- message format (small, safe subset of ICU MessageFormat) ---------- */
function parse(s, i, stop) { /* returns [nodes, nextIndex]; node = string | {arg, type, opts} */
  const out = []; let buf = '';
  while (i < s.length) {
    const c = s[i];
    if (c === "'" && s[i + 1] === "'") { buf += "'"; i += 2; continue }
    if (c === '{') { if (buf) { out.push(buf); buf = '' }
      let j = i + 1, depth = 1; const st = j; while (j < s.length && s[j] !== ',' && s[j] !== '}') j++;
      const arg = s.slice(st, j).trim();
      if (s[j] === '}') { out.push({ arg }); i = j + 1; continue }
      let k = j + 1; while (k < s.length && s[k] !== ',' && s[k] !== '}') k++;
      const type = s.slice(j + 1, k).trim();
      if (s[k] === '}') { out.push({ arg, type }); i = k + 1; continue }
      /* options: key {message} key {message} ... } */
      const opts = {}; k++;
      while (k < s.length) {
        while (/\s/.test(s[k])) k++;
        if (s[k] === '}') { k++; break }
        let ks = k; while (k < s.length && s[k] !== '{' && !/\s/.test(s[k])) k++;
        const key = s.slice(ks, k); while (/\s/.test(s[k])) k++;
        if (s[k] !== '{') throw new Error('bad message: ' + s);
        const [nodes, nx] = parse(s, k + 1, '}'); opts[key] = nodes; k = nx;
      }
      out.push({ arg, type, opts }); i = k; void depth; continue }
    if (c === stop) { if (buf) out.push(buf); return [out, i + 1] }
    buf += c; i++;
  }
  if (buf) out.push(buf); return [out, i];
}
const PCACHE = new Map();
function compiled(s) { let p = PCACHE.get(s); if (!p) { try { p = parse(s, 0, null)[0] } catch (e) { p = [s] } PCACHE.set(s, p) } return p }
function nf(lang) { return nfCache[lang] || (nfCache[lang] = (() => { const L = loc(lang); try { return new Intl.NumberFormat(L && L.numberingSystem ? lang + '-u-nu-' + L.numberingSystem : lang) } catch (e) { return { format: String } } })()) }
function pr(lang) { return prCache[lang] || (prCache[lang] = (() => { try { return new Intl.PluralRules(lang) } catch (e) { return { select: n => n === 1 ? 'one' : 'other' } } })()) }
function render(nodes, vars, lang, hash) {
  let s = '';
  for (const n of nodes) {
    if (typeof n === 'string') { s += hash != null ? n.replace(/#/g, nf(lang).format(hash)) : n; continue }
    const v = vars ? vars[n.arg] : undefined;
    if (!n.type) { s += v == null ? '' : (typeof v === 'number' ? nf(lang).format(v) : String(v)); continue }
    if (n.type === 'number') { s += nf(lang).format(+v || 0); continue }
    if (n.type === 'plural' && n.opts) { const x = +v || 0; const o = n.opts['=' + x] || n.opts[pr(lang).select(x)] || n.opts.other || []; s += render(o, vars, lang, x); continue }
    if (n.type === 'select' && n.opts) { const o = n.opts[String(v)] || n.opts.other || []; s += render(o, vars, lang, hash); continue }
    s += v == null ? '' : String(v);
  }
  return s;
}
I.format = (msg, vars, lang) => render(compiled(String(msg)), vars, lang || I.lang);

/* ---------- lookups ---------- */
function pickLt(lt) {
  if (lt == null) return { text: '', lang: null };
  if (typeof lt === 'string') return { text: lt, lang: null };
  for (const l of I.chain) if (lt[l] != null) return { text: lt[l], lang: l };
  const k = Object.keys(lt)[0]; return { text: k ? lt[k] : '', lang: k || null };
}
const SPOKEN = new Map(); /* text -> language it is in (for the voice) */
I.pick = lt => { const r = pickLt(lt); if (r.text && r.lang) SPOKEN.set(r.text, r.lang); return r.text };
I.t = (key, vars) => { const lt = UI[key]; if (!lt) return key; const r = pickLt(lt); const out = vars || /[{}']/.test(r.text) ? I.format(r.text, vars, r.lang || I.lang) : r.text; if (r.lang) SPOKEN.set(out, r.lang); return out };
I.has = key => !!UI[key];
I.list = key => I.t(key).split('\n').map(x => x.trim()).filter(Boolean).map(x => { SPOKEN.set(x, SPOKEN.get(I.t(key)) || I.lang); return x });
I.n = x => nf(I.lang).format(x);
I.langOf = t => SPOKEN.get(t) || (LIB && LIB.langOf && LIB.langOf(t)) || null;
I.markLang = (t, lang) => { if (t && lang) SPOKEN.set(t, lang) };
/* voice clip folder for a text: the voice of the language the text is in (null = this language has no voice) */
I.voiceBase = t => { const lg = I.langOf(t) || I.lang, L = loc(lg); if (!L) return 'voice/'; return L.voice ? L.voice.pack : null };
I.voiceLang = t => I.langOf(t) || I.lang;
I.name = tag => { const L = loc(tag); return L ? L.name : tag };

/* ---------- document language, direction, script fonts ---------- */
function apply() {
  const L = loc(I.lang) || { dir: 'ltr', fonts: null }; I.dir = L.dir || 'ltr';
  if (!D) return;
  const h = D.documentElement; h.lang = I.lang; h.dir = I.dir;
  h.classList.toggle('rtl', I.dir === 'rtl');
  h.dataset.script = L.script || 'Latn';
  if (L.fonts && L.fonts.length) h.style.setProperty('--ew-font', L.fonts.map(f => /^[a-z-]+$/.test(f) ? f : '"' + f.replace(/"/g, '') + '"').join(', '));
  else h.style.removeProperty('--ew-font');
  D.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = I.t(el.dataset.i18n) });
  D.querySelectorAll('[data-i18n-label]').forEach(el => { const v = I.t(el.dataset.i18nLabel); el.setAttribute('aria-label', v); if (el.hasAttribute('title')) el.title = v });
}
function sync() {
  I.lang = LIB.lang(); I.chain = LIB.chain(); I.locales = LIB.locales();
  const r = LIB.get('ew.ui.app'); UI = (r && r.payload && r.payload.strings) || {};
  nfCache = {}; prCache = {}; apply();
}
I.set = async tag => {
  if (!LIB) throw new Error('library not ready');
  if (tag === I.lang) return I.chain;
  await LIB.setLanguage(tag); sync();
  try { G.dispatchEvent(new CustomEvent('ewlang', { detail: { lang: I.lang, chain: I.chain } })) } catch (e) {}
  return I.chain;
};
/* languages a child can pick here: what this site's catalog offers (live: active only; preview: + in-review) */
I.offered = () => I.locales.map(l => ({ tag: l.tag, name: l.name, englishName: l.englishName, dir: l.dir, status: l.status, voicePack: (l.voice && l.voice.pack) || null }));
/* I.ready: Promise resolved when the library and the chosen language are loaded; I.ok: true from then on */
I.ready = (G.EWLib ? G.EWLib.ready : Promise.reject(new Error('no library'))).then(L => { LIB = L; sync(); I.ok = true; return I });
I.ready.catch(() => {});
G.EWi18n = I;
})(typeof window !== 'undefined' ? window : globalThis);
