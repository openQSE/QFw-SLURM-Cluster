import base64
import io
import json
import shlex
from pathlib import Path
from unittest.mock import patch
import zipfile

import pytest

from qfw_slurm_dashboard.runner import CommandResult
from qfw_slurm_dashboard.routes import _error
from qfw_slurm_dashboard.service import (
    DashboardService,
    SubmissionSetValidationError,
)
from qfw_slurm_dashboard.models import Experiment, Operation


class ImmediateThread:
    def __init__(self, target, args, **kwargs):
        self.target = target
        self.args = args

    def start(self):
        self.target(*self.args)


class DeferredThread:
    started = []

    def __init__(self, target, args, **kwargs):
        self.target = target
        self.args = args

    def start(self):
        self.started.append(self.args[0].experiment_id)

    @staticmethod
    def is_alive():
        return True


def service(tmp_path) -> DashboardService:
    return DashboardService(Path("."), tmp_path)


def written_batch_script(cluster) -> str:
    write_call = next(
        call for call in cluster.call_args_list
        if call.args[1][0:2] == ("python3", "-c")
        and str(call.args[1][-2]).endswith("/job.sbatch")
    )
    return base64.b64decode(write_call.args[1][-1]).decode("utf-8")


def written_script_for_path(cluster, path: str) -> str:
    write_call = next(
        call for call in cluster.call_args_list
        if call.args[1][0:2] == ("python3", "-c")
        and str(call.args[1][-3]) == path
    )
    return base64.b64decode(write_call.args[1][-2]).decode("utf-8")


def test_host_action_requires_root(tmp_path) -> None:
    with pytest.raises(PermissionError, match="root"):
        service(tmp_path).submit_action("cluster-start", "user-a")


def test_dashboard_reset_requires_root(tmp_path) -> None:
    with pytest.raises(PermissionError, match="root"):
        service(tmp_path).clear_dashboard_state("user-a")


def test_dashboard_reset_clears_stale_history_and_memory_caches(tmp_path) -> None:
    dashboard = service(tmp_path)
    dashboard.store.save_operation(Operation("op", "test", "root", "cluster"))
    experiment = Experiment(
        "exp", "user-a", "nwqsim", "qiskit-simple", "normal"
    )
    experiment.slurm_job_id = "42"
    dashboard.store.save_experiment(experiment)
    dashboard.store.append_event({"kind": "log", "message": "old"})
    dashboard._state_cache = {"stale": True}
    dashboard._state_cached_at = 10
    dashboard._examples_cache = [{"stale": True}]
    with patch.object(dashboard.runner, "cluster") as cluster:
        cluster.return_value = CommandResult(("squeue",), 0, "", "")
        result = dashboard.clear_dashboard_state("root")

    assert result["outcome"] == "success"
    assert result["cleared"] == {
        "operations": 1, "experiments": 1, "events": 1,
    }
    assert dashboard.store.operations() == []
    assert dashboard.store.experiments() == []
    assert dashboard._state_cache is None
    assert dashboard._state_cached_at == 0
    assert dashboard._examples_cache is None


def test_dashboard_reset_rejects_a_tracked_live_slurm_job(tmp_path) -> None:
    dashboard = service(tmp_path)
    experiment = Experiment(
        "exp", "user-a", "nwqsim", "qiskit-simple", "normal"
    )
    experiment.slurm_job_id = "42"
    dashboard.store.save_experiment(experiment)
    with patch.object(dashboard.runner, "cluster") as cluster:
        cluster.return_value = CommandResult(("squeue",), 0, "42+0\n", "")
        with pytest.raises(RuntimeError, match="tracked Slurm jobs"):
            dashboard.clear_dashboard_state("root")

    assert dashboard.store.experiments()[0]["experiment_id"] == "exp"


def test_clear_experiment_results_removes_only_historical_records(tmp_path) -> None:
    dashboard = service(tmp_path)
    old = Experiment("old", "user-a", "nwqsim", "qiskit-simple", "normal")
    old.slurm_job_id = "10"
    active = Experiment("active", "user-a", "nwqsim", "qiskit-simple", "normal")
    active.slurm_job_id = "42"
    other = Experiment("other", "user-b", "nwqsim", "qiskit-simple", "normal")
    dashboard.store.save_experiment(old)
    dashboard.store.save_experiment(active)
    dashboard.store.save_experiment(other)
    dashboard._state_cache = {"stale": True}
    dashboard._state_cached_at = 10

    with patch.object(dashboard.runner, "cluster") as cluster:
        cluster.return_value = CommandResult(("squeue",), 0, "42\n", "")
        result = dashboard.clear_experiment_results("root")

    assert result["cleared"] == {"experiments": 2}
    assert [item["experiment_id"] for item in dashboard.store.experiments()] == [
        "active"
    ]
    assert dashboard._state_cache is None
    assert dashboard._state_cached_at == 0


def test_clear_experiment_results_is_scoped_to_identity(tmp_path) -> None:
    dashboard = service(tmp_path)
    dashboard.store.save_experiment(
        Experiment("mine", "user-a", "nwqsim", "qiskit-simple", "normal")
    )
    dashboard.store.save_experiment(
        Experiment("other", "user-b", "nwqsim", "qiskit-simple", "normal")
    )

    result = dashboard.clear_experiment_results("user-a")

    assert result["cleared"] == {"experiments": 1}
    assert [item["experiment_id"] for item in dashboard.store.experiments()] == [
        "other"
    ]


def test_clear_experiment_results_rejects_unknown_identity(tmp_path) -> None:
    with pytest.raises(ValueError, match="unsupported identity"):
        service(tmp_path).clear_experiment_results("nobody")


@pytest.mark.parametrize(
    ("action", "expected"),
    (
        ("cluster-status", ("./do_ls.sh",)),
        (
            "cluster-synchronize",
            (
                "/bin/bash", "-lc",
                "git pull --ff-only && git submodule sync --recursive "
                "&& git submodule update --init --recursive",
            ),
        ),
        (
            "cluster-rebuild-incremental",
            (
                "/bin/bash", "-lc",
                "./do_build.sh && ./do_stop.sh && ./do_startup.sh",
            ),
        ),
        (
            "cluster-rebuild-clean",
            (
                "/bin/bash", "-lc",
                "./do_build.sh --no-cache && ./do_stop.sh && ./do_startup.sh",
            ),
        ),
    ),
)
def test_cluster_management_actions(tmp_path, action, expected) -> None:
    dashboard = service(tmp_path)
    with patch("qfw_slurm_dashboard.service.threading.Thread", ImmediateThread):
        with patch.object(dashboard.runner, "stream_host") as host:
            host.return_value = CommandResult(expected, 0, "ok", "")
            operation = dashboard.submit_action(action, "root")
    assert host.call_args.args[0] == expected
    assert operation.status == "succeeded"


def test_action_is_idempotent_by_request_id(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch("qfw_slurm_dashboard.service.threading.Thread", ImmediateThread):
        with patch.object(dashboard.runner, "stream_host") as host:
            host.return_value = CommandResult(("./do_startup.sh",), 0, "ready", "")
            first = dashboard.submit_action(
                "cluster-start", "root", request_id="same-request"
            )
            second = dashboard.submit_action(
                "cluster-start", "root", request_id="same-request"
            )
    assert first.operation_id == second.operation_id
    assert host.call_count == 1


def test_cluster_action_dry_run_records_command_without_streaming(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch.object(dashboard.runner, "stream_host") as host:
        operation = dashboard.submit_action(
            "cluster-start", "root", dry_run=True
        )
    host.assert_not_called()
    assert operation.dry_run is True
    assert operation.status == "succeeded"
    assert operation.return_code == 0
    output = "\n".join(operation.output)
    assert "DRY RUN - command was not executed" in output
    assert "./do_startup.sh" in output
    assert "./do_startup.sh --dry-run" in output


def test_service_action_dry_run_keeps_logging_env_without_streaming(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch.object(dashboard.runner, "stream_host") as host:
        operation = dashboard.submit_action(
            "service-restart",
            "root",
            target="nwqsim",
            options={
                "defw_log_level": "all",
                "defw_py_loglevel": "DEFW_ALL",
            },
            dry_run=True,
        )
    host.assert_not_called()
    assert operation.dry_run is True
    output = "\n".join(operation.output)
    assert "QFW_SERVICE_DEFW_LOG_LEVEL=all" in output
    assert "QFW_SERVICE_DEFW_PY_LOGLEVEL=DEFW_ALL" in output
    assert "qfw-site-services restart --target nwqsim" in output
    assert "qfw-site-services --dry-run restart --target nwqsim" in output


def test_node_action_dry_run_records_scontrol_without_streaming(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch.object(dashboard.runner, "stream_host") as host:
        operation = dashboard.submit_action(
            "node-drain",
            "root",
            target="compute-1",
            reason="maintenance",
            dry_run=True,
        )
    host.assert_not_called()
    assert operation.dry_run is True
    output = "\n".join(operation.output)
    assert "scontrol update NodeName=compute-1 State=DRAIN Reason=maintenance" in output


def test_packaged_application_catalog_includes_supported_examples(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch.object(dashboard.runner, "cluster") as cluster:
        cluster.return_value = CommandResult(("test",), 0, "", "")
        names = {record["name"] for record in dashboard.examples()}
    assert names == {
        "init-test", "qiskit-simple", "ghz-qiskit", "ghz-pennylane",
        "pennylane", "qaoa", "qiskit-vqe", "supermarq", "chemistry",
    }


def test_packaged_application_catalog_describes_runtime_parameters(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch.object(dashboard.runner, "cluster") as cluster:
        cluster.return_value = CommandResult(("test",), 0, "", "")
        examples = {record["name"]: record for record in dashboard.examples()}
    assert [item["name"] for item in examples["ghz-qiskit"]["parameters"]] == [
        "qubits", "iterations",
    ]
    assert examples["qaoa"]["parameters"] == []


def test_running_experiments_are_derived_from_live_slurm_jobs(tmp_path) -> None:
    dashboard = service(tmp_path)
    experiments = [
        {"experiment_id": "stale", "status": "submitting", "slurm_job_id": ""},
        {"experiment_id": "live", "status": "running", "slurm_job_id": "42"},
        {"experiment_id": "old", "status": "submitted", "slurm_job_id": "41"},
    ]
    slurm_records = [
        {"kind": "job", "job_id": "42+1", "state": "RUNNING"},
        {"kind": "node", "node": "c1", "state": "allocated"},
    ]
    assert dashboard._running_experiments(experiments, slurm_records) == [
        experiments[1]
    ]


def test_running_experiments_include_active_submission_thread(tmp_path) -> None:
    dashboard = service(tmp_path)

    class LiveThread:
        @staticmethod
        def is_alive() -> bool:
            return True

    dashboard._threads["submitting"] = LiveThread()
    experiment = {
        "experiment_id": "submitting", "status": "submitting", "slurm_job_id": "",
    }
    assert dashboard._running_experiments([experiment], []) == [experiment]


@pytest.mark.parametrize("backend", ("iqm", "ibm"))
def test_hardware_submission_requires_confirmation(tmp_path, backend) -> None:
    with pytest.raises(PermissionError, match="confirmation"):
        service(tmp_path).submit_experiment({
            "identity": "user-a",
            "backend": backend,
            "example": "qiskit-simple",
        })


def test_preview_covers_heterogeneous_quantum_request(tmp_path) -> None:
    experiment_id = "7cb57000-724f-4db5-bc9b-b9e357525a08"
    preview = service(tmp_path).command_preview({
        "experiment_id": experiment_id,
        "identity": "user-c",
        "backend": "nwqsim",
        "allocation_mode": "heterogeneous",
        "nodes": 2,
        "circ_count": 3,
        "max_qubits": 8,
        "max_depth": 200,
        "shots": 64,
        "tasks": 4,
        "service_nodes": 1,
        "service_tasks": 1,
        "partition": "",
        "account": "science",
        "qos": "debug",
        "tasks_per_node": 2,
        "cpus_per_task": 4,
        "memory": "8G",
        "memory_scope": "node",
        "gpus": 1,
        "gpus_scope": "task",
        "constraint": "zen4&gpu",
        "exclusive": True,
    })
    assert "--qpu=nwqsim" in preview
    assert "--circ-count=3" in preview
    assert "--max-shots=64" in preview
    assert "--max-one-q-gates" not in preview
    assert "#SBATCH --account=science" in preview
    assert "#SBATCH --qos=debug" in preview
    assert "#SBATCH --nodes=2" in preview
    assert "#SBATCH hetjob" in preview
    assert "#SBATCH --partition=normal" in preview
    assert "#SBATCH --ntasks=4" in preview
    assert "#SBATCH --ntasks-per-node=2" in preview
    assert "#SBATCH --cpus-per-task=4" in preview
    assert "#SBATCH --mem=8G" in preview
    assert "#SBATCH --gpus-per-task=1" in preview
    assert "#SBATCH --constraint=zen4&gpu" in preview
    assert "--exclusive" in preview
    application_group, service_group = preview.split("#SBATCH hetjob", 1)
    assert "#SBATCH --qpu=nwqsim" in application_group
    assert "#SBATCH --nodes=2" in application_group
    assert "#SBATCH --ntasks=4" in application_group
    assert "#SBATCH --ntasks-per-node=2" in application_group
    assert "#SBATCH --nodes=1" in service_group
    assert "#SBATCH --ntasks=1" in service_group
    assert "#SBATCH --qpu=" not in service_group
    assert "#SBATCH --ntasks-per-node=" not in service_group
    assert "QFW_RUN_ALL_TESTS=qiskit-simple" in preview
    assert "source /opt/openqse/qfw/bin/qfw-activate" in preview
    assert preview.startswith("# Generated batch file:")
    assert f"/experiments/{experiment_id}/job.sbatch" in preview
    assert "<experiment-id>" not in preview


def test_allocation_mode_cannot_be_used_as_slurm_partition(tmp_path) -> None:
    with pytest.raises(ValueError, match="allocation mode, not a Slurm partition"):
        service(tmp_path).command_preview({
            "identity": "user-a",
            "backend": "nwqsim",
            "allocation_mode": "heterogeneous",
            "partition": "heterogeneous",
        })


def test_service_partition_cannot_be_used_for_application(tmp_path) -> None:
    with pytest.raises(ValueError, match="reserved for site-owned services"):
        service(tmp_path).command_preview({
            "identity": "root",
            "backend": "nwqsim",
            "partition": "qfw-services",
        })


def test_backend_catalog_drives_batch_script_qpu_and_provider(tmp_path) -> None:
    shim_preview = service(tmp_path).command_preview({
        "identity": "user-a",
        "backend": "shim",
        "submit_real_hardware": True,
    })
    assert "#SBATCH --qpu=ornl-shim-20q" in shim_preview
    assert "--backend shim" in shim_preview

    fake_iqm_preview = service(tmp_path).command_preview({
        "identity": "user-a",
        "backend": "fake-iqm",
    })
    assert "#SBATCH --qpu=fake-iqm-20q" in fake_iqm_preview
    assert "--backend fake-iqm" in fake_iqm_preview

    ibm_preview = service(tmp_path).command_preview({
        "identity": "user-a",
        "backend": "ibm",
        "submit_real_hardware": True,
    })
    assert "#SBATCH --qpu=ibm-156-nh" in ibm_preview
    assert "--backend ibm" in ibm_preview


def test_submission_writes_and_submits_batch_file(tmp_path) -> None:
    dashboard = service(tmp_path)
    experiment_id = "c0a4a796-756d-45e7-9f31-ef933af72aa1"
    with patch("qfw_slurm_dashboard.service.threading.Thread", ImmediateThread):
        with patch.object(dashboard.runner, "cluster") as cluster:
            cluster.return_value = CommandResult(("sbatch",), 0, "42\n", "")
            experiment = dashboard.submit_experiment({
                "experiment_id": experiment_id,
                "identity": "user-a",
                "backend": "nwqsim",
                "example": "qiskit-simple",
            })
    argv = cluster.call_args.args[1]
    batch = written_batch_script(cluster)
    assert argv[:2] == ("sbatch", "--parsable")
    assert argv[-1].endswith(f"/{experiment_id}/job.sbatch")
    assert "--wrap" not in " ".join(argv)
    assert 'cd "${QFW_SHARE_DIR}/examples"' in batch
    assert "#SBATCH --qpu=nwqsim" in batch
    assert "export DEFW_LOG_LEVEL=error" in batch
    assert "export DEFW_PY_LOGLEVEL=critical" in batch
    archive_dir = (
        "/workspace/home/user-a/qfw-dashboard/experiments/"
        f"{experiment_id}/defw-logs"
    )
    assert f"QFW_EXAMPLE_LOG_ARCHIVE_DIR={archive_dir}" in batch
    assert experiment.manifest["batch_script_path"] == argv[-1]
    assert experiment.artifacts[-1] == argv[-1]
    assert experiment.slurm_job_id == "42"


def test_submission_set_starts_each_validated_experiment(tmp_path) -> None:
    dashboard = service(tmp_path)
    first_id = "2440c16e-865b-4a67-834e-dda390a67f32"
    second_id = "f23bf181-f679-4a18-ae19-b880826ffaba"
    DeferredThread.started = []
    with patch("qfw_slurm_dashboard.service.threading.Thread", DeferredThread):
        experiments = dashboard.submit_experiment_batch({
            "identity": "user-a",
            "experiments": [
                {
                    "experiment_id": first_id,
                    "backend": "nwqsim",
                    "example": "qiskit-simple",
                },
                {
                    "experiment_id": second_id,
                    "backend": "nwqsim",
                    "example": "ghz-qiskit",
                },
            ],
        })

    assert [item.experiment_id for item in experiments] == [first_id, second_id]
    assert DeferredThread.started == [first_id, second_id]
    assert {
        item["experiment_id"] for item in dashboard.store.experiments()
    } == {first_id, second_id}


def test_submission_set_dry_run_reports_commands_without_running(tmp_path) -> None:
    dashboard = service(tmp_path)
    experiment_id = "2440c16e-865b-4a67-834e-dda390a67f32"

    with patch.object(dashboard.runner, "cluster") as cluster:
        result = dashboard.dry_run_experiment_batch({
            "identity": "user-a",
            "experiments": [{
                "experiment_id": experiment_id,
                "backend": "nwqsim",
                "example": "qiskit-simple",
            }],
        })

    cluster.assert_not_called()
    assert result["outcome"] == "dry-run"
    assert dashboard.store.experiments() == []
    entry = result["experiments"][0]
    assert entry["experiment_id"] == experiment_id
    assert entry["submit_command"] == (
        "sbatch --parsable "
        f"/workspace/home/user-a/qfw-dashboard/experiments/{experiment_id}/job.sbatch"
    )
    assert "docker exec --user user-a" in entry["submit_host_command"]
    assert "timeout --signal=TERM --kill-after=2 30" in entry["submit_host_command"]
    assert entry["write_command"].startswith("python3 -c ")
    assert "docker exec --user user-a" in entry["write_host_command"]
    write_argv = shlex.split(entry["write_command"])
    assert base64.b64decode(write_argv[-1]).decode("utf-8") == entry["batch_script"]
    assert "#SBATCH --qpu=nwqsim" in entry["batch_script"]
    assert "qfw_run_all.sh --service-mode site --backend nwqsim" in entry["batch_script"]


def test_submission_set_dry_run_external_sbatch_skips_batch_write(tmp_path) -> None:
    dashboard = service(tmp_path)

    with patch.object(dashboard.runner, "cluster") as cluster:
        result = dashboard.dry_run_experiment_batch({
            "identity": "user-a",
            "experiments": [{
                "experiment_id": "f23bf181-f679-4a18-ae19-b880826ffaba",
                "backend": "nwqsim",
                "application_source": "path",
                "application_submission_type": "sbatch",
                "application_path": "/workspace/home/user-a/manual.sbatch",
            }],
        })

    cluster.assert_not_called()
    entry = result["experiments"][0]
    assert entry["external_batch"] is True
    assert entry["batch_script"] == ""
    assert entry["write_command"] == ""
    assert entry["write_host_command"] == ""
    assert entry["submit_command"] == (
        "sbatch --parsable /workspace/home/user-a/manual.sbatch"
    )


def test_submission_records_reusable_submission_entry_identity(tmp_path) -> None:
    dashboard = service(tmp_path)
    entry_id = "0e52826c-d58d-42bc-9c4d-bf6062d78614"
    with patch("qfw_slurm_dashboard.service.threading.Thread", DeferredThread):
        experiment = dashboard.submit_experiment({
            "experiment_id": "1e6d5bad-69ca-45a7-91dd-a42c4ba7a14f",
            "submission_entry_id": entry_id,
            "identity": "user-a",
            "backend": "nwqsim",
            "example": "ghz-qiskit",
        })

    assert experiment.manifest["submission_entry_id"] == entry_id


def test_submission_entry_can_create_repeated_same_example_executions(
    tmp_path,
) -> None:
    dashboard = service(tmp_path)
    entry_id = "0e52826c-d58d-42bc-9c4d-bf6062d78614"
    first_id = "1e6d5bad-69ca-45a7-91dd-a42c4ba7a14f"
    second_id = "2de5896f-63db-40d7-903e-3d67fd81b588"
    DeferredThread.started = []
    with patch("qfw_slurm_dashboard.service.threading.Thread", DeferredThread):
        for experiment_id in (first_id, second_id):
            dashboard.submit_experiment({
                "experiment_id": experiment_id,
                "submission_entry_id": entry_id,
                "identity": "user-a",
                "backend": "nwqsim",
                "example": "ghz-qiskit",
                "application_parameters": {"qubits": 4, "iterations": 1},
            })

    records = dashboard.store.experiments()
    assert {item["experiment_id"] for item in records} == {first_id, second_id}
    assert {
        item["manifest"]["submission_entry_id"] for item in records
    } == {entry_id}
    assert DeferredThread.started == [first_id, second_id]


def test_submission_set_validates_every_entry_before_starting_any(tmp_path) -> None:
    dashboard = service(tmp_path)
    DeferredThread.started = []
    with patch("qfw_slurm_dashboard.service.threading.Thread", DeferredThread):
        with pytest.raises(
            SubmissionSetValidationError, match="iterations"
        ) as captured:
            dashboard.submit_experiment_batch({
                "identity": "user-a",
                "experiments": [
                    {
                        "experiment_id": "9cd164b7-c453-42a9-8930-ef7521d2d882",
                        "backend": "nwqsim",
                        "example": "qiskit-simple",
                    },
                    {
                        "experiment_id": "bce23286-cf07-483c-a85d-63cfa5b3a1da",
                        "backend": "nwqsim",
                        "example": "ghz-qiskit",
                        "application_parameters": {
                            "qubits": 4,
                            "iterations": 0,
                        },
                    },
                    {
                        "experiment_id": "6326bd8f-58a4-4244-a99e-ee70d68671e2",
                        "backend": "nwqsim",
                        "example": "supermarq",
                    },
                ],
            })

    assert captured.value.index == 1
    assert captured.value.experiment_id == (
        "bce23286-cf07-483c-a85d-63cfa5b3a1da"
    )
    assert DeferredThread.started == []
    assert dashboard.store.experiments() == []


def test_submission_set_error_response_identifies_invalid_entry() -> None:
    response = _error(SubmissionSetValidationError(
        2,
        "bce23286-cf07-483c-a85d-63cfa5b3a1da",
        "iterations outside permitted range",
    ))

    assert response.status == 400
    assert response.payload["error"]["submission"] == {
        "index": 2,
        "experiment_id": "bce23286-cf07-483c-a85d-63cfa5b3a1da",
    }


def test_submission_forwards_validated_application_parameters(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch("qfw_slurm_dashboard.service.threading.Thread", ImmediateThread):
        with patch.object(dashboard.runner, "cluster") as cluster:
            cluster.return_value = CommandResult(("sbatch",), 0, "42\n", "")
            experiment = dashboard.submit_experiment({
                "identity": "user-a",
                "backend": "nwqsim",
                "example": "ghz-qiskit",
                "circ_count": 3,
                "max_qubits": 8,
                "application_parameters": {"qubits": 7, "iterations": 3},
            })
    argv = cluster.call_args.args[1]
    batch = written_batch_script(cluster)
    assert argv[:2] == ("sbatch", "--parsable")
    assert "QFW_RUN_ALL_QUBITS=7" in batch
    assert "QFW_RUN_ALL_ITERS=3" in batch
    assert experiment.manifest["requirements"]["application_parameters"] == {
        "qubits": 7, "iterations": 3,
    }


def test_submission_forwards_logging_levels(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch("qfw_slurm_dashboard.service.threading.Thread", ImmediateThread):
        with patch.object(dashboard.runner, "cluster") as cluster:
            cluster.return_value = CommandResult(("sbatch",), 0, "42\n", "")
            dashboard.submit_experiment({
                "identity": "user-a",
                "backend": "nwqsim",
                "example": "qiskit-simple",
                "defw_log_level": "debug",
                "defw_py_loglevel": "DEFW_ALL",
            })
    batch = written_batch_script(cluster)
    assert "export DEFW_LOG_LEVEL=debug" in batch
    assert "export DEFW_PY_LOGLEVEL=DEFW_ALL" in batch


@pytest.mark.parametrize(
    "logging_options",
    (
        {"defw_log_level": "verbose"},
        {"defw_py_loglevel": "debug,DEFW_ALL"},
        {"defw_py_loglevel": "debug;rm"},
    ),
)
def test_submission_rejects_invalid_logging_levels(
    tmp_path, logging_options
) -> None:
    payload = {
        "identity": "user-a",
        "backend": "nwqsim",
        "example": "qiskit-simple",
        **logging_options,
    }
    with pytest.raises(ValueError, match="defw_"):
        service(tmp_path).submit_experiment(payload)


def test_submission_rejects_application_runtime_over_reservation_limit(tmp_path) -> None:
    with pytest.raises(ValueError, match="application qubits"):
        service(tmp_path).submit_experiment({
            "identity": "user-a",
            "backend": "nwqsim",
            "example": "qiskit-simple",
            "max_qubits": 4,
            "application_parameters": {"qubits": 5},
        })


def test_submission_rejects_unknown_application_parameter(tmp_path) -> None:
    with pytest.raises(ValueError, match="unsupported qaoa runtime parameter"):
        service(tmp_path).submit_experiment({
            "identity": "user-a",
            "backend": "nwqsim",
            "example": "qaoa",
            "application_parameters": {"iterations": 2},
        })


def test_refresh_accepts_structured_ok_terminal_record(tmp_path) -> None:
    dashboard = service(tmp_path)
    from qfw_slurm_dashboard.models import Experiment
    stored = Experiment("exp", "user-a", "nwqsim", "qiskit-simple", "normal")
    stored.slurm_job_id = "42"
    stored.artifacts = ["/workspace/home/user-a/output"]
    dashboard.store.save_experiment(stored)
    summary = {
        "schema": "qfw-example-wrapper-v1", "kind": "wrapper",
        "event": "finish", "status": "ok", "rc": 0, "teardown_rc": 0,
    }
    responses = iter((
        CommandResult(("sacct",), 0, "42|COMPLETED|0:0\n", ""),
        CommandResult(("tail",), 0, "Summary JSONL: /tmp/summary\n", ""),
        CommandResult(("cat",), 0, __import__("json").dumps(summary) + "\n", ""),
    ))
    with patch.object(dashboard.runner, "cluster", side_effect=lambda *a, **k: next(responses)):
        dashboard._refresh_experiments()
    assert dashboard.store.experiments()[0]["status"] == "succeeded"


def test_refresh_exposes_live_application_output(tmp_path) -> None:
    dashboard = service(tmp_path)
    from qfw_slurm_dashboard.models import Experiment
    stored = Experiment("exp", "user-a", "nwqsim", "qiskit-simple", "normal")
    stored.slurm_job_id = "42"
    stored.manifest["output_path"] = "/workspace/home/user-a/job.out"
    dashboard.store.save_experiment(stored)
    responses = iter((
        CommandResult(("sacct",), 0, "42|RUNNING|0:0|c1\n", ""),
        CommandResult(("tail",), 0, "application is running\n", ""),
    ))
    with patch.object(
        dashboard.runner, "cluster", side_effect=lambda *a, **k: next(responses)
    ):
        dashboard._refresh_experiments()
    refreshed = dashboard.store.experiments()[0]
    assert refreshed["status"] == "running"
    assert refreshed["result"]["output_tail"] == "application is running\n"


def test_individual_qpm_action_runs_on_service_node(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch("qfw_slurm_dashboard.service.threading.Thread", ImmediateThread):
        with patch.object(dashboard.runner, "stream_host") as host:
            host.return_value = CommandResult(("docker",), 0, "ready", "")
            operation = dashboard.submit_action(
                "service-start", "root", target="nwqsim"
            )
    argv = host.call_args.args[0]
    assert "slurmctld" in argv
    assert "qfw-site-services start --target nwqsim" in argv[-1]
    assert operation.status == "succeeded"


def test_ibm_service_action_uses_site_service_target(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch("qfw_slurm_dashboard.service.threading.Thread", ImmediateThread):
        with patch.object(dashboard.runner, "stream_host") as host:
            host.return_value = CommandResult(("docker",), 0, "ready", "")
            operation = dashboard.submit_action(
                "service-start", "root", target="ibm"
            )
    argv = host.call_args.args[0]
    assert "qfw-site-services start --target ibm" in argv[-1]
    assert operation.status == "succeeded"


def test_service_action_forwards_logging_levels(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch("qfw_slurm_dashboard.service.threading.Thread", ImmediateThread):
        with patch.object(dashboard.runner, "stream_host") as host:
            host.return_value = CommandResult(("docker",), 0, "ready", "")
            dashboard.submit_action(
                "service-restart",
                "root",
                target="nwqsim",
                options={
                    "defw_log_level": "all",
                    "defw_py_loglevel": "DEFW_ALL",
                },
            )
    command = host.call_args.args[0][-1]
    assert "QFW_SERVICE_DEFW_LOG_LEVEL=all" in command
    assert "QFW_SERVICE_DEFW_PY_LOGLEVEL=DEFW_ALL" in command
    assert "qfw-site-services restart --target nwqsim" in command


def test_service_status_returns_concise_health_output(tmp_path) -> None:
    dashboard = service(tmp_path)
    detail = "QFw site services: DOWN\n\nDirectory: DOWN\nNWQSim: STALE\n"

    def stream(command, on_line, **_kwargs):
        for line in detail.splitlines():
            on_line(line)
        return CommandResult(tuple(command), 0, detail, "")

    with patch("qfw_slurm_dashboard.service.threading.Thread", ImmediateThread), \
         patch("qfw_slurm_dashboard.service.service_health_summary") as summary, \
         patch.object(dashboard.runner, "stream_host") as host:
        host.side_effect = stream
        summary.return_value = [
            "QFw site services: DOWN", "", "IQM: DOWN",
        ]
        operation = dashboard.submit_action(
            "service-status", "root", target="all"
        )
    argv = host.call_args.args[0]
    assert "qfw-site-services status --target all" in argv[-1]
    assert operation.status == "succeeded"
    assert any("QFw site services: DOWN" in line for line in operation.output)
    summary.assert_called_once_with(dashboard.runner, "all")


def test_service_action_rejects_unknown_target(tmp_path) -> None:
    dashboard = service(tmp_path)
    with pytest.raises(ValueError, match="unsupported service target"):
        dashboard.submit_action("service-stop", "root", target="other")


def test_operation_abort_terminates_running_process_group(tmp_path) -> None:
    dashboard = service(tmp_path)
    operation = Operation("op", "service-start", "root", "all", status="running")
    dashboard.store.save_operation(operation)
    process = type("Process", (), {"pid": 42, "poll": lambda self: None})()
    dashboard._processes[operation.operation_id] = process
    with patch("qfw_slurm_dashboard.service.os.getpgid", return_value=84):
        with patch("qfw_slurm_dashboard.service.os.killpg") as killpg:
            result = dashboard.abort_operation(operation.operation_id, "root")
    killpg.assert_called_once()
    assert result.status == "aborting"


def test_regular_shell_target_must_be_allocated(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch.object(dashboard.runner, "cluster") as cluster:
        cluster.return_value = CommandResult(("squeue",), 0, "", "")
        with pytest.raises(PermissionError, match="not allocated"):
            dashboard.shell_context("user-a", "c1")
    assert dashboard.shell_context("user-a", "slurmctld")["home"] == (
        "/workspace/home/user-a"
    )


def test_regular_shell_cannot_target_service_node(tmp_path) -> None:
    with pytest.raises(PermissionError, match="service-node"):
        service(tmp_path).shell_context("user-a", "iqm-head")
    with pytest.raises(PermissionError, match="service-node"):
        service(tmp_path).shell_context("user-a", "shim-head")
    with pytest.raises(PermissionError, match="service-node"):
        service(tmp_path).shell_context("user-a", "fake-iqm-head")


def test_experiment_archive_contains_manifest_and_all_artifacts(tmp_path) -> None:
    from qfw_slurm_dashboard.models import Experiment
    dashboard = service(tmp_path)
    item = Experiment("result", "user-a", "nwqsim", "qiskit-simple", "normal")
    item.manifest["output_path"] = (
        "/workspace/home/user-a/qfw-dashboard/experiments/result/slurm.out"
    )
    item.artifacts = [
        "/workspace/home/user-a/job.out",
        "/workspace/home/user-a/job.sbatch",
        "/workspace/home/user-a/qfw-dashboard/experiments/result/"
        "defw-logs/application/logs/defw_py.log",
    ]
    dashboard.store.save_experiment(item)
    files = {
        "/workspace/home/user-a/job.out": b"application output\n",
        "/workspace/home/user-a/job.sbatch": b"#!/bin/bash\n",
        "/workspace/home/user-a/qfw-dashboard/experiments/result/"
        "defw-logs/application/logs/defw_py.log": b"defw app log\n",
    }
    with patch.object(dashboard.runner, "cluster") as cluster:
        def respond(identity, argv, **kwargs):
            if argv[0] == "find":
                return CommandResult(argv, 0, "\n".join(files) + "\n", "")
            return CommandResult(
                argv, 0, base64.b64encode(files[argv[-2]]).decode(), ""
            )
        cluster.side_effect = respond
        payload = dashboard.experiment_archive("result", "user-a")
    read_calls = [
        call for call in cluster.call_args_list
        if call.args[1][0:2] == ("python3", "-c")
    ]
    assert read_calls
    assert all(call.args[1][-1] == "" for call in read_calls)
    assert all(call.kwargs["timeout"] == 300 for call in read_calls)
    archive_data = base64.b64decode(payload["content_base64"])
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        assert sorted(archive.namelist()) == [
            "artifacts/00-job.out",
            "artifacts/01-job.sbatch",
            "experiment.json",
            "logs/application/logs/defw_py.log",
        ]
        manifest = json.loads(archive.read("experiment.json"))
        assert manifest["experiment_id"] == "result"
        assert archive.read("artifacts/00-job.out") == b"application output\n"
        assert archive.read("logs/application/logs/defw_py.log") == (
            b"defw app log\n"
        )
    assert payload["mime_type"] == "application/zip"
    with pytest.raises(PermissionError):
        dashboard.experiment_archive("result", "user-b")


def test_experiment_archive_rescans_defw_logs_on_download(tmp_path) -> None:
    dashboard = service(tmp_path)
    item = Experiment("result", "user-a", "nwqsim", "qiskit-simple", "normal")
    item.manifest["output_path"] = (
        "/workspace/home/user-a/qfw-dashboard/experiments/result/slurm.out"
    )
    item.artifacts = [
        "/workspace/home/user-a/qfw-dashboard/experiments/result/slurm.out",
    ]
    dashboard.store.save_experiment(item)
    log_root = (
        "/workspace/home/user-a/qfw-dashboard/experiments/result/defw-logs"
    )
    files = {
        "/workspace/home/user-a/qfw-dashboard/experiments/result/slurm.out":
        b"application output\n",
        f"{log_root}/application/logs/defw_py.log": b"python log\n",
        f"{log_root}/application/logs/defw_out.log": b"native log\n",
    }
    with patch.object(dashboard.runner, "cluster") as cluster:
        def respond(identity, argv, **kwargs):
            if argv[0] == "find":
                return CommandResult(argv, 0, "\n".join(files) + "\n", "")
            return CommandResult(
                argv, 0, base64.b64encode(files[argv[-2]]).decode(), ""
            )
        cluster.side_effect = respond
        payload = dashboard.experiment_archive("result", "user-a")
    archive_data = base64.b64decode(payload["content_base64"])
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        assert "logs/application/logs/defw_py.log" in archive.namelist()
        assert "logs/application/logs/defw_out.log" in archive.namelist()
        assert archive.read("logs/application/logs/defw_py.log") == (
            b"python log\n"
        )
        assert archive.read("logs/application/logs/defw_out.log") == (
            b"native log\n"
        )


def test_service_archive_is_root_only_and_contains_diagnostics(tmp_path) -> None:
    from qfw_slurm_dashboard.logs import SERVICE_DIAGNOSTICS
    dashboard = service(tmp_path)
    encoded = base64.b64encode(b"diagnostic api_key=secret\n").decode()
    with patch.object(dashboard.runner, "cluster") as cluster:
        cluster.return_value = CommandResult(("python3",), 0, encoded, "")
        payload = dashboard.service_archive("directory-service", "root")
    diagnostic_paths = {
        item.path for item in SERVICE_DIAGNOSTICS["directory-service"]
    }
    read_paths = {
        call.args[1][-2] for call in cluster.call_args_list
        if call.args[1][0:2] == ("python3", "-c")
        and call.args[1][-2] in diagnostic_paths
    }
    assert read_paths == diagnostic_paths
    read_calls = [
        call for call in cluster.call_args_list
        if call.args[1][0:2] == ("python3", "-c")
    ]
    assert read_calls
    assert all(call.args[1][-1] == "" for call in read_calls)
    assert all(call.kwargs["timeout"] == 300 for call in read_calls)
    archive_data = base64.b64decode(payload["content_base64"])
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        assert "service-status.json" in archive.namelist()
        assert "logs/defw_out.log" in archive.namelist()
        assert "logs/defw_py.log" in archive.namelist()
        assert "state/service-plane.json" in archive.namelist()
        assert b"secret" not in archive.read("logs/defw_py.log")
        assert b"[REDACTED]" in archive.read("logs/defw_py.log")
    assert payload["mime_type"] == "application/zip"
    with pytest.raises(PermissionError):
        dashboard.service_archive("directory-service", "user-a")
    with pytest.raises(KeyError):
        dashboard.service_archive("unknown", "root")


def test_artifact_download_uses_captured_owner(tmp_path) -> None:
    import base64
    from qfw_slurm_dashboard.models import Experiment
    dashboard = service(tmp_path)
    experiment = Experiment(
        "exp", "user-a", "nwqsim", "qiskit-simple", "normal"
    )
    experiment.artifacts = ["/workspace/home/user-a/result.json"]
    dashboard.store.save_experiment(experiment)
    encoded = base64.b64encode(b"result\n").decode()
    with patch.object(dashboard.runner, "cluster") as cluster:
        cluster.return_value = CommandResult(("python3",), 0, encoded, "")
        payload = dashboard.artifact("exp", 0, "user-a")
    assert payload["size"] == 7
    assert payload["name"] == "result.json"
    assert cluster.call_args.args[0] == "user-a"
    with pytest.raises(PermissionError):
        dashboard.artifact("exp", 0, "user-b")


def test_preview_rejects_unbounded_hardware_request(tmp_path) -> None:
    with pytest.raises(ValueError, match="time_minutes"):
        service(tmp_path).command_preview({
            "identity": "user-a", "backend": "iqm", "time_minutes": 16,
        })


def test_chemistry_requires_workspace_application_path(tmp_path) -> None:
    with pytest.raises(ValueError, match="application path"):
        service(tmp_path).submit_experiment({
            "identity": "user-a", "backend": "nwqsim",
            "example": "chemistry", "application_path": "relative.py",
        })


def test_chemistry_submission_sets_application_directory(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch("qfw_slurm_dashboard.service.threading.Thread", ImmediateThread):
        with patch.object(dashboard.runner, "cluster") as cluster:
            cluster.return_value = CommandResult(("sbatch",), 0, "42\n", "")
            dashboard.submit_experiment({
                "identity": "user-a",
                "backend": "iqm",
                "example": "chemistry",
                "application_path": "/workspace/apps/chemistry/run.py",
                "submit_real_hardware": True,
            })
    batch = written_batch_script(cluster)
    assert "QFW_CHEM_APP_DIR=/workspace/apps/chemistry" in batch
    assert "QFW_RUN_ALL_CHEM_APP=/workspace/apps/chemistry/run.py" in batch


def test_custom_python_application_runs_inside_activated_qfw(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch("qfw_slurm_dashboard.service.threading.Thread", ImmediateThread):
        with patch.object(dashboard.runner, "cluster") as cluster:
            cluster.return_value = CommandResult(("sbatch",), 0, "42\n", "")
            experiment = dashboard.submit_experiment({
                "identity": "user-a",
                "backend": "nwqsim",
                "application_source": "path",
                "application_path": "/workspace/home/user-a/app.py",
            })
    batch = written_batch_script(cluster)
    assert "source /opt/openqse/qfw/bin/qfw-activate" in batch
    assert "cd /workspace/home/user-a" in batch
    assert "python3 /workspace/home/user-a/app.py" in batch
    assert "qfw-deactivate" in batch
    assert experiment.example == "custom"


def test_custom_executable_arguments_are_quoted_in_generated_batch(tmp_path) -> None:
    preview = service(tmp_path).preview_experiment({
        "identity": "user-a",
        "backend": "nwqsim",
        "application_source": "path",
        "application_submission_type": "executable",
        "application_path": "/workspace/home/user-a/run_app",
        "application_arguments": "--alpha 'two words' --count 3",
    })

    assert preview["application_batch_script_save_path"] == (
        "/workspace/home/user-a/run_app.qfw.sbatch"
    )
    assert "batch_script" in preview
    assert (
        "/workspace/home/user-a/run_app --alpha 'two words' --count 3"
        in preview["batch_script"]
    )


def test_custom_executable_submission_uses_edited_batch_script(tmp_path) -> None:
    dashboard = service(tmp_path)
    edited = "#!/usr/bin/env bash\n#SBATCH --job-name=edited\n/bin/true\n"
    experiment_id = "43645c5c-c6b5-43fc-8982-64c331dd2cd5"
    with patch("qfw_slurm_dashboard.service.threading.Thread", ImmediateThread):
        with patch.object(dashboard.runner, "cluster") as cluster:
            cluster.return_value = CommandResult(("sbatch",), 0, "42\n", "")
            experiment = dashboard.submit_experiment({
                "experiment_id": experiment_id,
                "identity": "user-a",
                "backend": "nwqsim",
                "application_source": "path",
                "application_submission_type": "executable",
                "application_path": "/workspace/home/user-a/app.py",
                "batch_script": edited,
            })

    assert written_batch_script(cluster) == edited
    assert experiment.manifest["batch_script_sha256"]


def test_existing_sbatch_application_submits_path_directly(tmp_path) -> None:
    dashboard = service(tmp_path)
    with patch("qfw_slurm_dashboard.service.threading.Thread", ImmediateThread):
        with patch.object(dashboard.runner, "cluster") as cluster:
            cluster.return_value = CommandResult(("sbatch",), 0, "42\n", "")
            experiment = dashboard.submit_experiment({
                "identity": "user-a",
                "backend": "nwqsim",
                "application_source": "path",
                "application_submission_type": "sbatch",
                "application_path": "/workspace/home/user-a/app.sbatch",
            })

    assert cluster.call_args.args[1] == (
        "sbatch", "--parsable", "/workspace/home/user-a/app.sbatch"
    )
    assert not any(call.args[1][0:2] == ("python3", "-c")
                   for call in cluster.call_args_list)
    assert experiment.manifest["batch_script_path"] == (
        "/workspace/home/user-a/app.sbatch"
    )
    assert "batch_script_sha256" not in experiment.manifest


def test_save_application_batch_script_writes_beside_application(tmp_path) -> None:
    dashboard = service(tmp_path)
    script = "#!/usr/bin/env bash\n/bin/true\n"
    with patch.object(dashboard.runner, "cluster") as cluster:
        cluster.return_value = CommandResult(("python3",), 0, "", "")
        result = dashboard.save_application_batch_script({
            "identity": "user-a",
            "backend": "nwqsim",
            "application_source": "path",
            "application_submission_type": "executable",
            "application_path": "/workspace/home/user-a/app.py",
            "batch_script": script,
        })

    assert result == {
        "outcome": "success",
        "path": "/workspace/home/user-a/app.qfw.sbatch",
    }
    assert written_script_for_path(
        cluster, "/workspace/home/user-a/app.qfw.sbatch"
    ) == script


def test_tagged_driver_results_recover_reservation() -> None:
    records = DashboardService._tagged_json(
        'noise QFW_SLURM_DRIVER_RESULT {"reservation_id":"8","backend":"nwqsim"}',
        "QFW_SLURM_DRIVER_RESULT",
    )
    assert records == [{"reservation_id": "8", "backend": "nwqsim"}]


def test_refresh_recovers_reservation_from_application_log(tmp_path) -> None:
    from qfw_slurm_dashboard.models import Experiment
    dashboard = service(tmp_path)
    stored = Experiment("exp", "user-a", "iqm", "chemistry", "normal")
    stored.slurm_job_id = "42"
    stored.artifacts = ["/workspace/home/user-a/output"]
    dashboard.store.save_experiment(stored)
    summary = {
        "kind": "wrapper", "event": "finish", "status": "ok",
        "rc": 0, "teardown_rc": 0,
    }
    responses = iter((
        CommandResult(("sacct",), 0, "42|COMPLETED|0:0\n", ""),
        CommandResult(
            ("tail",), 0,
            "log=/workspace/home/user-a/case.log\n"
            "Summary JSONL: /workspace/home/user-a/summary.jsonl\n", "",
        ),
        CommandResult(("cat",), 0, __import__("json").dumps(summary), ""),
        CommandResult(("tail",), 0, "Estimator reservation_id=17\n", ""),
    ))
    with patch.object(
        dashboard.runner, "cluster", side_effect=lambda *a, **k: next(responses)
    ):
        dashboard._refresh_experiments()
    assert dashboard.store.experiments()[0]["reservations"] == [["iqm", "17"]]


@pytest.mark.parametrize(
    ("slurm_state", "terminal", "records", "expected"),
    [
        ("COMPLETED", True, [], "none"),
        ("CANCELLED", False, [], "cancellation"),
        ("TIMEOUT", False, [], "timeout"),
        ("COMPLETED", False, [], "incomplete"),
        ("COMPLETED", False, [{"error": "provider failed"}], "provider"),
        ("FAILED", False, [{"error": "application"}], "slurm"),
    ],
)
def test_failure_classification(slurm_state, terminal, records, expected) -> None:
    assert DashboardService._failure_classification(
        slurm_state, terminal, records
    ) == expected
