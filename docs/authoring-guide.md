# Authoring guide — adding content to Emmavengers World

You only edit files in `content/src/`. Never edit `content/library/`, `content/registry.lock.json`,
`content/build-report.md` or `sw.js` by hand: they are generated. How it works: `docs/content-library.md`.

## The routine for ANY change

```bash
python3 tools/content_build.py      # 1. validate + build. Read the errors; fix; repeat until "OK"
                                    #    -> read content/build-report.md (plain summary, languages, warnings)
python3 tools/check_voice.py > missing.json   # 2. spoken lines without a voice clip (the build also tells you)
#    make the clips: python3 tools/voice_jobs.py --lang fr > j.json && python3 tools/gen_voice.py j.json --locale fr
python3 tools/build_sw.py           # 3. offline cache list for the new files
python3 tools/run_tests.py          # 4. all tests (validator first). --quick for a 20-second check
git add -A && git commit            # 5. commit content/src AND the generated files together
```

Optional: `python3 tools/run_tests.py --install-hook` makes git run the quick tests before every commit.

## Rules the validator enforces (so you don't have to remember them)

- **Ids** `ew.<type>.<name>`: lower case, digits, dashes, dots. The prefix must match the type
  (`ew.quiz.*` is a quiz-item, `ew.country.*` a country …). Never rename or reuse an id: to replace a record,
  give the new one a new id and set the old one to `withdrawn` (or delete it — its id is then retired forever).
- **Texts** are `{"en": "...", "fr": "..."}` with tags from `content/src/locales.json` only. Every language listed in
  the pack's `locales.required` must be present in every text. `{placeholders}` must match across languages.
  No HTML or script, except bold `<b>` where `capabilities.json` allows it (letter cards).
- **Facts need sources**: a factual quiz item or learn card must cite `ew.source.*` records (URL + date checked).
- **References** must point at records that exist, of the right type, in the same pack or in `core`.
- **Tags** come from `content/src/taxonomy.json` (age bands `5-7`, `8-10`, `11-13`; regions; subjects; difficulty
  `starter`/`core`/`stretch`; modes). Add a new value there first if it is truly needed.
- **Status**: start at `draft`. The preview site shows drafts; the live channel ships only `published`.
- **Files**: every picture and voice clip a record uses must exist; every spoken line must have its clip.
- **Activity types** must be ones the player supports (`content/src/capabilities.json`).

## Add a country

1. Copy the pilot: `cp -r content/src/countries/cameroon content/src/countries/<slug>` (slug: lower-case English name, e.g. `kenya`).
2. In **every** file of the new folder, replace ids: `pilot-cameroon` → `<slug>` (or `pilot-<slug>`), `ew.country.cameroon`
   → `ew.country.<slug>`, `country.cameroon` → `country.<slug>`. Ids must be unique across the library.
3. `pack.json`: `id` `country.<slug>`, `collection` the region (`countries.africa`, `countries.americas`,
   `countries.asia`, `countries.europe`, `countries.oceania`), `summary` `ew.country.<slug>`, the `defaults.tags.regions`,
   `locales.required` (the languages that must be complete), and `"preload": false` (only the pilot is a starter pack).
4. `country.json`: name per language, ISO 3166-1 code in `externalIdentifiers`, flag, hub lines, learn/play/quiz/stories lists.
5. Replace every text and fact; add `sources.json` records for every fact (URL, date checked, publisher). Keep `status: draft`.
6. Add a place in World Land (`content/src/core/lands.json`, record `ew.land.world`, `places`):
   `{"key": "<slug>", "name": {"en": "Kenya"}, "sub": {"en": "Learn · Play · Quiz · Stories"}, "icon": "img/world/countries/<slug>-flag.webp", "type": "country", "country": "ew.country.<slug>", "x": 50, "y": 30}`.
7. Run the routine above. A country test can copy `tools/test_cameroon.py`.
8. When the reviews are done (facts, educator, cultural, language, Emmanuel): set statuses to `published`.

## Add a language

Full guide: `docs/languages.md`. In short:

1. `content/src/locales.json`: add `{"tag": "sw", "name": "Kiswahili", "englishName": "Swahili", "dir": "ltr", "script": "Latn",
   "status": "in-review", "fallback": ["en"], "voice": null}` (BCP 47 tag; `dir` `rtl` for Arabic, Hebrew…).
2. Translate in `content/src/l10n/sw/*.json` (copy the French files: same record ids and paths), `reviewStatus: "draft"`.
   Small texts can also go straight into records: `{"en": "Hello", "fr": "Bonjour", "sw": "Habari"}`.
3. Build; read "Language coverage" in `content/build-report.md`. Missing words fall back to the next language of the chain.
4. Voice: set `voice` (Kokoro voice, phonemizer language, speed, pitch, folder `voice/sw/`), then
   `python3 tools/voice_jobs.py --lang sw > /tmp/jobs.json && python3 tools/gen_voice.py /tmp/jobs.json --locale sw`.
   Without a voice the phone's own voice reads the language (fine for testing, not for children).
5. Pictures with English text drawn in them: add `<name>.sw.<ext>` next to the original.
6. After a fluent review set `reviewStatus: "reviewed"` (it then ships on live); `status: "active"` when complete.

## Add or change a land, a place, a deck item, a Study shelf

- Lands: `content/src/core/lands.json` (one `land` record each) and the order in `content/src/core/world.json`
  (`payload.lands`). A land needs a map picture, a color, a music theme and its places.
- Places: `type` `link` (opens a game module), `cards` or `quiz` (with a deck), `count`, `country`.
- Deck items (letters, numbers, animals, country cards, prayers): `content/src/core/decks.json`. Facts need sources.
- Study shelves: `content/src/core/study.json`.
- Letter sounds (IPA for the voice): `content/src/core/lexicon.json`.

## Add a game (activity)

- Using an existing type (`grid-route.v1`, `ordered-slots.v1`, `match.v1`, `map-select.v1`, `evidence-comparison.v1`,
  `inquiry.v1`): add an `activity` record in the country's `play.json` and list it in the country's `play` list.
- A **new** type needs code: add it to `content/src/capabilities.json`, to `TEMPLATES` in `library.js`, write the player in
  `country.js`, and bump `player` in `build.json` if old apps must not receive it. Old app versions skip packs that need
  types they don't know (they never crash on them).

## Add a quiz (or questions to a quiz)

Full design: `docs/quiz-engine.md`. Nothing about a quiz is in the code - it is all records.

1. **Questions**: copy a `quiz-item` record (e.g. in `content/src/core/quiz.json`), give it a new id `ew.quiz.<name>`.
   Pick `responseType`: `single-choice`, `picture-pick` (add `optionMedia` pictures + `optionSay` words for the voice),
   `count` (`count: {n, img}`), `true-false` (`answerKey` `"true"`/`"false"`), `order` (`answerKey` = option ids in order)
   or `match` (`targets` + `answerKey` = `{option: target}`). Write `prompt`, `options`, `hint`, `feedback` and, if it
   helps, `explanation`. Tag the age band and `difficulty` (`starter`, `core`, `stretch`). A digit answer such as "5"
   gets an `optionSay` word ("Five.") so the voice never guesses. Facts need `evidence` with a `source` record.
2. **The quiz**: a `quiz-bank` record lists the `items` (or a `generator` for deck quizzes), a `title`, an `intro`
   and optional Ari/Ezra `lines` (`start`, `correct`, `tryAgain`, `hint`, `done` - pre-written `line` records only).
3. **Rules**: name a `quiz-rules` record in `rules` (`ew.quizrules.default` if you leave it out) and, for one quiz only,
   change single values in `ruleOverrides` (e.g. `{"choices": {"default": 4}}`). Precedence: built-in <- the rules
   record <- `ruleOverrides`. The validator refuses impossible rules (2 stars stricter than 3, unknown levels,
   intervals going down).
4. **Put it on a land**: add a place with `"type": "bank"` and `"quiz": "<bank id>"` to the land record (name, sub,
   icon, x, y, intro, + translations in `l10n/<lang>/core-lands.json`). A draft bank is left out of the live site, and so
   is its place.
5. **Voice**: run the routine above (voice_jobs -> gen_voice for English E3 and for French). Every question, answer,
   hint and line needs an English clip, or the build stops.
6. Test: `python3 tools/test_quiz_schema.py`, `node tools/test_quiz_engine.js`, `python3 tools/test_quiz.py`.

## Add a Daily Ari Mission or a Together Time activity

1. Copy a record in `content/src/life/missions.json` (or `together.json`), give it a new id `ew.mission.<name>` /
   `ew.together.<name>` (never reuse an old id) and a matching `key`.
2. Pick `kind` from `taxonomy.missionKinds` / `taxonomy.togetherKinds`, the age bands, `where` and `timeOfDay`.
3. Keep `task` short enough for a 5-year-old. If a grown-up must be close by, set `adultNearby: true`, `parentConfirm: true`
   and write a `parentNote`. No web addresses, no photos of the child, nothing that sends the child to strangers.
4. A parent tip (`kind: parent-tip`, `audience: parent`) must cite a `source` record (add one to `life/sources.json`).
5. Leave `status: draft` until Emmanuel approves it; then run the routine above.

## Change an app rule (missions on/off, gentle/firm, parent gate, screen limit, bedtime)

Edit `content/src/core/settings.json` (record `ew.settings.app`), run the routine, publish. No app rebuild. The validator
refuses impossible combinations (a default mode that is not offered, firm missions without a grown-up check, a default
outside min/max, a parent-changeable setting that does not exist, a second settings record).

## Statuses and reviews

`draft` (being written) → `checking` (sent to reviewers) → `changes-requested` → `reviewed` → `approved` (Emmanuel) →
`published` (on live). `withdrawn` removes it from children at once (the build blocks anything still using it);
`archived` keeps history only. Write who reviewed what in `review` (`records`, `note`) and per language in `l10n`.

## Publishing to the live site

`main` is the live site (GitHub Pages), so on `main` the build setting `channel` in `content/src/build.json` is `live`
(published records only). The test site must be built with `python3 tools/content_build.py --channel preview`
(drafts included). Release 1 (2026-11-10): the Cameroon pilot, Ari/Ezra and the country-player buttons were approved
for live by Emmanuel CLETUS, with French pending fluent review, placeholder art and synthetic voices recorded in each
record's `review`. The hub's "Draft for testing" badge only shows for a country that is not `published`.

