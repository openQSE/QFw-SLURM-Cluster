#!/usr/bin/env python3
"""The smallest useful COMPSs + QFw application.

Each task rotates one qubit by a different angle and measures it. The tasks
run at the same time on different nodes, and each sends its circuit to QFw.
The answer is easy to check: a qubit rotated by an angle reads 1 with
probability sin(angle / 2) squared.
"""

import math
import socket
import time

from pycompss.api.api import compss_wait_on
from pycompss.api.task import task
from qiskit import QuantumCircuit

from qfw_compss import QFwClient

ANGLES = [step * math.pi / 7 for step in range(8)]
SHOTS = 1024


@task(returns=1)
def measure(angle):
	"""One quantum task. @task makes COMPSs run it in parallel with the others."""
	started = time.time()
	circuit = QuantumCircuit(1)
	circuit.ry(angle, 0)
	circuit.measure_all()

	with QFwClient(provider="nwqsim") as qfw:
		result = qfw.sampler(default_shots=SHOTS).run([circuit]).result()

	counts = result[0].data.meas.get_counts()
	return {
		"angle": angle,
		"measured": counts.get("1", 0) / SHOTS,
		"node": socket.gethostname(),
		"seconds": time.time() - started,
	}


def main():
	started = time.time()
	# Each call returns straight away with a placeholder, and COMPSs runs the
	# tasks as workers become free.
	futures = [measure(angle) for angle in ANGLES]
	# This is where the program waits for all the real results.
	results = compss_wait_on(futures)
	elapsed = time.time() - started

	print("hello: angle  measured  expected  node")
	for r in results:
		expected = math.sin(r["angle"] / 2) ** 2
		print(f"hello: {r['angle']:5.2f}  {r['measured']:8.3f}  {expected:8.3f}  {r['node']}")
	longest = max(r["seconds"] for r in results)
	print(f"hello: {len(results)} tasks finished in {elapsed:.0f} s; "
		  f"the slowest took {longest:.0f} s")


if __name__ == "__main__":
	main()
