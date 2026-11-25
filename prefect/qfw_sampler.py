#!/usr/bin/env python3
"""Sample a serialized circuit through QFw inside a qfw-slurm allocation.

This is the application step of the quantum stage: it runs under qfw-srun,
reads a QPY circuit, runs it on the QFw backend for the requested provider
with the reservation qfw-slurm placed in the environment, and writes the
counts to a JSON file that the submitting workflow reads back.

Usage inside the allocation:

    qfw-srun qfw_sampler.py --circuit circuit.qpy.gz \\
        --shots 1024 --provider nwqsim --out counts.json
"""

import argparse
import gzip
import json
import os
import socket
import time

from qiskit import qpy

from qfw_qiskit import QFwBackend
from qfw_qiskit.reservation_set import (
    parse_qfw_reservations,
    select_qpm_reservation,
)

GZIP_MAGIC = b"\x1f\x8b"


def load_circuit(path):
    with open(path, "rb") as handle:
        magic = handle.read(2)
    opener = gzip.open if magic == GZIP_MAGIC else open
    with opener(path, "rb") as handle:
        circuits = qpy.load(handle)
    if len(circuits) != 1:
        raise SystemExit(f"{path} holds {len(circuits)} circuits, expected one")
    return circuits[0]


def reservation_options(service_id=None):
    """The reservation qfw-slurm injected, as QFwBackend.run options."""
    reservations = parse_qfw_reservations(required=False)
    if not reservations:
        return {}, None
    selected = select_qpm_reservation(reservations, service_id=service_id)
    options = {"reservation_id": selected.reservation_id}
    token = os.environ.get("QFW_RESERVATION_TOKEN")
    if token:
        options["token"] = token
    return options, selected


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--circuit", required=True,
                        help="QPY file, plain or gzip-compressed, one circuit")
    parser.add_argument("--shots", type=int, default=1024)
    parser.add_argument("--provider", default="nwqsim",
                        help="QFw provider selector, as QFwBackend(provider=)")
    parser.add_argument("--service-id", default=None,
                        help="QPM service to use when several are reserved")
    parser.add_argument("--out", required=True, help="counts JSON to write")
    args = parser.parse_args()

    circuit = load_circuit(args.circuit)
    options, reservation = reservation_options(args.service_id)

    started = time.time()
    backend = QFwBackend(provider=args.provider, service_id=args.service_id)
    job = backend.run(circuit, shots=args.shots, **options)
    result = job.result()
    counts = result.get_counts(circuit)
    elapsed = time.time() - started

    record = {
        "counts": {str(key): int(value) for key, value in counts.items()},
        "shots": args.shots,
        "provider": args.provider,
        "backend": backend.name,
        "service_id": reservation.service_id if reservation else None,
        "reservation_id": reservation.reservation_id if reservation else None,
        "circuit": {
            "name": circuit.name,
            "num_qubits": circuit.num_qubits,
            "num_clbits": circuit.num_clbits,
            "depth": circuit.depth(),
        },
        "job_id": getattr(job, "job_id", lambda: None)(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "host": socket.gethostname(),
        "time_taken_sec": getattr(result, "time_taken", None),
        "elapsed_sec": round(elapsed, 3),
    }
    tmp = f"{args.out}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, args.out)
    print(f"qfw_sampler: {sum(counts.values())} shots on {backend.name} "
          f"reservation {record['reservation_id']} in {elapsed:.1f}s, "
          f"{len(counts)} distinct outcomes -> {args.out}")


if __name__ == "__main__":
    main()
