#!/usr/bin/env python3

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys

import yaml
from streamflow.config.validator import SfValidator


RESOURCES = {"nwqsim": ("nwqsim", "simulation"),
             "fake-iqm-20q": ("fake-iqm", "synthetic"),
             "ornl-iqm-20q": ("iqm", "hardware")}


def load_backend(bundle, config, step):
    workflow, = config["workflows"].values()
    binding, = [item for item in workflow["bindings"] if item["step"] == "/" + step]
    target = binding["target"]
    deployment = config["deployments"][target["deployment"]]
    if deployment["type"] != "slurm" or target["locations"] != 1:
        raise ValueError("Each fragment requires one native Slurm location")
    service = deployment["config"]["services"][target["service"]]
    script = (bundle / service["file"]).read_text()
    options = dict(re.findall(r"^#SBATCH --([\w-]+)=(\S+)\s*$", script, re.MULTILINE))
    resource = options.get("qpu")
    if resource not in RESOURCES or options.get("workload-kind") != "hybrid":
        raise ValueError(f"Unsupported quantum resource or workload kind for {step}")
    provider, kind = RESOURCES[resource]
    for option in ("max-shots", "circ-count", "max-qubits", "max-depth"):
        value = options.get(option, "")
        if not value.isdecimal() or int(value) < 1:
            raise ValueError(f"{step}: --{option} must be a positive integer")
    if int(options["max-shots"]) != 4096:
        raise ValueError("The chemistry estimator requires 4096 shots at its default precision")
    return dict(resource=resource, provider=provider, result_kind=kind, shots=4096)


def resolve_job(bundle, case, application, config):
    profile = yaml.safe_load((bundle / "profile.yml").read_text())
    if any(type(value) is not int or value < 1 for value in profile["optimizer"].values()):
        raise ValueError("Optimizer iteration limits must be positive integers")
    job = deepcopy({"case": case, "application": application})
    for group in ("a", "b"):
        selected = load_backend(bundle, config, "chemistry_" + group)
        job["settings_" + group] = {"qfw": dict(shared_root=profile["qfw"]["shared_root"], **selected),
                                     "optimizer": profile["optimizer"]}
    files = [job["application"], job["case"]["gamess_input"], job["case"]["fcidump"],
             *job["case"]["fragments"]]
    for item in files:
        item["path"] = str((bundle / item["path"]).resolve(strict=True))
    return job


def configure_slurm(bundle, run, config):
    profile = yaml.safe_load((bundle / "profile.yml").read_text())
    site = profile["slurm"]
    deployments = config["deployments"]
    deployments["slurm"]["workdir"] = str(run / "work")
    deployments["cluster-login"]["config"].update(
        nodes=[site["hostname"]], username=pwd.getpwuid(os.getuid()).pw_name,
        sshKey=str(Path(site["ssh_key"]).expanduser().resolve(strict=True)), checkHostKey=True)
    for service in deployments["slurm"]["config"]["services"].values():
        service["file"] = str((bundle / service["file"]).resolve(strict=True))


def write_configuration(bundle, run):
    catalog = yaml.safe_load((bundle / "cases.yml").read_text())
    names = [case["name"] for case in catalog["cases"]]
    if (not names or any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name) for name in names)
            or len(set(names)) != len(names)):
        raise ValueError("Case names must be unique, nonempty and safe for filenames")
    config = yaml.safe_load((bundle / "streamflow.yml").read_text())
    template, = config["workflows"].values()
    configs, jobs = {}, {}
    for case in catalog["cases"]:
        name = "chemistry-" + case["name"]
        job = resolve_job(bundle, case, catalog["application"], config)
        job_path = run / f"{name}.yml"
        job_path.write_text(yaml.safe_dump(job, sort_keys=False))
        instance = deepcopy(config)
        workflow = deepcopy(template)
        workflow["config"] = {"file": str(bundle / "cwl/workflow.cwl"), "settings": str(job_path)}
        instance["workflows"] = {name: workflow}
        instance["database"] = {"type": "sqlite", "config": {"connection": str(run / f"{name}.sqlite")}}
        configure_slurm(bundle, run, instance)
        config_path = run / f"streamflow-{name}.yml"
        config_path.write_text(yaml.safe_dump(instance, sort_keys=False))
        SfValidator().validate_file(str(config_path))
        configs[name], jobs[name] = config_path, job
    return configs, jobs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    bundle, run = args.bundle.resolve(strict=True), args.run_directory.resolve(strict=True)
    configs, jobs = write_configuration(bundle, run)
    bin_dir = Path(sys.executable).parent
    subprocess.run([str(bin_dir / "cwltool"), "--quiet", "--validate", str(bundle / "cwl/workflow.cwl")], check=True)
    for name, config in configs.items():
        subprocess.run([str(bin_dir / "streamflow"), "run", "--outdir", str(run / "output" / name), str(config)],
                       cwd=run, check=True)
    paths = list((run / "output").rglob("workflow-results.json"))
    if len(paths) != len(jobs):
        raise RuntimeError("Missing workflow results")
    summary = []
    for path in paths:
        aggregate = json.loads(path.read_text())
        job = jobs["chemistry-" + aggregate["case"]]
        expected = [Path(item["path"]).name for item in job["case"]["fragments"]]
        if set(aggregate["cases"]) != set(expected):
            raise RuntimeError("Unexpected fragment results")
        prepared = json.loads((path.parent / "preparation/preparation.json").read_text())
        chemistry = []
        for fragment in prepared["fragments"]:
            record = json.loads((path.parent / "fragments" / fragment["name"] / "submission.json").read_text())
            if record["backend"] != job["settings_" + fragment["group"]]["qfw"]["provider"]:
                raise RuntimeError("Fragment backend does not match its StreamFlow binding")
            chemistry.append({"fragment": fragment["name"], **{key: record[key] for key in
                              ("job_id", "nodes", "backend", "qpu", "result_kind", "qfw_reservations")}})
        collection = json.loads((path.parent / "submission.json").read_text())
        summary.append({"case": aggregate["case"], "backend_counts": aggregate["backend_counts"],
                        "result_kind": aggregate["result_kind"], "result": str(path),
                        "prepare": prepared["allocation"], "chemistry": chemistry,
                        "collect": {key: collection[key] for key in ("job_id", "nodes")}})
    (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
