# pdf2audio

An agent skill that turns a PDF into audio worth listening to. The agent rewrites the extracted
text into a narration script: citations removed, tables and figures described in prose,
acronyms respelled. A neural voice running locally then reads it, and the result is packaged as
MP3 and as a chaptered M4B audiobook. Nothing leaves the machine.

## Install

Copy or symlink this folder into a skills directory, for example:

```bash
ln -s "$PWD" ~/.claude/skills/pdf2audio
bash scripts/setup_tts.sh        # one time: voice model (~350 MB) into ~/.cache/pdf2audio
```

Requires `python3`, `pdftotext` (poppler), and `ffmpeg`. Then ask: "convert paper.pdf into
audio I can listen to".

## How it works

A PDF read aloud as-is is unlistenable: page numbers land mid-sentence, table cells come out in
scrambled order, citation numbers are read aloud, and acronyms are pronounced as words. So most
of the work is turning the extracted text into a script written for the ear. Only one step
needs judgment; the rest are scripts.

![pdf2audio pipeline: every stage is a deterministic script except narration.json, which the agent writes; lint loops back into it until the script is clean](docs/pdf2audio-schematic.png)

```
PDF → pdftotext → raw.txt → [narration.json] → build_script.py → script/*.txt
    → lint_script.py (fix, rebuild) → synth.py → wav/*.wav → assemble.py → .mp3 + .m4b
```

1. **Extract.** `pdftotext` dumps the text, one line per printed line.
2. **Write `narration.json`** (the judgment step, done by the agent). It reads the whole raw
   text, and the page images where a table's layout is ambiguous, and records its decisions:
   - which line ranges to drop: page numbers, figure and table bodies with their captions, the
     reference list;
   - where chapters, sections and paragraphs start, so the listener hears the structure;
   - *inserts*: prose that replaces each figure and table, with content tables walked through
     row by row in full sentences;
   - *substitutions* for the ear: acronyms, respelled names, dates, symbols, lost hyphens.

   The body text itself is never summarized or reworded.
3. **Build and lint.** `build_script.py` applies the config and writes one text file per
   chapter. It also applies a few fixes that are always right: Unicode normalization,
   citation removal, and respelling the letter "A" in acronyms so it isn't read as "uh".
   `lint_script.py` reports what the voice would stumble on: leftover symbols, leaked page
   numbers, fused words, and, for every acronym and respelling, the exact phonemes the voice
   will produce in that sentence. Because the agent cannot hear audio, these phonemes are how it
   checks pronunciation. It fixes the config and rebuilds until the script is clean.
4. **Narrate.** `synth.py` reads each chapter through the voice in sentence-sized pieces and
   adds pauses after paragraphs and headings. A chapter whose audio is newer than its text is
   skipped, so fixing one chapter re-narrates only that chapter.
5. **Package.** `assemble.py` writes per-chapter MP3s, one full MP3, and an `.m4b` with chapter
   marks. It also copies the script next to the audio, so the listener can check what was read.

**Several PDFs:** step 2 is independent per document, so the agent can hand each document to a
parallel sub-agent. Narration then runs as one sequential job, because each narration already
uses every CPU core.

## The voice: Kokoro

[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) is a small, open-weight text-to-speech
model:

- **Origin and size:** released around the turn of 2025 by hexgrad, with 82 million parameters.
- **Quality:** it ranked near the top of the public TTS Arena leaderboard at release, despite
  being far smaller than cloud voices.
- **License:** Apache 2.0, free to use, including commercially.
- **Architecture:** based on StyleTTS 2; it produces 24 kHz audio.

This skill runs it through [`kokoro-onnx`](https://github.com/thewh1teagle/kokoro-onnx), a port
that uses ONNX Runtime on the CPU, so no GPU or PyTorch is needed. The model
(`kokoro-v1.0.onnx`, 325 MB) and the voice pack (`voices-v1.0.bin`) live in
`~/.cache/pdf2audio`. On Apple silicon it runs about 10x faster than real time: an hour of audio
in about six minutes.

**Voices** are named by accent and gender: `af_heart` (default, **A**merican **f**emale),
`af_bella`, `am_michael`, `am_adam` (American male), and `bf_emma`, `bm_george` (British; use
`--lang en-gb`).

**Why pronunciation needs care.** Kokoro does not read letters directly. First a rule-based
tool, [espeak-ng](https://github.com/espeak-ng/espeak-ng), converts the text into phonemes, and
Kokoro then voices those phonemes. Most mispronunciations come from that first step, not from
the voice model:

- a lone "A" becomes "uh";
- "LLMs" loses its plural;
- "UVA" is said differently before a comma.

For the same reason, `lint_script.py` can show pronunciations as phonemes without anyone
listening: it asks espeak-ng for exactly what Kokoro will be told to say.

**Trade-offs versus cloud voices** (OpenAI, ElevenLabs):

- Kokoro is free, private and fast, and no text leaves the machine, which matters for
  unpublished drafts.
- It is somewhat flatter over a long listen and has no emotional range to direct.
- It cannot clone a voice.
- Its English is much stronger than its other languages.

## Layout

| Path | Purpose |
|---|---|
| `SKILL.md` | The workflow the agent follows. |
| `references/narration-guide.md` | Config fields and the rules for rewriting text for the ear. |
| `assets/narration.example.json` | Starting point for a document's config. |
| `scripts/setup_tts.sh` | Installs the Kokoro voice and checks dependencies. |
| `scripts/tts_common.py` | Locates and loads the installed voice (shared by the scripts that speak). |
| `scripts/build_script.py` | `raw.txt` + `narration.json` -> one text file per chapter. |
| `scripts/lint_script.py` | Flags symbols, leaked page numbers and fused words; shows phonemes in context. |
| `scripts/synth.py` | Script -> one WAV per chapter (incremental). |
| `scripts/assemble.py` | WAVs -> chapter MP3s, full MP3, chaptered M4B. |
| `docs/pdf2audio-schematic.png` | The pipeline diagram above; `.excalidraw` beside it is the editable source. |

## Manual use

```bash
V=~/.cache/pdf2audio/venv/bin/python
pdftotext paper.pdf work/raw.txt
# write work/narration.json (see assets/ and references/)
python3 scripts/build_script.py work/raw.txt work/narration.json work/script
$V scripts/lint_script.py work/script --words "Nersk, Sigh-Dack"   # --words: test respellings
$V scripts/synth.py work/script work/wav --voice af_heart
python3 scripts/assemble.py work/wav work/script paper-audio --title "Paper title"
```
