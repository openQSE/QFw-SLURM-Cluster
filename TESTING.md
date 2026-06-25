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
- Both repos checked out at the branch under test:
  - this repo (`QFw-SLURM-Cluster`) on `shim-phase2` (or `main` once merged);
  - the QFw checkout the cluster bind-mounts, in `shared-dir/QFw`, on the
    matching branch.

```bash
# inner QFw checkout with the shim wiring (PR branch shown; use openQSE/main if merged)
git clone https://github.com/DougSO/QFw.git shared-dir/QFw
cd shared-dir/QFw && git checkout shim-phase2 && git submodule update --init --recursive && cd ../..
```

## Build

```bash
./do_configure.sh
./do_build.sh        # builds QRMI + iqm-qdmi[qiskit] + QFw + qhw; takes a while
```

The shim Python is bind-mounted, so after the first build, code changes in
`shared-dir/QFw/services/svc_lib_qpm` are picked up without rebuilding.

## Tier 1 — Local smoke (no credentials)

```bash
./do_startup.sh
docker exec -w /workspace/qfw-container-base slurmctld sbatch shim-smoke.sbatch
# read the result:
cat shared-dir/shim-smoke.<jobid>.out
```

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

Credentials (env vars, or the standard `dev-config` device-access file):

- `QFW_QC_URL` — IQM endpoint (e.g. `https://resonance.iqm.tech`)
- `QFW_API_KEY` — IQM token
- `QFW_IQM_QUANTUM_COMPUTER` — device / qc_alias (the q20 device, or
  `emerald:mock` for a low-risk first run against the real API)

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
