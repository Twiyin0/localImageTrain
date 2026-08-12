#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_VERSION="${PYTHON_VERSION:-3.11.15}"
PYTHON_SHA256="${PYTHON_SHA256:-272179ddd9a2e41a0fc8e42e33dfbdca0b3711aa5abf372d3f2d51543d09b625}"
INSTALL_ROOT="${PROJECT_ROOT}/.local/python-${PYTHON_VERSION}"
BUILD_ROOT="${PROJECT_ROOT}/.tmp/python-build-${PYTHON_VERSION}"
ARCHIVE_NAME="Python-${PYTHON_VERSION}.tar.xz"
ARCHIVE_PATH="${PROJECT_ROOT}/.tmp/${ARCHIVE_NAME}"
SOURCE_DIR="${BUILD_ROOT}/Python-${PYTHON_VERSION}"
OPENSSL_PREFIX="${OPENSSL_PREFIX:-/opt/homebrew/opt/openssl@3}"
READLINE_PREFIX="${READLINE_PREFIX:-/opt/homebrew/opt/readline}"
SQLITE_PREFIX="${SQLITE_PREFIX:-/opt/homebrew/opt/sqlite}"
XZ_PREFIX="${XZ_PREFIX:-/opt/homebrew/opt/xz}"
ZLIB_PREFIX="${ZLIB_PREFIX:-/opt/homebrew/opt/zlib}"

mkdir -p "${PROJECT_ROOT}/.tmp"
export COPYFILE_DISABLE=1
export COPY_EXTENDED_ATTRIBUTES_DISABLE=1

if [[ -x "${INSTALL_ROOT}/bin/python3.11" ]]; then
  "${INSTALL_ROOT}/bin/python3.11" --version
  exit 0
fi

if [[ ! -f "${ARCHIVE_PATH}" ]]; then
  curl -L "https://www.python.org/ftp/python/${PYTHON_VERSION}/${ARCHIVE_NAME}" -o "${ARCHIVE_PATH}"
fi

echo "${PYTHON_SHA256}  ${ARCHIVE_PATH}" | shasum -a 256 -c -

rm -rf "${BUILD_ROOT}"
mkdir -p "${BUILD_ROOT}"
tar -xJf "${ARCHIVE_PATH}" -C "${BUILD_ROOT}"

cd "${SOURCE_DIR}"
find . -name '._*' -delete
python3 - <<'PY'
from pathlib import Path

path = Path("Tools/scripts/generate_global_objects.py")
text = path.read_text(encoding="utf-8")
needle = "                if not name.endswith(('.c', '.h')):\n                    continue\n                yield os.path.join(dirname, name)\n"
replacement = (
    "                if name.startswith('._'):\n"
    "                    continue\n"
    "                if not name.endswith(('.c', '.h')):\n"
    "                    continue\n"
    "                yield os.path.join(dirname, name)\n"
)
if needle not in text:
    raise SystemExit("Failed to patch generate_global_objects.py")
path.write_text(text.replace(needle, replacement), encoding="utf-8")
PY

CONFIGURE_ARGS=(
  "--prefix=${INSTALL_ROOT}"
  "--with-openssl=${OPENSSL_PREFIX}"
)

CPPFLAGS_PARTS=("-I${OPENSSL_PREFIX}/include")
LDFLAGS_PARTS=("-L${OPENSSL_PREFIX}/lib")
PKG_CONFIG_PARTS=("${OPENSSL_PREFIX}/lib/pkgconfig")

for prefix in "${READLINE_PREFIX}" "${SQLITE_PREFIX}" "${XZ_PREFIX}" "${ZLIB_PREFIX}"; do
  if [[ -d "${prefix}" ]]; then
    CPPFLAGS_PARTS+=("-I${prefix}/include")
    LDFLAGS_PARTS+=("-L${prefix}/lib")
    PKG_CONFIG_PARTS+=("${prefix}/lib/pkgconfig")
  fi
done

export CPPFLAGS="${CPPFLAGS_PARTS[*]}"
export LDFLAGS="${LDFLAGS_PARTS[*]}"
export PKG_CONFIG_PATH="$(IFS=:; echo "${PKG_CONFIG_PARTS[*]}")"

./configure \
  "${CONFIGURE_ARGS[@]}"
make -j"$(sysctl -n hw.ncpu)"
make install
find "${INSTALL_ROOT}" -name '._*' -delete

"${INSTALL_ROOT}/bin/python3.11" --version
