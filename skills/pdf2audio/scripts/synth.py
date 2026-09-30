#!/usr/bin/env python3
"""Narrate a script directory into one WAV per chapter with the local Kokoro voice.

    ~/.cache/pdf2audio/venv/bin/python synth.py script_dir wav_dir [--voice af_heart] [--speed 1.0]

A chapter is skipped when its WAV is newer than its text, so fixing one chapter re-narrates
only that chapter. A different voice or speed needs --force.
"""
import argparse
import re
import time
from pathlib import Path

import numpy as np
import soundfile as sf

import tts_common

SR = tts_common.SAMPLE_RATE
# Pauses in seconds. The voice already trails off at sentence ends; these add the breathing room
# that tells a listener a paragraph or heading has ended.
PAUSE_CHUNK, PAUSE_PARAGRAPH, PAUSE_HEADING = 0.22, 0.65, 1.0


def silence(seconds):
    return np.zeros(int(SR * seconds), dtype=np.float32)


def chunks(paragraph, limit=320):
    """Group sentences into pieces short enough for the voice to keep steady prosody."""
    current = ""
    for sentence in re.split(r"(?<=[.?!”\"])\s+(?=[A-Z“\"(])", paragraph):
        if current and len(current) + len(sentence) + 1 > limit:
            yield current
            current = sentence
        else:
            current = (current + " " + sentence).strip()
    if current:
        yield current


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("script_dir")
    ap.add_argument("wav_dir")
    ap.add_argument("--voice", default="af_heart")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--lang", default="en-us", help="en-us or en-gb")
    ap.add_argument("--force", action="store_true", help="re-narrate chapters that are up to date")
    args = ap.parse_args()

    out_dir = Path(args.wav_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(Path(args.script_dir).glob("*.txt"))
    stems = {f.stem for f in files}
    for stale in out_dir.glob("*.wav"):
        if stale.stem not in stems:
            stale.unlink()

    voice = tts_common.load()
    for f in files:
        out = out_dir / (f.stem + ".wav")
        if out.exists() and out.stat().st_mtime > f.stat().st_mtime and not args.force:
            print(f"{out.name}: up to date, skipped", flush=True)
            continue
        started = time.time()
        audio = [silence(0.5)]
        for para in filter(None, (p.strip() for p in f.read_text().split("\n\n"))):
            is_heading = para.startswith("#")
            for piece in chunks(para.lstrip("# ")):
                samples, sr = voice.create(piece, voice=args.voice, speed=args.speed, lang=args.lang)
                assert sr == SR, sr
                audio += [samples.astype(np.float32), silence(PAUSE_CHUNK)]
            audio.append(silence(PAUSE_HEADING if is_heading else PAUSE_PARAGRAPH))
        samples = np.concatenate(audio)
        sf.write(out, samples, SR, subtype="PCM_16")
        print(f"{out.name}: {len(samples) / SR / 60:.1f} min of audio in {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
