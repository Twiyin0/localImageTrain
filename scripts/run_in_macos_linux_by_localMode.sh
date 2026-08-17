#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)
VENV_PATH="${VENV_PATH:-.venv}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-7861}"
PYTHON_IN_VENV="$PROJECT_ROOT/$VENV_PATH/bin/python"

LOCAL_NO_PROXY="localhost,127.0.0.1,0.0.0.0"
NO_PROXY="${NO_PROXY:+$NO_PROXY,}$LOCAL_NO_PROXY"
no_proxy="${no_proxy:+$no_proxy,}$LOCAL_NO_PROXY"
export NO_PROXY no_proxy

if [ ! -x "$PYTHON_IN_VENV" ]; then
  echo "Python executable not found: $PYTHON_IN_VENV. Run scripts/app_setup.sh first." >&2
  exit 1
fi

cd "$PROJECT_ROOT"
exec "$PYTHON_IN_VENV" api.py --host "$HOST" --port "$PORT" "$@"
