# Run a Workflow's Quantum Stage Through qfw-slurm

This recipe runs one circuit's sampling as a Slurm job that carries the
qfw-slurm options, so that qfw-slurm reserves the QPM at allocation time, the
site QPM service executes the circuit, and the job shows up in QFw's
telemetry. It is the quantum stage of a workflow done the way QFw's Slurm
integration expects, and it works offline against the NWQSim QPM. A
workflow manager such as Prefect only submits the job, waits for it and
reads a file back; it holds no QFw state of its own.

The cluster ships two files for it under `prefect/`, installed in the Prefect
workspace at `/workspace/qfw-container-base/qfw-prefect/bin/` by
`tools/provision-prefect.sh`:

| File | Role |
| --- | --- |
| `qfw_sampler.py` | The application step. Runs under `qfw-srun`, reads a QPY circuit, runs it on `QFwBackend` with the reservation qfw-slurm placed in `QFW_RESERVATIONS`, writes `counts.json`. |
| `qfw_slurm_sampler.py` | The submitter. Renders the job script with the six qfw-slurm options, submits it with `sbatch`, waits through `sacct`, returns the counts record. Also a command-line smoke test. |

The job script follows qfw-slurm's
[Workflow Manager Integration Guide](https://github.com/openQSE/qfw-slurm/blob/main/docs/workflow-manager-integration.md):
the qfw-slurm options go to `sbatch` only, and the application runs between
`qfw-setup` and `qfw-teardown` through `qfw-srun`.

## Prerequisites

- The cluster is running and provisioned, and `tools/provision-prefect.sh`
  has run (it installs the two files and the Python environment the
  submitter uses).
- The site service plane is up: `qfw-site-services start`. The directory,
  the QPM named by `--qpu` and the qfw-slurm gateway must report `UP`.
- The public QPU name is one the site maps in
  `config/qfw-slurm/plugin.conf`. For an offline run use `nwqsim`.
- That mapping holds one service per public name. As of 2026-10-19 the
  tracked file maps both AWS names to `shim-aws-qpm`, and qfw-slurm's
  driver and SPANK plugin reject a repeated service id, so every `--qpu`
  job stays pending with "resource mappings must be unique". Until the
  mapping is fixed, comment one of the two out on `slurmctld` and on
  `c1` to `c8`.

## Smoke Test

As an application user in `slurmctld`, sample a five-qubit GHZ circuit:

```bash
docker exec -u user-a slurmctld \
  /workspace/qfw-container-base/qfw-prefect/venv/bin/python \
  /workspace/qfw-container-base/qfw-prefect/bin/qfw_slurm_sampler.py \
  --qpu nwqsim --qubits 5 --shots 1024
```

The submitter prints the Slurm job id, waits, and prints the counts record.
Each run gets its own directory under `~/qfw_jobs/` holding the circuit,
the rendered `qfw_sampler.slurm`, `slurm.out`, `slurm.err`, the QFw run
directory and `counts.json`. A healthy record shows the two GHZ outcomes,
the `nwqsim` service and the reservation id qfw-slurm created. On this
cluster the job takes about eight seconds end to end, of which the QPM
spends a tenth of a second executing.

qfw-slurm's own record of the allocation is in
`/var/lib/qfw-slurm/allocations/linux-<jobid>.json` on `slurmctld`, and its
gateway journal shows the evaluate, reserve and release operations for the
job.

Confirm the reservation and the telemetry:

```bash
docker exec slurmctld sacct -X --format=JobID,JobName,State,ExitCode,Elapsed,NodeList
```

In Grafana, the QFw Jobs dashboard lists the run, because the sampler goes
through the Qiskit client and the site QPM service like any QFw
application. Tempo holds its `qfw.app.job` trace.

## From a Workflow

A Prefect task, or any Python running on the controller with `sbatch` and
`sacct` on its path, calls the submitter as a library:

```python
import sys
sys.path.insert(0, "/workspace/qfw-container-base/qfw-prefect/bin")
from qfw_slurm_sampler import run_sampler_job

record = run_sampler_job(circuit, shots=100_000, qpu="nwqsim",
                         work_dir="/workspace/home/user-a/qfw_jobs")
counts = record["counts"]
```

`run_sampler_job` takes the partition, account, walltime, QFw prefix and venv
as keyword arguments, defaults to one node and one task, and derives the
admission bounds from the circuit: the qubit count exactly, the depth with
headroom for the QPM's transpilation, and the shot count. The record carries
the counts, the service and reservation ids, the Slurm job id and the job
directory.

For workflows that need a custom application-side sampler, pass its path with
`sampler` and any additional command-line arguments with `sampler_args`.
The submitter safely quotes these arguments before rendering the Slurm job.

For example:

```python
record = run_sampler_job(
    circuit,
    shots=shots,
    qpu="ibm-156-nh",
    work_dir="/workspace/home/user-a/qfw_jobs",
    sampler="/path/to/custom_sampler.py",
    sampler_args=["--option", "value"],
)
```

For the SQD closed loop, the walker uses this call to submit its quantum sampling
stage through QFw-SLURM. The returned counts are converted to a BitArray before
the workflow continues with recovery and SBD.

## What the Job Carries

The rendered script holds, in this order: the Slurm directives for the
partition, account, one node, one task, walltime and output files; the six
qfw-slurm options; QFw activation with the image's prefix and venv; a
`QFW_RUN_BASE_DIR` inside the job directory; `qfw-setup`; the sampler under
`qfw-srun`; and `qfw-teardown` on exit. The job structure is not specific to
a particular sampler, so the same shape serves any QFw application a workflow
wants to launch under a reservation.
