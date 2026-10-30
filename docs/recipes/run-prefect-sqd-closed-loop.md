# Run the Prefect SQD Closed Loop

This recipe runs the Prefect-orchestrated SQD closed-loop workflow from
[qiskit-community/qcsc-prefect](https://github.com/qiskit-community/qcsc-prefect)
on the QFw-SLURM cluster.

The workflow optimizes LUCJ circuit parameters by differential evolution. Each
walker samples a quantum circuit, recovers configurations with
`qiskit-addon-sqd`, and runs the SBD Davidson solver as a Slurm MPI job.

The upstream workflow tutorial is:

[run_sbd_closed_loop_workflow_qfw-slurm.md](https://github.com/qiskit-community/qcsc-prefect/blob/main/docs/tutorials/run_sbd_closed_loop_workflow_qfw-slurm.md)

The cluster adds two host tools and a compose file so that the tutorial's
manual setup becomes repeatable:

| Piece | Purpose |
| --- | --- |
| `tools/provision-prefect.sh` | Build the workflow environment on the shared workspace. |
| `tools/prefect-sqd` | Start the Prefect server, create blocks, submit runs, and stop. |
| `docker-compose.prefect.yml` | Publish the Prefect UI on the Docker host. |

The workflow runtime runs as a non-root application user. The Prefect server,
served deployment, and workflow process live in `slurmctld`. Quantum stages
using `quantum_source=qfw` and the SBD solver run on the `normal` partition as
Slurm jobs.

## Prerequisites

- The QFw-SLURM cluster is available.
- The Docker host can reach PyPI and GitHub from inside `slurmctld`.
- For QFw execution, the cluster must be provisioned with the required device
  and credential configuration.

## Publish the Prefect UI

The Prefect server listens on port 4200 inside `slurmctld`.

To reach the UI from the Docker host, append the Prefect compose file to
`COMPOSE_FILE` in `.env`:

```text
COMPOSE_FILE=docker-compose.yml:docker-compose.telemetry.yml:docker-compose.prefect.yml
```

The mapping binds `127.0.0.1:4200` on the Docker host.

If this changes after the cluster has already been created, recreate
`slurmctld`, reprovision the QFw-SLURM cluster, and restart the QFw site
services.

If the cluster is running on a remote host, forward the Prefect UI port from
your local machine:

```bash
ssh -L 4200:127.0.0.1:4200 <user>@<remote-host>
```

Then open:

```text
http://127.0.0.1:4200
```

If the cluster is running locally, open the same URL directly without SSH port
forwarding.

The Prefect UI can be used to follow flow and task execution and inspect the
SQD walkers while their quantum and SBD stages run through Slurm.

A workflow can also be submitted from the deployment page with
**Run → Custom run** using the parameters described in the upstream tutorial.

The command-line workflow shown below remains available when the UI is not
needed.

## Run the fake-Lagos pipe-cleaner

The recommended first validation is a lightweight end-to-end run against the
QSA `fake_lagos` simulator.

This exercises the complete path:

```text
Prefect
  -> Slurm quantum job
  -> QFw
  -> QRMI/QSA
  -> fake_lagos
  -> result retrieval
  -> configuration recovery
  -> Slurm SBD solver
```

### Configure QFw access to fake Lagos

The QFw-SLURM cluster includes the `ibm-fake-lagos` device for use with the
QSA simulator.

The simulator-specific device-access and credential files are created as part
of the [IBM QSA simulator recipe](start-ibm-qsa-sim.md).

The [IBM job recipe](run-ibm-job.md) can be used as a standalone smoke test of
the QFw/QRMI/QSA path before running the full SQD workflow.

### Provision the Prefect workflow environment

Run:

```bash
tools/provision-prefect.sh
```

Provision the QFw-SLURM cluster before the Prefect environment so that
`user-a` and the Slurm environment are available before the workflow
environment is created.

`tools/provision-prefect.sh` is safe to rerun.

Its one root step creates the Prefect workspace:

```text
/workspace/qfw-container-base/qfw-prefect
```

`QFW_PREFECT_ROOT` can be used to override this location.

The shared mount's root belongs to whoever owns it on the Docker host, so the
application user cannot create the workspace directly. After creation, the
workspace is handed to `user-a`.

Everything else runs as `user-a` inside that workspace:

1. Clone `qcsc-prefect` to `qcsc-prefect/` at the commit this recipe was
   validated with. `QCSC_PREFECT_REF` can be used to override the revision.
2. Create `venv/` with the image venv's package set so that QFw's Qiskit,
   QRMI, and QDMI versions remain in force, then install Prefect, Ray, ffsim,
   PySCF, `qiskit-addon-sqd`, and the qcsc-prefect packages.
3. Override dependency constraints needed to reproduce the working QFw
   environment, including `ruamel-yaml` for compatibility with
   `pydantic_numpy` under NumPy 2.5 and Qiskit 2.5.2 from the QFw image.
4. Hold FastAPI below 0.150 because Prefect's server still uses an API removed
   by newer FastAPI versions.
5. Rebuild ffsim from source when its wheel fails with an illegal instruction,
   which can occur on Apple Silicon hosts.
6. Build the native SBD solver with the image's OpenMPI and OpenBLAS.
7. Install the quantum-stage SQD sampler and submitter under `bin/`.
8. Verify the environment under `qfw-activate`, which is how the workflow uses
   the venv.

The workspace lives on the shared mount and survives a container recreation.

### Start Prefect and serve the deployment

Start the Prefect server and deployment:

```bash
PREFECT_RAY_NUM_CPUS=4 tools/prefect-sqd start
```

For a lightweight pipe-cleaner, create the QFw block with a small shot count.
`SBD_SHOTS` controls the number of shots stored in the SQD runtime
options used by the workflow:

```bash
SBD_SHOTS=500 \
QFW_PREFECT_DEVICE=ibm-fake-lagos \
tools/prefect-sqd blocks
```
Increase `SBD_SHOTS` as needed for other validation or real-device runs.

Check the deployment:

```bash
tools/prefect-sqd status
```

`start` launches the Prefect server in the background and serves the
`riken-sqd-de/riken_sqd_de` deployment from a `nohup` process:

```text
/workspace/home/user-a/sbd-deploy.log
```

`PREFECT_RAY_NUM_CPUS` bounds the Ray task runner used to fan out the SQD
walkers.

`blocks` creates the Slurm SBD configuration and stores the SQD runtime options,
including the sampling shot count, in Prefect.

The generated cluster configuration is written to:

```text
/workspace/home/user-a/sbd_blocks.toml
```

It also registers the `QFwResource` block type and creates the `qfw-runner`
block for `QFW_PREFECT_DEVICE`.

The workflow loads this block for its QFw configuration, while quantum
sampling with `quantum_source=qfw` is submitted through `run_sampler_job()`
and QFw-SLURM.

### Run the H2 pipe-cleaner

The standard SQD workflow uses the N2 FCIDUMP by default. For the fake-Lagos
pipe-cleaner, use the smaller H2/STO-3G FCIDUMP.

Override the default N2 input with H2 for this pipe-cleaner:

```bash
SBD_FCIDUMP=algorithms/sbd/data/fcidump_H2_STO3G.txt \
tools/prefect-sqd run qfw 10000 1
```
The arguments to `run` are:

```text
<quantum-source> <SQD-subspace-dimension> <DE-iterations>
```

For this run:

```text
quantum source       = qfw
SQD dimension        = 10000
DE iterations        = 1
```

Each differential-evolution iteration launches four walkers.

Each walker generates its LUCJ circuit, submits the sampling stage as a Slurm
quantum job, executes it through QFw and QSA, retrieves the samples, and then
continues with configuration recovery, postselection, subsampling, and the
Slurm-based SBD solver.

Monitor the Slurm jobs with:

```bash
docker exec slurmctld squeue -u user-a
```

or:

```bash
docker exec slurmctld sacct -u user-a -X \
  --format=JobID,JobName%20,State,ExitCode,Elapsed,NodeList
```

A successful pipe-cleaner should:

1. submit each SQD sampling stage as a Slurm quantum job;
2. obtain the device-specific `fake_lagos` target through QFw telemetry;
3. construct a 7-qubit target with the Lagos coupling map;
4. execute the sampling stage through QSA;
5. retrieve the quantum result;
6. continue through configuration recovery; and
7. complete the Slurm-based SBD stage.

The H2 input is intended only as a lightweight end-to-end validation.

## Run on a real QFw device

After the simulator pipe-cleaner succeeds, configure a real QFw-supported
device.

The existing SQD example uses the N2 FCIDUMP by default:

```text
algorithms/sbd/data/fcidump_N2_MO.txt
```

### Configure QFw device access

Before provisioning the cluster, review:

```text
config/device-access.yaml
config/qpu-users.json
```

Select the device that should execute the quantum sampling stages and ensure
that its provider configuration and credentials are available before running
`tools/provision-qfw-cluster.sh`.

The cluster configuration includes `ibm-156-nh` as an IBM Quantum example.

For this device, set `provider-device-id` in `config/device-access.yaml` to the
IBM Quantum backend that should execute the circuits.

For example:

```yaml
ibm-156-nh:
  provider: ibm
  provider-device-id: <ibm-backend-name>
  resource-type: IBMQiskitRuntimeService
  url: https://quantum.cloud.ibm.com/api/v1
  credential-db: qpu-users.json
  libraries:
    - qrmi
  preference: qrmi
  execution-owner: qrmi
  caps:
    run_circuit: [qrmi]
    get_backend_info: [qrmi]
    get_task_timing: [qrmi]
    get_task_metadata: [qrmi]
```

The corresponding entry in `config/qpu-users.json` must contain enabled IBM
Quantum credentials for the Slurm application user and `ibm-156-nh`,
including the API key and service CRN.

For another QFw-supported device, configure the corresponding logical device,
provider mapping, and credentials required by that provider.

### Apply the real-device configuration

After updating `config/device-access.yaml` and `config/qpu-users.json`,
reprovision the QFw-SLURM cluster so that the updated configuration is copied
into the QFw service and compute containers:

```bash
tools/provision-qfw-cluster.sh
```

Enter the cluster environment and start the QFw site services:

```bash
./do_ssh.sh
qfw-site-services start
```

Then return to the Docker host:

```bash
exit
```

The Prefect workflow environment does not need to be reprovisioned solely
because the selected QFw device has changed.

### Create the real-device QFw block

For the included IBM example:

```bash
SBD_SHOTS=<shots> \
QFW_PREFECT_DEVICE=ibm-156-nh \
tools/prefect-sqd blocks
```

The command should report:

```text
Device ID: ibm-156-nh
```

For another configured QFw device:

```bash
SBD_SHOTS=<shots> \
QFW_PREFECT_DEVICE=<device-id> \
tools/prefect-sqd blocks
```

### Run the N2 SQD workflow

Run:

```bash
tools/prefect-sqd run qfw 10000 1
```

With no `SBD_FCIDUMP` override, `tools/prefect-sqd` uses:

```text
algorithms/sbd/data/fcidump_N2_MO.txt
```

Each walker generates its LUCJ circuit, submits the sampling stage as a Slurm
quantum job, executes it through the selected QFw device, retrieves the
samples, and continues with configuration recovery, postselection,
subsampling, and the Slurm-based SBD solver.

Monitor the workflow with:

```bash
docker exec slurmctld squeue -u user-a
```

or:

```bash
docker exec slurmctld sacct -u user-a -X \
  --format=JobID,JobName%20,State,ExitCode,Elapsed,NodeList
```

## How the qfw quantum source works

With `quantum_source=qfw`, each SQD walker submits its quantum sampling stage
as a Slurm job through `qfw_slurm_sqd_sampler.py`.

The Slurm job carries the QFw-SLURM reservation options, runs the SQD sampler
under `qfw-srun`, and executes the circuit through `QFwBackend`.

`tools/prefect-sqd` sets `QFW_SLURM_BIN` to the provisioned `bin/` directory
under the Prefect workspace by default.

This directory contains:

```text
qfw_slurm_sqd_sampler.py
```

installed by `tools/provision-prefect.sh`.

Set `QFW_SLURM_BIN` explicitly only when using a different helper location.

The workflow process itself does not hold the QFw reservation.

Instead:

1. Prefect creates the LUCJ circuit and applies the ffsim pre-initialization
   required before QPY serialization.
2. `qfw_slurm_sqd_sampler.py` writes the circuit to the job directory and
   submits a Slurm job.
3. QFw-SLURM reserves the selected QPM for the allocation.
4. The SQD sampler runs under `qfw-srun`.
5. The sampler obtains the device-specific `QFwBackend.target` through the
   QPM telemetry path.
6. The sampler performs target-aware transpilation and executes the circuit.
7. The sampler writes the counts record back to the shared job directory.
8. The Prefect walker converts the returned counts to a `BitArray`.
9. The workflow continues with configuration recovery and the SBD stage.

For IBM devices accessed through QRMI, the corresponding
`config/device-access.yaml` entry must provide:

```yaml
caps:
  run_circuit: [qrmi]
  get_backend_info: [qrmi]
  get_task_timing: [qrmi]
  get_task_metadata: [qrmi]
```

`get_backend_info` allows `QFwBackend.target` to obtain device-specific
metadata through the QPM telemetry path.

The SQD path uses the generic `run_sampler_job()` helper with a custom sampler
and `sampler_args` to pass the SQD transpilation options into the Slurm job.

The QFw-SLURM SQD path has been validated end to end with both a QSA
`fake_lagos` simulator and an IBM Quantum device accessed through QRMI.

Other QFw-supported devices may be used when their QPM provides the backend
target required for SQD transpilation.

## Optional: run with random sampling

The `random` quantum source can be used as a lightweight sanity test when QFw,
QSA, or real quantum hardware is not available.

This path validates the Prefect orchestration and classical SQD stages but
does not exercise QFw quantum execution.

Run:

```bash
tools/prefect-sqd run random 10000 1
```

The command uses the existing N2 example and waits for the workflow to
complete.

Each iteration launches four walkers, and each walker submits one SBD job.

Monitor the SBD jobs with:

```bash
docker exec slurmctld squeue -u user-a
```

or:

```bash
docker exec slurmctld sacct -u user-a -X \
  --format=JobID,JobName%20,State,ExitCode,Elapsed,NodeList
```

Job directories, generated `sbd_solver.slurm` scripts, and solver output are
stored under:

```text
/workspace/home/user-a/sbd_jobs/
```

The run's energies are available in the `sqd-telemetry` artifact.

The Prefect UI shows this artifact under the flow run, or it can be inspected
with:

```bash
prefect artifact inspect sqd-telemetry
```

On this cluster, the random-source command finishes in about half a minute.
The four walkers run in Ray workers, each SBD job spends about five seconds on
its node, and the four walkers report energies near `-134.77 Ha` for N2 with
the fast solver preset.

## Stop

Stop the served deployment and Prefect server with:

```bash
tools/prefect-sqd stop
```

The venv, qcsc-prefect checkout, blocks, and run history remain on the shared
workspace.
