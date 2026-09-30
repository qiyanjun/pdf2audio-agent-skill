"""assemble.py: chapter WAVs -> full MP3 + chaptered M4B (needs ffmpeg and ffprobe)."""
import json
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

from helpers import run_script

SR = 24000


def silent_wav(path, seconds):
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(SR)
        fh.writeframes(b"\0\0" * int(SR * seconds))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe not installed")
class Assemble(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        work = Path(tempfile.mkdtemp(prefix="pdf2audio-asm-"))
        (work / "wav").mkdir()
        (work / "script").mkdir()
        for stem, title, secs in [("00-intro", "Intro: the idea", 1.0), ("01-method", "Method; with = signs", 1.5)]:
            silent_wav(work / "wav" / f"{stem}.wav", secs)
            (work / "script" / f"{stem}.txt").write_text(f"# {title}.\n\nBody.\n")
        cls.out = work / "paper-audio"
        cls.proc = run_script("assemble.py", work / "wav", work / "script", cls.out, "--title", "Test Paper")

    def probe(self, path):
        res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:format_tags=title",
                              "-show_chapters", "-of", "json", str(path)], capture_output=True, text=True)
        return json.loads(res.stdout)

    def test_outputs_exist(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        for rel in ["paper.mp3", "paper.m4b", "chapters/00-intro.mp3", "chapters/01-method.mp3",
                    "script/00-intro.txt"]:
            self.assertTrue((self.out / rel).exists(), rel)

    def test_m4b_chapters_titles_and_length(self):
        info = self.probe(self.out / "paper.m4b")
        titles = [c["tags"]["title"] for c in info["chapters"]]
        self.assertEqual(titles, ["Intro: the idea", "Method; with = signs"])  # escaping survives
        self.assertAlmostEqual(float(info["format"]["duration"]), 2.5, delta=0.15)
        self.assertEqual(info["format"]["tags"]["title"], "Test Paper")

    def test_full_mp3_length(self):
        self.assertAlmostEqual(float(self.probe(self.out / "paper.mp3")["format"]["duration"]), 2.5, delta=0.15)

    def test_wav_without_script_is_rejected(self):
        work = Path(tempfile.mkdtemp(prefix="pdf2audio-asm-"))
        (work / "wav").mkdir()
        (work / "script").mkdir()
        silent_wav(work / "wav" / "00-orphan.wav", 0.2)
        proc = run_script("assemble.py", work / "wav", work / "script", work / "out")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("00-orphan", proc.stderr)


if __name__ == "__main__":
    unittest.main()
