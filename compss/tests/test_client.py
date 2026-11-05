"""Tests for qfw_compss that need neither QFw nor COMPSs.

A stub ``qfw_qiskit`` backs the primitives with Qiskit's statevector ones, and
a ``defw-python`` shim runs the child under this interpreter. What is tested
is the qfw_compss side: the session, the child's lifecycle, the request
protocol and the failure paths. Run from QFw-SLURM-Cluster with:

	python3 -m unittest discover -s compss/tests -v
"""

import json
import os
import signal
import stat
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import Parameter
from qiskit.primitives import StatevectorEstimator
from qiskit.quantum_info import SparsePauliOp

COMPSS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(COMPSS_DIR))

from qfw_compss import QFwClient, QFwError, QFwSession  # noqa: E402
from qfw_compss import launch  # noqa: E402
from qfw_compss.launch import build_command  # noqa: E402
from qfw_compss.session import SESSION_ENV  # noqa: E402

STUB = textwrap.dedent('''
	import os
	import time
	from pathlib import Path
	from types import SimpleNamespace
	from qiskit.primitives import StatevectorEstimator, StatevectorSampler

	def _mark(what):
		with open(os.environ["STUB_MARKS"], "a") as marks:
			marks.write(f"{what} {os.getpid()}\\n")

	class QFwBackend:
		def __init__(self, provider=None, service_id=None):
			if provider == "broken":
				raise RuntimeError("no QPM for provider broken")
			self.provider = provider
			self.name = f"stub-{provider}"
			self.options = SimpleNamespace(reservation_id="r-1")
			_mark("connect")

		def shutdown(self):
			_mark("shutdown")
			if self.provider == "bad-shutdown":
				raise RuntimeError("QPM binding would not close")
			# Like QFw: me.exit() ends the DEFw process from here.
			os._exit(0)

	class QFwEstimatorV2:
		def __init__(self, backend=None, options=None):
			self._inner = StatevectorEstimator(
				default_precision=(options or {}).get("default_precision", 0.0))

		def run(self, pubs, precision=None):
			if any(getattr(pub[0], "name", "") == "crash" for pub in pubs):
				os._exit(3)
			if any(getattr(pub[0], "name", "") == "hang" for pub in pubs):
				time.sleep(600)
			if any(getattr(pub[0], "name", "") == "fail" for pub in pubs):
				raise ValueError("estimator refused the circuit")
			return self._inner.run(pubs, precision=precision)

	class QFwSamplerV2:
		def __init__(self, backend=None, options=None):
			self._inner = StatevectorSampler(
				default_shots=(options or {}).get("default_shots", 1024))

		def run(self, pubs, shots=None):
			return self._inner.run(pubs, shots=shots)
''')


class NotInTheChild:
	"""Pickled by reference to this module, which the child cannot import."""


def ansatz(name="ansatz"):
	theta = Parameter("theta")
	circuit = QuantumCircuit(2, name=name)
	circuit.ry(theta, 0)
	circuit.cx(0, 1)
	return circuit


class ClientTest(unittest.TestCase):
	def setUp(self):
		self.tmp = Path(tempfile.mkdtemp())
		stub = self.tmp / "stub" / "qfw_qiskit"
		stub.mkdir(parents=True)
		(stub / "__init__.py").write_text(STUB)
		shim = self.tmp / "bin" / "defw-python"
		shim.parent.mkdir()
		shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
		shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
		self.marks = self.tmp / "marks"
		environment = {
			"PATH": f"{shim.parent}{os.pathsep}{os.environ['PATH']}",
			"PYTHONPATH": f"{stub.parent}{os.pathsep}{COMPSS_DIR}",
			"STUB_MARKS": str(self.marks),
			"QFW_RESERVATIONS": '[["nwqsim", "r-1"]]',
			"SLURM_PROCID": "0",
			"DEFW_LISTEN_PORT": "4000",
		}
		self.session = QFwSession(environment, self.tmp / "scratch")

	def marked(self, what):
		if not self.marks.exists():
			return []
		return [line.split()[1] for line in self.marks.read_text().splitlines()
				if line.split()[0] == what]

	def clients_left(self):
		clients = self.tmp / "scratch" / "clients"
		return list(clients.iterdir()) if clients.exists() else []

	def test_estimator_matches_statevector(self):
		observables = [SparsePauliOp("ZZ"), SparsePauliOp("XI")]
		values = [[0.3], [1.2]]
		expected = StatevectorEstimator().run(
			[(ansatz(), observables, values)]).result()
		with QFwClient(self.session, provider="nwqsim") as qfw:
			self.assertEqual(qfw.info["host"], os.uname().nodename)
			self.assertEqual(qfw.info["reservation_id"], "r-1")
			estimator = qfw.estimator()
			for _ in range(3):
				result = estimator.run([(ansatz(), observables, values)]).result()
			np.testing.assert_allclose(result[0].data.evs, expected[0].data.evs)
			self.assertEqual(qfw.calls, 3)
		self.assertEqual(len(self.marked("connect")), 1)
		self.assertEqual(self.marked("shutdown"), self.marked("connect"))
		self.assertEqual(self.clients_left(), [])

	def test_sampler(self):
		circuit = QuantumCircuit(1)
		circuit.x(0)
		circuit.measure_all()
		with QFwClient(self.session) as qfw:
			result = qfw.sampler(default_shots=64).run([circuit]).result()
		self.assertEqual(result[0].data.meas.get_counts(), {"1": 64})

	def test_failed_call_keeps_client_usable(self):
		observable = SparsePauliOp("ZZ")
		with self.assertRaises(QFwError) as raised:
			with QFwClient(self.session) as qfw:
				estimator = qfw.estimator()
				with self.assertRaisesRegex(QFwError, "refused the circuit"):
					estimator.run([(ansatz("fail"), observable, [0.1])]).result()
				estimator.run([(ansatz(), observable, [0.1])]).result()
				raise QFwError("the task gives up")
		self.assertIn("gives up", str(raised.exception))
		self.assertEqual(len(self.marked("shutdown")), 1)
		self.assertEqual(len(self.clients_left()), 1)

	def test_child_crash(self):
		with QFwClient(self.session) as qfw:
			with self.assertRaisesRegex(QFwError, "exited with status 3"):
				qfw.estimator().run(
					[(ansatz("crash"), SparsePauliOp("ZZ"), [0.1])]).result()
		self.assertEqual(self.marked("shutdown"), [])
		[left] = self.clients_left()
		self.assertTrue((left / "output.log").exists())

	def test_call_after_child_crash(self):
		with QFwClient(self.session) as qfw:
			pub = (ansatz("crash"), SparsePauliOp("ZZ"), [0.1])
			with self.assertRaises(QFwError):
				qfw.estimator().run([pub]).result()
			with self.assertRaisesRegex(QFwError, "closed"):
				qfw.estimator().run([pub]).result()

	def test_child_killed_between_calls(self):
		with QFwClient(self.session) as qfw:
			os.killpg(qfw._proc.pid, signal.SIGKILL)
			qfw._proc.wait()
			pub = (ansatz(), SparsePauliOp("ZZ"), [0.1])
			with self.assertRaisesRegex(QFwError, "exited with status"):
				qfw.estimator().run([pub]).result()
		self.assertEqual(len(self.clients_left()), 1)

	def test_request_the_child_cannot_unpickle(self):
		with QFwClient(self.session) as qfw:
			with self.assertRaisesRegex(QFwError, "ModuleNotFoundError"):
				qfw._call("estimator", {}, [NotInTheChild()], {})
			qfw.estimator().run(
				[(ansatz(), SparsePauliOp("ZZ"), [0.1])]).result()
		self.assertEqual(len(self.marked("shutdown")), 1)

	def test_hung_child_is_killed(self):
		started = time.time()
		with QFwClient(self.session, call_timeout=2) as qfw:
			pid = qfw._proc.pid
			with self.assertRaisesRegex(QFwError, "no answer"):
				qfw.estimator().run(
					[(ansatz("hang"), SparsePauliOp("ZZ"), [0.1])]).result()
		self.assertLess(time.time() - started, 60)
		with self.assertRaises(ProcessLookupError):
			os.killpg(pid, 0)
		self.assertEqual(len(self.clients_left()), 1)

	def test_connect_failure(self):
		with self.assertRaisesRegex(QFwError, "no QPM for provider broken"):
			QFwClient(self.session, provider="broken")
		self.assertEqual(len(self.clients_left()), 1)

	def test_failed_shutdown_keeps_directory(self):
		with QFwClient(self.session, provider="bad-shutdown"):
			pass
		[left] = self.clients_left()
		self.assertIn("would not close", (left / "output.log").read_text())

	def test_close_twice(self):
		qfw = QFwClient(self.session)
		qfw.close()
		qfw.close()
		with self.assertRaisesRegex(QFwError, "closed"):
			qfw.estimator().run(
				[(ansatz(), SparsePauliOp("ZZ"), [0.1])]).result()

	def test_session_round_trip(self):
		self.assertNotIn("SLURM_PROCID", self.session.environment)
		self.assertNotIn("DEFW_LISTEN_PORT", self.session.environment)
		path = self.tmp / "session.json"
		self.session.save(path)
		self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
		loaded = QFwSession.load(path)
		self.assertEqual(loaded.environment, self.session.environment)
		env = loaded.child_environment(self.tmp / "c" / "logs")
		self.assertNotEqual(env["DEFW_LISTEN_PORT"], "4000")
		self.assertEqual(env["DEFW_LOG_DIR"], str(self.tmp / "c" / "logs"))
		self.assertTrue(env["DEFW_AGENT_NAME"].endswith("_c"))
		self.assertEqual(json.loads(env["QFW_RESERVATIONS"]),
						 [["nwqsim", "r-1"]])


class LaunchTest(unittest.TestCase):
	def args(self, **overrides):
		values = dict(
			sc_cfg="qfw-cluster", cpus_per_node=4, worker_in_master_cpus=0,
			worker_in_master_memory=2048, working_dir="/w", log_dir="/l",
			log_level="off", pythonpath=["/app/src"], launch_option=[],
			application="/x/app.py", arguments=["--flag", "1"])
		values.update(overrides)
		return SimpleNamespace(**values)

	def test_master_is_not_a_worker(self):
		command = build_command(self.args(), ["c1", "c2", "c3"], "c1")
		self.assertIn("--worker_nodes=c2 c3", command)
		self.assertIn("--worker_in_master_cpus=0", command)
		self.assertIn("--pythonpath=/x:/app/src", command)
		self.assertEqual(command[-3:], ["/x/app.py", "--flag", "1"])

	def test_single_node_runs_tasks_on_the_master(self):
		command = build_command(self.args(), ["c1"], "c1")
		self.assertIn("--worker_nodes=", command)
		self.assertIn("--worker_in_master_cpus=4", command)


class LaunchMainTest(unittest.TestCase):
	def test_session_reaches_compss_and_is_removed(self):
		tmp = Path(tempfile.mkdtemp())
		seen = {}

		def fake_run(command, **kwargs):
			if command[0] == "scontrol":
				return SimpleNamespace(stdout="c1 c2\n", returncode=0)
			path = Path(kwargs["env"][SESSION_ENV])
			seen["session"] = QFwSession.load(path)
			seen["path"] = path
			return SimpleNamespace(returncode=7)

		session = QFwSession({"QFW_RESERVATIONS": "x"}, tmp / "qfw")
		environment = {"SLURM_JOB_NODELIST": "c[1-2]", "SLURM_JOB_ID": "5"}
		self.addCleanup(os.chdir, os.getcwd())
		os.chdir(tmp)
		with mock.patch.object(launch.subprocess, "run", fake_run), \
				mock.patch.object(QFwSession, "capture", return_value=session), \
				mock.patch.object(launch.socket, "gethostname", return_value="c1"), \
				mock.patch.dict(os.environ, environment):
			status = launch.main(["--working-dir", "w", "/x/app.py"])
		self.assertEqual(status, 7)
		self.assertTrue(seen["path"].is_absolute())
		self.assertEqual(seen["session"].environment["QFW_RESERVATIONS"], "x")
		self.assertFalse(seen["path"].exists())


if __name__ == "__main__":
	unittest.main()
