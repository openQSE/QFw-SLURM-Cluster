# Libquantum Dual-Backend System Test

This procedure builds QFw, libquantum, and the Qiskit compiler from sibling
checkouts, then runs the same installed QFw example through the legacy and V2
backend paths in one qfw-slurm allocation. It is simulator qualification, not
physical-device evidence.

The Amendment 03 simulator qualification used QFw `0db5e4b8c34b`, qfw-slurm
`e940e0a60022`, libquantum `6fc1428035da`, the Qiskit plugin
`fba35c827e5f`, and the MQT plugin `352aee7549b4`. The cluster integration
branch was rebased onto upstream `827fff2`. The installed environment used
Qiskit 2.5.2 and MQT Core 4.1.1.

## Freeze the sources

Record the exact commits before building.

```bash
git -C /path/to/QFw rev-parse HEAD
git -C /path/to/qfw-slurm rev-parse HEAD
git -C /path/to/QFw-SLURM-Cluster rev-parse HEAD
git -C /path/to/libquantum rev-parse HEAD
git -C /path/to/libquantum-compiler-qiskit rev-parse HEAD
git -C /path/to/libquantum-compiler-mqt rev-parse HEAD
```

Set `QFW_CONTAINER_BASE` to the OpenQSE workspace. The build uses QFw and
qfw-slurm from `QFw-release-v0.1/repos-main-sync`, and the three new
libquantum repositories from the workspace root. Run `./do_configure.sh` after
changing the mount, then start and provision the cluster.

```bash
./do_build.sh
./do_startup.sh
./do_qfw_build.sh --clean
./test_scripts/test_libquantum_integration.sh
```

`do_qfw_build.sh` builds wheels for libquantum, both compiler plugins, and
qfw-slurm. It installs them into the shared QFw virtual environment and
verifies both packaged manifests. QFw activation and qfw-slurm's canonical
`QFW_RESERVATIONS` injection remain unchanged.

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

Run the MQT route and managed-QFw gates from the same account.

```bash
sbatch --wait /mnt/libquantum-mqt-qri.sbatch
sbatch --wait /mnt/libquantum-phase12.sbatch
```

The MQT log must contain `target_reused: True` and
`LIBQUANTUM MQT QRI SYSTEM TEST: PASS`.

## Amendment 03 Results

NWQSim job 51 completed the legacy and V2 paths with exit status zero. Both
paths produced 1,024 GHZ samples using only `0000` and `1111`. V2 reported
`target_shared: true`; the legacy record did not gain a V2 target field.

NWQSim job 53 completed the MQT route with exit status zero. Direct target
access and two compilations returned the same target object. Managed-QFw job
54 passed its allocation-scoped integration test.

The deployed regression matrix reported 135 core tests passed with one skip,
16 Qiskit plugin tests passed, 15 MQT plugin tests passed, 12 focused V2 and
selector tests passed, four standard target tests passed, 60 legacy backend
and job tests passed with one skip, and 96 qfw-slurm tests passed with one
skip. Skips were not counted as qualification.

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
