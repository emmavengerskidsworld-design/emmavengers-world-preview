# English voice choice (Stage 2)

Owner's request: use the clear female French voice (Kokoro `ff_siwis`, speed 0.8, pitch 1.1) for English across the
app; if it does not read English well, use the most similar clear female English voice.

## Method (objective, repeatable: `tools/voice_eval/`)
1. **Word error rate (WER)**: each voice speaks the same English lines; an English speech recogniser
   (faster-whisper `base.en` and `small.en`, CPU int8, greedy) writes down what it hears; WER = words it got wrong
   / words in the line. A lower WER means more words a listener catches the first time. `base.en` is a deliberately
   weaker "listener" (more sensitive to unclear speech), `small.en` a stronger one.
   - 5 Cameroon/app lines (`wer.py`, samples in /workspace/voice-samples/)
   - 40 real app lines picked at random from `check_voice.py --all` (`big.py`, `lines40.json`)
2. **Similarity to the French voice**: Kokoro style-vector cosine to `ff_siwis` and median pitch (F0) of the
   samples (`sim.py`).

## Results
40 real app lines (main test):

| Voice (speed / pitch) | WER base.en | WER small.en |
|---|---|---|
| ff_siwis French voice reading English (0.8 / 1.1) | 15.7% | 12.4% |
| af_heart, old "Mia" (0.72 / 1.18) | 34.2%* | 7.7% |
| **bf_isabella (0.85 / 1.05)** | **5.4%** | **3.3%** |
| bf_isabella (0.85 / 1.10) | 7.7% | 4.4% |
| bf_emma (0.85 / 1.10) | 7.5% | 10.5% |
| af_sarah (0.85 / 1.10) | 51.1%* | 4.7% |
| af_aoede (0.85 / 1.10) | 7.3% | 3.7% |

\* includes recogniser "loops" on long Bible lines; still a sign of a less clear voice.

5 short lines: ff_siwis + English phonemes 17.5% / 31.8% ("Cameroon" heard as "The G", "We're in Cameroon" as "R I"),
ff_siwis + French phonemes 73.2% / 55.0%, bf_isabella 0% / 0%, old Mia 11.4% / 1.7%.

Similarity: median pitch ff_siwis 211 Hz (natural) / 231 Hz (pitch 1.1); bf_isabella 219 Hz (closest of the
clear English voices); old Mia 231 Hz but heavily pitch-shifted (the main reason it sounded unclear).

## Decision
The French voice reads English with 3-4x more misheard words than the best English voices, so (per the owner's
fallback) the English voice is **`bf_isabella`, en-gb, speed 0.85, pitch 1.05**: lowest WER in both tests, closest
pitch to the French voice, a calm British accent (also familiar to children in English-speaking Cameroon and most
Commonwealth countries). The friend voice name "Mia" in Voice Settings is unchanged.

Settings: `content/src/locales.json` -> `en.voice` (also `tools/gen_voice.py` VOICES["mia"], `voice/voices.json`).
Samples for the owner: /workspace/stage2-shots/sample-french-voice-english.mp3, sample-chosen-english.mp3,
sample-old-english-mia.mp3 (same 5 lines).
