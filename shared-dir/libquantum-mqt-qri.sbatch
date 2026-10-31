#!/bin/bash
#SBATCH --job-name=libquantum-mqt-qri
#SBATCH --output=libquantum-mqt-qri.%J.out
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:10:00
#SBATCH --qpu=nwqsim
#SBATCH --workload-kind=quantum
#SBATCH --circ-count=1
#SBATCH --max-qubits=2
#SBATCH --max-depth=8
#SBATCH --max-shots=256

set -euo pipefail

QFW_BASE="${QFW_BASE:-/workspace/qfw-container-base}"
QFW_PREFIX="${LIBQUANTUM_QFW_PREFIX:-${QFW_BASE}/qfw-main-install}"
QFW_VENV="${LIBQUANTUM_QFW_VENV:-${QFW_BASE}/qfw-main-venv}"
QFW_CLUSTER_SOURCE="${QFW_CLUSTER_SOURCE:-${QFW_BASE}/QFw-release-v0.1/repos-main-sync/QFw-SLURM-Cluster}"
export QFW_SHARED_ROOT="${QFW_SHARED_ROOT:-${QFW_BASE}}"
export QFW_PREFIX
source "${QFW_PREFIX}/bin/qfw-activate" --venv "${QFW_VENV}"

test -n "${QFW_RESERVATIONS:-}"
source "${QFW_SHARE_DIR}/examples/qfw_example_common.sh"
export QFW_EXAMPLE_SERVICE_MODE=site
qfw_example_begin "libquantum-mqt-qri"
qfw_example_setup_backend_service nwqsim
qfw_example_srun_with_backend_reservation \
    nwqsim libquantum-mqt-qri 2 256 1 async_run \
    "${QFW_CLUSTER_SOURCE}/shared-dir/libquantum_mqt_qri.py"
