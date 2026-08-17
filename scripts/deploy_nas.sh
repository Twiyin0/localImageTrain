#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)
VENV_PATH="${VENV_PATH:-.venv}"
PYTHON_IN_VENV="$PROJECT_ROOT/$VENV_PATH/bin/python"

HOST_NAME="${HOST_NAME:-}"
SSH_PORT="${SSH_PORT:-22}"
USERNAME="${USERNAME:-root}"
PASSWORD="${PASSWORD:-}"
REMOTE_DIR="${REMOTE_DIR:-/opt/python/huggingface/localImageTrain}"
LOCAL_DIR="${LOCAL_DIR:-.}"
NO_UPLOAD="${NO_UPLOAD:-0}"

if [ -z "$HOST_NAME" ]; then
  echo "HOST_NAME is required, for example: HOST_NAME=10.10.1.9 sh scripts/deploy_nas.sh" >&2
  exit 2
fi
if [ -z "$PASSWORD" ]; then
  echo "PASSWORD is required." >&2
  exit 2
fi
if [ ! -x "$PYTHON_IN_VENV" ]; then
  echo "Python executable not found: $PYTHON_IN_VENV. Run scripts/app_setup.sh first." >&2
  exit 1
fi

set -- deploy_nas.py \
  --host "$HOST_NAME" \
  --port "$SSH_PORT" \
  --username "$USERNAME" \
  --password "$PASSWORD" \
  --remote-dir "$REMOTE_DIR" \
  --local-dir "$LOCAL_DIR"

if [ "$NO_UPLOAD" = "1" ]; then
  set -- "$@" --no-upload
fi

cd "$PROJECT_ROOT"
exec "$PYTHON_IN_VENV" "$@"
