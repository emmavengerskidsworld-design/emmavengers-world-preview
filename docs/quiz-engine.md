# Quiz engine (Stage 3)

Plain summary: every quiz in Emmavengers World is now **data played by one engine** (`quiz.js`). A question is a
`quiz-item` record (any language, any country, any land); a quiz is a `quiz-bank` record (a list of questions, or a
"generator" that makes questions from a card deck, like Letter Hunt or Count It!); the rules (how many questions, how
many answer buttons, stars, hints, retries, review of old questions, adaptive difficulty, what the voice reads) are a
`quiz-rules` record. Adding a question, a quiz, a country, a language or changing a rule is a **content release, not
an app rebuild**. Nothing about the child leaves the phone.

## 1. What the research says (and the rule it became)

| Finding | Source | Rule in the engine |
|---|---|---|
| Answering questions (retrieval practice) helps children remember more than re-reading; it worked in 46 of 49 classroom studies, across ages and subjects. | Agarwal, Nunes & Blunt (2021), *Educational Psychology Review* 33, 1409-1453; Roediger & Karpicke (2006), *Psychological Science* 17(3) | Quizzes come after Learn/cards, are short (4-8 questions) and low-stakes: no timer, no score shown to others, no losing. |
| Spacing practice over days beats massed practice ("spaced repetition"); the Leitner box system is the simplest form. | Cepeda et al. (2006), *Psychological Bulletin* 132(3); Kang (2016), *Policy Insights from the Behavioral and Brain Sciences* 3(1) | `selection: "leitner"`: each question has a box (0-5); right first time moves it up (seen again after 1, 3, 7, 14, 30 days), a miss moves it back to box 1. Due questions come first. The interval list is data. |
| Feedback helps most when it is about the task ("the star is in the middle") and immediate for young learners; feedback about the person ("you're bad at this") harms. Praise effort and strategy, not "being smart". | Hattie & Timperley (2007), *Review of Educational Research* 77(1); Shute (2008), *RER* 78(1); Mueller & Dweck (1998), *JPSP* 75(1) | Wrong answer: a soft sound, the option greys out, Ari says a pre-written "Nice try! Let's look again." - never red crosses, buzzers, "wrong!" or lost lives. Correct: a short task-specific feedback/explanation line. |
| Mistakes followed by corrective feedback are good for learning (errorful learning), especially with a hint and another try. | Metcalfe (2017), *Annual Review of Psychology* 68 | Retry until right (`retry.untilCorrect`), hint button + hint after the first miss (`hintAfterTries`), Skip offered after a miss (`skipAfterTries`) so no child is stuck. |
| Learning is fastest when the task is neither too easy nor too hard - about 85% success in a two-choice task. | Wilson et al. (2019), *Nature Communications* 10:4646 ("Eighty Five Percent Rule") | Simple adaptive difficulty (`adaptive`): items carry `tags.difficulty` starter/core/stretch; 3 right-first-time in a row -> one level up, 2 misses in a row -> one level down, never more than one step at a time; the child never sees a "level". Off by default for migrated quizzes. |
| Good educational apps are active ("minds-on"), engaged (few distractions), meaningful and social; 5-7 year olds are pre- or early readers. | Hirsh-Pasek et al. (2015), *Psychological Science in the Public Interest* 16(1) | Every question and every answer can be heard; ages 5-7 get the answers read on screen entry, 2-3 big choices, pictures where possible. Explanations connect to Learn cards. |
| 4 in 5 apps used by 3-5 year olds use manipulative design: fake time pressure, characters pressuring the child, lures (streaks, daily rewards), blocked navigation. | Radesky et al. (2022), *JAMA Network Open* 5(6):e2217641 | Forbidden by the validator/engine design: no timers, no streak or "come back tomorrow" pressure, no loss of stars, Back always works, Ari/Ezra never guilt the child (lines are pre-written and reviewed). |
| Touch targets: at least 24x24 CSS px (WCAG 2.2 SC 2.5.8, AA), 44x44 for AAA (SC 2.5.5); platform guides 44pt (Apple) / 48dp (Material). Young children's motor control is less precise. | W3C WCAG 2.2 (2023); Apple Human Interface Guidelines; Material Design 3; Nielsen Norman Group, *Children's UX* research | Every quiz button is >= 48x48 px (tested in the browser suite); answers never rely on colour alone. |
| Children's data: collect the minimum, high-privacy defaults, no profiling, no nudges; parental consent for any personal data. | UK ICO *Age Appropriate Design Code* (2020), 15 standards; US COPPA Rule (16 CFR Part 312); GDPR Art. 8 | Progress (boxes, levels, best stars) is kept **only in this phone's localStorage**, under a profile id that is just a label ("default" until the Parents' Corner adds profiles in Stage 5). No names, no answers text, no network calls, no analytics. Parents can clear it. |
| Offline-first learning tools (Kolibri) keep content and progress on the device. | Learning Equality, Kolibri docs | Questions come from the verified content library (IndexedDB); voice clips are cached by the service worker; the engine never needs the network. |

Age bands (taxonomy `5-7`, `8-10`, `11-13`) follow the reading-stage split used by NN/g children's research and
most national curricula: 5-7 = pre/early readers (voice reads everything, pictures, 2-3 choices), 8-10 = readers
(voice on demand, 3-4 choices), 11-13 = reasoning, evidence and sources questions (4 choices allowed). All of these are
numbers in `quiz-rules`, not code.

## 2. Data

### `quiz-item` (one question) - `ew.quiz.<name>`

| Field | Meaning |
|---|---|
| `responseType` | `single-choice` (pick one text answer), `picture-pick` (pick one picture), `count` (count the objects, pick the number), `true-false`, `order` (tap the answers in the right order), `match` (pair each answer with its partner). The app lists what it can play in `capabilities.json` `quizResponseTypes`; the validator refuses anything else. |
| `prompt` | the question, per language `{"en": "...", "fr": "..."}` - spoken by the language's voice |
| `options` | `{id: text}` stable ids (2-6). The key is bound to the id, never to a position; positions are shuffled on screen only. |
| `optionMedia` | `{id: picture}` - required for every option of `picture-pick`, optional elsewhere |
| `optionSay` | `{id: text}` - what the voice says for a picture answer when the answers are read |
| `promptMedia` | a picture shown with the question (optional) |
| `count` | `{n, img}` for `count`: how many objects and which picture; `numbers` (optional) fixes the answer buttons |
| `targets` | for `match`: `{id: text}` the right-hand column |
| `answerKey` | `single-choice` / `picture-pick`: an option id; `true-false`: `"true"`/`"false"`; `count`: the number as text; `order`: the option ids in order (array); `match`: `{optionId: targetId}` |
| `hint`, `feedback`, `explanation` | per language; hint after a miss or on the Hint button; feedback + explanation after the right answer |
| `lines` | optional Ari/Ezra line records (`ew.line.*`) for this item: `{correct, tryAgain, hint}` |
| `tags.ageBands`, `tags.difficulty`, `tags.land`, `tags.topics` (country/topic), `tags.subjects` | the pool filters: `EWLib.find({type:'quiz-item', ageBand, topic})` |
| `evidence` | sources for facts (`factual: true` needs `ew.source.*`); arithmetic / picture items set `factual: false` with a note |

### `quiz-bank` (one quiz) - `ew.quizbank.<name>`

`items` (authored questions) **or** `generator` (questions made from a deck: `{kind: "deck-pick"}` for Letter Hunt /
Animal Quiz / Flag Quiz, `{kind: "count", min, max, near}` for Count It!), plus `title`, `intro`, `rules`
(a `quiz-rules` record), `ruleOverrides` (a few rule values for this quiz only), `lines` (Ari/Ezra lines:
`start`, `correct`, `tryAgain`, `hint`, `done`) and the older `roundRules` note. A land place opens a bank with
`"type": "bank", "quiz": "ew.quizbank.<name>"`; deck quizzes keep their place fields (`deck`, `mode`, `ask`) and add
`"quiz"` to point at their bank's rules.

### `quiz-rules` (engine settings) - `ew.quizrules.<name>`

Every rule has its switch and numbers here (see `content/src/core/quiz.json`):
`enabled`, `selection` (`random` | `fresh-today` | `leitner`), `roundSize` (default + per age band), `choices`
(answer buttons per age band), `shuffleOptions`, `noRepeatInRound`, `exhaustion` (`finish-or-practice` | `reshuffle`),
`retry` (`untilCorrect`, `disableWrong`, `hintAfterTries`, `skipAfterTries`, `hintButton`), `stars` (`basis: mistakes`,
`three` = most mistakes for 3 stars, `two` = for 2 stars), `adaptive` (`enabled`, `start`, `upAfter`, `downAfter`),
`spaced` (`intervalsDays`), `voice` (`readQuestionOnShow`, `readAnswersOnShow` per age band, `speakerReadsAnswers`,
`pictureAnswers`), `feedback` (`praise`: `app` lists or `lines`, `confetti`), `progress` (`keepItems`).
Order of precedence: built-in defaults (= the behaviour of the quizzes before Stage 3) <- `ew.quizrules.default` <-
the bank's `rules` record <- the bank's `ruleOverrides`. A rule the running app does not know is ignored, so old
phones never break on new rules. Timers, lives, streaks and leaderboards do not exist and the schema has no place
for them.

Records shipped now: `ew.quizrules.default` (the new gentle rules: Leitner review, adaptive on, hints, answers read
for 5-7), `ew.quizrules.land-classic` (Letter Hunt, Animal Quiz, Flag Quiz, Count It! exactly as before) and
`ew.quizrules.country-classic` (the Cameroon quiz exactly as before: fresh-today rounds, finish-or-practice,
Little/Big pools).

## 3. Engine (`quiz.js`, `window.EWQuiz`)

- `rules(bank)` merged rules; `rng(seed)` + `shuffle` (Fisher-Yates); `choicesFor(rules, band)`; `stars(miss, rules)`.
- `buildRound({pool, n, practice, strategy, seen, prev, progress, level})` - `fresh-today` is the Cameroon algorithm
  (unseen today first, then not seen last time; `null` when exhausted -> Finish / Practise again), `leitner` puts due
  questions first and then new ones, `random` for deck quizzes; adaptive level filters by difficulty when items have it.
- Deck generators: `deckTarget`/`distractors` (Letter Hunt / Animal / Flag), `countRound`/`countOptions` (Count It!).
- `view(record)` turns a `quiz-item` into what the screen needs in the child's language (fallback chain, every text
  marked with its language so the right voice folder plays it).
- `progress` - per profile, on this device only: `record(bank, item, {first, hint, skipped})` updates the Leitner box
  and adaptive level; `finish(bank, stars)` keeps the best stars; `summary()` for the Parents' Corner (Stage 5);
  `clear()`.
- The generic player screen (`qplay` -> `qdone`) plays any authored bank with the six response types: question +
  🔊 (reads the question and every answer), big answer buttons, Hint, gentle retry, Skip, feedback + explanation,
  Ari/Ezra lines, stars at the end. Voice goes through the app's clip system (`say`, `cacheClips`, `warmVoice`), so
  every line has a recorded clip (validator) and the first tap plays from the phone.

## 4. Voice

Every text a quiz can speak (questions, answers, `optionSay`, hints, feedback, explanations, Ari/Ezra lines, the app
words True/False) is a "spoken line": the validator lists it per language and fails the build if an active
language's clip is missing (`tools/content/legacy.py: quiz_spoken`). English clips are made with
`tools/gen_voice.py` (E3 voice, pronunciation dictionary, listening check), French with ff_siwis.

## 5. Honest limits

- Profiles: there is one "default" profile until Stage 5 adds child profiles in the Parents' Corner; the store is
  already keyed by profile.
- Adaptive difficulty needs items tagged with `difficulty`; the Cameroon items have none yet (left empty rather than
  guessed), so it stays off there.
- Picture answers in the land quizzes are not read aloud (the picture is the answer and the old games never read
  them); `voice.pictureAnswers` can switch it on per quiz once Emmanuel decides.
- The sampler quiz ("Quiz Time" in Number Land) is a draft for the preview site only; its French is machine-drafted
  and needs a fluent review.
