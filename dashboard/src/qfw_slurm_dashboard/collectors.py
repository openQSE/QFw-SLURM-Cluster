"""Independent collectors for Docker, Slurm, and the QFw service plane."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .models import SourceState, utc_now
from .runner import CommandResult, CommandRunner


def _unavailable(name: str, error: str) -> SourceState:
    return SourceState(name, "unavailable", utc_now(), error=error[:1000])


def _json_objects(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return []
    try:
        value = json.loads(stripped)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]
    except json.JSONDecodeError:
        pass
    records: list[dict[str, Any]] = []
    for line in stripped.splitlines():
        value = json.loads(line)
        if isinstance(value, dict):
            records.append(value)
    return records


def docker_status(runner: CommandRunner) -> SourceState:
    result = runner.host(("docker", "compose", "ps", "--format", "json"))
    if result.returncode:
        return _unavailable("docker", result.stderr or result.stdout)
    try:
        raw_records = _json_objects(result.stdout)
    except (TypeError, json.JSONDecodeError) as error:
        return _unavailable("docker", f"malformed Docker JSON: {error}")
    records = [{
        "kind": "container",
        "name": item.get("Name") or item.get("Names") or item.get("Service"),
        "service": item.get("Service", ""),
        "image": item.get("Image", ""),
        "state": item.get("State", ""),
        "status": item.get("Status", ""),
        "health": item.get("Health", ""),
    } for item in raw_records]
    running = all(str(item.get("state", "")).lower() == "running" for item in records)
    status = "ready" if records and running else "stopped" if not records else "degraded"
    return SourceState("docker", status, utc_now(), records)


def _pipe_records(result: CommandResult, fields: tuple[str, ...]) -> list[dict[str, str]]:
    records = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        values = line.split("|")
        values += [""] * (len(fields) - len(values))
        records.append(dict(zip(fields, values, strict=False)))
    return records


def _slurm_number(value: Any) -> int:
    if isinstance(value, dict):
        number = value.get("number", 0)
        return int(number) if value.get("set", False) else 0
    return int(value or 0)


def _slurm_jobs(text: str) -> list[dict[str, str]]:
    payload = json.loads(text)
    jobs = payload.get("jobs", [])
    if not isinstance(jobs, list):
        raise ValueError("Slurm JSON lacks jobs array")
    records = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("job_id", ""))
        heterogeneous_id = _slurm_number(job.get("het_job_id"))
        if heterogeneous_id:
            job_id = f"{heterogeneous_id}+{_slurm_number(job.get('het_job_offset'))}"
        state = job.get("job_state", "")
        if isinstance(state, list):
            state = state[0] if state else ""
        records.append({
            "job_id": job_id,
            "user": str(job.get("user_name", "")),
            "state": str(state),
            "partition": str(job.get("partition", "")),
            "nodes": str(job.get("nodes", "")),
            "elapsed": str(_slurm_number(job.get("time_used"))),
            "reason": str(
                job.get("state_description") or job.get("state_reason") or ""
            ),
            "job_name": str(job.get("name", "")),
        })
    return records


def slurm_status(runner: CommandRunner) -> SourceState:
    controller = runner.cluster("root", ("scontrol", "ping"))
    database = runner.cluster(
        "root", ("sacctmgr", "--noheader", "--parsable2", "show", "cluster")
    )
    nodes = runner.cluster(
        "root",
        ("sinfo", "--noheader", "--Node", "--format=%N|%P|%T|%E|%c|%m|%f"),
    )
    if nodes.returncode:
        return _unavailable("slurm", nodes.stderr or nodes.stdout)
    jobs = runner.cluster(
        "root",
        ("squeue", "--json"),
    )
    if jobs.returncode:
        return _unavailable("slurm", jobs.stderr or jobs.stdout)
    records: list[dict[str, Any]] = [
        {
            "kind": "controller", "name": "slurmctld",
            "state": "ready" if controller.returncode == 0 else "unavailable",
            "detail": (controller.stdout or controller.stderr).strip(),
        },
        {
            "kind": "database", "name": "slurmdbd",
            "state": "ready" if database.returncode == 0 else "unavailable",
            "detail": (database.stdout or database.stderr).strip(),
        },
    ] + [
        {"kind": "node", **item}
        for item in _pipe_records(
            nodes,
            ("node", "partition", "state", "reason", "cpus", "memory", "features"),
        )
    ]
    try:
        records.extend({"kind": "job", **item} for item in _slurm_jobs(jobs.stdout))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        return _unavailable("slurm", f"malformed Slurm job JSON: {error}")
    status = "ready" if controller.returncode == 0 and database.returncode == 0 \
        else "degraded"
    return SourceState("slurm", status, utc_now(), records)


def _qfw_json(
    runner: CommandRunner, name: str, record_key: str, argv: tuple[str, ...]
) -> SourceState:
    result = runner.cluster("root", argv, timeout=20)
    if result.returncode:
        message = result.stderr or result.stdout
        stopped_markers = ("not running", "not ready", "state not found")
        status = "stopped" if any(
            marker in message.lower() for marker in stopped_markers
        ) else "unavailable"
        return SourceState(name, status, utc_now(), error=message[:1000])
    try:
        envelopes = _json_objects(result.stdout)
    except (TypeError, json.JSONDecodeError) as error:
        return _unavailable(name, f"malformed {name} JSON: {error}")
    if len(envelopes) != 1 or not isinstance(envelopes[0].get(record_key), list):
        return _unavailable(name, f"{name} JSON lacks {record_key} array")
    records = [item for item in envelopes[0][record_key] if isinstance(item, dict)]
    errors = envelopes[0].get("errors", [])
    return SourceState(
        name, "degraded" if errors else "ready", utc_now(), records,
        error="; ".join(str(item) for item in errors)[:1000],
    )


def service_status(runner: CommandRunner) -> SourceState:
    return _qfw_json(runner, "services", "services", (
        "bash", "-lc",
        "export QFW_SHARED_ROOT=/workspace/qfw-container-base; "
        "source /opt/openqse/qfw/bin/qfw-activate "
        "--venv /opt/openqse/qfw-venv >/dev/null && qfw-sinfo --json",
    ))


def allocation_status(runner: CommandRunner) -> SourceState:
    return _qfw_json(runner, "allocations", "jobs", (
        "bash", "-lc",
        "export QFW_SHARED_ROOT=/workspace/qfw-container-base; "
        "source /opt/openqse/qfw/bin/qfw-activate "
        "--venv /opt/openqse/qfw-venv >/dev/null && qfw-squeue --json",
    ))


def _first_json_object(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    if start < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def service_plane_status(runner: CommandRunner) -> SourceState:
    result = runner.cluster(
        "root", ("qfw-site-services", "status", "--json"), timeout=12)
    output = f"{result.stdout}\n{result.stderr}"
    payload = _first_json_object(output) or {}
    services = payload.get("services") or {}
    records: list[dict[str, Any]] = []
    for component in (
        "directory", "nwqsim", "iqm", "shim", "ibm", "fake-iqm", "gateway",
    ):
        entry = services.get(component) or {}
        document = entry.get("detail") if isinstance(entry, dict) else {}
        document = document if isinstance(document, dict) else {}
        component_key = {
            "directory": "directory",
            "nwqsim": "qpm:nwqsim",
            "iqm": "qpm:iqm-ornl-20q",
            "shim": "qpm:shim-ornl-20q",
            "ibm": "qpm:shim-ibm-156-nh",
            "fake-iqm": "qpm:fake-iqm",
        }.get(component)
        managed = document.get("components", {}).get(component_key, {}) \
            if component_key else {}
        if isinstance(managed, dict) and managed:
            component_state = str(managed.get("state", "stopped")).lower()
            ready = managed.get("ready", component_state == "ready")
            component_state = "ready" if ready and component_state == "ready" else "stopped"
        else:
            component_state = (
                "ready" if str(entry.get("state", "down")).lower() == "up"
                else "stopped"
            )
        records.append({
            "component": component,
            "service_id": {
                "directory": "directory-service",
                "nwqsim": "nwqsim",
                "iqm": "iqm-ornl-20q",
                "shim": "shim-ornl-20q",
                "ibm": "shim-ibm-156-nh",
                "fake-iqm": "fake-iqm",
                "gateway": "qfw-slurm-gateway",
            }[component],
            "node": managed.get("node", "slurmctld" if component in {
                "directory", "gateway",
            } else ""),
            "state": component_state,
            "backend": {
                "directory": "DEFw",
                "nwqsim": "NWQSim",
                "iqm": "IQM",
                "shim": "Shim",
                "ibm": "IBM",
                "fake-iqm": "Fake IQM",
                "gateway": "QSGP",
            }[component],
            "active_reservations": "—",
            "detail": json.dumps(document, indent=2, sort_keys=True)[-1000:],
        })
        if component == "nwqsim":
            dvm = document.get("components", {}).get("prte-dvm", {})
            dvm_ready = isinstance(dvm, dict) and dvm.get("ready") is True \
                and dvm.get("state") == "ready"
            records.append({
                "component": "dvm", "service_id": "nwqsim-dvm",
                "node": dvm.get("node", "") if isinstance(dvm, dict) else "",
                "state": "ready" if dvm_ready else "stopped",
                "backend": "PRTE", "active_reservations": "—",
                "detail": "NWQSim PRTE DVM",
            })
    if not services:
        return SourceState("service-plane", "error", utc_now(), [], output[-1000:])
    ready = sum(item["state"] == "ready" for item in records)
    status = "ready" if ready == len(records) else "degraded" if ready else "stopped"
    return SourceState("service-plane", status, utc_now(), records)


def reconcile_qpm_registration(
    sources: list[SourceState],
) -> list[SourceState]:
    """Require a live directory registration for a managed QPM to be ready."""
    by_name = {source.name: source for source in sources}
    catalog = by_name.get("services")
    service_plane = by_name.get("service-plane")
    if catalog is None or service_plane is None or catalog.status == "loading":
        return sources

    catalog_by_id = {
        str(record.get("service_id")): record
        for record in catalog.records
        if record.get("service_id")
    }
    records: list[dict[str, Any]] = []
    for original in service_plane.records:
        record = dict(original)
        if record.get("component") not in {
            "nwqsim", "iqm", "shim", "ibm", "fake-iqm",
        }:
            records.append(record)
            continue
        process_state = str(record.get("state", "stopped")).lower()
        catalog_record = catalog_by_id.get(str(record.get("service_id")), {})
        registration_state = str(catalog_record.get("state", "DOWN")).upper()
        try:
            generation = int(catalog_record.get("generation", 0) or 0)
        except (TypeError, ValueError):
            generation = 0
        registered = (
            catalog.status in {"ready", "degraded"}
            and registration_state not in {
                "", "DOWN", "ERROR", "STALE", "STOPPED", "UNAVAILABLE",
            }
            and bool(catalog_record.get("runtime_id"))
            and generation > 0
        )
        record.update({
            "process_state": process_state,
            "registration_state": registration_state,
            "registered": registered,
        })
        if process_state == "ready" and not registered:
            record["state"] = "stopped"
            record["ready"] = False
            record["health_detail"] = (
                "process is ready but the QPM is not registered with the "
                "directory service"
            )
        records.append(record)

    ready = sum(record.get("state") == "ready" for record in records)
    status = (
        "ready" if records and ready == len(records)
        else "degraded" if ready
        else "stopped"
    )
    replacement = SourceState(
        service_plane.name,
        status,
        service_plane.observed_at,
        records,
        service_plane.error,
    )
    return [replacement if source.name == "service-plane" else source
            for source in sources]


def service_health_summary(
    runner: CommandRunner, target: str = "all",
) -> list[str]:
    sources = reconcile_qpm_registration([
        service_plane_status(runner),
        service_status(runner),
    ])
    service_plane = next(
        source for source in sources if source.name == "service-plane")
    records = {
        str(record.get("component")): record
        for record in service_plane.records
        if record.get("component") != "dvm"
    }
    labels = {
        "directory": "Directory",
        "nwqsim": "NWQSim",
        "iqm": "IQM",
        "shim": "Shim",
        "ibm": "IBM",
        "fake-iqm": "Fake IQM",
        "gateway": "Gateway",
    }
    selected = list(labels) if target == "all" else [target]
    lines = []
    all_ready = True
    for component in selected:
        record = records.get(component, {})
        ready = str(record.get("state", "stopped")).lower() == "ready"
        all_ready = all_ready and ready
        state = "UP" if ready else "DOWN"
        if not ready and record.get("process_state") == "ready" \
                and not record.get("registered", False):
            state += " (process ready; not registered)"
        lines.append(f"{labels[component]}: {state}")
    overall = "UP" if all_ready and lines else "DOWN"
    heading = "QFw site services" if target == "all" else labels[target]
    return [f"{heading}: {overall}", "", *lines]


def inventory_status(runner: CommandRunner) -> SourceState:
    records: list[dict[str, Any]] = []
    cluster_revision = runner.host(("git", "rev-parse", "HEAD"))
    electroboy_revision = runner.host((
        "git", "-C", "dashboard/external/electroboy", "rev-parse", "HEAD",
    ))
    records.extend((
        {
            "kind": "revision", "component": "QFw-SLURM-Cluster",
            "value": cluster_revision.stdout.strip() or "unknown",
        },
        {
            "kind": "revision", "component": "ElectroBoy",
            "value": electroboy_revision.stdout.strip() or "unknown",
        },
    ))
    images = runner.host(("docker", "compose", "images", "--format", "json"))
    if images.returncode == 0:
        try:
            for item in _json_objects(images.stdout):
                records.append({
                    "kind": "image",
                    "component": item.get("Service") or item.get("ContainerName"),
                    "value": item.get("ID") or item.get("Repository"),
                    "tag": item.get("Tag", ""),
                })
        except (TypeError, json.JSONDecodeError):
            pass
    commands = (
        ("Slurm", ("slurmctld", "-V")),
        ("MUNGE", ("munge", "--version")),
        ("Python", ("python3", "--version")),
        ("PRTE", ("prte", "--version")),
        ("libfabric", ("fi_info", "--version")),
    )
    for component, argv in commands:
        result = runner.cluster("root", argv, timeout=5)
        records.append({
            "kind": "version", "component": component,
            "value": (result.stdout or result.stderr).splitlines()[0]
            if (result.stdout or result.stderr).splitlines() else "unavailable",
        })
    for component, path in (
        ("QFw site", "/etc/openqse/qfw/site.yaml"),
        ("qfw-slurm", "/etc/openqse/qfw-slurm/plugin.conf"),
    ):
        result = runner.cluster("root", ("sha256sum", path), timeout=5)
        fingerprint = result.stdout.split()[0] if result.returncode == 0 else "unavailable"
        records.append({
            "kind": "configuration", "component": component,
            "path": path, "value": fingerprint,
        })
    ready = cluster_revision.returncode == 0 and electroboy_revision.returncode == 0
    return SourceState(
        "inventory", "ready" if ready else "degraded", utc_now(), records
    )


def diagnostics(runner: CommandRunner) -> SourceState:
    checks: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("munge", "slurmctld", ("bash", "-lc", "munge -n | unmunge")),
        ("clock", "slurmctld", ("date", "--iso-8601=ns")),
        ("cpu", "slurmctld", ("nproc",)),
        ("mounts", "slurmctld", ("findmnt", "--json", "-T", "/workspace")),
        ("modules", "slurmctld", ("bash", "-lc", "module -t avail 2>&1")),
        (
            "gateway-connectivity", "slurmctld",
            ("bash", "-lc", "timeout 2 bash -c '</dev/tcp/slurmctld/18095'"),
        ),
        (
            "credential-readiness", "iqm-head",
            (
                "bash", "-lc",
                "test -r /etc/openqse/qfw/device/qpu-users.json",
            ),
        ),
        (
            "ibm-credential-readiness", "ibm-156-nh",
            (
                "bash", "-lc",
                "test -r /etc/openqse/qfw/device/qpu-users.json",
            ),
        ),
        (
            "fake-iqm-device-readiness", "fake-iqm-head",
            (
                "bash", "-lc",
                "test -r /etc/openqse/qfw/device/device-access.yaml",
            ),
        ),
        (
            "directory-connection-record", "slurmctld",
            (
                "test", "-s",
                "/workspace/qfw-container-base/qfw-site-services/"
                "directory-service.json",
            ),
        ),
        (
            "dvm-uri", "nwqsim-head",
            (
                "test", "-s",
                "/var/lib/qfw-site-services/qpm/nwqsim/prte_dvm/dvm-uri",
            ),
        ),
        (
            "service-registration", "slurmctld",
            (
                "bash", "-lc",
                "export QFW_SHARED_ROOT=/workspace/qfw-container-base; "
                "source /opt/openqse/qfw/bin/qfw-activate "
                "--venv /opt/openqse/qfw-venv >/dev/null; "
                "qfw-sinfo --json",
            ),
        ),
    )
    records: list[dict[str, Any]] = []
    for name, container, argv in checks:
        try:
            result = runner.cluster(
                "root", argv, container=container,
                timeout=20 if name == "service-registration" else 5,
            )
            check_status = "ready" if result.returncode == 0 else "failed"
            output = (result.stdout or result.stderr)[-2000:]
        except Exception as error:
            check_status = "failed"
            output = str(error)[-2000:]
        records.append(
            {
                "check": name,
                "node": container,
                "status": check_status,
                "output": output,
            }
        )
    clock_values = []
    for container in (
        "c1", "nwqsim-head", "iqm-head", "shim-head", "ibm-156-nh",
        "fake-iqm-head",
    ):
        try:
            result = runner.cluster("root", (
                "bash", "-lc",
                "printf 'clock='; date +%s%N; printf 'cpus='; nproc; "
                "test $(nproc) -eq 4; findmnt -n -T /workspace >/dev/null; "
                "munge -n | unmunge >/dev/null",
            ), container=container, timeout=5)
            output = (result.stdout or result.stderr)[-2000:]
            check_status = "ready" if result.returncode == 0 else "failed"
        except Exception as error:
            output = str(error)[-2000:]
            check_status = "failed"
        match = next((
            line.split("=", 1)[1] for line in output.splitlines()
            if line.startswith("clock=")
        ), "")
        if match.isdigit():
            clock_values.append(int(match))
        records.append({
            "check": "node-baseline", "node": container,
            "status": check_status,
            "output": output,
        })
    skew = max(clock_values) - min(clock_values) if len(clock_values) > 1 else 0
    records.append({
        "check": "clock-skew", "node": "cluster",
        "status": "ready" if len(clock_values) == 5 and skew < 5_000_000_000
        else "failed",
        "output": f"maximum skew {skew} ns",
    })
    status = "ready" if all(item["status"] == "ready" for item in records) else "degraded"
    return SourceState("diagnostics", status, utc_now(), records)


COLLECTORS: tuple[Callable[[CommandRunner], SourceState], ...] = (
    docker_status,
    slurm_status,
    service_status,
    allocation_status,
    service_plane_status,
    inventory_status,
)

_COLLECTOR_NAMES = {
    docker_status: "docker",
    slurm_status: "slurm",
    service_status: "services",
    allocation_status: "allocations",
    service_plane_status: "service-plane",
    inventory_status: "inventory",
}


class LiveCollectorSet:
    """Refresh collectors independently without blocking state snapshots."""

    def __init__(
        self,
        runner: CommandRunner,
        *,
        collectors: tuple[Callable[[CommandRunner], SourceState], ...] = COLLECTORS,
        refresh_interval: float = 2.5,
    ) -> None:
        self.runner = runner
        self.collectors = collectors
        self.refresh_interval = refresh_interval
        self._lock = threading.Lock()
        self._results: dict[str, SourceState] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._finished_at: dict[str, float] = {}

    @staticmethod
    def _name(collector: Callable[[CommandRunner], SourceState]) -> str:
        return _COLLECTOR_NAMES.get(
            collector, collector.__name__.removesuffix("_status").replace("_", "-")
        )

    def snapshot(self) -> list[SourceState]:
        now = time.monotonic()
        start: list[threading.Thread] = []
        with self._lock:
            for collector in self.collectors:
                name = self._name(collector)
                if name in self._threads:
                    continue
                if now - self._finished_at.get(name, 0.0) < self.refresh_interval:
                    continue
                thread = threading.Thread(
                    target=self._refresh,
                    args=(name, collector),
                    daemon=True,
                    name=f"qfw-dashboard-collector-{name}",
                )
                self._threads[name] = thread
                start.append(thread)
            results = [
                self._results.get(
                    self._name(collector),
                    SourceState(
                        self._name(collector), "loading", utc_now(),
                        error="live data refresh is in progress",
                    ),
                )
                for collector in self.collectors
            ]
        for thread in start:
            thread.start()
        return results

    def _refresh(
        self,
        name: str,
        collector: Callable[[CommandRunner], SourceState],
    ) -> None:
        try:
            result = collector(self.runner)
        except Exception as error:
            result = _unavailable(name, str(error))
        with self._lock:
            self._results[name] = result
            self._finished_at[name] = time.monotonic()
            self._threads.pop(name, None)


def collect_all(runner: CommandRunner) -> list[SourceState]:
    def collect(collector: Callable[[CommandRunner], SourceState]) -> SourceState:
        try:
            return collector(runner)
        except Exception as error:
            name = _COLLECTOR_NAMES[collector]
            return _unavailable(name, str(error))

    with ThreadPoolExecutor(max_workers=len(COLLECTORS)) as pool:
        return reconcile_qpm_registration(list(pool.map(collect, COLLECTORS)))
