import argparse
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sqd", ROOT / "sqd.py")
sqd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sqd)


class SQDTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        environment = patch.dict(os.environ, {"SLURM_JOB_ID": "123", "SLURM_JOB_NODELIST": "c1"})
        environment.start()
        self.addCleanup(environment.stop)
        self.config = json.loads((ROOT / "settings.json").read_text())
        self.state = dict(config=self.config, iteration=0, population=np.arange(12).reshape(4, 3).tolist(),
                          energies=[], carryover=[], history=[])

    def test_configuration_rejects_invalid_bounds_and_unknown_keys(self):
        for name, value in (("walkers", 3), ("iterations", 0), ("shots", -1), ("seed", True), ("typo", 1)):
            config = dict(self.config, **{name: value})
            sqd.write("config.json", config)
            with self.subTest(name=name), self.assertRaises(ValueError):
                sqd.configuration("config.json")

    def test_initial_population_is_preserved_without_aliasing(self):
        result = sqd.trial_population(self.state)
        np.testing.assert_array_equal(result, self.state["population"])
        result[0, 0] = 999
        self.assertEqual(self.state["population"][0][0], 0)

    def test_solver_configuration_rejects_invalid_values(self):
        cases = [("block", 0), ("iteration", True), ("tolerance", 0), ("tolerance", float("nan")),
                 ("carryover_ratio", 1.1), ("carryover_ratio", True), ("typo", 1)]
        for name, value in cases:
            config = deepcopy(self.config)
            config["solver"][name] = value
            Path("config.json").write_text(json.dumps(config))
            with self.subTest(name=name, value=value), self.assertRaisesRegex(ValueError, "solver"):
                sqd.configuration("config.json")

    def test_mutation_is_reproducible_and_uses_previous_energies(self):
        self.state.update(iteration=1, energies=[0, 1, 2, 3])
        first = sqd.trial_population(self.state)
        np.testing.assert_array_equal(first, sqd.trial_population(self.state))
        self.state["energies"] = [3, 2, 1, 0]
        self.assertFalse(np.array_equal(first, sqd.trial_population(self.state)))

    def test_basis_preserves_carryover_and_respects_dimension(self):
        problem = dict(norb=2, nelec=1, config=dict(dimension=4))
        basis = sqd.determinant_basis({"0101": 100}, problem, [2], 24)
        self.assertEqual(basis, [1, 2])
        self.assertLessEqual(len(basis) ** 2, 4)

    def test_basis_rejects_invalid_counts_and_carryover(self):
        problem = dict(norb=2, nelec=1, config=dict(dimension=4))
        for counts in ({}, {"01": 10}, {"01x1": 10}, {"0101": 0}, {"0101": True}):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                sqd.determinant_basis(counts, problem, [], 24)
        with self.assertRaisesRegex(ValueError, "carryover"):
            sqd.determinant_basis({"0101": 100}, problem, [3], 24)

    def results(self, energies, iteration=1):
        paths = []
        for index, energy in enumerate(energies):
            path = self.root / f"result-{iteration}-{index}"
            path.mkdir()
            sqd.write(path / "result.json", dict(walker=index, iteration=iteration, energy=energy,
                      parameters=[100 + index] * 3, carryover=[2]))
            paths.append(path)
        return paths

    def test_selection_carries_state_into_next_iteration(self):
        sqd.write("input.json", self.state)
        sqd.select(argparse.Namespace(state=Path("input.json"), results=self.results([-1, -2, -3, -4])))
        state = sqd.read("state.json")
        self.assertEqual(state["best_energy"], -4)
        self.assertEqual(state["carryover"], [2])
        self.assertEqual(state["iteration"], 1)
        population = deepcopy(state["population"])
        sqd.write("input.json", state)
        sqd.select(argparse.Namespace(state=Path("input.json"), results=self.results([0, 0, 0, 0], 2)))
        state = sqd.read("state.json")
        self.assertEqual(state["population"], population)
        self.assertEqual(state["best_energy"], -4)
        self.assertEqual(len(state["history"]), 2)
        self.assertEqual(state["iteration"], 2)

    def test_selection_rejects_missing_or_wrong_iteration(self):
        sqd.write("input.json", self.state)
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            sqd.select(argparse.Namespace(state=Path("input.json"), results=self.results([-1, -2, -3])))
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            sqd.select(argparse.Namespace(state=Path("input.json"), results=self.results([-1] * 4, 2)))

    def test_sampling_requires_reservation_and_unchanged_circuit(self):
        with patch.dict(os.environ, {"QFW_RESERVATIONS": "[]"}), self.assertRaisesRegex(ValueError, "reservation"):
            sqd.sample(argparse.Namespace())
        (self.root / "circuit.qpy").write_bytes(b"changed")
        sqd.write(self.root / "request.json", dict(circuit_sha256="wrong"))
        with patch.dict(os.environ, {"QFW_RESERVATIONS": '[["nwqsim","id"]]'}), self.assertRaisesRegex(ValueError, "Circuit"):
            sqd.sample(argparse.Namespace(request=self.root))

    def test_allocation_is_required(self):
        with patch.dict(os.environ, {"SLURM_JOB_ID": ""}), self.assertRaises(RuntimeError):
            sqd.allocation()

    def test_h2_preparation_and_lucj_requests(self):
        from qiskit import qpy
        from qiskit.quantum_info import Statevector

        sqd.write("config.json", self.config)
        sqd.prepare(argparse.Namespace(config=Path("config.json"), fcidump=ROOT / "data/h2.FCIDUMP"))
        problem = sqd.read("problem/problem.json")
        self.assertEqual((problem["norb"], problem["nelec"]), (2, 1))
        sqd.propose(argparse.Namespace(problem=Path("problem"), state=Path("state.json")))
        requests = sqd.read("cwl.output.json")["requests"]
        self.assertEqual(len(requests), 4)
        for entry in requests:
            directory = Path(entry["path"])
            with (directory / "circuit.qpy").open("rb") as stream:
                circuit, = qpy.load(stream)
            self.assertEqual(circuit.num_qubits, 4)
            self.assertEqual(sqd.read(directory / "request.json")["circuit_sha256"], sqd.digest(directory / "circuit.qpy"))
            if directory.name == "walker-0":
                probabilities = Statevector.from_instruction(circuit.remove_final_measurements(inplace=False)).probabilities()
                expected = np.zeros(16)
                expected[[5, 6, 9, 10]] = [0.2530308589806405, 0.25697504220178935,
                                          0.25697504220178946, 0.2330190566157809]
                np.testing.assert_allclose(probabilities, expected, atol=1e-8, rtol=0)
