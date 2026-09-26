#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<EOF
Usage: $(basename "$0") [--jobs N] [--clean] [--skip-venv] [--container NAME]

Build and install QFw + DEFw and MQT Core developer overrides inside the
running cluster from checkouts on the shared mount. The cluster image's official
installation remains unchanged.

Everything lands on the shared mount, so every node sees the same install and
the tree being built is your own shared-dir/QFw checkout:

  source              \${QFW_BASE}/QFw
  python venv         \${QFW_BASE}/qfw-venv
  build tree          \${QFW_BASE}/qfw-build
  install tree        \${QFW_BASE}/qfw-install
  mqt-core source     \${QFW_BASE}/mqt-core
  mqt-cc venv         \${QFW_BASE}/mqt-cc-venv

Activate the result inside a container with:

  source \${QFW_PREFIX}/bin/qfw-activate --venv \${QFW_VENV}

Options:
  --jobs N          Parallel build jobs (default: nproc in the container)
  --clean           Remove the QFw build and install trees first
  --skip-venv       Reuse the existing venv, skip Python installs
  --container NAME  Container to build in (default: slurmctld)
  -h, --help        Show this help
EOF
}

JOBS=""
CLEAN=false
SKIP_VENV=false
CONTAINER=slurmctld

while [ "$#" -gt 0 ]; do
    case "$1" in
        --jobs)
            [ "$#" -ge 2 ] || { echo "--jobs requires a number" >&2; exit 2; }
            JOBS="$2"; shift 2 ;;
        --clean)   CLEAN=true; shift ;;
        --skip-venv) SKIP_VENV=true; shift ;;
        --container)
            [ "$#" -ge 2 ] || { echo "--container requires a name" >&2; exit 2; }
            CONTAINER="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
    echo "Container ${CONTAINER} is not running. Start the cluster with ./do_startup.sh first." >&2
    exit 1
fi

# The image exports QRMI_VERSION so the bindings match the C ABI it ships.
# Older images predate that ENV, so fall back to the Dockerfile's pinned ARG.
QRMI_VERSION_HOST="$(sed -n 's/^ARG QRMI_VERSION=//p' "${SCRIPT_DIR}/Dockerfile" | head -1)"

# The host path behind the shared mount, so the preflight checks below can name
# the directory the user actually has to fix rather than the container path.
QFW_HOST_BASE="$(sed -n 's/^QFW_CONTAINER_BASE=//p' "${SCRIPT_DIR}/qfw-install.env" 2>/dev/null | head -1)"
[ -n "${QFW_HOST_BASE}" ] || QFW_HOST_BASE="shared-dir"

echo "Building QFw + DEFw inside ${CONTAINER}"

docker exec -i \
    -e QFW_VERSION_FALLBACK="${QRMI_VERSION_HOST}" \
    -e QFW_BUILD_JOBS_OVERRIDE="${JOBS}" \
    -e QFW_DO_CLEAN="${CLEAN}" \
    -e QFW_SKIP_VENV="${SKIP_VENV}" \
    -e QFW_HOST_BASE="${QFW_HOST_BASE}" \
    -e QFW_CONTAINER_NAME="${CONTAINER}" \
    "${CONTAINER}" bash -s <<'REMOTE'
set -euo pipefail

QFW_BASE="${QFW_BASE:-/workspace/qfw-container-base}"
QFW_SRC="${QFW_DEV_SRC:-${QFW_BASE}/QFw}"
QFW_VENV="${QFW_DEV_VENV:-${QFW_BASE}/qfw-venv}"
QFW_BUILD="${QFW_DEV_BUILD:-${QFW_BASE}/qfw-build}"
QFW_PREFIX="${QFW_DEV_PREFIX:-${QFW_BASE}/qfw-install}"
QFW_HOST_BASE="${QFW_HOST_BASE:-shared-dir}"
QFW_CONTAINER_NAME="${QFW_CONTAINER_NAME:-slurmctld}"
MQT_CORE_SRC="${QFW_BASE}/mqt-core"
export MLIR_DIR="${MLIR_DIR:-/opt/llvm-23.1.1/lib/cmake/mlir}"

jobs="${QFW_BUILD_JOBS_OVERRIDE:-}"
[ -n "${jobs}" ] || jobs="$(nproc)"

# Preflight. These conditions all used to surface as "No CMakeLists.txt",
# because a [ -f ] test is false whether a file is absent or merely unreadable.
# An unlabelled SELinux bind mount therefore reported a missing checkout, which
# sends you looking in the wrong place entirely.
if [ ! -d "${QFW_BASE}" ]; then
    echo "The shared mount ${QFW_BASE} does not exist in this container." >&2
    echo "Check QFW_CONTAINER_BASE in qfw-install.env, then re-run ./do_startup.sh." >&2
    exit 1
fi

if ! ls "${QFW_BASE}" >/dev/null 2>&1; then
    echo "The shared mount ${QFW_BASE} exists but its contents cannot be read." >&2
    echo "On an SELinux host this is the bind-mount label, not a missing checkout." >&2
    echo "Compare the host against the container:" >&2
    echo "    ls -l ${QFW_HOST_BASE}" >&2
    echo "    docker exec ${QFW_CONTAINER_NAME} ls -l ${QFW_BASE}" >&2
    echo "If the host can read it and the container cannot, relabel it:" >&2
    echo "    chcon -Rt container_file_t ${QFW_HOST_BASE}" >&2
    exit 1
fi

if [ ! -d "${QFW_SRC}" ]; then
    echo "No QFw checkout at ${QFW_SRC}." >&2
    echo "QFw is a separate repository, not a submodule of the cluster repo, so" >&2
    echo "clone it onto the shared mount from the host:" >&2
    echo "    git clone --recursive https://github.com/openQSE/QFw.git ${QFW_HOST_BASE}/QFw" >&2
    exit 1
fi

if [ ! -f "${QFW_SRC}/CMakeLists.txt" ]; then
    echo "No CMakeLists.txt in ${QFW_SRC}." >&2
    echo "This build needs a QFw checkout on the v0.1 release line or later." >&2
    echo "Check what the checkout is on with:" >&2
    echo "    git -C ${QFW_HOST_BASE}/QFw log --oneline -1" >&2
    exit 1
fi

if [ "${QFW_SKIP_VENV}" != "true" ]; then
    if [ ! -f "${MQT_CORE_SRC}/pyproject.toml" ]; then
        echo "No MQT Core checkout at ${MQT_CORE_SRC}." >&2
        echo "Clone it onto the shared mount from the host:" >&2
        echo "    git clone https://github.com/munich-quantum-toolkit/core.git ${QFW_HOST_BASE}/mqt-core" >&2
        exit 1
    fi
    if [ ! -f "${MLIR_DIR}/MLIRConfig.cmake" ]; then
        echo "No MLIR installation at ${MLIR_DIR}. Rebuild the cluster image first." >&2
        exit 1
    fi
fi

if [ "${QFW_DO_CLEAN}" = "true" ]; then
    echo "== removing ${QFW_BUILD} and ${QFW_PREFIX}"
    rm -rf "${QFW_BUILD}" "${QFW_PREFIX}"
fi

if [ "${QFW_SKIP_VENV}" != "true" ]; then
    echo "== python venv: ${QFW_VENV}"
    [ -d "${QFW_VENV}" ] || uv venv --python python3 "${QFW_VENV}"
    # shellcheck disable=SC1091
    source "${QFW_VENV}/bin/activate"
    uv pip install --upgrade pip setuptools wheel
    uv pip install -r "${QFW_SRC}/setup/build-requirements.txt"
    uv pip install -r "${QFW_SRC}/setup/requirements.txt"

    # Match the QRMI bindings to the C library built into the image.
    qrmi_pin="${QRMI_VERSION:-${QFW_VERSION_FALLBACK:-}}"
    if [ -n "${qrmi_pin}" ]; then
        echo "== qrmi bindings pinned to ${qrmi_pin}"
        uv pip install "qrmi==${qrmi_pin}"
    else
        echo "No QRMI version pin available; installing unpinned qrmi" >&2
        uv pip install qrmi
    fi
    # The QFw driver needs the IQM device library, ID, and prefix. Version 1.4
    # also provides the queue properties used with QDMI 1.3.3.
    uv pip install 'iqm-qdmi>=1.4'

    # The QFw driver imports mqt.core.qdmi.driver, available since 3.9.
    uv pip install 'mqt-core==3.9.2'

    # The bundled QHW packages (qhw-data, qhw-iqm, qhw-admission, qhw-scheduler)
    # are installed into site-packages by file copy, so their declared
    # dependencies are not resolved. qhw-data needs jsonschema for
    # schema validation, which the shim's qhw record building relies on.
    uv pip install 'jsonschema>=4'
else
    # shellcheck disable=SC1091
    source "${QFW_VENV}/bin/activate"
fi

echo "== cmake configure"
cmake -S "${QFW_SRC}" -B "${QFW_BUILD}" \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DCMAKE_INSTALL_PREFIX="${QFW_PREFIX}" \
    -DQFW_BUILD_BUNDLED_DEFW=ON

echo "== cmake build (-j ${jobs})"
cmake --build "${QFW_BUILD}" -j "${jobs}"

echo "== cmake install"
cmake --install "${QFW_BUILD}"

if [ "${QFW_SKIP_VENV}" != "true" ]; then
    # Build mqt-cc from the mounted checkout, apart from QFw's SDK dependencies.
    mqt_cc_venv="${QFW_BASE}/mqt-cc-venv"
    [ -d "${mqt_cc_venv}" ] || uv venv --python python3 "${mqt_cc_venv}"
    uv pip install --python "${mqt_cc_venv}" --upgrade pip
    CMAKE_BUILD_PARALLEL_LEVEL="${jobs}" \
        uv pip install --python "${mqt_cc_venv}" \
        "${MQT_CORE_SRC}" 'qiskit==2.5.2'
fi

echo
echo "QFw installed to ${QFW_PREFIX}"
echo "Activate with: source ${QFW_PREFIX}/bin/qfw-activate --venv ${QFW_VENV}"
REMOTE
