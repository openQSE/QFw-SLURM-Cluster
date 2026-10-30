"""Frozen input factory for the libquantum managed-QFw phase gate."""

import libquantum as lq
from qiskit import QuantumCircuit


def create_case():
    """Return one allocation-scoped Qiskit integration case."""
    circuit = QuantumCircuit(2, 2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure((0, 1), (0, 1))
    return {
        "payload": circuit,
        "constraints": lq.RouteConstraints(),
        "execution_options": lq.ExecutionOptions(shots=256),
        "completion_timeout": 300.0,
    }
