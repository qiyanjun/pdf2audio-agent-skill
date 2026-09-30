#!/usr/bin/env python3
"""Package narrated chapters as per-chapter MP3s, one full MP3, and a chaptered M4B audiobook.

    assemble.py wav_dir script_dir out_dir [--title "Document title"] [--name file-stem]

Chapter titles come from the first line of each script file. The narration text is copied to
out_dir/script so the listener can check what was read.
"""
import argparse
import shutil
import subprocess
import sys
import wave
from pathlib import Path


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("wav_dir")
    ap.add_argument("script_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--title", help="audiobook title (default: out_dir name)")
    ap.add_argument("--name", help="file stem for the full MP3/M4B (default: out_dir name without '-audio')")
    ap.add_argument("--bitrate", default="64k", help="mono speech; 64k is transparent for a 24 kHz voice")
    args = ap.parse_args()

    wav_dir, script_dir, out = Path(args.wav_dir).resolve(), Path(args.script_dir), Path(args.out_dir)
    wavs = sorted(wav_dir.glob("*.wav"))
    if not wavs:
        sys.exit(f"No WAV files in {wav_dir}")
    missing = [w.stem for w in wavs if not (script_dir / f"{w.stem}.txt").exists()]
    if missing:
        sys.exit("WAVs without a script file (stale?): " + ", ".join(missing))

    name = args.name or out.name.removesuffix("-audio")
    title = args.title or name
    (out / "chapters").mkdir(parents=True, exist_ok=True)
    shutil.rmtree(out / "script", ignore_errors=True)
    shutil.copytree(script_dir, out / "script")
    for old in (out / "chapters").glob("*.mp3"):
        old.unlink()

    meta = [";FFMETADATA1", f"title={title}", f"album={title}", "genre=Audiobook"]
    concat, position_ms = [], 0
    for w in wavs:
        chapter_title = (script_dir / f"{w.stem}.txt").read_text().split("\n")[0].lstrip("# ").rstrip(".")
        with wave.open(str(w)) as fh:
            length_ms = round(fh.getnframes() / fh.getframerate() * 1000)
        ffmpeg("-i", str(w), "-ac", "1", "-b:a", args.bitrate, "-metadata", f"title={chapter_title}",
               "-metadata", f"album={title}", str(out / "chapters" / f"{w.stem}.mp3"))
        escaped = chapter_title.replace("\\", "\\\\").replace("=", "\\=").replace(";", "\\;").replace("#", "\\#")
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={position_ms}", f"END={position_ms + length_ms}",
                 f"title={escaped}"]
        concat.append("file '" + str(w).replace("'", "'\\''") + "'")
        print(f"{position_ms // 60000:3d}:{position_ms // 1000 % 60:02d}  {chapter_title}")
        position_ms += length_ms

    list_file, meta_file = wav_dir / "concat.txt", wav_dir / "chapters.ffmeta"
    list_file.write_text("\n".join(concat) + "\n")
    meta_file.write_text("\n".join(meta) + "\n")
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(list_file), "-ac", "1", "-b:a", args.bitrate,
           "-metadata", f"title={title}", str(out / f"{name}.mp3"))
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(list_file), "-i", str(meta_file), "-map", "0:a",
           "-map_metadata", "1", "-map_chapters", "1", "-ac", "1", "-c:a", "aac", "-b:a", args.bitrate,
           "-f", "mp4", str(out / f"{name}.m4b"))
    print(f"Total {position_ms / 60000:.1f} min -> {out}")


if __name__ == "__main__":
    main()
