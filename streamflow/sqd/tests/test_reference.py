import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sqd_reference", ROOT / "reference.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReferenceTests(unittest.TestCase):
    def test_examples_match_recorded_fci_references(self):
        for name in ("h2", "h4"):
            with self.subTest(case=name):
                recorded = json.loads((ROOT / f"data/{name}.reference.json").read_text())
                result = module.reference(ROOT / f"data/{name}.FCIDUMP")
                self.assertEqual(result["fcidump_sha256"], recorded["fcidump_sha256"])
                self.assertAlmostEqual(result["fci_total_energy_hartree"], recorded["fci_total_energy_hartree"], places=10)

    def test_comparison_reports_inaccurate_energy_and_rejects_another_input(self):
        path = ROOT / "data/h2.FCIDUMP"
        reference = module.reference(path)
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            state.write_text(json.dumps(dict(fcidump_sha256=reference["fcidump_sha256"],
                             best_energy=reference["fci_total_energy_hartree"] + 0.01)))
            result = module.reference(path, state)
            self.assertFalse(result["matches_fci_at_1e_8"])
            self.assertAlmostEqual(result["absolute_error_hartree"], 0.01)
            state.write_text(json.dumps(dict(fcidump_sha256="another molecule", best_energy=0)))
            with self.assertRaisesRegex(ValueError, "same input"):
                module.reference(path, state)
