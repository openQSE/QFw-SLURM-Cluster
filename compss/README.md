# COMPSs Integration

This directory adds [COMPSs](https://compss.bsc.es) 3.4 to the cluster and
lets PyCOMPSs tasks use QFw QPMs. COMPSs runs the application's task graph
across the allocated nodes. A quantum task is an ordinary COMPSs task that
opens a QFw client, uses its Qiskit estimator or sampler, and closes it.

```text
 sbatch --qpu=nwqsim --circ-count=N ...    qfw-slurm reserves QPM capacity
   qfw-activate; qfw-setup                 QFw runtime for this job
   qfw-compss-launch app.py                captures the QFw session, starts
     │                                     the COMPSs master here and the
     │                                     workers on the other nodes via srun
     ├── classical @task                   plain Python on a worker core
     └── quantum @task
           QFwClient(session) ──pipes──► defw-python -m qfw_compss._server
           estimator.run(pubs)  ───────►   QFwEstimatorV2(QFwBackend).run()
                                ◄───────   PrimitiveResult       ──► QPM
   qfw-teardown
```

The example is chemistry_he's He4 FMO-VQE; see
[chemistry/README.md](chemistry/README.md).

## Why a child process

QFw's client, `qfw_qiskit.QFwBackend`, needs the DEFw runtime, and
`defw-python` provides it: Python embedded in a native process with its own
RPC listener threads. A COMPSs worker is an ordinary interpreter that forks
its executors, and a forked child loses those threads. So each `QFwClient`
starts one `defw-python` child with its own DEFw identity (a free listen
port, a unique agent name and a private log directory) and talks to it over a
pair of pipes.

The child stays up for as long as the client is open. It pays the DEFw
start-up and the QPM lookup once, about 6 s on an Apple silicon laptop,
however many estimator calls the task makes. Open one client per task, not
per call.

A task does not run under `qfw-srun`: a COMPSs worker starts it, usually on
another node. So `qfw-compss-launch` runs a small script under `qfw-srun`
once, before COMPSs starts, and saves the environment it sees as the job's
`QFwSession`, and tasks find it through `$QFW_COMPSS_SESSION`. Clients build
the child's environment from it. The launcher deletes the file when the
application ends, because the environment can hold tokens.

## Pieces

| Path | Role |
| --- | --- |
| `qfw_compss/session.py` | `QFwSession`: the environment `qfw-srun` gives an application, captured once per job, saved to a file and loaded by tasks. |
| `qfw_compss/client.py` | `QFwClient`, with Qiskit `BaseEstimatorV2` and `BaseSamplerV2` front ends. Works from any Python process. |
| `qfw_compss/_server.py` | The child. Runs `QFwBackend`, `QFwEstimatorV2` and `QFwSamplerV2`. |
| `qfw_compss/launch.py` | `qfw-compss-launch`, which captures the session and runs `launch_compss` inside the current allocation. |
| `qfw-cluster.cfg` | COMPSs configuration for these containers: Slurm, 4 CPUs, 6 GB, workers started by `srun`. |
| `chemistry/` | The He4 FMO-VQE example: the COMPSs application, its scripts, and a copy of chemistry_he's solver and data. |
| `tests/` | Tests that need neither QFw nor COMPSs. |

`enqueue_compss` is not used, because it writes its own batch script. That
leaves no room for the `--qpu` options or for the `qfw-setup` and
`qfw-teardown` lifecycle. `qfw-compss-launch` runs the part of that generated
script that matters from a batch script you write. Workers start through
`srun`, so they inherit the job environment, including `QFW_RESERVATIONS` and
`QFW_COMPSS_SESSION`, and need no SSH setup.

## Build

COMPSs is off by default. On a host with no prebuilt image, such as an arm64
laptop, build a slim image with COMPSs:

```bash
./do_configure.sh --slim --with-compss --image-tag rocky10.1-compss
./do_build.sh
./do_startup.sh
```

To add COMPSs to an image that is already built or pulled, use
`Dockerfile.compss`:

```bash
docker build -f Dockerfile.compss \
  --build-arg BASE_IMAGE=ghcr.io/openqse/qfw-slurm-cluster:<tag> \
  -t qfw-slurm-cluster:<tag>-compss .
```

Both install COMPSs from the release tarball, without tracing, the C binding,
Kafka or the monitor, and put `qfw_compss` into the QFw venv. COMPSs'
Python binding is built against the image's Python, the one the QFw venv and
`defw-python` use.

## Writing an application

```python
from pycompss.api.api import compss_wait_on
from pycompss.api.task import task
from qfw_compss import QFwClient

@task(returns=1)
def energy(ansatz, hamiltonian, params):
    with QFwClient(provider="nwqsim") as qfw:
        estimator = qfw.estimator(default_precision=1 / 64)   # 4096 shots
        result = estimator.run([(ansatz, hamiltonian, params)]).result()
        return float(result[0].data.evs)

energies = compss_wait_on(
    [energy(ansatz, hamiltonian, params) for params in points])
```

Import anything that loads `h5py`, such as PySCF or OpenFermion, inside the
task rather than at module level, because the module is also imported in the
COMPSs master. With `h5py` loaded there, a failed task leaves the master hung
until the job's time limit: the JVM calls `exit()`, HDF5's exit handler waits
for the GIL, and the main thread holds the GIL inside a COMPSs call that is
waiting for the JVM.

`QFwClient` loads the job's session from `$QFW_COMPSS_SESSION`, which
`qfw-compss-launch` sets. Do not pass a `QFwSession` as a task argument: COMPSs
would write the job's environment, which can hold tokens, to its working files.

A failed primitive call raises `QFwError` in the task and leaves the client
usable. Pass `call_timeout` to bound each call; by default a call waits as long
as QFw does. When anything fails, the client keeps its directory under
`~/.qfw-compss/<job id>-<time>/qfw/clients/` with the child's output and DEFw
logs, next to COMPSs' own logs in `.COMPSs/<job id>/`. It is outside the QFw
run directory because `qfw-teardown` removes that.

Size the reservation for the whole run: `--circ-count`, `--max-qubits`,
`--max-depth` and `--max-shots` form one envelope for the allocation, and
COMPSs never sees it. Whether a QPM enforces the envelope depends on its
admission policy. The site NWQ-Sim QPM here admits with an unlimited policy;
under an enforcing one, a task that goes past the envelope fails rather than
waits.

## Observing a run

None of these needs Extrae, which the image leaves out:

- **Task graph.** `qfw-compss-launch --launch-option=--graph=true` writes
  `monitor/complete_graph.dot` under `~/.qfw-compss/<job id>-<time>/.COMPSs/<job id>/`.
  Render it with Graphviz, which the image does not include, for example
  `dot -Tpng complete_graph.dot -o graph.png`.
- **Task summary.** `--launch-option=--summary` prints task counts per worker
  at the end of the job.
- **QFw telemetry.** Configure the cluster with `--telemetry`; see the
  [telemetry README](../telemetry/README.md). The QFw clients in COMPSs tasks
  inherit the variables through the session and report as `qfw-client`, and
  each estimator call is one `qfw.app.job` trace. Traces do not name the COMPSs
  task they came from.

A Paraver trace with `--tracing` needs Extrae, so it is not available.

## What has been tested

The example runs on a slim arm64 image against the site NWQ-Sim QPM. The full
image, amd64, `Dockerfile.compss` and the other QPMs are not tested. After a
failed job one small Python helper process of COMPSs stays on the master node.

## Tests

From `QFw-SLURM-Cluster`, with any Python that has Qiskit:

```bash
python3 -m unittest discover -s compss/tests -v
```

A stub `qfw_qiskit` and a `defw-python` shim stand in for QFw. The tests cover
the session, the child's lifecycle, the estimator and sampler, failed calls,
a crashed child, a failed connect and the `launch_compss` command line.

## Container-specific settings

- `qfw-compss-launch` passes `--cpu_affinity=disabled`. With automatic
  binding, the NIO worker exits with status 0 right after creating its CPU
  binder inside these containers, and the master only reports "connection
  refused".
- `qfw-cluster.cfg` adds the keys COMPSs' `default.cfg` lacks, such as
  `DEFAULT_FPGAS_PER_NODE`. `launch_compss` passes them unquoted into the
  worker command line, so one missing key makes the worker reject its
  arguments with "Incorrect number of parameters".
- Worker steps use `srun --overlap --mem=0`, so they share the job's CPUs
  with the batch step instead of waiting for them.
