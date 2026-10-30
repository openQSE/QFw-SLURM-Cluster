from copy import deepcopy
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("runner", ROOT / "run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bundle = Path(self.temp.name)
        shutil.copytree(ROOT / "slurm", self.bundle / "slurm")
        self.config = yaml.safe_load((ROOT / "streamflow.yml").read_text())
        profile_path = ROOT / "local.yml" if (ROOT / "local.yml").exists() else ROOT / "profile.yml"
        profile = yaml.safe_load(profile_path.read_text())
        self.key = self.bundle / "key"
        self.key.touch()
        profile["slurm"]["ssh_key"] = str(self.key)
        (self.bundle / "profile.yml").write_text(yaml.safe_dump(profile))
        self.application = {"class": "Directory", "path": "."}
        for name in ("input.inp", "FCIDUMP", "FCIDUMP-1-1"):
            (self.bundle / name).touch()
        self.case = {"name": "Test", "gamess_input": {"class": "File", "path": "input.inp"},
                     "fcidump": {"class": "File", "path": "FCIDUMP"},
                     "fragments": [{"class": "File", "path": "FCIDUMP-1-1"}]}

    def test_default_deployment_bindings_use_nwqsim_for_all_fragments(self):
        job = runner.resolve_job(self.bundle, self.case, self.application, self.config)
        self.assertEqual(job["settings_a"]["qfw"]["provider"], "nwqsim")
        self.assertEqual(job["settings_b"]["qfw"]["provider"], "nwqsim")
        self.assertEqual(job["settings_b"]["qfw"]["resource"], "nwqsim")
        self.assertEqual(job["settings_b"]["qfw"]["result_kind"], "simulation")

    def test_changing_only_binding_changes_provider(self):
        self.config["workflows"]["chemistry"]["bindings"][1]["target"]["service"] = "chemistry-fake-iqm"
        job = runner.resolve_job(self.bundle, self.case, self.application, self.config)
        self.assertEqual(job["settings_a"]["qfw"]["provider"], "fake-iqm")

    def test_iqm_binding_uses_public_qpu_and_application_provider(self):
        self.config["workflows"]["chemistry"]["bindings"][2]["target"]["service"] = "chemistry-iqm"
        job = runner.resolve_job(self.bundle, self.case, self.application, self.config)
        self.assertEqual(job["settings_b"]["qfw"], dict(shared_root="/workspace/qfw-container-base",
                         resource="ornl-iqm-20q", provider="iqm", result_kind="hardware", shots=4096))

    def test_configure_preserves_services_and_bindings(self):
        bindings = deepcopy(self.config["workflows"]["chemistry"]["bindings"])
        services = self.config["deployments"]["slurm"]["config"]["services"]
        expected = set(services)
        runner.configure_slurm(self.bundle, self.bundle, self.config)
        self.assertEqual(bindings, self.config["workflows"]["chemistry"]["bindings"])
        self.assertEqual(expected, set(services))
        self.assertTrue(all(Path(value["file"]).is_absolute() for value in services.values()))

    def test_resolve_preserves_catalog_and_resolves_all_files(self):
        original = deepcopy(self.case)
        job = runner.resolve_job(self.bundle, self.case, self.application, self.config)
        self.assertEqual(self.case, original)
        self.assertTrue(Path(job["case"]["fragments"][0]["path"]).is_absolute())

    def test_missing_input_is_rejected(self):
        (self.bundle / "FCIDUMP-1-1").unlink()
        with self.assertRaises(FileNotFoundError):
            runner.resolve_job(self.bundle, self.case, self.application, self.config)

    def test_invalid_optimizer_is_rejected(self):
        path = self.bundle / "profile.yml"
        profile = yaml.safe_load(path.read_text())
        profile["optimizer"]["macro_iterations"] = 0
        path.write_text(yaml.safe_dump(profile))
        with self.assertRaisesRegex(ValueError, "positive"):
            runner.resolve_job(self.bundle, self.case, self.application, self.config)

    def test_invalid_resource_and_bounds_are_rejected(self):
        path = self.bundle / "slurm/chemistry-nwqsim.sbatch"
        original = path.read_text()
        for old, new in (("--qpu=nwqsim", "--qpu=unknown"), ("--workload-kind=hybrid", "--workload-kind=classical"),
                         ("--max-depth=1000", "--max-depth=0"), ("--max-shots=4096", "--max-shots=16")):
            with self.subTest(option=new):
                path.write_text(original.replace(old, new))
                with self.assertRaises(ValueError):
                    runner.load_backend(self.bundle, self.config, "chemistry_a")

    def test_duplicate_case_names_are_rejected(self):
        (self.bundle / "cases.yml").write_text(yaml.safe_dump({"application": self.application, "cases": [self.case, self.case]}))
        with self.assertRaisesRegex(ValueError, "unique"):
            runner.write_configuration(self.bundle, self.bundle)

    def test_multiple_cases_have_separate_streamflow_configurations(self):
        second = dict(self.case, name="Other")
        (self.bundle / "cases.yml").write_text(yaml.safe_dump({"application": self.application, "cases": [self.case, second]}))
        (self.bundle / "streamflow.yml").write_text(yaml.safe_dump(self.config))
        configs, jobs = runner.write_configuration(self.bundle, self.bundle)
        self.assertEqual(len(jobs), 2)
        databases = set()
        for path in configs.values():
            config = yaml.safe_load(path.read_text())
            self.assertEqual(len(config["workflows"]), 1)
            databases.add(config["database"]["config"]["connection"])
        self.assertEqual(len(databases), 2)

    def test_catalog_lists_four_monomers_and_six_dimers(self):
        case, = yaml.safe_load((ROOT / "cases.yml").read_text())["cases"]
        names = [Path(item["path"]).name for item in case["fragments"]]
        self.assertEqual(len(names), 10)
        self.assertEqual(sum(".FCIDUMP-1-" in name for name in names), 4)
        self.assertEqual(sum(".FCIDUMP-2-" in name for name in names), 6)
