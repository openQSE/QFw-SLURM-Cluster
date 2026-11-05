# Chemistry Example

This example calculates the energy of a small cluster of four helium atoms, using
COMPSs to run the work in parallel and QFw to run the quantum circuits.

**This is an integration test.** It shows a real application running across the
cluster. To keep the run short it stops the calculation early, so its energies are
not accurate; see [About the energies](#about-the-energies).

If you are new to COMPSs and QFw, start with
[the `hello` example](../README.md#try-it-in-a-few-minutes).

## Run it

After [building the image and starting the cluster](../README.md#try-it-in-a-few-minutes):

```bash
./compss/run-local.sh chemistry
```

It takes 10 to 12 minutes on a laptop. Everything it needs is in this directory, so
there is nothing else to install or download. It prints the final energy and where
to find the results:

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
each. The tasks add up to about 75 minutes of work, so running them in parallel is
about 6.6 times faster than one after the other. All the quantum tasks share one
simulator, which is what limits going faster.

## What's in this directory

| File | What it is |
| --- | --- |
| [`he4_fmo_vqe.py`](he4_fmo_vqe.py) | The COMPSs application. Its `@task` functions are what run in parallel |
| [`chemistry-nwqsim.sbatch`](chemistry-nwqsim.sbatch) | The batch script, with the job's resources and quantum reservation |
| [`chemistry_he/`](chemistry_he/README.md) | The chemistry itself, copied unchanged from [openQSE/chemistry_he](https://github.com/openQSE/chemistry_he): the solver and the helium data |

An image built with COMPSs also has a copy at `/opt/openqse/qfw-compss/chemistry/`.

## About the energies

Three runs gave these energies, in Hartree, the usual unit in chemistry:

| | This example | Accurate value |
| --- | --- | --- |
| Single atoms (monomers) | -2.869 to -2.893 | -2.8876 |
| Pairs of atoms (dimers) | -1.096 to -5.742 | -5.7361 |
| **Total energy** | **-2.27, -4.60 and -9.89** | **-11.3155** |

The accurate value comes from a full run of the same solver, on a simulator without
measurement noise, which took about 3 hours on MareNostrum 5.

The difference is expected in this short run, and it does not come from QFw. A
quantum measurement is statistical, so every energy the optimiser sees has some
noise in it, and the noise can lead the optimiser astray. Some dimers end up far
from the right value, and because the total adds and subtracts all ten energies, one
poor dimer moves the total a long way. Each run also gives a different answer.

We checked this in three ways:

- With the circuit's parameters held fixed, QFw's energies match an exact simulation
  to within the measurement noise, about 0.01 to 0.02 Hartree.
- With no noise and the same short limits, the dimers that went furthest wrong reach
  -5.7355 Hartree, within 0.001 of the accurate value.
- Neither more measurements nor more optimiser steps fixes it. Simulating the noise
  with a million measurements per circuit still left two dimers 0.02 to 0.05 Hartree
  too low, and 200 optimiser steps at the default 4096 measurements left one 0.75
  Hartree too low.

## Changing the run

The default is 2 *macro*, 50 *amplitude* and 1 *orbital* optimiser iterations, with
4096 measurements per circuit. To change the iterations, set
`MAX_MACRO_ITERATIONS`, `MAX_AMPLITUDE_ITERATIONS` or `MAX_ORBITAL_ITERATIONS` when
you submit the batch script. Raise `--time` and `--circ-count` in the script to
match.
