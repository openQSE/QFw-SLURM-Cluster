# StreamFlow Integration

This example runs the ten existing He4 fragment FCIDUMPs through NWQSim, then
collects the energy and execution metadata for each fragment. GAMESS is not required.
The optimizer limits are small to keep test runs short.

## Run locally

Start Docker and keep `chemistry_he` next to `QFw-SLURM-Cluster`. The virtual
cluster image must already be available. From `QFw-SLURM-Cluster`, run:

```sh
./streamflow/chemistry/setup-local.sh
./streamflow/chemistry/run-local.sh
```

Setup starts the virtual cluster if needed, starts the NWQSim and fake IQM services,
installs StreamFlow 0.2.0rc3 in a separate shared-directory virtual environment and
prepares SSH access for the application user. It copies the workflow into the shared
directory. Run setup again after changing the workflow or its configuration.
The application checkout is copied only when the shared copy does not exist.

The launcher prints the run directory. It contains `streamflow.log`, the resolved
configuration, `summary.json` and the collected outputs. The summary lists each
fragment's backend, Slurm job ID, compute node and QFw reservation.
`workflow-results.json` contains the individual fragment results. `CHEMISTRY_RUN_ID` can give the run a recognisable directory name.

## What runs where

| Step | Compute node | Work |
| --- | --- | --- |
| Prepare | c1 | Validate the input and fragment set, check fragments against the full FCIDUMP and prepare two groups |
| Chemistry A | c2 | Calculate monomers 1 and 3 and dimers 1, 3 and 5 through QFw |
| Chemistry B | c2 | Calculate monomers 2 and 4 and dimers 2, 4 and 6 through QFw |
| Collect | c3 | Check results and provenance, run the collector and gather fragment results |

Both chemistry groups use NWQSim by default. There are ten separate chemistry jobs;
Slurm schedules them as resources become available. The coordinator runs inside
`slurmctld` and uses SSH and StreamFlow's native Slurm connector to submit the jobs.

Qiskit and the optimizer run on c2. Inside the allocation, `qfw-setup`, `qfw-srun`
and `qfw-teardown` manage the application runtime. QFw sends the circuits to the
reserved provider. The provider service runs on its dedicated service node, such
as `nwqsim-head`; `qfw-slurm` owns reservation and release. A service node listed
as `idle` by `sinfo` does not prove that its quantum endpoint is operational.

This follows the allocation contract in the Confluence Workflow Manager Integration
Guide and the service topology in the QFw-SLURM-Cluster Tutorial. `--qpu` belongs on
`sbatch`, alongside the circuit, qubit, depth and shot bounds. It is not repeated
on `qfw-srun`.

## Select a quantum backend

`cwl/workflow.cwl` defines dependencies and the two fragment scatters.
`streamflow.yml` binds each chemistry step to a Slurm service. The service references
a `.sbatch` file: `--nodelist=c2` selects the application node, while `--qpu` selects
the public quantum resource. The runner derives the QFw provider from that selection;
there is no backend launcher option.

| StreamFlow service | Public `--qpu` | QPM service | Application provider | Status |
| --- | --- | --- | --- | --- |
| `chemistry-nwqsim` | `nwqsim` | `nwqsim` | `nwqsim` | Default simulator |
| `chemistry-fake-iqm` | `fake-iqm-20q` | `fake-iqm` | `fake-iqm` | Synthetic integration test |
| `chemistry-iqm` | `ornl-iqm-20q` | `iqm-ornl-20q` | `iqm` | Optional hardware profile, not tested |

The default bindings are:

```yaml
- step: /chemistry_a
  target: {deployment: slurm, service: chemistry-nwqsim, locations: 1}
- step: /chemistry_b
  target: {deployment: slurm, service: chemistry-nwqsim, locations: 1}
```

To test five fragments with fake IQM, change only `/chemistry_b` to
`service: chemistry-fake-iqm`, then run setup and launch again. To use IQM hardware,
select `chemistry-iqm` only after the site administrator has enabled the IQM QPM,
configured valid credentials and confirmed the endpoint, permissions and workload
bounds. Setup does not start IQM or submit hardware jobs. The IQM profile's provider
mapping and reservation validation are unit tested; hardware execution is not.

The IBM/AWS Confluence enablement document lists unfinished execution paths despite
their service nodes and resource mappings being present. This integration does not
enable those backends. QEC and shim-specific workflows are outside this example.

`locations: 1` requests one Slurm allocation per scattered job. It does not mean
one quantum processor or one fragment for the entire workflow. `local.yml` contains
the login host, shared root and optimizer limits. `cases.yml` lists the inputs:
the ten fragment files belong to one He4 case, not ten separate molecular cases.

`fragment.py` calls the unchanged application's calculation and QFw lifecycle
functions. `fragment.sh` starts and tears down the runtime for each fragment.
The original chemistry batch script runs the whole case with one provider, which
is why fragment execution needs this adapter. The final stage reuses
`chemistry_he/workflow/slurm/collect-results.sbatch`. Neither GAMESS nor the
original submission driver is executed.

StreamFlow handles the declared file and directory dependencies. This testbed uses
a shared filesystem; transfers between separate sites remain untested.

## Tests

After setup, run the unit tests inside the controller:

```sh
docker exec --user user-a \
  --env CHEMISTRY_TEST_SOURCE=/workspace/qfw-container-base/chemistry_he \
  slurmctld \
  /workspace/qfw-container-base/streamflow-chemistry/venv-0.2.0rc3/bin/python \
  -m unittest discover -v \
  -s /workspace/qfw-container-base/streamflow-chemistry/tests
```

They check backend bindings, resource bounds, complete fragment sets, unchanged
input bytes, reservation validation, failed application scripts, result writing
before QFw shutdown, invalid energies and missing, duplicate or modified results.
They also verify collected fragment results and the labels for simulation and
synthetic runs. The four Docker failure tests are skipped by this command.

Run those four tests using Python 3 on the Docker host, from `QFw-SLURM-Cluster`:

```sh
CHEMISTRY_TEST_DOCKER=1 python3 -m unittest discover -v \
  -s streamflow/chemistry/tests -p test_streamflow.py
```

These submit real StreamFlow/Slurm jobs with isolated application fixtures. They
cover rejected submission, invalid preparation input, failed chemistry and failed
collection, checking error propagation, blocked downstream execution and released
quantum reservations. They do not run the scientific solver. Fixtures and logs
are retained under the shared directory.

`run-local.sh` is the positive end-to-end test. It uses the scientific application
functions on all ten supplied fragments, with classical preparation and collection.
Hardware execution is not covered by these tests.
