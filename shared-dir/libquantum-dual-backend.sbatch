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
QFW_PREFIX="${LIBQUANTUM_QFW_PREFIX:-${QFW_BASE}/qfw-main-install}"
QFW_VENV="${LIBQUANTUM_QFW_VENV:-${QFW_BASE}/qfw-main-venv}"
export QFW_SHARED_ROOT="${QFW_SHARED_ROOT:-${QFW_BASE}}"
export QFW_PREFIX
source "${QFW_PREFIX}/bin/qfw-activate" --venv "${QFW_VENV}"

test -n "${QFW_RESERVATIONS:-}"
python - <<'PY'
from importlib import metadata
from pathlib import Path

from libquantum_compiler_qiskit import plugin_path
import qfw_qiskit
from qfw_qiskit import QFwBackend, QFwBackendV2

manifest = Path(plugin_path()) / "compiler.json"
assert manifest.is_file(), manifest
print({
    "qfw_backend_legacy": f"{QFwBackend.__module__}.{QFwBackend.__name__}",
    "qfw_backend_v2": f"{QFwBackendV2.__module__}.{QFwBackendV2.__name__}",
    "libquantum": metadata.version("libquantum"),
    "qfw_qiskit": qfw_qiskit.__file__,
    "qiskit_compiler": metadata.version("libquantum-compiler-qiskit"),
    "qiskit": metadata.version("qiskit"),
    "manifest": str(manifest),
})
PY

example="${QFW_SHARE_DIR}/examples/qfw_qiskit_simple.sh"
submit_dir="${QFW_EVIDENCE_DIR:-/workspace/home/user-a}"
legacy_log="${submit_dir}/libquantum-legacy.${SLURM_JOB_ID}.log"
v2_log="${submit_dir}/libquantum-v2.${SLURM_JOB_ID}.log"

"${example}" --service-mode site 4 --backend-api legacy \
    2>&1 | tee "${legacy_log}"
"${example}" --service-mode site 4 --backend-api v2 \
    2>&1 | tee "${v2_log}"

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

LEGACY_LOG="${legacy_log}" V2_LOG="${v2_log}" python - <<'PY'
import json
import os
from pathlib import Path


def example_result(path):
    text = Path(path).read_text()
    marker = "QFW_EXAMPLE_RESULT "
    decoder = json.JSONDecoder()
    offset = 0
    matches = []
    while True:
        start = text.find(marker, offset)
        if start < 0:
            break
        start += len(marker)
        record, consumed = decoder.raw_decode(text[start:])
        offset = start + consumed
        if record.get("kind") == "example":
            matches.append(record)
    assert len(matches) == 1, (path, len(matches))
    return matches[0]


legacy = example_result(os.environ["LEGACY_LOG"])
v2 = example_result(os.environ["V2_LOG"])
for mode, record in (("legacy", legacy), ("v2", v2)):
    assert record["status"] == "ok", (mode, record)
    assert record["parameters"] == {
        "backend": "nwqsim", "qubits": 4, "shots": 1024}
    counts = record["metrics"]["counts"]
    assert sum(counts.values()) == 1024, (mode, counts)
    assert set(counts).issubset({"0000", "1111"}), (mode, counts)
    assert record["metrics"]["statevector_available"] is True
print({
    "legacy_counts": legacy["metrics"]["counts"],
    "v2_counts": v2["metrics"]["counts"],
    "parity": "qualified",
})
PY

echo "QFW DUAL BACKEND SYSTEM TEST: PASS"
