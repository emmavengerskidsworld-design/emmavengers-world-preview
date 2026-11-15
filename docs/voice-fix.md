# English voice fix: why it sounds heavy and breathy, and the choices (15 Nov 2026, Asia/Dubai)

Branch stage2-language-voice. The app's clips have NOT been changed.

## Causes found
1. **Muffled / "heavy" sound: the MP3 bitrate.** Clips are saved as 32 kbps MP3. At that bitrate the encoder throws away everything above about 6 kHz, which is the part of a voice that makes it clear and bright. Measured on the same sentence: the raw voice has a spectral centroid ("brightness") of about 1,120 Hz and energy up to about 10.4 kHz. The app clip has about 540–620 Hz, cut off at about 5.3–6.6 kHz, so roughly half the brightness is gone. At 40 kbps or more the full band survives (40k: 9.6 kHz, 48k: 10.3 kHz). This affects every clip, but long book pages show it most. Books use exactly the same pipeline and settings as everything else (gen_voice.py → voice/<hash>.mp3; build_sw.py only lists them), with no extra processing.
2. **Breathy, "out of breath" sound: mostly the voice itself, made worse by the compressed model.**
   - **bf_isabella** has a lot of breath noise. Measured on vowels: HNR (harmonics-to-noise; higher is cleaner) is about 15 dB and CPPS (the standard breathiness measure; higher is crisper) is only 4.0–4.8, among the lowest of all the Kokoro female voices. Raw Isabella also puts a large share of its energy above 8 kHz (about −12.6 dB), which is the "air". Kokoro's own quality grade for Isabella is only C.
   - **The int8 (compressed) Kokoro model** adds noise: CPPS was 3.5 with int8 and 4.8 with the full fp32 model, same voice and settings. It is also about 5× slower on this computer, which is why the last regeneration took about 15 hours.
   - **Pitch shift 1.05 (resample plus stretch) and speed 0.85:** these made almost no measurable difference to breathiness (CPPS 4.0 with the shift, 3.5 without, 4.6–4.8 at speeds 0.85–1.0) or to pitch (201 Hz against 198 Hz). They are unnecessary processing, so the new set-ups drop the pitch step and use speed 0.95.
3. **Mispronounced words: the phonemizer (espeak-ng) guesses names it doesn't know.** There was no pronunciation dictionary for whole words, only for letter sounds.

## Mispronounced words (current clips; Whisper float32 ASR plus phoneme check)
- **Places:** Yaoundé (said "yay-uh-ruhn-DAY"; heard as "yerende"/"day" 4–6×), Douala (heard "walla"/"diwala"), Cameroon (heard "ruins"/"maroon" 3–6×), Dja, Sangha, Diy-Gid-Biy (spelled out as letters), UNESCO ("un-ESS-co"), Northwest/Northeast (heard only "west"/"east").
- **People:** Tchami ("tee-CHAH-mee", heard "army"), Awa, Ari (heard "Henry" twice), Emmavengers ("emma-VENG-uhz" with no j sound, heard "Wenger's"), Cletus Emmanuel ("Collettus").
- **Bible:** Esau ("ESS-ow", heard "L"/"earth"), Canaan ("KAN-ahn"), Shinar, Sarai, Haran.
- **Food:** Ugali ("YOU-gali").

All of these are now fixed as DATA in `content/voice-lexicon/en.json` (19 words, British and American IPA). `tools/gen_voice.py` applies it automatically, so any future line with these words is said correctly. Adding a word is one line in that file, and only the clips containing it need regenerating. With the dictionary, the place/name lines' word errors fell from 6.0% to 4.6% (Aoede) and from 6.7% to 5.3% (Isabella). Most of what is left is spelling, for example "younday" or "camaroon", which means the word is now said right.

## Samples (same 5 real app lines: a Bible page, an Ari line, a quiz line, two tricky-name lines)
| File | What it is | Word errors (80 lines: all / books / names) | Breathiness (HNR↑ / CPPS↑ / air↓) | Pitch |
|---|---|---|---|---|
| A-current.mp3 | The app now: Isabella, int8, speed 0.85, pitch 1.05, 32k | 3.7% / 1.4% / 8.2% | 15.2 / 4.0 / −24.5 | 201 Hz |
| B-isabella-natural.mp3 | Isabella, clean model, speed 0.95, no pitch step, 48k (muffling fixed) | 2.9 / 0.9 / 6.7 | 15.0 / 4.6 / −26.2 | 201 |
| C1-heart-bright.mp3 | af_heart (Kokoro's top-graded voice, American) | 2.7 / 0.5 / 7.0 | 13.2 / 4.4 / −26.0 | 196 |
| C2-bella-bright.mp3 | af_bella, warm American (breathy: ruled out) | – | 15.3 / 3.4 / −21.6 | 201 |
| C3-emma-british.mp3 | bf_emma, British (breathy: ruled out) | – | 12.6 / 5.2 / −22.8 | 180 |
| C4-aoede-crisp.mp3 | af_aoede, American: cleanest tone, little breath | 2.4 / 0.5 / 6.0 | **16.8** / 6.2 / −26.0 | 180 |
| C5-jessica-light.mp3 | af_jessica, light and crisp, American | 2.8 / 0.5 / 7.2 | 13.6 / 6.6 / −26.5 | 207 |
| C6-alice-british-crisp.mp3 | bf_alice, light British, little air | 3.1 / 0.6 / 8.0 | 14.1 / 5.1 / −29.3 | 208 |
| C7-kore-firm.mp3 | af_kore, American: firmest/crispest, lower voice | 2.2 / 0.5 / 5.5 | 15.0 / **7.8** / −23.6 | 158 |
| D1-heart-fixed-words.mp3 | af_heart plus pronunciation dictionary | – | as C1 | 196 |
| D2-isabella-fixed-words.mp3 | Isabella (B) plus pronunciation dictionary | 2.4 / 0.9 / 5.3 | as B | 201 |
| **D3-aoede-fixed-words.mp3** | **af_aoede plus pronunciation dictionary (recommended)** | **1.9 / 0.5 / 4.6** | as C4 | 180 |

All B–D samples use the full fp32 model, speed 0.95, no pitch processing and 48 kbps MP3. Single-line clips are in `lines/`. ASR used Whisper small.en in float32 with beam 5; int8 Whisper produced garbage on this CPU and was discarded. Breathiness was measured with Praat (parselmouth) on the Bible, Ari and quiz lines before MP3 coding.

## Recommendation (Emmanuel's ear decides)
1. **D3: Aoede plus the dictionary.** It has the fewest word errors (1.9%), the cleanest tone of all 19 set-ups tested (HNR 16.8) and little breath noise. Caveats: an American accent instead of British, and a smoother, warmer tone. He should check it doesn't sound "heavy" to him.
2. **C7: Kore** (plus the dictionary once picked). It is the crispest and least breathy by CPPS (7.8), with 2.2% word errors even without the dictionary. Its pitch is lower (158 Hz), so it may sound more grown-up.
3. **D2: Isabella, fixed** (keeps today's British voice). The muffling and the word errors are fixed, but she is still the airiest. Choose this only if he wants to keep Isabella.

Whatever he picks, the bitrate (48k, or 40k to save data), the fp32 model, no pitch step and the dictionary apply to the whole pipeline. Voice, speed and bitrate are data in content/src/locales.json (`voice`, `speed`, `pitch`, plus new `model` and `bitrate` fields).

## Full regeneration time (after he picks)
The English clips are 1,923 files, about 84 minutes of speech. With the fp32 model (5× faster than int8 here), synthesis takes about **30–60 minutes**. Library rebuild, full tests, an ASR spot check and the preview deploy add about another hour, so **about 2 hours in total** instead of the earlier 15. Size: the English clips grow from about 20 MB to about 30 MB at 48k (about 25 MB at 40k). French clips have the same 32k muffling and int8 model, so they can be remade the same way in about 20–30 minutes if he wants.
