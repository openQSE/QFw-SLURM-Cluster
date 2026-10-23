#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary="$(mktemp -d)"
trap 'rm -rf "${temporary}"' EXIT
export QFW_BASE="${temporary}/workspace with spaces"
export MLIR_DIR="${temporary}/mlir"
export QFW_SKIP_VENV=false QFW_DO_CLEAN=false QFW_BUILD_JOBS_OVERRIDE=1
export QFW_DEV_SRC="" QFW_DEV_VENV="" QFW_DEV_BUILD="" QFW_DEV_PREFIX=""
export UV_LOG="${temporary}/uv.log"

mkdir -p "${QFW_BASE}/QFw/setup" "${QFW_BASE}/mqt-core" \
    "${QFW_BASE}/qfw-venv/bin" "${MLIR_DIR}"
touch "${QFW_BASE}/QFw/CMakeLists.txt" "${QFW_BASE}/mqt-core/pyproject.toml" \
    "${QFW_BASE}/qfw-venv/bin/activate" "${MLIR_DIR}/MLIRConfig.cmake" \
    "${QFW_BASE}/QFw/setup/build-requirements.txt" \
    "${QFW_BASE}/QFw/setup/requirements.txt" \
    "${QFW_BASE}/QFw/setup/qdmi-requirements.txt" \
    "${QFW_BASE}/QFw/setup/overrides.txt"
sed -n '/^QFW_BASE=/,/^REMOTE$/p' "${repo_dir}/do_qfw_build.sh" |
    sed '$d' >"${temporary}/remote.sh"

uv() { printf '<%s>' "$@" >>"${UV_LOG}"; printf '\n' >>"${UV_LOG}"; }
cmake() { :; }
ldd() { echo libfabric; }
export -f uv cmake ldd

for qrmi in pinned fallback unpinned; do
    export QRMI_VERSION="" QFW_VERSION_FALLBACK=""
    requirement=qrmi
    if [ "${qrmi}" = pinned ]; then
        export QRMI_VERSION=0.26.0
        requirement=qrmi==0.26.0
    elif [ "${qrmi}" = fallback ]; then
        export QFW_VERSION_FALLBACK=0.25.0
        requirement=qrmi==0.25.0
    fi
    : >"${UV_LOG}"
    bash -euo pipefail "${temporary}/remote.sh" >"${temporary}/output" 2>&1
    expected="<pip><install><-r><${QFW_BASE}/QFw/setup/build-requirements.txt><-r><${QFW_BASE}/QFw/setup/requirements.txt><-r><${QFW_BASE}/QFw/setup/qdmi-requirements.txt><--override><${QFW_BASE}/QFw/setup/overrides.txt><${requirement}>"
    if ! grep -Fxq "${expected}" "${UV_LOG}"; then
        echo "Dependencies were not resolved together (${qrmi} QRMI):" >&2
        cat "${UV_LOG}" >&2
        exit 1
    fi
    [ "$(grep -c 'requirements.txt' "${UV_LOG}")" -eq 1 ]
    grep -Fxq "<pip><install><--reinstall-package><mqt-core><${QFW_BASE}/mqt-core>" "${UV_LOG}"
    ! grep -Fq "mqt-cc-venv" "${UV_LOG}"
done

rm "${QFW_BASE}/QFw/setup/overrides.txt"
: >"${UV_LOG}"
if bash -euo pipefail "${temporary}/remote.sh" >"${temporary}/output" 2>&1; then
    echo "Missing overrides did not stop the build" >&2
    exit 1
fi
grep -Fq "No dependency overrides at ${QFW_BASE}/QFw/setup/overrides.txt" "${temporary}/output"
[ ! -s "${UV_LOG}" ]

touch "${QFW_BASE}/QFw/setup/overrides.txt"
rm "${QFW_BASE}/QFw/setup/qdmi-requirements.txt"
: >"${UV_LOG}"
if bash -euo pipefail "${temporary}/remote.sh" >"${temporary}/output" 2>&1; then
    echo "Missing QDMI requirements did not stop the build" >&2
    exit 1
fi
grep -Fq "No QDMI requirements at ${QFW_BASE}/QFw/setup/qdmi-requirements.txt" "${temporary}/output"
[ ! -s "${UV_LOG}" ]

echo "QFw dependency install passed: pinned, fallback, unpinned, missing file, paths with spaces"
