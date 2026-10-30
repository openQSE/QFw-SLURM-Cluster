"""Execute the exact managed-QFw pytest gate inside a Slurm step."""

import json
import os
from pathlib import Path

from libquantum_compiler_qiskit import plugin_path
import pytest


qfw_base = Path(os.environ.get(
    "QFW_BASE", "/workspace/qfw-container-base"))
cluster_source = Path(os.environ.get(
    "QFW_CLUSTER_SOURCE",
    qfw_base / "QFw-release-v0.1/repos-main-sync/QFw-SLURM-Cluster",
))
libquantum_source = Path(os.environ.get(
    "LIBQUANTUM_SOURCE", qfw_base / "libquantum"))
prior_pythonpath = os.environ.get("PYTHONPATH", "")
os.environ.update({
    "LIBQUANTUM_QFW_INTEGRATION": "1",
    "QFW_ALLOCATION_ID": os.environ["SLURM_JOB_ID"],
    "LIBQUANTUM_COMPILER_PATHS": str(plugin_path()),
    "LIBQUANTUM_INTEGRATION_FACTORY": (
        "libquantum_qfw_integration_factory:create_case"),
    "LIBQUANTUM_QFW_COMPONENT_REVISIONS": json.dumps({
        "QFw": "91be0828ea91",
        "DEFw": "87b8090cd30b",
        "qfw-slurm": "e940e0a60022",
        "compiler": "b1d19e927803",
    }),
    "LIBQUANTUM_QFW_EVIDENCE_KIND": "simulator",
    "PYTHONPATH": os.pathsep.join((
        str(cluster_source / "shared-dir"),
        prior_pythonpath,
    )),
})
os.chdir("/tmp")
raise SystemExit(pytest.main([
    "-q",
    "-m",
    "qfw_integration",
    str(libquantum_source /
        "tests/phase_tests/test_phase_12_qfw_integration.py"),
]))
