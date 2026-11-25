"""The QFw application environment, captured once and shared with tasks.

``qfw-srun`` gives an application the environment recorded by ``qfw-setup``
plus the DEFw client settings for the directory service. A COMPSs task does
not run under ``qfw-srun``: a COMPSs worker starts it, usually on another node.
So ``qfw-compss-launch`` runs a small script under ``qfw-srun`` once, before
COMPSs starts, and saves the environment it sees. The application loads that
:class:`QFwSession` in its quantum tasks, through ``$QFW_COMPSS_SESSION``.
Do not pass it as a task argument: COMPSs would write the environment, which
can hold tokens, to its own working files.

The per-process DEFw identity (listen port, agent name, log directory) is not
kept. Several tasks run at once on one node and each is its own DEFw agent, so
every :class:`~qfw_compss.client.QFwClient` gets a fresh one.
"""

import json
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path


SESSION_ENV = "QFW_COMPSS_SESSION"

# Identity of the process or job step that was captured. A task runs in
# another process, often on another node, and must not inherit these.
_DROP_NAMES = frozenset({
	"_",
	"HOSTNAME",
	"OLDPWD",
	"PWD",
	"SHLVL",
	"DEFW_AGENT_NAME",
	"DEFW_LISTEN_PORT",
	"DEFW_LOG_DIR",
	"DEFW_TELNET_PORT",
	"SLURMD_NODENAME",
	"SLURM_CPUS_ON_NODE",
	"SLURM_GTIDS",
	"SLURM_LAUNCH_NODE_IPADDR",
	"SLURM_LOCALID",
	"SLURM_NODEID",
	"SLURM_PROCID",
	"SLURM_STEPID",
	"SLURM_TASK_PID",
	"SLURM_TOPOLOGY_ADDR",
	"SLURM_TOPOLOGY_ADDR_PATTERN",
})
_DROP_PREFIXES = (
	"COMPSS_",
	"OMPI_",
	"PMIX_",
	"PRTE_",
	"SLURM_PTY_",
	"SLURM_SRUN_COMM_",
	"SLURM_STEP_",
	"SSH_",
)


def _keep(name):
	return name not in _DROP_NAMES and not name.startswith(_DROP_PREFIXES)


class QFwSession:
	"""How a process outside ``qfw-srun`` reaches this job's QFw runtime.

	``environment`` is what ``qfw-srun`` gives an application, minus the
	per-process identity. ``scratch_dir`` holds one directory per client, with
	the child's output and DEFw logs; it is outside the QFw run directory
	because ``qfw-teardown`` deletes that.
	"""

	def __init__(self, environment, scratch_dir):
		self.environment = {k: v for k, v in environment.items() if _keep(k)}
		self.scratch_dir = str(scratch_dir)

	@classmethod
	def capture(cls, scratch_dir, run_dir=None, timeout=300):
		"""Record the environment ``qfw-srun`` gives an application.

		Call this inside the Slurm job, after ``qfw-activate`` and
		``qfw-setup``, from the batch step. ``qfw-compss-launch`` does it.
		"""
		qfw_srun = shutil.which("qfw-srun")
		if qfw_srun is None:
			raise RuntimeError(
				"qfw-srun is not on PATH; source qfw-activate first")
		scratch = Path(scratch_dir)
		scratch.mkdir(parents=True, exist_ok=True)
		with tempfile.TemporaryDirectory(dir=scratch) as tmp:
			out = Path(tmp) / "environment.json"
			command = [qfw_srun]
			if run_dir:
				command += ["--run-dir", str(run_dir)]
			command += ["--nodes=1", "--ntasks=1", "--",
						str(Path(__file__).with_name("_capture_env.py")),
						str(out)]
			subprocess.run(command, check=True, timeout=timeout)
			environment = json.loads(out.read_text())
		if not environment.get("QFW_RESERVATIONS"):
			raise RuntimeError(
				"QFW_RESERVATIONS is not set. Submit the job with --qpu so "
				"the qfw-slurm plugin reserves QPM capacity.")
		return cls(environment, scratch)

	def save(self, path):
		path = Path(path)
		tmp = path.with_suffix(path.suffix + ".tmp")
		# Private from the moment it exists: the environment can hold tokens.
		fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
		with os.fdopen(fd, "w") as stream:
			json.dump({"environment": self.environment,
					   "scratch_dir": self.scratch_dir}, stream)
		tmp.rename(path)

	@classmethod
	def load(cls, path=None):
		"""Load the session ``qfw-compss-launch`` saved for this job.

		``path`` defaults to ``$QFW_COMPSS_SESSION``, which the launcher sets
		for the COMPSs master and its workers.
		"""
		path = path or os.environ.get(SESSION_ENV)
		if not path:
			raise RuntimeError(
				f"{SESSION_ENV} is not set; start the application with "
				"qfw-compss-launch")
		data = json.loads(Path(path).read_text())
		return cls(data["environment"], data["scratch_dir"])

	def child_environment(self, log_dir):
		"""Environment for one ``defw-python`` child.

		The captured environment plus a DEFw identity of its own: a free
		listen port on this host, a unique agent name and a private log
		directory. The telnet port is left to defw-python's default.
		"""
		env = dict(self.environment)
		env["DEFW_LISTEN_PORT"] = str(_free_tcp_port())
		env["DEFW_AGENT_NAME"] = (
			f"qfw_compss_{socket.gethostname()}_{os.getpid()}_"
			f"{Path(log_dir).parent.name}")
		env["DEFW_LOG_DIR"] = str(log_dir)
		return env

	def __repr__(self):
		return (f"QFwSession(reservations="
				f"{self.environment.get('QFW_RESERVATIONS')!r}, "
				f"scratch_dir={self.scratch_dir!r})")


def _free_tcp_port():
	# The port is released before DEFw binds it, so another process could take
	# it first. The window is short, and qfw-srun picks ports the same way.
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
		sock.bind(("", 0))
		return sock.getsockname()[1]
