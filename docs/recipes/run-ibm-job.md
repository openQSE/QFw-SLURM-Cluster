# Run a circuit against IBM Quantum System devices

The `qfw_ibm_simple.sh` and `qfw_qrmi_ibm.sh` scripts are documented in the [QFW/examples/README.md](https://github.com/openQSE/QFw/blob/main/examples/README.md). This recipe explains how to run them in the container-based slurm cluster provided by this repository.

**The examples below run circuits against the `ibm-fake-lagos` device provided by the `qsa-sim`, which must be started and configured as described in [start-ibm-qsa-sim.md](./start-ibm-qsa-sim.md).**

## 1. Using `qfw_ibm_simple.sh`

`qfw_ibm_simple.sh` is a simple script used to run a Qiskit circuit in QFw against IBM devices. You could easily reuse it to run your own Qiskit circuit by replacing the python file it runs at the end (`tests/test_ibm_simple.py`).

### 1.1. With `--service-mode site`

This is an end-to-end job execution with slurm and QFw. The slurm resource reservation request goes through the site QPM. More details in the [detailed QFw slurm workflow](https://github.com/openQSE/qfw-slurm/blob/main/docs/detailed-design-workflow.md).

First, connect to `slurmctld` as `user-a` and allocate resources. That will grant you a reservation through the site QPM that is running in the container `qsa-sim-head`.

```bash
./do_ssh.sh --user user-a
salloc --partition=normal \
  --nodes=1 \
  --ntasks=1 \
  --time=00:10:00 \
  --qpu=ibm-fake-lagos \
  --workload-kind=quantum \
  --circ-count=1 \
  --max-qubits=5 \
  --max-depth=20 \
  --max-shots=1024 \
  --account qfw-test
```

Then, run the quantum circuit in the granted allocation.

```bash
export QFW_SHARED_ROOT=/workspace/qfw-container-base
# Uncomment the line below only if you want to use the QFw installed
# with "./do_qfw_build.sh" rather than the QFw that comes in the
# container image.
#export QFW_PREFIX=$QFW_SHARED_ROOT/qfw-install
source $QFW_PREFIX/bin/qfw-activate --venv $QFW_PREFIX/../qfw-venv
cd $QFW_SHARE_DIR/examples
./qfw_ibm_simple.sh --service-mode site
```

At the bottom, a successful run should print messages like below. It should also include RESULT fields such as `metrics.counts` and circuit parameter values. The `"service_id": "shim-ibm-fake-lagos"` in the output indicates that the site QPM was used.

```text
QFW_EXAMPLE_RESULT {
  "args": [],
  "duration_sec": 21.0,
  "event": "finish",
  "example": "qfw_ibm_simple",
  "kind": "wrapper",
  "rc": 0,
  "schema": "qfw-example-wrapper-v1",
  "status": "ok",
  "teardown_rc": 0,
  "timestamp_ns": 1793220531311956940
}
```

### 1.2. With `--service-mode local`

You can run this example inside or outside a slurm allocation.

The default value for `--service-mode` is `local` so we can omit it from the command line. However, we must set the `QFW_IBM_LOCAL_DEVICE_CONFIG` variable to the device configuration.

```bash
./do_ssh.sh --user user-a
export QFW_SHARED_ROOT=/workspace/qfw-container-base
# Uncomment the line below only if you want to use the QFw installed
# with "./do_qfw_build.sh" rather than the QFw that comes in the
# container image.
#export QFW_PREFIX=$QFW_SHARED_ROOT/qfw-install
source $QFW_PREFIX/bin/qfw-activate --venv $QFW_PREFIX/../qfw-venv
cd $QFW_SHARE_DIR/examples
QFW_IBM_LOCAL_DEVICE_CONFIG=/mnt/qsa-sim-device-access.yaml ./qfw_ibm_simple.sh
```

At the bottom, a successful run should print messages like below. And also, it should include RESULT fields such as `metrics.counts` and circuit parameter values. The `"service_id": "shim_ibm_local_qpm-928cfdcc5d025f5db7e9923126fc5c9d"` in the output indicates that the local QPM was used.

```text
QFW_EXAMPLE_RESULT {
  "args": [],
  "duration_sec": 37.0,
  "event": "finish",
  "example": "qfw_ibm_simple",
  "kind": "wrapper",
  "rc": 0,
  "schema": "qfw-example-wrapper-v1",
  "status": "ok",
  "teardown_rc": 0,
  "timestamp_ns": 1793220617060732705
}
```

## 2. Using `qfw_qrmi_ibm.sh`

The `qfw_qrmi_ibm.sh` does not involve QPM, you could run it inside or outside a slurm allocation, using your preferred user.

The example below shows how to run it in the `slurmctld` node using the user `user-a`.

```bash
./do_ssh.sh --user user-a
export QFW_SHARED_ROOT=/workspace/qfw-container-base
# Uncomment the line below only if you want to use the QFw installed
# with "./do_qfw_build.sh" rather than the QFw that comes in the
# container image.
#export QFW_PREFIX=$QFW_SHARED_ROOT/qfw-install
source $QFW_PREFIX/bin/qfw-activate --venv $QFW_PREFIX/../qfw-venv
cd $QFW_SHARE_DIR/examples
QFW_IBM_LOCAL_DEVICE_CONFIG=/mnt/qsa-sim-device-access.yaml ./qfw_qrmi_ibm.sh
```

At the bottom, a successful run should print messages like below. It should also include Qiskit circuit compilation passes and calls to each qrmi_driver capability.

```text
<...>
2026-10-28 20:56:05,500 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: FixedPoint - 0.00381 (ms)
2026-10-28 20:56:05,500 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: Size - 0.00143 (ms)
2026-10-28 20:56:05,500 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: FixedPoint - 0.00238 (ms)
2026-10-28 20:56:05,500 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: Optimize1qGatesDecomposition - 0.01812 (ms)
2026-10-28 20:56:05,500 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: InverseCancellation - 0.00548 (ms)
2026-10-28 20:56:05,500 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: ContractIdleWiresInControlFlow - 0.00095 (ms)
2026-10-28 20:56:05,500 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: GatesInBasis - 0.00334 (ms)
2026-10-28 20:56:05,500 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: Depth - 0.00453 (ms)
2026-10-28 20:56:05,500 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: FixedPoint - 0.00238 (ms)
2026-10-28 20:56:05,500 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: Size - 0.00095 (ms)
2026-10-28 20:56:05,500 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: FixedPoint - 0.00191 (ms)
2026-10-28 20:56:05,500 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: ContainsInstruction - 0.00358 (ms)
2026-10-28 20:56:05,500 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: InstructionDurationCheck - 0.00477 (ms)
2026-10-28 20:56:05,508 - root - [INFO] - ibm_transcode.py:qiskit_sampler_input_json() -> Circuit param_values used: {'th[0]': 0.1, 'th[1]': 0.2, 'th[2]': 0.3}
2026-10-28 20:56:07,646 - root - [INFO] - test_qrmi_ibm.py:<module>() -> Call get_task_timing
2026-10-28 20:56:07,646 - root - [INFO] - test_qrmi_ibm.py:<module>() -> get_task_timing = {'cid': '7f55b00d-fd9f-4ea5-8b21-ff4703480356', 'job_id': '50cab744-35e6-48ea-a849-b00ee3fbd7ea', 'status': 'completed', 'timing': {'submit_seconds': 0.02821160387247801, 'wait_seconds': 2.0104156150482595, 'result_fetch_seconds': 0.007525853114202619, 'total_wall_seconds': 2.046159294899553}}
2026-10-28 20:56:07,646 - root - [INFO] - test_qrmi_ibm.py:<module>() -> Call get_task_metadata
2026-10-28 20:56:07,646 - root - [INFO] - test_qrmi_ibm.py:<module>() -> get_task_metadata = {'cid': '7f55b00d-fd9f-4ea5-8b21-ff4703480356', 'job_id': '50cab744-35e6-48ea-a849-b00ee3fbd7ea', 'status': 'completed', 'shots': 128, 'backend': 'ibm'}
2026-10-28 20:56:07,646 - root - [INFO] - test_qrmi_ibm.py:<module>() -> All checks passed
[Wed Oct 28 20:56:09 UTC 2026] ./qfw_qrmi_ibm.sh done on c1

```