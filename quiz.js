/* ===== Emmavengers World quiz engine (Stage 3) - docs/quiz-engine.md =====
   One engine for every quiz: questions are content records (quiz-item), quizzes are quiz-bank records (authored items
   or a generator that makes questions from a card deck), and the rules are quiz-rules records. Nothing about a quiz is
   hard-coded here: how many questions, how many answer buttons, stars, hints, retries, spaced review, adaptive
   difficulty and what the voice reads all come from data (built-in defaults below = the quizzes before Stage 3).

   Part 1 (pure logic, no screen; also runs in Node for tools/test_quiz_engine.js):
     EWQuiz.rules(bank) merged rules        EWQuiz.stars(miss, R)          EWQuiz.choicesFor(R, band)
     EWQuiz.roundSize(R, band, fallback)    EWQuiz.buildRound({...})       EWQuiz.deckQuestion(pool, st, R, band)
     EWQuiz.countQuestion(gen, st, R, band) EWQuiz.rng(seed) / shuffle      EWQuiz.progress (this phone only)
   Part 2 (in the app): the generic quiz player screens qplay -> qdone for authored banks (single-choice,
   picture-pick, count, true-false, order, match), voice through the app's clip system (say / cacheClips / warmVoice).

   Privacy: progress (Leitner box per question, adaptive level and best stars per quiz) is kept ONLY in this phone's
   localStorage ('emmaQuiz'), under a profile label ('default' until Stage 5 adds child profiles). No names, no
   answer texts, no network. Pre-written Ari/Ezra lines only - no generated text. No timers, no lives, no streaks. */
(function (G) {
'use strict';
const BANDS = ['5-7', '8-10', '11-13'];
const LEVELS = ['starter', 'core', 'stretch'];
/* Built-in rules = exactly how the land quizzes behaved before Stage 3, so an older content release (no rules record)
   plays the same as always. Data overrides every value: ew.quizrules.default <- the bank's rules <- ruleOverrides. */
const BUILTIN = {
  enabled: true, selection: 'random',
  roundSize: { default: 8, byAgeBand: {} }, choices: { default: 3, byAgeBand: {} },
  shuffleOptions: true, noRepeatInRound: true, exhaustion: 'reshuffle',
  retry: { untilCorrect: true, disableWrong: true, hintAfterTries: 0, skipAfterTries: 0, hintButton: false },
  stars: { basis: 'mistakes', three: 1, two: 2, min: 1 },
  adaptive: { enabled: false, start: 'starter', upAfter: 3, downAfter: 2 },
  spaced: { intervalsDays: [0, 1, 3, 7, 14, 30] },
  voice: { readQuestionOnShow: true, readAnswersOnShow: {}, speakerReadsAnswers: false, pictureAnswers: false, tapReadsAnswer: {}, readAloudToggle: {} },
  feedback: { praise: 'app', confetti: true, sound: true },
  progress: { keepItems: 2000 }
};
const isObj = v => v && typeof v === 'object' && !Array.isArray(v);
const clone = o => JSON.parse(JSON.stringify(o));
function merge(a, b) { if (!isObj(b)) return a; for (const k in b) { if (k === 'key') continue; a[k] = isObj(a[k]) && isObj(b[k]) ? merge(a[k], b[k]) : clone(b[k]) } return a }
const lib = () => G.EWLib || null;
const rec = id => { try { const L = lib(); return (L && id) ? L.get(id) : null } catch (e) { return null } };

/* ---------- rules ---------- */
function rules(bank) {
  const B = typeof bank === 'string' ? rec(bank) : bank;
  const R = clone(BUILTIN);
  const def = rec('ew.quizrules.default');
  const own = B && B.payload && B.payload.rules ? rec(B.payload.rules) : null;
  /* the default record applies to banks with no rules of their own; a bank with a rules record uses that record
     on top of the built-in rules (so the "classic" records reproduce the old behaviour exactly) */
  if (own) merge(R, own.payload); else if (def && B) merge(R, def.payload);
  if (B && B.payload && B.payload.ruleOverrides) merge(R, B.payload.ruleOverrides);
  return R;
}
const pickBand = (o, band, dflt) => (o && o.byAgeBand && band && o.byAgeBand[band] != null) ? o.byAgeBand[band] : (o && o.default != null ? o.default : dflt);
const choicesFor = (R, band) => Math.max(2, Math.min(6, pickBand(R.choices, band, 3)));
const roundSize = (R, band, fallback) => pickBand(R.roundSize, band, fallback == null ? 8 : fallback);
function starsFor(miss, R) { const s = (R && R.stars) || BUILTIN.stars; miss = miss || 0;
  return miss <= s.three ? 3 : miss <= s.two ? 2 : Math.max(1, Math.min(3, s.min == null ? 1 : s.min)) }
/* a voice setting is one true/false for every age, or one per age band {"5-7": true, "8-10": false, ...} */
const bandVal = (v, band, dflt) => typeof v === 'boolean' ? v : (isObj(v) && band && v[band] != null) ? !!v[band] : dflt;
const readAnswersOnShow = (R, band) => bandVal(R.voice && R.voice.readAnswersOnShow, band, false);
/* what the voice does for this child (docs/quiz-engine.md "Voice"): all from the rules record, per age band.
   on = the child turned "Read to me" on (kept on this phone, per profile, until they turn it off) */
function voiceFor(R, band) { const V = (R && R.voice) || BUILTIN.voice, toggle = bandVal(V.readAloudToggle, band, false), on = toggle && progress.readAloud();
  return { band, toggle, on, question: bandVal(V.readQuestionOnShow, band, true) || on, answers: readAnswersOnShow({ voice: V }, band) || on,
    speakerAnswers: !!V.speakerReadsAnswers, tap: bandVal(V.tapReadsAnswer, band, false), pictures: !!V.pictureAnswers } }
/* the age band of the child playing: the Little / Big Explorers choice (Little = 5-7, Big = 8-10, deep = 11-13);
   a child who has not chosen yet plays as Little (everything read aloud) */
const AGE_BAND = { little: '5-7', big: '8-10', deep: '11-13' };
function childBand() { try { const a = JSON.parse((ls() && ls().getItem('emmaCtryPrefs')) || '{}').age; return AGE_BAND[a] || '5-7' } catch (e) { return '5-7' } }
/* the word a deck card says as an answer (generator.answerSay: 'name', 'word', 'say.0', 'say.1') */
function deckSay(it, path) { if (!it) return null; path = path || 'say.0';
  if (path === 'name' || path === 'word') return it[path] || null;
  const m = /^say\.(\d)$/.exec(path); const sy = it.say; return m && Array.isArray(sy) ? (sy[+m[1]] || null) : null }

/* ---------- randomness: Fisher-Yates; a seed makes it repeatable (tests) ---------- */
function rng(seed) { let a = (seed >>> 0) || 1; return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296 } }
function shuffle(arr, rnd) { rnd = rnd || Math.random; const a = arr.slice(); for (let i = a.length - 1; i > 0; i--) { const j = rnd() * (i + 1) | 0; [a[i], a[j]] = [a[j], a[i]] } return a }
const pickN = (arr, n, ex, rnd) => shuffle(arr.filter(x => !(ex || []).includes(x)), rnd).slice(0, n);

/* ---------- days (local calendar day numbers, for spaced review) ---------- */
const dayNum = d => { d = d || new Date(); return Math.floor((d.getTime() - d.getTimezoneOffset() * 60000) / 864e5) };

/* ---------- rounds ----------
   pool: [{id, difficulty?}]; strategy: random | fresh-today | leitner.
   fresh-today (the Cameroon rule): only questions not seen today, preferring ones not seen last time; null when fewer
   than n are left (the screen then offers Finish / Practise again). practice: any n questions, labelled as practice.
   leitner: due reviews first (lowest box first), then new questions, then the rest; with adaptive on, questions of the
   child's level come first inside each group. */
function buildRound(o) {
  const rnd = o.rnd || Math.random, pool = o.pool || [], n = Math.min(o.n || pool.length, pool.length);
  const strategy = o.strategy || 'random';
  if (o.practice) return shuffle(pool, rnd).slice(0, n).map(x => x.id);
  if (strategy === 'fresh-today') {
    const seen = new Set(o.seen || []), prev = new Set(o.prev || []);
    const fresh = pool.filter(it => !seen.has(it.id)); if (fresh.length < (o.n || pool.length)) return null;
    const a = shuffle(fresh.filter(it => !prev.has(it.id)), rnd), b = shuffle(fresh.filter(it => prev.has(it.id)), rnd);
    return [...a, ...b].slice(0, o.n).map(x => x.id) }
  if (strategy === 'leitner') {
    const items = (o.progress && o.progress.items) || {}, now = o.today == null ? dayNum() : o.today;
    const lv = o.level ? LEVELS.indexOf(o.level) : -1;
    const dist = it => (lv < 0 || !it.difficulty) ? 0 : Math.abs(LEVELS.indexOf(it.difficulty) - lv);
    const keyed = shuffle(pool, rnd).map((it, i) => { const p = items[it.id];
      const grp = !p ? 1 : (p.due != null && p.due <= now) ? 0 : 2;
      return { it, k: [grp === 0 ? 0 : 1, dist(it), grp, grp === 0 ? (p.box || 0) : grp === 2 ? (p.due || 0) : 0, i] } });
    keyed.sort((x, y) => { for (let i = 0; i < x.k.length; i++) if (x.k[i] !== y.k[i]) return x.k[i] - y.k[i]; return 0 });
    return keyed.slice(0, n).map(x => x.it.id) }
  return shuffle(pool, rnd).slice(0, n).map(x => x.id);
}

/* ---------- deck generators (Letter Hunt, Animal Quiz, Flag Quiz; Count It!) ---------- */
/* st keeps {used, last} between questions of one round: no repeat until every card was asked */
function deckQuestion(pool, st, R, band, rnd) {
  R = R || BUILTIN; const k = choicesFor(R, band) - 1;
  let t = pickN(pool, 1, R.noRepeatInRound === false ? [] : st.used, rnd)[0];
  if (!t) { st.used = []; t = pickN(pool, 1, [st.last], rnd)[0] }
  st.used = (st.used || []).concat([t]); st.last = t;
  const choices = R.shuffleOptions === false ? [t, ...pickN(pool, k, [t], rnd)] : shuffle([t, ...pickN(pool, k, [t], rnd)], rnd);
  return { target: t, choices };
}
const COUNT_GEN = { kind: 'count', min: 1, max: 10, near: [-2, -1, 1, 2, 3, -3], noRepeatPrevious: true };
function countOptions(N, gen, R, band, rnd) {
  gen = Object.assign({}, COUNT_GEN, gen || {}); const k = choicesFor(R || BUILTIN, band) - 1;
  const near = shuffle(gen.near.map(d => N + d).filter(x => x >= gen.min && x <= gen.max && x !== N), rnd);
  return shuffle([N, ...near.slice(0, k)], rnd);
}
function countQuestion(gen, st, R, band, rnd) {
  rnd = rnd || Math.random; gen = Object.assign({}, COUNT_GEN, gen || {}); let N, guard = 0;
  do { N = gen.min + (rnd() * (gen.max - gen.min + 1) | 0) } while (gen.noRepeatPrevious && N === st.prev && gen.max > gen.min && guard++ < 50);
  st.prev = N; return { n: N, options: countOptions(N, gen, R, band, rnd) };
}
const generator = bank => { const B = typeof bank === 'string' ? rec(bank) : bank; return (B && B.payload && B.payload.generator) || null };

/* ---------- progress: this phone only, per profile ---------- */
const PKEY = 'emmaQuiz';
const ls = () => { try { return G.localStorage || null } catch (e) { return null } };
function load() { try { const s = ls(); const o = JSON.parse((s && s.getItem(PKEY)) || '{}'); return isObj(o) && isObj(o.profiles) ? o : { v: 1, profiles: {} } } catch (e) { return { v: 1, profiles: {} } } }
function save(o) { try { const s = ls(); s && s.setItem(PKEY, JSON.stringify(o)) } catch (e) {} }
const profileId = () => { try { const s = ls(); return (s && s.getItem('emmaProfile')) || 'default' } catch (e) { return 'default' } };
function prof(o, pid) { pid = pid || profileId(); o.profiles[pid] = o.profiles[pid] || { items: {}, banks: {} }; return o.profiles[pid] }
const progress = {
  profile: profileId,
  get(pid) { return prof(load(), pid) },
  level(bankId, R) { const b = prof(load()).banks[bankId]; return (b && b.level) || ((R && R.adaptive && R.adaptive.start) || 'starter') },
  /* one answered question: first = right on the first try with no hint. Leitner: right first time -> next box,
     otherwise back to box 0 (due again today: it comes back in the next round). Adaptive: upAfter right-first-time in a row -> one level up,
     downAfter misses in a row -> one level down (never more than one step). */
  record(bankId, itemId, r, R) {
    R = R || BUILTIN; const o = load(), P = prof(o), iv = (R.spaced && R.spaced.intervalsDays) || BUILTIN.spaced.intervalsDays, today = r && r.today != null ? r.today : dayNum();
    const it = P.items[itemId] = P.items[itemId] || { box: 0, seen: 0, right: 0, miss: 0 };
    const first = !!(r && r.first && !r.hint && !r.skipped);
    it.seen++; it.last = today;
    if (first) { it.box = Math.min((it.box || 0) + 1, iv.length - 1); it.right++ } else { it.box = 0; it.miss++ }
    it.due = today + iv[Math.min(it.box, iv.length - 1)];
    const b = P.banks[bankId] = P.banks[bankId] || { level: (R.adaptive && R.adaptive.start) || 'starter', up: 0, down: 0, best: 0, plays: 0 };
    if (R.adaptive && R.adaptive.enabled) {
      if (first) { b.up++; b.down = 0; if (b.up >= (R.adaptive.upAfter || 3)) { b.level = LEVELS[Math.min(LEVELS.indexOf(b.level) + 1, LEVELS.length - 1)]; b.up = 0 } }
      else { b.down++; b.up = 0; if (b.down >= (R.adaptive.downAfter || 2)) { b.level = LEVELS[Math.max(LEVELS.indexOf(b.level) - 1, 0)]; b.down = 0 } } }
    const keep = (R.progress && R.progress.keepItems != null) ? R.progress.keepItems : 2000, ids = Object.keys(P.items);
    if (ids.length > keep) ids.sort((x, y) => (P.items[x].last || 0) - (P.items[y].last || 0)).slice(0, ids.length - keep).forEach(k => delete P.items[k]);
    save(o); return { box: it.box, due: it.due, level: b.level };
  },
  finish(bankId, s) { const o = load(), P = prof(o); const b = P.banks[bankId] = P.banks[bankId] || { level: 'starter', up: 0, down: 0, best: 0, plays: 0 };
    b.best = Math.max(b.best || 0, s || 0); b.plays = (b.plays || 0) + 1; save(o); return b },
  /* what a parent may see later (Parents' Corner, Stage 5): counts only */
  summary(pid) { const P = prof(load(), pid), t = dayNum(); const items = Object.values(P.items);
    return { profile: pid || profileId(), questions: items.length, dueToday: items.filter(i => i.due != null && i.due <= t).length,
      quizzes: Object.fromEntries(Object.entries(P.banks).map(([k, b]) => [k, { best: b.best || 0, plays: b.plays || 0, level: b.level }])) } },
  clear(pid) { const o = load(); if (pid) delete o.profiles[pid]; else o.profiles = {}; save(o) },
  /* "Read to me" switch for older children: get (no argument) or set (true/false); this profile only */
  readAloud(v) { const o = load(), P = prof(o); if (v === undefined) return !!(P.prefs && P.prefs.readAloud);
    P.prefs = P.prefs || {}; P.prefs.readAloud = !!v; save(o); return !!v }
};

/* the "Read to me" switch (shown only when the rules allow it for this age band). Works in every quiz player. */
const TQ0 = (k, v) => (G.EWi18n ? G.EWi18n.t(k, v) : ({ quizReadToMe: 'Read to me: {state}', quizOn: 'On', quizOff: 'Off' })[k] || k);
const readLabel = on => { const st = TQ0(on ? 'quizOn' : 'quizOff'), full = String(TQ0('quizReadToMe', { state: '\u0001' })); const [a, b] = full.includes('\u0001') ? full.split('\u0001') : [full + ' ', ''];
  return `${esc0(a)}<b>${esc0(st)}</b>${esc0(b)}` };
const esc0 = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
/* the age choice is on every quiz screen (Little 5-7 = read aloud; Big 8-13 = speaker / tap / Read to me), so a parent
   or child can see and change it anywhere - not only in the Cameroon player. Same store as Cameroon: emmaCtryPrefs.age */
const ageNow = () => { try { return JSON.parse((ls() && ls().getItem('emmaCtryPrefs')) || '{}').age || null } catch (e) { return null } };
const TA = (k, d) => { const t = G.EWi18n && G.EWi18n.has && G.EWi18n.has(k) ? G.EWi18n.t(k) : null; return t || d };
function toggleHtml(VM) { if (!VM) return ''; const big = VM.band && VM.band !== '5-7';
  const seg = `<div class="cseg qage" role="group" aria-label="${esc0(TA('quizWhoPlays', 'Who is playing?'))}"><button class="qagebtn${!big ? ' on' : ''}" data-age="little" aria-pressed="${!big}">🐣 ${esc0(TA('quizLittle', 'Little 5–7'))}</button><button class="qagebtn${big ? ' on' : ''}" data-age="big" aria-pressed="${big}">🦁 ${esc0(TA('quizBig8', 'Big 8–13'))}</button></div>`;
  const rd = VM.toggle ? `<button class="qread${VM.on ? ' on' : ''}" id="qread" role="switch" aria-checked="${VM.on}">🗣️ <span>${readLabel(VM.on)}</span></button>` : '';
  return `<div class="qreadrow">${seg}${rd}</div>` }
/* onOn: what to read straight away when the child turns it on (the current question and its answers) */
function bindToggle(root, VM, onOn) {
  root && root.querySelectorAll('.qagebtn').forEach(x => x.onclick = () => { if (x.classList.contains('on')) return;
    try { const s = ls(), o = JSON.parse((s && s.getItem('emmaCtryPrefs')) || '{}'); o.age = x.dataset.age; s.setItem('emmaCtryPrefs', JSON.stringify(o)) } catch (e) {}
    if (typeof sfx !== 'undefined' && sfx.tap) sfx.tap(); if (typeof stopVoice === 'function') stopVoice();
    const lg = G.__lastGo; if (lg && typeof go === 'function') { const scr = lg[0], a = Object.assign({}, lg[1] || {});
      if (scr === 'cquiz') go('cquiz', { c: a.c }); else if (scr === 'qplay') go('qplay', Object.assign(a, { fresh: 1, i: 0 })); else { delete a.r; go(scr, a) } } });
  const b = root && root.querySelector('#qread'); if (!b) return;
  b.onclick = () => { const on = progress.readAloud(!progress.readAloud()); VM.on = on; VM.question = VM.question || on; VM.answers = VM.answers || on;
    b.classList.toggle('on', on); b.setAttribute('aria-checked', String(on)); b.querySelector('span').innerHTML = readLabel(on);
    if (typeof sfx !== 'undefined' && sfx.tap) sfx.tap();
    if (on) { if (onOn) onOn() } else if (typeof stopVoice === 'function') stopVoice() } }
const API = { BUILTIN, LEVELS, BANDS, rules, stars: starsFor, choicesFor, roundSize, readAnswersOnShow, voiceFor, childBand, ageNow, deckSay, bandVal, toggleHtml, bindToggle, rng, shuffle, buildRound, deckQuestion,
  countQuestion, countOptions, generator, progress, dayNum, merge };
G.EWQuiz = API;
if (typeof module !== 'undefined' && module.exports) module.exports = API;

/* ======================= Part 2: the generic quiz player (in the app only) ======================= */
if (typeof document === 'undefined' || typeof XSCREENS === 'undefined') return;
const $q = s => document.querySelector(s);
const escq = t => String(t == null ? '' : t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const TQ = (k, v) => G.EWi18n ? G.EWi18n.t(k, v) : k;
const NQ = x => G.EWi18n ? G.EWi18n.n(x) : String(x);
/* a language map -> text in the child's language (fallback chain), remembered with its language for the voice */
const P = lt => { if (lt == null) return ''; if (typeof lt === 'string') return lt; if (G.EWi18n) return G.EWi18n.pick(lt); return lt.en != null ? lt.en : lt[Object.keys(lt)[0]] };
const lineOf = id => { const r = rec(id); return r ? { speaker: (rec(r.payload.speaker) || { payload: { key: 'ari' } }).payload.key, text: P(r.payload.text) } : null };
/* which age band plays this bank: a one-band bank is that band; otherwise the Little/Big choice made in the country
   player (Little = 5-7, Big = 8-10), else the bank's first band */
function bandFor(B) { const bs = (B.tags && B.tags.ageBands) || []; if (bs.length === 1) return bs[0];
  let age = null; try { age = JSON.parse(localStorage.getItem('emmaCtryPrefs') || '{}').age } catch (e) {}
  if (age === 'big') return bs.find(b => b !== '5-7') || bs[0] || '8-10'; return bs[0] || '5-7' }
/* a quiz-item record -> what the screen shows and says, in the child's language */
function view(r) { const p = r.payload, say = p.optionSay || {};
  const opt = (id, lt) => ({ id, text: P(lt), img: (p.optionMedia || {})[id] || null, say: say[id] ? P(say[id]) : null });
  const v = { id: r.id, type: p.responseType, prompt: P(p.prompt), key: p.answerKey, hint: P(p.hint), feedback: P(p.feedback), explanation: P(p.explanation),
    promptMedia: p.promptMedia || null, shuffle: p.shuffleOptions !== false, difficulty: r.tags && r.tags.difficulty, lines: p.lines || {},
    options: Object.entries(p.options || {}).map(([id, lt]) => opt(id, lt)), targets: Object.entries(p.targets || {}).map(([id, lt]) => ({ id, text: P(lt), say: null })), count: p.count || null };
  if (v.type === 'true-false') { const ui = rec('ew.ui.app'), s = ui ? ui.payload.strings : {};
    v.options = [{ id: 'true', text: P(s.quizTrue || 'True'), img: null, say: null, icon: '✓' }, { id: 'false', text: P(s.quizFalse || 'False'), img: null, say: null, icon: '✗' }] }
  return v }
const spoken = (o, R) => o.say || (o.img && !(R.voice && R.voice.pictureAnswers) ? null : o.img ? o.say : o.text);
const numWord = n => { const N = (typeof LANDS !== 'undefined' && LANDS && LANDS.decks && LANDS.decks.numbers && LANDS.decks.numbers.items) || []; const w = N.find(x => +x.n === +n); return (w && w.say && w.say[0]) || null };
function answerLines(v, R) { if (v.type === 'count') return (v._nums || []).map(numWord).filter(Boolean); return [...v.options.map(o => spoken(o, R)), ...v.targets.map(t => t.text)].filter(Boolean) }
/* every line a bank can speak (tools/check_voice.py; mirrors tools/content/legacy.py quiz_spoken) */
function bankLines(B) { const out = [], R = rules(B), p = B.payload; out.push(P(p.title), P(p.intro));
  Object.values(p.lines || {}).forEach(ids => ids.forEach(id => { const l = lineOf(id); if (l) out.push(l.text) }));
  (p.items || []).map(rec).filter(Boolean).forEach(r => { const v = view(r); out.push(v.prompt, v.hint, v.feedback, v.explanation, ...answerLines(v, Object.assign({}, R, { voice: Object.assign({}, R.voice, { pictureAnswers: false }) })));
    Object.values(v.lines).forEach(ids => ids.forEach(id => { const l = lineOf(id); if (l) out.push(l.text) })) });
  return out.filter(Boolean) }
G.__quizVoice = () => { const L = lib(); if (!L) return []; const cb = new Set(L.find({ type: 'country' }).map(c => c.payload.quiz && c.payload.quiz.bank));
  return [...new Set(L.find({ type: 'quiz-bank' }).filter(b => b.payload.items && !cb.has(b.id)).flatMap(bankLines))] };

let QS = null;   /* the round being played: {a, B, R, band, ids, i, miss, score, level} */
function pickLine(ids) { const ls2 = (ids || []).map(lineOf).filter(Boolean); return ls2.length ? ls2[Math.random() * ls2.length | 0] : null }
function praiseLine(kind, v) { const R = QS.R, own = (v && v.lines && v.lines[kind]) || (QS.B.payload.lines || {})[kind];
  if (R.feedback.praise === 'lines' && own && own.length) return pickLine(own);
  if (kind === 'correct' && typeof wPraise === 'function') return { speaker: 'ari', text: wPraise() };
  if (kind === 'tryAgain' && G.worldTry) { const t = G.worldTry(); if (t) return { speaker: 'ari', text: t } }
  return own && own.length ? pickLine(own) : null }
function guide(ls2) { const box = $q('#qguide'); if (!box) return; box.innerHTML = ''; ls2 = ls2.filter(Boolean); box.classList.toggle('hide', !ls2.length);
  ls2.forEach(l => { const d = document.createElement('button'); d.className = 'cbub ' + (l.speaker === 'ezra' ? 'ezra' : 'ari');
    d.innerHTML = `<img src="img/world/guides/${l.speaker === 'ezra' ? 'ezra-face' : 'ari-hello'}.webp" alt=""><span><b>${l.speaker === 'ezra' ? 'Ezra' : 'Ari'}</b> ${escq(l.text)}</span>`;
    d.setAttribute('aria-label', (l.speaker === 'ezra' ? 'Ezra: ' : 'Ari: ') + l.text); d.onclick = e => { e.stopPropagation(); stopVoice(); box.classList.add('hide') }; box.appendChild(d) }) }
const sayQ = parts => say(parts.filter(Boolean), 0, 1);

function startRound(a) {
  const B = rec(a.b); if (!B || !B.payload.items) return null;
  const R = rules(B), band = bandFor(B), pr = progress.get();
  let pool = B.payload.items.map(rec).filter(r => r && r.status !== 'withdrawn' && r.type === 'quiz-item');
  const inBand = pool.filter(r => !(r.tags.ageBands || []).length || r.tags.ageBands.includes(band)); if (inBand.length) pool = inBand;
  const level = R.adaptive.enabled ? progress.level(B.id, R) : null;
  const n = roundSize(R, band, pool.length);
  let ids = buildRound({ pool: pool.map(r => ({ id: r.id, difficulty: r.tags.difficulty })), n, strategy: R.selection, progress: pr, level, seen: [], prev: [] });
  if (!ids) ids = buildRound({ pool: pool.map(r => ({ id: r.id })), n, practice: true });
  return { a: { l: a.l, p: a.p, b: a.b }, B, R, band, ids, i: 0, miss: 0, score: 0, level };
}
function qplay(a) {
  if (!a || !a.b) { go('home'); return }
  if (!QS || a.fresh || QS.a.b !== a.b || a.i == null) { QS = startRound(a); if (!QS) { go('land', { id: a.l || curLand }); return }
    cacheClips(bankLines(QS.B)) }
  const i = a.i == null ? 0 : a.i; QS.i = i; curLand = QS.a.l; state = { land: QS.a.l, place: QS.a.p, quiz: QS.B.id };
  const r = rec(QS.ids[i]); if (!r) { qnext(); return }
  const v = view(r), R = QS.R, band = QS.band, VM = voiceFor(R, childBand());   /* the voice follows the child's age choice, not the quiz's */ let tries = 0, hinted = false, done = false, tw = null;
  $q('#title').textContent = P(QS.B.payload.title) || QS.B.id;
  const ord = list => v.shuffle && R.shuffleOptions !== false ? shuffle(list) : list.slice();
  const opts = ord(v.options), tgts = ord(v.targets);
  let body = '';
  if (v.type === 'single-choice' || v.type === 'true-false')
    body = `<div class="copts${v.type === 'true-false' ? ' qtf' : ''}">${(v.type === 'true-false' ? v.options : opts).map(o => `<button class="copt" data-o="${escq(o.id)}">${o.icon ? `<i aria-hidden="true">${o.icon}</i> ` : ''}${escq(o.text)}</button>`).join('')}</div>`;
  else if (v.type === 'picture-pick')
    body = `<div class="choices wpics qpics">${opts.map(o => `<button class="wpic copt-pic" data-o="${escq(o.id)}" aria-label="${escq(o.say || o.text)}"><img src="${escq(o.img)}" alt=""></button>`).join('')}</div>`;
  else if (v.type === 'count') {
    const C = v.count, nums = C.numbers ? ord(C.numbers) : countOptions(C.n, { min: 1, max: Math.max(10, C.n + 3) }, R, band); v._nums = nums;
    body = `<div class="wcount" id="qc">${Array.from({ length: C.n }, (_, k) => `<button class="wobj" style="animation-delay:${(k * .06).toFixed(2)}s" aria-label="${escq(TQ('count'))}"><img src="${escq(C.img)}" alt=""></button>`).join('')}</div><div class="hint">${escq(TQ('tapToCount'))}</div><div class="choices wnums">${nums.map(n => `<button class="opt wn copt-n" data-o="${n}">${NQ(n)}</button>`).join('')}</div>` }
  else if (v.type === 'order')
    body = `<p class="csmall qhelp">${escq(TQ('quizOrderHelp'))}</p><div class="qslots" id="qslots">${v.options.map((_, k) => `<span class="qslot" data-k="${k}">${NQ(k + 1)}</span>`).join('')}</div><div class="copts qorder">${opts.map(o => `<button class="copt" data-o="${escq(o.id)}">${escq(o.text)}</button>`).join('')}</div><div class="cnav"><button class="cbtn2" id="qundo">↶ ${escq(TQ('quizUndo'))}</button></div>`;
  else if (v.type === 'match')
    body = `<p class="csmall qhelp">${escq(TQ('quizMatchHelp'))}</p><div class="qmatch"><div class="copts">${opts.map(o => `<button class="copt qleft" data-o="${escq(o.id)}">${escq(o.text)}</button>`).join('')}</div><div class="copts">${tgts.map(t => `<button class="copt qright" data-t="${escq(t.id)}">${escq(t.text)}</button>`).join('')}</div></div>`;
  main.innerHTML = `<div class="cscr qscr" data-type="${v.type}"><div class="cprog">${escq(TQ('quizQuestion', { n: i + 1, total: QS.ids.length }))}</div>
   <p class="ctext sm" id="qprompt"><span>${escq(v.prompt)}</span><button class="say" id="qsay" aria-label="${escq(TQ('readAloud'))}">🔊</button></p>${toggleHtml(VM)}
   ${v.promptMedia ? `<img class="qmedia" src="${escq(v.promptMedia)}" alt="">` : ''}${body}
   ${R.retry.hintButton && v.hint ? `<div class="cnav"><button class="cbtn2" id="qhint">? ${escq(TQ('quizHint'))}</button></div>` : ''}
   <p class="cfb hint hide" id="qhintline"></p><div id="qafter"></div><div class="cguide hide" id="qguide" aria-live="polite"></div></div>`;
  const ans = answerLines(v, R);
  const showHint = () => { hinted = true; const h = $q('#qhintline'); if (!v.hint || !h) return; h.textContent = v.hint; h.classList.remove('hide'); const l = praiseLine('hint', v); guide([l]); sayQ([l && l.text, v.hint]) };
  const showSkip = () => { if ($q('#qskip') || done) return; const d = $q('#qafter'); d.innerHTML = `<div class="cnav"><button class="cbtn2" id="qskip">${escq(TQ('quizSkip'))} ▶</button></div>`;
    $q('#qskip').onclick = () => { sfx.tap(); progress.record(QS.B.id, v.id, { skipped: true }, R); qnext() } };
  const miss = (el) => { tries++; QS.miss++; sfx.wrong(); if (el) { el.classList.add('no'); if (R.retry.disableWrong) el.disabled = true }
    const l = praiseLine('tryAgain', v); guide([l]); const w = tw; tw = null;
    if (R.retry.hintAfterTries > 0 && tries >= R.retry.hintAfterTries && v.hint) { const h = $q('#qhintline'); h.textContent = v.hint; h.classList.remove('hide'); hinted = true; sayQ([w, l && l.text, v.hint]) } else sayQ([w, l && l.text]);
    if (R.retry.skipAfterTries > 0 && tries >= R.retry.skipAfterTries) showSkip();
    if (R.retry.untilCorrect === false) { lockQ(); setTimeout(qnext, 1600) } };
  const lockQ = () => main.querySelectorAll('.qscr .copt,.qscr .wpic,.qscr .wn,.qscr .wobj,#qundo,#qhint').forEach(b => b.disabled = true);
  const good = (el) => { if (done) return; done = true; sfx.right(); stars++; setScore(); QS.score++; if (el) { el.classList.add('ok'); const rr = el.getBoundingClientRect(); burst(rr.left + rr.width / 2, rr.top + rr.height / 2) }
    lockQ(); if (R.feedback.confetti) confetti(60);
    const first = tries === 0 && !hinted; const res = progress.record(QS.B.id, v.id, { first, hint: hinted }, R); QS.level = res.level;
    $q('#qhintline').classList.add('hide'); const l = praiseLine('correct', v);
    $q('#qafter').innerHTML = `${v.feedback ? `<p class="cfb ok">✓ ${escq(v.feedback)}</p>` : ''}${v.explanation ? `<p class="cfb">${escq(v.explanation)}</p>` : ''}<div class="cnav"><button class="btn" id="qnext">${escq(TQ(i + 1 < QS.ids.length ? 'next' : 'done'))} ▶</button></div>`;
    $q('#qnext').onclick = () => { sfx.tap(); qnext() }; guide([l]); const w = tw; tw = null; sayQ([w, l && l.text, v.feedback, v.explanation]) };
  /* ages 8-13 (rules: tapReadsAnswer): tapping an answer also says that answer's word */
  const tapSay = o => { tw = VM.tap && o ? (o.say || (o.img && !o.say ? null : o.text)) : null };
  /* answers */
  if (['single-choice', 'true-false', 'picture-pick'].includes(v.type))
    main.querySelectorAll('.qscr [data-o]').forEach(b => b.onclick = () => { if (b.disabled || done) return; tapSay(v.options.find(o => o.id === b.dataset.o)); if (b.dataset.o === String(v.key)) good(b); else miss(b) });
  if (v.type === 'count') { let c = 0; const NUM = (typeof LANDS !== 'undefined' && LANDS && LANDS.decks && LANDS.decks.numbers && LANDS.decks.numbers.items) || [];
    main.querySelectorAll('.wobj').forEach(b => b.onclick = () => { if (b.classList.contains('counted') || b.disabled) return; c++; b.classList.add('counted'); b.dataset.c = NQ(c); sfx.pop(); const w = NUM[c - 1]; if (w && w.say) say(w.say[0], 0, 1) });
    main.querySelectorAll('.wn').forEach(b => b.onclick = () => { if (b.disabled || done) return; tw = VM.tap ? numWord(b.dataset.o) : null; if (String(b.dataset.o) === String(v.key)) good(b); else miss(b) }) }
  if (v.type === 'order') { let placed = [];
    const draw = () => { main.querySelectorAll('.qslot').forEach((s, k) => { const o = v.options.find(x => x.id === placed[k]); s.textContent = o ? o.text : NQ(k + 1); s.classList.toggle('full', !!o) });
      main.querySelectorAll('.qorder .copt').forEach(b => { b.disabled = done || placed.includes(b.dataset.o); b.classList.toggle('used', placed.includes(b.dataset.o)) }) };
    main.querySelectorAll('.qorder .copt').forEach(b => b.onclick = () => { if (b.disabled || done) return; sfx.tap(); placed.push(b.dataset.o); const o = v.options.find(x => x.id === b.dataset.o); if (o) say(o.say || o.text, 0, 1); draw();
      if (placed.length === v.key.length) { if (placed.every((x, k) => x === v.key[k])) good($q('#qslots')); else { let k = 0; while (placed[k] === v.key[k]) k++; placed = placed.slice(0, k); miss(null); draw() } } });
    $q('#qundo').onclick = () => { if (done || !placed.length) return; sfx.tap(); placed.pop(); draw() } }
  if (v.type === 'match') { let sel = null; const matched = new Set();
    main.querySelectorAll('.qleft').forEach(b => b.onclick = () => { if (b.disabled || done) return; sfx.tap(); sel = b.dataset.o; main.querySelectorAll('.qleft').forEach(x => x.classList.toggle('sel', x === b)); const o = v.options.find(x => x.id === sel); if (o) say(o.say || o.text, 0, 1) });
    main.querySelectorAll('.qright').forEach(b => b.onclick = () => { if (b.disabled || done) return;
      if (!sel) { const t = v.targets.find(x => x.id === b.dataset.t); if (t) say(t.text, 0, 1); return }
      const L = main.querySelector(`.qleft[data-o="${CSS.escape(sel)}"]`);
      if (v.key[sel] === b.dataset.t) { sfx.pop(); matched.add(sel); [L, b].forEach(x => { x.classList.add('ok'); x.classList.remove('sel'); x.disabled = true }); sel = null; if (matched.size === v.options.length) good(null) }
      else { miss(null); L.classList.remove('sel'); sel = null } }) }
  $q('#qsay').onclick = () => { stopVoice(); sayQ([v.prompt, ...(VM.speakerAnswers ? ans : [])]) };
  bindToggle(main, VM, () => { stopVoice(); sayQ([v.prompt, ...ans]) });
  if ($q('#qhint')) $q('#qhint').onclick = () => { sfx.tap(); showHint(); if (R.retry.skipAfterTries > 0) showSkip() };
  const first = i === 0 && !a.keep, intro = first ? (P(QS.B.payload.intro) || (pickLine((QS.B.payload.lines || {}).start) || {}).text) : null;
  /* the voice rule is data (rules.voice, per age band): ages 5-7 hear the question and every answer; ages 8-13 hear
     nothing until they tap the speaker, tap an answer, or turn "Read to me" on */
  if (VM.question) sayQ([intro, v.prompt, ...(VM.answers ? ans : [])]);
  const nx = QS.ids[i + 1] && rec(QS.ids[i + 1]); if (nx) { const w = view(nx); warmVoice([w.prompt, ...answerLines(w, R)], 1) }
}
function qnext() { if (!QS) { go('home'); return } if (QS.i + 1 < QS.ids.length) go('qplay', Object.assign({}, QS.a, { i: QS.i + 1 })); else go('qdone', QS.a) }
function qdone(a) {
  if (!QS) { go('land', { id: (a && a.l) || curLand }); return }
  const s = starsFor(QS.miss, QS.R), n = QS.score, tot = QS.ids.length, name = String(P(QS.B.payload.title) || '').replace(/[\s\u00a0\u202f]*[!?.\uff01]+$/, '');  /* "Quiz Time!" -> no "Quiz Time!!" in "You finished {name}!" */
  progress.finish(QS.B.id, s);
  if (QS.a.p && typeof wSave === 'function') { const sv = wSave(); sv.best = sv.best || {}; sv.best[QS.a.p] = Math.max(s, sv.best[QS.a.p] || 0); wPut(sv) }
  curLand = QS.a.l; $q('#title').textContent = TQ('greatJob'); sfx.win();
  const l = pickLine((QS.B.payload.lines || {}).done);
  main.innerHTML = `<div class="reward qdone"><h1>${escq(TQ('greatJob'))}</h1><div class="bigstars">${[0, 1, 2].map(k => `<span style="${k < s ? '' : 'filter:grayscale(1);opacity:.35'}">⭐</span>`).join('')}</div><div class="prompt">${escq(TQ('finished', { name, n, total: tot }))}<br>${escq(TQ('totalStars', { stars: (typeof stars === 'number' ? stars : 0) }))}</div><div class="cguide hide" id="qguide" aria-live="polite"></div><div style="display:flex;gap:14px;justify-content:center;flex-wrap:wrap"><button class="btn" id="qagain">${escq(TQ('playAgain'))}</button><button class="btn" id="qtomap">${escq(TQ('backToMap'))}</button></div></div>`;
  guide([l]); sayQ([l ? l.text : TQ('levelComplete')]); if (QS.R.feedback.confetti) { confetti(200); for (let k = 0; k < 4; k++) setTimeout(() => burst(innerWidth * (.2 + .2 * k), innerHeight * .35), k * 250) }
  $q('#qagain').onclick = () => { sfx.tap(); go('qplay', Object.assign({}, QS.a, { fresh: 1 })) };
  $q('#qtomap').onclick = () => { sfx.tap(); go('land', { id: QS.a.l }) }
}
Object.assign(XSCREENS, { qplay, qdone });
Object.assign(XBACK, { qplay: () => go('land', { id: (QS && QS.a.l) || curLand }), qdone: () => go('land', { id: (QS && QS.a.l) || curLand }) });
if (typeof WORLD_SCREENS !== 'undefined') WORLD_SCREENS.push('qplay', 'qdone');
/* language switched: redraw the same question in the new language */
addEventListener('ewlang', () => { if (!QS) return; if (screen === 'qplay') go('qplay', Object.assign({}, QS.a, { i: QS.i, keep: 1 })); else if (screen === 'qdone') go('qdone', QS.a) });
API.view = view; API.bankLines = bankLines; API._state = () => QS;
})(typeof window !== 'undefined' ? window : globalThis);
