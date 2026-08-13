#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-7861}"

cd "${PROJECT_ROOT}"
exec "${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/Gradio/app.py" --host "${HOST}" --port "${PORT}"
