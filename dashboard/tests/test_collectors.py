import threading
import time
from pathlib import Path

from qfw_slurm_dashboard.collectors import (
    collect_all,
    docker_status,
    LiveCollectorSet,
    reconcile_qpm_registration,
    service_health_summary,
    service_plane_status,
    slurm_status,
)
from qfw_slurm_dashboard.models import SourceState, utc_now
from qfw_slurm_dashboard.runner import CommandResult


class FakeRunner:
    def host(self, argv, timeout=None):
        return CommandResult(tuple(argv), 0, '{"State":"running","Name":"c1"}\n', "")

    def cluster(self, identity, argv, **kwargs):
        command = argv[0]
        if command == "bash":
            command = "qfw-sinfo" if "qfw-sinfo" in argv[-1] else "qfw-squeue"
        if command == "sinfo":
            return CommandResult(tuple(argv), 0, "c1|normal|idle||4|1024|compute\n", "")
        if command == "squeue":
            return CommandResult(tuple(argv), 0, '{"jobs": []}\n', "")
        if command == "scontrol":
            return CommandResult(tuple(argv), 0, "Slurmctld(primary) at UP\n", "")
        if command == "sacctmgr":
            return CommandResult(tuple(argv), 0, "linux|\n", "")
        if command == "qfw-sinfo":
            return CommandResult(tuple(argv), 1, "", "not running")
        if command == "qfw-squeue":
            return CommandResult(
                tuple(argv), 0,
                '{"schema":"qfw-squeue-v1","errors":[],"jobs":[]}\n', ""
            )
        if command == "qfw-site-services":
            return CommandResult(
                tuple(argv), 0,
                '{"schema":"qfw-site-services-status-v1","state":"down",'
                '"services":{'
                '"directory":{"state":"down","detail":{"state":"stopped"}},'
                '"nwqsim":{"state":"down","detail":{"state":"stopped"}},'
                '"iqm":{"state":"down","detail":{"state":"stopped"}},'
                '"shim":{"state":"down","detail":{"state":"stopped"}},'
                '"fake-iqm":{"state":"down","detail":{"state":"stopped"}},'
                '"gateway":{"state":"down","detail":{"state":"stopped"}}}}\n',
                "",
            )
        raise AssertionError(command)


def test_collectors_keep_partial_state_when_service_is_stopped() -> None:
    sources = {item.name: item for item in collect_all(FakeRunner())}
    assert sources["docker"].status == "ready"
    assert next(
        item for item in sources["slurm"].records if item["kind"] == "node"
    )["node"] == "c1"
    assert sources["services"].status == "stopped"
    assert sources["allocations"].status == "ready"
    assert sources["service-plane"].status == "stopped"


def test_malformed_docker_output_is_typed_unavailable() -> None:
    runner = FakeRunner()
    runner.host = lambda argv, timeout=None: CommandResult(tuple(argv), 0, "{", "")
    assert docker_status(runner).status == "unavailable"


def test_collector_exception_does_not_hide_healthy_sources() -> None:
    runner = FakeRunner()
    original = runner.host
    runner.host = lambda argv, timeout=None: (_ for _ in ()).throw(
        RuntimeError("docker unavailable")
    ) if argv[0] == "docker" else original(argv, timeout)
    sources = {item.name: item for item in collect_all(runner)}
    assert sources["docker"].status == "unavailable"
    assert sources["slurm"].status == "ready"


def test_live_collectors_publish_each_source_without_blocking() -> None:
    release = threading.Event()

    def slow_status(_runner):
        release.wait(1)
        return SourceState("slow", "ready", utc_now(), [{"value": "live"}])

    collectors = LiveCollectorSet(
        FakeRunner(), collectors=(slow_status,), refresh_interval=60
    )
    started = time.monotonic()
    assert collectors.snapshot()[0].status == "loading"
    assert time.monotonic() - started < 0.1
    release.set()
    for _ in range(100):
        result = collectors.snapshot()[0]
        if result.status == "ready":
            break
        time.sleep(0.01)
    assert result.records == [{"value": "live"}]


def test_slurm_jobs_include_names_for_topology_activity() -> None:
    class JobRunner(FakeRunner):
        def cluster(self, identity, argv, **kwargs):
            if argv[0] == "squeue":
                return CommandResult(
                    tuple(argv), 0,
                    '{"jobs":[{'
                    '"job_id":42,"user_name":"user-a",'
                    '"job_state":["RUNNING"],"partition":"normal",'
                    '"nodes":"c1","name":"qfw-qiskit-simple",'
                    '"state_reason":"None","state_description":""}]}\n',
                    "",
                )
            return super().cluster(identity, argv, **kwargs)

    source = slurm_status(JobRunner())
    job = next(item for item in source.records if item["kind"] == "job")
    assert job["job_name"] == "qfw-qiskit-simple"
    assert job["nodes"] == "c1"


def test_slurm_multiline_pending_reason_is_one_job_record() -> None:
    class PendingRunner(FakeRunner):
        def cluster(self, identity, argv, **kwargs):
            if argv[0] == "squeue":
                return CommandResult(
                    tuple(argv), 0,
                    '{"jobs":[{'
                    '"job_id":36,"het_job_id":{"set":true,"number":35},'
                    '"het_job_offset":{"set":true,"number":1},'
                    '"user_name":"user-a","job_state":["PENDING"],'
                    '"partition":"normal","nodes":"",'
                    '"name":"qfw-qiskit-simple",'
                    '"state_reason":"BurstBufferOperation",'
                    '"state_description":"first line\\ntraceback line"}]}\n',
                    "",
                )
            return super().cluster(identity, argv, **kwargs)

    jobs = [
        item for item in slurm_status(PendingRunner()).records
        if item["kind"] == "job"
    ]
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == "35+1"
    assert jobs[0]["reason"] == "first line\ntraceback line"


def test_service_plane_reports_each_component_independently() -> None:
    class PartialServiceRunner:
        def cluster(self, identity, argv, **kwargs):
            assert argv == ("qfw-site-services", "status", "--json")
            output = """{
  "schema":"qfw-site-services-status-v1",
  "state":"down",
  "services":{
    "directory":{"state":"down","detail":{"components":{"directory":{"node":"slurmctld","ready":false,"state":"stopped"}}}},
    "nwqsim":{"state":"up","detail":{"components":{"prte-dvm":{"node":"nwqsim-head","ready":true,"state":"ready"},"qpm:nwqsim":{"node":"nwqsim-head","ready":true,"state":"ready"}}}},
    "iqm":{"state":"up","detail":{"components":{"qpm:iqm-ornl-20q":{"node":"iqm-head","ready":true,"state":"ready"}}}},
    "shim":{"state":"up","detail":{"components":{"qpm:shim-ornl-20q":{"node":"shim-head","ready":true,"state":"ready"}}}},
    "ibm":{"state":"up","detail":{"components":{"qpm:shim-ibm-156-nh":{"node":"ibm-156-nh","ready":true,"state":"ready"}}}},
    "aws":{"state":"up","detail":{"components":{"qpm:shim-aws-qpm":{"node":"aws","ready":true,"state":"ready"}}}},
    "fake-iqm":{"state":"up","detail":{"components":{"qpm:fake-iqm":{"node":"fake-iqm-head","ready":true,"state":"ready"}}}},
    "gateway":{"state":"up","detail":{"state":"ready"}}
  }
}
"""
            return CommandResult(tuple(argv), 0, output, "")

    source = service_plane_status(PartialServiceRunner())
    records = {item["component"]: item for item in source.records}
    assert source.status == "degraded"
    assert records["directory"]["state"] == "stopped"
    assert records["nwqsim"]["state"] == "ready"
    assert records["dvm"]["state"] == "ready"
    assert records["iqm"]["state"] == "ready"
    assert records["shim"]["state"] == "ready"
    assert records["ibm"]["state"] == "ready"
    assert records["ibm"]["service_id"] == "shim-ibm-156-nh"
    assert records["ibm"]["node"] == "ibm-156-nh"
    assert records["aws"]["state"] == "ready"
    assert records["aws"]["service_id"] == "shim-aws-qpm"
    assert records["aws"]["node"] == "aws"
    assert records["fake-iqm"]["state"] == "ready"
    assert records["gateway"]["state"] == "ready"


def test_qpm_processes_are_down_when_directory_registration_is_missing() -> None:
    managed = SourceState("service-plane", "ready", utc_now(), [
        {
            "component": "nwqsim",
            "service_id": "nwqsim",
            "state": "ready",
        },
        {
            "component": "iqm",
            "service_id": "iqm-ornl-20q",
            "state": "ready",
        },
    ])
    catalog = SourceState("services", "ready", utc_now(), [
        {
            "service_id": "nwqsim",
            "state": "DOWN",
            "runtime_id": "",
            "generation": 0,
        },
        {
            "service_id": "iqm-ornl-20q",
            "state": "DOWN",
            "runtime_id": "",
            "generation": 0,
        },
    ])

    sources = reconcile_qpm_registration([managed, catalog])
    service_plane = next(
        source for source in sources if source.name == "service-plane")

    assert service_plane.status == "stopped"
    assert {record["component"] for record in service_plane.records} == {
        "nwqsim", "iqm",
    }
    for record in service_plane.records:
        assert record["state"] == "stopped"
        assert record["process_state"] == "ready"
        assert record["registered"] is False
        assert record["registration_state"] == "DOWN"


def test_service_health_summary_reports_unregistered_live_qpm() -> None:
    class HealthRunner:
        def cluster(self, identity, argv, **kwargs):
            if argv[0] == "qfw-site-services":
                return CommandResult(tuple(argv), 0, """{
  "services": {
    "directory": {"state": "up", "detail": {"components": {"directory": {"node": "slurmctld", "ready": true, "state": "ready"}}}},
    "nwqsim": {"state": "down", "detail": {}},
    "iqm": {"state": "up", "detail": {"components": {"qpm:iqm-ornl-20q": {"node": "iqm-head", "ready": true, "state": "ready"}}}},
    "gateway": {"state": "up", "detail": {"state": "ready"}}
  }
}\n""", "")
            return CommandResult(tuple(argv), 0, (
                '{"services":[{"service_id":"iqm-ornl-20q",'
                '"state":"DOWN","runtime_id":"","generation":0}],'
                '"errors":[]}\n'), "")

    lines = service_health_summary(HealthRunner(), "iqm")

    assert lines == [
        "IQM: DOWN",
        "",
        "IQM: DOWN (process ready; not registered)",
    ]


def test_idle_catalog_record_confirms_qpm_registration() -> None:
    managed = SourceState("service-plane", "ready", utc_now(), [{
        "component": "nwqsim",
        "service_id": "nwqsim",
        "state": "ready",
    }])
    catalog = SourceState("services", "ready", utc_now(), [{
        "service_id": "nwqsim",
        "state": "IDLE",
        "runtime_id": "runtime-1",
        "generation": 1,
    }])

    sources = reconcile_qpm_registration([managed, catalog])
    service_plane = next(
        source for source in sources if source.name == "service-plane")

    assert service_plane.status == "ready"
    assert service_plane.records[0]["state"] == "ready"
    assert service_plane.records[0]["registered"] is True
