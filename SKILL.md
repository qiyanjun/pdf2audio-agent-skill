---
name: pdf2audio
description: Turn a PDF (paper, grant proposal, report, book chapter, lecture notes) into audio that is pleasant to listen to - a narration script rewritten for the ear, then a natural neural voice that runs locally, packaged as MP3 plus a chaptered M4B audiobook. Use this whenever the user wants to listen to a document instead of reading it - "convert this PDF to audio", "make an audiobook/podcast of my paper", "read this proposal to me", "I want to listen to this on my commute", "text to speech for this PDF" - even if they only say "audio" or "mp3". Do not use it for video voiceovers, for transcribing audio to text, or for a two-host podcast-style discussion of a document.
---

# pdf2audio

A PDF read aloud verbatim is unlistenable: citation numbers, page numbers, table cells read
row-by-row in scrambled order, figure labels, a reference list, acronyms pronounced as words.
The value of this skill is the middle step - rewriting the extracted text into a **narration
script** - not the text-to-speech call. Expect to spend most of the effort there.

The pipeline:

```
PDF --pdftotext--> raw.txt --(you write narration.json)--> build_script.py --> script/*.txt
     --> lint_script.py (fix, rebuild) --> synth.py --> wav/*.wav --> assemble.py --> MP3 + M4B
```

Everything runs on the user's machine. Documents people want narrated are often unpublished
(drafts, proposals, manuscripts under review), so do not send the text to a cloud TTS service
unless the user asks for one, even if API keys are present in the environment.

## 0. Setup (once per machine)

```bash
bash scripts/setup_tts.sh
```

Installs the Kokoro neural voice (about 350 MB) into `~/.cache/pdf2audio` (override with
`PDF2AUDIO_HOME`) and checks for `pdftotext` and `ffmpeg`. It is idempotent; rerun it freely.
Scripts that speak (`synth.py`, and `lint_script.py` for phonemes) must be run with the
interpreter it prints: `~/.cache/pdf2audio/venv/bin/python`.

## 1. Extract and read the whole text

```bash
pdftotext input.pdf work/raw.txt
```

Use a scratch directory for `work/`. Read `raw.txt` end to end with line numbers, not just the
first page: the decisions below depend on where the floats, headings, and back matter are.
If the text comes out empty or garbled the PDF is scanned; OCR it first (see the `pdf` skill).
For two-column layouts check that columns were not interleaved; if they were, try
`pdftotext -layout` or per-column cropping (`-x -y -W -H`).

## 2. Write `narration.json`

This config tells `build_script.py` how to turn `raw.txt` into chapters. Start from
`assets/narration.example.json`. Read `references/narration-guide.md` first: it explains each
field and the judgment calls (what to drop, how to speak a table, what to do with acronyms).

In short, you decide:

- **`drop_lines`** - line ranges to delete: page numbers, running headers, the scrambled text
  of figures and tables *including their captions*, the reference list.
- **`chapter_headings` / `section_headings`** - regexes for heading lines. Chapters become
  separate audio files and audiobook chapter marks.
- **`paragraph_starts`** - run-in heads ("Preliminary.", "Success criterion:") that should
  begin a new paragraph, so the listener hears a pause.
- **`inserts`** - prose you write to stand in for each figure and table, placed after a named
  anchor sentence. A float usually interrupts a sentence in the raw text, which is why captions
  are dropped and re-inserted at a paragraph boundary rather than left where they fall.
- **`substitutions`** - regex rewrites for the ear: acronyms, model names, dates, award
  numbers, symbols, and words that lost their hyphen at a line break.

Stay faithful. The listener wants *this document*, so rewrite only what cannot be spoken;
do not summarize or editorialize the body text. If the user wants a digest instead, that is a
different request - ask.

## 3. Build and lint, then iterate

```bash
python3 scripts/build_script.py work/raw.txt work/narration.json work/script
~/.cache/pdf2audio/venv/bin/python scripts/lint_script.py work/script
```

`build_script.py` prints words and estimated minutes per chapter. `lint_script.py` reports:
characters a voice would skip or misread, stray numbers that look like leaked page numbers,
words that look like two words fused by a lost hyphen, and every acronym, respelling, spaced
letter run and mid-sentence "A" with the phonemes the voice produces *in that sentence*. Read
the phonemes: that is how you catch "LLMs" losing its plural or "case A" becoming "case uh"
without being able to hear the audio. Try a respelling first with `--words "Sigh-Dack, Chee"`.
Fix the config, rebuild, relint. Then read the script as prose, at least the first two
chapters and both sides of every dropped range. Lint cannot tell you a caption landed
mid-sentence.

## 4. Narrate

```bash
~/.cache/pdf2audio/venv/bin/python scripts/synth.py work/script work/wav --voice af_heart
```

Roughly 10x faster than real time on Apple silicon (an hour of audio in about six minutes), so
run it in the background for long documents. Chapters whose WAV is newer than their text are
skipped, so after a script fix only the changed chapters are re-narrated.
Voices: `af_heart` (default, warm US female), `af_bella`, `am_michael`, `am_adam` (US male),
`bf_emma`, `bm_george` (British; add `--lang en-gb`). `--speed 1.1` for a brisker read.

## 5. Package and deliver

```bash
python3 scripts/assemble.py work/wav work/script "<pdf-folder>/<pdf-name>-audio" --title "Document title"
```

Writes, next to the PDF unless the user names another place:

```
<pdf-name>-audio/
  <pdf-name>.mp3        whole document
  <pdf-name>.m4b        audiobook with chapter marks (Apple Books, most podcast apps)
  chapters/NN-*.mp3     one file per chapter
  script/NN-*.txt       the narration text, so the user can see what was changed
```

Copy `narration.json` into that folder too; it is what makes a re-run after the PDF changes
cheap. Tell the user the total length, what was dropped (references, citation markers), what
was rewritten as prose (tables, figures), and any pronunciations you were unsure about.
Be plain that you could not hear the result: you checked phonemes and durations, not sound.

## Several PDFs at once

Writing the config is the slow, judgment-heavy step. Documents are independent, so when there
are several, hand each one to a parallel agent. Give each agent this skill's path, its PDF, a
work directory, and a finished `narration.json` from a similar document as a style model. Have
them stop after step 3 and report chapters, drops, inserts, and uncertain pronunciations. Then
narrate the documents one after another, not concurrently: each narration already uses all
CPU cores, so running them in parallel is no faster.

Run all the narrations as **one** sequential background command with a long timeout, not as one
background job per document waiting on a lock. Queued jobs count their waiting time against the
background time limit and get killed partway through. If a run is interrupted anyway, just run
it again: `synth.py` skips chapters that are already done.

## Troubleshooting

- **`Error processing file '.../espeak-ng-data/phontab'` and the process exits** - the
  phonemizer ignores long data paths and falls back to a build-time path that does not exist.
  `setup_tts.sh` avoids this by copying the data to a short path; if `PDF2AUDIO_HOME` is deeply
  nested, move it somewhere shorter. A symlink does not help (the path is resolved first).
- **`build_script.py` says an insert anchor was not found** - anchors match the raw paragraph
  text before substitutions, within one paragraph. Use a short, distinctive phrase that does
  not span a dropped range.
- **Model download fails** - the two files come from the `kokoro-onnx` GitHub releases; retry,
  or place `kokoro-v1.0.onnx` and `voices-v1.0.bin` in `PDF2AUDIO_HOME` by hand.
