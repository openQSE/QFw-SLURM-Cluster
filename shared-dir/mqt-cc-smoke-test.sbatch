#!/bin/bash
#
#SBATCH --job-name=mqt-cc-smoke-test
#SBATCH --output=mqt-cc-smoke-test.%J.out
#SBATCH --time=00:05:00
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=512M
#
# Smoke test: compile for the bundled IQM Garnet model and run QIR on
# local DDSIM.
# No QPU or credentials needed.

set -euo pipefail

MQT_CC_VENV="${MQT_CC_VENV:-/opt/openqse/mqt-cc-venv}"
if [ ! -x "${MQT_CC_VENV}/bin/python" ]; then
    echo "No mqt-cc environment at ${MQT_CC_VENV}. Build the image or run ./do_qfw_build.sh." >&2
    exit 1
fi

echo "[$(date)] mqt-cc-smoke-test on $(hostname)"

"${MQT_CC_VENV}/bin/python" - <<'PY'
from qiskit import QuantumCircuit

from mqt.core.mlir import CompilerTarget, compile_program
from mqt.core.qdmi import ProgramFormat
from mqt.core.qdmi.driver import open_device

model = open_device("mqt.sc.iqm.garnet")
target = CompilerTarget.from_device(model)

circuit = QuantumCircuit(3, 3)
circuit.h(0)
circuit.cx(0, 2)
circuit.x(1)
# The fixed bit distinguishes measurement order from physical qubit order.
circuit.measure([2, 0, 1], [0, 1, 2])

compiled = compile_program(circuit, target=target, program_format=ProgramFormat.QIR_BASE_STRING)
assert compiled.program_format == ProgramFormat.QIR_BASE_STRING
print("[mqt-cc-smoke-test] Qiskit -> mqt-cc -> QIR Base: OK")

simulator = open_device("mqt.ddsim.default")
job = simulator.submit_job(compiled.payload, compiled.program_format, 256, custom1=7)
job.wait()
counts = job.get_counts()
assert sum(counts.values()) == 256, counts
assert set(counts) == {"100", "111"}, counts
print(f"[mqt-cc-smoke-test] compiled QIR -> QDMI DDSIM: {counts}")

print("MQT-CC QIR SMOKE TEST: PASS")
PY
