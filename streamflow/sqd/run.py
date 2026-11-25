#!/usr/bin/env python3

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import yaml


def configure_services(config, run):
    for name, service in config["deployments"]["slurm"]["config"]["services"].items():
        qfw = service.pop("qfw", {})
        if qfw:
            path = run / f"{name}.sh"
            path.write_text("\n".join(["#!/bin/sh", *(f"#SBATCH --{key}={value}" for key, value in qfw.items()), "{{ streamflow_command }}\n"]))
            service["file"] = str(path)


def configure(bundle, run, inputs="inputs.yml"):
    inputs = (bundle / inputs).resolve(strict=True)
    job = yaml.safe_load(inputs.read_text())
    for item in job.values():
        item["path"] = str((inputs.parent / item["path"]).resolve(strict=True))
    iterations = json.loads(Path(job["config"]["path"]).read_text())["iterations"]
    if type(iterations) is not int or iterations < 1:
        raise ValueError("iterations must be a positive integer")
    workflow = yaml.safe_load((bundle / "cwl/workflow.cwl").read_text())
    template = workflow["steps"].pop("iteration")
    workflow["steps"]["prepare"]["run"] = str(bundle / "cwl/tools.cwl") + "#prepare"
    state = "prepare/state"
    names = []
    for index in range(iterations):
        name = f"iteration_{index + 1}"
        names.append(name)
        step = deepcopy(template)
        step["run"] = str(bundle / "cwl/iteration.cwl")
        step["in"]["state"] = state
        workflow["steps"][name] = step
        state = name + "/next_state"
    workflow["outputs"]["result"]["outputSource"] = state
    (run / "workflow.cwl").write_text(yaml.safe_dump(workflow, sort_keys=False))
    (run / "inputs.yml").write_text(yaml.safe_dump(job))
    config = yaml.safe_load((bundle / "streamflow.yml").read_text())
    deployment = config["deployments"]["slurm"]
    deployment["workdir"] = str(run / "work")
    configure_services(config, run)
    definition = config["workflows"]["sqd"]
    bindings = definition["bindings"]
    definition["bindings"] = [deepcopy(binding) for binding in bindings if binding["step"] == "/prepare"]
    for name in names:
        for binding in bindings:
            if binding["step"].startswith("/iteration"):
                copy = deepcopy(binding)
                copy["step"] = copy["step"].replace("/iteration", "/" + name, 1)
                definition["bindings"].append(copy)
    definition["config"] = {"file": str(run / "workflow.cwl"), "settings": str(run / "inputs.yml")}
    config["database"] = {"type": "sqlite", "config": {"connection": str(run / "streamflow.sqlite")}}
    path = run / "streamflow.yml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return path, iterations


def main():
    from streamflow.config.validator import SfValidator

    bundle, run = (Path(value).resolve(strict=True) for value in sys.argv[1:3])
    config, iterations = configure(bundle, run, sys.argv[3] if len(sys.argv) > 3 else "inputs.yml")
    SfValidator().validate_file(str(config))
    command = Path(sys.executable).parent / "streamflow"
    subprocess.run([str(command), "run", "--outdir", str(run / "output"), str(config)], cwd=run, check=True)
    state = json.loads((run / "output/state.json").read_text())
    if state["iteration"] != iterations:
        raise RuntimeError("The SQD loop did not complete")
    print(f"Best energy: {state['best_energy']}")


if __name__ == "__main__":
    main()
