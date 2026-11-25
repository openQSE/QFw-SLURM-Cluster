"""The defw-python side of a :class:`~qfw_compss.client.QFwClient`.

Runs under ``defw-python``, never directly: it is the only module of
``qfw_compss`` that imports ``qfw_qiskit``. The client starts it with the pipe
descriptors in ``QFW_COMPSS_FDS`` and sends, in order:

	{"op": "connect", "provider": ..., "service_id": ...}
	{"op": "run", "primitive": "estimator" | "sampler", "options": {...},
	 "pubs": [...], "kwargs": {...}}                      (any number)
	{"op": "close"}

Each request gets one ``("ok", payload)`` or ``("error", traceback)`` reply.
After an error in ``connect`` the child exits; after an error in ``run`` it
keeps serving, so the task decides what to do. However the loop ends, the
backend is shut down, and that ends the process.
"""

import json
import os
import sys
import time
import traceback
from multiprocessing.connection import Connection


def _primitive(cache, backend, kind, options):
	key = (kind, json.dumps(options, sort_keys=True, default=repr))
	if key not in cache:
		from qfw_qiskit import QFwEstimatorV2, QFwSamplerV2

		cls = {"estimator": QFwEstimatorV2, "sampler": QFwSamplerV2}[kind]
		cache[key] = cls(backend=backend, options=options or None)
	return cache[key]


def serve(recv, send):
	backend = None
	primitives = {}
	try:
		while True:
			try:
				request = recv.recv()
			except EOFError:
				return 1
			except Exception:
				# For example a pub with a class this process cannot import.
				traceback.print_exc()
				send.send(("error", traceback.format_exc()))
				continue
			op = request["op"]
			try:
				if op == "connect":
					from qfw_qiskit import QFwBackend

					started = time.time()
					backend = QFwBackend(
						provider=request["provider"],
						service_id=request.get("service_id"))
					send.send(("ok", {
						"host": os.uname().nodename,
						"backend": str(backend.name),
						"reservation_id": getattr(
							backend.options, "reservation_id", None),
						"connect_sec": round(time.time() - started, 3),
					}))
				elif op == "run":
					primitive = _primitive(
						primitives, backend, request["primitive"],
						request["options"])
					job = primitive.run(request["pubs"], **request["kwargs"])
					send.send(("ok", job.result()))
				elif op == "close":
					# QFwBackend.shutdown ends this process, so answer first.
					# The client learns the outcome from the exit status.
					send.send(("ok", None))
					return 0
				else:
					raise ValueError(f"unknown request {op!r}")
			except Exception:
				traceback.print_exc()
				send.send(("error", traceback.format_exc()))
				if op != "run":
					return 1
	finally:
		if backend is not None:
			backend.shutdown()


def main():
	req_fd, rep_fd = (int(fd) for fd in os.environ["QFW_COMPSS_FDS"].split(","))
	recv = Connection(req_fd, writable=False)
	send = Connection(rep_fd, readable=False)
	return serve(recv, send)


if __name__ == "__main__":
	sys.exit(main())
