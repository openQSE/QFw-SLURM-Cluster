#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<EOF
Usage: $(basename "$0") [--jobs N] [--clean] [--skip-venv] [--container NAME]

Build and install QFw + DEFw inside the running cluster, out of the shared
mount. This replaces the old image-baked QFw build: as of the v0.1 release
line QFw builds with CMake, and the setup/qfw_configure + qfw_build.sh pair
the Dockerfile used to run no longer exists upstream.

Everything lands on the shared mount, so every node sees the same install and
the tree being built is your own shared-dir/QFw checkout:

  source              \${QFW_BASE}/QFw
  python venv         \${QFW_BASE}/qfw-venv
  build tree          \${QFW_BASE}/qfw-build
  install tree        \${QFW_BASE}/qfw-install

Activate the result inside a container with:

  source \${QFW_PREFIX}/bin/qfw-activate --venv \${QFW_VENV}

Options:
  --jobs N          Parallel build jobs (default: nproc in the container)
  --clean           Remove the build and install trees first
  --skip-venv       Reuse the existing venv, skip all pip installs
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

echo "Building QFw + DEFw inside ${CONTAINER}"

docker exec -i \
    -e QFW_VERSION_FALLBACK="${QRMI_VERSION_HOST}" \
    -e QFW_BUILD_JOBS_OVERRIDE="${JOBS}" \
    -e QFW_DO_CLEAN="${CLEAN}" \
    -e QFW_SKIP_VENV="${SKIP_VENV}" \
    "${CONTAINER}" bash -s <<'REMOTE'
set -euo pipefail

QFW_BASE="${QFW_BASE:-/workspace/qfw-container-base}"
QFW_SRC="${QFW_SRC:-${QFW_BASE}/QFw}"
QFW_VENV="${QFW_VENV:-${QFW_BASE}/qfw-venv}"
QFW_BUILD="${QFW_BUILD:-${QFW_BASE}/qfw-build}"
QFW_PREFIX="${QFW_PREFIX:-${QFW_BASE}/qfw-install}"

jobs="${QFW_BUILD_JOBS_OVERRIDE:-}"
[ -n "${jobs}" ] || jobs="$(nproc)"

if [ ! -f "${QFW_SRC}/CMakeLists.txt" ]; then
    echo "No CMakeLists.txt in ${QFW_SRC}." >&2
    echo "This build needs a QFw checkout on the v0.1 release line or later." >&2
    exit 1
fi

if [ "${QFW_DO_CLEAN}" = "true" ]; then
    echo "== removing ${QFW_BUILD} and ${QFW_PREFIX}"
    rm -rf "${QFW_BUILD}" "${QFW_PREFIX}"
fi

if [ "${QFW_SKIP_VENV}" != "true" ]; then
    echo "== python venv: ${QFW_VENV}"
    [ -d "${QFW_VENV}" ] || python3 -m venv "${QFW_VENV}"
    # shellcheck disable=SC1091
    source "${QFW_VENV}/bin/activate"
    python -m pip install --upgrade pip setuptools wheel
    python -m pip install -r "${QFW_SRC}/setup/build-requirements.txt"
    python -m pip install -r "${QFW_SRC}/setup/requirements.txt"

    # Shim dependencies. These used to be baked into the image venv. The C ABI
    # in ${QRMI_PREFIX}/lib is built at image build time, so the bindings are
    # pinned to the same QRMI_VERSION the image exported.
    qrmi_pin="${QRMI_VERSION:-${QFW_VERSION_FALLBACK:-}}"
    if [ -n "${qrmi_pin}" ]; then
        echo "== qrmi bindings pinned to ${qrmi_pin}"
        python -m pip install "qrmi==${qrmi_pin}"
    else
        echo "No QRMI version pin available; installing unpinned qrmi" >&2
        python -m pip install qrmi
    fi
    python -m pip install 'iqm-qdmi[qiskit]'

    # mqt-core 3.8.0 removed fomac.add_dynamic_device_library in favour of
    # register_device/open_device. The QDMI driver still calls the 3.7 API, so
    # pin until services/svc_lib_qpm/drivers/qdmi_driver.py is ported. Installed
    # after iqm-qdmi so this pin wins over whatever that extra resolves to.
    python -m pip install 'mqt-core==3.7.0'

    # The bundled QHW packages (qhw-data, qhw-iqm, qhw-admission, qhw-scheduler)
    # are installed into site-packages by file copy, so pip never resolves the
    # dependencies their pyproject.toml declares. qhw-data needs jsonschema for
    # schema validation, which the shim's qhw record building relies on.
    python -m pip install 'jsonschema>=4'
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

echo
echo "QFw installed to ${QFW_PREFIX}"
echo "Activate with: source ${QFW_PREFIX}/bin/qfw-activate --venv ${QFW_VENV}"
REMOTE
