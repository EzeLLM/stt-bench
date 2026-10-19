#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/stt-lab-uv-cache}"
export npm_config_cache="${npm_config_cache:-/tmp/stt-lab-npm-cache}"
command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
uv sync --frozen
npm --prefix apps/web ci --no-audit --no-fund
npm --prefix apps/web run build
if [[ "${1:-}" == "--reference" || "${1:-}" == "--all-references" ]]; then
  uv venv .venv-reference --allow-existing
  if [[ "$(uname -s)" == "Linux" ]]; then
    uv pip install --python .venv-reference/bin/python 'torch==2.8.0' --index-url https://download.pytorch.org/whl/cpu
    uv pip install --python .venv-reference/bin/python -r requirements/whisper-reference-linux.lock
  else
    uv pip install --python .venv-reference/bin/python 'torch==2.8.0'
  fi
  if [[ "$(uname -s)" != "Linux" ]]; then
    uv pip install --python .venv-reference/bin/python -r requirements/whisper-reference.txt
  fi
  uv pip install --python .venv-reference/bin/python --no-deps --editable .
  .venv/bin/python scripts/install_whisper.py
fi
if [[ "${1:-}" == "--all-references" ]]; then
  if [[ "$(uname -s)" != "Linux" ]]; then
    echo "All-reference locked environments are validated for Linux only; see docs/models.md for Mac validation."
    exit 1
  fi
  for profile in qwen parakeet; do
    uv venv ".venv-$profile" --allow-existing
    uv pip install --python ".venv-$profile/bin/python" 'torch==2.8.0' 'torchaudio==2.8.0' --index-url https://download.pytorch.org/whl/cpu
    if [[ "$profile" == "qwen" ]]; then
      uv pip install --python .venv-qwen/bin/python 'torchvision==0.23.0' --index-url https://download.pytorch.org/whl/cpu
    fi
    uv pip install --python ".venv-$profile/bin/python" -r "requirements/$profile-reference-linux.lock"
    uv pip install --python ".venv-$profile/bin/python" --no-deps --editable .
  done
  .venv/bin/python scripts/install_additional_references.py
fi
.venv/bin/pytest -q
if [[ -x /usr/bin/chromium ]]; then
  npm --prefix apps/web test
fi
