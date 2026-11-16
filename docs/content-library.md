# Emmavengers World content library (Stage 1)

This explains, in plain language, how the game's content is stored, checked, shipped and loaded.
For step-by-step instructions (add a country, a language, a land, a game), see `docs/authoring-guide.md`.

## The idea in one paragraph

All content (the world map, the six lands, the card decks, the Study shelves, the countries with their lessons,
games, quizzes, stories and guide lines) is **data**, written once in `content/src/`. A checker (the validator)
reads all of it and refuses anything broken, unsafe, unsourced or untranslated where a translation is required.
A compiler then turns it into small, numbered, fingerprinted files in `content/library/`. The app's loader
(`library.js`) downloads only what it does not have yet, proves every file is exactly what was published (SHA-256),
keeps everything on the device for offline play, and keeps the previous release in case the new one is damaged.

## Words used here

| Word | Meaning |
|---|---|
| **record** | One piece of content with a stable id, e.g. `ew.quiz.pilot-cameroon-q01` (a quiz question) or `ew.land.world`. |
| **pack** | A folder of records that ship together: `core` (map, lands, decks, characters, shared buttons) and one per country (`country.cameroon`). |
| **collection** | A group of packs with its own small index: `core`, `countries.africa`, `countries.americas`, `countries.asia`, `countries.europe`, `countries.oceania`. |
| **release** | One published state of the whole library, numbered by `sequence` (1, 2, 3 … never goes down). |
| **channel** | Which statuses a release contains. `preview` (the test site) includes drafts; `live` contains only `published`. |

## What a record looks like

Every record has the same envelope (schema `content/schema/v1/record.schema.json`):

```json
{
  "id": "ew.quiz.pilot-cameroon-q01",
  "type": "quiz-item",
  "status": "draft",
  "sourceLanguage": "en",
  "tags": {"land": "world", "ageBands": ["5-7"], "subjects": ["geography"], "regions": ["africa"], "modes": ["quiz"]},
  "evidence": {"sources": ["ew.source.pilot-cameroon-un"], "factual": true},
  "review": {"note": "Pilot draft: needs educator, cultural and Emmanuel review"},
  "l10n": {"fr": {"status": "draft-pending-fluent-french-review"}},
  "payload": {"prompt": {"en": "Which describes Cameroon itself?", "fr": "Qu'est-ce qui décrit le Cameroun lui-même ?"}, "...": "..."}
}
```

- **id** — `ew.<type>.<name>`, lower case. Never reused: once removed, an id is *retired* forever (the build refuses to reuse it).
- **type** — one of: world, land, deck, library, lexicon, character, strings, country, topic, source, lesson,
  learn-card, activity, quiz-bank, quiz-item, quiz-rules, story, line, media, mission, together, settings. Each type has its own payload schema (`payloads.schema.json`).
- **revision** — added by the build, never typed by hand. It goes up by one whenever the record's content changes
  (tracked in `content/registry.lock.json`).
- **status** — `draft → checking → changes-requested → reviewed → approved → published`, plus `withdrawn` and `archived`.
- **tags** — closed lists from `content/src/taxonomy.json`: age bands `5-7`, `8-10`, `11-13`; subjects; land; regions
  (UN M49 continental regions); difficulty `starter`, `core`, `stretch`; modes; sensitivity; access.
- **texts** — every text a child sees or hears is a language map `{"en": "...", "fr": "..."}` keyed by BCP 47 tags
  registered in `content/src/locales.json`. There is **no silent fallback**: if a pack says French is required, a missing
  French text stops the build. Placeholders such as `{place}` must be identical in every language.
- **evidence** — sources (records of type `source`, with URL and date checked) for factual content; notes otherwise.
- **review / l10n** — who must still check it, and the review state of each language.

Source files may set **defaults** in `pack.json` (e.g. all Cameroon records are `draft`, tagged `world` + `africa`), so
records stay short. The pack's `summary` record (e.g. `ew.country.cameroon`) gates the whole pack: on a channel where the
country itself is not allowed, none of its records ship — a country appears as one complete unit or not at all.

## What gets shipped (`content/library/`)

```
catalog.json                                  ~2 KB  the root: release sequence, languages, list of collections
indexes/countries.africa.<hash16>.json        one per collection: the packs in it, their files, sizes, SHA-256, summary
packs/country.cameroon.<hash16>.json          structure: records with every text replaced by {"$t": n}
packs/country.cameroon@en.<hash16>.json       the texts in English, in the same order (n-th string = text n)
packs/country.cameroon@fr.<hash16>.json       the texts in French
packs/country.cameroon.assets.<hash16>.json   every picture and voice clip the pack needs (bytes, SHA-256, rights)
```

- **Content-addressed names**: the 16 hex digits are the start of the file's SHA-256. A file never changes after it is
  published; a change produces a new name. So caches can keep files forever and an update downloads only new names.
  `catalog.json` is the only file that changes in place (the service worker reads it network-first).
- **Languages are separate files**, each bound to its structure file by hash, so a phone can later download only the
  child's languages, and adding a sixth language does not make other languages' downloads bigger.
- **Old releases are kept** on the server (`retainReleases: 2`) so phones in the middle of an update and rollbacks work.

## How the app loads it (`library.js`)

1. **Start**: open the copy saved on the device (IndexedDB). Every file is re-hashed before use. If it is fine, the
   game starts with no network at all. If the saved release is damaged, it uses the previous saved release
   (rollback); if that is damaged too, it downloads a fresh copy.
2. **First visit**: download `catalog.json`, the collection indexes and the starter packs (`"preload": true`: core and,
   for the pilot, Cameroon), verify each file, then save them **in one transaction** with the new state — a phone that
   loses power mid-download never ends up half-updated.
3. **Updates** (in the background, a few seconds after start, at most every 6 hours): read `catalog.json`. Same file →
   nothing to do. A higher sequence → fetch only files the device does not already have, verify them, save them. The
   game the child is playing does not change under them: the new release is used from the next start (or `applyUpdate()`).
   An *older* sequence (replay) is refused; a file whose size or SHA-256 is wrong is refused and the last good
   release stays in use; a pack that needs an activity type this app version does not have is skipped.
4. **Countries not marked preload** are downloaded the first time the child opens them, then kept for offline.
5. **No IndexedDB** (some private modes): everything still works for the visit, from memory.

Query API (for Stages 2–5): `EWLib.get(id)`, `EWLib.find({type, land, ageBand, mode, subject, region, topic, lang, status, pack})`,
`EWLib.text(lt, lang)` / `textOr(lt, [langs])` (explicit, no hidden fallback), `locales()`, `packs()`, `ensure(packId)`,
`forEachText(fn)`, `status()`, `checkForUpdates()`, `applyUpdate()`, `on('update'|'rollback'|'pack'|'ready', fn)`.
`EWLib.legacy.*` rebuilds the pre-Stage-1 shapes so `world.js` (`LANDS`) and `country.js` work unchanged; Stage 5 moves
the screens onto the query API and then the legacy adapter can be deleted.

## How the plug-in stages fit

- **Stage 2 (languages + voice)**: done — see `docs/languages.md` (language records, translation files, fallback
  chain, ICU-lite messages with CLDR plurals, right-to-left, localized pictures, per-language voice folders, only the
  chosen languages on the device).
- **Stage 3 (quiz engine)**: done - see `docs/quiz-engine.md`. Questions are `quiz-item` records (six types:
  single-choice, picture-pick, count, true-false, order, match) with stable option ids, answer keys, per-language text,
  age band, difficulty, hint and explanation; quizzes are `quiz-bank` records (authored items or a generator that makes
  questions from a deck); every rule (round size, answer buttons, stars, hints, retry, spaced review, adaptive level,
  what the voice reads) is a `quiz-rules` record. One player (`quiz.js`) plays them all; progress stays on the phone.
- **Stage 4 (kid-safe search)**: search only over records in the library (never the open web): `forEachText` gives
  every text per language to build an index on the device.
- **Stage 5 (migration of the six lands, parents area, privacy page)**: screens switch from `LANDS` to the query API.

## Daily Ari Missions, Together Time and app settings (room made in Stage 2)

Added to the plan by Emmanuel on 2026-11-14. Only the **data shapes, checks and loader** exist now; the screens come with the
Parents' Corner in Stage 5. Everything below is `draft`, so the live channel strips it (the live library is byte-for-byte unchanged).

- **`mission`** (`ew.mission.<name>`, pack `life`, file `content/src/life/missions.json`): one small real-life task done away
  from the screen. Fields: `kind` (closed list `taxonomy.missionKinds`: chore, kindness, gratitude, prayer, family, creative,
  outdoor, care), `title`, `task` (what Ari says), optional `steps`, `doneText`, `where` (home / outdoors / anywhere / travel),
  `timeOfDay` (`taxonomy.timesOfDay`), `minutes`, **`parentConfirm`** (a grown-up confirms through the parent gate before the
  star), `proof` (parent-check / draw / tell / none), `adultNearby`, `parentNote` (Parents' Corner only), `stars`,
  `scripture` (references only). Age bands are the usual `tags.ageBands`.
  Checks: a mission that needs a grown-up close by (adultNearby, outdoors, or sensitivity adult-accompaniment) must have
  `parentConfirm: true`; no web addresses; prayer missions should carry subject faith.
- **`together`** (`ew.together.<name>`, `content/src/life/together.json`): `audience` parent-and-child (activities, family
  devotion, talk after a story...) or parent (`kind: parent-tip`, the weekly tip in the Parents' Corner). Fields: `title`,
  `intro`, `steps`, `talkAbout`, `materials`, `minutes`, `cadence`, `timeOfDay`, `screen` (off / on / either), `links` (records
  in the same pack or core - never web links), `scripture`. Checks: parent tips give advice, so they **must cite sources**;
  kind parent-tip and audience parent always go together.
- **`settings`** (exactly one record, `ew.settings.app`, `content/src/core/settings.json`): the app's rules as data, each with
  an on/off switch and its numbers - `missions` (enabled, defaultMode gentle/firm/off, modes offered, showOnOpen,
  laterAllowed, breakAfterMinutes {default,min,max}, perDay, confirm, starsUnlock, kinds), `parentGate` (methods math/pin/hold,
  primary, fallback, pinLength, maxTries, lockSeconds, logConfirmations), `screenTime` (enabled, dailyMinutes range,
  warnBeforeMinutes, gentle-goodbye end, offlineIdeas), `bedtime` (enabled, start, end, dim, which timesOfDay and record types
  stay open, musicOff), `together` (enabled, tip cadence and weekday) and `parentsMayChange` (which of these a parent may set on
  the device). **Every rule is off** until its screen is built, tested and approved.
  In the app: `EWLib.settings()` = built-in defaults (all off) <- the release's record <- the parent's own choices on this
  device (`setParentSetting(path, value)`; only listed paths, numbers clamped to min/max, modes must be offered;
  `clearParentSettings()`). So switching a rule on, changing a number or switching it off is a **content release, not an app
  rebuild**. A brand-new kind of rule still needs an app change once (the app must know what the rule does), then it is data.

Voices are data in the same way: each language's voice (name, speed, pitch, clip folder) lives in `content/src/locales.json`,
so a voice can be swapped by regenerating that language's clips (`tools/gen_voice.py`) with no change to the app code.

## Research this design follows

- **Kolibri (Learning Equality)** — offline-first education platform for low-connectivity schools: content is
  shipped as versioned *channels*; files are stored under their checksum so identical files are never downloaded twice;
  the app checks the content schema version it supports. (kolibri.readthedocs.io, Kolibri developer docs on content
  channels and the content database.)
- **Workbox precaching (Google)** — the standard for offline web apps: files listed with a revision/hash, only
  changed files are downloaded, old caches cleaned after activation. (developer.chrome.com/docs/workbox/modules/workbox-precaching)
- **web.dev, "Update" for PWAs** — never change what a running page uses mid-session; apply on next start. (web.dev/learn/pwa/update)
- **The Update Framework (TUF) 1.0** — sequence numbers that only go up (rollback/replay protection), hashes and sizes
  for every target file, keeping a last-known-good state. (theupdateframework.github.io/specification)
- **JSON Schema Draft 2020-12** — schema language for every file. (json-schema.org/draft/2020-12)
- **BCP 47 / CLDR** language tags and **Unicode MessageFormat 2.0** (stable since CLDR 47). (unicode.org/reports/tr35/tr35-messageFormat.html)
- **Contentful / headless CMS practice** — stable ids, per-locale fields, publish states, versions. (contentful.com/developers/docs)

## Honest limits (see the Stage 1 report too)

- SHA-256 proves a file is **intact and the one listed in the catalog**; it does not prove **who** published the catalog.
  Anyone who can push to the repository can publish content. Signing (TUF-style keys) is deferred; GitHub Pages HTTPS
  protects the transfer.
- The legacy decks (animals, country cards) have no sources yet — the validator warns about this on every build.
- Age bands on the pre-Stage-1 content were inferred and are marked provisional; difficulty is left empty rather than guessed.
