# Aoede clean-up: less breath (15 Nov 2026)

Emmanuel picked D3 (af_aoede plus the pronunciation dictionary) and said it is "clear and ok to use but still a little breathy".
Every sample here reads the same 5 lines: a Bible line (Isaac and Rebekah, Esau), an Ari line, the Yaoundé quiz,
"An Emmavengers World Story, by Cletus Emmanuel." and the Tchami line. All use fp32, speed 0.95, 48k MP3 and the dictionary.

| File | One line | Breath (air 8–12 kHz, lower = less) | Tone clean (HNR) | Crisp (CPPS) | Brightness | Word errors (80 lines: all / books / names) |
|---|---|---|---|---|---|---|
| D3-as-picked.mp3 | the voice he picked, untouched (comparison) | −26.1 dB | 16.8 | 6.2 | 469 Hz | 1.9% / 0.5% / 4.6% |
| E1-aoede-firm-eq.mp3 | pure Aoede, firmer EQ (lifts the 3 kHz voice, cuts the hiss above 6.5 kHz) and a de-esser | −26.6 dB | **17.4** | 6.2 | 444 Hz | 1.8% / 0.5% / 4.3% |
| **E2-aoede-blend-firm-eq.mp3** | **70% Aoede + 15% Kore + 15% Nova voice style, same firmer EQ (top pick)** | **−28.5 dB** | 17.3 | **6.4** | 455 Hz | **1.6% / 0.5% / 3.9%** |
| E3-aoede-nova-bright-eq.mp3 | 80% Aoede + 20% Nova, mild EQ, the brightest of the three | −27.7 dB | 16.8 | 6.2 | 492 Hz | 2.0% / 0.5% / 4.8% |

Old app voice for reference: 3.7% / 1.4% / 8.2% word errors.

## Top pick: E2
- About 2.4 dB less breath than D3 (roughly 40% less breath energy). It is the least airy of the three.
- Its tone is cleaner and crisper: HNR 16.8 → 17.3, CPPS 6.2 → 6.4.
- It has the fewest word errors of anything tested so far: 1.6%, with names down from 4.6% to 3.9%.
- It is still Aoede's voice. Kore and Nova only firm up the style, and the pitch drops slightly, from 182 to 175 Hz.

If he hears E2 as "less like D3", choose E1. E1 is pure Aoede with only the EQ, so it sounds almost the same but with a little less hiss.

## What did not help (measured)
- Denoise (afftdn) and a noise gate did almost nothing. The breath is part of how the voice is made, not background noise, so neither moved the numbers.
- Heavier blends (30% Kore) are crisper (CPPS 6.6), but they start to sound like a different person.
- Speed 1.0 instead of 0.95 made no difference to the breath.

## How it is applied (data, not code)
- The set-up is in `content/src/locales.json` → `en.voice.next`:
  - `blend` [[af_kore, .15], [af_nova, .15]]
  - `post` {highpass 100, presence 3 kHz +3 dB, air shelf 6.5 kHz −5 dB, de-ess 0.4}
  - `model` fp32, `bitrate` 48k, `verifyShort` 3
- `tools/gen_voice.py --locale en --next` renders it, using `tools/voice_post.py`.
- The app's voice is unchanged until all clips are regenerated. Then `next` moves up into `voice`.
- To pick E1 or E3 instead, change only those fields.
