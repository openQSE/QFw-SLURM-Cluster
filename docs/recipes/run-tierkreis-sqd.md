# Run the Tierkreis SQD He2 demo

This example runs the
[Tierkreis scientific-computing demo](https://github.com/Quantinuum/tierkreis-sc-demo)
on the local QFw-SLURM cluster. The demo supplies the workflow and FCIDUMP
integrals; the cluster supplies Slurm, QFw and the NWQ-Sim service.

## Setup

Build the cluster image from this checkout first, then run from the repository
root:

```bash
./tools/setup-tierkreis-demo.sh
```

This starts the cluster if necessary. It checks for the
`nlohmann-json` header and `pkg-config` before installing the demo; an older
image without them must be rebuilt and its containers recreated first. Setup
clones the demo into the shared workspace, installs it
 dependencies on `slurmctld` and `c1`–`c8` (for warm caches), builds the native SBD
solver and starts the directory, NWQ-Sim and gateway services. It requires
GitHub and Python package index access.


After `./do_restart.sh --force-recreate`, run the setup again: the Python
environments are local to the containers. Do not recreate containers while
jobs are running.

## Run and compare

```bash
./test_scripts/test_tierkreis_sqd_he2.sh
```

This manual integration test starts the needed services and runs the demo's
`test/sqd-e2e.py` as `user-a`. It reports the Tierkreis result and elapsed
time, runs PySCF SCF and computes a full configuration interaction (FCI)
reference from the same FCIDUMP, including its core energy. It compares SQD
with FCI  and fails if they differ by more
than `1e-5` Hartree or the workflow result is missing or invalid. The input's expected FCI energy is
approximately **-5.7751543 Ha**.

This repository does not run this integration test in CI; run it manually
after setup or when validating changes.

## Configure

All runtime connfiguration live in the user space of the demo.

Interesting file are:
- `runtime.toml`
- `resource_profiles/qfw-slurm/*`

Examples can be updated by editing the `*_input.json` files; the demo's
`test/sqd-e2e.py` also accepts `--input`, `--config` and `--profile`.

E.g. setting ` "compilation": "qfw"` in `sqd_he2_input.json` will change to the original qiskit based qfw compilation.

You can run a workflow directly (e.g. the demo one) through tierkreis direclty with"

```bash
tkr run -g tkr.graphs.sqd:workflow -i examples sqd_he2_input.json --config runtime.toml --profile qfw-slurm --timeout 86400 -o
```
