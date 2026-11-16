# Languages and voice (Stage 2)

Plain summary: every word the child sees or hears comes from data, per language. A language is added by adding
data (no code change); the child (or a parent) picks it once and the phone remembers it; the phone downloads only
that language and the languages it falls back to; missing words fall back along a chain (fr-CM → fr → en) and every
line is spoken by the voice of the language it is actually written in.

## What a language is

`content/src/locales.json`, one entry per language:

| Field | Meaning |
|---|---|
| `tag` | BCP 47 tag (`en`, `fr`, `fr-CM`, `ar`, `sw`, `zh-Hant`) — case-insensitive; file names use lower case |
| `name`, `englishName` | the language's own name (shown in the picker) and its English name |
| `dir` | `ltr` or `rtl` — must match the script (the validator checks) |
| `script` | ISO 15924 code (`Latn`, `Arab`, `Deva`, `Ethi`, `Hans`, `Hant`); the font stack comes from `scripts` in the same file |
| `status` | `active` (ready for children), `in-review` (live: only reviewed/approved texts; preview: drafts too), `planned`, `test-only` (never shipped) |
| `fallback` | languages to try next, in order (after the tag's own shorter forms: `fr-CM` tries `fr` by itself) |
| `numberingSystem` | optional (`arab` for Arabic-Indic digits); numbers are formatted with `Intl.NumberFormat` |
| `voice` | `{pack, engine, voice, lang, speed, pitch}` — where its clips live (`voice/fr/`) and how they are made; `null` = the phone's own voice reads it |

Which languages a channel ships is in `content/src/build.json` (`channels.<name>.locales` = allowed statuses,
`overlays` = allowed review states of translation files). Live ships `active` + `in-review` languages but only
`reviewed`/`approved` translation files; preview ships drafts too; the `test` channel adds the `test-only` samples
(`ar`, right-to-left, and `fr-CM`, the fallback chain). The test channel is built only into temporary folders by
`tools/test_i18n.py` — it is never written to `content/library` or `content/preview`.

## Where the words are

- **Inside records**, as `{"en": "...", "fr": "..."}` (content written together, e.g. the Cameroon pilot).
- **Translation files** `content/src/l10n/<tag>/*.json`: `{locale, translator, reviewStatus, strings: {recordId: {path: text}}}`.
  Paths are dot-paths into the payload (`payload.places.safari.name`; list items by their `key`/`id`, or by number).
  `reviewStatus` is `draft`, `machine-draft`, `reviewed` or `approved`; the channel decides which ones ship.
- **App words** (buttons, praise, Parents' Corner, the language picker, the update button): record `ew.ui.app`
  (`content/src/core/ui-app.json`). Messages use a small, safe subset of ICU MessageFormat:
  `{name}`, `{n, number}`, `{n, plural, one {# star} other {# stars}}` (CLDR plural rules through `Intl.PluralRules`,
  so Arabic gets its six forms), `{x, select, a {...} other {...}}`. No HTML.
- **Pictures with text drawn in them**: put `<name>.<tag>.<ext>` next to the original (`img/world/nature-land.fr.jpg`).
  The build lists it under that language (`pictures` in the catalog); the app shows it for that language and the
  languages that fall back to it, and the original for everyone else. Only devices using that language download it.
- **Question templates** (`"Find {nameDef}!"`) are filled with the item's words **in the template's own language**, so a
  half-translated deck never produces mixed sentences. Grammar helper fields (`nameDef` "the lion" / "le lion",
  `nameOf` "of Cameroon" / "du Cameroun") let each language phrase it correctly.

## Fallback chain

`chain(tag)` = the tag, its shorter forms (`fr-CM` → `fr`), its `fallback` list (each expanded the same way), then the
source language `en` — keeping only languages the channel ships. The same function exists in Python
(`tools/content/common.py: chain_for`) and JavaScript (`library.js: chainFor`), and the tests compare both adapters.

## Right-to-left

`EWi18n.apply()` sets `<html lang dir data-script>`, the class `rtl` and the font variable `--ew-font`. The layout uses
CSS logical properties (`margin-inline-start`, `inset-inline-end`, `text-align: start`), so it mirrors by itself;
the back arrow flips; numbers like the star score stay left-to-right (`dir="ltr"` on `#score`). Text never contains
bidi override control characters (the validator rejects them; embeddings are a warning). The land map itself is a
picture and is not mirrored (places stay where they are drawn).

## On the device (`library.js`, `i18n.js`)

1. First visit: the best match of the phone's languages (`navigator.languages`, by BCP 47 lookup), else English.
2. The choice (`localStorage.emmaLang`) is remembered; the picker is the 🌐 button in the header and a section in
   Parents' Corner.
3. Only the chain's text files are downloaded and verified (SHA-256); switching language downloads the new files,
   then removes the old language's files from the device. The language's voice folder (`voice/fr/`) is downloaded
   for offline by the service worker (pack `lang:fr`).
4. Every flattened text remembers the language it came from (`EWi18n.langOf`), so the voice plays the clip from that
   language's folder (or, with no recorded voice, the phone's voice in that language). A French line never gets an
   English clip and vice versa.

## Add a language (checklist)

1. `locales.json`: add the entry with `status: "in-review"` (or `planned`). Add a `scripts` entry if it is a new script.
2. Translate: `content/src/l10n/<tag>/*.json` (copy the French files as a template), `reviewStatus: "draft"`.
3. `python3 tools/content_build.py` → `content/build-report.md`, "Language coverage in this channel": texts translated,
   what falls back, spoken lines and missing voice clips per language.
4. Voice: add `voice` to the entry, then `python3 tools/voice_jobs.py --lang <tag> > /tmp/jobs.json` and
   `python3 tools/gen_voice.py /tmp/jobs.json --locale <tag>`. Listen to a sample; `python3 tools/build_sw.py`.
5. A fluent reviewer checks the texts → `reviewStatus: "reviewed"` (then it ships on live), Emmanuel approves → `approved`.
6. `python3 tools/run_tests.py`.

## Validator checks for languages

- Every shipped language: script has a font stack, `dir` matches the script, fallbacks exist and the chain ends in English.
- Coverage per language and pack (records marked `l10n.sourceOnly`, e.g. English letter sounds, are not counted).
- Placeholders: the same ICU arguments in every language (`{n}` in English must be `{n}` in French).
- Voice: every spoken line in every language has its clip in that language's folder (error for active languages,
  warning for in-review, note for test-only); an active language without a voice is a warning.
- RTL: bidi override characters are errors; a right-to-left text with no right-to-left letters or identical to
  English is flagged.
- Localized pictures: the language must exist and the original must be there.

## Research this follows

- BCP 47 tags (RFC 5646) and lookup/fallback (RFC 4647 §3.4) — tag truncation `fr-CM` → `fr`.
- Unicode CLDR plural rules (UTS #35) through `Intl.PluralRules`; ICU MessageFormat argument syntax (only the safe
  subset above; Unicode MessageFormat 2 is the long-term target once `Intl.MessageFormat` is standard).
- W3C Internationalization: "Structural markup and right-to-left text in HTML" — set `dir` on `<html>`, avoid bidi
  control characters, isolate numbers; CSS Logical Properties and Values Level 1 for mirroring.
- `Intl.NumberFormat` with `numberingSystem` for digits; Noto font families per script for fallback.
- Android/iOS app localization practice: per-language resource files, a base-language fallback, localized drawable
  variants (`drawable-fr`) — the picture variants follow the same idea.
