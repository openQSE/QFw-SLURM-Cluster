from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import unittest
import uuid


BUNDLE = "/workspace/qfw-container-base/streamflow-sqd"


@unittest.skipUnless(os.environ.get("SQD_TEST_DOCKER") == "1", "Set SQD_TEST_DOCKER=1 on the Docker host")
class SlurmFailureTests(unittest.TestCase):
    def run_failure(self, fault):
        user = os.environ.get("QFW_USER", "user-a")
        run = BUNDLE + "/tests/failure-" + uuid.uuid4().hex[:12]
        script = '''
from pathlib import Path
import shutil,sys,yaml
bundle,run,fault=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
run.mkdir()
for name in ("cwl","data"):
    shutil.copytree(bundle/name,run/name)
for name in ("sqd.py","sample.sh","run.py","streamflow.yml","settings.json"):
    shutil.copyfile(bundle/name,run/name)
inputs=yaml.safe_load((bundle/"inputs.yml").read_text())
for item in inputs.values():item["path"]=str(bundle/item["path"])
if fault=="prepare":
    (run/"invalid.FCIDUMP").write_text("invalid input")
    inputs["fcidump"]["path"]=str(run/"invalid.FCIDUMP")
else:
    (run/"sample.sh").write_text("exit 7\\n")
(run/"inputs.yml").write_text(yaml.safe_dump(inputs))
'''
        subprocess.run(["docker", "exec", "-i", "--user", user, "slurmctld", BUNDLE + "/coordinator/bin/python",
                        "-", BUNDLE, run, fault], input=script, text=True, check=True)
        command = ["docker", "exec", "--user", user, "slurmctld", "bash", "-c",
                   '"$1/coordinator/bin/python" "$2/run.py" "$2" "$2" > "$2/streamflow.log" 2>&1', "_", BUNDLE, run]
        try:
            result = subprocess.run(command, text=True, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "exec", "--user", user, "slurmctld", "pkill", "-f", run], check=False)
            log = subprocess.check_output(["docker", "exec", "--user", user, "slurmctld", "cat", run + "/streamflow.log"], text=True)
            jobs = re.findall(r"with job id (\d+)", log)
            if jobs:
                subprocess.run(["docker", "exec", "slurmctld", "scancel", *jobs], check=False)
            self.fail("StreamFlow did not terminate after failure: " + run)
        log = subprocess.check_output(["docker", "exec", "--user", user, "slurmctld", "cat", run + "/streamflow.log"], text=True)
        self.assertNotEqual(result.returncode, 0, run)
        jobs = re.findall(r"Scheduled job .* with job id (\d+)", log)
        self.assertTrue(jobs, "Failure occurred before Slurm execution: " + run)
        self.assertNotIn("Scheduled job /iteration_1/select", log)
        self.assertNotIn("Scheduled job /iteration_1/solve", log)
        exists = subprocess.run(["docker", "exec", "--user", user, "slurmctld", "test", "-f", run + "/output/state.json"])
        self.assertNotEqual(exists.returncode, 0)
        if fault == "prepare":
            self.assertEqual(len(jobs), 1)
        else:
            quantum = subprocess.check_output(["docker", "exec", "slurmctld", "sacct", "-X", "-j", ",".join(jobs),
                       "--noheader", "--parsable2", "-o", "JobID,JobName,State"], text=True)
            quantum_jobs = [row.split("|")[0] for row in quantum.splitlines() if "|sqd-quantum|FAILED" in row]
            self.assertTrue(quantum_jobs, run)
            for job in quantum_jobs:
                allocation = json.loads(subprocess.check_output(["docker", "exec", "slurmctld", "cat",
                             f"/var/lib/qfw-slurm/allocations/linux-{job}.json"], text=True))
                self.assertEqual(allocation["state"], "released")
                self.assertEqual(allocation["release"]["unresolved_count"], 0)

    def test_invalid_input_blocks_quantum(self):
        self.run_failure("prepare")

    def test_quantum_failure_blocks_solver_and_releases_reservation(self):
        self.run_failure("quantum")


@unittest.skipUnless(os.environ.get("SQD_TEST_DOCKER") == "1", "Set SQD_TEST_DOCKER=1 on the Docker host")
class SlurmNumericalTests(unittest.TestCase):
    def test_h2_full_basis_matches_pyscf(self):
        user = os.environ.get("QFW_USER", "user-a")
        run = BUNDLE + "/tests/full-basis-" + uuid.uuid4().hex[:12]
        script = '''
from pathlib import Path
import hashlib,json,sys,yaml
bundle,run=map(Path,sys.argv[1:])
sys.path.insert(0,str(bundle))
from run import configure_services
run.mkdir()
samples=run/"samples"
samples.mkdir()
(samples/"counts.json").write_text(json.dumps(dict(counts={"0101":512,"1010":512},provider="controlled-test")))
(samples/"sampling.json").write_text(json.dumps(dict(counts_sha256=hashlib.sha256((samples/"counts.json").read_bytes()).hexdigest())))
(samples/"request.json").write_text(json.dumps(dict(walker=0,iteration=1,parameters=[],carryover=[],shots=1024)))
settings=json.loads((bundle/"settings.json").read_text())
settings["solver"].update(iteration=20,tolerance=1e-10)
(run/"settings.json").write_text(json.dumps(settings))
inputs={key:{"class":"File","path":str(path)} for key,path in
        (("fcidump",bundle/"data/h2.FCIDUMP"),("config",run/"settings.json"),
         ("solver",bundle/"source/algorithms/sbd/native/diag"))}
inputs["samples"]={"class":"Directory","path":str(samples)}
(run/"inputs.yml").write_text(yaml.safe_dump(inputs))
workflow={"cwlVersion":"v1.2","class":"Workflow",
          "requirements":yaml.safe_load((bundle/"cwl/workflow.cwl").read_text())["requirements"],
          "inputs":dict(fcidump="File",config="File",samples="Directory",solver="File"),
          "outputs":{"result":{"type":"Directory","outputSource":"solve/results"}},
          "steps":{"prepare":{"run":str(bundle/"cwl/tools.cwl")+"#prepare",
                    "in":dict(fcidump="fcidump",config="config"),"out":["problem","state"]},
                   "solve":{"run":str(bundle/"cwl/tools.cwl")+"#solve",
                    "in":dict(problem="prepare/problem",samples="samples",solver="solver"),"out":["results"]}}}
(run/"workflow.cwl").write_text(yaml.safe_dump(workflow))
config=yaml.safe_load((bundle/"streamflow.yml").read_text())
deployment=config["deployments"]["slurm"]
deployment["workdir"]=str(run/"work")
configure_services(config,run)
config["workflows"]={"control":{"type":"cwl","config":{"file":str(run/"workflow.cwl"),"settings":str(run/"inputs.yml")},
 "bindings":[{"step":"/"+step,"target":{"deployment":"slurm","service":service,"locations":1}}
             for step,service in (("prepare","classical"),("solve","solver"))]}}
config["database"]={"type":"sqlite","config":{"connection":str(run/"streamflow.sqlite")}}
(run/"streamflow.yml").write_text(yaml.safe_dump(config))
'''
        subprocess.run(["docker", "exec", "-i", "--user", user, "slurmctld", BUNDLE + "/coordinator/bin/python",
                        "-", BUNDLE, run], input=script, text=True, check=True)
        result = subprocess.run(["docker", "exec", "--user", user, "slurmctld", "bash", "-c",
                    '"$1/coordinator/bin/streamflow" run --outdir "$2/output" "$2/streamflow.yml" > "$2/streamflow.log" 2>&1',
                    "_", BUNDLE, run], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, run + "/streamflow.log")
        check = '''
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from reference import reference
result,=Path(sys.argv[2],"output").rglob("result.json")
print(json.dumps(dict(result=json.loads(result.read_text()),reference=reference(Path(sys.argv[1],"data/h2.FCIDUMP")))))
'''
        evidence = json.loads(subprocess.check_output(["docker", "exec", "-i", "--user", user,
                    "--env", "OMP_NUM_THREADS=1", "slurmctld", BUNDLE + "/application/bin/python", "-", BUNDLE, run],
                    input=check, text=True))
        self.assertEqual(set(evidence["result"]["basis"]), {1, 2})
        self.assertAlmostEqual(evidence["result"]["energy"], evidence["reference"]["fci_total_energy_hartree"], places=8)


@unittest.skipUnless(os.environ.get("SQD_TEST_DOCKER") == "1", "Set SQD_TEST_DOCKER=1 on the Docker host")
class SlurmParallelTests(unittest.TestCase):
    def run_parallel(self, inputs, walkers):
        user = os.environ.get("QFW_USER", "user-a")
        run_id = "parallel-" + uuid.uuid4().hex[:12]
        run = BUNDLE + "/runs/" + run_id
        launcher = Path(__file__).resolve().parents[1] / "run-local.sh"
        result = subprocess.run([str(launcher), inputs], env=dict(os.environ, SQD_RUN_ID=run_id),
                                text=True, capture_output=True, timeout=420)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.verify_run(run, walkers)

    def verify_run(self, run, walkers):
        user = os.environ.get("QFW_USER", "user-a")
        state = json.loads(subprocess.check_output(["docker", "exec", "--user", user, "slurmctld", "cat", run + "/output/state.json"], text=True))
        self.assertEqual(state["config"]["walkers"], walkers)
        self.assertEqual(state["iteration"], 2)
        self.assertEqual(len(state["history"]), 2)
        self.assertTrue(all(len(item["walkers"]) == walkers for item in state["history"]))
        for generation in state["history"]:
            for result in generation["walkers"]:
                settings = dict(state["config"]["solver"])
                settings["block"] = min(settings["block"], len(result["basis"]) ** 2)
                self.assertEqual(result["solver_settings"], settings)
        log = subprocess.check_output(["docker", "exec", "--user", user, "slurmctld", "cat", run + "/streamflow.log"], text=True)
        all_jobs = re.findall(r"Scheduled job .* with job id (\d+)", log)
        accounting = subprocess.check_output(["docker", "exec", "slurmctld", "sacct", "-X", "-j", ",".join(all_jobs),
                     "--noheader", "--parsable2", "-o", "JobID,State,ExitCode,Start,End"], text=True)
        events = []
        for row in accounting.splitlines():
            fields = row.split("|")
            self.assertEqual(fields[1:3], ["COMPLETED", "0:0"], accounting)
            start, end = (datetime.fromisoformat(value) for value in fields[3:5])
            if start < end:
                events.extend(((start, 1), (end, -1)))
        running = peak = 0
        for _, change in sorted(events):
            running += change
            peak = max(peak, running)
        self.assertLessEqual(peak, 4, accounting)
        groups = {}
        for iteration, stage, job in re.findall(r"Scheduled job /iteration_(\d+)/(sample|solve)/\S+ with job id (\d+)", log):
            groups.setdefault((iteration, stage), []).append(job)
        self.assertEqual(set(groups), {("1", "sample"), ("1", "solve"), ("2", "sample"), ("2", "solve")})
        for (iteration, stage), jobs in groups.items():
            with self.subTest(iteration=iteration, stage=stage):
                self.assertEqual(len(jobs), walkers)
                accounting = subprocess.check_output(["docker", "exec", "slurmctld", "sacct", "-X", "-j", ",".join(jobs),
                             "--noheader", "--parsable2", "-o", "JobID,State,ExitCode,Start,End,NodeList,NNodes"], text=True)
                rows = [row.split("|") for row in accounting.splitlines()]
                self.assertEqual(len(rows), walkers)
                self.assertTrue(all(row[1:3] == ["COMPLETED", "0:0"] for row in rows), accounting)
                events, used, allocations = [], set(), []
                for row in rows:
                    start, end = (datetime.fromisoformat(value) for value in row[3:5])
                    self.assertLess(start, end, accounting)
                    events.extend(((start, 1), (end, -1)))
                    nodes = set(subprocess.check_output(["docker", "exec", "slurmctld", "scontrol", "show", "hostnames", row[5]], text=True).split())
                    self.assertEqual(len(nodes), 2 if stage == "solve" else 1)
                    for previous_start, previous_end, previous_nodes in allocations:
                        if start < previous_end and previous_start < end:
                            self.assertFalse(nodes.intersection(previous_nodes), accounting)
                    allocations.append((start, end, nodes))
                    used.update(nodes)
                    if stage == "sample":
                        allocation = json.loads(subprocess.check_output(["docker", "exec", "slurmctld", "cat",
                                     f"/var/lib/qfw-slurm/allocations/linux-{row[0]}.json"], text=True))
                        self.assertEqual(allocation["state"], "released")
                        self.assertEqual(allocation["release"]["unresolved_count"], 0)
                running = peak = 0
                for _, change in sorted(events):
                    running += change
                    peak = max(peak, running)
                self.assertGreaterEqual(peak, 2, accounting)
                self.assertLessEqual(peak, 4, accounting)
                self.assertTrue(used.issubset({f"c{i}" for i in range(1, 9)}))

    def test_walkers_overlap_with_two_node_sbd(self):
        self.run_parallel("inputs.yml", 4)

    def test_eight_walkers_respect_job_window_and_queue_sbd(self):
        self.run_parallel("inputs-h4.yml", 8)
