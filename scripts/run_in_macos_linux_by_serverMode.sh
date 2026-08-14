#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)
VENV_PATH="${VENV_PATH:-.venv}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
PYTHON_IN_VENV="$PROJECT_ROOT/$VENV_PATH/bin/python"

if [ ! -x "$PYTHON_IN_VENV" ]; then
  echo "Python executable not found: $PYTHON_IN_VENV. Run scripts/app_setup.sh first." >&2
  exit 1
fi

cd "$PROJECT_ROOT"
exec "$PYTHON_IN_VENV" api.py --host "$HOST" --port "$PORT" "$@"
