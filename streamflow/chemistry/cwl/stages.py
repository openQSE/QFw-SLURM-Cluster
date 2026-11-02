#!/usr/bin/env python3

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def allocation():
    job_id = os.environ.get("SLURM_JOB_ID", "")
    if not re.fullmatch(r"[1-9][0-9]*", job_id):
        raise RuntimeError("This stage requires a Slurm allocation from StreamFlow's native connector")
    return {"job_id": int(job_id), "hostname": socket.gethostname(),
            "nodes": os.environ.get("SLURM_JOB_NODELIST", ""),
            "qfw_reservations": os.environ.get("QFW_RESERVATIONS", "")}


def fresh_output(name):
    output = Path(name).resolve()
    output.mkdir()
    return output


def run_script(args, output, script, script_args, metadata=None, env=None):
    batch = Path(script)
    if not batch.is_absolute():
        batch = args.chemistry_source / "workflow/slurm" / batch
    batch = batch.resolve(strict=True)
    record = dict(metadata or {}, stage=args.stage, script=batch.name,
                  allocation_owner="streamflow", **allocation())
    if args.stage == "chemistry":
        reservations = json.loads(record["qfw_reservations"] or "[]")
        if (not isinstance(reservations, list) or not reservations or
                any(not isinstance(pair, list) or len(pair) != 2 or
                    any(not isinstance(value, str) or not value for value in pair)
                    or pair[0] != {"nwqsim": "nwqsim", "fake-iqm": "fake-iqm", "iqm": "iqm-ornl-20q"}[args.backend]
                    for pair in reservations)):
            raise RuntimeError("Quantum stage has no matching QFw reservation")
    record["state"] = "running"
    write_json(output / "submission.json", record)
    with (output / "slurm.out").open("w") as log:
        result = subprocess.run(["bash", str(batch), *map(str, script_args)],
                                env=env, stdout=log, stderr=subprocess.STDOUT)
    record.update(state="completed" if result.returncode == 0 else "failed",
                  exit_code=result.returncode)
    write_json(output / "submission.json", record)
    if result.returncode:
        raise RuntimeError(f"Application script failed ({result.returncode}); see {output / 'slurm.out'}")
    return record


def normalized(text):
    text = re.sub(r"(\bISYM\s*=\s*\d+)\s+(?=UHF\s*=)", r"\1,", text, flags=re.IGNORECASE)
    return re.sub(r"(?<=\d)[dD](?=[+-]\d)", "E", text)


def prepare(args):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.case_name):
        raise ValueError("Invalid case name")
    match = re.search(r"\bNFRAG\s*=\s*(\d+)", args.gamess_input.read_text(), re.IGNORECASE)
    count = int(match.group(1)) if match else 1
    if count < 1:
        raise ValueError("NFRAG must be positive")
    blocks = re.split(r"(?=^\s*&FCI\b)", args.fcidump.read_text(), flags=re.MULTILINE | re.IGNORECASE)
    blocks = [block for block in blocks if block.strip()]
    electrons = [re.search(r"\bNELEC\s*=\s*(\d+)", block, re.IGNORECASE) for block in blocks]
    if not blocks or any(value is None for value in electrons):
        raise ValueError("Invalid FCIDUMP headers")
    smallest = min(int(value.group(1)) for value in electrons)
    expected = []
    for kind, size in ((1, count), (2, count * (count - 1) // 2)):
        selected = [block for block, value in zip(blocks, electrons) if int(value.group(1)) == smallest * kind]
        if len(selected) < size:
            raise ValueError("FCIDUMP does not contain the expected final fragments")
        if size:
            expected.extend((f"{args.fcidump.name}-{kind}-{index}", normalized(block))
                            for index, block in enumerate(selected[-size:], 1))
    supplied = {path.name: path for path in args.fragments}
    if len(supplied) != len(args.fragments) or set(supplied) != {name for name, _ in expected}:
        raise ValueError("Fragment inputs do not match the complete monomer/dimer set")
    for name, block in expected:
        if supplied[name].read_text() != block:
            raise ValueError(f"Fragment differs from its source FCIDUMP: {name}")
    output = fresh_output("prepared")
    shutil.copyfile(args.gamess_input, output / "input.inp")
    fragments = []
    for index, (name, _) in enumerate(expected):
        group = "a" if index % 2 == 0 else "b"
        (output / group).mkdir(exist_ok=True)
        shutil.copyfile(supplied[name], output / group / name)
        fragments.append({"name": name, "group": group, "sha256": digest(supplied[name])})
    write_json(output / "preparation.json", {
        "case_name": args.case_name, "allocation": allocation(),
        "fragments": fragments,
        "fcidump_sha256": digest(args.fcidump), "input_sha256": digest(args.gamess_input),
    })


def validate_result(path):
    result = json.loads(Path(path).read_text())
    if (not isinstance(result, dict) or not isinstance(result.get("fragment"), str)
            or result.get("backend") not in ("nwqsim", "fake-iqm", "iqm")
            or type(result.get("energy")) not in (int, float) or not math.isfinite(result["energy"])):
        raise ValueError("Invalid fragment result or non-finite energy")
    return result


def chemistry(args):
    source = args.chemistry_source.resolve(strict=True)
    output = fresh_output("chemistry")
    fragment = output / args.fragment.name
    shutil.copyfile(args.fragment, fragment)
    env = dict(os.environ, CHEMISTRY_ROOT=str(source), QFW_SHOTS=str(args.shots),
               MAX_MACRO_ITERATIONS=str(args.max_macro_iterations),
               MAX_AMPLITUDE_ITERATIONS=str(args.max_amplitude_iterations),
               MAX_ORBITAL_ITERATIONS=str(args.max_orbital_iterations))
    metadata = {"backend": args.backend, "qpu": args.qpu, "execution_check_only": True,
                "result_kind": args.result_kind, "shots": args.shots,
                "fragment": fragment.name, "input_sha256": digest(fragment),
                "application_sha256": digest(source / "chemapp_fcidump_workflow.py")}
    record = run_script(args, output, Path("fragment.sh").resolve(),
                        [fragment, args.backend, output], metadata, env)
    result = validate_result(output / "workflow-result.json")
    if result["fragment"] != fragment.name or result["backend"] != args.backend:
        raise ValueError("Fragment result does not match the requested input/backend")
    record["result_sha256"] = digest(output / "workflow-result.json")
    write_json(output / "submission.json", record)


def collect(args):
    prepared = json.loads((args.prepared / "preparation.json").read_text())
    expected = {item["name"]: item for item in prepared["fragments"]}
    if digest(args.prepared / "input.inp") != prepared["input_sha256"]:
        raise ValueError("Input metadata changed after preparation")
    records, results = {}, {}
    for calculation in args.calculations:
        record = json.loads((calculation / "submission.json").read_text())
        result = validate_result(calculation / "workflow-result.json")
        name = result["fragment"]
        if name not in expected or name in records:
            raise ValueError("Unknown or duplicate fragment result")
        if (record.get("state") != "completed" or record.get("exit_code") != 0
                or type(record.get("job_id")) is not int or record["job_id"] < 1
                or record.get("fragment") != name or record.get("backend") != result["backend"]
                or record.get("result_kind") != {"nwqsim": "simulation", "fake-iqm": "synthetic", "iqm": "hardware"}[result["backend"]]
                or record.get("input_sha256") != expected[name]["sha256"]
                or digest(calculation / name) != expected[name]["sha256"]
                or record.get("result_sha256") != digest(calculation / "workflow-result.json")):
            raise ValueError("Fragment output does not match successful submission metadata")
        records[name], results[name] = (calculation, record), result
    if set(records) != set(expected):
        raise ValueError("Missing fragment results")
    output = fresh_output("results")
    shutil.copytree(args.prepared, output / "preparation")
    lines = []
    for name, (calculation, record) in sorted(records.items()):
        target = output / "fragments" / name
        shutil.copytree(calculation, target)
        fields = [name, str(output / "preparation/input.inp"), "0", str(record["job_id"]),
                  str(target / "workflow-result.json")]
        if any(any(char in field for char in "\t\r\n") for field in fields):
            raise ValueError("Job plan fields must not contain tabs or newlines")
        lines.append("\t".join(fields))
    plan = output / "jobs.tsv"
    plan.write_text("\n".join(lines) + "\n")
    providers = {result["backend"] for result in results.values()}
    backend = next(iter(providers)) if len(providers) == 1 else "mixed"
    run_script(args, output, "collect-results.sbatch", [output, backend, plan])
    path = output / "workflow-results.json"
    aggregate = json.loads(path.read_text())
    if aggregate["cases"] != results or aggregate["backend"] != backend:
        raise ValueError("Collected results do not match fragment outputs")
    aggregate.update(case=prepared["case_name"], execution_check_only=True,
                     backend_counts=dict(Counter(item["backend"] for item in results.values())),
                     result_kind="synthetic" if "fake-iqm" in providers else "hardware" if "iqm" in providers else "simulation")
    write_json(path, aggregate)


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="stage", required=True)
    for name in ("prepare", "chemistry", "collect"):
        command = commands.add_parser(name)
        if name == "prepare":
            command.add_argument("--case-name", required=True)
            command.add_argument("--gamess-input", type=Path, required=True)
            command.add_argument("--fcidump", type=Path, required=True)
            command.add_argument("--fragments", type=Path, nargs="+", required=True)
        else:
            command.add_argument("--application", dest="chemistry_source", type=Path, required=True)
        if name == "chemistry":
            command.add_argument("--fragment", type=Path, required=True)
            command.add_argument("--backend", required=True)
            command.add_argument("--qpu", required=True)
            command.add_argument("--shots", type=positive, required=True)
            command.add_argument("--result-kind", choices=("simulation", "synthetic", "hardware"), required=True)
            for kind in ("macro", "amplitude", "orbital"):
                command.add_argument(f"--max-{kind}-iterations", type=positive, required=True)
        if name == "collect":
            command.add_argument("--prepared", type=Path, required=True)
            command.add_argument("--calculations", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    {"prepare": prepare, "chemistry": chemistry, "collect": collect}[args.stage](args)


if __name__ == "__main__":
    main()
