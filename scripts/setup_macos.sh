#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="${PROJECT_ROOT}/.venv"
PYTHON_VERSION="${PYTHON_VERSION:-3.11.15}"
LOCAL_PYTHON="${PROJECT_ROOT}/.local/python-${PYTHON_VERSION}/bin/python3.11"
INSTALL_TRAINING="${INSTALL_TRAINING:-1}"
export COPYFILE_DISABLE=1
export COPY_EXTENDED_ATTRIBUTES_DISABLE=1

if [[ ! -x "${LOCAL_PYTHON}" ]]; then
  echo "Missing local Python 3.11 at ${LOCAL_PYTHON}"
  echo "Run scripts/bootstrap_python311_macos.sh first."
  exit 1
fi

if [[ -x "${VENV_PATH}/bin/python" ]]; then
  CURRENT_VERSION="$("${VENV_PATH}/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [[ "${CURRENT_VERSION}" != "3.11" ]]; then
    rm -rf "${VENV_PATH}"
  fi
fi

if [[ ! -x "${VENV_PATH}/bin/python" ]]; then
  "${LOCAL_PYTHON}" -m venv "${VENV_PATH}"
fi

find "${PROJECT_ROOT}/.local/python-${PYTHON_VERSION}" -name '._*' -delete
find "${VENV_PATH}" -name '._*' -delete

"${VENV_PATH}/bin/python" -m pip install --upgrade pip
"${VENV_PATH}/bin/pip" install -r "${PROJECT_ROOT}/requirements.txt"

if [[ "${INSTALL_TRAINING}" == "1" ]]; then
  "${VENV_PATH}/bin/pip" install torch torchvision torchaudio
  "${VENV_PATH}/bin/pip" install -r "${PROJECT_ROOT}/requirements-train.txt"
fi

find "${VENV_PATH}" -name '._*' -delete

"${VENV_PATH}/bin/python" --version
echo "Environment ready at ${VENV_PATH}"
