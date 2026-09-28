# Testing the QRMI/QDMI shim and `mqt-cc`

This describes how to validate the QFw QRMI/QDMI front-end
(`services/svc_lib_qpm`) and the MQT Compiler Collection (`mqt-cc`) in the
containerized Slurm cluster. The shim has two test tiers:

1. **Local smoke:** routing and `qhw` normalization, with no credentials and no
   network access. This is the everyday check.
2. **Hardware introspection:** real device introspection through both QDMI and
   QRMI against an IQM system, confirming they return the same `qhw` shape.
   Requires IQM credentials.

The shim test vehicle is `shared-dir/shim-smoke.sbatch`. It needs no Slurm
allocation and reads no Slurm environment, so both tiers run it directly inside
`slurmctld`.

## Build the cluster

```bash
./do_configure.sh --qfw-ref v0.1.0-rc.1 --qfw-slurm-ref v0.1.0-rc.1
./do_build.sh
./do_startup.sh
```

Omit the two ref options to build from `main`. Along with Slurm and the
simulators, the image installs QFw at `/opt/openqse/qfw`, and its Python
environment at `/opt/openqse/qfw-venv`, including the shim's QRMI and QDMI
dependencies.

## Which shim installation is tested

The image sets `QFW_PREFIX` and `QFW_VENV` to those paths, and
`shim-smoke.sbatch` honours both. So **by default the smoke tests the image
installation**, not a checkout of your own.

To test shim changes that are not in the image yet, build a developer override
and point the run at it, as described next.

## Optional: a developer override

Clone QFw and MQT Core onto the shared mount and build them inside the running
cluster:

```bash
git clone --recursive https://github.com/openQSE/QFw.git shared-dir/QFw
git clone https://github.com/munich-quantum-toolkit/core.git shared-dir/mqt-core
./do_qfw_build.sh
```

`--recursive` is required, because the shim needs DEFw and the `qhw-*` packages.
Check out the desired MQT Core ref before running `do_qfw_build.sh`. The image
provides the MLIR toolchain used to build its Python package.
QFw declares its submodules over SSH, so without GitHub SSH access to openQSE,
rewrite them to HTTPS before cloning:

```bash
git config --global url."https://github.com/".insteadOf "git@github.com:"
```

The override installs a copy of the sources into `shared-dir/qfw-install`, so
editing `shared-dir/QFw/services/svc_lib_qpm` changes nothing until you
reinstall. After the first build, reinstall without touching the venv:

```bash
./do_qfw_build.sh --skip-venv
```

## Tier 1: local smoke (no credentials)

The smoke test resolves a device descriptor for `ornl-iqm-20q` from a
device-access file. That file is gitignored and the install tree ships no
default, so copy the example once:

```bash
cp shared-dir/iqm-device-access.yaml.example shared-dir/iqm-device-access.yaml
```

Leave the contents as they are. Tier 1 reads only the descriptor fields
(`provider`, `provider-device-id`, `libraries`, `preference`, `caps`), so the
`url` and `credential-db` values in the example are never dereferenced. Without
the file the run fails with:

```text
QFw device access config file was not found: ...
```

This file is separate from `/etc/openqse/qfw/device/device-access.yaml`, which
the cluster's site QPM services read. The smoke runs in-process and does not use
those services.

With the cluster running, test the image installation:

```bash
docker exec -w /workspace/qfw-container-base slurmctld \
  bash shim-smoke.sbatch 2>&1 | tee shared-dir/shim-smoke.out
```

or a developer override:

```bash
docker exec -w /workspace/qfw-container-base \
  -e QFW_PREFIX=/workspace/qfw-container-base/qfw-install \
  -e QFW_VENV=/workspace/qfw-container-base/qfw-venv \
  slurmctld bash shim-smoke.sbatch 2>&1 | tee shared-dir/shim-smoke.out
```

Submitting the script with `sbatch` also works on a cluster that defines the
`quantum` partition and `qpu` GRES its `#SBATCH` lines request. Neither tier
needs an allocation, so running it directly avoids depending on that
configuration.

Keeping a baseline to diff against is the usual way to check that an upgrade
changed nothing:

```bash
cp shared-dir/shim-smoke.out shared-dir/shim-smoke-baseline.out
```

Both files match the gitignored `shared-dir/*.out`, so they stay local.

Expected (abridged):

```text
[shim-smoke] imported frontend + drivers + descriptor + QRC: OK
[shim-smoke] [iqm-q20]  get_device_info            -> qdmi
[shim-smoke] [iqm-q20]  run_circuit                -> qrmi
[shim-smoke] [ibm-heron] introspection (device_info/coupling) -> qrmi (QRMI-only resource still introspects)
[shim-smoke] [ibm-heron] get_calibration_snapshot -> NOT_IMPLEMENTED (gap map: no calibration-capable library wired)
[shim-smoke] QRC constructed from descriptor:          OK
[shim-smoke] FoMaC Device -> qhw normalization: device(3 qubits ['QB1', 'QB2', 'QB3']) + coupling(2 edges, 2 ops), schema-valid
[shim-smoke] live introspection: skipped (set QFW_QC_URL + QFW_API_KEY to enable)

SHIM BIFURCATION + INTROSPECTION SMOKE: PASS
```

This exercises descriptor-driven routing, where introspection is composable with
QDMI preferred and execution is pinned to QRMI, the gap map, and the FoMaC to
`qhw` normalizer with real `jsonschema` validation, all without touching
hardware.

## Tier 2: hardware introspection (IQM credentials)

Tier 2 is the same run with credentials, which enables the live section. It
introspects the device through both QDMI and QRMI and compares the results.

For getting a token and for remote access over an SSH tunnel, see sections 1
and 3 of [IQM-ACCESS.md](IQM-ACCESS.md).

The live section runs only when **both** `QFW_QC_URL` and `QFW_API_KEY` are set
in the environment. A credential file on its own is not enough: the drivers
could use it, but the script skips the live section without both variables.

The shim takes the device alias from `provider-device-id` in
`shared-dir/iqm-device-access.yaml`. It does not read `QFW_IQM_QUANTUM_COMPUTER`,
so to target a different device, change `provider-device-id`.

```bash
docker exec -w /workspace/qfw-container-base \
  -e QFW_QC_URL="https://qccsw.ccs.ornl.gov" \
  -e QFW_API_KEY="<token>" \
  slurmctld bash shim-smoke.sbatch 2>&1 | tee shared-dir/shim-smoke.out
```

Add the `QFW_PREFIX` and `QFW_VENV` options from Tier 1 to test a developer
override instead.

Expected additional lines, replacing the `skipped` line:

```text
[shim-smoke] live qdmi -> qhw-device-v1 (N qubits) + qhw-coupling-v1 (M edges)
[shim-smoke] live qrmi -> qhw-device-v1 (N qubits) + qhw-coupling-v1 (M edges)
[shim-smoke] cross-library: QDMI and QRMI agree on qhw shape (N qubits, M edges)
```

The `cross-library: ... agree` line is the key result. Introspection returns one
normalized shape regardless of which library served it. Check that `N` and `M`
match the device's known topology.

### When the QRMI leg reports unavailable

The shim fills QRMI's IQM endpoint and token variables from the same credentials
as the QDMI leg, so no Slurm reservation is needed, and this image does not load
the `spank_qrmi` plugin. If QRMI still fails, the leg prints:

```text
[shim-smoke] live QRMI introspection: unavailable (...) -- needs QRMI resource env (SPANK reservation)
```

That wording predates the shim supplying the environment itself. Treat it as a
QRMI failure and read the exception name in the parentheses. The run still
passes on the QDMI leg.

## `mqt-cc` smoke test (no credentials)

The image builds MQT Core from the ref selected by `do_configure.sh` and installs
it with Qiskit at `/opt/openqse/mqt-cc-venv`. This separate
environment allows the compiler and QFw to use different Qiskit versions.
`do_qfw_build.sh` builds the mounted MQT Core checkout into
`/workspace/qfw-container-base/mqt-cc-venv` unless `--skip-venv` is used.

`shared-dir/mqt-cc-smoke-test.sbatch` compiles a Qiskit circuit for
MQT Core's bundled IQM Garnet model to QIR Base. It uses QDMI to read the
model's capabilities and run the QIR on local DDSIM. The model is a
historical hardware snapshot, not live device discovery. This check makes no hardware calls and does not exercise
QFw submission or QRMI. The image build runs it too.

Test the image installation:

```bash
docker exec -w /workspace/qfw-container-base slurmctld \
  bash mqt-cc-smoke-test.sbatch 2>&1 | tee shared-dir/mqt-cc-smoke-test.out
```

For the developer environment, add
`-e MQT_CC_VENV=/workspace/qfw-container-base/mqt-cc-venv` to `docker exec`.
To test on a Slurm application node, submit from inside `slurmctld`:

```bash
cd /workspace/qfw-container-base
sbatch --wait mqt-cc-smoke-test.sbatch
```

The job uses the `normal` partition and needs no QPU allocation. Success ends
with `MQT-CC QIR SMOKE TEST: PASS`.

## What to capture

The full `shim-smoke.out`, in particular the qubit and edge counts from each
leg, whether the QRMI leg ran or reported unavailable, and whether the
`cross-library: ... agree` line appeared.

For the `mqt-cc` smoke test, capture `mqt-cc-smoke-test.out` or the Slurm job's
`mqt-cc-smoke-test.<job-id>.out`.
