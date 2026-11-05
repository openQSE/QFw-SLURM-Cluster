"""Start a PyCOMPSs application inside the current Slurm allocation.

``enqueue_compss`` writes and submits its own batch script, which leaves no
place for the qfw-slurm options (``--qpu``, ``--circ-count``, ...) or for the
``qfw-setup``/``qfw-teardown`` lifecycle around the run. This command is the
part of that generated script that matters, run from a batch script the user
writes::

	#SBATCH --qpu=nwqsim --circ-count=64 ...
	source "${QFW_INSTALL_PREFIX}/bin/qfw-activate" --venv "${QFW_VENV}"
	qfw-setup --site-config "${QFW_SITE_CONFIG}"
	qfw-compss-launch my_app.py
	qfw-teardown

It first captures the job's :class:`~qfw_compss.session.QFwSession` and saves
it where ``$QFW_COMPSS_SESSION`` points. The COMPSs master then runs here, on
the batch host. The remaining allocated nodes become COMPSs workers, started
by ``launch_compss`` through ``srun``, so they inherit that variable along
with the rest of the job environment.
"""

import argparse
import os
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

from .session import SESSION_ENV, QFwSession


def _allocated_hosts():
	nodelist = os.environ.get("SLURM_JOB_NODELIST")
	if not nodelist:
		raise SystemExit(
			"qfw-compss-launch: SLURM_JOB_NODELIST is not set; run it inside "
			"an sbatch or salloc allocation")
	output = subprocess.run(
		["scontrol", "show", "hostnames", nodelist],
		check=True, stdout=subprocess.PIPE, text=True).stdout
	return [host for host in output.split() if host]


def build_command(args, hosts, master):
	compss_home = os.environ.get("COMPSS_HOME", "/opt/COMPSs")
	launch = Path(compss_home) / "Runtime" / "scripts" / "user" / "launch_compss"
	workers = [host for host in hosts if host != master]
	worker_in_master = args.worker_in_master_cpus
	if not workers and worker_in_master == 0:
		# One node: it has to run tasks as well as the master.
		worker_in_master = args.cpus_per_node

	app = Path(args.application).resolve()
	pythonpath = [str(app.parent)] + [
		str(Path(path).resolve()) for path in args.pythonpath]
	command = [
		str(launch),
		f"--sc_cfg={args.sc_cfg}",
		f"--master_node={master}",
		f"--worker_nodes={' '.join(workers)}",
		f"--cpus_per_node={args.cpus_per_node}",
		f"--worker_in_master_cpus={worker_in_master}",
		f"--master_working_dir={args.working_dir}",
		f"--worker_working_dir={args.working_dir}",
		f"--log_dir={args.log_dir}",
		f"--log_level={args.log_level}",
		# Automatic binding makes the NIO worker exit silently, with status
		# 0, right after it creates its CPU binder inside these containers.
		# Pinning buys nothing on a node that is a 4-CPU cgroup anyway.
		"--cpu_affinity=disabled",
		"--lang=python",
		f"--pythonpath={':'.join(pythonpath)}",
	]
	if worker_in_master:
		command.append(f"--worker_in_master_memory={args.worker_in_master_memory}")
	command.extend(args.launch_option)
	command.append(str(app))
	command.extend(args.arguments)
	return command


def main(argv=None):
	parser = argparse.ArgumentParser(
		prog="qfw-compss-launch",
		description="Run a PyCOMPSs application across the current Slurm "
					"allocation, with the QFw runtime already set up.")
	parser.add_argument(
		"--sc-cfg", dest="sc_cfg", default="qfw-cluster",
		help="COMPSs supercomputer configuration (default: qfw-cluster)")
	parser.add_argument(
		"--cpus-per-node", type=int,
		default=int(os.environ.get("SLURM_CPUS_ON_NODE", "4")),
		help="COMPSs computing units per worker node")
	parser.add_argument(
		"--worker-in-master-cpus", type=int, default=0,
		help="Also run tasks on the master node with this many units")
	parser.add_argument(
		"--worker-in-master-memory", type=int, default=2048,
		help="Memory in MB for the worker in the master node")
	parser.add_argument(
		"--working-dir", default=None,
		help="Directory for COMPSs' working files and logs and the QFw "
			 "clients' logs (default: $HOME/.qfw-compss/<job id>-<time>)")
	parser.add_argument(
		"--qfw-run-dir", default=None,
		help="QFw run directory, when qfw-setup was given --run-dir")
	parser.add_argument(
		"--log-dir", default=None,
		help="COMPSs log directory (default: the working directory)")
	parser.add_argument(
		"--log-level", default="off", choices=["off", "info", "debug"])
	parser.add_argument(
		"--pythonpath", action="append", default=[],
		help="Extra directory for the application's PYTHONPATH")
	parser.add_argument(
		"--launch-option", action="append", default=[],
		help="Extra option passed verbatim to launch_compss")
	parser.add_argument(
		"--dry-run", action="store_true",
		help="Print the launch_compss command without running it")
	parser.add_argument("application")
	parser.add_argument("arguments", nargs=argparse.REMAINDER)
	args = parser.parse_args(argv)

	home = Path(os.environ.get("HOME", "."))
	job_id = os.environ.get("SLURM_JOB_ID", "nojob")
	# Job IDs restart when a cluster is rebuilt, and COMPSs refuses a log
	# directory that exists, so the job ID alone does not name a fresh one.
	stamp = time.strftime("%Y%m%dT%H%M%S")
	base = Path(args.working_dir or home / ".qfw-compss" / f"{job_id}-{stamp}")
	# Workers and clients run from other directories.
	base = base.resolve()
	args.working_dir = str(base / "compss")
	if args.log_dir is None:
		args.log_dir = str(base)

	hosts = _allocated_hosts()
	master = socket.gethostname().split(".")[0]
	if master not in hosts:
		raise SystemExit(
			f"qfw-compss-launch: this host ({master}) is not in the "
			f"allocation {hosts}; run it from the batch script")
	command = build_command(args, hosts, master)
	print("qfw-compss-launch:", shlex.join(command), flush=True)
	if args.dry_run:
		return 0

	base.mkdir(parents=True, exist_ok=True)
	session_file = base / "qfw-session.json"
	session = QFwSession.capture(base / "qfw", run_dir=args.qfw_run_dir)
	session.save(session_file)
	print(f"qfw-compss-launch: {session!r}", flush=True)
	env = dict(os.environ, **{SESSION_ENV: str(session_file)})
	try:
		return subprocess.run(command, env=env).returncode
	finally:
		# It holds the job's environment, which can include tokens.
		session_file.unlink(missing_ok=True)


if __name__ == "__main__":
	sys.exit(main())
