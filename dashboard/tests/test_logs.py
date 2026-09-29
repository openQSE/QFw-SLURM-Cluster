import json
from pathlib import Path

import pytest

from qfw_slurm_dashboard.logs import (
    LogSource,
    SERVICE_DIAGNOSTICS,
    SOURCES,
    read_source,
)
from qfw_slurm_dashboard.runner import CommandResult


class Runner:
    def cluster(self, identity, argv, **kwargs):
        payload = {"cursor": 12, "gap": False, "lines": [
            "INFO ready", "ERROR api_key=secret",
        ]}
        return CommandResult(tuple(argv), 0, json.dumps(payload), "")


def test_log_reader_redacts_and_classifies() -> None:
    page = read_source(
        Runner(), SOURCES["gateway"], identity="root", cursor=0, limit=50
    )
    assert page["cursor"] == 12
    assert page["events"][1]["severity"] == "error"
    assert "secret" not in page["events"][1]["message"]


def test_service_logs_are_not_exposed_to_regular_users() -> None:
    with pytest.raises(PermissionError, match="root"):
        read_source(
            Runner(), SOURCES["iqm-qpm"], identity="user-a", cursor=0, limit=10
        )


def test_shim_qpm_log_source_uses_shim_node() -> None:
    source = SOURCES["shim-qpm"]
    assert source.container == "shim-head"
    assert "shim-ornl-20q/logs/defw_py.log" in source.path


def test_shim_service_diagnostics_include_defw_logs() -> None:
    diagnostics = {
        item.name: item
        for item in SERVICE_DIAGNOSTICS["shim-ornl-20q"]
    }
    assert diagnostics["logs/defw_py.log"].container == "shim-head"
    assert diagnostics["logs/defw_out.log"].container == "shim-head"
    assert "shim-ornl-20q/logs/defw_py.log" in (
        diagnostics["logs/defw_py.log"].path
    )
    assert "shim-ornl-20q/logs/defw_out.log" in (
        diagnostics["logs/defw_out.log"].path
    )


def test_fake_iqm_logs_use_fake_iqm_node() -> None:
    source = SOURCES["fake-iqm-qpm"]
    assert source.container == "fake-iqm-head"
    assert "fake-iqm/logs/defw_py.log" in source.path

    diagnostics = {
        item.name: item
        for item in SERVICE_DIAGNOSTICS["fake-iqm"]
    }
    assert diagnostics["logs/defw_py.log"].container == "fake-iqm-head"
    assert diagnostics["logs/defw_out.log"].container == "fake-iqm-head"


def test_ibm_logs_and_diagnostics_use_ibm_node() -> None:
    source = SOURCES["ibm-qpm"]
    assert source.container == "ibm-156-nh"
    assert "shim-ibm-156-nh/logs/defw_py.log" in source.path

    diagnostics = {
        item.name: item
        for item in SERVICE_DIAGNOSTICS["shim-ibm-156-nh"]
    }
    assert diagnostics["logs/defw_py.log"].container == "ibm-156-nh"
    assert diagnostics["logs/defw_out.log"].container == "ibm-156-nh"


def test_application_log_retains_captured_identity() -> None:
    source = LogSource(
        "application", "experiment", "slurmctld", "/tmp/output",
        visibility="user-a",
    )
    page = read_source(Runner(), source, identity="user-a", cursor=5, limit=10)
    assert page["events"][0]["identity"] == "user-a"
    assert page["events"][0]["source_position"] == "5:5"
