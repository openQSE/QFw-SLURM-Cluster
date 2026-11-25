#!/usr/bin/env python3
"""Run a circuit's sampling as a qfw-slurm job and return its counts.

This is the quantum stage of a workflow done the way QFw's Slurm integration
expects it: the workflow submits a Slurm job that carries the qfw-slurm
options, qfw-slurm reserves the QPM at allocation time, and the job runs the
sampler application under qfw-setup, qfw-srun and qfw-teardown. The
workflow only ever submits, waits and reads a file; it holds no QFw state.

Library use, from a Prefect task or anywhere else on the controller:

    from qfw_slurm_sampler import run_sampler_job
    record = run_sampler_job(circuit, shots=1024, qpu="nwqsim",
                             work_dir="/workspace/home/user-a/qfw_jobs")
    counts = record["counts"]

Command-line smoke test with a GHZ circuit:

    python3 qfw_slurm_sampler.py --qpu nwqsim --qubits 5 --shots 1024
"""

import argparse
import datetime
import gzip
import json
import os
import pathlib
import shlex
import subprocess
import time
import uuid

from qiskit import QuantumCircuit, qpy

HERE = pathlib.Path(__file__).resolve().parent
TERMINAL_STATES = ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL",
                   "OUT_OF_MEMORY", "BOOT_FAIL", "DEADLINE", "PREEMPTED")

# The job script. The qfw-slurm options go to sbatch, never to srun; see
# qfw-slurm's Workflow Manager Integration Guide. The lifecycle below is the
# guide's: activate, qfw-setup, qfw-srun the application, qfw-teardown.
# qfw-srun runs a Python application from its path, so the sampler is named
# directly, not through an interpreter.
JOB_TEMPLATE = """#!/usr/bin/env bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --account={account}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time={walltime}
#SBATCH --output={job_dir}/slurm.out
#SBATCH --error={job_dir}/slurm.err
#SBATCH --qpu={qpu}
#SBATCH --workload-kind=quantum
#SBATCH --circ-count=1
#SBATCH --max-qubits={max_qubits}
#SBATCH --max-depth={max_depth}
#SBATCH --max-shots={max_shots}

set -euo pipefail

QFW_PREFIX="{qfw_prefix}"
QFW_VENV="{qfw_venv}"
export QFW_SHARED_ROOT="${{QFW_SHARED_ROOT:-/workspace/qfw-container-base}}"
export QFW_RUN_BASE_DIR="{job_dir}/qfw-run"
export DEFW_LOG_LEVEL="${{DEFW_LOG_LEVEL:-error}}"
export DEFW_PY_LOGLEVEL="${{DEFW_PY_LOGLEVEL:-critical}}"

mkdir -p "${{QFW_RUN_BASE_DIR}}"
cd "{job_dir}"

source "${{QFW_PREFIX}}/bin/qfw-activate" --venv "${{QFW_VENV}}"

unset DEFW_AGENT_NAME
unset DEFW_AGENT_TYPE
unset DEFW_DISABLE_DIRSVC
unset DEFW_EXTERNAL_EXPERIMENTS_PATH
unset DEFW_LISTEN_PORT
unset DEFW_LOG_DIR
unset DEFW_PARENT_ADDR
unset DEFW_PARENT_HOSTNAME
unset DEFW_PARENT_NAME
unset DEFW_PARENT_PORT
unset DEFW_SHELL_TYPE
unset DEFW_TELNET_PORT

qfw_runtime_ready=0
cleanup() {{
    local rc=$?
    trap - EXIT
    if [[ "${{qfw_runtime_ready}}" == "1" ]]; then
        qfw-teardown || true
    fi
    qfw-deactivate || true
    exit "${{rc}}"
}}
trap cleanup EXIT

setup_args=()
if [[ -n "${{QFW_SITE_CONFIG:-}}" ]]; then
    setup_args+=(--site-config "${{QFW_SITE_CONFIG}}")
fi
qfw-setup "${{setup_args[@]}}"
qfw_runtime_ready=1

qfw-srun "{sampler}" \\
    --circuit "{circuit_file}" \\
    --shots {shots} \\
    --provider "{provider}" \\
    --out "{counts_file}" {sampler_args}
"""


def render_job_script(**fields):
    return JOB_TEMPLATE.format(**fields)


def _run(command, **kwargs):
    return subprocess.run(command, check=True, text=True,
                          capture_output=True, **kwargs).stdout


def _job_state(job_id, submitted_after):
    # Slurm numbers jobs from 1 again when its controller state is reset, as
    # a cluster recreate does, but the accounting database keeps the old
    # jobs. Until the new job reaches the database, `sacct -j` shows the old
    # job with the same number, often COMPLETED. --starttime leaves out jobs
    # that ended before this one was submitted.
    out = _run(["sacct", "-j", str(job_id), "-X", "-n", "-P",
                "--starttime", submitted_after,
                "-o", "State,ExitCode"])
    line = out.strip().splitlines()[0] if out.strip() else ""
    if not line:
        return None, None
    state, exit_code = line.split("|")[:2]
    return state.split()[0], exit_code


def run_sampler_job(circuit, *, shots, qpu, work_dir, provider=None,
                    partition="normal", account="qfw-test", walltime="00:10:00",
                    max_depth=None, qfw_prefix="/opt/openqse/qfw",
                    qfw_venv="/opt/openqse/qfw-venv", sampler=None,
                    sampler_args=None,
                    poll_interval=5.0, timeout=1800.0, logger=print):
    """Submit the sampling of ``circuit`` as a qfw-slurm job and return the
    sampler's record (counts plus metadata). Raises on failure."""
    provider = provider or qpu
    sampler = pathlib.Path(sampler) if sampler else HERE / "qfw_sampler.py"
    sampler_args = sampler_args or []
    sampler_args_text = " ".join(
        shlex.quote(str(value))
        for value in sampler_args
    )
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    job_dir = pathlib.Path(work_dir).expanduser().resolve() / \
        f"qfw_{stamp}_{uuid.uuid4().hex[:8]}"
    job_dir.mkdir(parents=True, exist_ok=False)

    circuit_file = job_dir / "circuit.qpy.gz"
    with gzip.open(circuit_file, "wb") as handle:
        qpy.dump(circuit, handle)
    counts_file = job_dir / "counts.json"

    depth = circuit.depth()
    script = render_job_script(
        job_name="qfw-sampler",
        partition=partition,
        account=account,
        walltime=walltime,
        job_dir=job_dir,
        qpu=qpu,
        max_qubits=circuit.num_qubits,
        # Upper bounds for admission; the QPM's transpilation may deepen the
        # circuit, so leave headroom unless the caller knows better.
        max_depth=max_depth or max(2 * depth + 16, 32),
        max_shots=shots,
        qfw_prefix=qfw_prefix,
        qfw_venv=qfw_venv,
        sampler=sampler,
        circuit_file=circuit_file,
        shots=shots,
        provider=provider,
        counts_file=counts_file,
        sampler_args=sampler_args_text,
    )
    script_file = job_dir / "qfw_sampler.slurm"
    script_file.write_text(script)

    # A minute early, in case this host's clock runs ahead of slurmdbd's.
    submitted_after = time.strftime("%Y-%m-%dT%H:%M:%S",
                                    time.localtime(time.time() - 60))
    job_id = _run(["sbatch", "--parsable", str(script_file)]).strip().split(";")[0]
    logger(f"qfw_slurm_sampler: job {job_id} submitted for {circuit.num_qubits} "
           f"qubits, {shots} shots on {qpu} ({job_dir})")

    deadline = time.time() + timeout
    state = None
    while time.time() < deadline:
        state, exit_code = _job_state(job_id, submitted_after)
        if state in TERMINAL_STATES:
            break
        time.sleep(poll_interval)
    else:
        subprocess.run(["scancel", str(job_id)], check=False)
        raise TimeoutError(f"job {job_id} did not finish within {timeout}s")

    if state != "COMPLETED" or not counts_file.exists():
        err = (job_dir / "slurm.err")
        tail = err.read_text()[-2000:] if err.exists() else ""
        raise RuntimeError(f"job {job_id} ended {state} ({exit_code}); "
                           f"stderr tail:\n{tail}")

    record = json.loads(counts_file.read_text())
    record["slurm_job_id"] = job_id
    record["job_dir"] = str(job_dir)
    logger(f"qfw_slurm_sampler: job {job_id} COMPLETED, "
           f"{sum(record['counts'].values())} shots, "
           f"reservation {record.get('reservation_id')}")
    return record


def ghz(num_qubits):
    circuit = QuantumCircuit(num_qubits, name="ghz")
    circuit.h(0)
    for qubit in range(num_qubits - 1):
        circuit.cx(qubit, qubit + 1)
    circuit.measure_all()
    return circuit


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--qpu", default="nwqsim",
                        help="public qfw-slurm QPU name (--qpu)")
    parser.add_argument("--provider", default=None,
                        help="QFwBackend provider selector (default: the QPU name)")
    parser.add_argument("--qubits", type=int, default=5,
                        help="GHZ size when no --circuit is given")
    parser.add_argument("--circuit", default=None,
                        help="QPY file to sample instead of the GHZ circuit")
    parser.add_argument("--shots", type=int, default=1024)
    parser.add_argument("--work-dir",
                        default=os.path.join(os.path.expanduser("~"), "qfw_jobs"))
    parser.add_argument("--partition", default="normal")
    parser.add_argument("--account", default="qfw-test")
    parser.add_argument("--walltime", default="00:10:00")
    parser.add_argument("--qfw-prefix", default="/opt/openqse/qfw")
    parser.add_argument("--qfw-venv", default="/opt/openqse/qfw-venv")
    args = parser.parse_args()

    if args.circuit:
        with (gzip.open if args.circuit.endswith(".gz") else open)(args.circuit, "rb") as handle:
            circuit = qpy.load(handle)[0]
    else:
        circuit = ghz(args.qubits)

    record = run_sampler_job(
        circuit, shots=args.shots, qpu=args.qpu, provider=args.provider,
        work_dir=args.work_dir, partition=args.partition, account=args.account,
        walltime=args.walltime, qfw_prefix=args.qfw_prefix,
        qfw_venv=args.qfw_venv)
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
