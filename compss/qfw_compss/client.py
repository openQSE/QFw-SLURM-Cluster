"""Qiskit primitives on a QFw QPM, usable from any Python process.

QFw's client needs the DEFw runtime, which ``defw-python`` provides: Python
embedded in a native process with its own RPC listener threads. A COMPSs
worker is an ordinary interpreter that forks its executors, and a forked
child would lose those threads. So a :class:`QFwClient` starts one
``defw-python`` child of its own and keeps it for as long as the client is
open::

	COMPSs task                          defw-python -m qfw_compss._server
	-----------                          ---------------------------------
	QFwClient(session, provider)  ─────► QFwBackend(provider=...)
	client.estimator().run(pubs)  ─────► QFwEstimatorV2(backend).run(pubs)
	                              ◄───── PrimitiveResult
	client.close()                ─────► backend.shutdown()

The child pays the DEFw start-up and the QPM lookup once, however many times
the task calls the primitives. An iterative algorithm such as VQE makes
hundreds of estimator calls, so open one client per task, not per call.

Requests and results travel as pickles over a pair of pipes the child
inherits. Both ends run the same Qiskit from the same venv.
"""

import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from multiprocessing.connection import Connection
from pathlib import Path

from qiskit.primitives import BaseEstimatorV2, BaseSamplerV2, PrimitiveJob

from .session import QFwSession


FDS_ENV = "QFW_COMPSS_FDS"


class QFwError(RuntimeError):
	"""The defw-python child failed, or a primitive call raised in it."""


class QFwClient:
	"""One ``defw-python`` child bound to one QFw QPM.

	``provider`` selects the QPM the same way ``QFwBackend(provider=...)``
	does, for example ``"nwqsim"`` or ``"fake-iqm"``. ``service_id`` picks one
	reservation when the job reserved several QPMs. ``session`` defaults to
	the one ``qfw-compss-launch`` saved for the job, which is what a COMPSs
	task should use.

	Use it as a context manager so the child always shuts its backend down::

		with QFwClient(provider="nwqsim") as qfw:
			estimator = qfw.estimator()
			energy = estimator.run([(ansatz, observables, params)]).result()

	``call_timeout`` bounds each primitive call in seconds. A child that goes
	past it counts as hung and is killed. By default a call waits as long as
	QFw does, since a real device can queue for a long time.

	The client directory under ``session.scratch_dir`` keeps the child's
	output and DEFw logs. It is removed when the client closes cleanly,
	unless ``keep_files`` is set, and kept when anything failed, including
	an exception in the ``with`` block. A failed primitive call raises
	:class:`QFwError` and leaves the client usable; a child that died or
	stopped answering does not.
	"""

	def __init__(self, session=None, provider="nwqsim", service_id=None,
				 startup_timeout=300, call_timeout=None, keep_files=False):
		self.session = session if session is not None else QFwSession.load()
		self.provider = provider
		self.service_id = service_id
		self.keep_files = keep_files
		self.call_timeout = call_timeout
		self.info = {}
		self.calls = 0
		self._lock = threading.Lock()
		self._proc = None
		self._send = None
		self._recv = None
		# _broken: the child can no longer answer. _keep: something failed,
		# so keep the client directory for whoever investigates.
		self._broken = False
		self._keep = False
		self._closed = False
		self.directory = (Path(self.session.scratch_dir) / "clients" /
						  uuid.uuid4().hex)
		try:
			self._start(startup_timeout)
		except BaseException:
			self._keep = True
			self.close()
			raise

	def _start(self, startup_timeout):
		log_dir = self.directory / "defw-logs"
		log_dir.mkdir(parents=True)
		env = self.session.child_environment(log_dir)
		defw_python = shutil.which("defw-python", path=env.get("PATH"))
		if defw_python is None:
			raise QFwError(
				"defw-python is not on the session PATH; was the session "
				"captured after qfw-activate?")

		# Two one-way pipes: requests to the child, replies back. The child
		# inherits one end of each; this process keeps the other.
		req_read, req_write = os.pipe()
		rep_read, rep_write = os.pipe()
		self._send = Connection(req_write, readable=False)
		self._recv = Connection(rep_read, writable=False)
		env[FDS_ENV] = f"{req_read},{rep_write}"
		started = time.time()
		try:
			with (self.directory / "output.log").open("wb") as log:
				self._proc = subprocess.Popen(
					[defw_python, "-m", "qfw_compss._server"],
					env=env, cwd=self.directory, stdin=subprocess.DEVNULL,
					stdout=log, stderr=subprocess.STDOUT,
					pass_fds=(req_read, rep_write),
					# defw-python is a wrapper around the real process, so
					# killing the child has to reach its whole group.
					start_new_session=True)
		finally:
			os.close(req_read)
			os.close(rep_write)

		self._request({
			"op": "connect",
			"provider": self.provider,
			"service_id": self.service_id,
		})
		ready = self._reply(timeout=startup_timeout)
		self.info = dict(ready,
						 wall_connect_sec=round(time.time() - started, 3))

	def _request(self, request):
		try:
			self._send.send(request)
		except OSError:
			self._broken = True
			self._raise(
				f"defw-python exited with status {self._proc.wait()}")

	def _reply(self, timeout=None):
		"""The child's answer to the last request, or ``QFwError``."""
		if timeout is not None and not self._recv.poll(timeout):
			self._broken = True
			self._raise(f"no answer from defw-python within {timeout}s")
		try:
			status, payload = self._recv.recv()
		except (EOFError, OSError):
			self._broken = True
			self._raise(
				f"defw-python exited with status {self._proc.wait()}")
		if status == "error":
			self._raise(f"QFw call failed in defw-python:\n{payload}")
		return payload

	def _raise(self, message):
		self._keep = True
		raise QFwError(f"{message}\nsee {self.directory}/output.log")

	def _call(self, primitive, options, pubs, kwargs):
		with self._lock:
			if self._closed or self._broken:
				raise QFwError("the QFw client is closed")
			self._request({
				"op": "run",
				"primitive": primitive,
				"options": options,
				"pubs": pubs,
				"kwargs": kwargs,
			})
			result = self._reply(timeout=self.call_timeout)
			self.calls += 1
			return result

	def estimator(self, **options):
		"""A Qiskit ``BaseEstimatorV2`` backed by ``QFwEstimatorV2``.

		``options`` are ``QFwEstimatorV2``'s, such as ``default_precision``.
		"""
		return QFwEstimator(self, options)

	def sampler(self, **options):
		"""A Qiskit ``BaseSamplerV2`` backed by ``QFwSamplerV2``.

		``options`` are ``QFwSamplerV2``'s, such as ``default_shots``.
		"""
		return QFwSampler(self, options)

	def close(self, timeout=120):
		"""Shut the child's backend down and wait for the child to exit.

		``QFwBackend.shutdown`` ends the whole DEFw process, so the child
		answers first and its exit status says whether the shutdown worked.
		"""
		with self._lock:
			if self._closed:
				return
			self._closed = True
			proc = self._proc
			try:
				if proc is not None and not self._broken:
					self._request({"op": "close"})
					self._reply(timeout=timeout)
			except (QFwError, OSError):
				pass
			finally:
				# A child that missed the close request sees the request pipe
				# close, and shuts its backend down and exits all the same.
				for conn in (self._send, self._recv):
					if conn is not None:
						conn.close()
			if proc is not None:
				if self._broken:
					_kill_group(proc)
				try:
					proc.wait(timeout=timeout)
				except subprocess.TimeoutExpired:
					self._keep = True
					_kill_group(proc)
					proc.wait()
				if proc.returncode != 0:
					self._keep = True
		if not self._keep and not self.keep_files:
			shutil.rmtree(self.directory, ignore_errors=True)

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc, tb):
		if exc_type is not None:
			self._keep = True
		self.close()

	def __repr__(self):
		return (f"QFwClient(provider={self.provider!r}, "
				f"service_id={self.service_id!r}, "
				f"host={self.info.get('host')!r})")


def _kill_group(proc):
	try:
		os.killpg(proc.pid, signal.SIGKILL)
	except ProcessLookupError:
		pass


def _submit(client, primitive, options, pubs, kwargs):
	job = PrimitiveJob(client._call, primitive, options, list(pubs), kwargs)
	job._submit()
	return job


class QFwEstimator(BaseEstimatorV2):
	"""``QFwEstimatorV2`` running in a :class:`QFwClient`'s child."""

	def __init__(self, client, options=None):
		self._client = client
		self._options = dict(options or {})

	def run(self, pubs, *, precision=None):
		return _submit(self._client, "estimator", self._options, pubs,
					   {"precision": precision})


class QFwSampler(BaseSamplerV2):
	"""``QFwSamplerV2`` running in a :class:`QFwClient`'s child."""

	def __init__(self, client, options=None):
		self._client = client
		self._options = dict(options or {})

	def run(self, pubs, *, shots=None):
		return _submit(self._client, "sampler", self._options, pubs,
					   {"shots": shots})
