"""Versioned dashboard records and correlation identifiers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "qfw-dashboard-v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SourceState:
    name: str
    status: str
    observed_at: str
    records: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Operation:
    operation_id: str
    action: str
    identity: str
    target: str
    status: str = "queued"
    created_at: str = field(default_factory=utc_now)
    started_at: str = ""
    completed_at: str = ""
    return_code: int | None = None
    output: list[str] = field(default_factory=list)
    request_id: str = ""
    dry_run: bool = False

    def payload(self) -> dict[str, Any]:
        return {"schema": SCHEMA_VERSION, **asdict(self)}


@dataclass
class Experiment:
    experiment_id: str
    identity: str
    backend: str
    example: str
    allocation_mode: str
    status: str = "created"
    slurm_job_id: str = ""
    reservations: list[list[str]] = field(default_factory=list)
    operation_id: str = ""
    created_at: str = field(default_factory=utc_now)
    modified_at: str = field(default_factory=utc_now)
    completed_at: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)
    timeline: list[dict[str, Any]] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        return {"schema": SCHEMA_VERSION, **asdict(self)}


def aggregate_state(sources: list[SourceState]) -> dict[str, Any]:
    statuses = {source.status for source in sources}
    if statuses == {"ready"}:
        health = "ready"
    elif "ready" in statuses:
        health = "partial"
    elif statuses <= {"stopped", "unavailable"}:
        health = "stopped"
    else:
        health = "degraded"
    return {
        "schema": SCHEMA_VERSION,
        "observed_at": utc_now(),
        "health": health,
        "sources": {source.name: source.payload() for source in sources},
    }
