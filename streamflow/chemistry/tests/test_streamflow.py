import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
VENV = "/workspace/qfw-container-base/streamflow-chemistry/venv-0.2.0rc3"


@unittest.skipUnless(os.environ.get("CHEMISTRY_TEST_DOCKER") == "1", "Set CHEMISTRY_TEST_DOCKER=1 on the Docker host")
class StreamFlowFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.user = os.environ.get("QFW_USER", "user-a")
        mounts = json.loads(subprocess.check_output(["docker", "inspect", "slurmctld", "--format", "{{json .Mounts}}"], text=True))
        source = next(item["Source"] for item in mounts if item["Destination"] == "/workspace/qfw-container-base")
        cls.shared = Path(source.removeprefix("/host_mnt") if sys.platform == "darwin" else source)
        cls.home = cls.docker("getent", "passwd", cls.user).strip().split(":")[5]
        if not cls.home.startswith("/workspace/home/") or cls.user == "root":
            raise RuntimeError("Tests require a non-root application user with a shared home")

    @staticmethod
    def docker(*command):
        return subprocess.check_output(["docker", "exec", "slurmctld", *command], text=True)

    def run_failure(self, fault, expected_stages):
        token = "failure-" + uuid.uuid4().hex[:12]
        bundle = self.shared / "streamflow-chemistry/tests" / token
        bundle.mkdir(parents=True)
        for directory in ("cwl", "slurm"):
            shutil.copytree(ROOT / directory, bundle / directory)
        for name in ("run.py", "streamflow.yml"):
            shutil.copyfile(ROOT / name, bundle / name)
        shutil.copyfile(ROOT / "local.yml", bundle / "profile.yml")
        source = bundle / "application"
        scripts = source / "workflow/slurm"
        scripts.mkdir(parents=True)
        (source / "chemapp_fcidump_workflow.py").touch()
        (bundle / "input.inp").write_text(" $FMO NFRAG=2 $END\n")
        fragments = []
        blocks = []
        for kind, count in ((1, 2), (2, 1)):
            for index in range(1, count + 1):
                name = f"FCIDUMP-{kind}-{index}"
                block = f" &FCI NORB={kind * 2}, NELEC={kind * 2},\n &END\n {index}.0 0 0 0 0\n"
                (bundle / name).write_text(block)
                blocks.append(block)
                fragments.append({"class": "File", "path": name})
        (bundle / "FCIDUMP").write_text("".join(blocks))
        case = {"cases": [{"name": "FailureTest", "gamess_input": {"class": "File", "path": "input.inp"},
                          "fcidump": {"class": "File", "path": "FCIDUMP"}, "fragments": fragments}],
                "application": {"class": "Directory", "path": "application"}}
        (bundle / "cases.yml").write_text(json.dumps(case))
        config = bundle / "streamflow.yml"
        config.write_text(config.read_text().replace("service: chemistry-nwqsim", "service: chemistry-fake-iqm"))
        fixture = "python3 - \"$1\" \"$2\" \"$3\" <<'PYTHON'\nimport json, sys\nfrom pathlib import Path\nfragment, backend, output = sys.argv[1:]\n(Path(output) / 'workflow-result.json').write_text(json.dumps(dict(fragment=Path(fragment).name, backend=backend, energy=-1.0)))\nPYTHON\n"
        (bundle / "cwl/fragment.sh").write_text("exit 7\n" if fault == "chemistry" else fixture)
        (scripts / "collect-results.sbatch").write_text("exit 9\n")
        if fault == "prepare":
            (bundle / "FCIDUMP").write_text("invalid integral input\n")
        elif fault == "submission":
            path = bundle / "slurm/prepare.sbatch"
            path.write_text(path.read_text().replace("--partition=normal", "--partition=sf-no-such-partition"))

        container_bundle = "/workspace/qfw-container-base/" + str(bundle.relative_to(self.shared))
        container_run = self.home + "/chemistry-test-" + token
        run = self.shared / "home" / self.home.removeprefix("/workspace/home/") / ("chemistry-test-" + token)
        subprocess.run(["docker", "exec", "--user", self.user, "slurmctld", "mkdir", container_run], check=True)
        command = ["docker", "exec", "--user", self.user, "--env", "HOME=" + self.home, "slurmctld",
                   VENV + "/bin/python", container_bundle + "/run.py", container_bundle, container_run]
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
            log, returncode = result.stdout, result.returncode
        except subprocess.TimeoutExpired as error:
            log = (error.stdout or b"").decode()
            subprocess.run(["docker", "exec", "--user", self.user, "slurmctld", "pkill", "-f", container_run], check=False)
            jobs = re.findall(r"with job id (\d+)", log)
            if jobs:
                self.docker("scancel", *jobs)
            (run / "streamflow.log").write_text(log)
            self.fail(f"StreamFlow did not terminate after failure; see {run}")
        (run / "streamflow.log").write_text(log)
        self.assertIn("EXECUTING workflow", log, f"Failure happened before StreamFlow execution: {run}")
        self.assertNotEqual(returncode, 0, f"Failure was reported as success: {run}")
        self.assertFalse((run / "summary.json").exists())
        self.assertFalse(any((run / "output").rglob("workflow-results.json")))
        jobs = re.findall(r"Scheduled job .* with job id (\d+)", log)
        if fault in ("submission", "prepare"):
            self.assertEqual(len(jobs), len(expected_stages), f"Unexpected downstream execution: {run}")
        if fault == "submission":
            self.assertIn("sf-no-such-partition", log)
        rows, releases = [], []
        if jobs:
            accounting = self.docker("sacct", "-j", ",".join(jobs), "-X", "--parsable2", "--noheader",
                                     "-o", "JobID,JobName,State,ExitCode,NodeList")
            (run / "sacct.txt").write_text(accounting)
            by_id = {row.split("|")[0]: row.split("|") for row in accounting.splitlines() if row}
            seen = []
            for job in jobs:
                row = by_id[job]
                stage = row[1].removeprefix("sf-")
                seen.append(stage)
                self.assertIn(stage, expected_stages)
                self.assertEqual(row[4], {"prepare": "c1", "chemistry": "c2", "collect": "c3"}[stage])
                if stage == fault:
                    self.assertIn(row[2], ("FAILED", "CANCELLED"))
                else:
                    self.assertEqual(row[2], "COMPLETED")
                rows.append(dict(zip(("job_id", "name", "state", "exit_code", "node"), row)))
                if stage == "chemistry":
                    record = json.loads(self.docker("cat", f"/var/lib/qfw-slurm/allocations/linux-{job}.json"))
                    self.assertEqual(record["state"], "released")
                    self.assertEqual(record["release"]["unresolved_count"], 0)
                    self.assertTrue(record["reservations"])
                    self.assertTrue(all(pair[0] == "fake-iqm" for pair in record["reservations"]))
                    releases.append({"job_id": job, "state": record["state"], "unresolved_count": 0})
            self.assertEqual(set(seen), set(expected_stages))
            if fault == "collect":
                self.assertEqual(seen.count("chemistry"), 3)
        evidence = {"fault": fault, "exit_code": returncode, "jobs": rows, "releases": releases,
                    "downstream_blocked": True, "application": "isolated test fixture", "hardware_executed": False}
        (run / "verification.json").write_text(json.dumps(evidence, indent=2) + "\n")

    def test_rejected_slurm_submission_does_not_start_any_stage(self):
        self.run_failure("submission", ())

    def test_failed_preparation_blocks_chemistry_and_collection(self):
        self.run_failure("prepare", ("prepare",))

    def test_failed_chemistry_blocks_collection_and_releases_reservation(self):
        self.run_failure("chemistry", ("prepare", "chemistry"))

    def test_failed_collection_is_not_reported_as_workflow_success(self):
        self.run_failure("collect", ("prepare", "chemistry", "collect"))
