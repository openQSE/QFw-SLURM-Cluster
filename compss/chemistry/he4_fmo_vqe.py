#!/usr/bin/env python3
"""chemistry_he's He4 FMO-VQE as a PyCOMPSs application, on a QFw QPM.

chemistry_he's ``example_3_He4_FMO_VQE.py`` runs the fragments one after the
other. Here, for each of the four monomers and six dimers, a classical task
reads the FCIDUMP and builds the pUCCD problem, and a quantum task runs its
orbital-optimised VQE. The main program waits for all ten energies and adds
them up into the FMO energy. The fragments, the solver and the
dimer-to-monomer map are chemistry_he's. The ``chemistry_he`` directory next to
this file is a submodule that ``setup-local.sh`` fetches.

The optimiser limits are small by default to keep test runs short, so this is
an integration test and its energies are not converged; see README.md.

The quantum task opens one QFw client and keeps it for the whole optimisation,
so the DEFw start-up and the QPM lookup are paid once per fragment, not once
per estimator call. Run it with ``qfw-compss-launch`` from a batch script
submitted with ``--qpu``; see ``chemistry-nwqsim.sbatch``.
"""

import argparse
import json
import math
import time
from pathlib import Path

from pycompss.api.api import compss_wait_on
from pycompss.api.task import task

# From ./chemistry_he, which qfw-compss-launch --pythonpath adds. puccd is imported
# in the tasks that use it; see make_puccd.
from setup_FMO import setup_FMO

from qfw_compss import QFwClient


# Dimer index -> the two monomers it contains, as chemistry_he has it.
DIMER_MONOMERS = {0: (2, 0), 1: (2, 1), 2: (3, 0), 3: (3, 1), 4: (3, 2),
				  5: (1, 0)}


@task(returns=1)
def make_puccd(fcidump):
	# Not at module level: the COMPSs master must not load puccd. It pulls in
	# h5py through PySCF and OpenFermion, and when a task fails the master
	# hangs instead of exiting. The JVM calls exit(), HDF5's exit handler
	# waits for the GIL, and the main thread holds the GIL inside a COMPSs
	# call that is waiting for the JVM.
	from puccd import pairUCC

	return pairUCC.from_FCIDUMP(fcidump)


@task(returns=1)
def vqe_energy(problem, fragment, provider, shots, limits):
	import puccd

	started = time.time()
	# QFwEstimatorV2 runs ceil(1 / precision**2) shots. The factor keeps
	# rounding from adding one to the count asked for.
	precision = 1 / math.sqrt(shots) * (1 + 1e-12)
	with QFwClient(provider=provider) as qfw:
		# puccd_initialize would create a QFwBackend here, which only works
		# under defw-python, so set the solver's estimator directly.
		puccd.estimator = qfw.estimator(default_precision=precision)
		energy = problem.optimize_ansatz_qk(
			problem.initial_guess_mp2d(),
			maxiter_macro=limits["macro"],
			maxiter_amps=limits["amplitude"],
			maxiter_orbs=limits["orbital"])
	energy = float(energy)
	if not math.isfinite(energy):
		raise ValueError(f"{fragment}: VQE energy is not finite")
	return {
		"fragment": fragment,
		"energy": energy,
		"estimator_calls": qfw.calls,
		"qfw": qfw.info,
		"task_sec": round(time.time() - started, 3),
	}


def fmo_energy(monomers, dimers):
	energy = sum(monomers)
	for dimer, (i, j) in DIMER_MONOMERS.items():
		energy += dimers[dimer] - monomers[i] - monomers[j]
	return energy


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument(
		"--fcidump", required=True, type=Path,
		help="chemistry_he's He4/He1-4.FCIDUMP, next to its -1-* and -2-* "
			 "fragments")
	parser.add_argument("--provider", default="nwqsim",
						help="QFw provider of the reserved QPM")
	parser.add_argument("--shots", type=int, default=4096,
						help="shots per estimator circuit")
	# Small limits for an integration test, not a converged calculation.
	parser.add_argument("--max-macro-iterations", type=int, default=2)
	parser.add_argument("--max-amplitude-iterations", type=int, default=50)
	parser.add_argument("--max-orbital-iterations", type=int, default=1)
	parser.add_argument("--output", type=Path, required=True,
						help="JSON file for the energies and QFw metadata")
	args = parser.parse_args()

	started = time.time()
	limits = {"macro": args.max_macro_iterations,
			  "amplitude": args.max_amplitude_iterations,
			  "orbital": args.max_orbital_iterations}
	monomer_files, dimer_files = setup_FMO(args.fcidump)
	if len(monomer_files) != 4 or len(dimer_files) != len(DIMER_MONOMERS):
		raise SystemExit(
			f"expected 4 monomers and {len(DIMER_MONOMERS)} dimers in "
			f"{args.fcidump.parent}, found {len(monomer_files)} and "
			f"{len(dimer_files)}")

	futures = {}
	for kind, files in (("monomer", monomer_files), ("dimer", dimer_files)):
		futures[kind] = [
			vqe_energy(make_puccd(str(path)), path.name, args.provider,
					   args.shots, limits)
			for path in files]
	results = {kind: compss_wait_on(items) for kind, items in futures.items()}

	monomers = [r["energy"] for r in results["monomer"]]
	dimers = [r["energy"] for r in results["dimer"]]
	energy = fmo_energy(monomers, dimers)
	summary = {
		"fmo_energy": energy,
		"monomer_energies": monomers,
		"dimer_energies": dimers,
		"provider": args.provider,
		"shots": args.shots,
		"limits": limits,
		"wall_sec": round(time.time() - started, 3),
		"fragments": results["monomer"] + results["dimer"],
	}
	args.output.write_text(json.dumps(summary, indent=2) + "\n")
	print(f"*FMO-VQE energy = {energy:.12f}")
	print(f"Results: {args.output}")


if __name__ == "__main__":
	main()
