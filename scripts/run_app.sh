#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
MODE="${MODE:-client}"

case "$MODE" in
  local)
    exec sh "$SCRIPT_DIR/run_in_macos_linux_by_localMode.sh" "$@"
    ;;
  client)
    exec sh "$SCRIPT_DIR/run_in_macos_linux_by_clientMode.sh" "$@"
    ;;
  server)
    exec sh "$SCRIPT_DIR/run_in_macos_linux_by_serverMode.sh" "$@"
    ;;
  *)
    echo "Unsupported MODE: $MODE. Use MODE=local, MODE=client, or MODE=server." >&2
    exit 2
    ;;
esac
