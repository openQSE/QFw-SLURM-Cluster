"""Dashboard capabilities independent of browser rendering."""

from __future__ import annotations

import json
import base64
import hashlib
import io
import os
import re
import signal
import shlex
import subprocess
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backends import BACKENDS, backend_payload, backend_spec
from .collectors import (
    diagnostics,
    inventory_status,
    LiveCollectorSet,
    reconcile_qpm_registration,
    service_health_summary,
)
from .models import Experiment, Operation, aggregate_state, utc_now
from .logs import LogSource, SERVICE_DIAGNOSTICS, SOURCES, read_source
from .redaction import redact, redact_payload
from .runner import CommandRunner, IDENTITIES
from .store import DashboardStore


@dataclass(frozen=True)
class CommandSpec:
    argv: tuple[str, ...]
    container: str | None = None


@dataclass(frozen=True)
class OperationActionPlan:
    command: CommandSpec
    dry_run_commands: tuple[CommandSpec, ...] = ()


@dataclass(frozen=True)
class ExperimentSubmissionPlan:
    experiment_id: str
    identity: str
    backend: str
    example: str
    allocation_mode: str
    requirements: dict[str, Any]
    experiment_root: str
    output_path: str
    batch_path: str
    batch_script: str
    external_batch: bool
    submit_argv: tuple[str, ...]
    write_argv: tuple[str, ...] | None


class SubmissionSetValidationError(ValueError):
    """Identify the staged experiment that failed batch validation."""

    def __init__(self, index: int, experiment_id: str, message: str) -> None:
        super().__init__(message)
        self.index = index
        self.experiment_id = experiment_id


_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_SAFE_CONSTRAINT = re.compile(r"^[A-Za-z0-9_.+*|&!\[\]-]+$")
_MEMORY_SIZE = re.compile(r"^[1-9][0-9]*(?:[KMGTP])?$", re.IGNORECASE)
DEFW_OUT_LOG_LEVELS = {"error", "message", "debug", "all"}
DEFW_PY_LOG_LEVEL_TOKENS = {
    "critical",
    "error",
    "warning",
    "info",
    "debug",
    "DEFW_APP",
    "DEFW_SERVICE",
    "DEFW_RPC",
    "DEFW_WORKER",
    "DEFW_CORE",
    "DEFW_STACKTRACE",
    "DEFW_ALL",
}
APPLICATION_SUBMISSION_TYPES = {"executable", "sbatch"}
MAX_APPLICATION_ARGUMENTS_LENGTH = 8192
MAX_EDITED_BATCH_SCRIPT_BYTES = 262144
EXAMPLE_SCRIPTS = {
    "init-test": "qfw_init_test.sh",
    "qiskit-simple": "qfw_qiskit_simple.sh",
    "ghz-qiskit": "qfw_ghz.sh",
    "ghz-pennylane": "qfw_ghz.sh",
    "pennylane": "qfw_pennylane.sh",
    "qaoa": "qfw_qaoa.sh",
    "qiskit-vqe": "qfw_qiskit_vqe.sh",
    "supermarq": "qfw_supermarq.sh",
    "chemistry": "qfw_chem_app.sh",
}
EXAMPLE_PARAMETERS: dict[str, list[dict[str, Any]]] = {
    "qiskit-simple": [{
        "name": "qubits", "label": "Qubits", "type": "integer",
        "default": 4, "minimum": 1, "maximum": 10000,
        "help": "Number of qubits used by the circuit.",
    }],
    "ghz-qiskit": [
        {
            "name": "qubits", "label": "Qubits", "type": "integer",
            "default": 4, "minimum": 1, "maximum": 10000,
            "help": "Width of each GHZ circuit.",
        },
        {
            "name": "iterations", "label": "Iterations", "type": "integer",
            "default": 1, "minimum": 1, "maximum": 1000000,
            "help": "Number of GHZ executions.",
        },
    ],
    "ghz-pennylane": [
        {
            "name": "qubits", "label": "Qubits", "type": "integer",
            "default": 4, "minimum": 1, "maximum": 10000,
            "help": "Width of each GHZ circuit.",
        },
        {
            "name": "iterations", "label": "Iterations", "type": "integer",
            "default": 1, "minimum": 1, "maximum": 1000000,
            "help": "Number of GHZ executions.",
        },
    ],
    "qiskit-vqe": [{
        "name": "optimizer_iterations", "label": "Optimizer iterations",
        "type": "integer", "default": 1, "minimum": 1, "maximum": 1000000,
        "help": "Maximum number of VQE optimizer iterations.",
    }],
    "supermarq": [
        {
            "name": "starting_qubits", "label": "Starting qubits",
            "type": "integer", "default": 4, "minimum": 1, "maximum": 10000,
            "help": "Starting circuit width for the benchmark.",
        },
        {
            "name": "shots", "label": "Execution shots", "type": "integer",
            "default": 16, "minimum": 1, "maximum": 65536,
            "help": "Shots actually executed; this must not exceed Maximum shots.",
        },
    ],
}
EXAMPLES = set(EXAMPLE_SCRIPTS)
STATEVECTOR_EXAMPLES = {"qiskit-vqe"}


class DashboardService:
    HOST_ACTIONS = {
        "cluster-build": ("./do_build.sh",),
        "cluster-status": ("./do_ls.sh",),
        "cluster-synchronize": (
            "/bin/bash", "-lc",
            "git pull --ff-only && git submodule sync --recursive "
            "&& git submodule update --init --recursive",
        ),
        "cluster-start": ("./do_startup.sh",),
        "cluster-stop": ("./do_stop.sh",),
        "cluster-restart": ("./do_restart.sh",),
        "cluster-rebuild-incremental": (
            "/bin/bash", "-lc",
            "./do_build.sh && ./do_stop.sh && ./do_startup.sh",
        ),
        "cluster-rebuild-clean": (
            "/bin/bash", "-lc",
            "./do_build.sh --no-cache && ./do_stop.sh && ./do_startup.sh",
        ),
        "cluster-recreate": (
            "/bin/bash", "-lc",
            "./do_stop.sh delete && ./do_build.sh && ./do_startup.sh",
        ),
    }
    SERVICE_TARGETS = {
        "all", "directory", "gateway",
        *(spec.service_target for spec in BACKENDS.values()),
    }
    SERVICE_OPERATIONS = {"start", "stop", "restart", "recover", "status"}

    def __init__(self, cluster_root: Path, state_root: Path) -> None:
        self.cluster_root = cluster_root.resolve()
        self.runner = CommandRunner(self.cluster_root)
        self.live_collectors = LiveCollectorSet(self.runner)
        self.store = DashboardStore(state_root / "qfw-slurm-cluster")
        self._threads: dict[str, threading.Thread] = {}
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._cancelled: set[str] = set()
        self._operation_lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()
        self._state_lock = threading.Lock()
        self._state_cache: dict[str, Any] | None = None
        self._state_cached_at = 0.0
        self._examples_cache: list[dict[str, Any]] | None = None

    def state(self) -> dict[str, Any]:
        with self._state_lock:
            now = time.monotonic()
            if self._state_cache is not None and now - self._state_cached_at < 2:
                return self._state_cache
            self._refresh_experiments()
            payload = aggregate_state(reconcile_qpm_registration(
                self.live_collectors.snapshot()))
            payload["operations"] = self.store.operations()
            experiments = self.store.experiments()
            payload["experiments"] = experiments
            payload["running_experiments"] = self._running_experiments(
                experiments,
                payload.get("sources", {}).get("slurm", {}).get("records", []),
            )
            payload["identities"] = list(IDENTITIES)
            payload["backends"] = backend_payload()
            payload["examples"] = self.examples()
            self._state_cache = payload
            self._state_cached_at = time.monotonic()
            return payload

    def _running_experiments(
        self,
        experiments: list[dict[str, Any]],
        slurm_records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        live_job_ids = {
            str(record.get("job_id", "")).split("+")[0]
            for record in slurm_records
            if record.get("kind") == "job" and record.get("job_id")
        }
        live_submissions = {
            experiment_id
            for experiment_id, thread in self._threads.items()
            if getattr(thread, "is_alive", lambda: False)()
        }
        return [
            experiment for experiment in experiments
            if (
                str(experiment.get("experiment_id", "")) in live_submissions
                or (
                    bool(experiment.get("slurm_job_id"))
                    and str(experiment["slurm_job_id"]).split("+")[0]
                    in live_job_ids
                )
            )
        ]

    def examples(self) -> list[dict[str, Any]]:
        if self._examples_cache is not None:
            return self._examples_cache
        self._examples_cache = [
            {
                "name": name,
                "script": script,
                "backends": ["nwqsim"] if name in STATEVECTOR_EXAMPLES
                else [spec.name for spec in BACKENDS.values()],
                "hardware_risk": name != "init-test",
                "parameters": EXAMPLE_PARAMETERS.get(name, []),
            }
            for name, script in EXAMPLE_SCRIPTS.items()
        ]
        return self._examples_cache

    def _refresh_experiments(self) -> None:
        terminal = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL"}
        for stored in self.store.experiments():
            if stored.get("completed_at") or not stored.get("slurm_job_id"):
                continue
            fields = {
                key: value for key, value in stored.items()
                if key in Experiment.__dataclass_fields__
            }
            experiment = Experiment(**fields)
            previous_status = experiment.status
            status = self.runner.cluster(
                experiment.identity,
                (
                    "sacct", "--noheader", "--parsable2",
                    "--jobs", experiment.slurm_job_id,
                    "--format=JobIDRaw,State,ExitCode,NodeList",
                ),
            )
            if status.returncode:
                continue
            first = next((line for line in status.stdout.splitlines() if line), "")
            values = first.split("|")
            slurm_records = []
            for line in status.stdout.splitlines():
                item = line.split("|")
                if not item or not item[0]:
                    continue
                item += [""] * (4 - len(item))
                slurm_records.append({
                    "job_id": item[0], "state": item[1].split()[0],
                    "exit_code": item[2], "nodes": item[3],
                    "kind": "step" if "." in item[0] else "job",
                })
            slurm_state = values[1].split()[0].upper() if len(values) > 1 else ""
            if slurm_state and slurm_state not in terminal:
                experiment.status = slurm_state.lower()
                output_path = str(experiment.manifest.get("output_path", ""))
                if output_path:
                    output = self.runner.cluster(
                        experiment.identity, ("tail", "-n", "1000", output_path)
                    )
                    if output.returncode == 0:
                        experiment.result = {
                            **experiment.result,
                            "output_tail": output.stdout[-64000:],
                        }
                if experiment.status != previous_status:
                    experiment.timeline.append({
                        "timestamp": utc_now(), "phase": experiment.status,
                        "component": "slurm", "job_id": experiment.slurm_job_id,
                    })
                self.store.save_experiment(experiment)
                if experiment.status != previous_status:
                    self.store.append_event({
                        "kind": "progress", "component": "slurm",
                        "identity": experiment.identity,
                        "experiment_id": experiment.experiment_id,
                        "job_id": experiment.slurm_job_id,
                        "severity": "info", "message": experiment.status,
                    })
                continue
            if slurm_state in terminal:
                artifact = experiment.artifacts[0] if experiment.artifacts else ""
                output = self.runner.cluster(
                    experiment.identity,
                    ("tail", "-n", "1000", artifact),
                ) if artifact else None
                output_text = output.stdout if output else ""
                records: list[dict[str, Any]] = []
                match = re.search(
                    r"^Summary JSONL: (.+)$", output_text, re.MULTILINE
                )
                if match:
                    summary_path = match.group(1).strip()
                    summary = self.runner.cluster(
                        experiment.identity, ("cat", summary_path)
                    )
                    if summary.returncode == 0:
                        for line in summary.stdout.splitlines():
                            try:
                                record = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if isinstance(record, dict):
                                records.append(record)
                        experiment.artifacts.append(summary_path)
                for log_path in re.findall(r"\blog=([^\s]+)", output_text):
                    if log_path in experiment.artifacts:
                        continue
                    case_log = self.runner.cluster(
                        experiment.identity, ("tail", "-c", "262144", log_path)
                    )
                    if case_log.returncode != 0:
                        continue
                    experiment.artifacts.append(log_path)
                    driver_records = self._tagged_json(
                        case_log.stdout, "QFW_SLURM_DRIVER_RESULT"
                    )
                    records.extend(driver_records)
                    for record in driver_records:
                        reservation_value = record.get("reservation_id")
                        service_value = record.get("backend")
                        if reservation_value is not None and service_value:
                            reservation = str(reservation_value)
                            service = str(service_value)
                            pair = [service, reservation]
                            if pair not in experiment.reservations:
                                experiment.reservations.append(pair)
                    if not experiment.reservations:
                        reservation_match = re.search(
                            r"\breservation_id\s*[=:]\s*([0-9]+)",
                            case_log.stdout,
                        )
                        if reservation_match:
                            experiment.reservations.append([
                                experiment.backend,
                                reservation_match.group(1),
                            ])
                self._collect_experiment_log_artifacts(experiment)
                terminal_success = any(
                    record.get("kind") == "wrapper"
                    and record.get("event") == "finish"
                    and record.get("status") in {"ok", "success"}
                    and record.get("rc") == 0
                    and record.get("teardown_rc", 0) == 0
                    for record in records
                )
                experiment.status = "succeeded" if (
                    slurm_state == "COMPLETED" and terminal_success
                ) else "failed"
                experiment.result = {
                    "slurm_state": slurm_state,
                    "terminal_result": terminal_success,
                    "failure_classification": self._failure_classification(
                        slurm_state, terminal_success, records
                    ),
                    "exit_code": values[2] if len(values) > 2 else "",
                    "records": records,
                    "slurm_records": slurm_records,
                    "output_tail": output_text[-8000:],
                }
                experiment.completed_at = utc_now()
                experiment.timeline.append({
                    "timestamp": experiment.completed_at,
                    "phase": experiment.status,
                    "component": "application",
                    "job_id": experiment.slurm_job_id,
                    "reservation_release": "terminal",
                })
                self.store.save_experiment(experiment)
                self.store.append_event({
                    "kind": "progress", "component": "application",
                    "identity": experiment.identity,
                    "experiment_id": experiment.experiment_id,
                    "job_id": experiment.slurm_job_id,
                    "severity": "info" if terminal_success else "error",
                    "message": (
                        f"{experiment.status}; Slurm cleanup and reservation "
                        "release reached terminal state"
                    ),
                })
                self.store.audit({
                    "identity": experiment.identity,
                    "host_identity": "electroboy-service",
                    "action": "experiment-complete",
                    "target": experiment.backend,
                    "request_id": experiment.experiment_id,
                    "job_id": experiment.slurm_job_id,
                    "completed_at": experiment.completed_at,
                    "outcome": experiment.status,
                })

    @staticmethod
    def _failure_classification(
        slurm_state: str,
        terminal_success: bool,
        records: list[dict[str, Any]],
    ) -> str:
        if terminal_success:
            return "none"
        if slurm_state == "CANCELLED":
            return "cancellation"
        if slurm_state == "TIMEOUT":
            return "timeout"
        text = json.dumps(records).lower()
        if any(value in text for value in ("provider", "iqm error", "job failed")):
            return "provider"
        if slurm_state != "COMPLETED":
            return "slurm"
        if not records:
            return "incomplete"
        return "application"

    @staticmethod
    def _tagged_json(text: str, tag: str) -> list[dict[str, Any]]:
        decoder = json.JSONDecoder()
        records: list[dict[str, Any]] = []
        offset = 0
        while True:
            position = text.find(tag, offset)
            if position < 0:
                return records
            start = text.find("{", position + len(tag))
            if start < 0:
                return records
            try:
                value, length = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                offset = start + 1
                continue
            if isinstance(value, dict):
                records.append(value)
            offset = start + length

    def diagnostic_state(self) -> dict[str, Any]:
        return {"schema": "qfw-dashboard-v1", **diagnostics(self.runner).payload()}

    def clear_dashboard_state(self, identity: str) -> dict[str, Any]:
        """Clear Dashboard-owned state after proving no tracked work is active."""
        if identity != "root":
            raise PermissionError("clearing Dashboard state requires root selection")

        with self._lifecycle_lock:
            active_threads = sorted(
                identifier for identifier, thread in self._threads.items()
                if getattr(thread, "is_alive", lambda: False)()
            )
            with self._operation_lock:
                active_processes = sorted(
                    identifier for identifier, process in self._processes.items()
                    if process.poll() is None
                )
            if active_threads or active_processes:
                identifiers = sorted(set(active_threads + active_processes))
                raise RuntimeError(
                    "cannot clear Dashboard state while managed work is active: "
                    + ", ".join(identifiers)
                )

            tracked_job_ids = {
                str(item.get("slurm_job_id", "")).split(";", 1)[0].split("+", 1)[0]
                for item in self.store.experiments()
                if item.get("slurm_job_id")
            }
            if tracked_job_ids:
                result = self.runner.cluster(
                    "root", ("squeue", "--noheader", "--format=%A")
                )
                if result.returncode:
                    detail = result.stderr.strip() or result.stdout.strip()
                    raise RuntimeError(
                        "cannot verify whether tracked Slurm jobs are active"
                        + (f": {detail}" if detail else "")
                    )
                active_job_ids = {
                    line.strip().split("+", 1)[0]
                    for line in result.stdout.splitlines()
                    if line.strip()
                }
                active = sorted(tracked_job_ids & active_job_ids)
                if active:
                    raise RuntimeError(
                        "cannot clear Dashboard state while tracked Slurm jobs "
                        "are active: " + ", ".join(active)
                    )

            cleared = self.store.clear_dashboard_state()
            self._threads.clear()
            self._cancelled.clear()
            with self._state_lock:
                self._state_cache = None
                self._state_cached_at = 0.0
            self._examples_cache = None
        return {
            "schema": "qfw-dashboard-reset-v1",
            "outcome": "success",
            "timestamp": utc_now(),
            "cleared": cleared,
        }

    def clear_experiment_results(self, identity: str) -> dict[str, Any]:
        """Remove historical experiment records while preserving active work."""
        if identity not in IDENTITIES:
            raise ValueError("unsupported identity")

        with self._lifecycle_lock:
            experiments = self.store.experiments()
            active_threads = {
                identifier for identifier, thread in self._threads.items()
                if getattr(thread, "is_alive", lambda: False)()
            }
            tracked_job_ids = {
                str(item.get("slurm_job_id", "")).split(";", 1)[0].split("+", 1)[0]
                for item in experiments
                if item.get("slurm_job_id")
            }
            active_job_ids: set[str] = set()
            if tracked_job_ids:
                result = self.runner.cluster(
                    "root", ("squeue", "--noheader", "--format=%A")
                )
                if result.returncode:
                    detail = result.stderr.strip() or result.stdout.strip()
                    raise RuntimeError(
                        "cannot verify whether tracked Slurm jobs are active"
                        + (f": {detail}" if detail else "")
                    )
                active_job_ids = {
                    line.strip().split("+", 1)[0]
                    for line in result.stdout.splitlines()
                    if line.strip()
                }
            active_experiments = {
                str(item.get("experiment_id", ""))
                for item in experiments
                if (
                    str(item.get("experiment_id", "")) in active_threads
                    or (
                        bool(item.get("slurm_job_id"))
                        and str(item["slurm_job_id"]).split(";", 1)[0]
                        .split("+", 1)[0] in active_job_ids
                    )
                )
            }
            removable = {
                str(item.get("experiment_id", ""))
                for item in experiments
                if (
                    item.get("experiment_id")
                    and str(item.get("experiment_id", "")) not in active_experiments
                    and (
                        identity == "root"
                        or str(item.get("identity", "")) == identity
                    )
                )
            }
            removed = self.store.delete_experiments(removable)
            with self._state_lock:
                self._state_cache = None
                self._state_cached_at = 0.0
        self.store.audit({
            "identity": identity,
            "host_identity": "electroboy-service",
            "action": "experiment-results-clear",
            "target": "experiments",
            "outcome": "success",
            "cleared": removed,
        })
        return {
            "schema": "qfw-dashboard-experiment-results-clear-v1",
            "outcome": "success",
            "timestamp": utc_now(),
            "cleared": {"experiments": removed},
        }

    def submit_action(
        self,
        action: str,
        identity: str,
        target: str = "cluster",
        request_id: str = "",
        reason: str = "qfw-dashboard",
        options: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> Operation:
        plan = self._operation_action_plan(
            action, identity, target, reason, options or {}
        )
        if request_id:
            for existing in self.store.operations():
                if existing.get("request_id") == request_id:
                    return Operation(**{
                        key: value for key, value in existing.items()
                        if key in Operation.__dataclass_fields__
                    })
        operation = Operation(
            operation_id=str(uuid.uuid4()),
            action=action,
            identity=identity,
            target=target,
            request_id=request_id,
        )
        if dry_run:
            self._complete_dry_run_operation(operation, plan)
            return operation
        with self._lifecycle_lock:
            self.store.save_operation(operation)
            thread = threading.Thread(
                target=self._run_operation,
                args=(operation, plan.command),
                daemon=True,
                name=f"qfw-dashboard-{operation.operation_id}",
            )
            self._threads[operation.operation_id] = thread
            thread.start()
        return operation

    def _operation_action_plan(
        self,
        action: str,
        identity: str,
        target: str,
        reason: str,
        options: dict[str, Any],
    ) -> OperationActionPlan:
        if identity not in IDENTITIES:
            raise ValueError("unsupported identity")
        if action in self.HOST_ACTIONS:
            if identity != "root":
                raise PermissionError("host cluster actions require root selection")
            argv = self.HOST_ACTIONS[action]
            return OperationActionPlan(
                CommandSpec(argv),
                self._host_dry_run_commands(action),
            )
        elif action.startswith("service-"):
            if identity != "root":
                raise PermissionError("service actions require root selection")
            service_operation = action.removeprefix("service-")
            if service_operation not in self.SERVICE_OPERATIONS:
                raise ValueError(f"unsupported service operation: {service_operation}")
            if target not in self.SERVICE_TARGETS:
                raise ValueError(f"unsupported service target: {target}")
            command = (
                "qfw-site-services", service_operation, "--target", target,
            )
            dry_run_command = (
                "qfw-site-services", "--dry-run", service_operation,
                "--target", target,
            )
            if service_operation in {"start", "restart", "recover"}:
                log_env = self._service_log_environment(options)
                argv = (
                    (
                        "/usr/bin/env",
                        *(f"{name}={value}" for name, value in log_env.items()),
                        *command,
                    )
                    if log_env else command
                )
                dry_run_argv = (
                    (
                        "/usr/bin/env",
                        *(f"{name}={value}" for name, value in log_env.items()),
                        *dry_run_command,
                    )
                    if log_env else dry_run_command
                )
            else:
                argv = command
                dry_run_argv = dry_run_command
            return OperationActionPlan(
                CommandSpec(argv, "slurmctld"),
                (CommandSpec(dry_run_argv, "slurmctld"),),
            )
        elif action in {"node-drain", "node-resume"}:
            if identity != "root" or not _SAFE_NAME.fullmatch(target):
                raise PermissionError("valid node and root selection required")
            if len(reason) > 200 or any(character in reason for character in "\r\n"):
                raise ValueError("invalid node reason")
            argv = (
                "scontrol",
                "update",
                f"NodeName={target}",
                "State=DRAIN" if action == "node-drain" else "State=RESUME",
                f"Reason={reason}" if action == "node-drain" else "",
            )
            argv = tuple(item for item in argv if item)
            return OperationActionPlan(CommandSpec(argv, "slurmctld"))
        else:
            raise ValueError(f"unsupported action: {action}")

    def _host_dry_run_commands(self, action: str) -> tuple[CommandSpec, ...]:
        commands = {
            "cluster-build": (("./do_build.sh", "--dry-run"),),
            "cluster-status": (("./do_ls.sh", "--dry-run"),),
            "cluster-start": (("./do_startup.sh", "--dry-run"),),
            "cluster-stop": (("./do_stop.sh", "--dry-run"),),
            "cluster-restart": (("./do_restart.sh", "--dry-run"),),
            "cluster-rebuild-incremental": (
                ("./do_build.sh", "--dry-run"),
                ("./do_stop.sh", "--dry-run"),
                ("./do_startup.sh", "--dry-run"),
            ),
            "cluster-rebuild-clean": (
                ("./do_build.sh", "--dry-run", "--no-cache"),
                ("./do_stop.sh", "--dry-run"),
                ("./do_startup.sh", "--dry-run"),
            ),
        }
        return tuple(CommandSpec(command) for command in commands.get(action, ()))

    def _render_command(self, identity: str, command: CommandSpec) -> str:
        if command.container is None:
            return shlex.join(command.argv)
        return shlex.join(self.runner.cluster_argv(
            identity,
            command.argv,
            container=command.container,
        ))

    def _complete_dry_run_operation(
        self, operation: Operation, plan: OperationActionPlan
    ) -> None:
        operation.started_at = utc_now()
        operation.completed_at = operation.started_at
        operation.status = "succeeded"
        operation.return_code = 0
        operation.dry_run = True
        output = [
            "DRY RUN - command was not executed",
            "Would run from the Docker host:",
            f"  {self._render_command(operation.identity, plan.command)}",
        ]
        if plan.dry_run_commands:
            output.extend(["", "Available dry-run helper command(s):"])
            output.extend(
                f"  {self._render_command(operation.identity, command)}"
                for command in plan.dry_run_commands
            )
        operation.output = output
        with self._lifecycle_lock:
            self.store.save_operation(operation)
            self.store.audit({
                "identity": operation.identity,
                "host_identity": "electroboy-service",
                "action": operation.action,
                "target": operation.target,
                "request_id": operation.request_id,
                "operation_id": operation.operation_id,
                "started_at": operation.started_at,
                "outcome": "dry-run",
            })

    def _run_operation(
        self, operation: Operation, command_spec: CommandSpec
    ) -> None:
        operation.status = "running"
        operation.started_at = utc_now()
        self.store.save_operation(operation)
        self.store.audit({
            "identity": operation.identity,
            "host_identity": "electroboy-service",
            "action": operation.action,
            "target": operation.target,
            "request_id": operation.request_id,
            "operation_id": operation.operation_id,
            "started_at": operation.started_at,
            "outcome": "started",
        })
        try:
            command = (
                command_spec.argv if command_spec.container is None
                else self.runner.cluster_argv(
                    operation.identity,
                    command_spec.argv,
                    container=command_spec.container,
                )
            )
            def on_start(process: subprocess.Popen[str]) -> None:
                with self._operation_lock:
                    self._processes[operation.operation_id] = process
                    cancelled = operation.operation_id in self._cancelled
                if cancelled:
                    self._terminate_process(process)

            def on_line(line: str) -> None:
                operation.output.append(line)
                self.store.save_operation(operation)
                self.store.append_event({
                    "kind": "log",
                    "component": operation.action,
                    "instance": operation.target,
                    "identity": operation.identity,
                    "severity": "info",
                    "operation_id": operation.operation_id,
                    "message": line,
                })
            result = self.runner.stream_host(command, on_line, on_start=on_start)
            operation.return_code = result.returncode
            with self._operation_lock:
                cancelled = operation.operation_id in self._cancelled
            operation.status = (
                "aborted" if cancelled else
                "succeeded" if result.returncode == 0 else "failed"
            )
            if operation.action == "service-status" and \
                    result.returncode == 0 and not cancelled:
                operation.output = service_health_summary(
                    self.runner, operation.target)
                operation.return_code = 0
                operation.status = "succeeded"
        except Exception as error:
            operation.output = [str(error)]
            operation.return_code = 1
            with self._operation_lock:
                cancelled = operation.operation_id in self._cancelled
            operation.status = "aborted" if cancelled else "failed"
        finally:
            with self._operation_lock:
                self._processes.pop(operation.operation_id, None)
                self._cancelled.discard(operation.operation_id)
        operation.completed_at = utc_now()
        self.store.save_operation(operation)
        if operation.return_code:
            self.store.append_event({
                "kind": "progress",
                "component": operation.action,
                "instance": operation.target,
                "identity": operation.identity,
                "severity": "error",
                "operation_id": operation.operation_id,
                "message": f"command exited with {operation.return_code}",
            })
        self.store.audit({
            "identity": operation.identity,
            "host_identity": "electroboy-service",
            "action": operation.action,
            "target": operation.target,
            "request_id": operation.request_id,
            "operation_id": operation.operation_id,
            "started_at": operation.started_at,
            "completed_at": operation.completed_at,
            "outcome": operation.status,
        })

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            return

    def abort_operation(self, operation_id: str, identity: str) -> Operation:
        if identity != "root":
            raise PermissionError("operation abort requires root selection")
        stored = next((
            item for item in self.store.operations()
            if item.get("operation_id") == operation_id
        ), None)
        if stored is None:
            raise KeyError(f"unknown operation: {operation_id}")
        operation = Operation(**{
            key: value for key, value in stored.items()
            if key in Operation.__dataclass_fields__
        })
        if operation.status not in {"queued", "running", "aborting"}:
            raise RuntimeError(f"operation is already {operation.status}")
        operation.status = "aborting"
        operation.output.append("Abort requested by root")
        self.store.save_operation(operation)
        with self._operation_lock:
            self._cancelled.add(operation_id)
            process = self._processes.get(operation_id)
        if process is not None:
            self._terminate_process(process)
        self.store.audit({
            "identity": identity,
            "host_identity": "electroboy-service",
            "action": "operation-abort",
            "target": operation.target,
            "operation_id": operation_id,
            "outcome": "requested",
        })
        return operation

    def submit_experiment(self, request: dict[str, Any]) -> Experiment:
        identity, backend, example, mode, requirements = (
            self._validated_experiment_request(
                request, default_identity="", require_hardware_confirmation=True
            )
        )
        backend_config = backend_spec(backend)
        experiment_id = self._experiment_id(request)
        if any(
            item.get("experiment_id") == experiment_id
            for item in self.store.experiments()
        ):
            raise ValueError(f"experiment already exists: {experiment_id}")
        experiment = Experiment(
            experiment_id=experiment_id,
            identity=identity,
            backend=backend,
            example=example,
            allocation_mode=mode,
            manifest={
                "schema": "qfw-experiment-manifest-v1",
                "identity": identity,
                "backend": backend,
                "example": example,
                "allocation_mode": mode,
                "requirements": requirements,
                "submission_entry_id": str(
                    request.get("submission_entry_id", "")
                ).strip(),
                "retry_of": str(request.get("retry_of", "")),
                "cluster_revision": self._revision(self.cluster_root),
                "electroboy_revision": self._revision(
                    self.cluster_root / "dashboard/external/electroboy"
                ),
                "backend_configuration": {
                    "service_id": backend_config.service_id,
                    "provider": backend_config.provider,
                    "qpu": backend_config.qpu,
                    "site_config": "/etc/openqse/qfw/site.yaml",
                },
                "deployment_inventory": inventory_status(self.runner).records,
            },
            timeline=[{
                "timestamp": utc_now(), "phase": "created",
                "component": "dashboard",
            }],
        )
        with self._lifecycle_lock:
            self.store.save_experiment(experiment)
            self.store.audit({
                "identity": identity,
                "host_identity": "electroboy-service",
                "action": "experiment-submit",
                "target": backend,
                "request_id": experiment.experiment_id,
                "hardware": backend_config.requires_hardware_confirmation,
                "outcome": "accepted",
            })
            thread = threading.Thread(
                target=self._run_experiment,
                args=(experiment, requirements),
                daemon=True,
                name=f"qfw-experiment-{experiment.experiment_id}",
            )
            self._threads[experiment.experiment_id] = thread
            thread.start()
        return experiment

    def _prepared_experiment_batch(
        self,
        request: dict[str, Any],
        *,
        require_hardware_confirmation: bool,
    ) -> tuple[
        str,
        list[tuple[dict[str, Any], tuple[str, str, str, str, dict[str, Any]]]],
    ]:
        identity = str(request.get("identity", ""))
        submissions = request.get("experiments")
        if identity not in IDENTITIES:
            raise ValueError("unsupported identity")
        if not isinstance(submissions, list) or not submissions:
            raise ValueError("submission set must contain at least one experiment")
        if len(submissions) > 64:
            raise ValueError("submission set cannot exceed 64 experiments")

        hardware_confirmed = request.get("submit_real_hardware") is True
        prepared: list[
            tuple[dict[str, Any], tuple[str, str, str, str, dict[str, Any]]]
        ] = []
        experiment_ids: set[str] = set()
        for index, submission in enumerate(submissions):
            if not isinstance(submission, dict):
                raise SubmissionSetValidationError(
                    index, "", "submission set entry must be an object"
                )
            candidate = {
                **submission,
                "identity": identity,
                "submit_real_hardware": hardware_confirmed,
            }
            supplied_id = str(candidate.get("experiment_id", "")).strip()
            try:
                experiment_id = self._experiment_id(candidate)
                validated = self._validated_experiment_request(
                    candidate,
                    default_identity="",
                    require_hardware_confirmation=require_hardware_confirmation,
                )
            except (PermissionError, TypeError, ValueError) as error:
                raise SubmissionSetValidationError(
                    index, supplied_id, str(error)
                ) from error
            if experiment_id in experiment_ids:
                raise SubmissionSetValidationError(
                    index,
                    experiment_id,
                    f"duplicate experiment in submission set: {experiment_id}",
                )
            experiment_ids.add(experiment_id)
            prepared.append(({**candidate, "experiment_id": experiment_id}, validated))
        return identity, prepared

    def submit_experiment_batch(
        self, request: dict[str, Any]
    ) -> list[Experiment]:
        _identity, prepared = self._prepared_experiment_batch(
            request, require_hardware_confirmation=True
        )
        prepared_requests = [item for item, _validated in prepared]
        experiment_ids = {
            str(item["experiment_id"]) for item in prepared_requests
        }

        with self._lifecycle_lock:
            existing_ids = {
                str(item.get("experiment_id", ""))
                for item in self.store.experiments()
            }
            duplicate = sorted(experiment_ids & existing_ids)
            if duplicate:
                experiment_id = duplicate[0]
                index = next(
                    index for index, item in enumerate(prepared_requests)
                    if item["experiment_id"] == experiment_id
                )
                raise SubmissionSetValidationError(
                    index,
                    experiment_id,
                    f"experiment already exists: {experiment_id}",
                )
            return [self.submit_experiment(item) for item in prepared_requests]

    def dry_run_experiment_batch(self, request: dict[str, Any]) -> dict[str, Any]:
        _identity, prepared = self._prepared_experiment_batch(
            request, require_hardware_confirmation=False
        )
        experiments: list[dict[str, Any]] = []
        for candidate, validated in prepared:
            identity, backend, example, mode, requirements = validated
            experiment = Experiment(
                str(candidate["experiment_id"]),
                identity,
                backend,
                example,
                mode,
            )
            plan = self._experiment_submission_plan(experiment, requirements)
            experiments.append(self._submission_dry_run_payload(plan))
        return {
            "schema": "qfw-dashboard-submission-dry-run-v1",
            "outcome": "dry-run",
            "experiments": experiments,
        }

    def _validated_experiment_request(
        self,
        request: dict[str, Any],
        *,
        default_identity: str,
        require_hardware_confirmation: bool,
    ) -> tuple[str, str, str, str, dict[str, Any]]:
        identity = str(request.get("identity", default_identity))
        backend = str(request.get("backend", ""))
        if backend not in BACKENDS:
            raise ValueError(
                "backend must be one of "
                + ", ".join(sorted(BACKENDS))
            )
        backend_config = backend_spec(backend)
        application_source, example, application_path, submission_type = (
            self._application(request)
        )
        application_parameters = self._application_parameters(
            request, application_source, example
        )
        application_arguments = self._application_arguments(
            request, application_source, submission_type
        )
        batch_script = self._request_batch_script(
            request, application_source, submission_type
        )
        mode = str(request.get("allocation_mode", "normal"))
        if identity not in IDENTITIES:
            raise ValueError("unsupported identity")
        if mode not in {"normal", "heterogeneous"}:
            raise ValueError("invalid allocation mode")
        partition = self._optional_name(request, "partition", "normal")
        if partition == "heterogeneous":
            raise ValueError(
                "heterogeneous is an allocation mode, not a Slurm partition; "
                "use the normal partition"
            )
        if partition == "qfw-services":
            raise ValueError("qfw-services is reserved for site-owned services")
        if (
            require_hardware_confirmation
            and backend_config.requires_hardware_confirmation
            and request.get("submit_real_hardware") is not True
        ):
            raise PermissionError(
                f"{backend_config.label} submission requires explicit confirmation"
            )
        shots = int(request.get("shots", 16))
        if shots < 1 or shots > backend_config.max_shots:
            raise ValueError("shots outside permitted range")
        nodes = int(request.get("nodes", 1))
        if nodes < 1 or nodes > 8:
            raise ValueError("nodes outside permitted range")
        classical = self._classical_requirements(request, nodes)
        service_nodes = self._bounded(request, "service_nodes", 1, 1, 8)
        service_tasks = self._bounded(
            request, "service_tasks", service_nodes, 1, 128
        )
        time_minutes = int(request.get(
            "time_minutes",
            min(45, backend_config.max_time_minutes),
        ))
        if time_minutes < 1 or time_minutes > backend_config.max_time_minutes:
            raise ValueError("time_minutes outside permitted range")
        requirements = {
            "circ_count": self._bounded(request, "circ_count", 1, 1, 1000000),
            "max_qubits": self._bounded(request, "max_qubits", 5, 1, 10000),
            "max_depth": self._bounded(request, "max_depth", 100, 1, 10000000),
            "max_one_q_gates": self._bounded(
                request, "max_one_q_gates", 0, 0, 100000000
            ),
            "max_two_q_gates": self._bounded(
                request, "max_two_q_gates", 0, 0, 100000000
            ),
            "max_measurements": self._bounded(
                request, "max_measurements", 0, 0, 100000000
            ),
            "workload_kind": str(request.get("workload_kind", "quantum")),
            "shots": shots,
            "nodes": nodes,
            **classical,
            "service_nodes": service_nodes,
            "service_tasks": service_tasks,
            "partition": partition,
            "account": self._optional_name(request, "account"),
            "qos": self._optional_name(request, "qos"),
            "time_minutes": time_minutes,
            "defw_log_level": self._defw_log_level(
                request.get("defw_log_level", "error")
            ),
            "defw_py_loglevel": self._defw_py_loglevel(
                request.get("defw_py_loglevel", "critical")
            ),
            "application_source": application_source,
            "application_path": application_path,
            "application_submission_type": submission_type,
            "application_arguments": application_arguments,
            "application_parameters": application_parameters,
            "batch_script": batch_script,
            "backend_configuration": backend_config.as_dict(),
        }
        self._validate_application_capacity(example, requirements)
        if requirements["workload_kind"] not in {"quantum", "hybrid"}:
            raise ValueError("workload_kind must be quantum or hybrid")
        return identity, backend, example, mode, requirements

    def _revision(self, path: Path) -> str:
        result = self.runner.host(("git", "-C", str(path), "rev-parse", "HEAD"))
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    @staticmethod
    def _bounded(
        request: dict[str, Any], name: str, default: int, minimum: int, maximum: int
    ) -> int:
        value = int(request.get(name, default))
        if value < minimum or value > maximum:
            raise ValueError(f"{name} outside permitted range")
        return value

    @staticmethod
    def _optional_name(
        request: dict[str, Any], name: str, default: str = ""
    ) -> str:
        value = str(request.get(name, default)).strip()
        if not value:
            value = default
        if value and not _SAFE_NAME.fullmatch(value):
            raise ValueError(f"invalid {name}")
        return value

    @staticmethod
    def _defw_log_level(value: Any) -> str:
        level = str(value).strip()
        if level not in DEFW_OUT_LOG_LEVELS:
            raise ValueError("invalid defw_out.log level")
        return level

    @staticmethod
    def _defw_py_loglevel(value: Any) -> str:
        level = str(value).strip()
        if level not in DEFW_PY_LOG_LEVEL_TOKENS:
            raise ValueError("invalid defw_py.log level")
        return level

    def _service_log_environment(self, options: dict[str, Any]) -> dict[str, str]:
        environment: dict[str, str] = {}
        if "defw_log_level" in options:
            environment["QFW_SERVICE_DEFW_LOG_LEVEL"] = self._defw_log_level(
                options["defw_log_level"]
            )
        if "defw_py_loglevel" in options:
            environment["QFW_SERVICE_DEFW_PY_LOGLEVEL"] = self._defw_py_loglevel(
                options["defw_py_loglevel"]
            )
        return environment

    @staticmethod
    def _experiment_id(request: dict[str, Any]) -> str:
        supplied = str(request.get("experiment_id", "")).strip()
        if not supplied:
            return str(uuid.uuid4())
        try:
            parsed = uuid.UUID(supplied)
        except ValueError as error:
            raise ValueError("experiment_id must be a UUID") from error
        if str(parsed) != supplied.lower():
            raise ValueError("experiment_id must use canonical UUID syntax")
        return str(parsed)

    @staticmethod
    def _application(request: dict[str, Any]) -> tuple[str, str, str, str]:
        source = str(request.get("application_source", "example"))
        if source not in {"example", "path"}:
            raise ValueError("application_source must be example or path")
        example = str(request.get("example", "qiskit-simple"))
        path = str(request.get("application_path", "")).strip()
        submission_type = str(
            request.get("application_submission_type", "executable")
        )
        if submission_type not in APPLICATION_SUBMISSION_TYPES:
            raise ValueError("application_submission_type must be executable or sbatch")
        if path and (
            not path.startswith("/workspace/")
            or ".." in Path(path).parts
            or "\n" in path
            or "\x00" in path
        ):
            raise ValueError("application path must be an absolute /workspace path")
        if source == "path":
            if not path:
                raise ValueError("custom application path is required")
            return source, "custom", path, submission_type
        if example not in EXAMPLES:
            raise ValueError("unsupported QFw example")
        if example == "chemistry" and not path:
            raise ValueError("chemistry requires an absolute /workspace application path")
        return source, example, path, "executable"

    @staticmethod
    def _application_parameters(
        request: dict[str, Any], source: str, example: str
    ) -> dict[str, Any]:
        raw = request.get("application_parameters", {})
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ValueError("application_parameters must be an object")
        if source == "path":
            if raw:
                raise ValueError(
                    "custom application runtime parameters are not yet supported"
                )
            return {}
        definitions = EXAMPLE_PARAMETERS.get(example, [])
        known = {definition["name"] for definition in definitions}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(
                f"unsupported {example} runtime parameter: {sorted(unknown)[0]}"
            )
        parameters: dict[str, Any] = {}
        for definition in definitions:
            name = str(definition["name"])
            value = raw.get(name, definition["default"])
            if definition["type"] == "integer":
                try:
                    value = int(value)
                except (TypeError, ValueError) as error:
                    raise ValueError(f"{name} must be an integer") from error
                minimum = int(definition["minimum"])
                maximum = int(definition["maximum"])
                if value < minimum or value > maximum:
                    raise ValueError(f"{name} outside permitted range")
            parameters[name] = value
        return parameters

    @staticmethod
    def _application_arguments(
        request: dict[str, Any], source: str, submission_type: str
    ) -> str:
        arguments = str(request.get("application_arguments", "")).strip()
        if not arguments:
            return ""
        if source != "path" or submission_type != "executable":
            raise ValueError(
                "application_arguments are only supported for executables"
            )
        if "\x00" in arguments or "\n" in arguments:
            raise ValueError("application_arguments must be a single line")
        if len(arguments) > MAX_APPLICATION_ARGUMENTS_LENGTH:
            raise ValueError("application_arguments are too long")
        try:
            shlex.split(arguments)
        except ValueError as error:
            raise ValueError("invalid application_arguments") from error
        return arguments

    @staticmethod
    def _request_batch_script(
        request: dict[str, Any], source: str, submission_type: str
    ) -> str:
        script = request.get("batch_script", "")
        if script is None:
            script = ""
        if not isinstance(script, str):
            raise ValueError("batch_script must be a string")
        if not script:
            return ""
        if source != "path" or submission_type != "executable":
            raise ValueError("batch_script is only supported for executables")
        if "\x00" in script:
            raise ValueError("batch_script must not contain NUL bytes")
        if len(script.encode("utf-8")) > MAX_EDITED_BATCH_SCRIPT_BYTES:
            raise ValueError("batch_script is too large")
        return script.replace("\r\n", "\n")

    @staticmethod
    def _validate_application_capacity(
        example: str, requirements: dict[str, Any]
    ) -> None:
        parameters = requirements["application_parameters"]
        qubits = parameters.get("qubits", parameters.get("starting_qubits"))
        if qubits is not None and qubits > requirements["max_qubits"]:
            raise ValueError("application qubits exceed Maximum qubits")
        if parameters.get("shots", 0) > requirements["shots"]:
            raise ValueError("application shots exceed Maximum shots")
        if example.startswith("ghz-") and (
            parameters.get("iterations", 1) > requirements["circ_count"]
        ):
            raise ValueError("application iterations exceed Circuit count")

    @staticmethod
    def _application_environment(
        example: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        environment: dict[str, str] = {}
        if example in {"qiskit-simple", "ghz-qiskit", "ghz-pennylane"}:
            environment["QFW_RUN_ALL_QUBITS"] = str(parameters["qubits"])
        elif example == "supermarq":
            environment["QFW_RUN_ALL_QUBITS"] = str(parameters["starting_qubits"])
            environment["QFW_RUN_ALL_SHOTS"] = str(parameters["shots"])
        if example in {"ghz-qiskit", "ghz-pennylane"}:
            environment["QFW_RUN_ALL_ITERS"] = str(parameters["iterations"])
        elif example == "qiskit-vqe":
            environment["QFW_RUN_ALL_VQE_ITERS"] = str(
                parameters["optimizer_iterations"]
            )
        return environment

    def _classical_requirements(
        self, request: dict[str, Any], nodes: int
    ) -> dict[str, Any]:
        requirements: dict[str, Any] = {
            "tasks": self._bounded(request, "tasks", nodes, 1, 128),
        }
        for name, maximum in (
            ("tasks_per_node", 128),
            ("cpus_per_task", 256),
            ("gpus", 64),
        ):
            if name in request and request[name] not in {None, ""}:
                requirements[name] = self._bounded(request, name, 1, 1, maximum)
        memory = str(request.get("memory", "")).strip()
        if memory:
            if not _MEMORY_SIZE.fullmatch(memory):
                raise ValueError("invalid memory size")
            memory_scope = str(request.get("memory_scope", "node"))
            if memory_scope not in {"node", "cpu"}:
                raise ValueError("memory_scope must be node or cpu")
            requirements["memory"] = memory.upper()
            requirements["memory_scope"] = memory_scope
        if "gpus" in requirements:
            gpu_scope = str(request.get("gpus_scope", "node"))
            if gpu_scope not in {"node", "task"}:
                raise ValueError("gpus_scope must be node or task")
            requirements["gpus_scope"] = gpu_scope
        constraint = str(request.get("constraint", "")).strip()
        if constraint:
            if len(constraint) > 128 or not _SAFE_CONSTRAINT.fullmatch(constraint):
                raise ValueError("invalid constraint")
            requirements["constraint"] = constraint
        if "exclusive" in request:
            if not isinstance(request["exclusive"], bool):
                raise ValueError("exclusive must be boolean")
            requirements["exclusive"] = request["exclusive"]
        return requirements

    @staticmethod
    def _classical_options(requirements: dict[str, Any]) -> list[str]:
        options: list[str] = []
        option_names = {
            "tasks_per_node": "ntasks-per-node",
            "cpus_per_task": "cpus-per-task",
        }
        for name, option in option_names.items():
            if name in requirements:
                options.append(f"--{option}={requirements[name]}")
        if "memory" in requirements:
            option = "mem" if requirements["memory_scope"] == "node" else "mem-per-cpu"
            options.append(f"--{option}={requirements['memory']}")
        if "gpus" in requirements:
            option = "gpus-per-node" if requirements["gpus_scope"] == "node" else "gpus-per-task"
            options.append(f"--{option}={requirements['gpus']}")
        if "constraint" in requirements:
            options.append(f"--constraint={requirements['constraint']}")
        if requirements.get("exclusive") is True:
            options.append("--exclusive")
        return options

    def _run_experiment(
        self, experiment: Experiment, requirements: dict[str, Any]
    ) -> None:
        experiment.status = "submitting"
        experiment.timeline.append({
            "timestamp": utc_now(), "phase": "submitting",
            "component": "slurm",
        })
        self.store.save_experiment(experiment)
        plan = self._experiment_submission_plan(experiment, requirements)
        experiment.manifest["command"] = shlex.join(plan.submit_argv)
        experiment.manifest["batch_script_path"] = plan.batch_path
        if plan.batch_script:
            experiment.manifest["batch_script_sha256"] = hashlib.sha256(
                plan.batch_script.encode("utf-8")
            ).hexdigest()
        experiment.manifest["output_path"] = plan.output_path
        experiment.manifest["submitted_at"] = utc_now()
        if plan.external_batch:
            result = self.runner.cluster(
                experiment.identity, plan.submit_argv, timeout=30
            )
            failure_classification = "submission"
        else:
            write_result = self._write_batch_script(
                experiment.identity, plan.batch_path, plan.batch_script
            )
            if write_result.returncode:
                result = write_result
                failure_classification = "batch-script"
            else:
                result = self.runner.cluster(
                    experiment.identity, plan.submit_argv, timeout=30
                )
                failure_classification = "submission"
        if result.returncode:
            experiment.status = "failed"
            experiment.result = {
                "failure_classification": failure_classification,
                "error": result.stderr or result.stdout,
            }
            experiment.completed_at = utc_now()
            experiment.timeline.append({
                "timestamp": experiment.completed_at, "phase": "failed",
                "component": "slurm", "classification": failure_classification,
            })
        else:
            experiment.slurm_job_id = result.stdout.strip().split(";")[0]
            experiment.status = "submitted"
            experiment.artifacts = (
                [plan.batch_path]
                if plan.external_batch else [plan.output_path, plan.batch_path]
            )
            experiment.timeline.append({
                "timestamp": utc_now(), "phase": "submitted",
                "component": "slurm", "job_id": experiment.slurm_job_id,
            })
        self.store.save_experiment(experiment)
        self.store.append_event({
            "kind": "progress",
            "component": "application",
            "identity": experiment.identity,
            "experiment_id": experiment.experiment_id,
            "job_id": experiment.slurm_job_id,
            "severity": "error" if result.returncode else "info",
            "message": experiment.status,
        })

    def _experiment_submission_plan(
        self, experiment: Experiment, requirements: dict[str, Any]
    ) -> ExperimentSubmissionPlan:
        experiment_root = (
            f"/workspace/home/{experiment.identity}/qfw-dashboard/experiments/"
            f"{experiment.experiment_id}"
        )
        output_path = f"{experiment_root}/job.out"
        external_batch = (
            requirements["application_source"] == "path"
            and requirements["application_submission_type"] == "sbatch"
        )
        batch_path = (
            str(requirements["application_path"])
            if external_batch else f"{experiment_root}/job.sbatch"
        )
        batch_script = ""
        if not external_batch:
            batch_script = (
                str(requirements.get("batch_script") or "")
                or self._batch_script(experiment, requirements, output_path)
            )
        submit_argv = ("sbatch", "--parsable", batch_path)
        write_argv = (
            None if external_batch
            else self._batch_script_write_argv(batch_path, batch_script)
        )
        return ExperimentSubmissionPlan(
            experiment_id=experiment.experiment_id,
            identity=experiment.identity,
            backend=experiment.backend,
            example=experiment.example,
            allocation_mode=experiment.allocation_mode,
            requirements=requirements,
            experiment_root=experiment_root,
            output_path=output_path,
            batch_path=batch_path,
            batch_script=batch_script,
            external_batch=external_batch,
            submit_argv=submit_argv,
            write_argv=write_argv,
        )

    def _submission_dry_run_payload(
        self, plan: ExperimentSubmissionPlan
    ) -> dict[str, Any]:
        write_command = ""
        write_host_command = ""
        if plan.write_argv is not None:
            write_command = shlex.join(plan.write_argv)
            write_host_command = shlex.join(self.runner.cluster_argv(
                plan.identity, plan.write_argv, timeout=15
            ))
        return {
            "schema": "qfw-dashboard-submission-dry-run-entry-v1",
            "outcome": "dry-run",
            "experiment_id": plan.experiment_id,
            "identity": plan.identity,
            "backend": plan.backend,
            "example": plan.example,
            "allocation_mode": plan.allocation_mode,
            "experiment_root": plan.experiment_root,
            "output_path": plan.output_path,
            "batch_script_path": plan.batch_path,
            "batch_script": plan.batch_script,
            "external_batch": plan.external_batch,
            "write_command": write_command,
            "write_host_command": write_host_command,
            "submit_command": shlex.join(plan.submit_argv),
            "submit_host_command": shlex.join(self.runner.cluster_argv(
                plan.identity, plan.submit_argv, timeout=30
            )),
        }

    def _batch_script(
        self,
        experiment: Experiment,
        requirements: dict[str, Any],
        output_path: str,
    ) -> str:
        backend_config = backend_spec(experiment.backend)
        quantum_fields = [
            f"--qpu={backend_config.qpu}",
            f"--workload-kind={requirements['workload_kind']}",
            f"--circ-count={requirements['circ_count']}",
            f"--max-qubits={requirements['max_qubits']}",
            f"--max-depth={requirements['max_depth']}",
            f"--max-shots={requirements['shots']}",
        ]
        for name in ("max_one_q_gates", "max_two_q_gates", "max_measurements"):
            if requirements[name]:
                quantum_fields.append(
                    f"--{name.replace('_', '-')}={requirements[name]}"
                )
        shared_allocation = [f"--partition={requirements['partition']}"]
        for name in ("account", "qos"):
            if requirements[name]:
                shared_allocation.append(f"--{name}={requirements[name]}")
        application_allocation = [
            *shared_allocation,
            f"--nodes={requirements['nodes']}",
            f"--ntasks={requirements['tasks']}",
            *self._classical_options(requirements),
        ]
        common_directives = [
            *quantum_fields,
            f"--job-name=qfw-{experiment.example}",
            f"--time={requirements['time_minutes']}",
            f"--output={output_path}",
        ]
        if experiment.allocation_mode == "normal":
            directive_groups = [[*common_directives, *application_allocation]]
        else:
            service_allocation = [
                *shared_allocation,
                f"--nodes={requirements['service_nodes']}",
                f"--ntasks={requirements['service_tasks']}",
            ]
            directive_groups = [
                [*common_directives, *application_allocation],
                [f"--time={requirements['time_minutes']}", *service_allocation],
            ]
        directives: list[str] = []
        for index, group in enumerate(directive_groups):
            if index:
                directives.append("#SBATCH hetjob")
            directives.extend(f"#SBATCH {option}" for option in group)

        body = [
            "",
            "set -euo pipefail",
            "export QFW_SHARED_ROOT=/workspace/qfw-container-base",
            'export QFW_RUN_BASE_DIR="${HOME}/qfw-runs"',
            f"export DEFW_LOG_LEVEL={shlex.quote(requirements['defw_log_level'])}",
            "export DEFW_PY_LOGLEVEL="
            f"{shlex.quote(requirements['defw_py_loglevel'])}",
            "export QFW_EXAMPLE_LOG_ARCHIVE_DIR="
            f"{shlex.quote(str(Path(output_path).parent / 'defw-logs'))}",
            'mkdir -p "${QFW_RUN_BASE_DIR}"',
            'mkdir -p "${QFW_EXAMPLE_LOG_ARCHIVE_DIR}"',
            "source /opt/openqse/qfw/bin/qfw-activate \\",
            "    --venv /opt/openqse/qfw-venv",
            "qfw_dashboard_deactivate() {",
            "    type qfw-deactivate >/dev/null 2>&1 && qfw-deactivate || true",
            "}",
            "trap qfw_dashboard_deactivate EXIT",
        ]
        if requirements["application_source"] == "path":
            application_path = str(requirements["application_path"])
            arguments = shlex.split(str(requirements["application_arguments"]))
            if application_path.endswith(".py"):
                application_command = shlex.join((
                    "python3", application_path, *arguments
                ))
            elif application_path.endswith(".sh"):
                application_command = shlex.join((
                    "bash", application_path, *arguments
                ))
            else:
                application_command = shlex.join((application_path, *arguments))
            body.extend((
                f"cd {shlex.quote(str(Path(application_path).parent))}",
                application_command,
            ))
        else:
            runtime_environment = self._application_environment(
                experiment.example, requirements["application_parameters"]
            )
            if experiment.example == "chemistry":
                chemistry_app = str(requirements["application_path"])
                runtime_environment.update({
                    "QFW_CHEM_APP_DIR": str(Path(chemistry_app).parent),
                    "QFW_RUN_ALL_CHEM_APP": chemistry_app,
                })
            body.extend((
                'cd "${QFW_SHARE_DIR}/examples"',
                shlex.join((
                    "env",
                    *(f"{name}={value}" for name, value in runtime_environment.items()),
                    f"QFW_RUN_ALL_TESTS={experiment.example}",
                    "./qfw_run_all.sh",
                    "--service-mode", "site",
                    "--backend", backend_config.provider,
                )),
            ))
        return "\n".join((
            "#!/usr/bin/env bash",
            *directives,
            *body,
            "",
        ))

    def _write_batch_script(
        self,
        identity: str,
        batch_path: str,
        batch_script: str,
    ) -> CommandResult:
        return self.runner.cluster(
            identity,
            self._batch_script_write_argv(batch_path, batch_script),
            timeout=15,
        )

    @staticmethod
    def _batch_script_write_argv(
        batch_path: str, batch_script: str
    ) -> tuple[str, ...]:
        encoded = base64.b64encode(batch_script.encode("utf-8")).decode("ascii")
        writer = (
            "import base64, os, pathlib, sys; "
            "path = pathlib.Path(sys.argv[1]); "
            "path.parent.mkdir(parents=True, exist_ok=True); "
            "temporary = path.with_suffix(path.suffix + '.new'); "
            "temporary.write_bytes(base64.b64decode(sys.argv[2], validate=True)); "
            "os.chmod(temporary, 0o700); temporary.replace(path)"
        )
        return ("python3", "-c", writer, batch_path, encoded)

    @staticmethod
    def _application_batch_script_save_path(application_path: str) -> str:
        path = Path(application_path)
        name = f"{path.stem}.qfw.sbatch" if path.stem else "application.qfw.sbatch"
        return str(path.with_name(name))

    def save_application_batch_script(
        self, request: dict[str, Any]
    ) -> dict[str, str]:
        identity, _backend, _example, _mode, requirements = (
            self._validated_experiment_request(
                request,
                default_identity="",
                require_hardware_confirmation=False,
            )
        )
        if requirements["application_source"] != "path":
            raise ValueError("batch scripts can only be saved for application paths")
        if requirements["application_submission_type"] != "executable":
            raise ValueError("only executable submissions generate a batch script")
        batch_script = str(requirements.get("batch_script") or "")
        if not batch_script:
            raise ValueError("batch_script is required")

        save_path = self._application_batch_script_save_path(
            str(requirements["application_path"])
        )
        encoded = base64.b64encode(batch_script.encode("utf-8")).decode("ascii")
        overwrite = "1" if request.get("overwrite") is True else "0"
        writer = (
            "import base64, os, pathlib, sys; "
            "path = pathlib.Path(sys.argv[1]); "
            "overwrite = sys.argv[3] == '1'; "
            "path.parent.mkdir(parents=True, exist_ok=True); "
            "data = base64.b64decode(sys.argv[2], validate=True); "
            "sys.exit(3) if path.exists() and not overwrite else None; "
            "temporary = path.with_suffix(path.suffix + '.new'); "
            "temporary.write_bytes(data); "
            "os.chmod(temporary, 0o700); temporary.replace(path)"
        )
        result = self.runner.cluster(
            identity,
            ("python3", "-c", writer, save_path, encoded, overwrite),
            timeout=15,
        )
        if result.returncode == 3:
            raise FileExistsError(save_path)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        return {"outcome": "success", "path": save_path}

    def cancel_experiment(self, experiment_id: str, identity: str) -> None:
        matches = [
            item for item in self.store.experiments()
            if item.get("experiment_id") == experiment_id
        ]
        if not matches:
            raise KeyError("experiment not found")
        experiment = matches[0]
        if identity != "root" and identity != experiment.get("identity"):
            raise PermissionError("experiment is owned by another identity")
        job_id = str(experiment.get("slurm_job_id", ""))
        if job_id:
            result = self.runner.cluster(identity, ("scancel", job_id))
            if result.returncode:
                raise RuntimeError(result.stderr or result.stdout)
        self.store.append_event({
            "kind": "progress",
            "component": "slurm",
            "identity": str(experiment.get("identity", identity)),
            "experiment_id": experiment_id,
            "job_id": job_id,
            "severity": "warning",
            "message": "cancellation requested",
        })
        self.store.audit({
            "identity": identity,
            "host_identity": "electroboy-service",
            "action": "experiment-cancel",
            "target": experiment_id,
            "request_id": job_id,
            "outcome": "requested",
        })

    def retry_experiment(
        self, experiment_id: str, identity: str, submit_real_hardware: bool
    ) -> Experiment:
        source = self._owned_experiment(experiment_id, identity)
        manifest = source.get("manifest", {})
        requirements = manifest.get("requirements", {})
        request = {
            "identity": identity,
            "backend": source.get("backend"),
            "example": source.get("example"),
            "allocation_mode": source.get("allocation_mode"),
            **requirements,
            "submit_real_hardware": submit_real_hardware,
            "retry_of": experiment_id,
        }
        return self.submit_experiment(request)

    def _owned_experiment(self, experiment_id: str, identity: str) -> dict[str, Any]:
        if identity not in IDENTITIES:
            raise ValueError("unsupported identity")
        match = next((
            item for item in self.store.experiments()
            if item.get("experiment_id") == experiment_id
        ), None)
        if match is None:
            raise KeyError("experiment not found")
        if identity != "root" and match.get("identity") != identity:
            raise PermissionError("experiment is owned by another identity")
        return match

    def shell_context(self, identity: str, target: str) -> dict[str, str]:
        if identity not in IDENTITIES:
            raise ValueError("unsupported identity")
        if not _SAFE_NAME.fullmatch(target):
            raise ValueError("invalid shell target")
        service_nodes = {
            "iqm-head", "shim-head", "fake-iqm-head",
            "nwqsim-head", "nwqsim-worker-1", "nwqsim-worker-2",
            "slurmdbd", "slurmrestd", "mysql",
        }
        if target in service_nodes and identity != "root":
            raise PermissionError("service-node shells require root selection")
        home = "/root" if identity == "root" else f"/workspace/home/{identity}"
        if target == "slurmctld":
            return {"identity": identity, "target": target, "home": home}
        allowed = {"slurmctld"}
        if identity == "root":
            containers = self.runner.host((
                "docker", "compose", "ps", "--services", "--status", "running",
            ))
            if containers.returncode == 0:
                allowed.update(containers.stdout.split())
        else:
            jobs = self.runner.cluster(identity, (
                "squeue", "--noheader", "--user", identity,
                "--states=RUNNING", "--format=%N",
            ))
            if jobs.returncode == 0:
                for node_list in jobs.stdout.split():
                    hosts = self.runner.cluster(
                        identity, ("scontrol", "show", "hostnames", node_list)
                    )
                    if hosts.returncode == 0:
                        allowed.update(hosts.stdout.split())
        if target not in allowed:
            raise PermissionError("target is not allocated to the selected identity")
        return {"identity": identity, "target": target, "home": home}

    def events(self, cursor: int, limit: int, identity: str) -> dict[str, Any]:
        if identity not in IDENTITIES:
            raise ValueError("unsupported identity")
        return {
            "schema": "qfw-dashboard-event-page-v1",
            **self.store.events(cursor=cursor, limit=limit, identity=identity),
        }

    def logs(
        self, source: str, cursor: int, limit: int, identity: str,
        instance: str = "",
    ) -> dict[str, Any]:
        if source == "application":
            experiment = self._owned_experiment(instance, identity)
            artifacts = experiment.get("artifacts", [])
            if not artifacts:
                raise KeyError("experiment output is not available")
            owner = str(experiment.get("identity"))
            prefix = f"/workspace/home/{owner}/"
            path = str(artifacts[0])
            if not path.startswith(prefix):
                raise PermissionError("application output is outside its home")
            selected = LogSource(
                "application", instance, "slurmctld", path, visibility=owner
            )
        elif source in SOURCES:
            selected = SOURCES[source]
        else:
            raise ValueError("unknown log source")
        return read_source(
            self.runner, selected, identity=identity,
            cursor=max(0, cursor), limit=max(1, min(limit, 500)),
        )

    def artifact(
        self, experiment_id: str, index: int, identity: str
    ) -> dict[str, Any]:
        experiment = self._owned_experiment(experiment_id, identity)
        artifacts = experiment.get("artifacts", [])
        if index < 0 or index >= len(artifacts):
            raise KeyError("artifact not found")
        owner = str(experiment.get("identity"))
        path = str(artifacts[index])
        if not path.startswith(f"/workspace/home/{owner}/"):
            raise PermissionError("artifact is outside the experiment home")
        data = self._read_artifact(owner, path)
        return {
            "schema": "qfw-dashboard-artifact-v1",
            "experiment_id": experiment_id,
            "identity": owner,
            "path": path,
            "name": Path(path).name,
            "size": len(data),
            "content_base64": base64.b64encode(data).decode("ascii"),
        }

    def experiment_archive(
        self, experiment_id: str, identity: str
    ) -> dict[str, Any]:
        experiment = self._owned_experiment(experiment_id, identity)
        owner = str(experiment.get("identity"))
        prefix = f"/workspace/home/{owner}/"
        artifacts = list(experiment.get("artifacts", []))
        self._collect_experiment_log_artifact_paths(owner, experiment, artifacts)
        archived_experiment = {**experiment, "artifacts": artifacts}
        missing: list[str] = []
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(
            archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr(
                "experiment.json",
                json.dumps(archived_experiment, indent=2, sort_keys=True) + "\n",
            )
            for index, artifact_path in enumerate(artifacts):
                path = str(artifact_path)
                if not path.startswith(prefix):
                    missing.append(f"{path}: outside experiment home")
                    continue
                try:
                    data = self._read_artifact(owner, path, max_bytes=None)
                except RuntimeError as error:
                    missing.append(f"{path}: {error}")
                    continue
                name = self._archive_artifact_name(experiment, index, path)
                archive.writestr(name, data)
            if missing:
                archive.writestr("missing-artifacts.txt", "\n".join(missing) + "\n")
        data = archive_buffer.getvalue()
        name = f"qfw-experiment-{experiment_id}.zip"
        return {
            "schema": "qfw-dashboard-experiment-archive-v1",
            "experiment_id": experiment_id,
            "identity": owner,
            "name": name,
            "mime_type": "application/zip",
            "size": len(data),
            "content_base64": base64.b64encode(data).decode("ascii"),
        }

    def service_archive(self, service_id: str, identity: str) -> dict[str, Any]:
        if identity != "root":
            raise PermissionError("service diagnostics require root selection")
        files = SERVICE_DIAGNOSTICS.get(service_id)
        if files is None:
            raise KeyError(f"unknown service: {service_id}")
        state = self.state()
        records = [
            record
            for source_name in ("services", "service-plane")
            for record in state.get("sources", {}).get(source_name, {}).get(
                "records", []
            )
            if record.get("service_id") == service_id
        ]
        missing: list[str] = []
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(
            archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr(
                "service-status.json",
                json.dumps(redact_payload({
                    "service_id": service_id,
                    "captured_at": utc_now(),
                    "records": records,
                }), indent=2, sort_keys=True) + "\n",
            )
            for diagnostic in files:
                try:
                    data = self._read_cluster_file(
                        "root", diagnostic.container, diagnostic.path,
                        max_bytes=None,
                    )
                except RuntimeError as error:
                    missing.append(f"{diagnostic.path}: {error}")
                    continue
                archive.writestr(
                    diagnostic.name,
                    redact(data.decode("utf-8", "replace")).encode("utf-8"),
                )
            if missing:
                archive.writestr("missing-files.txt", "\n".join(missing) + "\n")
        data = archive_buffer.getvalue()
        return {
            "schema": "qfw-dashboard-service-archive-v1",
            "service_id": service_id,
            "identity": identity,
            "name": f"qfw-service-{service_id}-diagnostics.zip",
            "mime_type": "application/zip",
            "size": len(data),
            "content_base64": base64.b64encode(data).decode("ascii"),
        }

    def _read_artifact(
        self, owner: str, path: str, *, max_bytes: int | None = 8388608
    ) -> bytes:
        return self._read_cluster_file(
            owner, "slurmctld", path, max_bytes=max_bytes
        )

    @staticmethod
    def _experiment_log_archive_root(experiment: Any) -> str:
        manifest = (
            experiment.manifest if isinstance(experiment, Experiment)
            else experiment.get("manifest", {})
        )
        output_path = str(manifest.get("output_path", ""))
        if not output_path:
            return ""
        return str(Path(output_path).parent / "defw-logs")

    def _collect_experiment_log_artifacts(self, experiment: Experiment) -> None:
        self._collect_experiment_log_artifact_paths(
            experiment.identity, experiment, experiment.artifacts
        )

    def _collect_experiment_log_artifact_paths(
        self, identity: str, experiment: Any, artifacts: list[str]
    ) -> None:
        root = self._experiment_log_archive_root(experiment)
        prefix = f"/workspace/home/{identity}/"
        if not root.startswith(prefix):
            return
        result = self.runner.cluster(
            identity,
            ("find", root, "-maxdepth", "8", "-type", "f"),
            timeout=15,
        )
        if result.returncode:
            return
        log_prefix = f"{root.rstrip('/')}/"
        for path in sorted(line.strip() for line in result.stdout.splitlines()):
            if (
                path.startswith(prefix)
                and path.startswith(log_prefix)
                and path not in artifacts
            ):
                artifacts.append(path)

    def _archive_artifact_name(
        self, experiment: dict[str, Any], index: int, path: str
    ) -> str:
        log_root = self._experiment_log_archive_root(experiment).rstrip("/")
        if log_root and path.startswith(f"{log_root}/"):
            relative = path[len(log_root) + 1:]
            if relative and ".." not in Path(relative).parts:
                return f"logs/{relative}"
        return f"artifacts/{index:02d}-{Path(path).name}"

    def _read_cluster_file(
        self, identity: str, container: str, path: str, *,
        max_bytes: int | None = 8388608,
    ) -> bytes:
        reader = (
            "import base64, pathlib, sys; "
            "p=pathlib.Path(sys.argv[1]); "
            "data=p.read_bytes(); "
            "limit=sys.argv[2]; "
            "assert not limit or len(data) <= int(limit), "
            "f'artifact exceeds {limit} bytes'; "
            "print(base64.b64encode(data).decode('ascii'))"
        )
        timeout = 300 if max_bytes is None else 15
        result = self.runner.cluster(
            identity,
            ("python3", "-c", reader, path, "" if max_bytes is None else str(max_bytes)),
            container=container,
            timeout=timeout,
        )
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        try:
            data = base64.b64decode(result.stdout.strip(), validate=True)
        except ValueError as error:
            raise RuntimeError("artifact reader returned invalid data") from error
        return data

    def preview_experiment(self, request: dict[str, Any]) -> dict[str, str]:
        return self._experiment_preview(request)

    def command_preview(self, request: dict[str, Any]) -> str:
        return self._experiment_preview(request)["command"]

    def _experiment_preview(self, request: dict[str, Any]) -> dict[str, str]:
        identity, backend, example, mode, requirements = (
            self._validated_experiment_request(
                request,
                default_identity="user-a",
                require_hardware_confirmation=False,
            )
        )
        preview_id = self._experiment_id(request)
        experiment_root = (
            f"/workspace/home/{identity}/qfw-dashboard/experiments/{preview_id}"
        )
        batch_path = f"{experiment_root}/job.sbatch"
        output_path = f"{experiment_root}/job.out"
        external_batch = (
            requirements["application_source"] == "path"
            and requirements["application_submission_type"] == "sbatch"
        )
        if external_batch:
            batch_path = str(requirements["application_path"])
            return {
                "experiment_id": preview_id,
                "command": "\n".join((
                    f"# Existing batch file: {batch_path}",
                    "# Submission command: "
                    f"{shlex.join(('sbatch', '--parsable', batch_path))}",
                )),
                "batch_script": "",
                "batch_script_path": batch_path,
                "application_batch_script_save_path": "",
            }

        experiment = Experiment(preview_id, identity, backend, example, mode)
        batch_script = (
            str(requirements.get("batch_script") or "")
            or self._batch_script(experiment, requirements, output_path)
        )
        command = "\n".join((
            f"# Generated batch file: {batch_path}",
            f"# Submission command: {shlex.join(('sbatch', '--parsable', batch_path))}",
            "",
            batch_script,
        ))
        save_path = ""
        if requirements["application_source"] == "path":
            save_path = self._application_batch_script_save_path(
                str(requirements["application_path"])
            )
        return {
            "experiment_id": preview_id,
            "command": command,
            "batch_script": batch_script,
            "batch_script_path": batch_path,
            "application_batch_script_save_path": save_path,
        }
