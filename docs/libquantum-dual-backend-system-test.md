# Libquantum Dual-Backend System Test

This procedure builds QFw, libquantum, and the Qiskit compiler from sibling
checkouts, then runs the same installed QFw example through the legacy and V2
backend paths in one qfw-slurm allocation. It is simulator qualification, not
physical-device evidence.

The frozen simulator qualification inputs are QFw `daae4a59e47c`, qfw-slurm
`e940e0a60022`, QFw-SLURM-Cluster `61ef996c7e97`, libquantum `62ec4a809a32`,
libquantum-compiler-qiskit `698062f20752`, and Qiskit `2.2.3`. QFw owns the QPM
query and qhw implementations at the same `daae4a59e47c` revision.

## Freeze the sources

Record the exact commits before building.

```bash
git -C /path/to/QFw rev-parse HEAD
git -C /path/to/qfw-slurm rev-parse HEAD
git -C /path/to/QFw-SLURM-Cluster rev-parse HEAD
git -C /path/to/libquantum rev-parse HEAD
git -C /path/to/libquantum-compiler-qiskit rev-parse HEAD
```

Set `QFW_CONTAINER_BASE` to a host directory containing checkouts named `QFw`,
`libquantum`, `libquantum-compiler-qiskit`, and `mqt-core`. Run
`./do_configure.sh` again after changing the mount, then start and provision the
cluster.

```bash
./do_build.sh
./do_startup.sh
./do_qfw_build.sh --clean
./test_scripts/test_libquantum_integration.sh
```

`do_qfw_build.sh` builds wheels for libquantum and the Qiskit compiler, installs
them into the shared QFw virtual environment, and verifies the packaged
`compiler.json`. QFw activation and qfw-slurm's `QFW_RESERVATIONS` injection
remain unchanged.

## Run through Slurm

Start the site directory, NWQSim DVM, NWQSim QPMd, and qfw-slurm gateway using
the existing cluster recipes. Submit the retained system job as a non-root test
user.

```bash
./do_ssh.sh --user user-a
sbatch /mnt/libquantum-dual-backend.sbatch
squeue --me
```

The job requests NWQSim through qfw-slurm. It verifies the exact package
versions and compiler manifest from an ordinary Slurm application process,
runs `qfw_qiskit_simple.sh` once with `--backend-api legacy` and once with
`--backend-api v2`, and fails if either selected class is absent or one path
falls back to the other.

The output must end with `QFW DUAL BACKEND SYSTEM TEST: PASS`. Retain the main,
legacy, and V2 logs after removing access tokens, provider credentials, remote
service objects, and environment dumps. The test logs may retain reservation
service IDs and operation IDs needed for correlation.

## Regression and cleanup

Run the qfw-slurm gateway and protocol gates and the QFw isolated gates.

```bash
cd /path/to/qfw-slurm
PYTHONPATH=gateway python3 -m pytest -q tests/gateway tests/inspect
ctest --test-dir build --output-on-failure

cd /path/to/QFw
PYTHONPATH=tests/mock:backends:services:service-apis:setup \
  python3 -m pytest -q \
  tests/mock/test_qfw_backend_smoke.py tests/mock/test_qfw_job.py
```

After collecting sanitized logs, leave the allocation and stop the development
cluster with `./do_stop.sh`. A physical-device run requires a separate retained
log and must not be inferred from this simulator result.
