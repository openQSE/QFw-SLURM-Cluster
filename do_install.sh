#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_BASE_DIR="${SCRIPT_DIR}/../qfw-container-base"
BASE_DIR="${QFW_CONTAINER_BASE:-${1:-${DEFAULT_BASE_DIR}}}"
QFW_DIR="${BASE_DIR}/QFw"

mkdir -p \
    "${BASE_DIR}" \
    "${BASE_DIR}/venv" \
    "${BASE_DIR}/build" \
    "${BASE_DIR}/install" \
    "${BASE_DIR}/benchmarks" \
    "${BASE_DIR}/rocm"

echo "Prepared qfw-container-base at: ${BASE_DIR}"

if [ -d "${QFW_DIR}/.git" ] || [ -f "${QFW_DIR}/README.md" ]; then
    echo "Found QFw checkout at: ${QFW_DIR}"
else
    cat <<EOF
Missing QFw checkout at: ${QFW_DIR}

Clone or place the QFw source tree there before starting the cluster, for example:
  git clone <QFw-repo-url> "${QFW_DIR}"

The persistent Python venv is intentionally not created here. Create it later from
inside the built container so it matches the container Python runtime:
  python3 -m venv /workspace/qfw-container-base/venv
EOF
fi
