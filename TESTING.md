# Testing the QRMI/QDMI shim (`svc_lib_qpm`)

This describes how to validate the QFw QRMI/QDMI bifurcation front-end
(`services/svc_lib_qpm`) in the containerized SLURM cluster. There are two
tiers:

1. **Local smoke** — routing + `qhw` normalization, no credentials. Runs
   anywhere; this is the everyday check.
2. **Hardware introspection** — real device introspection through *both* QDMI
   and QRMI against an IQM system, confirming they yield the same `qhw` shape.
   Requires IQM credentials.

The test vehicle is `shared-dir/shim-smoke.sbatch`, submitted as a SLURM job on
the `quantum` partition.

## Prerequisites

- Docker + Docker Compose.
- This repo (`QFw-SLURM-Cluster`) checked out.
- A QFw checkout at `shared-dir/QFw`, which the cluster bind-mounts. QFw is a
  separate repository and not a submodule of this one, so clone it yourself:

```bash
git clone --recursive https://github.com/openQSE/QFw.git shared-dir/QFw
```

`--recursive` is required, since the shim needs the `qhw-*` packages and DEFw.
QFw declares its submodules over SSH, so without GitHub SSH access to openQSE,
rewrite them to HTTPS first:

```bash
git config --global url."https://github.com/".insteadOf "git@github.com:"
```

## Build

```bash
./do_configure.sh
./do_build.sh        # image: QRMI C library + SPANK plugin, OpenMPI, libfabric
./do_startup.sh      # start the cluster
./do_qfw_build.sh    # QFw + DEFw + the shim venv, onto the shared mount
```

The order matters. QFw is not baked into the image, so `do_build.sh` only builds
the image, and `do_qfw_build.sh` builds your `shared-dir/QFw` checkout *inside*
the running cluster. That is why the cluster has to be started between them.
`do_qfw_build.sh` also installs the QRMI and QDMI Python bindings into the
shared-mount venv, pinned to the `QRMI_VERSION` the image exports.

The shim Python is bind-mounted, so after the first build, code changes in
`shared-dir/QFw/services/svc_lib_qpm` are picked up without rebuilding.

## Tier 1 — Local smoke (no credentials)

The smoke test resolves a device descriptor for `ornl-iqm-20q`, which it reads
from a device-access config. That file is gitignored and the install tree ships
no default, so copy the example once:

```bash
cp shared-dir/iqm-device-access.yaml.example shared-dir/iqm-device-access.yaml
```

Leave the contents as they are. Tier 1 reads only the descriptor fields
(`provider`, `provider-device-id`, `libraries`, `preference`, `caps`), so the
`url` and `credential-db` values in the example are never dereferenced and no
credentials or network access are needed. Skipping this step fails with:

```text
QFw device access config file was not found: ...
```

Then, with the cluster running:

```bash
docker exec -w /workspace/qfw-container-base slurmctld sbatch shim-smoke.sbatch
# read the result:
cat shared-dir/shim-smoke.<jobid>.out
```

Keeping a baseline to diff against is the usual way to check an upgrade changed
nothing. Copy it to a name of your own first:

```bash
cp shared-dir/shim-smoke.<jobid>.out shared-dir/shim-smoke-baseline.out
```

SLURM job ids restart from 1 whenever the cluster is recreated, so
`shim-smoke.<jobid>.out` names are reused and a baseline left under a job-id
name is eventually overwritten by a later run. `shared-dir/*.out` is
gitignored, so these files are local either way.

Expected (abridged):

```
[shim-smoke] [iqm-q20]  get_device_info            -> qdmi
[shim-smoke] [iqm-q20]  run_circuit                -> qrmi
[shim-smoke] [ibm-heron] introspection (device_info/coupling) -> qrmi (QRMI-only resource still introspects)
[shim-smoke] [ibm-heron] get_calibration_snapshot -> NOT_IMPLEMENTED (gap map: no calibration-capable library wired)
[shim-smoke] backend->qhw normalization: device(4 qubits) + coupling(3 edges, 3 ops), schema-valid
[shim-smoke] live introspection: skipped (set QFW_QC_URL + QFW_API_KEY to enable)

SHIM BIFURCATION + INTROSPECTION SMOKE: PASS
```

This exercises descriptor-driven routing (introspection is composable — QDMI
preferred, QRMI also serves it; execution pinned to QRMI), the gap map, and the
shared `BackendV2 -> qhw` normalizer (with real `jsonschema` validation) — all
without touching hardware.

## Tier 2 — Hardware introspection (IQM credentials)

Provide the same credentials the native IQM service uses, then re-run the
smoke. The live section auto-runs **both** the QDMI and QRMI legs and compares
them.

> For a full walkthrough against the ORNL q20 — token setup, remote access over
> an SSH tunnel, and circuit **execution** — see [IQM-ACCESS.md](IQM-ACCESS.md).
> The env vars below work for this sbatch, but they do **not** reach the QPM
> service that executes circuits; that path reads the device-access file.

Credentials (env vars, or the standard `dev-config` device-access file):

- `QFW_QC_URL` — IQM endpoint (e.g. `https://resonance.iqm.tech`)
- `QFW_API_KEY` — IQM token
- `QFW_IQM_QUANTUM_COMPUTER` — device / qc_alias, read only by the native
  `svc_iqm_qpm` path. The **shim** takes its alias from `provider-device-id` in
  the device-access config and ignores this variable.

```bash
docker exec \
  -e QFW_QC_URL="https://resonance.iqm.tech" \
  -e QFW_API_KEY="<token>" \
  -e QFW_IQM_QUANTUM_COMPUTER="emerald:mock" \
  -w /workspace/qfw-container-base slurmctld sbatch shim-smoke.sbatch
```

Tip: start with `emerald:mock` — it exercises the full real API path against a
mock device before pointing at a physical QPU.

Expected additional lines (replacing the "skipped" line above):

```
[shim-smoke] live qdmi -> qhw-device-v1 (N qubits) + qhw-coupling-v1 (M edges)
[shim-smoke] live qrmi -> qhw-device-v1 (N qubits) + qhw-coupling-v1 (M edges)
[shim-smoke] cross-library: QDMI and QRMI agree on qhw shape (N qubits, M edges)
```

The `cross-library: ... agree` line is the key result: introspection returns
one normalized shape regardless of which library served it. Sanity-check that
`N` / `M` match the device's known topology.

### Note on the QRMI leg

QRMI's introspection needs QRMI's own resource environment, which the
`spank_qrmi` plugin populates inside a reservation. If that isn't configured,
the QRMI leg prints:

```
[shim-smoke] live QRMI introspection: unavailable (...) -- needs QRMI resource env (SPANK reservation)
```

and the test still passes on the QDMI leg — that is expected. To exercise the
QRMI leg too, run inside a reservation with `spank_qrmi` active, or set QRMI's
resource env per QRMI's IQM example.

## What to capture

The full `shared-dir/shim-smoke.<jobid>.out`, in particular: the qubit/edge
counts from each leg, whether the QRMI leg ran or reported unavailable, and
whether the `cross-library: ... agree` line appeared.
