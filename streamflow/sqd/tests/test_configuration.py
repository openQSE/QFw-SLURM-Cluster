import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sqd_runner", ROOT / "run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        for name in ("cwl", "data"):
            shutil.copytree(ROOT / name, self.bundle / name)
        for name in ("settings.json", "streamflow.yml"):
            shutil.copyfile(ROOT / name, self.bundle / name)
        for name in ("sampler.py", "solver"):
            (self.bundle / name).touch()
        inputs = {key: {"class": "File", "path": path} for key, path in
                  (("fcidump", "data/h2.FCIDUMP"), ("config", "settings.json"),
                   ("sampler", "sampler.py"), ("solver", "solver"))}
        (self.bundle / "inputs.yml").write_text(yaml.safe_dump(inputs))
        self.run = self.root / "run"
        self.run.mkdir()

    def test_iterations_are_standard_cwl_with_explicit_state_dependencies(self):
        runner.configure(self.bundle, self.run)
        workflow = yaml.safe_load((self.run / "workflow.cwl").read_text())
        self.assertEqual(set(workflow["steps"]), {"prepare", "iteration_1", "iteration_2"})
        self.assertEqual(workflow["steps"]["iteration_1"]["in"]["state"], "prepare/state")
        self.assertEqual(workflow["steps"]["iteration_2"]["in"]["state"], "iteration_1/next_state")
        self.assertEqual(workflow["outputs"]["result"]["outputSource"], "iteration_2/next_state")
        self.assertNotIn("cwltool:Loop", (self.run / "workflow.cwl").read_text())
        environment = workflow["requirements"]["EnvVarRequirement"]["envDef"]
        self.assertEqual(environment["QFW_SHARED_ROOT"], "/workspace/qfw-container-base")
        self.assertEqual(environment["OMP_NUM_THREADS"], "1")

    def test_native_slurm_bindings_are_preserved_for_every_iteration(self):
        path, count = runner.configure(self.bundle, self.run)
        config = yaml.safe_load(path.read_text())
        self.assertEqual(count, 2)
        bindings = {item["step"]: item["target"]["service"] for item in config["workflows"]["sqd"]["bindings"]}
        for index in (1, 2):
            self.assertEqual(bindings[f"/iteration_{index}/sample"], "quantum")
            self.assertEqual(bindings[f"/iteration_{index}/solve"], "solver")
        self.assertEqual(config["deployments"]["slurm"]["config"]["maxConcurrentJobs"], 4)
        self.assertNotIn("wraps", config["deployments"]["slurm"])
        services = config["deployments"]["slurm"]["config"]["services"]
        self.assertTrue(all("nodelist" not in service for service in services.values()))
        self.assertEqual((services["solver"]["nodes"], services["solver"]["ntasksPerNode"]), ("2", 1))
        script = Path(services["quantum"]["file"]).read_text()
        self.assertIn("#SBATCH --qpu=nwqsim", script)
        self.assertIn("#SBATCH --max-shots=4096", script)
        self.assertTrue(all("script" not in value and "qfw" not in value for value in services.values()))

    def test_invalid_iteration_count_fails_before_submission(self):
        path = self.bundle / "settings.json"
        config = json.loads(path.read_text())
        config["iterations"] = 0
        path.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, "iterations"):
            runner.configure(self.bundle, self.run)

    def test_missing_input_fails_before_submission(self):
        (self.bundle / "solver").unlink()
        with self.assertRaises(FileNotFoundError):
            runner.configure(self.bundle, self.run)

    def test_alternative_input_paths_are_relative_to_the_input_file(self):
        directory = self.bundle / "cases"
        directory.mkdir()
        (directory / "settings.json").write_text(json.dumps(dict(walkers=8, iterations=2)))
        inputs = yaml.safe_load((self.bundle / "inputs.yml").read_text())
        for item in inputs.values():
            item["path"] = "../" + item["path"]
        inputs["fcidump"]["path"] = "../data/h4.FCIDUMP"
        inputs["config"]["path"] = "settings.json"
        (directory / "inputs.yml").write_text(yaml.safe_dump(inputs))
        runner.configure(self.bundle, self.run, "cases/inputs.yml")
        result = yaml.safe_load((self.run / "inputs.yml").read_text())
        self.assertEqual(result["fcidump"]["path"], str(self.bundle / "data/h4.FCIDUMP"))
        self.assertEqual(result["config"]["path"], str(directory / "settings.json"))
        self.assertEqual(json.loads((self.bundle / "settings.json").read_text())["walkers"], 4)
