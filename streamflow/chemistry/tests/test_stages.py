import argparse
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import shutil
import runpy
import sys
from types import ModuleType
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("stages", ROOT / "cwl/stages.py")
stages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stages)


@contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(os.chdir, Path.cwd())
        os.chdir(self.root)
        environment = patch.dict(os.environ, {"SLURM_JOB_ID": "123", "SLURM_JOB_NODELIST": "c2",
                                             "QFW_RESERVATIONS": '[["nwqsim","test-reservation"]]'})
        environment.start()
        self.addCleanup(environment.stop)
        self.source = self.root / "application"
        scripts = self.source / "workflow/slurm"
        scripts.mkdir(parents=True)
        (self.source / "chemapp_fcidump_workflow.py").touch()
        original = os.environ.get("CHEMISTRY_TEST_SOURCE")
        if original:
            shutil.copyfile(Path(original) / "workflow/slurm/collect-results.sbatch", scripts / "collect-results.sbatch")
        self.full = self.root / "He.FCIDUMP"
        self.input = self.root / "He.inp"
        self.input.write_text(" $FMO NFRAG=4 $END\n")
        self.fragments = []
        blocks = []
        for kind, count in ((1, 4), (2, 6)):
            for index in range(1, count + 1):
                block = f" &FCI NORB={kind * 2}, NELEC={kind * 2},\n &END\n {index}.0 0 0 0 0\n"
                blocks.append(block)
                path = self.root / f"He.FCIDUMP-{kind}-{index}"
                path.write_text(block)
                self.fragments.append(path)
        self.full.write_text("".join(blocks))
        self.prepare_args = argparse.Namespace(stage="prepare", case_name="He4", gamess_input=self.input,
                                               fcidump=self.full, fragments=self.fragments)

    def prepared(self):
        stages.prepare(self.prepare_args)
        return self.root / "prepared"

    def calculations(self):
        prepared = self.prepared()
        manifest = json.loads((prepared / "preparation.json").read_text())
        calculations = []
        for index, fragment in enumerate(manifest["fragments"]):
            output = self.root / f"calculation-{index}"
            output.mkdir()
            name = fragment["name"]
            shutil.copyfile(prepared / fragment["group"] / name, output / name)
            backend = "nwqsim" if fragment["group"] == "a" else "fake-iqm"
            stages.write_json(output / "workflow-result.json", dict(fragment=name, backend=backend, energy=-1.0))
            stages.write_json(output / "submission.json", dict(state="completed", exit_code=0, job_id=200 + index,
                              fragment=name, backend=backend, result_kind="simulation" if backend == "nwqsim" else "synthetic",
                              input_sha256=fragment["sha256"], result_sha256=stages.digest(output / "workflow-result.json")))
            calculations.append(output)
        return argparse.Namespace(stage="collect", chemistry_source=self.source, prepared=prepared, calculations=calculations)

    def test_preparation_routes_five_fragments_per_group(self):
        prepared = self.prepared()
        for group in ("a", "b"):
            names = [path.name for path in (prepared / group).iterdir()]
            self.assertEqual(len(names), 5)
            self.assertEqual(sum("-1-" in name for name in names), 2)
            self.assertEqual(sum("-2-" in name for name in names), 3)

    def test_preparation_preserves_fragment_bytes_and_hashes(self):
        prepared = self.prepared()
        for item in json.loads((prepared / "preparation.json").read_text())["fragments"]:
            self.assertEqual(stages.digest(prepared / item["group"] / item["name"]), item["sha256"])
            self.assertEqual((prepared / item["group"] / item["name"]).read_bytes(), (self.root / item["name"]).read_bytes())

    def test_preparation_rejects_missing_fragment(self):
        self.prepare_args.fragments = self.fragments[:-1]
        with self.assertRaisesRegex(ValueError, "complete"):
            self.prepared()

    def test_preparation_rejects_duplicate_fragment(self):
        self.prepare_args.fragments = self.fragments + [self.fragments[0]]
        with self.assertRaisesRegex(ValueError, "complete"):
            self.prepared()

    def test_preparation_rejects_fragment_from_different_source(self):
        self.fragments[0].write_text(self.fragments[0].read_text().replace("1.0", "9.0"))
        with self.assertRaisesRegex(ValueError, "differs"):
            self.prepared()

    def test_preparation_rejects_invalid_full_fcidump(self):
        self.full.write_text("invalid\n")
        with self.assertRaisesRegex(ValueError, "headers"):
            self.prepared()

    def test_preparation_rejects_stale_output(self):
        self.prepared()
        with self.assertRaises(FileExistsError):
            stages.prepare(self.prepare_args)

    def test_stage_requires_slurm_allocation(self):
        with patch.dict(os.environ, {"SLURM_JOB_ID": ""}):
            with self.assertRaisesRegex(RuntimeError, "Slurm allocation"):
                stages.allocation()

    def test_quantum_stage_requires_matching_reservation(self):
        script = self.root / "fixture.sh"
        script.write_text("exit 0\n")
        output = self.root / "output"
        output.mkdir()
        args = argparse.Namespace(stage="chemistry", backend="nwqsim")
        for reservation in ("[]", '[["fake-iqm","id"]]', '["invalid"]'):
            with self.subTest(reservation=reservation), patch.dict(os.environ, {"QFW_RESERVATIONS": reservation}):
                with self.assertRaisesRegex(RuntimeError, "matching"):
                    stages.run_script(args, output, script, [])

    def test_iqm_reservation_matches_qpm_service_id(self):
        script = self.root / "fixture.sh"
        script.write_text("exit 0\n")
        output = self.root / "output"
        output.mkdir()
        args = argparse.Namespace(stage="chemistry", backend="iqm")
        with patch.dict(os.environ, {"QFW_RESERVATIONS": '[["iqm-ornl-20q","test-reservation"]]'}):
            record = stages.run_script(args, output, script, [])
        self.assertEqual(record["state"], "completed")

    def test_failed_script_records_failure_and_log(self):
        script = self.root / "fixture.sh"
        script.write_text("echo calculation-failed\nexit 7\n")
        output = self.root / "output"
        output.mkdir()
        args = argparse.Namespace(stage="chemistry", backend="nwqsim")
        with self.assertRaisesRegex(RuntimeError, "failed \\(7\\)"):
            stages.run_script(args, output, script, [])
        self.assertEqual(json.loads((output / "submission.json").read_text())["exit_code"], 7)
        self.assertIn("calculation-failed", (output / "slurm.out").read_text())

    def test_result_rejects_nonfinite_boolean_missing_energy(self):
        path = self.root / "result.json"
        for energy in (float("nan"), float("inf"), True, None):
            stages.write_json(path, dict(fragment="fragment", backend="nwqsim", energy=energy))
            with self.subTest(energy=energy), self.assertRaises(ValueError):
                stages.validate_result(path)

    def test_collection_rejects_missing_fragment(self):
        args = self.calculations()
        args.calculations.pop()
        with self.assertRaisesRegex(ValueError, "Missing"):
            stages.collect(args)

    def test_collection_rejects_duplicate_fragment(self):
        args = self.calculations()
        args.calculations.append(args.calculations[0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            stages.collect(args)

    def test_collection_rejects_modified_result(self):
        args = self.calculations()
        path = args.calculations[0] / "workflow-result.json"
        result = json.loads(path.read_text())
        result["energy"] = -5
        stages.write_json(path, result)
        with self.assertRaisesRegex(ValueError, "metadata"):
            stages.collect(args)

    def test_collection_rejects_modified_fragment(self):
        args = self.calculations()
        (args.calculations[0] / self.fragments[0].name).write_text("changed\n")
        with self.assertRaisesRegex(ValueError, "metadata"):
            stages.collect(args)

    def test_collection_rejects_failed_job(self):
        args = self.calculations()
        path = args.calculations[0] / "submission.json"
        record = json.loads(path.read_text())
        record["state"] = "failed"
        stages.write_json(path, record)
        with self.assertRaisesRegex(ValueError, "metadata"):
            stages.collect(args)

    @unittest.skipUnless(os.environ.get("CHEMISTRY_TEST_SOURCE"), "Set CHEMISTRY_TEST_SOURCE to chemistry_he")
    def test_original_collector_retains_all_fragments_and_marks_synthetic_result(self):
        args = self.calculations()
        stages.collect(args)
        result = json.loads((self.root / "results/workflow-results.json").read_text())
        self.assertEqual(result["backend_counts"], {"nwqsim": 5, "fake-iqm": 5})
        self.assertEqual(len(result["cases"]), 10)
        self.assertEqual(result["result_kind"], "synthetic")
        self.assertTrue(result["execution_check_only"])
        self.assertEqual(set(result), {"backend", "jobs", "cases", "case",
                                       "execution_check_only", "backend_counts", "result_kind"})

    @unittest.skipUnless(os.environ.get("CHEMISTRY_TEST_SOURCE"), "Set CHEMISTRY_TEST_SOURCE to chemistry_he")
    def test_collection_supports_both_bindings_using_one_provider(self):
        args = self.calculations()
        for calculation in args.calculations:
            result_path = calculation / "workflow-result.json"
            result = json.loads(result_path.read_text())
            result["backend"] = "nwqsim"
            stages.write_json(result_path, result)
            path = calculation / "submission.json"
            record = json.loads(path.read_text())
            record.update(backend="nwqsim", result_kind="simulation", result_sha256=stages.digest(result_path))
            stages.write_json(path, record)
        stages.collect(args)
        result = json.loads((self.root / "results/workflow-results.json").read_text())
        self.assertEqual(result["backend"], "nwqsim")
        self.assertEqual(result["backend_counts"], {"nwqsim": 10})
        self.assertEqual(result["result_kind"], "simulation")
        self.assertEqual(set(result), {"backend", "jobs", "cases", "case",
                                       "execution_check_only", "backend_counts", "result_kind"})


class FragmentAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "result.json"
        self.application = ModuleType("chemapp_fcidump_workflow")
        self.application.calculate = Mock(return_value=-1.0)
        self.puccd = ModuleType("puccd")
        self.puccd.puccd_initialize = Mock()
        self.puccd.puccd_finalize = Mock()

    def run_fragment(self):
        argv = ["fragment.py", "He.FCIDUMP-1-1", "nwqsim", str(self.output), "4096", "1", "18", "1"]
        with patch.dict(os.environ, {"CHEMISTRY_ROOT": str(self.root)}), patch.object(sys, "argv", argv), \
                patch.dict(sys.modules, {"chemapp_fcidump_workflow": self.application, "puccd": self.puccd}):
            previous = list(sys.path)
            try:
                runpy.run_path(str(ROOT / "cwl/fragment.py"), run_name="__main__")
            finally:
                sys.path[:] = previous

    def test_adapter_calls_upstream_calculation_with_qfw(self):
        self.run_fragment()
        self.puccd.puccd_initialize.assert_called_once_with(qfw=True, provider="nwqsim", shots=4096)
        self.application.calculate.assert_called_once_with("He.FCIDUMP-1-1", 1, 18, 1)
        self.puccd.puccd_finalize.assert_called_once_with(qfw=True)
        self.assertEqual(json.loads(self.output.read_text())["energy"], -1.0)

    def test_result_is_written_before_defw_shutdown_exits(self):
        self.puccd.puccd_finalize.side_effect = SystemExit(0)
        with self.assertRaises(SystemExit):
            self.run_fragment()
        self.assertTrue(self.output.is_file())

    def test_nonfinite_result_is_not_written(self):
        self.application.calculate.return_value = float("nan")
        with patch("sys.stderr"), self.assertRaises(ValueError):
            self.run_fragment()
        self.assertFalse(self.output.exists())
        self.puccd.puccd_finalize.assert_called_once_with(qfw=True)
