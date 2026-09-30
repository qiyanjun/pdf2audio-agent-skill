"""Shared paths and runners for the pdf2audio tests."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "pdf2audio"
SCRIPTS = SKILL / "scripts"


def run_script(name, *args, python=None):
    """Run one of the skill's scripts; return the CompletedProcess (never raises on failure)."""
    return subprocess.run([python or sys.executable, str(SCRIPTS / name), *map(str, args)],
                          capture_output=True, text=True)


def build(raw_lines, config, out_dir=None):
    """Run build_script.py on in-memory input. Returns (process, {file name: text})."""
    work = Path(tempfile.mkdtemp(prefix="pdf2audio-test-"))
    (work / "raw.txt").write_text("\n".join(raw_lines) + "\n")
    (work / "narration.json").write_text(json.dumps(config))
    out = Path(out_dir) if out_dir else work / "script"
    proc = run_script("build_script.py", work / "raw.txt", work / "narration.json", out)
    files = {p.name: p.read_text() for p in sorted(out.glob("*.txt"))} if out.exists() else {}
    return proc, files


def body(files):
    """All chapter text joined, for assertions that do not care which chapter holds it."""
    return "\n\n".join(files.values())


def paragraphs(text):
    return [p for p in text.split("\n\n") if p.strip()]


def voice_python():
    """The TTS interpreter if the voice is installed, else None."""
    home = Path(os.environ.get("PDF2AUDIO_HOME", Path.home() / ".cache" / "pdf2audio"))
    py = home / "venv" / "bin" / "python"
    needed = [py, home / "kokoro-v1.0.onnx", home / "voices-v1.0.bin", home / "espeak-ng-data"]
    return py if all(p.exists() for p in needed) else None
