"""Dashboard-owned backend catalog for QFw application submission."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackendSpec:
    name: str
    label: str
    provider: str
    qpu: str
    service_target: str
    service_id: str
    max_time_minutes: int
    max_shots: int
    requires_hardware_confirmation: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "label": self.label,
            "provider": self.provider,
            "qpu": self.qpu,
            "service_target": self.service_target,
            "service_id": self.service_id,
            "max_time_minutes": self.max_time_minutes,
            "max_shots": self.max_shots,
            "requires_hardware_confirmation": (
                self.requires_hardware_confirmation
            ),
        }


BACKENDS = {
    "nwqsim": BackendSpec(
        name="nwqsim",
        label="NWQSim",
        provider="nwqsim",
        qpu="nwqsim",
        service_target="nwqsim",
        service_id="nwqsim",
        max_time_minutes=240,
        max_shots=65536,
    ),
    "iqm": BackendSpec(
        name="iqm",
        label="IQM",
        provider="iqm",
        qpu="ornl-iqm-20q",
        service_target="iqm",
        service_id="iqm-ornl-20q",
        max_time_minutes=15,
        max_shots=256,
        requires_hardware_confirmation=True,
    ),
    "shim": BackendSpec(
        name="shim",
        label="IQM shim",
        provider="shim",
        qpu="ornl-shim-20q",
        service_target="shim",
        service_id="shim-ornl-20q",
        max_time_minutes=15,
        max_shots=256,
        requires_hardware_confirmation=True,
    ),
    "ibm": BackendSpec(
        name="ibm",
        label="IBM",
        provider="ibm",
        qpu="ibm-156-nh",
        service_target="ibm",
        service_id="shim-ibm-156-nh",
        max_time_minutes=15,
        max_shots=256,
        requires_hardware_confirmation=True,
    ),
    "fake-iqm": BackendSpec(
        name="fake-iqm",
        label="Fake IQM",
        provider="fake-iqm",
        qpu="fake-iqm-20q",
        service_target="fake-iqm",
        service_id="fake-iqm",
        max_time_minutes=240,
        max_shots=65536,
    ),
}

BACKEND_ORDER = ("nwqsim", "iqm", "shim", "ibm", "fake-iqm")


def backend_spec(name: str) -> BackendSpec:
    return BACKENDS[name]


def backend_payload() -> list[dict[str, object]]:
    return [BACKENDS[name].as_dict() for name in BACKEND_ORDER]
