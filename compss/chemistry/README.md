# Chemistry Example

This example calculates the energy of a small cluster of four helium atoms, using
COMPSs to run the work in parallel and QFw to run the quantum circuits.

**This is an integration test.** It shows a real application running across the
cluster. Its energies are not reliable yet, because of a bug in QFw and because the
run stops the calculation early to stay short; see
[About the energies](#about-the-energies).

If you are new to COMPSs and QFw, start with
[the `hello` example](../README.md#try-it-in-a-few-minutes).

## Run it

After [building the image and starting the cluster](../README.md#try-it-in-a-few-minutes):

```bash
./compss/run-local.sh chemistry
```

It takes 10 to 13 minutes on a laptop, and there is nothing else to do first:
`setup-local.sh` already fetched the chemistry code it needs. It prints the final
energy and where to find the results:

```text
*FMO-VQE energy = -4.603224680447
Output:  .../shared-dir/home/user-a/compss-chemistry-1.out
Results: .../shared-dir/home/user-a/compss-chemistry-1.json
Graph:   .../monitor/complete_graph.dot
```

The `.json` file lists each fragment's energy, how many quantum calls it made,
which node ran it and how long it took.

## What it does

Calculating four atoms together is hard, so the fragment molecular orbital (FMO)
method splits the problem into smaller pieces: each atom on its own, which gives 4
*monomers*, and each pair of atoms, which gives 6 *dimers*. The total energy is
then added up from the energies of those 10 fragments.

Each fragment gets two COMPSs tasks, so there are 20 in all:

1. `make_puccd`, an ordinary classical task, reads the fragment's data file and
   sets up the problem.
2. `vqe_energy`, a quantum task, finds the fragment's energy with VQE: a loop in
   which a classical optimiser keeps adjusting a quantum circuit and measuring its
   energy. Each fragment makes about 100 calls to the quantum simulator.

The fragments don't depend on each other, so they can all run at the same time:

```text
                          main
      ┌──────┬──────┬───── ... ─────┬──────┐
  make_puccd  ...                         ...      10 classical tasks
      │      │      │               │      │
  vqe_energy  ...                         ...      10 quantum tasks
      └──────┴──────┴───── ... ─────┴──────┘
                          sync                     add up the total energy
```

Node `c1` runs the main program, and `c2` and `c3` run the tasks, four at a time
each.

**Running in parallel does not make this example faster here.** The simulator runs
one circuit at a time, and almost all of the time goes on circuits, so they have to
pass through it one by one either way. One task at a time took 672 seconds, and
parallel runs took between 564 and 764 seconds, on a laptop in normal use, so treat
these as rough. A task takes about 75 seconds alone and up to 10 minutes when it is
waiting behind the others. Tasks that do more of their work outside the simulator
gain more: [`hello`](../README.md#try-it-in-a-few-minutes) runs about 4 times faster.

## What's in this directory

| File | What it is |
| --- | --- |
| [`he4_fmo_vqe.py`](he4_fmo_vqe.py) | The COMPSs application. Its `@task` functions are what run in parallel |
| [`chemistry-nwqsim.sbatch`](chemistry-nwqsim.sbatch) | The batch script, with the job's resources and quantum reservation |
| `chemistry_he/` | The chemistry itself, from [openQSE/chemistry_he](https://github.com/openQSE/chemistry_he): the solver and the helium data. It is a git submodule pinned to a tested commit, which `setup-local.sh` fetches for you |

## About the energies

These are the energies from our runs, in Hartree, the usual unit in chemistry:

| | Parallel | Parallel, with the QFw fix below (2 runs) | One task at a time (1 run) | Accurate value |
| --- | --- | --- | --- | --- |
| Single atoms (monomers) | -2.869 to -2.893 | -2.867 to -2.890 | -2.855 to -2.893 | -2.8876 |
| Pairs of atoms (dimers) | +3.544 to -5.742 | -5.672 to -5.748 | -5.700 to -5.731 | -5.7361 |
| **Total energy** | **+0.99, -1.62, -2.27, -4.60 and -9.89** | **-11.16 and -11.18** | **-11.28** | **-11.3155** |

The accurate value comes from a full run of the same solver, on a simulator without
measurement noise, which took about 3 hours on MareNostrum 5.

### The large errors: a bug in QFw

Each energy needs three circuits, one for each way of measuring the qubits. QFw
assumes their results come back in the order the circuits were sent. With several
tasks running at once, they sometimes do not: this happened in about 1 call in 5. The
energy from such a call can be about +23 Hartree instead of about -5.7, which sends
the optimiser the wrong way. Because the total adds and subtracts all ten energies,
one poor dimer moves the total a long way.

Putting the results back in order inside QFw brought the parallel runs close to the
accurate value, as the table shows. The fix belongs in QFw
([openQSE/QFw#192](https://github.com/openQSE/QFw/issues/192)), so until this
repository builds a QFw that has it, **expect parallel runs of this example to give
wrong energies**.

### The small errors: a short run with measurement noise

With the bug out of the way, the total is still 0.04 to 0.15 Hartree off. A quantum
measurement is statistical, so every energy the optimiser sees has some noise in it,
and this run also stops the optimiser early. We checked the noise with one client at
a time:

- With the circuit's parameters held fixed, QFw's energies match an exact simulation
  to within the measurement noise, about 0.01 to 0.02 Hartree.
- With no noise and the same short limits, the dimers reach -5.7355 Hartree, within
  0.001 of the accurate value.
- Neither more measurements nor more optimiser steps fixes it by itself. Simulating
  the noise with a million measurements per circuit still left two dimers 0.02 to
  0.05 Hartree too low, and 200 optimiser steps at the default 4096 measurements left
  one 0.75 Hartree too low.

## Changing the run

The default is 2 *macro*, 50 *amplitude* and 1 *orbital* optimiser iterations, with
4096 measurements per circuit. To change the iterations, set
`MAX_MACRO_ITERATIONS`, `MAX_AMPLITUDE_ITERATIONS` or `MAX_ORBITAL_ITERATIONS` when
you submit the batch script. Raise `--time` and `--circ-count` in the script to
match.
