#!/usr/bin/env bash
# Install the local Kokoro voice used by synth.py and lint_script.py. Safe to rerun.
set -euo pipefail

HOME_DIR="${PDF2AUDIO_HOME:-$HOME/.cache/pdf2audio}"
RELEASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"

for tool in pdftotext ffmpeg python3; do
  command -v "$tool" >/dev/null || { echo "Missing '$tool'. On macOS: brew install poppler ffmpeg" >&2; exit 1; }
done

mkdir -p "$HOME_DIR"
cd "$HOME_DIR"

[ -x venv/bin/python ] || python3 -m venv venv
venv/bin/python -c "import kokoro_onnx, soundfile" 2>/dev/null || venv/bin/pip -q install kokoro-onnx soundfile

for f in kokoro-v1.0.onnx voices-v1.0.bin; do
  [ -s "$f" ] || { echo "Downloading $f ..."; curl -L --fail --progress-bar -o "$f.part" "$RELEASE/$f" && mv "$f.part" "$f"; }
done

# espeak-ng ignores long data paths, and the phonemizer resolves symlinks, so keep a real copy
# at a short path instead of pointing into site-packages.
if [ ! -f espeak-ng-data/phontab ]; then
  rm -rf espeak-ng-data
  cp -R "$(venv/bin/python -c 'import espeakng_loader; print(espeakng_loader.get_data_path())')" espeak-ng-data
fi
if [ "${#HOME_DIR}" -gt 120 ]; then
  echo "Warning: $HOME_DIR is a long path; if narration fails with a 'phontab' error, set PDF2AUDIO_HOME to a shorter one." >&2
fi

PDF2AUDIO_HOME="$HOME_DIR" venv/bin/python - "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tts_common
print("Voice check:", tts_common.load().tokenizer.phonemize("ready to narrate", "en-us"))
EOF
echo "Ready. Run speaking scripts with: $HOME_DIR/venv/bin/python"
