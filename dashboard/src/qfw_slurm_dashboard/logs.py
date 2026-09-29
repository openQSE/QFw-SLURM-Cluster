"""Bounded, cursor-based access to cluster-owned logs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .redaction import redact
from .runner import CommandRunner
from .models import utc_now


@dataclass(frozen=True)
class LogSource:
    component: str
    instance: str
    container: str
    path: str
    visibility: str = "root"


@dataclass(frozen=True)
class DiagnosticFile:
    name: str
    container: str
    path: str


SOURCES = {
    "slurm": LogSource(
        "slurm", "controller", "slurmctld", "/var/log/slurm/slurmctld.log"
    ),
    "gateway": LogSource(
        "gateway", "qfw-slurm", "slurmctld",
        "/var/log/qfw-slurm-gateway/gateway.log",
    ),
    "directory": LogSource(
        "directory", "qfw-site-dirsvc", "slurmctld",
        "/var/lib/qfw-site-services/directory/services/"
        "qfw-site-dirsvc/logs/defw_py.log",
    ),
    "nwqsim-qpm": LogSource(
        "qpmd", "nwqsim", "nwqsim-head",
        "/var/lib/qfw-site-services/qpm/nwqsim/services/"
        "nwqsim/logs/defw_py.log",
    ),
    "nwqsim-dvm": LogSource(
        "dvm", "nwqsim", "nwqsim-head",
        "/var/lib/qfw-site-services/qpm/nwqsim/state/service-plane.json",
    ),
    "nwqsim-simulator": LogSource(
        "simulator", "nwqsim", "nwqsim-head",
        "/var/lib/qfw-site-services/qpm/nwqsim/services/"
        "nwqsim/logs/nwqsim.stdout.log",
    ),
    "iqm-qpm": LogSource(
        "qpmd", "iqm-ornl-20q", "iqm-head",
        "/var/lib/qfw-site-services/qpm/iqm-ornl-20q/services/"
        "iqm-ornl-20q/logs/defw_py.log",
    ),
    "iqm-provider": LogSource(
        "provider", "iqm-client", "iqm-head",
        "/var/lib/qfw-site-services/qpm/iqm-ornl-20q/services/"
        "iqm-ornl-20q/logs/defw_py.log",
    ),
    "shim-qpm": LogSource(
        "qpmd", "shim-ornl-20q", "shim-head",
        "/var/lib/qfw-site-services/qpm/shim-ornl-20q/services/"
        "shim-ornl-20q/logs/defw_py.log",
    ),
    "shim-provider": LogSource(
        "provider", "shim-qrmi-qdmi", "shim-head",
        "/var/lib/qfw-site-services/qpm/shim-ornl-20q/services/"
        "shim-ornl-20q/logs/defw_py.log",
    ),
    "ibm-qpm": LogSource(
        "qpmd", "shim-ibm-156-nh", "ibm-156-nh",
        "/var/lib/qfw-site-services/qpm/shim-ibm-156-nh/services/"
        "shim-ibm-156-nh/logs/defw_py.log",
    ),
    "ibm-provider": LogSource(
        "provider", "ibm-qrmi", "ibm-156-nh",
        "/var/lib/qfw-site-services/qpm/shim-ibm-156-nh/services/"
        "shim-ibm-156-nh/logs/defw_py.log",
    ),
    "fake-iqm-qpm": LogSource(
        "qpmd", "fake-iqm", "fake-iqm-head",
        "/var/lib/qfw-site-services/qpm/fake-iqm/services/"
        "fake-iqm/logs/defw_py.log",
    ),
    "fake-iqm-provider": LogSource(
        "provider", "fake-iqm", "fake-iqm-head",
        "/var/lib/qfw-site-services/qpm/fake-iqm/services/"
        "fake-iqm/logs/defw_py.log",
    ),
}


SERVICE_DIAGNOSTICS = {
    "directory-service": (
        DiagnosticFile("logs/defw_py.log", "slurmctld",
                       "/var/lib/qfw-site-services/directory/services/"
                       "qfw-site-dirsvc/logs/defw_py.log"),
        DiagnosticFile("logs/defw_out.log", "slurmctld",
                       "/var/lib/qfw-site-services/directory/services/"
                       "qfw-site-dirsvc/logs/defw_out.log"),
        DiagnosticFile("logs/stdout.log", "slurmctld",
                       "/var/lib/qfw-site-services/directory/services/"
                       "qfw-site-dirsvc/logs/qfw-site-dirsvc.stdout.log"),
        DiagnosticFile("logs/stderr.log", "slurmctld",
                       "/var/lib/qfw-site-services/directory/services/"
                       "qfw-site-dirsvc/logs/qfw-site-dirsvc.stderr.log"),
        DiagnosticFile("state/ready.json", "slurmctld",
                       "/var/lib/qfw-site-services/directory/services/"
                       "qfw-site-dirsvc/ready.json"),
        DiagnosticFile("state/service-plane.json", "slurmctld",
                       "/var/lib/qfw-site-services/directory/state/"
                       "service-plane.json"),
    ),
    "qfw-slurm-gateway": (
        DiagnosticFile("logs/gateway.log", "slurmctld",
                       "/var/log/qfw-slurm-gateway/gateway.log"),
    ),
    "nwqsim": (
        DiagnosticFile("logs/defw_py.log", "nwqsim-head",
                       "/var/lib/qfw-site-services/qpm/nwqsim/services/"
                       "nwqsim/logs/defw_py.log"),
        DiagnosticFile("logs/defw_out.log", "nwqsim-head",
                       "/var/lib/qfw-site-services/qpm/nwqsim/services/"
                       "nwqsim/logs/defw_out.log"),
        DiagnosticFile("logs/stdout.log", "nwqsim-head",
                       "/var/lib/qfw-site-services/qpm/nwqsim/services/"
                       "nwqsim/logs/nwqsim.stdout.log"),
        DiagnosticFile("logs/stderr.log", "nwqsim-head",
                       "/var/lib/qfw-site-services/qpm/nwqsim/services/"
                       "nwqsim/logs/nwqsim.stderr.log"),
        DiagnosticFile("state/ready.json", "nwqsim-head",
                       "/var/lib/qfw-site-services/qpm/nwqsim/services/"
                       "nwqsim/ready.json"),
        DiagnosticFile("state/service-ready.json", "nwqsim-head",
                       "/var/lib/qfw-site-services/qpm/nwqsim/services/"
                       "nwqsim/service-ready.json"),
        DiagnosticFile("state/service-plane.json", "nwqsim-head",
                       "/var/lib/qfw-site-services/qpm/nwqsim/state/"
                       "service-plane.json"),
    ),
    "nwqsim-dvm": (
        DiagnosticFile("state/service-plane.json", "nwqsim-head",
                       "/var/lib/qfw-site-services/qpm/nwqsim/state/"
                       "service-plane.json"),
        DiagnosticFile("state/dvm-uri", "nwqsim-head",
                       "/var/lib/qfw-site-services/qpm/nwqsim/prte_dvm/dvm-uri"),
    ),
    "iqm-ornl-20q": (
        DiagnosticFile("logs/defw_py.log", "iqm-head",
                       "/var/lib/qfw-site-services/qpm/iqm-ornl-20q/services/"
                       "iqm-ornl-20q/logs/defw_py.log"),
        DiagnosticFile("logs/defw_out.log", "iqm-head",
                       "/var/lib/qfw-site-services/qpm/iqm-ornl-20q/services/"
                       "iqm-ornl-20q/logs/defw_out.log"),
        DiagnosticFile("logs/stdout.log", "iqm-head",
                       "/var/lib/qfw-site-services/qpm/iqm-ornl-20q/services/"
                       "iqm-ornl-20q/logs/iqm-ornl-20q.stdout.log"),
        DiagnosticFile("logs/stderr.log", "iqm-head",
                       "/var/lib/qfw-site-services/qpm/iqm-ornl-20q/services/"
                       "iqm-ornl-20q/logs/iqm-ornl-20q.stderr.log"),
        DiagnosticFile("state/ready.json", "iqm-head",
                       "/var/lib/qfw-site-services/qpm/iqm-ornl-20q/services/"
                       "iqm-ornl-20q/ready.json"),
        DiagnosticFile("state/service-ready.json", "iqm-head",
                       "/var/lib/qfw-site-services/qpm/iqm-ornl-20q/services/"
                       "iqm-ornl-20q/service-ready.json"),
        DiagnosticFile("state/service-plane.json", "iqm-head",
                       "/var/lib/qfw-site-services/qpm/iqm-ornl-20q/state/"
                       "service-plane.json"),
    ),
    "shim-ornl-20q": (
        DiagnosticFile("logs/defw_py.log", "shim-head",
                       "/var/lib/qfw-site-services/qpm/shim-ornl-20q/services/"
                       "shim-ornl-20q/logs/defw_py.log"),
        DiagnosticFile("logs/defw_out.log", "shim-head",
                       "/var/lib/qfw-site-services/qpm/shim-ornl-20q/services/"
                       "shim-ornl-20q/logs/defw_out.log"),
        DiagnosticFile("logs/stdout.log", "shim-head",
                       "/var/lib/qfw-site-services/qpm/shim-ornl-20q/services/"
                       "shim-ornl-20q/logs/shim-ornl-20q.stdout.log"),
        DiagnosticFile("logs/stderr.log", "shim-head",
                       "/var/lib/qfw-site-services/qpm/shim-ornl-20q/services/"
                       "shim-ornl-20q/logs/shim-ornl-20q.stderr.log"),
        DiagnosticFile("state/ready.json", "shim-head",
                       "/var/lib/qfw-site-services/qpm/shim-ornl-20q/services/"
                       "shim-ornl-20q/ready.json"),
        DiagnosticFile("state/service-ready.json", "shim-head",
                       "/var/lib/qfw-site-services/qpm/shim-ornl-20q/services/"
                       "shim-ornl-20q/service-ready.json"),
        DiagnosticFile("state/service-plane.json", "shim-head",
                       "/var/lib/qfw-site-services/qpm/shim-ornl-20q/state/"
                       "service-plane.json"),
    ),
    "shim-ibm-156-nh": (
        DiagnosticFile("logs/defw_py.log", "ibm-156-nh",
                       "/var/lib/qfw-site-services/qpm/shim-ibm-156-nh/services/"
                       "shim-ibm-156-nh/logs/defw_py.log"),
        DiagnosticFile("logs/defw_out.log", "ibm-156-nh",
                       "/var/lib/qfw-site-services/qpm/shim-ibm-156-nh/services/"
                       "shim-ibm-156-nh/logs/defw_out.log"),
        DiagnosticFile("logs/stdout.log", "ibm-156-nh",
                       "/var/lib/qfw-site-services/qpm/shim-ibm-156-nh/services/"
                       "shim-ibm-156-nh/logs/shim-ibm-156-nh.stdout.log"),
        DiagnosticFile("logs/stderr.log", "ibm-156-nh",
                       "/var/lib/qfw-site-services/qpm/shim-ibm-156-nh/services/"
                       "shim-ibm-156-nh/logs/shim-ibm-156-nh.stderr.log"),
        DiagnosticFile("state/ready.json", "ibm-156-nh",
                       "/var/lib/qfw-site-services/qpm/shim-ibm-156-nh/services/"
                       "shim-ibm-156-nh/ready.json"),
        DiagnosticFile("state/service-ready.json", "ibm-156-nh",
                       "/var/lib/qfw-site-services/qpm/shim-ibm-156-nh/services/"
                       "shim-ibm-156-nh/service-ready.json"),
        DiagnosticFile("state/service-plane.json", "ibm-156-nh",
                       "/var/lib/qfw-site-services/qpm/shim-ibm-156-nh/state/"
                       "service-plane.json"),
    ),
    "fake-iqm": (
        DiagnosticFile("logs/defw_py.log", "fake-iqm-head",
                       "/var/lib/qfw-site-services/qpm/fake-iqm/services/"
                       "fake-iqm/logs/defw_py.log"),
        DiagnosticFile("logs/defw_out.log", "fake-iqm-head",
                       "/var/lib/qfw-site-services/qpm/fake-iqm/services/"
                       "fake-iqm/logs/defw_out.log"),
        DiagnosticFile("logs/stdout.log", "fake-iqm-head",
                       "/var/lib/qfw-site-services/qpm/fake-iqm/services/"
                       "fake-iqm/logs/fake-iqm.stdout.log"),
        DiagnosticFile("logs/stderr.log", "fake-iqm-head",
                       "/var/lib/qfw-site-services/qpm/fake-iqm/services/"
                       "fake-iqm/logs/fake-iqm.stderr.log"),
        DiagnosticFile("state/ready.json", "fake-iqm-head",
                       "/var/lib/qfw-site-services/qpm/fake-iqm/services/"
                       "fake-iqm/ready.json"),
        DiagnosticFile("state/service-ready.json", "fake-iqm-head",
                       "/var/lib/qfw-site-services/qpm/fake-iqm/services/"
                       "fake-iqm/service-ready.json"),
        DiagnosticFile("state/service-plane.json", "fake-iqm-head",
                       "/var/lib/qfw-site-services/qpm/fake-iqm/state/"
                       "service-plane.json"),
    ),
}


_READER = r"""
import json
import os
import sys

path, offset_text, limit_text = sys.argv[1:]
offset = max(0, int(offset_text))
limit = max(1, min(int(limit_text), 500))
size = os.path.getsize(path)
gap = offset > size
if gap:
    offset = 0
with open(path, "rb") as stream:
    stream.seek(offset)
    data = stream.read(262144)
    cursor = stream.tell()
lines = data.decode("utf-8", "replace").splitlines()
if len(lines) > limit:
    lines = lines[-limit:]
    gap = True
print(json.dumps({"cursor": cursor, "gap": gap, "lines": lines}))
"""


def read_source(
    runner: CommandRunner,
    source: LogSource,
    *,
    identity: str,
    cursor: int,
    limit: int,
) -> dict[str, Any]:
    if source.visibility == "root" and identity != "root":
        raise PermissionError("service logs require root selection")
    run_identity = "root" if source.visibility == "root" else identity
    result = runner.cluster(
        run_identity,
        ("python3", "-c", _READER, source.path, str(cursor), str(limit)),
        container=source.container,
        timeout=5,
    )
    if result.returncode:
        return {
            "schema": "qfw-dashboard-log-page-v1",
            "source": source.component,
            "instance": source.instance,
            "events": [],
            "cursor": cursor,
            "gap": False,
            "status": "unavailable",
            "error": redact(result.stderr or result.stdout)[-1000:],
        }
    try:
        page = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"malformed log reader result: {error}") from error
    events = [{
        "schema": "qfw-dashboard-event-v1",
        "timestamp": utc_now(),
        "kind": "log",
        "component": source.component,
        "instance": source.instance,
        "identity": run_identity,
        "severity": _severity(line),
        "source_position": f"{cursor}:{index}",
        "message": redact(line),
    } for index, line in enumerate(page.get("lines", []), start=cursor)]
    return {
        "schema": "qfw-dashboard-log-page-v1",
        "source": source.component,
        "instance": source.instance,
        "events": events,
        "cursor": int(page.get("cursor", cursor)),
        "gap": bool(page.get("gap", False)),
        "status": "ready",
        "error": "",
    }


def _severity(line: str) -> str:
    lowered = line.lower()
    if "critical" in lowered or "fatal" in lowered:
        return "critical"
    if "error" in lowered or "traceback" in lowered:
        return "error"
    if "warning" in lowered or "warn" in lowered:
        return "warning"
    if "debug" in lowered:
        return "debug"
    return "info"
