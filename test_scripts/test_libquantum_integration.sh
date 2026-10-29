#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bash -n "${script_dir}/do_qfw_build.sh"
bash -n "${script_dir}/shared-dir/libquantum-dual-backend.sbatch"
grep -q 'LIBQUANTUM_DEV_SRC' "${script_dir}/do_qfw_build.sh"
grep -q 'QISKIT_COMPILER_DEV_SRC' "${script_dir}/do_qfw_build.sh"
grep -q 'libquantum-compiler-qiskit' "${script_dir}/do_qfw_build.sh"
grep -q '^#SBATCH --qpu=nwqsim$' \
    "${script_dir}/shared-dir/libquantum-dual-backend.sbatch"
grep -q -- '--backend-api legacy' \
    "${script_dir}/shared-dir/libquantum-dual-backend.sbatch"
grep -q -- '--backend-api v2' \
    "${script_dir}/shared-dir/libquantum-dual-backend.sbatch"

echo "libquantum cluster integration static gate: PASS"
