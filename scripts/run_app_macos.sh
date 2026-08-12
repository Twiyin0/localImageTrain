#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-7860}"

exec "${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/app.py" --host "${HOST}" --port "${PORT}"
