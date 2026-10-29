#!/bin/bash
#SBATCH --job-name=libquantum-dual-backend
#SBATCH --output=libquantum-dual-backend.%J.out
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:10:00
#SBATCH --qpu=nwqsim
#SBATCH --workload-kind=quantum
#SBATCH --circ-count=2
#SBATCH --max-qubits=4
#SBATCH --max-depth=16
#SBATCH --max-shots=1024

set -euo pipefail

QFW_BASE="${QFW_BASE:-/workspace/qfw-container-base}"
QFW_PREFIX="${QFW_PREFIX:-${QFW_BASE}/qfw-install}"
QFW_VENV="${QFW_VENV:-${QFW_BASE}/qfw-venv}"
source "${QFW_PREFIX}/bin/qfw-activate" --venv "${QFW_VENV}"

test -n "${QFW_RESERVATIONS:-}"
python - <<'PY'
from importlib import metadata
from pathlib import Path

from libquantum_compiler_qiskit import plugin_path
from qfw_qiskit import QFwBackend, QFwBackendV2

manifest = Path(plugin_path()) / "compiler.json"
assert manifest.is_file(), manifest
print({
    "qfw_backend_legacy": f"{QFwBackend.__module__}.{QFwBackend.__name__}",
    "qfw_backend_v2": f"{QFwBackendV2.__module__}.{QFwBackendV2.__name__}",
    "libquantum": metadata.version("libquantum"),
    "qfw_qiskit": metadata.version("qfw-qiskit"),
    "qiskit_compiler": metadata.version("libquantum-compiler-qiskit"),
    "qiskit": metadata.version("qiskit"),
    "manifest": str(manifest),
})
PY

example="${QFW_SHARE_DIR}/examples/qfw_qiskit_simple.sh"
legacy_log="${SLURM_SUBMIT_DIR}/libquantum-legacy.${SLURM_JOB_ID}.log"
v2_log="${SLURM_SUBMIT_DIR}/libquantum-v2.${SLURM_JOB_ID}.log"

"${example}" 4 --backend-api legacy 2>&1 | tee "${legacy_log}"
"${example}" 4 --backend-api v2 2>&1 | tee "${v2_log}"

grep -q "qfw_qiskit.qfw_simulator.QFwBackend" "${legacy_log}"
grep -q "qfw_qiskit.qfw_backend_v2.QFwBackendV2" "${v2_log}"
if grep -q "qfw_backend_v2.QFwBackendV2" "${legacy_log}"; then
    echo "legacy mode fell back to V2" >&2
    exit 1
fi
if grep -q "qfw_simulator.QFwBackend'" "${v2_log}"; then
    echo "V2 mode fell back to legacy" >&2
    exit 1
fi

echo "QFW DUAL BACKEND SYSTEM TEST: PASS"
