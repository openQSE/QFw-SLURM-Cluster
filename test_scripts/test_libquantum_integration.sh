#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bash -n "${script_dir}/do_qfw_build.sh"
bash -n "${script_dir}/shared-dir/libquantum-dual-backend.sbatch"
grep -q 'LIBQUANTUM_DEV_SRC' "${script_dir}/do_qfw_build.sh"
grep -q 'LIBQUANTUM_SRC}/plugins/qiskit' "${script_dir}/do_qfw_build.sh"
grep -q 'LIBQUANTUM_SRC}/plugins/mqt' "${script_dir}/do_qfw_build.sh"
if grep -q 'QISKIT_COMPILER_DEV_SRC\|MQT_COMPILER_DEV_SRC' \
    "${script_dir}/do_qfw_build.sh"; then
    echo "standalone compiler repository override remains" >&2
    exit 1
fi
if grep -q 'qfw_mqt\|qfw_target_data\|qhw_target' \
    "${script_dir}/do_qfw_build.sh"; then
    echo "deleted QFw target helper remains in build path" >&2
    exit 1
fi
grep -q '^#SBATCH --qpu=nwqsim$' \
    "${script_dir}/shared-dir/libquantum-dual-backend.sbatch"
grep -q -- '--backend-api legacy' \
    "${script_dir}/shared-dir/libquantum-dual-backend.sbatch"
grep -q -- '--backend-api v2' \
    "${script_dir}/shared-dir/libquantum-dual-backend.sbatch"
grep -q 'target_shared' \
    "${script_dir}/shared-dir/libquantum-dual-backend.sbatch"

echo "libquantum cluster integration static gate: PASS"
