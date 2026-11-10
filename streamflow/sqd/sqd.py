#!/usr/bin/env python3

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def file(path):
    return {"class": "Directory" if Path(path).is_dir() else "File", "path": str(Path(path).resolve())}


def emit(**outputs):
    write("cwl.output.json", outputs)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def allocation():
    job = os.environ.get("SLURM_JOB_ID", "")
    if not job.isdecimal() or int(job) < 1:
        raise RuntimeError("Run this task inside a Slurm allocation")
    return {"job_id": int(job), "nodes": os.environ["SLURM_JOB_NODELIST"]}


def configuration(path):
    config = read(path)
    limits = {"walkers": 4, "iterations": 1, "shots": 1, "dimension": 1, "seed": 0}
    if set(config) != set(limits) | {"solver"} or any(type(config[k]) is not int or config[k] < v for k, v in limits.items()):
        raise ValueError("Expected integer walkers>=4, iterations>=1, shots>=1, dimension>=1 and seed>=0")
    solver = config["solver"]
    if (not isinstance(solver, dict) or set(solver) != {"block", "iteration", "tolerance", "carryover_ratio"} or
            any(type(solver[k]) is not int or solver[k] < 1 for k in ("block", "iteration")) or
            any(type(solver[k]) not in (int, float) or not math.isfinite(solver[k]) or solver[k] <= 0
                for k in ("tolerance", "carryover_ratio")) or solver["carryover_ratio"] > 1):
        raise ValueError("Expected positive solver block, iteration, tolerance and carryover_ratio<=1")
    return config


def prepare(args):
    import ffsim
    from pyscf import ao2mo, cc
    from pyscf.tools import fcidump

    config = configuration(args.config)
    mf = fcidump.to_scf(str(args.fcidump))
    mf.verbose = 0
    mf.kernel()
    if not mf.converged or mf.mol.spin != 0 or mf.mol.nelectron % 2:
        raise ValueError("This example requires converged closed-shell RHF integrals")
    coupled = cc.CCSD(mf).run(verbose=0)
    if not coupled.converged:
        raise ValueError("CCSD initialization did not converge")
    orbitals = mf.mo_coeff
    norb = orbitals.shape[1]
    nelec = mf.mol.nelectron // 2
    if not 1 <= norb <= 30:
        raise ValueError("This example supports up to 30 spatial orbitals")
    h1 = orbitals.T @ mf.get_hcore() @ orbitals
    h2 = ao2mo.restore(1, ao2mo.kernel(mf._eri, orbitals), norb)
    pairs = ([(i, i + 1) for i in range(norb - 1)], [(i, i) for i in range(0, norb, 4)])
    rng = np.random.default_rng(config["seed"])
    population = []
    for index in range(config["walkers"]):
        t2 = coupled.t2 if index == 0 else coupled.t2 + rng.uniform(-0.1, 0.1, coupled.t2.shape)
        expanded = ffsim.UCJOpSpinBalanced.from_t_amplitudes(t2, n_reps=2, interaction_pairs=pairs)
        operator = ffsim.UCJOpSpinBalanced(diag_coulomb_mats=expanded.diag_coulomb_mats[:-1],
                    orbital_rotations=expanded.orbital_rotations[:-1],
                    final_orbital_rotation=expanded.orbital_rotations[-1])
        population.append(operator.to_parameters(interaction_pairs=pairs).tolist())
    problem = Path("problem")
    problem.mkdir()
    fcidump.from_integrals(str(problem / "fcidump.txt"), h1, h2, norb, (nelec, nelec))
    write(problem / "problem.json", dict(config=config, norb=norb, nelec=nelec,
          nuclear_energy=float(mf.energy_nuc()), input_sha256=digest(args.fcidump), prepare=allocation()))
    write("state.json", dict(config=config, fcidump_sha256=digest(args.fcidump), iteration=0,
          population=population, energies=[], carryover=[], history=[]))
    emit(problem=file(problem), state=file("state.json"))


def trial_population(state):
    population = np.asarray(state["population"], dtype=float)
    if state["iteration"] == 0:
        return population.copy()
    rng = np.random.default_rng(state["config"]["seed"] + state["iteration"])
    best = population[int(np.argmin(state["energies"]))]
    candidates = []
    for current in population:
        a, b, c, d = rng.choice(len(population), 4, replace=False)
        mutant = best + 0.6 * (population[a] - population[b] + population[c] - population[d])
        mask = rng.random(population.shape[1]) < 0.9
        mask[rng.integers(population.shape[1])] = True
        candidates.append(np.where(mask, mutant, current))
    return np.asarray(candidates)


def propose(args):
    import ffsim
    from qiskit import QuantumCircuit, qpy, transpile

    problem, state = read(args.problem / "problem.json"), read(args.state)
    norb, nelec = problem["norb"], problem["nelec"]
    pairs = ([(i, i + 1) for i in range(norb - 1)], [(i, i) for i in range(0, norb, 4)])
    requests = []
    for index, parameters in enumerate(trial_population(state)):
        directory = Path(f"walker-{index}")
        directory.mkdir()
        circuit = QuantumCircuit(2 * norb)
        circuit.append(ffsim.qiskit.PrepareHartreeFockJW(norb, (nelec, nelec)), circuit.qubits)
        operator = ffsim.UCJOpSpinBalanced.from_parameters(parameters, norb=norb, n_reps=1,
                    interaction_pairs=pairs, with_final_orbital_rotation=True)
        circuit.append(ffsim.qiskit.UCJOpSpinBalancedJW(operator), circuit.qubits)
        circuit.measure_all()
        circuit = transpile(circuit, basis_gates=["rz", "sx", "x", "cx"],
                            optimization_level=1, seed_transpiler=problem["config"]["seed"] + index)
        with (directory / "circuit.qpy").open("wb") as stream:
            qpy.dump(circuit, stream)
        write(directory / "request.json", dict(walker=index, iteration=state["iteration"] + 1,
              parameters=parameters.tolist(), carryover=state["carryover"], shots=state["config"]["shots"],
              circuit_sha256=digest(directory / "circuit.qpy"), propose=allocation()))
        requests.append(file(directory))
    emit(requests=requests)


def sample(args):
    reservations = json.loads(os.environ.get("QFW_RESERVATIONS", "[]"))
    providers = {"nwqsim": "nwqsim", "fake-iqm": "fake-iqm", "iqm-ornl-20q": "iqm"}
    if (not isinstance(reservations, list) or len(reservations) != 1 or
            not isinstance(reservations[0], list) or len(reservations[0]) != 2 or
            reservations[0][0] not in providers or not all(reservations[0])):
        raise ValueError("Sampling requires one supported QFw reservation")
    request = read(args.request / "request.json")
    if digest(args.request / "circuit.qpy") != request["circuit_sha256"]:
        raise ValueError("Circuit does not match its request")
    output = Path("sample").resolve()
    output.mkdir()
    shutil.copyfile(args.request / "request.json", output / "request.json")
    subprocess.run(["bash", "sample.sh", str(args.sampler), str(args.request / "circuit.qpy"),
                    providers[reservations[0][0]], str(request["shots"]), str(output), sys.prefix], check=True)
    counts = read(output / "counts.json")
    if counts.get("service_id") != reservations[0][0] or counts.get("reservation_id") != reservations[0][1]:
        raise ValueError("Sampler did not use the allocated QFw reservation")
    write(output / "sampling.json", dict(**allocation(), counts_sha256=digest(output / "counts.json")))
    emit(samples=file(output))


def determinant_basis(counts, problem, carryover, seed):
    from qiskit_addon_sqd.counts import counts_to_arrays
    from qiskit_addon_sqd.configuration_recovery import recover_configurations

    norb, nelec = problem["norb"], problem["nelec"]
    if (not counts or any(not isinstance(key, str) or len(key) != 2 * norb or set(key) - {"0", "1"}
                          or type(value) is not int or value < 1 for key, value in counts.items())):
        raise ValueError("Invalid quantum counts")
    strings, probabilities = counts_to_arrays(counts)
    occupied = np.array([1.0] * nelec + [0.0] * (norb - nelec))
    strings, probabilities = recover_configurations(strings, probabilities,
        avg_occupancies=(occupied, occupied), num_elec_a=nelec, num_elec_b=nelec, rand_seed=seed)
    valid = (strings[:, :norb].sum(axis=1) == nelec) & (strings[:, norb:].sum(axis=1) == nelec)
    weights = {}
    for bits, probability in zip(strings[valid], probabilities[valid]):
        for half in (bits[:norb], bits[norb:]):
            value = int("".join("1" if bit else "0" for bit in half), 2)
            weights[value] = weights.get(value, 0.0) + float(probability)
    if not weights:
        raise ValueError("No valid configurations after SQD recovery")
    maximum = math.isqrt(problem["config"]["dimension"])
    basis = [(1 << nelec) - 1]
    for value in carryover:
        if type(value) is not int or not 0 <= value < (1 << norb) or value.bit_count() != nelec:
            raise ValueError("Invalid carryover configuration")
        if value not in basis and len(basis) < maximum:
            basis.append(value)
    rng = np.random.default_rng(seed)
    remaining = [value for value in weights if value not in basis]
    while remaining and len(basis) < maximum:
        probabilities = np.asarray([weights[value] for value in remaining])
        index = int(rng.choice(len(remaining), p=probabilities / probabilities.sum()))
        basis.append(remaining.pop(index))
    return basis


def solve(args):
    problem = read(args.problem / "problem.json")
    request = read(args.samples / "request.json")
    counts = read(args.samples / "counts.json")
    sampling = read(args.samples / "sampling.json")
    if digest(args.samples / "counts.json") != sampling["counts_sha256"] or sum(counts["counts"].values()) != request["shots"]:
        raise ValueError("Sampling result does not match its provenance or shot count")
    seed = problem["config"]["seed"] + request["iteration"] * problem["config"]["walkers"] + request["walker"]
    basis = determinant_basis(counts["counts"], problem, request["carryover"], seed)
    output = Path("solution").resolve()
    output.mkdir()
    shutil.copyfile(args.problem / "fcidump.txt", output / "fcidump.txt")
    width = (problem["norb"] + 7) // 8
    (output / "AlphaDets.bin").write_bytes(b"".join(value.to_bytes(width, "big") for value in basis))
    ranks = int(os.environ.get("SLURM_NTASKS", "1"))
    solver = dict(problem["config"]["solver"])
    solver["block"] = min(solver["block"], len(basis) ** 2)
    command = ["mpirun", "-np", str(ranks), "--map-by", "ppr:1:node", str(args.solver), "--task_comm_size", str(ranks),
               "--adet_comm_size", "1", "--bdet_comm_size", "1", "--block", str(solver["block"]),
               "--iteration", str(solver["iteration"]), "--tolerance", str(solver["tolerance"]),
               "--carryover_type", "1", "--carryover_ratio", str(solver["carryover_ratio"]),
               "--dump_matrix_form_wf", "matrixformwf.txt", "--rdm", "0"]
    with (output / "solver.log").open("w") as stream:
        subprocess.run(command, cwd=output, stdout=stream, stderr=subprocess.STDOUT, check=True)
    energy = float(np.loadtxt(output / "davidson_energy.txt")) + problem["nuclear_energy"]
    if not math.isfinite(energy):
        raise ValueError("SBD returned a non-finite energy")
    raw = (output / "carryover.bin").read_bytes()
    if len(raw) % width:
        raise ValueError("Invalid SBD carryover output")
    carryover = [int.from_bytes(raw[i:i + width], "big") >> (8 * width - problem["norb"])
                 for i in range(0, len(raw), width)]
    write(output / "result.json", dict(request, energy=energy, input_carryover=request["carryover"], carryover=carryover,
          basis=basis, sampling=sampling, solver=allocation(), solver_settings=solver, provider=counts["provider"]))
    emit(results=file(output))


def select(args):
    state = read(args.state)
    results = sorted((read(path / "result.json") for path in args.results), key=lambda result: result["walker"])
    if (len(results) != state["config"]["walkers"] or
            [result["walker"] for result in results] != list(range(len(results))) or
            any(result["iteration"] != state["iteration"] + 1 or not math.isfinite(result["energy"]) for result in results)):
        raise ValueError("Incomplete or invalid walker results")
    best = min(results, key=lambda result: result["energy"])
    if not state["energies"] or best["energy"] < min(state["energies"]):
        state["carryover"] = best["carryover"]
    for result in results:
        index = result["walker"]
        if not state["energies"] or result["energy"] < state["energies"][index]:
            state["population"][index] = result["parameters"]
    state["energies"] = [min(state["energies"][i], result["energy"]) if state["energies"] else result["energy"]
                         for i, result in enumerate(results)]
    state["iteration"] += 1
    state["best_energy"] = min(state["energies"])
    state["history"].append(dict(iteration=state["iteration"], walkers=results, selection=allocation()))
    write("state.json", state)
    emit(next_state=file("state.json"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "propose", "sample", "solve", "select"))
    for name in ("fcidump", "config", "problem", "state", "request", "samples", "sampler", "solver"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--results", nargs="+", type=Path)
    args = parser.parse_args()
    globals()[args.action](args)


if __name__ == "__main__":
    main()
