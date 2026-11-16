#!/usr/bin/env node
/* Unit tests for the pure quiz engine logic in quiz.js (Stage 3). No browser, no network.
   Run: node tools/test_quiz_engine.js  (part of tools/run_tests.py) */
'use strict';
const path = require('path'), fs = require('fs');
const ROOT = path.join(__dirname, '..');
/* fake phone storage + the real rules records from the content source */
const store = {};
globalThis.localStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v) }, removeItem: k => { delete store[k] } };
const RECS = {};
for (const f of ['content/src/core/quiz.json', 'content/src/countries/cameroon/quiz.json']) {
  const p = path.join(ROOT, f); if (!fs.existsSync(p)) continue;
  const d = JSON.parse(fs.readFileSync(p, 'utf8')); for (const r of (d.records || d)) if (r && r.id) RECS[r.id] = r }
globalThis.EWLib = { get: id => RECS[id] || null };
const Q = require(path.join(ROOT, 'quiz.js'));
let fails = 0, n = 0;
const ok = (c, m) => { n++; if (c) console.log('OK  ', m); else { fails++; console.log('FAIL', m) } };
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/* ---- rules: precedence ---- */
const B = Q.BUILTIN;
ok(eq(Q.rules(null), B), 'no bank -> built-in rules (old behaviour)');
const def = RECS['ew.quizrules.default'];
ok(def && def.status === 'published', 'ew.quizrules.default exists and is published');
const rNone = Q.rules({ id: 'x', payload: {} });
ok(rNone.selection === def.payload.selection && rNone.retry.hintAfterTries === def.payload.retry.hintAfterTries, 'bank with no rules -> ew.quizrules.default on top of built-in');
const lc = Q.rules({ id: 'x', payload: { rules: 'ew.quizrules.land-classic' } });
ok(lc.selection === 'random' && Q.roundSize(lc, '5-7') === 8 && Q.choicesFor(lc, '11-13') === 3, 'land-classic = the old land quiz behaviour (random, 8 questions, 3 choices)');
ok(!lc.adaptive.enabled && lc.retry.hintAfterTries === 0, 'land-classic does not inherit hints/adaptive from the default record');
const ov = Q.rules({ id: 'x', payload: { rules: 'ew.quizrules.land-classic', ruleOverrides: { choices: { default: 4 }, stars: { three: 0 } } } });
ok(Q.choicesFor(ov, '5-7') === 4 && ov.stars.three === 0 && ov.stars.two === lc.stars.two, 'ruleOverrides win and merge deeply');
ok(Q.rules('ew.quizbank.count-it').selection === 'random', 'rules(bankId) looks the bank up in the library');
const cbank = Object.values(RECS).find(r => r.type === 'quiz-bank' && r.payload.rules === 'ew.quizrules.country-classic');
{ const R = Q.rules(cbank || {}); ok(!!cbank && R.selection === 'fresh-today' && R.exhaustion === 'finish-or-practice' && R.retry.hintButton === true, 'Cameroon bank -> country-classic rules (fresh-today, finish-or-practice, hint button)') }
ok(Q.choicesFor({ choices: { default: 9 } }) === 6 && Q.choicesFor({ choices: { default: 1 } }) === 2, 'choices are clamped to 2..6');
const dR = Q.rules({ id: 'x', payload: {} });
ok(Q.roundSize(dR, '5-7') === 4 && Q.roundSize(dR, '11-13') === 6 && Q.roundSize(dR, 'nope') === 5, 'round size per age band, default for unknown band');
ok(Q.readAnswersOnShow(dR, '5-7') && !Q.readAnswersOnShow(dR, '8-10'), 'answers read on show for ages 5-7 only (default rules)');

/* ---- voice rule (Emmanuel, 2026-11-16): Little hears everything, Big hears nothing automatically ---- */
Q.progress.clear();
for (const id of ['ew.quizrules.default', 'ew.quizrules.land-classic', 'ew.quizrules.country-classic']) {
  const R = Q.rules({ id: 'x', payload: { rules: id } });
  const L = Q.voiceFor(R, '5-7'), B8 = Q.voiceFor(R, '8-10'), B11 = Q.voiceFor(R, '11-13');
  ok(L.question && L.answers && L.pictures && !L.toggle, `${id}: ages 5-7 hear the question and every answer (pictures too), no switch needed`);
  ok(!B8.question && !B8.answers && !B11.question && !B11.answers, `${id}: ages 8-10 and 11-13 hear nothing automatically`);
  ok(B8.toggle && B8.tap && B8.speakerAnswers && B11.toggle && B11.tap, `${id}: ages 8-13 get the Read to me switch, tap-an-answer and the speaker reads every answer`);
}
const Rd = Q.rules({ id: 'x', payload: {} });
ok(Q.progress.readAloud() === false, 'Read to me starts off');
Q.progress.readAloud(true);
const on8 = Q.voiceFor(Rd, '8-10');
ok(on8.on && on8.question && on8.answers, 'Read to me on -> an older child hears question + answers on show');
ok(Q.voiceFor(Rd, '8-10').on, 'Read to me stays on for the next question (remembered)');
ok(JSON.parse(store.emmaQuiz).profiles.default.prefs.readAloud === true, 'the switch is kept on this phone under the profile');
store.emmaProfile = 'kid2'; ok(!Q.voiceFor(Rd, '8-10').on, 'another profile has its own switch (off)'); delete store.emmaProfile;
Q.progress.readAloud(false); ok(!Q.voiceFor(Rd, '8-10').question, 'turned off -> no automatic reading again');
ok(Q.voiceFor(Q.rules(null), '8-10').question === true && !Q.voiceFor(Q.rules(null), '8-10').toggle, 'no rules record (older content) -> the old behaviour (question read, no switch)');
ok(Q.bandVal(true, '8-10', false) === true && Q.bandVal({ '8-10': false }, '8-10', true) === false && Q.bandVal({}, '8-10', true) === true, 'voice values: one for all ages, or per band, with a fallback');
globalThis.localStorage.setItem('emmaCtryPrefs', JSON.stringify({ age: 'big' })); ok(Q.childBand() === '8-10', 'Big Explorers -> 8-10');
globalThis.localStorage.setItem('emmaCtryPrefs', JSON.stringify({ age: 'little' })); ok(Q.childBand() === '5-7', 'Little Explorers -> 5-7');
globalThis.localStorage.removeItem('emmaCtryPrefs'); ok(Q.childBand() === '5-7', 'not chosen yet -> 5-7 (everything read aloud)');
ok(Q.deckSay({ name: 'Ghana', say: ['This is Ghana!'] }, 'name') === 'Ghana' && Q.deckSay({ say: ['Lion!', 'x'] }, 'say.0') === 'Lion!' && Q.deckSay({ say: [] }, 'say.1') === null, 'deck answer words come from generator.answerSay');
for (const [b, w] of [['ew.quizbank.letter-hunt', 'say.0'], ['ew.quizbank.animal-quiz', 'say.0'], ['ew.quizbank.flag-quiz', 'name'], ['ew.quizbank.count-it', 'say.0']])
  ok((RECS[b].payload.generator || {}).answerSay === w, `${b}: answers are spoken with ${w}`);
Q.progress.clear();

/* ---- stars ---- */
ok(Q.stars(0) === 3 && Q.stars(1) === 3 && Q.stars(2) === 2 && Q.stars(3) === 1 && Q.stars(40) === 1, 'stars: 0-1 misses 3, 2 misses 2, more 1 (never 0)');
ok(Q.stars(1, { stars: { three: 0, two: 1, min: 1 } }) === 2, 'stars thresholds come from the rules');

/* ---- shuffle / rng ---- */
const a = Q.shuffle([1, 2, 3, 4, 5, 6, 7, 8], Q.rng(7)), b = Q.shuffle([1, 2, 3, 4, 5, 6, 7, 8], Q.rng(7));
ok(eq(a, b) && eq([...a].sort(), [1, 2, 3, 4, 5, 6, 7, 8]), 'seeded shuffle is repeatable and keeps every item');
const counts = {}; const r = Q.rng(3); for (let i = 0; i < 6000; i++) { const s = Q.shuffle([1, 2, 3], r).join(''); counts[s] = (counts[s] || 0) + 1 }
ok(Object.keys(counts).length === 6 && Object.values(counts).every(c => c > 800 && c < 1200), 'shuffle is unbiased (all 6 orders ~1000 of 6000) ' + JSON.stringify(counts));

/* ---- rounds ---- */
const pool = 'abcdefghij'.split('').map((id, i) => ({ id, difficulty: Q.LEVELS[i % 3] }));
const rr = Q.buildRound({ pool, n: 5, strategy: 'random', rnd: Q.rng(1) });
ok(rr.length === 5 && new Set(rr).size === 5, 'random: n different questions');
ok(Q.buildRound({ pool, n: 50, strategy: 'random' }).length === 10, 'random: never more than the pool');
const ft = Q.buildRound({ pool, n: 4, strategy: 'fresh-today', seen: ['a', 'b'], prev: ['c', 'd', 'e', 'f', 'g', 'h'], rnd: Q.rng(2) });
ok(ft && ft.length === 4 && !ft.includes('a') && !ft.includes('b'), 'fresh-today: nothing seen today');
ok(ft && ft.slice(0, 2).every(x => x === 'i' || x === 'j'), 'fresh-today: questions not in the last round come first');
ok(Q.buildRound({ pool, n: 4, strategy: 'fresh-today', seen: 'abcdefg'.split('') }) === null, 'fresh-today: null when fewer than n are left (Finish / Practise screen)');
const pr = Q.buildRound({ pool, n: 4, strategy: 'fresh-today', seen: 'abcdefghij'.split(''), practice: true });
ok(pr && pr.length === 4, 'practice mode: a round even when everything was seen today');
const today = 20000;
const prog = { items: { a: { box: 3, due: today - 1 }, b: { box: 1, due: today }, c: { box: 2, due: today + 5 }, d: { box: 1, due: today + 1 } } };
const lr = Q.buildRound({ pool, n: 10, strategy: 'leitner', progress: prog, today, rnd: Q.rng(4) });
ok(eq(lr.slice(0, 2), ['b', 'a']), 'leitner: due reviews first, lowest box first ' + lr.join(''));
ok(lr.slice(2, 8).every(x => !'abcd'.includes(x)), 'leitner: then new questions');
ok(eq(lr.slice(8), ['d', 'c']), 'leitner: then not-due ones, soonest due first');
const ad = Q.buildRound({ pool, n: 3, strategy: 'leitner', progress: { items: {} }, today, level: 'stretch', rnd: Q.rng(5) });
ok(ad.every(id => pool.find(p => p.id === id).difficulty === 'stretch'), 'adaptive: a stretch child gets stretch questions first ' + ad);
const ad2 = Q.buildRound({ pool, n: 5, strategy: 'leitner', progress: { items: {} }, today, level: 'starter', rnd: Q.rng(5) });
ok(ad2.slice(0, 4).every(id => pool.find(p => p.id === id).difficulty === 'starter') && pool.find(p => p.id === ad2[4]).difficulty === 'core', 'adaptive: starter first, then the next level (one step) ' + ad2);

/* ---- deck generator ---- */
const deck = 'ABCDE'.split(''), st = {}; const asked = [];
for (let i = 0; i < 5; i++) { const q = Q.deckQuestion(deck, st, B, '5-7', Q.rng(10 + i)); asked.push(q.target);
  if (i === 0) ok(q.choices.length === 3 && q.choices.includes(q.target) && new Set(q.choices).size === 3, 'deck: 3 different choices including the answer') }
ok(new Set(asked).size === 5, 'deck: no repeat until every card was asked ' + asked.join(''));
const q6 = Q.deckQuestion(deck, st, B, '5-7', Q.rng(99));
ok(q6.target !== asked[4], 'deck: after the deck is used up, never the same card twice in a row');
ok(Q.deckQuestion(deck, {}, { choices: { default: 4 } }, '5-7').choices.length === 4, 'deck: choices count from the rules');

/* ---- count generator ---- */
const gen = { kind: 'count', min: 1, max: 10, near: [-2, -1, 1, 2, 3, -3], noRepeatPrevious: true };
let prev = null, inRange = true, distinct = true, hasN = true, rep = false; const cst = {}; const rc = Q.rng(11);
for (let i = 0; i < 300; i++) { const q = Q.countQuestion(gen, cst, B, '5-7', rc);
  if (q.n < 1 || q.n > 10) inRange = false; if (q.n === prev) rep = true; prev = q.n;
  if (!q.options.includes(q.n)) hasN = false; if (new Set(q.options).size !== q.options.length || q.options.some(o => o < 1 || o > 10)) distinct = false }
ok(inRange && !rep, 'count: numbers in min..max, never the same number twice in a row');
ok(hasN && distinct, 'count: options include the answer, are different and in range');
ok(Q.countOptions(1, gen, B, '5-7', Q.rng(1)).length === 3 && Q.countOptions(10, gen, B, '5-7', Q.rng(1)).every(o => o <= 10), 'count: edge numbers 1 and 10 still get 3 valid options');

/* ---- progress (this phone only, per profile) ---- */
Q.progress.clear();
const R = Q.rules({ id: 'x', payload: {} });
let p1 = Q.progress.record('bk', 'q1', { first: true, today }, R);
ok(p1.box === 1 && p1.due === today + 1, 'progress: right first time -> box 1, back tomorrow');
p1 = Q.progress.record('bk', 'q1', { first: true, today: today + 1 }, R);
ok(p1.box === 2 && p1.due === today + 4, 'progress: right again -> box 2, back in 3 days');
p1 = Q.progress.record('bk', 'q1', { first: false, today: today + 4 }, R);
ok(p1.box === 0 && p1.due === today + 4, 'progress: a miss -> box 0, comes back today');
ok(Q.progress.record('bk', 'q2', { first: true, hint: true, today }, R).box === 0, 'progress: right only after a hint does not move the box up');
Q.progress.clear();
for (let i = 0; i < 3; i++) Q.progress.record('bk', 'u' + i, { first: true, today }, R);
ok(Q.progress.level('bk', R) === 'core', 'adaptive: 3 right first time in a row -> one level up');
for (let i = 0; i < 3; i++) Q.progress.record('bk', 'v' + i, { first: true, today }, R);
ok(Q.progress.level('bk', R) === 'stretch', 'adaptive: up again to stretch');
Q.progress.record('bk', 'w1', { first: false, today }, R); ok(Q.progress.level('bk', R) === 'stretch', 'adaptive: one miss does not drop the level');
Q.progress.record('bk', 'w2', { first: false, today }, R); ok(Q.progress.level('bk', R) === 'core', 'adaptive: 2 misses in a row -> one level down');
const noAd = Q.rules({ id: 'x', payload: { rules: 'ew.quizrules.land-classic' } }); Q.progress.clear();
for (let i = 0; i < 5; i++) Q.progress.record('lc', 'x' + i, { first: true, today }, noAd);
ok(Q.progress.level('lc', noAd) === 'starter', 'adaptive off -> level never changes');
Q.progress.finish('bk', 2); Q.progress.finish('bk', 1);
const sm = Q.progress.summary();
ok(sm.quizzes.bk.best === 2 && sm.quizzes.bk.plays === 2, 'finish keeps the best stars and play count');
const raw = store.emmaQuiz;
const allowed = new Set(['readAloud', 'box', 'seen', 'right', 'miss', 'last', 'due', 'level', 'up', 'down', 'best', 'plays']);
const P0 = JSON.parse(raw).profiles.default;
ok(Object.values(P0.items).concat(Object.values(P0.banks)).every(o => Object.entries(o).every(([k, v]) => allowed.has(k) && (typeof v === 'number' || Q.LEVELS.includes(v)))), 'storage holds only counts, days and levels (no names, no answers)');
ok(Object.keys(JSON.parse(raw).profiles).join() === 'default', 'one default profile until Stage 5');
store.emmaProfile = 'kid2'; Q.progress.record('bk', 'z', { first: true, today }, R); delete store.emmaProfile;
ok(Object.keys(JSON.parse(store.emmaQuiz).profiles).sort().join() === 'default,kid2' && !Q.progress.get('default').items.z, 'progress is kept per profile');
Q.progress.clear();
const small = Q.merge(JSON.parse(JSON.stringify(R)), { progress: { keepItems: 3 } });
for (let i = 0; i < 6; i++) Q.progress.record('bk', 'k' + i, { first: true, today: today + i }, small);
ok(eq(Object.keys(Q.progress.get().items).sort(), ['k3', 'k4', 'k5']), 'keepItems: only the most recent questions are kept');
store.emmaQuiz = '{broken'; ok(Q.progress.level('bk', R) === 'starter', 'broken storage does not crash (starts fresh)');

console.log(fails ? `\n${fails} of ${n} FAILED: quiz engine unit tests` : `\nALL OK: quiz engine unit tests (${n})`);
process.exit(fails ? 1 : 0);
