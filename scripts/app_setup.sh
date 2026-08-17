#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)

MODE="${MODE:-full}"
VENV_PATH="${VENV_PATH:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
WITH_TRAINING="${WITH_TRAINING:-0}"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-}"
CPU_ONLY="${CPU_ONLY:-0}"

VENV_ROOT="$PROJECT_ROOT/$VENV_PATH"
PYTHON_IN_VENV="$VENV_ROOT/bin/python"

if [ ! -d "$VENV_ROOT" ]; then
  "$PYTHON_BIN" -m venv "$VENV_ROOT"
fi

if [ ! -x "$PYTHON_IN_VENV" ]; then
  echo "Python executable not found: $PYTHON_IN_VENV" >&2
  exit 1
fi

cd "$PROJECT_ROOT"
"$PYTHON_IN_VENV" -m pip install --upgrade pip

REQUIREMENTS="requirements-api.txt"
UNAME="$(uname -s 2>/dev/null || echo unknown)"
case "$UNAME" in
  MINGW*|MSYS*|CYGWIN*)
    if [ "$MODE" != "server" ] && [ "$CPU_ONLY" != "1" ]; then
      REQUIREMENTS="requirements.txt"
    fi
    ;;
esac
"$PYTHON_IN_VENV" -m pip install -r "$REQUIREMENTS"

if [ "$WITH_TRAINING" = "1" ]; then
  if [ -n "$TORCH_INDEX_URL" ]; then
    "$PYTHON_IN_VENV" -m pip install torch torchvision torchaudio --index-url "$TORCH_INDEX_URL"
  else
    "$PYTHON_IN_VENV" -m pip install torch torchvision torchaudio
  fi
  "$PYTHON_IN_VENV" -m pip install -r requirements-train.txt
fi

echo ""
echo "Environment ready: $VENV_ROOT"
echo "Unified macOS/Linux launcher:"
echo "  MODE=client sh scripts/run_app.sh"
echo "  MODE=local sh scripts/run_app.sh"
echo "  MODE=server sh scripts/run_app.sh"
echo ""
echo "macOS/Linux local:  scripts/run_in_macos_linux_by_localMode.sh  # API + static WebUI"
echo "macOS/Linux client: scripts/run_in_macos_linux_by_clientMode.sh"
echo "macOS/Linux server: scripts/run_in_macos_linux_by_serverMode.sh"
echo "NAS Docker WebUI: Python API serves the static frontend directly"
echo "NAS deploy: HOST_NAME=<ip> PASSWORD=<password> sh scripts/deploy_nas.sh"
