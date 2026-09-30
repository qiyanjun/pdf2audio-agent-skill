"""synth.py with the real voice. Runs only where setup_tts.sh has installed it (not in CI:
the model is a 350 MB download)."""
import tempfile
import unittest
import wave
from pathlib import Path

from helpers import run_script, voice_python

PY = voice_python()


@unittest.skipUnless(PY, "Kokoro voice not installed (run skills/pdf2audio/scripts/setup_tts.sh)")
class SynthSmoke(unittest.TestCase):
    def test_narrates_then_skips_when_up_to_date(self):
        work = Path(tempfile.mkdtemp(prefix="pdf2audio-synth-"))
        (work / "script").mkdir()
        (work / "script" / "00-hello.txt").write_text("# Hello.\n\nThis is a short test sentence.\n")
        first = run_script("synth.py", work / "script", work / "wav", python=PY)
        self.assertEqual(first.returncode, 0, first.stderr)
        with wave.open(str(work / "wav" / "00-hello.wav")) as fh:
            self.assertGreater(fh.getnframes() / fh.getframerate(), 1.0)
        second = run_script("synth.py", work / "script", work / "wav", python=PY)
        self.assertIn("up to date, skipped", second.stdout)


if __name__ == "__main__":
    unittest.main()
