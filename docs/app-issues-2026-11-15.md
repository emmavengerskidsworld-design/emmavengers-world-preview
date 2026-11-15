# App issues from Emmanuel's phone recording (15 Nov 2026)

A video model described the recording, so I checked each issue myself.
- Checked against the clip files: Whisper listened to the actual MP3s.
- Checked in the app: headless Chrome as a Pixel 7, with instrumented audio. The test logs every clip's start and stop, so it can see a cut-off line.
- Fixes are on branch `stage2-language-voice` and are **not deployed**.

| # | Report | Verdict | Cause | Fix |
|---|---|---|---|---|
| 1 | Number Land intro sounds like "Ah, let's count…" | **Not reproduced.** The clip is fine and plays whole in the app | Most likely the clip streamed on a slow network and its start was lost (see 6) | Worker fix in 6. Clip now preloaded on the home screen |
| 2 | Number 1 is glitchy, says "One apples" | **Confirmed in the clip file** | The current Isabella clips are garbled. Whisper hears "One apple!" as "One apples", "Six!" as "Zikzha", "Eight!" as "later", "Two!" as "Tooth" | New voice (Aoede set-up) plus a listening check (below). **Fixed once the clips are regenerated** |
| 3 | Number 2 stutters, "Two is… one, two hey… two ducks" | **Confirmed in the clip file** | Same: "One, two!" is heard as "1's 2, eh?" and "Two ducks!" as "To you, Duxley" | Same as 2 |
| 4 | Number 4 cut before "bananas"; World Land welcome cut after "Welcome to World Land. L…" | **Not reproduced.** Every line plays to its end, in order | Most likely network streaming: the clip stalls or is replaced while it loads | Worker fix in 6 |
| 5 | Count It! speaker plays "Welcome to Number Land", question not read | **Not reproduced.** The intro then the question play; the speaker reads "How many bananas can you count?" | The code is correct (`say(O.ask)`). On the phone a late, still-loading intro clip probably played over it | Worker fix in 6 |
| 6 | Tap-to-voice about 1 s, about 2 s entering World Land | **Reproduced** on a throttled phone (200 KB/s, 400 ms round trips): quick World Land entry 1,958 ms, Number Land 713 ms | The offline worker only took charge after its *whole* 55 MB download. On a slow phone that never finished, so every clip streamed from the internet. This probably also explains the earlier "offline link doesn't work" | See below |

## Fix for 6 (and most likely 1, 4 and 5)
- `tools/sw.template.js` and `tools/build_sw.py`: the worker now installs with only the app shell (225 files, 4.4 MB) and takes charge straight away. The rest (2,142 files, 55.4 MB) then downloads in the background, pausing when a newer version is installing. When it is all saved, it tells the page.
- `index.html`: the page reminds the worker to keep downloading, so a phone that was closed early picks up where it stopped.
- `world.js`: the home screen now saves the land intros, place intros and Count It! questions first. Before the worker is in charge, it also decodes the land intros into memory.

- Found while testing (second fix, same issue): the new shell-first install re-downloaded the pictures and fonts the
  page had *just* loaded, so on a first visit it used up the phone's bandwidth and the first card taps streamed
  (test_quick_tap failed at 170-190 ms). The worker now takes the browser's own copy of a shell file when its bytes are
  exactly this build's (SHA-256 checked, else it downloads fresh), steps aside for 6 s after every tap, and starts the
  big background download only after a quiet moment once it takes over. Saves ~4 MB of data on a first visit too.
- The home screen's own download of the land intros (first visit only) now counts as a warm-up: a tapped line that is
  not on the phone yet cancels it, and it re-queues.

**Results, slow phone, second visit, quick child (taps World Land 1 s after the title):**

| | Before | After |
|---|---|---|
| Worker in charge | not after 120 s | after 52 s |
| World Land voice starts | 1,958 ms | 185 ms |
| Number Land voice starts | 713 ms | 96 ms |
| Number card taps | – | 51–66 ms |

First visit on a slow phone, child taps Number Land 3 s after the title: 811 ms without the home-screen download of the
land intros, 94-99 ms with it. A tap in the very first second of the very first visit is still limited by the network
(about 2–3.6 s) because nothing is on the phone yet.

## Fix for 2 and 3: the voice listens to its own short lines
- `tools/voice_check.py` and `tools/gen_voice.py` (`verifyShort: 3` in locales.json): every line of 3 words or fewer is checked by Whisper while it is generated.
- If Whisper doesn't hear the written words, it records another take: a full stop instead of "!", no end mark, a touch faster, then a touch slower. Anything that still fails is listed for a person to hear.
- With the proposed Aoede set-up, all 33 Number Land lines (One… Ten, "One apple!", "Two ducks!", "Four bananas!"…) passed. "Six!" needed its no-end-mark take.

## Tests
- `tools/test_land_voice.py` is new and part of `tools/run_tests.py`, run with 400 ms round trips. It checks:
  - the worker takes charge after the first visit on a slow phone
  - the quick-child second visit
  - the Number Land intro
  - cards 1, 2 and 4 play all their lines, none cut
  - Count It! plays the intro then the question, and the speaker button reads the question
  - the World Land intro
  - no page errors
  - voice-start time
- The old code fails it ("service worker in charge after 120.0 s"). The new code passes.
- The short-line listening check runs every time clips are generated; `tools/test_voice_check.py` (in `run_tests --quick`) guards its re-take plan.
- Full suite after all fixes: 16/16 suites passed (15 Nov 2026, 23:5x Dubai).
- **Please ask Emmanuel to retest issues 1, 4 and 5 on his phone after this is deployed.** They did not show up in Chrome, and my best explanation is the worker problem, but only his phone can confirm it.
