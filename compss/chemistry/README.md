# COMPSs Chemistry Example

This example runs the He4 FMO-VQE application from
[chemistry_he](https://github.com/openQSE/chemistry_he) under COMPSs, with every
VQE run on the site NWQ-Sim QPM through QFw. Everything it needs is in this
directory, including a [copy of chemistry_he](chemistry_he/README.md)'s solver
and its ten fragment FCIDUMPs, so GAMESS and other checkouts are not required.

**This is an integration test.** It shows the application running across the
cluster with COMPSs and QFw. Its optimiser limits are small and its energies
are not converged; see [Energies](#energies).

## Run locally

Build an image with COMPSs. Use `--slim` where no prebuilt image exists, such
as on an arm64 host:

```sh
./do_configure.sh --slim --with-compss --image-tag rocky10.1-compss
./do_build.sh
```

Then, from `QFw-SLURM-Cluster`:

```sh
./compss/chemistry/setup-local.sh
./compss/chemistry/run-local.sh
```

Setup starts the cluster if needed, starts the directory service, the NWQ-Sim
QPM and the reservation gateway, and copies this directory into the shared
directory. Run it again after changing the example. An image built with COMPSs
also holds a copy at `/opt/openqse/qfw-compss/chemistry/`.

The launcher submits the job as `user-a` and waits for it. It prints where the
job's output, results and task graph are, and the FMO energy. On an Apple
silicon laptop, with Docker limited to 4 CPUs and 6 GB of memory, the job takes
about 12 minutes. The tasks add up to about 75 minutes of work, so running them
in parallel is about 6.6 times faster than running them one after the other.

## What runs where

| Node | Work |
| --- | --- |
| c1 | The COMPSs master: the main program, which waits for all ten energies and adds up the FMO energy |
| c2, c3 | The COMPSs workers, four tasks at a time each |
| `nwqsim-head` | The site NWQ-Sim QPM, which executes the circuits |

There are 20 COMPSs tasks. For each of the four monomers and six dimers, a
classical `make_puccd` task reads the FCIDUMP and builds the pUCCD problem, and
a quantum `vqe_energy` task runs the orbital-optimised VQE:

```text
                          main
      ┌──────┬──────┬───── ... ─────┬──────┐
  make_puccd  ...                          ...     10 classical tasks
      │      │      │               │      │
  vqe_energy  ...                          ...     10 quantum tasks
      └──────┴──────┴───── ... ─────┴──────┘
                          sync                     FMO energy
```

All ten quantum tasks share the job's one `--qpu=nwqsim` reservation. Each opens
one QFw client and keeps it for its whole optimisation, about 100 estimator
calls of 3 circuits each. The DEFw start-up and QPM lookup, about 6 s, are paid
once per fragment.

`he4_fmo_vqe.py` is the COMPSs application: its `@task` functions are what run
in parallel. It imports chemistry_he's solver unchanged and sets the solver's
estimator to the QFw client's.

## Results

Under the test user's home, which is `shared-dir/home/user-a` on the host:

| Path | Contents |
| --- | --- |
| `compss-chemistry-<job>.out` | The job's output, with the COMPSs task summary |
| `compss-chemistry-<job>.json` | Each fragment's energy, estimator calls, node, reservation and timings, and the FMO energy |
| `.qfw-compss/<job>-<time>/.COMPSs/<job>/` | COMPSs' logs, and the task graph in `monitor/complete_graph.dot` |

See [Observing a run](../README.md#observing-a-run) for rendering the graph and
adding QFw telemetry.

## Energies

The default limits are 2 macro, 50 amplitude and 1 orbital iterations at 4096
shots per circuit. Two runs gave these energies, in Hartree:

| | This example | Converged reference |
| --- | --- | --- |
| Monomers | -2.869 to -2.893 | -2.8876 |
| Dimers | -1.096 to -5.742 | -5.7361 |
| FMO energy | -2.27 and -4.60 | -11.3155 |

The reference is a full run of the pUCCD solver on a noiseless statevector with
its default limits, which took about 3 hours on MareNostrum 5.

The difference comes from shot noise in the optimisation, not from QFw:

- At fixed parameters, QFw's energies match the statevector's within the shot
  noise, about 0.01 to 0.02 Ha near the starting point of the dimers.
- On a noiseless statevector with the same limits, the dimers that went furthest
  wrong here reach -5.7355 Ha, within 1 mHa of the reference.
- Neither more shots nor more iterations closes the gap. Emulating the noise
  on a statevector, a million shots per circuit still left two dimers 20 to 50
  mHa below the reference, and 200 amplitude iterations at 4096 shots left one
  0.75 Ha below it.

The FMO sum adds and subtracts all ten energies, so one poor dimer moves the
total a long way, and each run differs from the last.

To change the limits, set `MAX_MACRO_ITERATIONS`, `MAX_AMPLITUDE_ITERATIONS` or
`MAX_ORBITAL_ITERATIONS` in the environment `sbatch` runs in. Raise `--time` and
`--circ-count` in `chemistry-nwqsim.sbatch` to match.

## Tests

`run-local.sh` is the end-to-end test. The tests in [`../tests`](../tests) cover
`qfw_compss` itself and need neither QFw nor COMPSs.
