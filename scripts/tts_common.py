"""Locate and load the local Kokoro voice installed by setup_tts.sh."""
import os
import sys
from pathlib import Path

HOME = Path(os.environ.get("PDF2AUDIO_HOME", Path.home() / ".cache" / "pdf2audio"))
SAMPLE_RATE = 24000


def load():
    try:
        from kokoro_onnx import EspeakConfig, Kokoro
    except ImportError:
        sys.exit(f"kokoro-onnx is not importable. Run scripts/setup_tts.sh, then use {HOME}/venv/bin/python")
    model, voices, espeak = HOME / "kokoro-v1.0.onnx", HOME / "voices-v1.0.bin", HOME / "espeak-ng-data"
    missing = [str(p) for p in (model, voices, espeak) if not p.exists()]
    if missing:
        sys.exit("Missing voice files (run scripts/setup_tts.sh): " + ", ".join(missing))
    return Kokoro(str(model), str(voices), espeak_config=EspeakConfig(data_path=str(espeak)))
